#!/usr/bin/python3
"""Schedule CloudflareSpeedTest and render SmartDNS response IP aliases."""

import csv
import datetime as dt
import fcntl
import ipaddress
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.parse
from pathlib import Path

ROOT = Path(os.environ.get("SMARTDNS_CFPATH", "/etc/smartdns"))
CONFIG = ROOT / "cloudflare.json"
STATE = ROOT / "cloudflare-state.json"
RULES = ROOT / "cloudflare.conf"
LOCK = ROOT / "cloudflare.lock"
CFST = os.environ.get("SMARTDNS_CFST_BIN", "/usr/lib/smartdns/cfst")
RANGES_URL = "https://api.cloudflare.com/client/v4/ips"
TIME = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")


def defaults():
    return {"enabled": False, "run_time": "03:00", "interval_days": 1,
            "ipv6_enabled": True, "threads": 40,
            "test_url": "https://speed.cloudflare.com/__down?bytes=200000000"}


def validate(raw):
    if not isinstance(raw, dict):
        raise ValueError("Expected a JSON object")
    config = defaults()
    config.update({key: raw[key] for key in config if key in raw})
    if not isinstance(config["enabled"], bool) or not isinstance(config["ipv6_enabled"], bool):
        raise ValueError("Enabled and IPv6 options must be booleans")
    if not isinstance(config["run_time"], str) or not TIME.fullmatch(config["run_time"]):
        raise ValueError("run_time must be HH:MM (local time)")
    if type(config["interval_days"]) is not int or not 1 <= config["interval_days"] <= 365:
        raise ValueError("interval_days must be between 1 and 365")
    if type(config["threads"]) is not int or not 1 <= config["threads"] <= 200:
        raise ValueError("threads must be between 1 and 200")
    url = config["test_url"]
    if not isinstance(url, str) or len(url) > 2048 or any(char.isspace() for char in url):
        raise ValueError("Invalid speed test URL")
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Speed test URL must be HTTP(S) without credentials")
    return config


def load_json(path, fallback):
    return json.loads(path.read_text()) if path.exists() else fallback


def read_config():
    return validate(load_json(CONFIG, defaults()))


def read_state():
    state = load_json(STATE, {})
    return state if isinstance(state, dict) else {}


def atomic_write(path, data):
    fd, name = tempfile.mkstemp(prefix=".cloudflare-", dir=ROOT)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(name, 0o644)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def save_json(path, value):
    atomic_write(path, (json.dumps(value, indent=2) + "\n").encode())


def read_ranges():
    request = urllib.request.Request(RANGES_URL, headers={"User-Agent": "smartdns-cloudflare/1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = response.read(65537)
    if len(payload) > 65536:
        raise ValueError("Cloudflare IP ranges response is too large")
    result = json.loads(payload)
    if not isinstance(result, dict) or result.get("success") is not True or not isinstance(result.get("result"), dict):
        raise ValueError("Cloudflare IP ranges API returned an error")
    output = {}
    for family, key in ((4, "ipv4_cidrs"), (6, "ipv6_cidrs")):
        values = result["result"].get(key)
        if not isinstance(values, list) or not 1 <= len(values) <= 1000:
            raise ValueError(f"Invalid Cloudflare IPv{family} ranges")
        networks = [ipaddress.ip_network(value, strict=True) for value in values]
        if any(network.version != family or not network.is_global for network in networks):
            raise ValueError(f"Invalid Cloudflare IPv{family} ranges")
        output[family] = networks
    return output


def select_best(csv_path, networks, family):
    if not csv_path.exists() or csv_path.stat().st_size > 1024 * 1024:
        raise ValueError(f"CloudflareSpeedTest produced no valid IPv{family} results")
    with csv_path.open(newline="", encoding="utf-8-sig") as source:
        for row in csv.reader(source):
            if len(row) < 6:
                continue
            try:
                address = ipaddress.ip_address(row[0].strip())
                speed = float(row[5])
            except ValueError:
                continue
            if address.version == family and math.isfinite(speed) and speed > 0 and any(address in network for network in networks):
                return str(address)
    raise ValueError(f"CloudflareSpeedTest found no usable IPv{family} address")


def speedtest(networks, family, threads, test_url, tempdir):
    input_path = Path(tempdir) / f"ips-v{family}.txt"
    output_path = Path(tempdir) / f"result-v{family}.csv"
    input_path.write_text("\n".join(str(network) for network in networks) + "\n")
    args = [CFST, "-f", str(input_path), "-o", str(output_path), "-p", "0",
            "-n", str(threads), "-t", "2", "-dn", "5", "-dt", "5", "-tl", "1000",
            "-url", test_url]
    done = subprocess.run(args, cwd=tempdir, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, timeout=600)
    if done.returncode:
        raise ValueError((done.stderr or done.stdout or "CloudflareSpeedTest failed")[-500:])
    return select_best(output_path, networks, family)


def rule_text(config, state):
    lines = ["# Managed by cloudflare-manager.py; based on Cloudflare response IP ranges.\n"]
    if not config["enabled"]:
        return "".join(lines).encode()
    for family in (4, 6):
        if family == 6 and not config["ipv6_enabled"]:
            continue
        best = state.get(f"best_v{family}")
        ranges = state.get(f"ranges_v{family}", [])
        if not best or not isinstance(ranges, list):
            continue
        address = ipaddress.ip_address(best)
        if not any(address in ipaddress.ip_network(value, strict=True) for value in ranges):
            raise ValueError("Selected address is outside the Cloudflare ranges")
        for value in ranges:
            network = ipaddress.ip_network(value, strict=True)
            if address.version != family or network.version != family:
                raise ValueError("Cloudflare IP family mismatch")
            lines.append(f"ip-alias {network} {address}\n")
    return "".join(lines).encode()


def status():
    return {**read_config(), **read_state(), "cfst_available": os.access(CFST, os.X_OK)}


def run_test(config, state):
    state["last_attempt"] = int(time.time())
    save_json(STATE, state)
    errors = []
    changed = False
    try:
        ranges = read_ranges()
        with tempfile.TemporaryDirectory(prefix="smartdns-cfst-") as tempdir:
            for family in (4, 6):
                if family == 6 and not config["ipv6_enabled"]:
                    continue
                try:
                    best = speedtest(ranges[family], family, config["threads"], config["test_url"], tempdir)
                    state[f"best_v{family}"] = best
                    state[f"ranges_v{family}"] = [str(network) for network in ranges[family]]
                    changed = True
                except (OSError, ValueError, subprocess.TimeoutExpired) as error:
                    errors.append(f"IPv{family}: {error}")
        if not changed:
            raise ValueError("; ".join(errors) or "CloudflareSpeedTest failed")
        state["last_success"] = int(time.time())
        state["last_error"] = "; ".join(errors)
        save_json(STATE, state)
        atomic_write(RULES, rule_text(config, state))
        return {"changed": True, **status()}
    except (OSError, ValueError) as error:
        state["last_error"] = str(error)
        save_json(STATE, state)
        raise


def due(config, state):
    if not config["enabled"]:
        return False
    now = dt.datetime.now()
    hour, minute = map(int, config["run_time"].split(":"))
    if now.time() < dt.time(hour, minute):
        return False
    last = state.get("last_attempt")
    return not last or (now.date() - dt.datetime.fromtimestamp(last).date()).days >= config["interval_days"]


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("show", "save", "run", "scheduled"):
        raise ValueError("Usage: cloudflare-manager.py show|save|run|scheduled")
    ROOT.mkdir(mode=0o755, parents=True, exist_ok=True)
    with LOCK.open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        command = sys.argv[1]
        if command == "show":
            return status()
        if command == "save":
            config = validate(json.load(sys.stdin))
            atomic_write(RULES, rule_text(config, read_state()))
            save_json(CONFIG, config)
            return {"changed": True, **status()}
        config, state = read_config(), read_state()
        if command == "scheduled" and not due(config, state):
            return {"changed": False, **status()}
        return run_test(config, state)


if __name__ == "__main__":
    try:
        print(json.dumps(main()))
    except (OSError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"error": str(error)}))
        sys.exit(1)
