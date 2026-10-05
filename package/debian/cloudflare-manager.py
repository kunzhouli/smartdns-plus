#!/usr/bin/python3
"""Schedule CloudflareSpeedTest and render SmartDNS response IP aliases."""

import csv
import codecs
import datetime as dt
import fcntl
import ipaddress
import json
import math
import os
import re
import signal
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(os.environ.get("SMARTDNS_CFPATH", "/etc/smartdns"))
CONFIG = ROOT / "cloudflare.json"
STATE = ROOT / "cloudflare-state.json"
RULES = ROOT / "cloudflare.conf"
LOCK = ROOT / "cloudflare.lock"
LOG = ROOT / "cloudflare-run.log"
CFST = os.environ.get("SMARTDNS_CFST_BIN", "/usr/lib/smartdns/cfst")
REMOTE_COMMAND = "/usr/lib/smartdns/cloudflare-cfst-remote"
RANGES_URL = "https://api.cloudflare.com/client/v4/ips"
TIME = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
PROGRESS = re.compile(r"\b\d+\s*/\s*\d+\s*\[[^\]\r\n]{1,200}\](?:\s*可用:\s*\d+)?")
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
ACTIVE_PROCESS = None


class TestStopped(Exception):
    def __init__(self):
        super().__init__("Stopped by user")


def defaults():
    return {"enabled": False, "schedule_enabled": False, "run_time": "03:00", "interval_days": 1,
            "ipv6_enabled": True, "threads": 40, "test_runner": "local",
            "remote_host": "", "remote_user": "cfst", "remote_port": 22,
            "remote_key": "/etc/smartdns/cfst-ssh-key"}


def validate(raw):
    if not isinstance(raw, dict):
        raise ValueError("Expected a JSON object")
    config = defaults()
    config.update({key: raw[key] for key in config if key in raw})
    if any(not isinstance(config[key], bool) for key in ("enabled", "schedule_enabled", "ipv6_enabled")):
        raise ValueError("Enabled, schedule, and IPv6 options must be booleans")
    if not isinstance(config["run_time"], str) or not TIME.fullmatch(config["run_time"]):
        raise ValueError("run_time must be HH:MM (local time)")
    if type(config["interval_days"]) is not int or not 1 <= config["interval_days"] <= 365:
        raise ValueError("interval_days must be between 1 and 365")
    if type(config["threads"]) is not int or not 1 <= config["threads"] <= 200:
        raise ValueError("threads must be between 1 and 200")
    if config["test_runner"] not in ("local", "ssh"):
        raise ValueError("test_runner must be local or ssh")
    if not isinstance(config["remote_host"], str) or (config["remote_host"] and
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.:-]*", config["remote_host"])):
        raise ValueError("Invalid remote host")
    if config["test_runner"] == "ssh" and not config["remote_host"]:
        raise ValueError("Remote host is required for SSH speed tests")
    if not isinstance(config["remote_user"], str) or not re.fullmatch(r"[a-z_][a-z0-9_-]*", config["remote_user"]):
        raise ValueError("Invalid remote user")
    if type(config["remote_port"]) is not int or not 1 <= config["remote_port"] <= 65535:
        raise ValueError("Invalid remote SSH port")
    if not isinstance(config["remote_key"], str) or not config["remote_key"].startswith("/") or any(c in config["remote_key"] for c in "\r\n\0"):
        raise ValueError("Remote SSH key must be an absolute path")
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


def log_event(message):
    with LOG.open("a", encoding="utf-8") as output:
        output.write(f"[{dt.datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")


def clean_log(text):
    text = ANSI.sub("", PROGRESS.sub("", text))
    return "\n".join(line.strip() for line in text.replace("\r", "\n").splitlines() if line.strip())


def read_log():
    if not LOG.exists():
        return ""
    with LOG.open("rb") as source:
        size = source.seek(0, os.SEEK_END)
        source.seek(max(0, size - 2 * 1024 * 1024))
        data = source.read().decode("utf-8", errors="replace")
        if size > 2 * 1024 * 1024:
            data = data.partition("\n")[2]
        return clean_log(data)[-65536:]


def stream_log(source):
    """Keep diagnostic lines while dropping CloudflareSpeedTest's animated progress."""
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    pending = ""
    with LOG.open("a", encoding="utf-8") as output:
        while chunk := source.read(4096):
            pending += decoder.decode(chunk)
            while "\n" in pending:
                line, pending = pending.split("\n", 1)
                line = clean_log(line)
                if line:
                    output.write(line + "\n")
                    output.flush()
            if len(pending) > 8192:
                pending = pending[-512:]
                match = PROGRESS.search(pending)
                if match:
                    pending = pending[match.start():]
        pending += decoder.decode(b"", final=True)
        line = clean_log(pending)
        if line:
            output.write(line + "\n")
            output.flush()


def process_alive(pid):
    if type(pid) is not int or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        stat = Path(f"/proc/{pid}/stat")
        fields = stat.read_text().split(") ", 1) if stat.exists() else []
        if len(fields) == 2 and fields[1].startswith("Z"):
            return False
        return True
    except OSError:
        return False


def is_manager_process(pid):
    try:
        args = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
    except OSError:
        return False
    return os.fsencode(Path(__file__).resolve()) in args and any(
        arg in (b"run", b"run-restart", b"scheduled") for arg in args)


def stop_test():
    state = read_state()
    pid = state.get("run_pid")
    if not state.get("running") or not process_alive(pid):
        return {"changed": False, **status()}
    if not is_manager_process(pid):
        raise ValueError("Cannot safely identify the running speed test")
    os.kill(pid, signal.SIGTERM)
    for _ in range(100):
        if not process_alive(pid):
            break
        time.sleep(0.05)
    if process_alive(pid):
        raise ValueError("Timed out stopping the speed test")
    state = read_state()
    if state.get("run_pid") == pid and state.get("running"):
        state["running"] = False
        state.pop("run_pid", None)
        state["last_error"] = ""
        save_json(STATE, state)
        log_event("Cloudflare speed test stopped by user")
    return {"changed": True, **status()}


def handle_stop(_signum, _frame):
    if ACTIVE_PROCESS is not None and ACTIVE_PROCESS.poll() is None:
        try:
            os.killpg(ACTIVE_PROCESS.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    raise TestStopped()


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


def runner_available(config):
    if config["test_runner"] == "ssh":
        return bool(shutil.which("ssh") and os.access(config["remote_key"], os.R_OK))
    return os.access(CFST, os.X_OK)


def run_logged_command(args, tempdir, source, results, remote):
    global ACTIVE_PROCESS
    with subprocess.Popen(args, cwd=tempdir, stdin=source,
                          stdout=results if remote else subprocess.PIPE,
                          stderr=subprocess.PIPE if remote else subprocess.STDOUT,
                          start_new_session=True) as process:
        ACTIVE_PROCESS = process
        reader = threading.Thread(target=stream_log,
                                  args=(process.stderr if remote else process.stdout,), daemon=True)
        reader.start()
        try:
            returncode = process.wait(timeout=600)
        except BaseException:
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            raise
        finally:
            ACTIVE_PROCESS = None
            reader.join(timeout=5)
        return returncode


def speedtest(networks, family, config, tempdir):
    input_path = Path(tempdir) / f"ips-v{family}.txt"
    output_path = Path(tempdir) / f"result-v{family}.csv"
    input_path.write_text("\n".join(str(network) for network in networks) + "\n")
    if config["test_runner"] == "ssh":
        args = ["ssh", "-T", "-i", config["remote_key"], "-p", str(config["remote_port"]),
                "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
                "-o", "ConnectTimeout=10", "-o", "UserKnownHostsFile=/etc/smartdns/cfst-known-hosts",
                f"{config['remote_user']}@{config['remote_host']}", REMOTE_COMMAND, str(config["threads"])]
    else:
        args = [CFST, "-f", str(input_path), "-o", str(output_path), "-p", "0",
                "-n", str(config["threads"]), "-t", "2", "-dn", "5", "-dt", "5", "-tl", "1000"]
    if config["test_runner"] == "ssh":
        with input_path.open("rb") as source, output_path.open("wb") as results:
            returncode = run_logged_command(args, tempdir, source, results, True)
    else:
        returncode = run_logged_command(args, tempdir, subprocess.DEVNULL, None, False)
    if returncode:
        raise ValueError(f"CloudflareSpeedTest exited with status {returncode}")
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
    state = read_state()
    state["running"] = bool(state.get("running") and process_alive(state.get("run_pid")))
    state.pop("run_pid", None)
    config = read_config()
    return {**config, **state, "log": read_log(), "cfst_available": runner_available(config)}


def run_test(config, state):
    previous_handler = signal.signal(signal.SIGTERM, handle_stop)
    LOG.write_text("")
    log_event("Cloudflare speed test started")
    state["running"] = True
    state["run_pid"] = os.getpid()
    state["last_attempt"] = int(time.time())
    save_json(STATE, state)
    errors = []
    changed = False
    try:
        log_event("Fetching Cloudflare IP ranges")
        ranges = read_ranges()
        with tempfile.TemporaryDirectory(prefix="smartdns-cfst-") as tempdir:
            for family in (4, 6):
                if family == 6 and not config["ipv6_enabled"]:
                    continue
                try:
                    log_event(f"Testing IPv{family}")
                    best = speedtest(ranges[family], family, config, tempdir)
                    log_event(f"IPv{family} selected: {best}")
                    state[f"best_v{family}"] = best
                    state[f"ranges_v{family}"] = [str(network) for network in ranges[family]]
                    changed = True
                except (OSError, ValueError, subprocess.TimeoutExpired) as error:
                    log_event(f"IPv{family} failed: {error}")
                    errors.append(f"IPv{family}: {error}")
        if not changed:
            raise ValueError("; ".join(errors) or "CloudflareSpeedTest failed")
        atomic_write(RULES, rule_text(config, state))
        state["last_success"] = int(time.time())
        state["last_error"] = "; ".join(errors)
        state["running"] = False
        state.pop("run_pid", None)
        save_json(STATE, state)
        log_event("Cloudflare speed test completed")
        return {"changed": True, **status()}
    except TestStopped:
        state = read_state()
        state["last_error"] = ""
        state["running"] = False
        state.pop("run_pid", None)
        save_json(STATE, state)
        log_event("Cloudflare speed test stopped by user")
        raise
    except (OSError, ValueError) as error:
        state["last_error"] = str(error)
        state["running"] = False
        state.pop("run_pid", None)
        save_json(STATE, state)
        log_event(f"Cloudflare speed test failed: {error}")
        raise
    finally:
        signal.signal(signal.SIGTERM, previous_handler)


def due(config, state):
    if not config["schedule_enabled"]:
        return False
    now = dt.datetime.now()
    hour, minute = map(int, config["run_time"].split(":"))
    if now.time() < dt.time(hour, minute):
        return False
    last = state.get("last_attempt")
    return not last or (now.date() - dt.datetime.fromtimestamp(last).date()).days >= config["interval_days"]


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("show", "save", "start", "stop", "clear-log", "run", "run-restart", "scheduled"):
        raise ValueError("Usage: cloudflare-manager.py show|save|start|stop|clear-log|run|scheduled")
    ROOT.mkdir(mode=0o755, parents=True, exist_ok=True)
    if sys.argv[1] == "show":
        return status()
    command = sys.argv[1]
    if command == "clear-log":
        LOG.write_text("")
        return {"changed": True, **status()}
    if command == "stop":
        return stop_test()
    with LOCK.open("a+b") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | (fcntl.LOCK_NB if command == "start" else 0))
        except BlockingIOError:
            raise ValueError("Cloudflare speed test is already running") from None
        if command == "save":
            config = validate(json.load(sys.stdin))
            atomic_write(RULES, rule_text(config, read_state()))
            save_json(CONFIG, config)
            return {"changed": True, **status()}
        config, state = read_config(), read_state()
        if command == "start":
            if state.get("running") and process_alive(state.get("run_pid")):
                raise ValueError("Cloudflare speed test is already running")
            if not runner_available(config):
                raise ValueError("CloudflareSpeedTest runner is unavailable")
            child = subprocess.Popen([sys.executable, __file__, "run-restart"],
                                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL, start_new_session=True)
            state["running"] = True
            state["run_pid"] = child.pid
            save_json(STATE, state)
            return status()
        if command == "scheduled" and not due(config, state):
            return {"changed": False, **status()}
        result = run_test(config, state)
        if command == "run-restart" and config["enabled"]:
            log_event("Reloading SmartDNS to apply Cloudflare rules")
            try:
                restart = subprocess.run(["/bin/systemctl", "try-restart", "smartdns.service"],
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
                if restart.returncode:
                    log_event(f"SmartDNS restart failed with status {restart.returncode}")
            except (OSError, subprocess.TimeoutExpired) as error:
                log_event(f"SmartDNS restart failed: {error}")
        return result


if __name__ == "__main__":
    try:
        print(json.dumps(main()))
    except (OSError, ValueError, TestStopped, json.JSONDecodeError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"error": str(error)}))
        sys.exit(1)
