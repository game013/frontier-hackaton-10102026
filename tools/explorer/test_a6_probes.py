"""Pruebas offline de las sondas A6: sin requests al original."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import a6_probes  # noqa: E402
from bb import load_steps  # noqa: E402
from control import control  # noqa: E402


class A6ProbesTest(unittest.TestCase):
    def test_committed_files_match_generator(self):
        files = sorted(a6_probes.OUT.glob("*.jsonl"))
        self.assertEqual([p.stem for p in files], sorted(a6_probes.SEQUENCES))
        for path in files:
            expected = "".join(json.dumps(s, ensure_ascii=False) + "\n"
                               for s in a6_probes.SEQUENCES[path.stem]())
            self.assertEqual(path.read_text(), expected, path.name)

    def test_runner_accepts_every_sequence_and_controls_are_valid(self):
        for path in a6_probes.OUT.glob("*.jsonl"):
            for step in load_steps(path):
                base, ctl = step["request"]["m"].rsplit(";", 1)
                self.assertEqual(int(ctl), control(base), path.name)

    def test_threshold_probes_use_one_origin_per_amount(self):
        steps = a6_probes.umbral([50000, 50001])
        origins = [s["request"]["m"].split(";")[1] for s in steps
                   if s["request"]["m"].startswith("TRANSFER")]
        self.assertEqual(origins, ["AC-0002", "AC-0003"])


if __name__ == "__main__":
    unittest.main()
