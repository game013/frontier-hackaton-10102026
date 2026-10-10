"""Pruebas offline de las sondas A7: sin requests al original."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import a7_probes  # noqa: E402
from bb import load_steps  # noqa: E402
from control import control  # noqa: E402


class A7ProbesTest(unittest.TestCase):
    def test_committed_files_match_generator(self):
        files = sorted(a7_probes.OUT.glob("*.jsonl"))
        self.assertEqual([p.stem for p in files], sorted(a7_probes.SEQUENCES))
        for path in files:
            expected = "".join(json.dumps(s, ensure_ascii=False) + "\n"
                               for s in a7_probes.SEQUENCES[path.stem]())
            self.assertEqual(path.read_text(), expected, path.name)

    def test_runner_accepts_every_sequence_and_controls_are_valid(self):
        for path in a7_probes.OUT.glob("*.jsonl"):
            for step in load_steps(path):
                self.assertTrue(step["hipotesis"])
                base, ctl = step["request"]["m"].rsplit(";", 1)
                self.assertEqual(int(ctl), control(base), path.name)

    def test_budget_fits_with_repetition_and_full_replay(self):
        steps = sum(len(build()) + 1 for build in a7_probes.SEQUENCES.values())  # + reset
        self.assertLessEqual(842 + 2 * steps, 1000)

    def test_e506_probe_amount_is_over_v2_limit_and_under_funds(self):
        amount = int(a7_probes.e506(1)["request"]["m"].split(";")[3])
        self.assertTrue(50000 < amount <= a7_probes.SETUP_FUNDS)


if __name__ == "__main__":
    unittest.main()
