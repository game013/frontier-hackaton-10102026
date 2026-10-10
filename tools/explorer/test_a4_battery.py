"""Pruebas offline de la batería A4: sin requests al original."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import a4_battery  # noqa: E402
from bb import load_steps  # noqa: E402
from control import control  # noqa: E402


class A4BatteryTest(unittest.TestCase):
    def test_committed_files_match_generator(self):
        files = sorted(a4_battery.OUT.glob("*.jsonl"))
        self.assertEqual([p.stem for p in files], sorted(a4_battery.SEQUENCES))
        for path in files:
            expected = "".join(json.dumps(s, ensure_ascii=False) + "\n"
                               for s in a4_battery.SEQUENCES[path.stem])
            self.assertEqual(path.read_text(), expected, path.name)

    def test_runner_accepts_every_sequence(self):
        for path in a4_battery.OUT.glob("*.jsonl"):
            self.assertTrue(load_steps(path), path.name)

    def test_control_helpers(self):
        good = a4_battery.m("ALTA;Lucia", "h")["request"]["m"]
        self.assertEqual(good, "ALTA;Lucia;82")
        self.assertEqual(a4_battery.ctl("ALTA;Lucia", "+82", "h")["request"]["m"], "ALTA;Lucia;+82")
        self.assertEqual(control("ALTA;Lucia"), 82)

    def test_auth_variants_are_known_to_runner(self):
        from bb import AUTH_VARIANTS
        for steps in a4_battery.SEQUENCES.values():
            for step in steps:
                self.assertIn(step.get("auth", "valid"), AUTH_VARIANTS)


if __name__ == "__main__":
    unittest.main()
