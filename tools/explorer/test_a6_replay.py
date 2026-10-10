"""Offline tests for the A6 v1→v2 replay; a fake client stands in for the original."""
import base64
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

import a6_replay


def b64(text):
    return base64.b64encode(text.encode()).decode()


def row(id_, seq, path="/msg", body=None, status=200, response='{"ok":true}', **extra):
    data = None if body is None else json.dumps(body)
    out = {"id": id_, "seq": seq, "method": "POST", "path": path, "auth": "valid",
           "request": body, "request_b64": "" if data is None else b64(data),
           "status": status, "response_b64": b64(response), "raw": response,
           "outcome": "completed", "epoch": "v1"}
    out.update(extra)
    return out


def write_jsonl(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


class FakeClient:
    """Answers with the base bytes unless `changes` maps a base ID to a new (status, body)."""

    epoch = "v1"
    daily_cap = 7800

    def __init__(self, sources, changes=None, used=0, fail_at=None):
        self.by_seq = {name: rows for name, rows in sources}
        self.changes = changes or {}
        self.used = used
        self.fail_at = fail_at
        self.calls = []
        self.log = []
        self.concluded = {}
        self.sequences = 0

    def used_today(self):
        return self.used

    def seq_steps(self, seq):
        return [e for e in self.log if e["seq"] == seq]

    def pending_steps(self, seq):
        return []

    def conclude(self, entry_id, text):
        self.concluded[entry_id] = text

    def sequence(self, seq, hipotesis, no_cache=False):
        assert no_cache
        self.sequences += 1
        return FakeSequence(self, seq)

    def answer(self, seq, base, call):
        if self.fail_at is not None and len(self.log) >= self.fail_at:
            raise OSError("corte simulado")
        status, body = self.changes.get(base["id"], (base["status"], None))
        raw = body if body is not None else base64.b64decode(base["response_b64"]).decode()
        entry = {"id": 5000 + len(self.log), "seq": seq, "method": call["method"],
                 "path": call["path"], "auth": call["kwargs"].get("auth", "valid"),
                 "request_b64": call["kwargs"].get("raw_body_b64"), "status": status,
                 "response_b64": b64(raw), "raw": raw, "outcome": "completed"}
        self.log.append(entry)
        return entry


class FakeSequence:
    def __init__(self, client, seq):
        self.client = client
        self.seq = seq
        self.source = seq.split("-", 1)[1]
        self.step = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def flush(self):
        base = self.client.by_seq[self.source][0]
        self.client.answer(self.seq, base, {"method": "POST", "path": "/__reset", "kwargs": {}})

    def call(self, method, path, body, hipotesis, **kwargs):
        assert body is None and hipotesis
        self.step += 1
        base = self.client.by_seq[self.source][self.step]
        call = {"method": method, "path": path, "kwargs": kwargs, "base_id": base["id"]}
        self.client.calls.append(call)
        return SimpleNamespace(entry=self.client.answer(self.seq, base, call))


class A6ReplayTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.dir = Path(self.temp.name)
        self.log = self.dir / "log.jsonl"
        self.a2 = self.dir / "a2.jsonl"
        write_jsonl(self.a2, [
            row(227, "a2-s001", path="/__reset"),
            row(228, "a2-s001", body={"m": "PING;64"}, response='{"pong":true}'),
        ])
        write_jsonl(self.log, [
            row(451, "a3-v1-01-ids", path="/__reset"),
            row(452, "a3-v1-01-ids", body={"m": "ALTA;Lucia;82"}, status=201,
                response='{"cuentaId":"AC-0001"}'),
            row(453, "a3-v1-01-ids", path="/__reset", auth="none", status=401,
                response='{"error":"E001"}', request_b64=None),
            row(618, "a3-v1-20-aislamiento-team", path="/__reset", status=401),
            row(671, "a3-v1r-01-ids", path="/__reset"),
            row(1935, "a5-c01-notas", path="/__reset", epoch="v2"),
            row(1966, "a5-c01-notas-r", path="/__reset", epoch="v2"),
        ])

    def tearDown(self):
        self.temp.cleanup()

    def test_sources_keep_order_and_skip_team_token_and_repeats(self):
        sources = a6_replay.load_sources(self.log, self.a2)
        self.assertEqual([s for s, _ in sources], ["a2-s001", "a3-v1-01-ids", "a5-c01-notas"])
        self.assertEqual([r["id"] for r in sources[1][1]], [451, 452, 453])

    def test_sources_reject_rows_without_bytes_or_incomplete(self):
        rows = a6_replay.read_jsonl(self.log)
        rows[1]["outcome"] = "transport_error"
        write_jsonl(self.log, rows)
        with self.assertRaisesRegex(ValueError, "no es evidencia completa"):
            a6_replay.load_sources(self.log, self.a2)

    def test_replay_without_changes_resends_exact_bytes_and_reports_no_delta(self):
        sources = a6_replay.load_sources(self.log, self.a2)
        fake = FakeClient(sources)
        report, code = a6_replay.replay(sources, epoch="v2", prefix="t", client=fake,
                                        capture_dir=self.dir / "out")
        self.assertEqual(code, 0)
        self.assertEqual(report["request_count"], 6)
        self.assertEqual(report["deltas"], [])
        alta = next(c for c in fake.calls if c["base_id"] == 452)
        self.assertEqual(alta["kwargs"]["raw_body_b64"], b64(json.dumps({"m": "ALTA;Lucia;82"})))
        reset = next(c for c in fake.calls if c["base_id"] == 453)
        self.assertNotIn("raw_body_b64", reset["kwargs"])
        self.assertEqual(reset["kwargs"]["auth"], "none")
        self.assertEqual(len(fake.concluded), 6)
        self.assertEqual(fake.epoch, "v2")

    def test_replay_separates_byte_only_and_contract_deltas(self):
        sources = a6_replay.load_sources(self.log, self.a2)
        fake = FakeClient(sources, changes={228: (200, '{ "pong": true }'),
                                            452: (400, '{"error":"E999"}')})
        report, code = a6_replay.replay(sources, epoch="v2", prefix="t", client=fake,
                                        capture_dir=self.dir / "out")
        self.assertEqual(code, 1)
        self.assertEqual((report["raw_deltas"], report["contract_deltas"]), (2, 1))
        by_base = {d["base_id"]: d for d in report["deltas"]}
        self.assertTrue(by_base[228]["contract_equal"])
        self.assertEqual((by_base[452]["base_status"], by_base[452]["v2_status"]), (201, 400))
        saved = json.loads((self.dir / "out" / "t" / "report.json").read_text())
        self.assertEqual(saved["raw_deltas"], 2)
        conclusion = next(t for t in fake.concluded.values() if "base ID 452" in t)
        self.assertIn("bytes=delta", conclusion)

    def test_budget_and_ceiling_checked_before_any_sequence(self):
        sources = a6_replay.load_sources(self.log, self.a2)
        fake = FakeClient(sources, used=7797)
        with self.assertRaisesRegex(ValueError, "cuota insuficiente"):
            a6_replay.replay(sources, epoch="v2", prefix="t", client=fake,
                             capture_dir=self.dir / "out")
        with self.assertRaisesRegex(ValueError, "supera max-requests"):
            a6_replay.replay(sources, epoch="v2", prefix="t", max_requests=5,
                             client=FakeClient(sources), capture_dir=self.dir / "out")
        self.assertEqual(fake.sequences, 0)
        self.assertFalse((self.dir / "out" / "t").exists())

    def test_failure_concludes_captured_steps_and_returns_incomplete(self):
        sources = a6_replay.load_sources(self.log, self.a2)
        fake = FakeClient(sources, fail_at=3)
        report, code = a6_replay.replay(sources, epoch="v2", prefix="t", client=fake,
                                        capture_dir=self.dir / "out")
        self.assertEqual(code, 2)
        self.assertTrue(report["incomplete"])
        self.assertEqual(report["request_count"], 3)
        self.assertEqual(len(fake.concluded), 3)


if __name__ == "__main__":
    unittest.main()
