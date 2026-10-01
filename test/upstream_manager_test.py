import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "package/debian/upstream-manager.py"


class UpstreamManagerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = {**os.environ, "SMARTDNS_UPSTREAM_PATH": str(self.root)}

    def command(self, action, payload=None):
        return subprocess.run(
            ["python3", str(SCRIPT), action],
            input=json.dumps(payload) if payload is not None else None,
            text=True, capture_output=True, env=self.env,
        )

    def test_saves_groups_and_servers_without_touching_manual_config(self):
        manual = "server 9.9.9.9 -group manual\n"
        (self.root / "smartdns.conf").write_text(manual)
        payload = {
            "groups": ["overseas", "office"],
            "servers": [
                {"endpoint": "tls://dns.google:853", "groups": ["overseas", "office"],
                 "exclude_default": True, "enabled": True, "host_ip": "8.8.8.8"},
                {"endpoint": "1.1.1.1", "groups": [], "exclude_default": False,
                 "enabled": False, "host_ip": ""},
            ],
        }
        result = self.command("save", payload)
        self.assertEqual(result.returncode, 0, result.stdout)
        rendered = (self.root / "upstream.conf").read_text()
        self.assertIn("server tls://dns.google:853 -group overseas -group office -exclude-default-group -host-ip 8.8.8.8", rendered)
        self.assertNotIn("server 1.1.1.1", rendered)
        self.assertEqual((self.root / "smartdns.conf").read_text(), manual)
        shown = json.loads(self.command("show").stdout)
        self.assertEqual(shown["manual_servers"], [manual.strip()])
        self.assertEqual(shown["groups"], payload["groups"])
        self.assertEqual(shown["default_group"], "")
        self.assertEqual(shown["bootstrap_dns"], {})

    def test_selected_default_group_excludes_other_managed_servers(self):
        payload = {
            "groups": ["China", "Overseas"],
            "default_group": "Overseas",
            "servers": [
                {"endpoint": "1.1.1.1", "groups": ["Overseas"],
                 "exclude_default": True, "enabled": True, "host_ip": ""},
                {"endpoint": "223.5.5.5", "groups": ["China"],
                 "exclude_default": False, "enabled": True, "host_ip": ""},
            ],
        }
        result = self.command("save", payload)
        self.assertEqual(result.returncode, 0, result.stdout)
        rendered = (self.root / "upstream.conf").read_text()
        self.assertIn("server 1.1.1.1 -group Overseas\n", rendered)
        self.assertIn("server 223.5.5.5 -group China -exclude-default-group\n", rendered)
        self.assertEqual(json.loads(self.command("show").stdout)["default_group"], "Overseas")

    def test_group_bootstrap_servers_route_upstream_hostnames(self):
        payload = {
            "groups": ["China", "Overseas"], "default_group": "Overseas",
            "bootstrap_dns": {"China": "223.5.5.5", "Overseas": "1.1.1.1:5353"},
            "servers": [
                {"endpoint": "https://dns.china.example/dns-query", "groups": ["China"],
                 "exclude_default": False, "enabled": True, "host_ip": ""},
                {"endpoint": "tls://dns.overseas.example:853", "groups": ["Overseas"],
                 "exclude_default": False, "enabled": True, "host_ip": ""},
            ],
        }
        result = self.command("save", payload)
        self.assertEqual(result.returncode, 0, result.stdout)
        rendered = (self.root / "upstream.conf").read_text()
        for group, address, host in (("China", "223.5.5.5", "dns.china.example"),
                                     ("Overseas", "1.1.1.1:5353", "dns.overseas.example")):
            internal = "webui_boot_" + hashlib.sha256(group.encode()).hexdigest()[:16]
            self.assertIn(f"server {address} -group {internal} -exclude-default-group\n", rendered)
            self.assertIn(f"priority-nameserver /-.{host}/ {internal}\n", rendered)
        self.assertNotIn("server tls://dns.overseas.example:853 -exclude-default-group", rendered)
        self.assertEqual(json.loads(self.command("show").stdout)["bootstrap_dns"], payload["bootstrap_dns"])

    def test_group_bootstrap_rejects_invalid_addresses_and_conflicting_hostnames(self):
        server = {"endpoint": "tls://dns.example:853", "groups": ["one"],
                  "exclude_default": False, "enabled": True, "host_ip": ""}
        original = {"groups": ["one", "two"], "bootstrap_dns": {"one": "1.1.1.1"},
                    "servers": [server]}
        self.assertEqual(self.command("save", original).returncode, 0)
        before = (self.root / "upstream.conf").read_bytes()
        invalid = [
            {**original, "bootstrap_dns": {"one": "dns.example"}},
            {**original, "bootstrap_dns": {"one": "https://1.1.1.1/dns-query"}},
            {**original, "bootstrap_dns": {"missing": "1.1.1.1"}},
            {**original, "bootstrap_dns": {"one": "1.1.1.1", "two": "9.9.9.9"},
             "servers": [server, {**server, "endpoint": "https://dns.example/dns-query", "groups": ["two"]}]},
            {**original, "servers": [{**server, "groups": ["one", "two"]}]},
        ]
        for payload in invalid:
            with self.subTest(payload=payload):
                self.assertNotEqual(self.command("save", payload).returncode, 0)
                self.assertEqual((self.root / "upstream.conf").read_bytes(), before)

    def test_unused_group_bootstrap_does_not_add_a_dns_server(self):
        payload = {"groups": ["one"], "bootstrap_dns": {"one": "[2606:4700:4700::1111]:53"},
                   "servers": [{"endpoint": "1.1.1.1", "groups": ["one"],
                                "exclude_default": False, "enabled": True, "host_ip": ""}]}
        result = self.command("save", payload)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("webui_boot_", (self.root / "upstream.conf").read_text())

    def test_invalid_inputs_do_not_change_saved_rules(self):
        original = {"groups": ["office"], "servers": [
            {"endpoint": "https://dns.google/dns-query", "groups": ["office"],
             "exclude_default": True, "enabled": True, "host_ip": "8.8.8.8"},
        ]}
        self.assertEqual(self.command("save", original).returncode, 0)
        before = (self.root / "upstream.conf").read_bytes()
        invalid = [
            {"groups": ["office"], "servers": [{**original["servers"][0], "endpoint": "1.1.1.1\nplugin evil"}]},
            {"groups": ["office", "office"], "servers": []},
            {"groups": [], "servers": original["servers"]},
            {"groups": [], "servers": [{**original["servers"][0], "groups": [], "host_ip": ""}]},
            {**original, "default_group": "missing"},
            {**original, "default_group": "office", "servers": []},
        ]
        for payload in invalid:
            with self.subTest(payload=payload):
                self.assertNotEqual(self.command("save", payload).returncode, 0)
                self.assertEqual((self.root / "upstream.conf").read_bytes(), before)

    def test_cannot_remove_group_used_by_geosite(self):
        original = {"groups": ["overseas"], "servers": []}
        self.assertEqual(self.command("save", original).returncode, 0)
        (self.root / "geosite.json").write_text(json.dumps({"rules": [
            {"site": "geolocation-!cn", "action": "route", "group": "overseas"},
        ]}))
        result = self.command("save", {"groups": [], "servers": []})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("used by GeoSite", result.stdout)
        self.assertEqual(json.loads((self.root / "upstream.json").read_text())["groups"], ["overseas"])

    def test_cannot_remove_group_used_by_domain_route(self):
        original = {"groups": ["overseas"], "servers": []}
        self.assertEqual(self.command("save", original).returncode, 0)
        (self.root / "domain-routes.json").write_text(json.dumps({"rules": [
            {"domain": "example.com", "group": "overseas"},
        ]}))
        result = self.command("save", {"groups": [], "servers": []})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("used by domain routing rules", result.stdout)
        self.assertEqual(json.loads((self.root / "upstream.json").read_text())["groups"], ["overseas"])

    def test_group_specific_order_and_parallel_batches(self):
        servers = [{"endpoint": ip, "groups": ["one", "two"], "exclude_default": False,
                    "enabled": True, "host_ip": ""} for ip in ("1.1.1.1", "2.2.2.2", "3.3.3.3")]
        payload = {"groups": ["one", "two"], "default_group": "one", "servers": servers,
                   "group_order": {"one": ["3.3.3.3", "1.1.1.1", "2.2.2.2"],
                                   "two": ["2.2.2.2", "3.3.3.3", "1.1.1.1"]},
                   "group_parallel": {"one": 1, "two": 2}}
        result = self.command("save", payload)
        self.assertEqual(result.returncode, 0, result.stdout)
        rules = (self.root / "upstream.conf").read_text()
        self.assertLess(rules.index("server 3.3.3.3"), rules.index("server 1.1.1.1"))
        self.assertIn("-group-order one:1 -group two -group-order two:2", rules)
        self.assertIn("server-group-parallel one 1\n", rules)
        self.assertIn("server-group-parallel two 2\n", rules)
        self.assertIn("server-group-parallel default 1\n", rules)
        self.assertEqual(json.loads(self.command("show").stdout)["group_order"], payload["group_order"])

    def test_invalid_group_order_and_parallel_count(self):
        server = {"endpoint": "1.1.1.1", "groups": ["one"], "exclude_default": False,
                  "enabled": True, "host_ip": ""}
        base = {"groups": ["one"], "servers": [server]}
        for patch in ({"group_order": {"one": []}},
                      {"group_order": {"one": ["9.9.9.9"]}},
                      {"group_parallel": {"one": 0}},
                      {"group_parallel": {"one": 2}},
                      {"group_parallel": {"one": True}},
                      {"group_parallel": {"missing": 1}}):
            with self.subTest(patch=patch):
                self.assertNotEqual(self.command("save", {**base, **patch}).returncode, 0)


if __name__ == "__main__":
    unittest.main()
