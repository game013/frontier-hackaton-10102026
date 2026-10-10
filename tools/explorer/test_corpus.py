"""Offline tests for the A2 frozen corpus builder and replay safeguards."""
import base64
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

import corpus


ROOT = Path(__file__).resolve().parents[2]


class CorpusTest(unittest.TestCase):
    def test_builder_keeps_all_sequences_and_auth_none_reset_without_inventing_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "corpus"
            manifest = corpus.build(out_dir=out)
            self.assertEqual((manifest["request_count"], manifest["sequence_count"]), (224, 10))
            rows = corpus.read_jsonl(out / "s003-sobre.jsonl")
            self.assertEqual(rows[-1]["source_id"], 50)
            self.assertEqual(rows[-1]["path"], "/__reset")
            self.assertEqual(rows[-1]["auth"], "none")
            self.assertEqual(rows[-1]["status"], 401)
            self.assertNotIn("response_b64", rows[-1])
            malformed = next(row for row in rows if row["source_id"] == 45)
            self.assertEqual(malformed["raw_body"], "{")
            self.assertIsNone(malformed["request"])
            first = corpus.read_jsonl(out / "s001-corpus.jsonl")
            self.assertEqual(len(first), 21)
            self.assertEqual(first[0]["path"], "/__reset")
            self.assertTrue(all("response_b64" not in row for row in first))
            self.assertEqual(len(list(out.glob("*.jsonl"))), 10)

    def test_examples_must_match_the_historical_s001_sequence(self):
        with tempfile.TemporaryDirectory() as temp:
            bad = Path(temp) / "examples.jsonl"
            examples = corpus.read_jsonl(corpus.DEFAULT_EXAMPLES)
            examples[0]["request"] = {"m": "changed"}
            bad.write_text("".join(json.dumps(row) + "\n" for row in examples))
            with self.assertRaisesRegex(ValueError, "no coincide"):
                corpus.build(examples_path=bad, out_dir=Path(temp) / "out")

    def test_strict_json_comparison_and_text_bytes(self):
        self.assertTrue(corpus.strict_equal({"a": [1, True], "b": 2}, {"b": 2, "a": [1, True]}))
        self.assertFalse(corpus.strict_equal(True, 1))
        self.assertFalse(corpus.strict_equal(1, 1.0))
        exp = {"status": 200, "response_b64": base64.b64encode(b"plain").decode(), "response": "plain"}
        got = {"status": 200, "response_b64": base64.b64encode(b"plain").decode(), "response": "plain"}
        self.assertTrue(corpus._byte_match(exp, got))
        self.assertTrue(corpus._contract_match(exp, got))
        got["response_b64"] = base64.b64encode(b"other").decode()
        self.assertFalse(corpus._byte_match(exp, got))
        self.assertFalse(corpus._contract_match(exp, got))
        json_string = {"status": 200, "response": "ok", "raw": '"ok"'}
        actual_json_string = {"status": 200,
                              "response_b64": base64.b64encode(b'"ok"').decode(), "raw": '"ok"'}
        self.assertTrue(corpus._contract_match(json_string, actual_json_string))
        historical_text = {"status": 200, "response": "ok", "raw": "ok"}
        self.assertFalse(corpus._contract_match(historical_text, actual_json_string))
        actual_text = {"status": 200, "response_b64": base64.b64encode(b"ok").decode(), "raw": "ok"}
        self.assertTrue(corpus._contract_match(historical_text, actual_text))

    def test_invalid_utf8_contract_uses_captured_bytes_without_replacement(self):
        original = b"\xff\x80"
        expected = {"status": 200, "response_b64": base64.b64encode(original).decode()}
        same = {"status": 200, "response_b64": base64.b64encode(original).decode(),
                "raw": "\ufffd\ufffd"}
        changed = {"status": 200, "response_b64": base64.b64encode(b"\xff\x81").decode(),
                   "raw": "\ufffd\ufffd"}
        self.assertTrue(corpus._contract_match(expected, same))
        self.assertFalse(corpus._contract_match(expected, changed))
        self.assertTrue(corpus._byte_match(expected, same))
        self.assertFalse(corpus._byte_match(expected, changed))

    def test_request_b64_null_and_empty_remain_distinct_valid_values(self):
        with tempfile.TemporaryDirectory() as temp:
            corpus_dir = Path(temp) / "corpus"
            corpus.build(out_dir=corpus_dir)
            path = corpus_dir / "a1-initial-20261010-retry.jsonl"
            rows = corpus.read_jsonl(path)
            rows[1]["request_b64"] = None
            rows[2]["request_b64"] = ""
            path.write_text("".join(json.dumps(row) + "\n" for row in rows))
            _, sequences = corpus.validate_corpus(corpus_dir)
            selected = dict(sequences)["a1-initial-20261010-retry"]
            self.assertIsNone(selected[1]["request_b64"])
            self.assertEqual(selected[2]["request_b64"], "")

    def test_replay_preserves_absent_and_empty_request_bytes_separately(self):
        with tempfile.TemporaryDirectory() as temp:
            corpus_dir = Path(temp) / "corpus"
            capture_dir = Path(temp) / "captures"
            corpus.build(out_dir=corpus_dir)
            path = corpus_dir / "a1-initial-20261010-retry.jsonl"
            rows = corpus.read_jsonl(path)
            for row in rows[1:3]:
                row["method"] = "GET"
                row["request"] = None
            rows[1]["request_b64"] = None
            rows[2]["request_b64"] = ""
            path.write_text("".join(json.dumps(row) + "\n" for row in rows))
            fake = FakeClient(corpus_dir)
            report, code = corpus.replay(corpus_dir, epoch="v1", prefix="bodybytes",
                                         client=fake, capture_dir=capture_dir)
            self.assertEqual(code, 0)
            no_body = next(call for call in fake.calls if call["source_id"] == rows[1]["source_id"])
            empty_body = next(call for call in fake.calls if call["source_id"] == rows[2]["source_id"])
            self.assertNotIn("raw_body_b64", no_body["kwargs"])
            self.assertEqual(empty_body["kwargs"]["raw_body_b64"], "")
            self.assertIsNone(no_body["body"])
            self.assertIsNone(empty_body["body"])

    def test_validate_rejects_noncanonical_initial_reset(self):
        with tempfile.TemporaryDirectory() as temp:
            corpus_dir = Path(temp) / "corpus"
            corpus.build(out_dir=corpus_dir)
            path = corpus_dir / "s001-corpus.jsonl"
            rows = corpus.read_jsonl(path)
            rows[0]["method"] = "GET"
            path.write_text("".join(json.dumps(row) + "\n" for row in rows))
            with self.assertRaisesRegex(ValueError, "reset"):
                corpus.validate_corpus(corpus_dir)

    def test_contract_comparison_requires_matching_status(self):
        expected = {"status": 200, "raw": '{"ok":true}'}
        actual = {"status": 201, "raw": '{"ok":true}',
                  "response_b64": base64.b64encode(b'{"ok":true}').decode()}
        self.assertFalse(corpus._contract_match(expected, actual))

    def test_invalid_corpus_bytes_fail_before_client_is_used(self):
        with tempfile.TemporaryDirectory() as temp:
            corpus_dir = Path(temp) / "corpus"
            corpus.build(out_dir=corpus_dir)
            path = corpus_dir / "a1-initial-20261010-retry.jsonl"
            rows = corpus.read_jsonl(path)
            rows[1]["request_b64"] = "!"
            path.write_text("".join(json.dumps(row) + "\n" for row in rows))
            with self.assertRaises(Exception):
                corpus.validate_corpus(corpus_dir)

    def test_replay_compares_all_224_rows_including_resets_and_replays_id45_and_id50(self):
        with tempfile.TemporaryDirectory() as temp:
            corpus_dir = Path(temp) / "corpus"
            capture_dir = Path(temp) / "captures"
            corpus.build(out_dir=corpus_dir)
            fake = FakeClient(corpus_dir)
            report, code = corpus.replay(corpus_dir, epoch="v1", prefix="offline",
                                         client=fake, capture_dir=capture_dir)
            self.assertEqual(code, 0)
            self.assertEqual(report["request_count"], 224)
            self.assertEqual(report["contract_compared"], 224)
            self.assertEqual(report["contract_deltas"], 0)
            self.assertEqual(report["missing_historical_bytes"], 50)
            malformed = next(call for call in fake.calls if call["source_id"] == 45)
            self.assertEqual(malformed["kwargs"].get("raw_body"), "{")
            self.assertIsNone(malformed["body"])
            unauth_reset = next(call for call in fake.calls if call["source_id"] == 50)
            self.assertEqual(unauth_reset["path"], "/__reset")
            self.assertEqual(unauth_reset["kwargs"]["auth"], "none")
            saved = corpus.read_jsonl(capture_dir / "offline" / "corpus.jsonl")
            self.assertEqual(len(saved), 224)
            self.assertEqual(saved[0]["source_id"], 1)
            self.assertEqual(saved[-1]["source_id"], 225)

    def test_replay_budget_guard_runs_before_sequence_and_capture_creation(self):
        with tempfile.TemporaryDirectory() as temp:
            corpus_dir = Path(temp) / "corpus"
            capture_dir = Path(temp) / "captures"
            corpus.build(out_dir=corpus_dir)
            fake = FakeClient(corpus_dir, used=7700)
            with self.assertRaisesRegex(ValueError, "cuota insuficiente"):
                corpus.replay(corpus_dir, epoch="v1", prefix="over-budget", client=fake,
                              capture_dir=capture_dir)
            self.assertEqual(fake.sequence_count, 0)
            self.assertFalse((capture_dir / "over-budget").exists())

    def test_replay_request_ceiling_rejects_before_token_or_capture_use(self):
        with tempfile.TemporaryDirectory() as temp:
            corpus_dir = Path(temp) / "corpus"
            capture_dir = Path(temp) / "captures"
            corpus.build(out_dir=corpus_dir)
            fake = FakeClient(corpus_dir)
            with self.assertRaisesRegex(ValueError, "supera max-requests"):
                corpus.replay(corpus_dir, epoch="v1", prefix="too-small", max_requests=223,
                              client=fake, capture_dir=capture_dir)
            self.assertEqual(fake.sequence_count, 0)
            self.assertFalse((capture_dir / "too-small").exists())

    def test_replay_failure_persists_partial_report_and_returns_incomplete_code(self):
        with tempfile.TemporaryDirectory() as temp:
            corpus_dir = Path(temp) / "corpus"
            capture_dir = Path(temp) / "captures"
            corpus.build(out_dir=corpus_dir)
            fake = FakeClient(corpus_dir, fail_after=2)
            report, code = corpus.replay(corpus_dir, epoch="v1", prefix="partial", client=fake,
                                         capture_dir=capture_dir)
            self.assertEqual(code, 2)
            self.assertEqual(report["request_count"], 2)
            saved = json.loads((capture_dir / "partial" / "report.json").read_text())
            self.assertEqual(saved["request_count"], 2)
            self.assertEqual(len(corpus.read_jsonl(capture_dir / "partial" / "corpus.jsonl")), 2)


class FakeClient:
    """Sequence double backed by expected rows; it performs no network calls."""

    epoch = "v1"
    daily_cap = 7800

    def __init__(self, corpus_dir, used=0, fail_after=None):
        _, sequences = corpus.validate_corpus(corpus_dir)
        self.rows = dict(sequences)
        self.used = used
        self.fail_after = fail_after
        self.calls = []
        self.sequence_count = 0
        self.current = None
        self.next_id = 1

    def used_today(self):
        return self.used

    def sequence(self, seq, *_args, **_kwargs):
        self.sequence_count += 1
        source_seq = seq.split("-", 1)[1]
        return FakeSequence(self, seq, self.rows[source_seq])

    def seq_steps(self, seq):
        if self.current is None or self.current.seq != seq:
            return []
        return self.current.entries

    def conclude(self, *_args):
        pass


class FakeSequence:
    def __init__(self, client, seq, rows):
        self.client = client
        self.seq = seq
        self.rows = rows
        self.index = 0
        self.entries = []

    def __enter__(self):
        self.client.current = self
        return self

    def __exit__(self, *_args):
        return False

    def flush(self):
        self.entries.append(self._actual(self.rows[0]))

    def call(self, method, path, body, _hypothesis, **kwargs):
        expected = self.rows[self.index + 1]
        self.index += 1
        self.client.calls.append({"source_id": expected["source_id"], "method": method,
                                  "path": path, "body": body, "kwargs": kwargs})
        if self.client.fail_after is not None and len(self.client.calls) >= self.client.fail_after:
            raise OSError("simulated transport failure")
        entry = self._actual(expected)
        self.entries.append(entry)
        return SimpleNamespace(id=entry["id"], entry=entry)

    def _actual(self, expected):
        if "response_b64" in expected:
            response_bytes = base64.b64decode(expected["response_b64"])
        else:
            response_bytes = expected["raw"].encode("utf-8")
        entry = {"id": self.client.next_id, "seq": self.seq,
                 "method": expected["method"], "path": expected["path"],
                 "auth": expected["auth"], "status": expected["status"],
                 "response": expected["response"],
                 "response_b64": base64.b64encode(response_bytes).decode("ascii"),
                 "raw": response_bytes.decode("utf-8", errors="replace"),
                 "epoch": "v1", "outcome": "completed"}
        self.client.next_id += 1
        return entry


if __name__ == "__main__":
    unittest.main()
