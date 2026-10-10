"""Pruebas A0 del cliente instrumentado contra servidor falso local."""
import base64
import json
import multiprocessing
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
    calls = []
    rate_limit_next = 0
    counter = 0

    def log_message(self, *a):
        pass

    def _reply(self, status, body, extra=None):
        Fake.counter += 1
        data = body if isinstance(body, bytes) else body.encode()
        self.send_response(status)
        self.send_header("X-Req", str(Fake.counter))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n)
        Fake.calls.append((self.path, body, self.headers.get("Authorization")))
        if Fake.rate_limit_next:
            Fake.rate_limit_next -= 1
            return self._reply(429, b"slow down", {"X-Frontier-Infra": "rate-limit"})
        if self.headers.get("Authorization") not in (f"Bearer {TOKEN}", "Bearer otro-token"):
            return self._reply(401, "no autorizado")
        if self.path == "/__reset":
            return self._reply(200, b'{"ok":true}')
        if self.path == "/msg":
            try:
                value = json.loads(body)
                return self._reply(200, json.dumps({"eco": value["m"]}))
            except (ValueError, KeyError, TypeError):
                return self._reply(200, body)
        self._reply(404, "Not Found")

    do_GET = do_POST


def _locked_child(url, log, coord, token, entered, release, finished):
    os.environ["BB_TEST_TOKEN"] = token
    c = bb.Client(base_url=url, log_path=log, token_var="BB_TEST_TOKEN", coord_dir=coord,
                  min_interval=0, sleep=lambda _: None)
    with c.sequence("child-a") as s:
        s.flush()
        entered.set()
        release.wait(5)
        s.msg("PING;1", "child A")
    finished.set()


class ClientTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.srv.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        Fake.calls.clear()
        Fake.rate_limit_next = 0
        self.tmp = tempfile.TemporaryDirectory()
        self.log = Path(self.tmp.name) / "experimentos.jsonl"
        os.environ["BB_TEST_TOKEN"] = TOKEN
        self.c = self.client()

    def client(self, **kw):
        args = dict(base_url=self.url, log_path=self.log, token_var="BB_TEST_TOKEN",
                    min_interval=0, sleep=lambda _: None,
                    coord_dir=Path(self.tmp.name) / ".explore")
        args.update(kw)
        return bb.Client(**args)

    def tearDown(self):
        self.tmp.cleanup()

    def test_sequence_context_resets_lazily_and_logs_contract(self):
        s = self.c.sequence("s1", "estado limpio")
        self.assertEqual(Fake.calls, [])  # __enter__ no hace flush
        with s:
            r = s.msg("PING;64", "PING sin estado")
            self.assertEqual([p for p, _, _ in Fake.calls], ["/__reset", "/msg"])
            es = self.c.entries()
            self.assertEqual([e["id"] for e in es], [1, 2])
            self.assertEqual(es[1]["request"], {"m": "PING;64"})
            self.assertEqual(es[1]["response"], {"eco": "PING;64"})
            self.assertEqual(r.x_req, es[1]["x_req"])
        with self.assertRaises(RuntimeError):
            s.msg("PING;1", "cerrada")

    def test_calls_and_execute_require_sequence_owner(self):
        s = self.c.sequence("s")
        with self.assertRaises(RuntimeError):
            s.flush()
        with self.assertRaises(RuntimeError):
            s.msg("PING;1", "fuera")
        with self.assertRaises(RuntimeError):
            self.c.execute("s", "POST", "/msg", {}, "directo")
        self.assertEqual(Fake.calls, [])

    def test_hypothesis_required_and_token_never_written(self):
        with self.c.sequence("s") as s:
            with self.assertRaises(ValueError):
                s.msg("PING;64", "  ")
            s.msg("PING;64", "h", auth="scheme")
            s.msg("PING;64", "h", auth="none", confirm=True)
        self.assertNotIn(TOKEN, self.log.read_text())

    def test_duplicate_sequence_name_rejected(self):
        with self.c.sequence("s1") as s:
            s.msg("PING;1", "h")
        with self.assertRaises(ValueError):
            with self.c.sequence("s1"):
                pass

    def test_cache_hit_and_miss_replays_prefix(self):
        with self.c.sequence("a") as a:
            a.msg("ALTA;X;1", "h1")
            a.msg("CONSULTA;AC-0001;2", "h2")
        Fake.calls.clear()
        with self.c.sequence("b") as b:
            r = b.msg("ALTA;X;1", "h1")
            self.assertTrue(r.cached)
            self.assertEqual(Fake.calls, [])
            r2 = b.msg("CONSULTA;AC-0009;3", "nuevo")
            self.assertFalse(r2.cached)
        self.assertEqual([p for p, _, _ in Fake.calls], ["/__reset", "/msg", "/msg"])
        self.assertEqual([e["seq"] for e in self.c.entries()[-3:]], ["b"] * 3)

    def test_no_cache_bypasses_lookup(self):
        with self.c.sequence("a") as a:
            a.msg("PING;64", "h")
        Fake.calls.clear()
        with self.c.sequence("b", no_cache=True) as b:
            r = b.msg("PING;64", "h")
        self.assertFalse(r.cached)
        self.assertEqual([p for p, _, _ in Fake.calls], ["/__reset", "/msg"])

    def test_cache_distinguishes_content_type(self):
        with self.c.sequence("a") as a:
            a.call("POST", "/msg", {"m": "PING;64"}, "json")
        Fake.calls.clear()
        with self.c.sequence("b") as b:
            r = b.call("POST", "/msg", {"m": "PING;64"}, "texto", content_type="text/plain")
        self.assertFalse(r.cached)
        self.assertEqual([p for p, _, _ in Fake.calls], ["/__reset", "/msg"])

    def test_resume_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "no se puede retomar"):
            self.c.resume("missing")

    def test_transport_failure_is_logged_and_context_releases_lock(self):
        def unavailable(*_args, **_kwargs):
            raise OSError("network down")
        c = self.client(opener=unavailable)
        with self.assertRaises(OSError):
            with c.sequence("s") as s:
                s.flush()
        self.assertEqual(c.entries()[0]["outcome"], "transport_error")
        self.assertNotIn("status", c.entries()[0])
        # Excepción dentro del bloque también libera la coordinación.
        with self.assertRaisesRegex(ValueError, "boom"):
            with self.c.sequence("next"):
                raise ValueError("boom")
        with self.c.sequence("after") as s:
            s.flush()

    def test_normal_exit_flushes_cached_steps_and_exception_aborts(self):
        with self.c.sequence("source") as s:
            s.msg("PING;64", "h")
        Fake.calls.clear()
        with self.c.sequence("cached") as s:
            self.assertTrue(s.msg("PING;64", "h").cached)
            self.assertEqual(Fake.calls, [])
        self.assertEqual([p for p, _, _ in Fake.calls], ["/__reset", "/msg"])
        Fake.calls.clear()
        with self.assertRaises(ValueError):
            with self.c.sequence("aborted") as s:
                self.assertTrue(s.msg("PING;64", "h").cached)
                raise ValueError("abort")
        self.assertEqual(Fake.calls, [])

    def test_explicit_close_aborts_without_reentering_on_exit(self):
        with self.c.sequence("closed") as s:
            s.close()
        self.assertEqual(Fake.calls, [])
        with self.c.sequence("after-close") as s:
            s.msg("PING;1", "lock libre")

    def test_initial_reset_required_and_failed_reset_aborts(self):
        with self.c.sequence("initial") as s:
            with self.assertRaisesRegex(RuntimeError, "reset inicial"):
                self.c.execute("initial", "POST", "/msg", {}, "bypass")
            s.flush()
        os.environ["BB_WRONG_TOKEN"] = "wrong-token"
        c = self.client(token_var="BB_WRONG_TOKEN")
        with c.sequence("failed-reset") as s:
            with self.assertRaisesRegex(RuntimeError, "reset no exitoso"):
                s.flush()
            with self.assertRaises(RuntimeError):
                s.msg("PING;1", "no enviar tras reset fallido")
        self.assertEqual(c.entries()[-1]["status"], 401)

    def test_runner_validates_all_steps_before_network(self):
        fixture = Path(self.tmp.name) / "bad.jsonl"
        fixture.write_text('{"request":{"m":"PING;1"},"hipotesis":"h"}\n{"request":{}}\n')
        with self.assertRaisesRegex(ValueError, "falta hipótesis"):
            bb.main(["run", "invalid", str(fixture)])
        self.assertEqual(Fake.calls, [])

    def test_raw_body_base64_round_trips_non_utf8(self):
        raw = b"\xff\x00\x80"
        with self.c.sequence("s") as s:
            result = s.call("POST", "/msg", None, "bytes arbitrarios", raw_body_b64=base64.b64encode(raw).decode())
        entry = self.c.entries()[-1]
        self.assertEqual(Fake.calls[-1][1], raw)
        self.assertEqual(entry["request_b64"], base64.b64encode(raw).decode())
        self.assertEqual(entry["response_b64"], base64.b64encode(raw).decode())
        self.assertEqual(entry["raw"], raw.decode("utf-8", errors="replace"))
        self.assertEqual(result.response, raw.decode("utf-8", errors="replace"))

    def test_base64_distinguishes_absent_and_empty_body(self):
        with self.c.sequence("s") as s:
            s.call("GET", "/nada", None, "sin cuerpo")
            s.call("POST", "/nada", None, "cuerpo vacío")
        self.assertIsNone(self.c.entries()[-2]["request_b64"])
        self.assertEqual(self.c.entries()[-1]["request_b64"], "")

    def test_rate_limit_discarded_and_retried(self):
        Fake.rate_limit_next = 2
        with self.c.sequence("s") as s:
            r = s.msg("PING;64", "h")
        es = self.c.entries()
        self.assertEqual(r.status, 200)
        self.assertEqual(len(es), 4)
        self.assertEqual(sum(e.get("infrastructure") == "rate-limit" for e in es), 2)
        self.assertEqual(self.c.used_today(), 4)

    def test_budget_cap_stops(self):
        c = self.client(daily_cap=1)
        with c.sequence("s") as s:
            with self.assertRaises(bb.BudgetExceeded):
                s.msg("PING;1", "h")
        self.assertEqual(len(Fake.calls), 1)  # reset consume el único turno

    def test_delayed_turns_do_not_burst_low_level(self):
        sent = []
        guard = threading.Lock()
        class Resp:
            status, headers = 200, {}
            def read(self): return b'{"ok":true}'
        def opener(_req, timeout):
            with guard: sent.append(time.time())
            return Resp()
        interval, n = 0.125, 11
        reserved, holding = threading.Barrier(n + 1), threading.Event()
        class Delayed(bb.Client):
            def _reserve_request(self):
                result = super()._reserve_request()
                reserved.wait()
                holding.wait()
                return result
        c = Delayed(base_url=self.url, log_path=self.log, token_var="BB_TEST_TOKEN",
                    min_interval=interval, opener=opener, daily_cap=n,
                    coord_dir=Path(self.tmp.name) / ".explore")
        def send(i):
            c._execute("low", "POST", "/msg", {"m": f"PING;{i}"}, "low level")
        workers = [threading.Thread(target=send, args=(i,)) for i in range(n)]
        def hold_log_lock():
            reserved.wait()
            with c._locked():
                holding.set()
                time.sleep(1.6)
        holder = threading.Thread(target=hold_log_lock)
        try:
            for t in [holder, *workers]: t.start()
            for t in [holder, *workers]: t.join(8)
            self.assertTrue(all(not t.is_alive() for t in [holder, *workers]))
        finally:
            holding.set()
        sent.sort()
        self.assertEqual(len(sent), n)
        self.assertGreaterEqual(min(b-a for a, b in zip(sent, sent[1:])), interval * 0.9)

    def test_coordination_across_processes_and_distinct_logs(self):
        ctx = multiprocessing.get_context("spawn")
        entered, release, finished = ctx.Event(), ctx.Event(), ctx.Event()
        coord = str(Path(self.tmp.name) / "shared-coord")
        log_a = str(Path(self.tmp.name) / "a.jsonl")
        log_b = str(Path(self.tmp.name) / "other-log-directory" / "b.jsonl")
        proc = ctx.Process(target=_locked_child, args=(self.url, log_a, coord, TOKEN, entered, release, finished))
        thread = None
        try:
            proc.start()
            self.assertTrue(entered.wait(5))
            os.environ["BB_TEST_TOKEN"] = TOKEN
            other = bb.Client(base_url=self.url, log_path=log_b, token_var="BB_TEST_TOKEN", coord_dir=coord,
                              min_interval=0, sleep=lambda _: None)
            done = threading.Event()
            def second():
                with other.sequence("child-b") as s:
                    s.msg("PING;2", "child B")
                done.set()
            thread = threading.Thread(target=second)
            thread.start()
            time.sleep(.2)
            self.assertFalse(done.is_set())
            release.set()
            self.assertTrue(finished.wait(5))
            thread.join(5)
            proc.join(5)
            self.assertEqual(proc.exitcode, 0)
            self.assertTrue(done.is_set())
        finally:
            release.set()
            if thread is not None: thread.join(5)
            if proc.is_alive(): proc.terminate()
            proc.join(5)
        self.assertEqual([path for path, _, _ in Fake.calls], ["/__reset", "/msg", "/__reset", "/msg"])

    def test_process_death_releases_lock_and_other_token_is_independent(self):
        ctx = multiprocessing.get_context("spawn")
        entered, release, finished = ctx.Event(), ctx.Event(), ctx.Event()
        coord = str(Path(self.tmp.name) / "shared-coord")
        proc = ctx.Process(target=_locked_child, args=(self.url, str(self.log), coord, TOKEN, entered, release, finished))
        try:
            proc.start()
            self.assertTrue(entered.wait(5))
            # Otro token puede adquirir su lock mientras el primero sigue vivo.
            os.environ["BB_OTHER_TOKEN"] = "otro-token"
            c = self.client(token_var="BB_OTHER_TOKEN", coord_dir=coord,
                            log_path=Path(self.tmp.name) / "other-token.jsonl")
            with c.sequence("independent") as s:
                s.flush()
            self.assertTrue(proc.is_alive())
            proc.terminate()
            proc.join(5)
            self.assertIsNotNone(proc.exitcode)
            # La muerte libera el lock del mismo token; un proceso nuevo lo adquiere.
            recovered = self.client(coord_dir=coord, log_path=Path(self.tmp.name) / "recovered.jsonl")
            with recovered.sequence("recovered") as s:
                s.flush()
        finally:
            # No notificar el Event después de matar a su waiter: su Condition
            # puede quedar esperando una confirmación que nunca llegará.
            if proc.is_alive(): proc.terminate()
            proc.join(5)

    def test_epoch_confirm_budget_sharing_non_json_and_conclude(self):
        with self.c.sequence("a") as s:
            s.msg("PING;64", "h")
            raw = s.call("GET", "/nada", None, "ruta inexistente")
        self.assertEqual((raw.status, raw.response, raw.raw), (404, "Not Found", "Not Found"))
        self.c.conclude(2, "aprendido")
        self.assertEqual(self.c.entries()[1]["conclusion"], "aprendido")
        Fake.calls.clear()
        with self.c.sequence("b") as s:
            self.assertTrue(s.msg("PING;64", "h").cached)
        with self.c.sequence("c") as s:
            self.assertFalse(s.msg("PING;64", "h", confirm=True).cached)
        old_epoch = self.client(epoch="v2")
        with old_epoch.sequence("d") as s:
            self.assertFalse(s.msg("PING;64", "h").cached)

    def test_budget_is_shared_across_instances_and_logs(self):
        first = self.client(daily_cap=2)
        with first.sequence("first") as s:
            s.flush()
        second = self.client(daily_cap=2, log_path=Path(self.tmp.name) / "other.jsonl")
        with second.sequence("second") as s:
            s.flush()
            with self.assertRaises(bb.BudgetExceeded):
                s.msg("PING;1", "quota compartida")

    def test_cli_runner_uses_local_fake_and_retires_loose_commands(self):
        fixture = Path(self.tmp.name) / "steps.jsonl"
        fixture.write_text(json.dumps({"request": {"m": "PING;7"}, "hipotesis": "runner"}) + "\n")
        env = dict(os.environ, BB_TOKEN=TOKEN, BB_BASE_URL=self.url,
                   BB_LOG=str(Path(self.tmp.name) / "cli.jsonl"),
                   BB_COORD_DIR=str(Path(self.tmp.name) / "cli-coord"), BB_MIN_INTERVAL="0")
        import subprocess
        run = subprocess.run([sys.executable, str(Path(bb.__file__)), "run", "cli-seq", str(fixture)],
                             env=env, capture_output=True, text=True, timeout=10)
        self.assertEqual(run.returncode, 0, run.stderr)
        cli_entries = [json.loads(line) for line in (Path(env["BB_LOG"])).read_text().splitlines()]
        self.assertEqual([e["path"] for e in cli_entries], ["/__reset", "/msg"])
        legacy = subprocess.run([sys.executable, str(Path(bb.__file__)), "msg", "old", "PING;1", "--hip", "h"],
                                env=env, capture_output=True, text=True, timeout=10)
        self.assertNotEqual(legacy.returncode, 0)


if __name__ == "__main__":
    unittest.main()
