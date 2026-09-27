"""Tests for Debian domain routing rule generation."""

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "package/debian/domain-routes-manager.py"
SPEC = importlib.util.spec_from_file_location("domain_routes_manager", SOURCE)
manager = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manager)


class DomainRoutesManagerTest(unittest.TestCase):
    def test_valid_routes_and_wildcards(self):
        config = manager.validate({"rules": [
            {"domain": "Example.COM", "group": "overseas"},
            {"domain": "*.internal.example", "group": "lan"},
            {"domain": "-.root.example", "group": "special"},
        ]})
        self.assertEqual(config["rules"][0]["domain"], "example.com")
        text = manager.render(config).decode()
        self.assertIn("domain-rules /example.com/ -nameserver overseas", text)
        self.assertIn("domain-rules /*.internal.example/ -nameserver lan", text)
        self.assertIn("domain-rules /-.root.example/ -nameserver special", text)

    def test_rejects_injection_and_duplicates(self):
        for domain in ("a/b", "bad name", "#comment", "example..com", "*.example.com\nserver 1.1.1.1"):
            with self.subTest(domain=domain), self.assertRaises(ValueError):
                manager.validate({"rules": [{"domain": domain, "group": "g"}]})
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            manager.validate({"rules": [{"domain": "EXAMPLE.com", "group": "g"},
                                        {"domain": "example.com", "group": "other"}]})
        with self.assertRaises(ValueError):
            manager.validate({"rules": [{"domain": "example.com", "group": "g\nserver"}]})

    def test_save_and_show(self):
        with tempfile.TemporaryDirectory() as root:
            import os
            env = {**os.environ, "SMARTDNS_DOMAIN_ROUTES_PATH": root}
            data = {"rules": [{"domain": "example.com", "group": "fast"}]}
            saved = subprocess.run([sys.executable, str(SOURCE), "save"], input=json.dumps(data),
                                   text=True, capture_output=True, env=env, check=True)
            self.assertEqual(json.loads(saved.stdout), data)
            shown = subprocess.run([sys.executable, str(SOURCE), "show"],
                                   text=True, capture_output=True, env=env, check=True)
            self.assertEqual(json.loads(shown.stdout), data)
            self.assertIn("-nameserver fast", (Path(root) / "domain-routes.conf").read_text())


if __name__ == "__main__":
    unittest.main()
