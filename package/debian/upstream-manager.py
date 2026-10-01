#!/usr/bin/python3
"""Manage Web UI upstream servers without rewriting hand-maintained config."""

import fcntl
import hashlib
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
    return {"groups": [], "default_group": "", "bootstrap_dns": {},
            "group_order": {}, "group_parallel": {}, "servers": []}


def valid_ip(host):
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


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


def valid_bootstrap_endpoint(value):
    endpoint = valid_endpoint(value)
    parsed = urllib.parse.urlsplit(endpoint if "://" in endpoint else "//" + endpoint)
    if parsed.scheme not in ("", "udp"):
        raise ValueError("Bootstrap DNS must use ordinary UDP DNS")
    try:
        ipaddress.ip_address(parsed.hostname)
    except ValueError as error:
        raise ValueError("Bootstrap DNS must use an IP address") from error
    return endpoint


def bootstrap_group(name):
    return "webui_boot_" + hashlib.sha256(name.encode()).hexdigest()[:16]


def bootstrap_routes(servers, bootstrap_dns):
    host_addresses = {}
    routes = {}
    for server in servers:
        if not server["enabled"] or server["host_ip"]:
            continue
        parsed = urllib.parse.urlsplit(server["endpoint"] if "://" in server["endpoint"]
                                     else "//" + server["endpoint"])
        host = parsed.hostname.rstrip(".").lower()
        if valid_ip(host):
            continue
        addresses = {bootstrap_dns.get(group, "") for group in server["groups"]}
        if len(addresses) > 1:
            raise ValueError(f"Upstream hostname {host} belongs to groups with different bootstrap DNS settings")
        address = next(iter(addresses), "")
        if host in host_addresses and host_addresses[host] != address:
            raise ValueError(f"Upstream hostname {host} belongs to groups with different bootstrap DNS settings")
        host_addresses[host] = address
        if address:
            routes[host] = next(group for group in server["groups"] if bootstrap_dns.get(group) == address)
    return routes


def validate(raw):
    if not isinstance(raw, dict) or set(raw) - {"groups", "default_group", "bootstrap_dns", "group_order", "group_parallel", "servers", "manual_servers"}:
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
    default_group = raw.get("default_group", "")
    if not isinstance(default_group, str) or (default_group and default_group not in cleaned_groups):
        raise ValueError("Default DNS group must be an existing server group")
    bootstrap_dns = raw.get("bootstrap_dns", {})
    if not isinstance(bootstrap_dns, dict) or any(not isinstance(name, str) or name not in cleaned_groups
                                                   for name in bootstrap_dns):
        raise ValueError("Bootstrap DNS must belong to an existing server group")
    cleaned_bootstrap = {}
    for name, endpoint in bootstrap_dns.items():
        if not isinstance(endpoint, str):
            raise ValueError("Bootstrap DNS address must be text")
        if endpoint:
            cleaned_bootstrap[name] = valid_bootstrap_endpoint(endpoint)
    cleaned_servers = []
    seen = set()
    for server in servers:
        if not isinstance(server, dict) or set(server) - {"endpoint", "groups", "exclude_default", "enabled", "host_ip", "bootstrap_dns"}:
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
        if (not isinstance(exclude_default, bool) or not isinstance(enabled, bool)
                or not isinstance(server.get("bootstrap_dns", False), bool)):
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
    if default_group and not any(server["enabled"] and default_group in server["groups"]
                                 for server in cleaned_servers):
        raise ValueError("Default DNS group needs at least one enabled server")
    if default_group and any(server["enabled"] and not server["groups"]
                             for server in cleaned_servers):
        raise ValueError("Assign each enabled server to a group when a default DNS group is selected")
    group_order = raw.get("group_order", {})
    group_parallel = raw.get("group_parallel", {})
    if not isinstance(group_order, dict) or not isinstance(group_parallel, dict):
        raise ValueError("Invalid group query settings")
    cleaned_order = {}
    cleaned_parallel = {}
    for group in cleaned_groups:
        members = [server["endpoint"] for server in cleaned_servers
                   if server["enabled"] and group in server["groups"]]
        order = group_order.get(group, members)
        if (not isinstance(order, list) or len(order) != len(members)
                or any(not isinstance(endpoint, str) for endpoint in order)
                or set(order) != set(members)):
            raise ValueError(f"Group {group} order must list every enabled server exactly once")
        cleaned_order[group] = order
        if group in group_parallel:
            parallel = group_parallel[group]
            if type(parallel) is not int or not 1 <= parallel <= min(len(members), 64):
                raise ValueError(f"Group {group} parallel count must be between 1 and its server count")
            if len(members) > 64:
                raise ValueError(f"Group {group} exceeds the 64-server core limit")
            cleaned_parallel[group] = parallel
    if set(group_order) - set(cleaned_groups) or set(group_parallel) - set(cleaned_groups):
        raise ValueError("Group query settings must belong to existing groups")
    bootstrap_routes(cleaned_servers, cleaned_bootstrap)
    return {"groups": cleaned_groups, "default_group": default_group,
            "bootstrap_dns": cleaned_bootstrap, "group_order": cleaned_order,
            "group_parallel": cleaned_parallel, "servers": cleaned_servers}


def render(config):
    lines = ["# Managed by upstream-manager.py; edit through the Web UI.\n"]
    hostname_bootstrap = bootstrap_routes(config["servers"], config["bootstrap_dns"])
    active_groups = set(hostname_bootstrap.values())
    bootstrap_servers = {}
    for name, endpoint in config["bootstrap_dns"].items():
        if name in active_groups:
            bootstrap_servers.setdefault(endpoint, []).append(name)
    for endpoint, names in bootstrap_servers.items():
        line = "server " + endpoint
        for name in names:
            line += " -group " + bootstrap_group(name)
        lines.append(line + " -exclude-default-group\n")
    default_order = (config["group_order"].get(config["default_group"], [])
                     if config["default_group"] in config["group_parallel"] else [])
    default_position = {endpoint: index for index, endpoint in enumerate(default_order)}
    servers = sorted(config["servers"], key=lambda server: default_position.get(server["endpoint"], 1000 + config["servers"].index(server)))
    group_position = {name: {endpoint: index + 1 for index, endpoint in enumerate(config["group_order"][name])}
                      for name in config["group_parallel"]}
    for server in servers:
        if not server["enabled"]:
            continue
        line = "server " + server["endpoint"]
        for group in server["groups"]:
            line += " -group " + group
            if group in group_position and server["endpoint"] in group_position[group]:
                line += f" -group-order {group}:{group_position[group][server['endpoint']]}"
        if (config["default_group"] not in server["groups"] if config["default_group"]
                else server["exclude_default"]):
            line += " -exclude-default-group"
        if server["host_ip"]:
            line += " -host-ip " + server["host_ip"]
        lines.append(line + "\n")
    for group, parallel in config["group_parallel"].items():
        lines.append(f"server-group-parallel {group} {parallel}\n")
    if config["default_group"] in config["group_parallel"]:
        lines.append(f"server-group-parallel default {config['group_parallel'][config['default_group']]}\n")
    for host, group in sorted(hostname_bootstrap.items()):
        lines.append(f"priority-nameserver /-.{host}/ {bootstrap_group(group)}\n")
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
    if not removed:
        return
    geosite_path = ROOT / "geosite.json"
    if geosite_path.exists():
        geosite = json.loads(geosite_path.read_text())
        referenced = {rule.get("group") for rule in geosite.get("rules", [])
                      if isinstance(rule, dict) and rule.get("action") == "route"}
        in_use = removed & referenced
        if in_use:
            raise ValueError("Group is used by GeoSite rules: " + ", ".join(sorted(in_use)))
    domain_path = ROOT / "domain-routes.json"
    if domain_path.exists():
        domain_routes = json.loads(domain_path.read_text())
        referenced = {rule.get("group") for rule in domain_routes.get("rules", [])
                      if isinstance(rule, dict)}
        in_use = removed & referenced
        if in_use:
            raise ValueError("Group is used by domain routing rules: " + ", ".join(sorted(in_use)))


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
