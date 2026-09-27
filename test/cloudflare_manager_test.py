"""Tests for Debian Cloudflare response alias generation."""

import importlib.util
import fcntl
import ipaddress
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parents[1] / "package/debian/cloudflare-manager.py"
SPEC = importlib.util.spec_from_file_location("cloudflare_manager", SOURCE)
manager = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manager)


class CloudflareManagerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        names = {"ROOT": root, "CONFIG": root / "cloudflare.json",
                 "STATE": root / "cloudflare-state.json", "RULES": root / "cloudflare.conf"}
        for key, value in names.items():
            original = getattr(manager, key)
            setattr(manager, key, value)
            self.addCleanup(setattr, manager, key, original)

    def test_response_aliases_and_failed_update_preserves_them(self):
        config = manager.defaults()
        config["enabled"] = True
        manager.save_json(manager.CONFIG, config)
        networks = {4: [ipaddress.ip_network("104.16.0.0/13")],
                    6: [ipaddress.ip_network("2606:4700::/32")]}
        with patch.object(manager, "read_ranges", return_value=networks), \
                patch.object(manager, "speedtest", side_effect=["104.16.1.1", "2606:4700::1"]):
            result = manager.run_test(config, {})
        self.assertTrue(result["changed"])
        rules = manager.RULES.read_text()
        self.assertIn("ip-alias 104.16.0.0/13 104.16.1.1", rules)
        self.assertIn("ip-alias 2606:4700::/32 2606:4700::1", rules)
        with patch.object(manager, "read_ranges", side_effect=ValueError("download failed")):
            with self.assertRaisesRegex(ValueError, "download failed"):
                manager.run_test(config, manager.read_state())
        self.assertEqual(manager.RULES.read_text(), rules)
        self.assertEqual(manager.read_state()["best_v4"], "104.16.1.1")

    def test_result_must_be_fast_and_in_cloudflare_range(self):
        result = manager.ROOT / "result.csv"
        result.write_text("IP,Sent,Recv,Loss,Latency,Speed,Colo\n"
                          "1.1.1.1,2,2,0,10,50,LAX\n"
                          "104.16.1.1,2,2,0,10,0,LAX\n"
                          "104.16.1.2,2,2,0,10,12,LAX\n")
        networks = [ipaddress.ip_network("104.16.0.0/13")]
        self.assertEqual(manager.select_best(result, networks, 4), "104.16.1.2")

    def test_schedule_and_disabled_rules(self):
        config = manager.defaults()
        self.assertFalse(manager.due(config, {}))
        self.assertNotIn("ip-alias", manager.rule_text(config, {"best_v4": "104.16.1.1",
                                                               "ranges_v4": ["104.16.0.0/13"]}).decode())
        config["enabled"] = True
        config["run_time"] = "00:00"
        self.assertTrue(manager.due(config, {}))
        self.assertFalse(manager.due(config, {"last_attempt": int(time.time())}))

    def test_legacy_download_url_is_ignored(self):
        config = manager.validate({**manager.defaults(), "test_url": "https://old.invalid/download"})
        self.assertNotIn("test_url", config)

    def test_speedtest_uses_bundled_default_download_url(self):
        networks = [ipaddress.ip_network("104.16.0.0/13")]
        with patch.object(manager.subprocess, "run") as run, \
                patch.object(manager, "select_best", return_value="104.16.1.1"):
            run.return_value.returncode = 0
            manager.speedtest(networks, 4, 40, str(manager.ROOT))
        args = run.call_args.args[0]
        self.assertNotIn("-url", args)

    def test_status_remains_available_during_speed_test(self):
        lock_path = manager.ROOT / "cloudflare.lock"
        with lock_path.open("a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            result = subprocess.run(
                [sys.executable, str(SOURCE), "show"],
                env={**os.environ, "SMARTDNS_CFPATH": str(manager.ROOT)},
                capture_output=True, text=True, timeout=2, check=True,
            )
        self.assertIn('"enabled": false', result.stdout)


if __name__ == "__main__":
    unittest.main()
