#!/usr/bin/env python3
"""Cliente instrumentado: la única vía permitida hacia el servicio original.

Cada request (incluido POST /__reset) se registra en experimentos.jsonl con su hipótesis.
El token se lee del entorno o de .env y nunca se escribe en disco ni en salida.

Uso como librería:

    from bb import Client
    c = Client()
    s = c.sequence("s-precedencia", "reset para medir precedencia")
    r = s.msg("SALDOS;AC-0001;0", "E301 se evalúa antes que el control")

Uso por CLI: ver `python3 tools/explorer/bb.py -h`.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import os
import sys
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASE_URL = "https://caja-negra-production-c64f.up.railway.app"
BOGOTA = dt.timezone(dt.timedelta(hours=-5))
RATE_LIMIT_HEADER = "X-Frontier-Infra"
AUTH_VARIANTS = ("valid", "none", "empty", "invalid", "scheme")


class BudgetExceeded(RuntimeError):
    pass


class RateLimited(RuntimeError):
    pass


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def bogota_day(ts: str) -> str:
    return dt.datetime.fromisoformat(ts).astimezone(BOGOTA).date().isoformat()


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")


class Result:
    def __init__(self, entry: dict, cached: bool):
        self.entry = entry
        self.cached = cached

    id = property(lambda self: self.entry["id"])
    status = property(lambda self: self.entry["status"])
    response = property(lambda self: self.entry["response"])
    raw = property(lambda self: self.entry["raw"])
    x_req = property(lambda self: self.entry["x_req"])

    def __repr__(self) -> str:
        tag = " (cache)" if self.cached else ""
        return f"#{self.id} {self.status} {self.raw}{tag}"


class Client:
    def __init__(
        self,
        base_url: str | None = None,
        log_path: Path | str | None = None,
        token_var: str | None = None,
        epoch: str | None = None,
        daily_cap: int | None = None,
        min_interval: float | None = None,
        opener=None,
        sleep=time.sleep,
    ):
        env = {**load_env(ROOT / ".env"), **os.environ}
        self.base_url = (base_url or env.get("BB_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.log_path = Path(log_path or env.get("BB_LOG") or ROOT / "experimentos.jsonl")
        self.side_dir = self.log_path.parent / ".explore"
        var = token_var or env.get("BB_TOKEN_VAR") or "BB_TOKEN"
        self._token = env.get(var)
        if not self._token:
            raise SystemExit(f"falta el token en la variable {var}")
        # epoch = versión observada del servicio; la caché solo reutiliza la misma epoch.
        self.epoch = epoch or env.get("BB_EPOCH") or "v1"
        self.daily_cap = int(daily_cap or env.get("BB_DAILY_CAP") or 7800)
        self.min_interval = float(min_interval if min_interval is not None else env.get("BB_MIN_INTERVAL", 0.125))
        self._opener = opener or urllib.request.urlopen
        self._sleep = sleep
        self._last_call = 0.0

    # ---------- log ----------
    @contextmanager
    def _locked(self):
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        lock = self.log_path.with_suffix(".lock")
        with open(lock, "w") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

    def entries(self) -> list[dict]:
        if not self.log_path.exists():
            return []
        return [json.loads(l) for l in self.log_path.read_text().splitlines() if l.strip()]

    def _side(self, name: str) -> list[dict]:
        p = self.side_dir / name
        if not p.exists():
            return []
        return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]

    def _append_side(self, name: str, obj: dict) -> None:
        self.side_dir.mkdir(parents=True, exist_ok=True)
        with open(self.side_dir / name, "a") as fh:
            fh.write(json.dumps(obj, ensure_ascii=False) + "\n")

    def used_today(self) -> int:
        today = bogota_day(now_iso())
        calls = [e for e in self.entries() if e.get("ts") and bogota_day(e["ts"]) == today]
        calls += [e for e in self._side("rate_limited.jsonl") if bogota_day(e["ts"]) == today]
        return len(calls)

    def conclude(self, entry_id: int, text: str) -> None:
        with self._locked():
            es = self.entries()
            for e in es:
                if e["id"] == entry_id:
                    e["conclusion"] = text
                    break
            else:
                raise KeyError(entry_id)
            tmp = self.log_path.with_suffix(".tmp")
            tmp.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in es))
            tmp.replace(self.log_path)

    # ---------- secuencias ----------
    def seq_steps(self, seq: str) -> list[dict]:
        return [e for e in self.entries() if e["seq"] == seq]

    def sequence(self, seq: str, hipotesis: str = "inicio de secuencia: estado limpio") -> "Sequence":
        """Abre una secuencia. El reset se envía de forma perezosa (ver Sequence)."""
        if self.seq_steps(seq):
            raise ValueError(f"la secuencia {seq!r} ya existe; usa otro nombre o Client.resume()")
        return Sequence(self, seq, reset_hipotesis=hipotesis)

    def resume(self, seq: str) -> "Sequence":
        steps = self.seq_steps(seq)
        if not steps:
            raise ValueError(f"la secuencia {seq!r} no existe")
        return Sequence(self, seq, steps=[self._step_key(e) for e in steps])

    # ---------- caché ----------
    @staticmethod
    def _step_key(e: dict) -> list:
        return [e["method"], e["path"], e.get("auth", "valid"), e["request"], e.get("raw_body")]

    def cache_lookup(self, prefix: list, step: list) -> dict | None:
        """Busca una secuencia previa (misma epoch) con el mismo prefijo desde reset."""
        by_seq: dict[str, list[dict]] = {}
        for e in self.entries():
            if e.get("epoch") == self.epoch:
                by_seq.setdefault(e["seq"], []).append(e)
        n = len(prefix)
        for steps in by_seq.values():
            if len(steps) > n and [self._step_key(e) for e in steps[:n]] == prefix \
                    and self._step_key(steps[n]) == step:
                return steps[n]
        return None

    # ---------- red ----------
    def _send(self, method: str, path: str, data: bytes | None, auth: str, content_type: str | None):
        headers = {}
        if data is not None:
            headers["Content-Type"] = content_type or "application/json"
        if auth == "valid":
            headers["Authorization"] = f"Bearer {self._token}"
        elif auth == "empty":
            headers["Authorization"] = "Bearer "
        elif auth == "invalid":
            headers["Authorization"] = "Bearer token-invalido-0000"
        elif auth == "scheme":
            headers["Authorization"] = f"Basic {self._token}"
        elif auth != "none":
            raise ValueError(f"auth desconocido: {auth}")
        req = urllib.request.Request(self.base_url + path, data=data, method=method, headers=headers)
        try:
            resp = self._opener(req, timeout=15)
            status, hdrs, body = resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as err:
            status, hdrs, body = err.code, dict(err.headers), err.read()
        return status, {k.lower(): v for k, v in hdrs.items()}, body

    def _throttle(self) -> None:
        wait = self.min_interval - (time.monotonic() - self._last_call)
        if wait > 0:
            self._sleep(wait)
        self._last_call = time.monotonic()

    def execute(self, seq: str, method: str, path: str, body, hipotesis: str, *,
                auth: str = "valid", raw_body: str | None = None, content_type: str | None = None,
                conclusion: str | None = None, retries: int = 3) -> Result:
        """Envía de verdad y registra. Usar a través de Sequence, que maneja caché y reset."""
        if not hipotesis or not hipotesis.strip():
            raise ValueError("cada request necesita una hipótesis")
        if auth not in AUTH_VARIANTS:
            raise ValueError(f"auth debe ser uno de {AUTH_VARIANTS}")
        if raw_body is not None:
            data = raw_body.encode()
        elif body is not None:
            data = json.dumps(body, ensure_ascii=False).encode()
        else:
            data = b"" if method == "POST" else None

        for attempt in range(retries + 1):
            if self.used_today() >= self.daily_cap:
                raise BudgetExceeded(f"tope diario alcanzado ({self.daily_cap})")
            self._throttle()
            ts = now_iso()
            status, hdrs, raw = self._send(method, path, data, auth, content_type)
            if hdrs.get(RATE_LIMIT_HEADER.lower()) == "rate-limit":
                # Respuesta de infraestructura: no es evidencia del servicio.
                self._append_side("rate_limited.jsonl", {"ts": ts, "seq": seq, "path": path, "status": status})
                self._sleep(min(2 ** attempt, 10))
                continue
            break
        else:
            raise RateLimited("rate limit persistente; tanda detenida")

        text = raw.decode("utf-8", errors="replace")
        try:
            parsed = json.loads(text)
        except ValueError:
            parsed = text
        with self._locked():
            es = self.entries()
            entry = {
                "id": (es[-1]["id"] + 1) if es else 1,
                "seq": seq,
                "x_req": hdrs.get("x-req"),
                "hipotesis": hipotesis,
                "request": body,
                "status": status,
                "response": parsed,
                "conclusion": conclusion,
                # Campos extra para reproducir y auditar.
                "method": method,
                "path": path,
                "auth": auth,
                "raw_body": raw_body,
                "content_type": content_type,
                "raw": text,
                "epoch": self.epoch,
                "ts": ts,
            }
            with open(self.log_path, "a") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return Result(entry, cached=False)


class Sequence:
    """Secuencia desde un reset.

    Caché: si el mismo prefijo + paso ya se observó (misma epoch), se devuelve sin llamar.
    Los pasos cacheados quedan pendientes; ante el primer fallo de caché se envían de verdad
    (reset incluido) para que el estado del original coincida con el prefijo lógico.
    """

    def __init__(self, client: Client, seq: str, steps: list | None = None,
                 reset_hipotesis: str | None = None):
        self.client, self.seq = client, seq
        self.steps: list = list(steps or [])
        self.pending: list[tuple[tuple, dict]] = []
        if reset_hipotesis is not None:
            self._queue(("POST", "/__reset", None, reset_hipotesis), {})

    def _queue(self, args: tuple, kw: dict) -> None:
        method, path, body, _ = args
        self.steps.append([method, path, kw.get("auth", "valid"), body, kw.get("raw_body")])
        self.pending.append((args, kw))

    def flush(self) -> None:
        if self.pending and self.pending[0][0][1] == "/__reset" and self.client.seq_steps(self.seq):
            raise ValueError(f"la secuencia {self.seq!r} ya existe en el log")
        while self.pending:
            (method, path, body, hip), kw = self.pending[0]
            if path != "/__reset":
                hip = f"[replay de prefijo] {hip}"
            self.client.execute(self.seq, method, path, body, hip, **kw)
            self.pending.pop(0)

    def call(self, method: str, path: str, body, hipotesis: str, *, confirm: bool = False,
             **kw) -> Result:
        step = [method, path, kw.get("auth", "valid"), body, kw.get("raw_body")]
        if not confirm and path != "/__reset":
            hit = self.client.cache_lookup(self.steps, step)
            if hit is not None:
                self._queue((method, path, body, hipotesis), kw)
                return Result(hit, cached=True)
        self.flush()
        res = self.client.execute(self.seq, method, path, body, hipotesis, **kw)
        self.steps.append(step)
        return res

    def msg(self, m: str, hipotesis: str, **kw) -> Result:
        return self.call("POST", "/msg", {"m": m}, hipotesis, **kw)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Cliente instrumentado del servicio original")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("reset", help="abre una secuencia nueva con POST /__reset")
    r.add_argument("seq")
    r.add_argument("--hip", default="inicio de secuencia: estado limpio")
    m = sub.add_parser("msg", help="POST /msg dentro de una secuencia existente")
    m.add_argument("seq")
    m.add_argument("m")
    m.add_argument("--hip", required=True)
    m.add_argument("--confirm", action="store_true", help="ignora la caché y repite")
    m.add_argument("--auth", default="valid", choices=AUTH_VARIANTS)
    h = sub.add_parser("http", help="request arbitrario (rutas, métodos, cuerpos raros)")
    h.add_argument("seq")
    h.add_argument("method")
    h.add_argument("path")
    h.add_argument("--json", help="cuerpo JSON")
    h.add_argument("--raw", help="cuerpo crudo (no JSON)")
    h.add_argument("--content-type")
    h.add_argument("--auth", default="valid", choices=AUTH_VARIANTS)
    h.add_argument("--hip", required=True)
    h.add_argument("--confirm", action="store_true")
    c = sub.add_parser("conclude", help="añade la conclusión a una línea del log")
    c.add_argument("id", type=int)
    c.add_argument("text")
    sub.add_parser("budget", help="requests usados hoy (día de Bogotá)")
    a = p.parse_args(argv)

    cl = Client()
    if a.cmd == "budget":
        print(f"usados hoy: {cl.used_today()} / tope {cl.daily_cap} (límite duro 8000)")
    elif a.cmd == "reset":
        cl.sequence(a.seq, a.hip).flush()
        print(cl.seq_steps(a.seq)[-1]["raw"])
    elif a.cmd == "msg":
        print(cl.resume(a.seq).msg(a.m, a.hip, confirm=a.confirm, auth=a.auth))
    elif a.cmd == "http":
        body = json.loads(a.json) if a.json else None
        print(cl.resume(a.seq).call(a.method, a.path, body, a.hip, raw_body=a.raw,
                                    content_type=a.content_type, auth=a.auth, confirm=a.confirm))
    elif a.cmd == "conclude":
        cl.conclude(a.id, a.text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
