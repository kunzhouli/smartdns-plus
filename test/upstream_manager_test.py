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


if __name__ == "__main__":
    unittest.main()
