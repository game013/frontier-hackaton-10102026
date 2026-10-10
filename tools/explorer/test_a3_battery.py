"""Pruebas offline de la batería A3: sin requests al original."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import a3_battery  # noqa: E402
from bb import load_steps  # noqa: E402
from control import control  # noqa: E402


class A3BatteryTest(unittest.TestCase):
    def test_committed_files_match_generator(self):
        files = sorted(a3_battery.OUT.glob("*.jsonl"))
        self.assertEqual([p.stem for p in files], sorted(a3_battery.SEQUENCES))
        for path in files:
            expected = "".join(json.dumps(s, ensure_ascii=False) + "\n"
                               for s in a3_battery.SEQUENCES[path.stem])
            self.assertEqual(path.read_text(), expected, path.name)

    def test_runner_accepts_every_sequence(self):
        for path in a3_battery.OUT.glob("*.jsonl"):
            self.assertTrue(load_steps(path), path.name)

    def test_control_helpers(self):
        good = a3_battery.m("ALTA;Lucia", "h")["request"]["m"]
        self.assertEqual(good, "ALTA;Lucia;82")
        wrong = int(a3_battery.bad("ALTA;Lucia", "h")["request"]["m"].rsplit(";", 1)[1])
        self.assertNotEqual(wrong, control("ALTA;Lucia"))


if __name__ == "__main__":
    unittest.main()
