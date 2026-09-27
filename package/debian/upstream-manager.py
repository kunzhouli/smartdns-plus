#!/usr/bin/python3
"""Manage Web UI upstream servers without rewriting hand-maintained config."""

import fcntl
import ipaddress
import json
import os
import re
import sys
import tempfile
import urllib.parse
from pathlib import Path

ROOT = Path(os.environ.get("SMARTDNS_UPSTREAM_PATH", "/etc/smartdns"))
CONFIG = ROOT / "upstream.json"
RULES = ROOT / "upstream.conf"
LOCK = ROOT / "upstream.lock"
GROUP = re.compile(r"[A-Za-z0-9_.-]{1,63}\Z")
LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\Z")
SCHEMES = {"udp", "tcp", "tls", "https", "quic", "h3", "http3"}


def defaults():
    return {"groups": [], "servers": []}


def valid_host(host):
    if not host or len(host) > 253:
        return False
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return all(LABEL.fullmatch(part) for part in host.rstrip(".").split("."))


def valid_endpoint(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 2048:
        raise ValueError("Server address or URL is required")
    if any(ord(char) < 33 or ord(char) > 126 for char in value) or "#" in value:
        raise ValueError("Server address contains unsupported characters")
    has_scheme = "://" in value
    parsed = urllib.parse.urlsplit(value if has_scheme else "//" + value)
    if has_scheme and parsed.scheme not in SCHEMES:
        raise ValueError("Unsupported DNS protocol")
    if not valid_host(parsed.hostname) or parsed.username or parsed.password:
        raise ValueError("Invalid DNS server host")
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError("Invalid DNS server port") from error
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("Invalid DNS server port")
    if parsed.query or parsed.fragment:
        raise ValueError("DNS server URL cannot contain a query or fragment")
    if has_scheme and parsed.scheme in ("https", "h3", "http3"):
        if not parsed.path.startswith("/") or parsed.path == "/":
            raise ValueError("DoH URL needs a path such as /dns-query")
    elif parsed.path:
        raise ValueError("Only DoH URLs may contain a path")
    return value


def validate(raw):
    if not isinstance(raw, dict) or set(raw) - {"groups", "servers", "manual_servers"}:
        raise ValueError("Expected upstream groups and servers")
    groups = raw.get("groups", [])
    servers = raw.get("servers", [])
    if not isinstance(groups, list) or len(groups) > 64:
        raise ValueError("At most 64 server groups are supported")
    if not isinstance(servers, list) or len(servers) > 100:
        raise ValueError("At most 100 DNS servers are supported")
    cleaned_groups = []
    for name in groups:
        if not isinstance(name, str) or not GROUP.fullmatch(name) or name in ("default", "-"):
            raise ValueError("Invalid server group name")
        if name in cleaned_groups:
            raise ValueError(f"Duplicate server group: {name}")
        cleaned_groups.append(name)
    cleaned_servers = []
    seen = set()
    for server in servers:
        if not isinstance(server, dict) or set(server) - {"endpoint", "groups", "exclude_default", "enabled", "host_ip"}:
            raise ValueError("Invalid DNS server entry")
        endpoint = valid_endpoint(server.get("endpoint"))
        if endpoint in seen:
            raise ValueError(f"Duplicate DNS server: {endpoint}")
        seen.add(endpoint)
        memberships = server.get("groups", [])
        if (not isinstance(memberships, list) or len(memberships) > 16
                or any(not isinstance(name, str) for name in memberships)
                or len(set(memberships)) != len(memberships)):
            raise ValueError("Invalid server group assignments")
        if any(not isinstance(name, str) or name not in cleaned_groups for name in memberships):
            raise ValueError("Assign servers only to existing groups")
        exclude_default = server.get("exclude_default", False)
        enabled = server.get("enabled", True)
        if not isinstance(exclude_default, bool) or not isinstance(enabled, bool):
            raise ValueError("Server switches must be booleans")
        if enabled and exclude_default and not memberships:
            raise ValueError("An excluded server needs at least one group")
        host_ip = server.get("host_ip", "")
        if not isinstance(host_ip, str):
            raise ValueError("Host IP must be an IP address")
        if host_ip:
            try:
                host_ip = str(ipaddress.ip_address(host_ip))
            except ValueError as error:
                raise ValueError("Host IP must be an IP address") from error
        cleaned_servers.append({"endpoint": endpoint, "groups": memberships,
                                "exclude_default": exclude_default, "enabled": enabled,
                                "host_ip": host_ip})
    return {"groups": cleaned_groups, "servers": cleaned_servers}


def render(config):
    lines = ["# Managed by upstream-manager.py; edit through the Web UI.\n"]
    for server in config["servers"]:
        if not server["enabled"]:
            continue
        line = "server " + server["endpoint"]
        for group in server["groups"]:
            line += " -group " + group
        if server["exclude_default"]:
            line += " -exclude-default-group"
        if server["host_ip"]:
            line += " -host-ip " + server["host_ip"]
        lines.append(line + "\n")
    return "".join(lines).encode()


def atomic_write(path, data):
    fd, name = tempfile.mkstemp(prefix=".upstream-", dir=ROOT)
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


def manual_servers():
    path = ROOT / "smartdns.conf"
    if not path.exists():
        return []
    commands = {"server", "server-tcp", "server-tls", "server-https", "server-quic", "server-h3", "server-http3"}
    return [line.strip() for line in path.read_text().splitlines()
            if line.strip() and line.strip().split(None, 1)[0] in commands]


def show(config=None):
    return {**(config if config is not None else read_config()), "manual_servers": manual_servers()}


def check_removed_groups(previous, current):
    removed = set(previous["groups"]) - set(current["groups"])
    path = ROOT / "geosite.json"
    if not removed or not path.exists():
        return
    geosite = json.loads(path.read_text())
    referenced = {rule.get("group") for rule in geosite.get("rules", [])
                  if isinstance(rule, dict) and rule.get("action") == "route"}
    in_use = removed & referenced
    if in_use:
        raise ValueError("Group is used by GeoSite rules: " + ", ".join(sorted(in_use)))


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("show", "save"):
        raise ValueError("Usage: upstream-manager.py show|save")
    ROOT.mkdir(mode=0o755, parents=True, exist_ok=True)
    with LOCK.open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if sys.argv[1] == "show":
            return show()
        config = validate(json.load(sys.stdin))
        check_removed_groups(read_config(), config)
        if RULES.exists() and not RULES.read_bytes().startswith(b"# Managed by upstream-manager.py"):
            raise ValueError("upstream.conf is not Web UI managed")
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
        return show(config)


if __name__ == "__main__":
    try:
        print(json.dumps(main()))
    except (OSError, ValueError) as error:
        print(json.dumps({"error": str(error)}))
        sys.exit(1)
