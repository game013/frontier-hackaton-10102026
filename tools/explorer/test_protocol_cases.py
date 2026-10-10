"""Offline checks for the protocol-case extractor (no token, no network)."""
from __future__ import annotations

import base64
import json
import unittest

from tools.explorer.protocol_cases import ResponseBytesError, extract


def b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode()


def record(rid, m, response, raw=None, **over):
    r = {"id": str(rid), "epoch": "v1", "method": "POST", "path": "/msg", "auth": "valid",
         "outcome": "completed", "status": 400, "request_b64": b64(json.dumps({"m": m})),
         "raw": response if raw is None else raw, "response_b64": b64(response)}
    r.update(over)
    return json.dumps(r, ensure_ascii=False)


E202 = '{"error":"E202","mensaje":"control inválido"}'


class ExtractTest(unittest.TestCase):
    def test_body_comes_from_response_b64_not_raw(self):
        cases, conflicts = extract([record(1, "ALTA;A;1", E202, raw="texto legible distinto")], "v1")
        self.assertEqual(conflicts, [])
        self.assertEqual([c["body"] for c in cases], [E202])

    def test_skips_records_without_response_b64(self):
        cases, _ = extract([record(1, "ALTA;A;1", E202, response_b64=None)], "v1")
        self.assertEqual(cases, [])

    def test_rejects_response_bytes_not_utf8(self):
        bad = base64.b64encode(b'{"error":"E202","mensaje":"\xff"}').decode()
        with self.assertRaises(ResponseBytesError):
            extract([record(7, "ALTA;A;1", E202, response_b64=bad)], "v1")

    def test_conflict_on_different_bytes_for_same_m(self):
        other = '{"error":"E201","mensaje":"control mal formado"}'
        _, conflicts = extract([record(1, "ALTA;A;1", E202), record(2, "ALTA;A;1", other)], "v1")
        self.assertEqual(conflicts, [("ALTA;A;1", "1", "2")])


if __name__ == "__main__":
    unittest.main()
