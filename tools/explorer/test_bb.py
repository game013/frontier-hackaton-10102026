"""Pruebas del cliente instrumentado contra un servidor falso local. No tocan el original."""
import json
import os
import sys
import tempfile
import threading
import time
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

    def test_cache_survives_a_new_cli_process_and_replays_prefix(self):
        self.c.sequence("a").msg("ALTA;X;1", "alta")
        self.c.sequence("b").flush()
        self.assertTrue(self.c.resume("b").msg("ALTA;X;1", "alta").cached)
        Fake.calls.clear()
        fresh = self.client()
        fresh.resume("b").msg("CONSULTA;AC-0001;2", "consulta")
        self.assertEqual([path for path, _, _ in Fake.calls], ["/msg", "/msg"])

    def test_cache_distinguishes_content_type(self):
        self.c.sequence("a").call("POST", "/msg", {"m": "PING;64"}, "json")
        Fake.calls.clear()
        r = self.c.sequence("b").call("POST", "/msg", {"m": "PING;64"}, "texto",
                                       content_type="text/plain")
        self.assertFalse(r.cached)
        self.assertEqual([path for path, _, _ in Fake.calls], ["/__reset", "/msg"])

    def test_fully_cached_sequence_resumes_with_its_reset(self):
        self.c.sequence("a").msg("ALTA;X;1", "alta")
        self.assertTrue(self.c.sequence("b").msg("ALTA;X;1", "alta").cached)
        Fake.calls.clear()
        fresh = self.client()
        with self.assertRaises(ValueError):
            fresh.sequence("b")
        fresh.resume("b").msg("CONSULTA;AC-0001;2", "consulta")
        self.assertEqual([path for path, _, _ in Fake.calls], ["/__reset", "/msg", "/msg"])
        self.assertEqual(fresh.pending_steps("b"), [])

    def test_resume_consumes_pending_already_completed_before_interruption(self):
        self.c.sequence("a").msg("ALTA;X;1", "alta")
        self.assertTrue(self.c.sequence("b").msg("ALTA;X;1", "alta").cached)
        original_remove = self.c._remove_pending
        alta_pending_id = self.c.pending_steps("b")[-1]["pending_id"]

        def interrupted_remove(_seq, pending_id):
            if pending_id == alta_pending_id:
                raise KeyboardInterrupt("corte después de registrar la respuesta")
            original_remove(_seq, pending_id)

        self.c._remove_pending = interrupted_remove
        with self.assertRaises(KeyboardInterrupt):
            self.c.resume("b").flush()
        self.c._remove_pending = original_remove
        Fake.calls.clear()
        self.client().resume("b").msg("CONSULTA;AC-0001;2", "consulta")
        self.assertEqual([path for path, _, _ in Fake.calls], ["/msg"])
        self.assertEqual(self.c.pending_steps("b"), [])

    def test_resume_rejects_unfinished_attempt(self):
        self.c.sequence("a").flush()
        with self.c._locked():
            entries = self.c.entries()
            entries[0]["outcome"] = "pending"
            self.c._replace_entries(entries)
        with self.assertRaises(ValueError):
            self.client().resume("a")

    def test_transport_failure_is_logged_before_propagating(self):
        def unavailable(*_args, **_kwargs):
            raise OSError("network down")

        c = self.client(opener=unavailable)
        with self.assertRaises(OSError):
            c.sequence("s1").flush()
        entry = c.entries()[0]
        self.assertEqual(entry["outcome"], "transport_error")
        self.assertEqual(entry["transport_error"], "OSError")
        self.assertNotIn("status", entry)

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
        self.assertEqual(len(self.c.entries()), 4)  # reset + tres intentos de msg auditados
        self.assertEqual(sum(e.get("infrastructure") == "rate-limit" for e in self.c.entries()), 2)
        for entry in self.c.entries():
            if entry.get("infrastructure"):
                self.assertNotIn("status", entry)
                self.assertNotIn("response", entry)
        self.assertEqual(self.c.used_today(), 4)  # también cuentan para el presupuesto

    def test_resume_retries_reset_after_infrastructure_rate_limits(self):
        sequence = self.c.sequence("s1")
        Fake.rate_limit_next = 4  # retries=3: los cuatro intentos se descartan
        with self.assertRaises(bb.RateLimited):
            sequence.flush()
        self.assertTrue(all(e.get("infrastructure") == "rate-limit" for e in self.c.entries()))
        Fake.rate_limit_next = 0
        self.client().resume("s1").flush()
        self.assertEqual([e["outcome"] for e in self.c.entries()][-1], "completed")
        self.assertEqual(self.c.pending_steps("s1"), [])

    def test_budget_cap_stops(self):
        c = self.client(daily_cap=2)
        s = c.sequence("s1")
        s.msg("PING;1", "h")
        with self.assertRaises(bb.BudgetExceeded):
            s.msg("PING;2", "h")

    def test_budget_is_shared_by_client_instances(self):
        first = self.client(daily_cap=2)
        first.sequence("s1").flush()  # reserva una de las dos solicitudes
        second = self.client(daily_cap=2)
        second.resume("s1").msg("PING;1", "h", confirm=True)
        with self.assertRaises(bb.BudgetExceeded):
            first.resume("s1").msg("PING;2", "h", confirm=True)

    def test_budget_is_atomic_with_distinct_log_paths(self):
        first = self.client(log_path=Path(self.tmp.name) / "a.jsonl", daily_cap=1)
        second = self.client(log_path=Path(self.tmp.name) / "b.jsonl", daily_cap=1)
        start = threading.Barrier(3)
        outcomes = []

        def reserve(client):
            start.wait()
            try:
                client._reserve_request()
            except bb.BudgetExceeded:
                outcomes.append("budget")
            except Exception as err:  # la carrera previa podía perder quota.tmp aquí
                outcomes.append(type(err).__name__)
            else:
                outcomes.append("reserved")

        workers = [threading.Thread(target=reserve, args=(client,)) for client in (first, second)]
        for worker in workers:
            worker.start()
        start.wait()
        for worker in workers:
            worker.join()
        self.assertCountEqual(outcomes, ["reserved", "budget"])
        self.assertEqual(first.used_today(), 1)

    def test_delayed_turns_do_not_burst(self):
        sent: list[float] = []
        guard = threading.Lock()

        class Resp:
            status, headers = 200, {}

            def read(self):
                return b'{"ok":true}'

        def opener(_req, timeout):
            with guard:
                sent.append(time.time())
            return Resp()

        interval, n = 0.125, 11
        reserved, holding = threading.Barrier(n + 1), threading.Event()

        class Delayed(bb.Client):
            def _reserve_request(self):
                result = super()._reserve_request()
                reserved.wait()  # todos reservaron cuota (y, antes del arreglo, turno)
                holding.wait()  # el log queda bloqueado entre la reserva y el envío
                return result

        c = Delayed(base_url=self.url, log_path=self.log, token_var="BB_TEST_TOKEN",
                    min_interval=interval, opener=opener)

        def hold_log_lock():
            reserved.wait()
            with c._locked():
                holding.set()
                time.sleep(1.6)  # los turnos vencen mientras el log está bloqueado

        holder = threading.Thread(target=hold_log_lock)
        workers = [threading.Thread(target=c.execute, args=("s", "POST", "/msg", {"m": f"PING;{i}"}, "h"))
                   for i in range(n)]
        for t in [holder, *workers]:
            t.start()
        for t in [holder, *workers]:
            t.join()
        sent.sort()
        self.assertEqual(len(sent), n)
        gaps = [b - a for a, b in zip(sent, sent[1:])]
        self.assertGreaterEqual(min(gaps), interval * 0.9)
        self.assertTrue(all(sum(1 for t in sent if s <= t < s + 1) <= 10 for s in sent))
        self.assertEqual(c.used_today(), n)

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
