#!/usr/bin/env python3
"""Cliente instrumentado: la única vía permitida hacia el servicio original.

Cada request (incluido POST /__reset) se registra en experimentos.jsonl con su hipótesis.
El token se lee del entorno o de .env y nunca se escribe en disco ni en salida.

Uso como librería:

    from bb import Client
    c = Client()
    with c.sequence("s-precedencia", "reset para medir precedencia") as s:
        r = s.msg("SALDOS;AC-0001;0", "E301 se evalúa antes que el control")

Uso por CLI: ver `python3 tools/explorer/bb.py -h`.
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import fcntl
import hashlib
import json
import os
import sys
import time
import threading
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
        coord_dir: Path | str | None = None,
    ):
        env = {**load_env(ROOT / ".env"), **os.environ}
        self.base_url = (base_url or env.get("BB_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.log_path = Path(log_path or env.get("BB_LOG") or ROOT / "experimentos.jsonl")
        self.side_dir = self.log_path.parent / ".explore"
        self.coord_dir = Path(coord_dir or env.get("BB_COORD_DIR") or ROOT / ".explore")
        self._active_sequence = None
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
        self.coord_dir.mkdir(parents=True, exist_ok=True)
        with open(self.coord_dir / "quota.lock", "w") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

    def entries(self) -> list[dict]:
        with self._locked():
            return self._read_entries()

    def _read_entries(self) -> list[dict]:
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
        return self.coord_dir / "quota.json"

    def _read_quota(self) -> dict:
        if not self._quota_path.exists():
            return {"tokens": {}}
        return json.loads(self._quota_path.read_text())

    def _write_quota(self, quota: dict) -> None:
        self.coord_dir.mkdir(parents=True, exist_ok=True)
        tmp = self._quota_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(quota))
        tmp.replace(self._quota_path)

    def _quota_state(self, quota: dict, today: str) -> dict:
        tokens = quota.setdefault("tokens", {})
        state = tokens.get(self._token_tag)
        if state is None or state.get("day") != today:
            # Solo reconstruir consumo atribuible a este token y día. Los registros
            # históricos sin etiqueta no permiten deducir quién consumió la cuota.
            entries = [e for e in self.entries()
                       if e.get("token_tag") == self._token_tag
                       and e.get("ts") and bogota_day(e["ts"]) == today]
            prior = len(entries)
            # Evitar duplicar rate limits que ya se auditaron en el log principal.
            if not any(e.get("infrastructure") == "rate-limit" for e in entries):
                with self._locked():
                    side_entries = self._side("rate_limited.jsonl")
                prior += sum(1 for e in side_entries
                             if e.get("token_tag") == self._token_tag
                             and e.get("ts") and bogota_day(e["ts"]) == today)
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
            es = self._read_entries()
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
        with self._locked():
            return [e for e in self._side("pending.jsonl") if e["seq"] == seq]

    def _append_pending(self, seq: str, args: tuple, kw: dict, pending_id: str) -> None:
        with self._locked():
            if args[1] == "/__reset" and (any(e["seq"] == seq for e in self._read_entries())
                                           or any(e["seq"] == seq for e in self._side("pending.jsonl"))):
                raise ValueError(f"la secuencia {seq!r} ya existe; usa otro nombre")
            self.side_dir.mkdir(parents=True, exist_ok=True)
            with open(self.side_dir / "pending.jsonl", "a") as fh:
                fh.write(json.dumps({"seq": seq, "args": args, "kw": kw,
                                     "pending_id": pending_id}, ensure_ascii=False) + "\n")

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

    def sequence(self, seq: str, hipotesis: str = "inicio de secuencia: estado limpio",
                 *, no_cache: bool = False) -> "Sequence":
        """Crear un contexto exclusivo; usar siempre con `with`."""
        if not seq or not hipotesis.strip():
            raise ValueError("la secuencia y la hipótesis del reset son obligatorias")
        return Sequence(self, seq, reset_hipotesis=hipotesis, no_cache=no_cache)

    def resume(self, seq: str) -> "Sequence":
        raise ValueError("no se puede retomar una secuencia sin su lock; empieza otra desde reset con run")

    # ---------- caché ----------
    @staticmethod
    def _step_key(e: dict) -> list:
        body = e.get("request")
        raw_body = e.get("raw_body")
        raw_body_b64 = e.get("raw_body_b64")
        has_data = raw_body is not None or raw_body_b64 is not None or body is not None or e.get("method") == "POST"
        content_type = e.get("content_type") or ("application/json" if has_data else None)
        return [e["method"], e["path"], e.get("auth", "valid"), body, raw_body, raw_body_b64, content_type]

    @classmethod
    def step_key(cls, method: str, path: str, body, kw: dict) -> list:
        return cls._step_key({"method": method, "path": path, "request": body,
                              "auth": kw.get("auth", "valid"), "raw_body": kw.get("raw_body"),
                              "content_type": kw.get("content_type"), "raw_body_b64": kw.get("raw_body_b64")})

    def cache_lookup(self, prefix: list, step: list) -> dict | None:
        """Busca una secuencia previa (misma epoch) con el mismo prefijo desde reset."""
        by_seq: dict[str, list[dict]] = {}
        for e in self.entries():
            if e.get("epoch") == self.epoch and e.get("token_tag") == self._token_tag \
                    and "response_b64" in e and "status" in e and not e.get("infrastructure"):
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

    def execute(self, seq: str, method: str, path: str, body, hipotesis: str, **kw) -> Result:
        """Solo el propietario activo de la secuencia puede enviar."""
        active = self._active_sequence
        if active is None or active.seq != seq:
            raise RuntimeError("envío fuera del contexto exclusivo de secuencia")
        active._require_owner()
        if not active._reset_complete and path != "/__reset":
            raise RuntimeError("envía el reset inicial con sequence.flush() antes de ejecutar")
        try:
            result = self._execute(seq, method, path, body, hipotesis, **kw)
            if not active._reset_complete and path == "/__reset":
                if result.status != 200:
                    raise RuntimeError("reset no exitoso; secuencia abortada")
                active._reset_complete = True
            return result
        except BaseException:
            active._failed = True
            raise

    def _execute(self, seq: str, method: str, path: str, body, hipotesis: str, *,
                auth: str = "valid", raw_body: str | None = None, raw_body_b64: str | None = None,
                content_type: str | None = None,
                conclusion: str | None = None, retries: int = 3,
                pending_id: str | None = None) -> Result:
        """Envía de verdad y registra. Usar a través de Sequence, que maneja caché y reset."""
        if not hipotesis or not hipotesis.strip():
            raise ValueError("cada request necesita una hipótesis")
        if auth not in AUTH_VARIANTS:
            raise ValueError(f"auth debe ser uno de {AUTH_VARIANTS}")
        if sum(x is not None for x in (body, raw_body, raw_body_b64)) > 1:
            raise ValueError("usar solo un cuerpo: request, raw_body o raw_body_b64")
        if raw_body_b64 is not None:
            data = base64.b64decode(raw_body_b64, validate=True)
        elif raw_body is not None:
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
                es = self._read_entries()
                entry = {
                    "id": (max((e["id"] for e in es), default=0) + 1),
                    "seq": seq, "token_tag": self._token_tag, "x_req": None, "hipotesis": hipotesis, "request": body,
                    "conclusion": conclusion, "method": method, "path": path, "auth": auth,
                    "raw_body": raw_body, "raw_body_b64": raw_body_b64,
                    "request_b64": None if data is None else base64.b64encode(data).decode("ascii"),
                    "content_type": content_type, "epoch": self.epoch, "ts": ts,
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
                    es = self._read_entries()
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
                es = self._read_entries()
                target = next(e for e in es if e["id"] == entry["id"])
                target["response_b64"] = base64.b64encode(raw).decode("ascii")
                if hdrs.get(RATE_LIMIT_HEADER.lower()) == "rate-limit":
                    target.update({"infrastructure": "rate-limit", "outcome": "infrastructure"})
                else:
                    target.update({"x_req": hdrs.get("x-req"), "status": status, "response": parsed,
                                   "raw": text, "outcome": "completed"})
                self._replace_entries(es)
                entry = target
            if hdrs.get(RATE_LIMIT_HEADER.lower()) == "rate-limit":
                # Infraestructura: queda auditada pero nunca alimenta la caché ni la evidencia.
                self._append_side("rate_limited.jsonl", {"ts": ts, "seq": seq, "path": path,
                                                        "status": status, "token_tag": self._token_tag})
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

    def __init__(self, client: Client, seq: str, *, reset_hipotesis: str, no_cache: bool = False):
        self.client, self.seq = client, seq
        self.steps: list = []
        self.pending: list[tuple[tuple, dict, str | None]] = []
        self.reset_hipotesis = reset_hipotesis
        self.no_cache = no_cache
        self._lock = None
        self._closed = False
        self._failed = False
        self._owner = None
        self._reset_complete = False

    def __enter__(self):
        if self._closed or self._lock is not None or self.client._active_sequence is not None:
            raise RuntimeError("contexto cerrado o secuencia anidada")
        self.client.coord_dir.mkdir(parents=True, exist_ok=True)
        self._lock = open(self.client.coord_dir / f"sequence-{self.client._token_tag}.lock", "a+")
        try:
            fcntl.flock(self._lock, fcntl.LOCK_EX)
            if self.client.seq_steps(self.seq) or self.client.pending_steps(self.seq):
                raise ValueError(f"la secuencia {self.seq!r} ya existe; empieza otra desde reset")
            self._lock.seek(0)
            self._lock.truncate()
            self._lock.write(json.dumps({"pid": os.getpid(), "seq": self.seq, "inicio": now_iso()}))
            self._lock.flush()
            self._owner = (os.getpid(), threading.get_ident())
            self.client._active_sequence = self
            self._queue(("POST", "/__reset", None, self.reset_hipotesis), {}, persist=True)
            return self
        except BaseException:
            self.close()
            raise

    def close(self):
        if self._lock is not None:
            try:
                if self.client._active_sequence is self:
                    self.client._active_sequence = None
            finally:
                fcntl.flock(self._lock, fcntl.LOCK_UN)
                self._lock.close()
                self._lock = None
        self._closed = True

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None and not self._failed and self._lock is not None:
                self.flush()
        finally:
            self.close()

    def _require_owner(self):
        if self.client._active_sequence is not self or self._lock is None \
                or self._owner != (os.getpid(), threading.get_ident()) or self._failed:
            raise RuntimeError("usa la secuencia dentro de with Client.sequence(...)")

    def _queue(self, args: tuple, kw: dict, *, persist: bool = False) -> None:
        method, path, body, _ = args
        self.steps.append(self.client.step_key(method, path, body, kw))
        pending_id = str(uuid.uuid4())
        self.pending.append((args, kw, pending_id))
        if persist:
            self.client._append_pending(self.seq, args, kw, pending_id)

    def flush(self) -> None:
        self._require_owner()
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
        self._require_owner()
        if not hipotesis or not hipotesis.strip():
            raise ValueError("cada request necesita una hipótesis")
        step = self.client.step_key(method, path, body, kw)
        if not self.no_cache and not confirm and path != "/__reset":
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


def load_steps(path: Path) -> list[dict]:
    """Validar la tanda completa antes de adquirir token o contactar al servidor."""
    steps = []
    allowed = {"method", "path", "request", "hipotesis", "auth", "raw_body", "raw_body_b64",
               "content_type", "confirm", "conclusion"}
    for n, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        item = json.loads(line)
        if not isinstance(item, dict) or set(item) - allowed:
            raise ValueError(f"línea {n}: campos desconocidos o paso no objeto")
        item = {"method": "POST", "path": "/msg", "auth": "valid", **item}
        if not isinstance(item.get("hipotesis"), str) or not item["hipotesis"].strip():
            raise ValueError(f"línea {n}: falta hipótesis")
        if not isinstance(item["method"], str) or not item["method"].isalpha() or item["method"] != item["method"].upper():
            raise ValueError(f"línea {n}: método inválido")
        if not isinstance(item["path"], str) or not item["path"].startswith("/"):
            raise ValueError(f"línea {n}: ruta inválida")
        if item["auth"] not in AUTH_VARIANTS:
            raise ValueError(f"línea {n}: auth inválido")
        if sum(item.get(k) is not None for k in ("request", "raw_body", "raw_body_b64")) > 1:
            raise ValueError(f"línea {n}: cuerpos excluyentes")
        for key in ("raw_body", "raw_body_b64", "content_type", "conclusion"):
            if item.get(key) is not None and not isinstance(item[key], str):
                raise ValueError(f"línea {n}: {key} debe ser texto")
        if "confirm" in item and not isinstance(item["confirm"], bool):
            raise ValueError(f"línea {n}: confirm debe ser booleano")
        if item.get("raw_body_b64") is not None:
            base64.b64decode(item["raw_body_b64"], validate=True)
        steps.append(item)
    if not steps:
        raise ValueError("la secuencia debe contener al menos un paso")
    return steps


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Cliente instrumentado del servicio original")
    sub = p.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="ejecuta una secuencia JSONL con reset y lock por token")
    run.add_argument("seq", help="nombre nuevo de secuencia")
    run.add_argument("file", type=Path, help="JSONL con hipótesis por paso")
    run.add_argument("--hip", default="inicio de secuencia: estado limpio", help="hipótesis del reset")
    run.add_argument("--no-cache", action="store_true", help="envía todos los pasos al servidor")
    for cmd in ("reset", "msg", "http"):
        legacy = sub.add_parser(cmd, help="retirado: usa run para mantener exclusión durante toda la secuencia")
        legacy.add_argument("legacy_args", nargs=argparse.REMAINDER)
    c = sub.add_parser("conclude", help="añade la conclusión a una línea del log")
    c.add_argument("id", type=int)
    c.add_argument("text")
    sub.add_parser("budget", help="requests usados hoy (día de Bogotá)")
    a = p.parse_args(argv)
    if a.cmd in ("reset", "msg", "http"):
        p.error("los comandos sueltos no conservan el lock; usa run SEQ ARCHIVO.jsonl")
    steps = load_steps(a.file) if a.cmd == "run" else None
    cl = Client()
    if a.cmd == "budget":
        print(f"usados hoy: {cl.used_today()} / tope {cl.daily_cap} (límite duro 8000)")
    elif a.cmd == "run":
        with cl.sequence(a.seq, a.hip, no_cache=a.no_cache) as sequence:
            sequence.flush()
            print(Result(cl.seq_steps(a.seq)[-1], cached=False))
            for step in steps:
                step = dict(step)
                method, path = step.pop("method"), step.pop("path")
                body, hip = step.pop("request", None), step.pop("hipotesis")
                print(sequence.call(method, path, body, hip, **step))
            # Materializa los aciertos pendientes para terminar con evidencia propia.
            sequence.flush()
    elif a.cmd == "conclude":
        cl.conclude(a.id, a.text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
