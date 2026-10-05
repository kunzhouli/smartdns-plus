"""Tests for priority order in generated GeoSite rules."""

import importlib.util
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "package/debian/geosite-manager.py"
SPEC = importlib.util.spec_from_file_location("geosite_manager", SOURCE)
manager = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manager)


class GeositeManagerTest(unittest.TestCase):
    def test_first_ui_rule_is_emitted_last_for_overlapping_categories(self):
        original_data = manager.DATA
        try:
            with tempfile.TemporaryDirectory() as root:
                manager.DATA = Path(root) / "geosite.dat"
                manager.DATA.touch()
                config = manager.validate({"rules": [
                    {"site": "preferred", "action": "route", "group": "fast"},
                    {"site": "fallback", "action": "route", "group": "slow"},
                ]})
                text = manager.config_text(config).decode()
                self.assertLess(text.index("-site fallback"), text.index("-site preferred"))
                self.assertIn("domain-rules /domain-set:geosite-0/ -nameserver fast", text)
        finally:
            manager.DATA = original_data


if __name__ == "__main__":
    unittest.main()
