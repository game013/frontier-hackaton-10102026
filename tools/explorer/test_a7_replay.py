"""Offline tests for the A7 v2→v2 replay; reuses the A6 fake client, never the original."""
import json
from pathlib import Path
import tempfile
import unittest

import a7_replay
from test_a6_replay import FakeClient, b64, row, write_jsonl


class A7ReplayTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.dir = Path(self.temp.name)
        self.capture = self.dir / "a6.jsonl"
        self.log = self.dir / "log.jsonl"
        write_jsonl(self.capture, [
            row(2020, "a6-v2-a2-s001", path="/__reset", epoch="v2"),
            row(2021, "a6-v2-a2-s001", body={"m": "PING;64"}, response='{"pong":true}',
                epoch="v2"),
        ])
        write_jsonl(self.log, [
            row(2745, "a6-v2-sonda-01", path="/__reset", epoch="v2"),
            row(2746, "a6-v2-sonda-01", body={"m": "ALTA;Lucia;82"}, status=201,
                response='{"cuentaId":"AC-0001"}', epoch="v2"),
            row(2862, "a6-v2r-sonda-01", path="/__reset", epoch="v2"),
            row(2020, "a6-v2-a2-s001", path="/__reset", epoch="v2"),
        ])

    def tearDown(self):
        self.temp.cleanup()

    def test_sources_are_a6_capture_plus_probes_without_repeats(self):
        sources = a7_replay.load_sources(self.capture, self.log)
        self.assertEqual([s for s, _ in sources], ["a2-s001", "sonda-01"])
        self.assertEqual([r["id"] for r in sources[1][1]], [2745, 2746])

    def test_duplicate_source_between_capture_and_log_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicadas"):
            a7_replay.load_sources(self.capture, self.log, patterns=("a6-v2-*",))

    def test_replay_labels_hypotheses_and_conclusions_as_a7(self):
        sources = a7_replay.load_sources(self.capture, self.log)
        fake = FakeClient(sources)
        report, code = a7_replay.replay(sources, epoch="v2", prefix="t", client=fake,
                                        capture_dir=self.dir / "out", label=a7_replay.LABEL,
                                        expectation=a7_replay.EXPECTATION)
        self.assertEqual((code, report["request_count"], report["deltas"]), (0, 4, []))
        self.assertTrue(all(t.startswith("A7 replay v2; base ID") for t in fake.concluded.values()))
        alta = next(c for c in fake.calls if c["base_id"] == 2746)
        self.assertEqual(alta["kwargs"]["raw_body_b64"], b64(json.dumps({"m": "ALTA;Lucia;82"})))

    def test_any_change_against_a6_is_reported(self):
        sources = a7_replay.load_sources(self.capture, self.log)
        fake = FakeClient(sources, changes={2746: (201, '{"cuentaId":"AC-0002"}')})
        report, code = a7_replay.replay(sources, epoch="v2", prefix="t", client=fake,
                                        capture_dir=self.dir / "out")
        self.assertEqual((code, report["contract_deltas"]), (1, 1))
        self.assertEqual(report["deltas"][0]["base_id"], 2746)

    def test_real_sources_cover_the_whole_a6_v2_evidence(self):
        sources = a7_replay.load_sources()
        self.assertEqual(len(sources), 65)
        ids = sorted(r["id"] for _, rows in sources for r in rows)
        self.assertEqual(ids, list(range(2020, 2862)))


if __name__ == "__main__":
    unittest.main()
