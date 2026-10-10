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
import hashlib
import json
import os
import sys
import time
import urllib.error
import uuid
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
    status = property(lambda self: self.entry.get("status"))
    response = property(lambda self: self.entry.get("response"))
    raw = property(lambda self: self.entry.get("raw"))
    x_req = property(lambda self: self.entry.get("x_req"))

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

    @contextmanager
    def _quota_locked(self):
        """Bloquea el recurso compartido de cuota, no un log concreto."""
        self.side_dir.mkdir(parents=True, exist_ok=True)
        with open(self.side_dir / "quota.lock", "w") as fh:
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
        with self._locked():
            self.side_dir.mkdir(parents=True, exist_ok=True)
            with open(self.side_dir / name, "a") as fh:
                fh.write(json.dumps(obj, ensure_ascii=False) + "\n")

    @property
    def _token_tag(self) -> str:
        """Etiqueta no reversible para separar las cuotas de tokens compartidos."""
        return hashlib.sha256(self._token.encode()).hexdigest()[:16]

    @property
    def _quota_path(self) -> Path:
        return self.side_dir / "quota.json"

    def _read_quota(self) -> dict:
        if not self._quota_path.exists():
            return {"tokens": {}}
        return json.loads(self._quota_path.read_text())

    def _write_quota(self, quota: dict) -> None:
        self.side_dir.mkdir(parents=True, exist_ok=True)
        tmp = self._quota_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(quota))
        tmp.replace(self._quota_path)

    def _quota_state(self, quota: dict, today: str) -> dict:
        tokens = quota.setdefault("tokens", {})
        state = tokens.get(self._token_tag)
        if state is None or state.get("day") != today:
            # Migra el contador previo del log la primera vez que se usa esta versión.
            entries = self.entries()
            prior = sum(1 for e in entries if e.get("ts") and bogota_day(e["ts"]) == today)
            # Las versiones anteriores guardaban los rate limits solo en el archivo lateral.
            if not any(e.get("infrastructure") == "rate-limit" for e in entries):
                prior += sum(1 for e in self._side("rate_limited.jsonl")
                             if e.get("ts") and bogota_day(e["ts"]) == today)
            state = {"day": today, "used": prior, "next_at": 0.0}
            tokens[self._token_tag] = state
        return state

    def used_today(self) -> int:
        today = bogota_day(now_iso())
        with self._quota_locked():
            return self._quota_state(self._read_quota(), today)["used"]

    def _reserve_request(self) -> None:
        """Reserva atómicamente una unidad de la cuota diaria (el turno se toma al enviar)."""
        today = bogota_day(now_iso())
        with self._quota_locked():
            quota = self._read_quota()
            state = self._quota_state(quota, today)
            if state["used"] >= self.daily_cap:
                raise BudgetExceeded(f"tope diario alcanzado ({self.daily_cap})")
            state["used"] += 1
            self._write_quota(quota)

    def _claim_turn(self) -> None:
        """Toma el turno de envío revalidándolo con la hora real, justo antes de conectar.

        Un turno no se agenda por adelantado: si el proceso se retrasa (bloqueo), vuelve a
        esperar al intervalo mínimo desde el último turno reclamado, y así los retrasos no se
        acumulan en una ráfaga. `next_at` se fija al reclamar el turno, antes de persistir la
        cuota y abrir la conexión; no mide el envío real al socket, así que una pausa del
        proceso entre reclamar y conectar puede acercar dos envíos (límite residual aceptado).
        """
        while True:
            with self._quota_locked():
                quota = self._read_quota()
                state = self._quota_state(quota, bogota_day(now_iso()))
                now = time.time()
                wait = state["next_at"] - now
                if wait <= 0:
                    state["next_at"] = now + self.min_interval
                    self._write_quota(quota)
                    return
            self._sleep(wait)

    def _replace_entries(self, entries: list[dict]) -> None:
        tmp = self.log_path.with_suffix(".tmp")
        tmp.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries))
        tmp.replace(self.log_path)

    def conclude(self, entry_id: int, text: str) -> None:
        with self._locked():
            es = self.entries()
            for e in es:
                if e["id"] == entry_id:
                    e["conclusion"] = text
                    break
            else:
                raise KeyError(entry_id)
            self._replace_entries(es)

    # ---------- secuencias ----------
    def seq_steps(self, seq: str) -> list[dict]:
        return [e for e in self.entries() if e["seq"] == seq]

    def pending_steps(self, seq: str) -> list[dict]:
        return [e for e in self._side("pending.jsonl") if e["seq"] == seq]

    def _append_pending(self, seq: str, args: tuple, kw: dict, pending_id: str) -> None:
        self._append_side("pending.jsonl", {"seq": seq, "args": args, "kw": kw,
                                             "pending_id": pending_id})

    def _remove_pending(self, seq: str, pending_id: str) -> None:
        with self._locked():
            pending = self._side("pending.jsonl")
            for index, item in enumerate(pending):
                if item["seq"] == seq and item.get("pending_id") == pending_id:
                    pending.pop(index)
                    break
            else:
                return
            self._write_pending(pending)

    def _write_pending(self, pending: list[dict]) -> None:
        path = self.side_dir / "pending.jsonl"
        tmp = path.with_suffix(".tmp")
        tmp.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in pending))
        tmp.replace(path)

    def _ensure_pending_ids(self, seq: str) -> None:
        """Da identidad persistente a pendientes antiguos antes de reenviarlos.

        Sin ella, la respuesta registrada no podría reconciliarse con su pendiente tras un corte.
        """
        with self._locked():
            pending = self._side("pending.jsonl")
            legacy = [e for e in pending if e["seq"] == seq and not e.get("pending_id")]
            for item in legacy:
                item["pending_id"] = str(uuid.uuid4())
            if legacy:
                self._write_pending(pending)

    def sequence(self, seq: str, hipotesis: str = "inicio de secuencia: estado limpio") -> "Sequence":
        """Abre una secuencia. El reset se envía de forma perezosa (ver Sequence)."""
        if self.seq_steps(seq) or self.pending_steps(seq):
            raise ValueError(f"la secuencia {seq!r} ya existe; usa otro nombre o Client.resume()")
        return Sequence(self, seq, reset_hipotesis=hipotesis)

    def resume(self, seq: str) -> "Sequence":
        self._ensure_pending_ids(seq)
        steps = self.seq_steps(seq)
        completed_pending = {e.get("pending_id") for e in steps
                             if e.get("outcome") == "completed" and e.get("pending_id")}
        pending_records = self.pending_steps(seq)
        # Un corte tras registrar la respuesta deja el pendiente. La respuesta ya representa
        # la operación lógica: se consume el pendiente al recuperar para no repetirla.
        for item in pending_records:
            if item.get("pending_id") in completed_pending:
                self._remove_pending(seq, item["pending_id"])
        pending = [(tuple(e["args"]), e["kw"], e.get("pending_id"))
                   for e in pending_records if e.get("pending_id") not in completed_pending]
        if not steps and not pending:
            raise ValueError(f"la secuencia {seq!r} no existe")
        if any(e.get("outcome") in ("transport_error", "pending") for e in steps):
            raise ValueError(f"la secuencia {seq!r} tiene un transporte incierto; empieza otra desde reset")
        logical_steps = [self._step_key(e) for e in steps
                         if "status" in e and not e.get("infrastructure")]
        logical_steps.extend(self.step_key(args[0], args[1], args[2], kw) for args, kw, _ in pending)
        return Sequence(self, seq, steps=logical_steps, pending=pending)

    # ---------- caché ----------
    @staticmethod
    def _step_key(e: dict) -> list:
        body = e.get("request")
        raw_body = e.get("raw_body")
        has_data = raw_body is not None or body is not None or e.get("method") == "POST"
        content_type = e.get("content_type") or ("application/json" if has_data else None)
        return [e["method"], e["path"], e.get("auth", "valid"), body, raw_body, content_type]

    @classmethod
    def step_key(cls, method: str, path: str, body, kw: dict) -> list:
        return cls._step_key({"method": method, "path": path, "request": body,
                              "auth": kw.get("auth", "valid"), "raw_body": kw.get("raw_body"),
                              "content_type": kw.get("content_type")})

    def cache_lookup(self, prefix: list, step: list) -> dict | None:
        """Busca una secuencia previa (misma epoch) con el mismo prefijo desde reset."""
        by_seq: dict[str, list[dict]] = {}
        for e in self.entries():
            if e.get("epoch") == self.epoch and "status" in e and not e.get("infrastructure"):
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

    def execute(self, seq: str, method: str, path: str, body, hipotesis: str, *,
                auth: str = "valid", raw_body: str | None = None, content_type: str | None = None,
                conclusion: str | None = None, retries: int = 3,
                pending_id: str | None = None) -> Result:
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
            self._reserve_request()
            ts = now_iso()
            # Escribir antes de abrir la conexión conserva evidencia incluso si se pierde la respuesta.
            with self._locked():
                es = self.entries()
                entry = {
                    "id": (max((e["id"] for e in es), default=0) + 1),
                    "seq": seq, "x_req": None, "hipotesis": hipotesis, "request": body,
                    "conclusion": conclusion, "method": method, "path": path, "auth": auth,
                    "raw_body": raw_body, "content_type": content_type, "epoch": self.epoch, "ts": ts,
                    "pending_id": pending_id, "outcome": "pending",
                }
                with open(self.log_path, "a") as fh:
                    fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
            # Último paso antes de conectar: nada que pueda bloquear entre el turno y el envío.
            self._claim_turn()
            try:
                status, hdrs, raw = self._send(method, path, data, auth, content_type)
            except Exception as err:
                with self._locked():
                    es = self.entries()
                    target = next(e for e in es if e["id"] == entry["id"])
                    target.update({"outcome": "transport_error", "transport_error": type(err).__name__})
                    self._replace_entries(es)
                raise

            text = raw.decode("utf-8", errors="replace")
            try:
                parsed = json.loads(text)
            except ValueError:
                parsed = text
            with self._locked():
                es = self.entries()
                target = next(e for e in es if e["id"] == entry["id"])
                if hdrs.get(RATE_LIMIT_HEADER.lower()) == "rate-limit":
                    target.update({"infrastructure": "rate-limit", "outcome": "infrastructure"})
                else:
                    target.update({"x_req": hdrs.get("x-req"), "status": status, "response": parsed,
                                   "raw": text, "outcome": "completed"})
                self._replace_entries(es)
                entry = target
            if hdrs.get(RATE_LIMIT_HEADER.lower()) == "rate-limit":
                # Infraestructura: queda auditada pero nunca alimenta la caché ni la evidencia.
                self._append_side("rate_limited.jsonl", {"ts": ts, "seq": seq, "path": path, "status": status})
                self._sleep(min(2 ** attempt, 10))
                continue
            return Result(entry, cached=False)
        raise RateLimited("rate limit persistente; tanda detenida")


class Sequence:
    """Secuencia desde un reset.

    Caché: si el mismo prefijo + paso ya se observó (misma epoch), se devuelve sin llamar.
    Los pasos cacheados quedan pendientes; ante el primer fallo de caché se envían de verdad
    (reset incluido) para que el estado del original coincida con el prefijo lógico.
    """

    def __init__(self, client: Client, seq: str, steps: list | None = None,
                 pending: list[tuple[tuple, dict, str | None]] | None = None, reset_hipotesis: str | None = None):
        self.client, self.seq = client, seq
        self.steps: list = list(steps or [])
        self.pending: list[tuple[tuple, dict, str | None]] = list(pending or [])
        if reset_hipotesis is not None:
            self._queue(("POST", "/__reset", None, reset_hipotesis), {}, persist=True)

    def _queue(self, args: tuple, kw: dict, *, persist: bool = False) -> None:
        method, path, body, _ = args
        self.steps.append(self.client.step_key(method, path, body, kw))
        pending_id = str(uuid.uuid4())
        self.pending.append((args, kw, pending_id))
        if persist:
            self.client._append_pending(self.seq, args, kw, pending_id)

    def flush(self) -> None:
        if self.pending and self.pending[0][0][1] == "/__reset" and any(
                not e.get("infrastructure") for e in self.client.seq_steps(self.seq)):
            raise ValueError(f"la secuencia {self.seq!r} ya existe en el log")
        while self.pending:
            args, kw, pending_id = self.pending[0]
            method, path, body, hip = args
            replay_hip = f"[replay de prefijo] {hip}" if path != "/__reset" else hip
            self.client.execute(self.seq, method, path, body, replay_hip, **kw, pending_id=pending_id)
            self.pending.pop(0)
            self.client._remove_pending(self.seq, pending_id)

    def call(self, method: str, path: str, body, hipotesis: str, *, confirm: bool = False,
             **kw) -> Result:
        step = self.client.step_key(method, path, body, kw)
        if not confirm and path != "/__reset":
            hit = self.client.cache_lookup(self.steps, step)
            if hit is not None:
                self._queue((method, path, body, hipotesis), kw, persist=True)
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
