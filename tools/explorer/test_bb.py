"""Pruebas del cliente instrumentado contra un servidor falso local. No tocan el original."""
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import bb  # noqa: E402

TOKEN = "tok-secreto-de-prueba"


class Fake(BaseHTTPRequestHandler):
    calls: list = []
    rate_limit_next = 0
    counter = 0

    def log_message(self, *a):
        pass

    def _reply(self, status, body, extra=None):
        Fake.counter += 1
        data = body.encode()
        self.send_response(status)
        self.send_header("X-Req", str(Fake.counter))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n).decode()
        Fake.calls.append((self.path, body, self.headers.get("Authorization")))
        if Fake.rate_limit_next:
            Fake.rate_limit_next -= 1
            return self._reply(429, "slow down", {"X-Frontier-Infra": "rate-limit"})
        if self.headers.get("Authorization") != f"Bearer {TOKEN}":
            return self._reply(401, "no autorizado")
        if self.path == "/__reset":
            return self._reply(200, '{"ok":true}')
        if self.path == "/msg":
            return self._reply(200, json.dumps({"eco": json.loads(body)["m"]}))
        self._reply(404, "Not Found")

    do_GET = do_POST


class ClientTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.srv.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        Fake.calls.clear()
        Fake.rate_limit_next = 0
        self.tmp = tempfile.TemporaryDirectory()
        self.log = Path(self.tmp.name) / "experimentos.jsonl"
        os.environ["BB_TEST_TOKEN"] = TOKEN
        self.c = self.client()

    def client(self, **kw):
        args = dict(base_url=self.url, log_path=self.log, token_var="BB_TEST_TOKEN",
                    min_interval=0, sleep=lambda s: None)
        args.update(kw)
        return bb.Client(**args)

    def tearDown(self):
        self.tmp.cleanup()

    def test_sequence_starts_with_reset_and_logs_contract_fields(self):
        s = self.c.sequence("s1", "estado limpio")
        r = s.msg("PING;64", "PING sin estado")
        self.assertEqual([p for p, _, _ in Fake.calls], ["/__reset", "/msg"])
        es = self.c.entries()
        self.assertEqual([e["id"] for e in es], [1, 2])
        self.assertEqual(es[0]["path"], "/__reset")
        for k in ("id", "seq", "x_req", "hipotesis", "request", "status", "response", "conclusion"):
            self.assertIn(k, es[1])
        self.assertEqual(es[1]["request"], {"m": "PING;64"})
        self.assertEqual(es[1]["response"], {"eco": "PING;64"})
        self.assertEqual(r.x_req, es[1]["x_req"])

    def test_token_never_written(self):
        s = self.c.sequence("s1")
        s.msg("PING;64", "h", auth="scheme")
        s.msg("PING;64", "h", auth="none", confirm=True)
        self.assertNotIn(TOKEN, self.log.read_text())

    def test_hypothesis_required(self):
        s = self.c.sequence("s1")
        with self.assertRaises(ValueError):
            s.msg("PING;64", "  ")

    def test_duplicate_sequence_name_rejected(self):
        self.c.sequence("s1").msg("PING;1", "h")
        with self.assertRaises(ValueError):
            self.c.sequence("s1")

    def test_cache_skips_network_and_replays_prefix_on_miss(self):
        a = self.c.sequence("a")
        a.msg("ALTA;X;1", "h1")
        a.msg("CONSULTA;AC-0001;2", "h2")
        Fake.calls.clear()
        b = self.c.sequence("b")
        r = b.msg("ALTA;X;1", "h1")
        self.assertTrue(r.cached)
        self.assertEqual(Fake.calls, [])
        r2 = b.msg("CONSULTA;AC-0009;3", "nuevo")
        self.assertFalse(r2.cached)
        # Se reenvía el reset y el paso cacheado antes del nuevo, para igualar el estado.
        self.assertEqual([p for p, _, _ in Fake.calls], ["/__reset", "/msg", "/msg"])
        self.assertEqual([e["seq"] for e in self.c.entries()[-3:]], ["b", "b", "b"])

    def test_cache_respects_epoch_and_confirm(self):
        self.c.sequence("a").msg("PING;64", "h")
        Fake.calls.clear()
        self.assertTrue(self.c.sequence("b").msg("PING;64", "h").cached)
        self.assertFalse(self.c.sequence("c").msg("PING;64", "h", confirm=True).cached)
        Fake.calls.clear()
        tarde = self.client(epoch="v2")
        self.assertFalse(tarde.sequence("d").msg("PING;64", "h").cached)

    def test_rate_limit_discarded_and_retried(self):
        s = self.c.sequence("s1")
        Fake.rate_limit_next = 2
        r = s.msg("PING;64", "h")
        self.assertEqual(r.status, 200)
        self.assertEqual(len(self.c.entries()), 2)  # reset + msg; los 429 no son evidencia
        self.assertNotIn("slow down", self.log.read_text())
        self.assertEqual(self.c.used_today(), 4)  # pero sí cuentan para el presupuesto

    def test_budget_cap_stops(self):
        c = self.client(daily_cap=2)
        s = c.sequence("s1")
        s.msg("PING;1", "h")
        with self.assertRaises(bb.BudgetExceeded):
            s.msg("PING;2", "h")

    def test_non_json_response_kept_verbatim(self):
        s = self.c.sequence("s1")
        r = s.call("GET", "/nada", None, "ruta inexistente")
        self.assertEqual((r.status, r.response, r.raw), (404, "Not Found", "Not Found"))

    def test_conclude_and_resume(self):
        self.c.sequence("s1").msg("PING;1", "h")
        self.c.conclude(2, "aprendido")
        self.assertEqual(self.c.entries()[1]["conclusion"], "aprendido")
        self.c.resume("s1").msg("PING;2", "h")
        self.assertEqual(self.c.entries()[-1]["seq"], "s1")


if __name__ == "__main__":
    unittest.main()
