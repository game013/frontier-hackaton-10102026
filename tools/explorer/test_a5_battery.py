"""Pruebas offline de la batería A5: sin requests al original."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import a5_battery  # noqa: E402
from bb import load_steps  # noqa: E402


class A5BatteryTest(unittest.TestCase):
    def test_committed_files_match_generator(self):
        files = sorted(a5_battery.OUT.glob("*.jsonl"))
        self.assertEqual([p.stem for p in files], sorted(a5_battery.SEQUENCES))
        for path in files:
            expected = "".join(json.dumps(s, ensure_ascii=False) + "\n"
                               for s in a5_battery.SEQUENCES[path.stem])
            self.assertEqual(path.read_text(), expected, path.name)

    def test_runner_accepts_every_sequence(self):
        for path in a5_battery.OUT.glob("*.jsonl"):
            self.assertTrue(load_steps(path), path.name)

    def test_sweep_excludes_known_and_duplicates(self):
        names = a5_battery.dictionary()
        self.assertEqual(len(names), len(set(names)))
        self.assertFalse(set(names) & a5_battery.KNOWN)

    def test_sweep_messages_carry_a1_control(self):
        steps = a5_battery.sweep(["RETIRO", "SALDO_TOTAL"])["barrido-01"]
        self.assertEqual([s["request"]["m"] for s in steps],
                         [f"RETIRO;{a5_battery.control('RETIRO')}",
                          f"SALDO_TOTAL;{a5_battery.control('SALDOTOTAL')}"])

    def test_sweep_chunks(self):
        seqs = a5_battery.sweep([f"N{chr(65 + i % 26)}{chr(65 + i // 26)}" for i in range(120)])
        self.assertEqual([len(v) for v in seqs.values()], [50, 50, 20])


if __name__ == "__main__":
    unittest.main()
