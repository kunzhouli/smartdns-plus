#!/usr/bin/python3
"""Manage explicit domain-to-nameserver routing rules for SmartDNS."""

import fcntl
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(os.environ.get("SMARTDNS_DOMAIN_ROUTES_PATH", "/etc/smartdns"))
CONFIG = ROOT / "domain-routes.json"
RULES = ROOT / "domain-routes.conf"
LOCK = ROOT / "domain-routes.lock"
GROUP = re.compile(r"[A-Za-z0-9_.-]{1,63}\Z")
LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\Z")
HEADER = b"# Managed by domain-routes-manager.py; edit through the Web UI.\n"


def defaults():
    return {"rules": []}


def validate(raw):
    if not isinstance(raw, dict) or set(raw) - {"rules"}:
        raise ValueError("Expected domain routing rules")
    entries = raw.get("rules", [])
    if not isinstance(entries, list) or len(entries) > 200:
        raise ValueError("At most 200 domain routing rules are supported")
    cleaned = []
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"domain", "group"}:
            raise ValueError("Each rule needs a domain and nameserver group")
        domain, group = entry["domain"], entry["group"]
        if not isinstance(domain, str) or not isinstance(group, str):
            raise ValueError("Domain and nameserver group must be text")
        domain = domain.strip().lower().rstrip(".")
        if domain.startswith(("*.", "-.")):
            name = domain[2:]
        else:
            name = domain
        if not name or len(name) > 253 or any(not LABEL.fullmatch(label) for label in name.split(".")):
            raise ValueError(f"Invalid domain: {domain}")
        if not GROUP.fullmatch(group) or group in ("default", "-"):
            raise ValueError(f"Invalid nameserver group: {group}")
        if domain in seen:
            raise ValueError(f"Duplicate domain: {domain}")
        seen.add(domain)
        cleaned.append({"domain": domain, "group": group})
    return {"rules": cleaned}


def render(config):
    return HEADER + "".join(
        f"domain-rules /{rule['domain']}/ -nameserver {rule['group']}\n"
        for rule in config["rules"]
    ).encode()


def atomic_write(path, data):
    fd, name = tempfile.mkstemp(prefix=".domain-routes-", dir=ROOT)
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


def read_config():
    return validate(json.loads(CONFIG.read_text())) if CONFIG.exists() else defaults()


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("show", "save"):
        raise ValueError("Usage: domain-routes-manager.py show|save")
    ROOT.mkdir(mode=0o755, parents=True, exist_ok=True)
    with LOCK.open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if sys.argv[1] == "show":
            return read_config()
        config = validate(json.load(sys.stdin))
        if RULES.exists() and not RULES.read_bytes().startswith(HEADER):
            raise ValueError("domain-routes.conf is not Web UI managed")
        previous_config = CONFIG.read_bytes() if CONFIG.exists() else None
        previous_rules = RULES.read_bytes() if RULES.exists() else None
        try:
            atomic_write(CONFIG, (json.dumps(config, indent=2) + "\n").encode())
            atomic_write(RULES, render(config))
        except OSError:
            if previous_config is None:
                CONFIG.unlink(missing_ok=True)
            else:
                atomic_write(CONFIG, previous_config)
            if previous_rules is None:
                RULES.unlink(missing_ok=True)
            else:
                atomic_write(RULES, previous_rules)
            raise
        return config


if __name__ == "__main__":
    try:
        print(json.dumps(main()))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"error": str(error)}))
        sys.exit(1)
