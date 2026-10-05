"""Tests for Debian Cloudflare response alias generation."""

import importlib.util
import fcntl
import io
import ipaddress
import multiprocessing
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parents[1] / "package/debian/cloudflare-manager.py"
REMOTE = SOURCE.with_name("cloudflare-cfst-remote")
SPEC = importlib.util.spec_from_file_location("cloudflare_manager", SOURCE)
manager = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manager)


class CloudflareManagerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        names = {"ROOT": root, "CONFIG": root / "cloudflare.json",
                 "STATE": root / "cloudflare-state.json", "RULES": root / "cloudflare.conf",
                 "LOCK": root / "cloudflare.lock", "LOG": root / "cloudflare-run.log"}
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
        self.assertIn("Cloudflare speed test failed: download failed", manager.read_log())

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
        self.assertFalse(manager.due(config, {}))
        config["schedule_enabled"] = True
        self.assertTrue(manager.due(config, {}))
        config["enabled"] = False
        self.assertTrue(manager.due(config, {}))
        self.assertFalse(manager.due(config, {"last_attempt": int(time.time())}))

    def test_manual_start_does_not_enable_schedule(self):
        config = manager.defaults()
        manager.save_json(manager.CONFIG, config)
        binary = manager.ROOT / "cfst"
        binary.write_text("#!/bin/sh\n")
        binary.chmod(0o755)
        with patch.object(manager, "CFST", str(binary)), \
                patch.object(manager.subprocess, "Popen") as launch:
            launch.return_value.pid = os.getpid()
            with patch.object(sys, "argv", [str(SOURCE), "start"]):
                result = manager.main()
        self.assertTrue(result["running"])
        self.assertFalse(manager.read_config()["enabled"])
        self.assertFalse(manager.read_config()["schedule_enabled"])
        self.assertEqual(launch.call_args.args[0][-1], "run-restart")

    def test_legacy_download_url_is_ignored(self):
        legacy = {key: value for key, value in manager.defaults().items() if key != "schedule_enabled"}
        config = manager.validate({**legacy, "test_url": "https://old.invalid/download"})
        self.assertNotIn("test_url", config)
        self.assertFalse(config["schedule_enabled"])

    def test_speedtest_uses_bundled_default_download_url(self):
        networks = [ipaddress.ip_network("104.16.0.0/13")]
        binary = manager.ROOT / "fake-cfst"
        arguments = manager.ROOT / "arguments"
        binary.write_text("#!/usr/bin/python3\n"
                          "import pathlib, sys\n"
                          f"pathlib.Path({str(arguments)!r}).write_text(' '.join(sys.argv))\n"
                          "pathlib.Path(sys.argv[sys.argv.index('-o') + 1]).write_text('104.16.1.1,2,2,0,10,12\\n')\n")
        binary.chmod(0o755)
        with patch.object(manager, "CFST", str(binary)):
            manager.speedtest(networks, 4, manager.defaults(), str(manager.ROOT))
        self.assertNotIn("-url", arguments.read_text())

    def test_progress_frames_are_removed_from_live_and_existing_logs(self):
        sample = ("Starting\n" + "20 / 5956 [↖________________] 可用: 20  " * 300 +
                  "\nDownload\n" + "2 / 5 [↗________________]  " * 100 + "\nFailed\n")
        manager.stream_log(io.BytesIO(sample.encode()))
        self.assertEqual(manager.read_log(), "Starting\nDownload\nFailed")
        manager.LOG.write_text(sample)
        self.assertEqual(manager.read_log(), "Starting\nDownload\nFailed")

    def test_stop_terminates_worker_and_keeps_previous_rules(self):
        config = {**manager.defaults(), "enabled": True, "ipv6_enabled": False}
        manager.save_json(manager.CONFIG, config)
        manager.RULES.write_text("previous rules\n")
        marker = manager.ROOT / "worker-pid"
        binary = manager.ROOT / "slow-cfst"
        binary.write_text("#!/usr/bin/python3\n"
                          "import os, pathlib, time\n"
                          f"pathlib.Path({str(marker)!r}).write_text(str(os.getpid()))\n"
                          "time.sleep(30)\n")
        binary.chmod(0o755)
        networks = {4: [ipaddress.ip_network("104.16.0.0/13")],
                    6: [ipaddress.ip_network("2606:4700::/32")]}

        def run_slow_test():
            with patch.object(manager, "CFST", str(binary)), \
                    patch.object(manager, "read_ranges", return_value=networks):
                try:
                    manager.run_test(config, {})
                except manager.TestStopped:
                    pass

        worker = multiprocessing.get_context("fork").Process(target=run_slow_test)
        worker.start()
        self.addCleanup(lambda: worker.is_alive() and worker.kill())
        deadline = time.monotonic() + 5
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(marker.exists())
        cfst_pid = int(marker.read_text())
        with patch.object(manager, "is_manager_process", return_value=True):
            result = manager.stop_test()
        worker.join(timeout=5)
        self.assertFalse(worker.is_alive())
        self.assertFalse(manager.process_alive(cfst_pid))
        self.assertFalse(result["running"])
        self.assertEqual(manager.RULES.read_text(), "previous rules\n")
        self.assertIn("stopped by user", manager.read_log())

    def test_clear_log_does_not_change_selected_ip(self):
        manager.LOG.write_text("old log\n")
        manager.save_json(manager.STATE, {"best_v4": "104.16.1.1"})
        with patch.object(sys, "argv", [str(SOURCE), "clear-log"]):
            result = manager.main()
        self.assertEqual(result["log"], "")
        self.assertEqual(manager.read_state()["best_v4"], "104.16.1.1")

    def test_remote_helper_stops_its_speedtest_child(self):
        marker = manager.ROOT / "remote-worker-pid"
        binary = manager.ROOT / "slow-remote-cfst"
        binary.write_text("#!/usr/bin/python3\n"
                          "import os, pathlib, time\n"
                          f"pathlib.Path({str(marker)!r}).write_text(str(os.getpid()))\n"
                          "time.sleep(30)\n")
        binary.chmod(0o755)
        helper = subprocess.Popen([str(REMOTE), "1"], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  env={**os.environ, "SMARTDNS_CFST_BIN": str(binary)})
        self.addCleanup(lambda: helper.poll() is None and helper.kill())
        self.addCleanup(helper.stdout.close)
        self.addCleanup(helper.stderr.close)
        helper.stdin.write(b"104.16.0.0/13\n")
        helper.stdin.close()
        deadline = time.monotonic() + 5
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(marker.exists())
        cfst_pid = int(marker.read_text())
        helper.send_signal(signal.SIGTERM)
        helper.wait(timeout=5)
        self.assertFalse(manager.process_alive(cfst_pid))

    def test_speedtest_output_is_visible_before_completion(self):
        binary = manager.ROOT / "fake-cfst"
        binary.write_text("#!/usr/bin/python3\n"
                          "import pathlib, sys, time\n"
                          "print('measuring IPv4', flush=True)\n"
                          "time.sleep(0.5)\n"
                          "pathlib.Path(sys.argv[sys.argv.index('-o') + 1]).write_text('104.16.1.1,2,2,0,10,12\\n')\n")
        binary.chmod(0o755)
        networks = [ipaddress.ip_network("104.16.0.0/13")]
        results = []
        with patch.object(manager, "CFST", str(binary)):
            worker = threading.Thread(target=lambda: results.append(
                manager.speedtest(networks, 4, {**manager.defaults(), "threads": 1}, str(manager.ROOT))))
            worker.start()
            deadline = time.monotonic() + 2
            while "measuring IPv4" not in manager.read_log() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertIn("measuring IPv4", manager.read_log())
            self.assertTrue(worker.is_alive())
            worker.join(timeout=2)
        self.assertEqual(results, ["104.16.1.1"])

    def test_remote_runner_streams_csv_and_logs(self):
        fake_ssh = manager.ROOT / "ssh"
        fake_ssh.write_text("#!/usr/bin/python3\n"
                            "import subprocess, sys\n"
                            "command = [sys.argv[-2], sys.argv[-1]]\n"
                            "result = subprocess.run(command, stdin=sys.stdin.buffer, "
                            "stdout=sys.stdout.buffer, stderr=sys.stderr.buffer)\n"
                            "sys.exit(result.returncode)\n")
        fake_ssh.chmod(0o755)
        fake_cfst = manager.ROOT / "cfst"
        fake_cfst.write_text("#!/usr/bin/python3\n"
                             "import pathlib, sys\n"
                             "args = sys.argv\n"
                             "assert '104.16.0.0/13' in pathlib.Path(args[args.index('-f') + 1]).read_text()\n"
                             "pathlib.Path(args[args.index('-o') + 1]).write_text('104.16.1.2,2,2,0,10,12\\n')\n"
                             "print('remote measurement', flush=True)\n")
        fake_cfst.chmod(0o755)
        key = manager.ROOT / "key"
        key.write_text("test")
        config = {**manager.defaults(), "test_runner": "ssh", "remote_host": "192.168.100.21",
                  "remote_key": str(key)}
        networks = [ipaddress.ip_network("104.16.0.0/13")]
        with patch.dict(os.environ, {"PATH": str(manager.ROOT) + ":" + os.environ["PATH"],
                                  "SMARTDNS_CFST_BIN": str(fake_cfst)}), \
                patch.object(manager, "REMOTE_COMMAND", str(REMOTE)):
            result = manager.speedtest(networks, 4, config, str(manager.ROOT))
        self.assertEqual(result, "104.16.1.2")
        self.assertIn("remote measurement", manager.read_log())

    def test_remote_runner_config_rejects_ssh_options_as_host(self):
        with self.assertRaisesRegex(ValueError, "Invalid remote host"):
            manager.validate({**manager.defaults(), "test_runner": "ssh", "remote_host": "-oProxyCommand=bad"})

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
