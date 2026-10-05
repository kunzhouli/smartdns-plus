#!/usr/bin/python3
"""Manage SmartDNS GeoSite rules and data on Debian."""

import fcntl
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(os.environ.get("SMARTDNS_GEOPATH", "/etc/smartdns"))
CONFIG = ROOT / "geosite.json"
DATA = ROOT / "geosite.dat"
RULES = ROOT / "geosite.conf"
STAMP = ROOT / "geosite.updated"
LOCK = ROOT / "geosite.lock"
SMARTDNS = os.environ.get("SMARTDNS_BIN", "/usr/sbin/smartdns")
DEFAULT_SOURCE = "https://github.com/v2fly/domain-list-community/releases/latest/download/dlc.dat"
TOKEN = re.compile(r"^[A-Za-z0-9_.!-]+(?:@[A-Za-z0-9_.-]+)?$")
GROUP = re.compile(r"^[A-Za-z0-9_.-]+$")
MAX_DOWNLOAD = 64 * 1024 * 1024


def defaults():
    return {"source": DEFAULT_SOURCE, "github_proxy": "", "auto_update": False,
            "interval_hours": 24, "rules": []}


def validate_url(value, optional=False):
    if not isinstance(value, str):
        raise ValueError("Source and proxy must be URLs")
    if optional and not value:
        return ""
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Source and proxy must be HTTP(S) URLs without credentials")
    return value


def validate(raw):
    if not isinstance(raw, dict):
        raise ValueError("Expected a JSON object")
    result = defaults()
    result.update({key: raw[key] for key in result if key in raw})
    result["source"] = validate_url(result["source"])
    result["github_proxy"] = validate_url(result["github_proxy"], True)
    if not isinstance(result["auto_update"], bool):
        raise ValueError("auto_update must be a boolean")
    if type(result["interval_hours"]) is not int or not 1 <= result["interval_hours"] <= 8760:
        raise ValueError("interval_hours must be between 1 and 8760")
    if not isinstance(result["rules"], list) or len(result["rules"]) > 100:
        raise ValueError("rules must be a list with at most 100 entries")
    for rule in result["rules"]:
        if not isinstance(rule, dict):
            raise ValueError("Invalid rule")
        site = rule.get("site", "")
        group = rule.get("group", "")
        action = rule.get("action", "route")
        if not isinstance(site, str) or not TOKEN.fullmatch(site):
            raise ValueError("Invalid GeoSite category")
        if action not in ("route", "block"):
            raise ValueError("Invalid rule action")
        if action == "route" and (not isinstance(group, str) or not GROUP.fullmatch(group)):
            raise ValueError("A route rule needs a nameserver group")
        rule.clear()
        rule.update({"site": site, "action": action, "group": group if action == "route" else ""})
    return result


def read_config():
    return validate(json.loads(CONFIG.read_text())) if CONFIG.exists() else defaults()


def atomic_write(path, data):
    fd, name = tempfile.mkstemp(prefix=".geosite-", dir=ROOT)
    try:
        with os.fdopen(fd, "wb") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.chmod(name, 0o644)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def check_data(path, rules):
    sites = {rule["site"] for rule in rules}
    for site in sites or {None}:
        args = [SMARTDNS, "--check-geosite", str(path)]
        if site:
            args.append(site)
        done = subprocess.run(args, capture_output=True, text=True, timeout=60)
        if done.returncode:
            raise ValueError((done.stderr or done.stdout or "Invalid GeoSite data").strip())


def config_text(config):
    lines = ["# Managed by geosite-manager.py; edit geosite.json through the Web UI.\n"]
    if DATA.exists():
        # SmartDNS replaces an earlier rule of the same type for an overlapping
        # domain. Emit the lowest priority first so the first UI row wins.
        for index in range(len(config["rules"]) - 1, -1, -1):
            rule = config["rules"][index]
            name = f"geosite-{index}"
            lines.append(f"domain-set -name {name} -type geosite -site {rule['site']} -file {DATA}\n")
            option = f"-nameserver {rule['group']}" if rule["action"] == "route" else "-address #"
            lines.append(f"domain-rules /domain-set:{name}/ {option}\n")
    return "".join(lines).encode()


def download(config):
    url = config["source"]
    if config["github_proxy"] and urllib.parse.urlsplit(url).hostname == "github.com":
        url = config["github_proxy"].rstrip("/") + "/" + url
    request = urllib.request.Request(url, headers={"User-Agent": "smartdns-geosite/1"})
    fd, name = tempfile.mkstemp(prefix=".geosite-download-", dir=ROOT)
    try:
        with os.fdopen(fd, "wb") as output, urllib.request.urlopen(request, timeout=60) as response:
            if urllib.parse.urlsplit(response.url).scheme not in ("http", "https"):
                raise ValueError("Unexpected download URL")
            total = 0
            while chunk := response.read(65536):
                total += len(chunk)
                if total > MAX_DOWNLOAD:
                    raise ValueError("GeoSite data exceeds 64 MiB")
                output.write(chunk)
        check_data(name, config["rules"])
        os.chmod(name, 0o644)
        os.replace(name, DATA)
        atomic_write(STAMP, str(int(time.time())).encode())
    finally:
        if os.path.exists(name):
            os.unlink(name)


def show():
    result = read_config()
    result["has_data"] = DATA.exists()
    result["last_update"] = int(STAMP.read_text()) if STAMP.exists() else None
    return result


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("show", "save", "update", "scheduled"):
        raise ValueError("Usage: geosite-manager.py show|save|update|scheduled")
    ROOT.mkdir(mode=0o755, parents=True, exist_ok=True)
    with LOCK.open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        command = sys.argv[1]
        if command == "save":
            config = validate(json.load(sys.stdin))
            if config["rules"]:
                previous = read_config()
                if DATA.exists() and config["source"] == previous["source"] and config["github_proxy"] == previous["github_proxy"]:
                    check_data(DATA, config["rules"])
                else:
                    download(config)
            atomic_write(CONFIG, (json.dumps(config, indent=2) + "\n").encode())
            atomic_write(RULES, config_text(config))
            return {"changed": True, **show()}
        if command in ("update", "scheduled"):
            config = read_config()
            due = not STAMP.exists() or time.time() - int(STAMP.read_text()) >= config["interval_hours"] * 3600
            if command == "scheduled" and (not config["auto_update"] or not due):
                return {"changed": False, **show()}
            download(config)
            atomic_write(RULES, config_text(config))
            return {"changed": True, **show()}
        return show()


if __name__ == "__main__":
    try:
        print(json.dumps(main()))
    except (OSError, ValueError, TimeoutError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"error": str(error)}))
        sys.exit(1)
