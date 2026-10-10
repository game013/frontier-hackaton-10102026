#!/usr/bin/env python3
"""A6: replay the v1 baseline against the current service and diff every step.

Sources are v1 sequences with captured bytes: the A2 replay capture (IDs 227–450) and the
A3/A4/A5 sequences of experimentos.jsonl. Each one is resent from reset through bb.Client
with no cache; status, JSON contract and raw bytes are compared step by step.
"""
from __future__ import annotations

import argparse
import base64
import fnmatch
import json
from pathlib import Path

try:
    from .bb import Client
    from .corpus import _byte_match, _captured, _contract_match, read_jsonl
except ImportError:  # direct script execution from tools/explorer
    from bb import Client
    from corpus import _byte_match, _captured, _contract_match, read_jsonl

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOG = ROOT / "experimentos.jsonl"
DEFAULT_A2 = ROOT / "tests/corpus/v1-replays/a2-baseline-20261010-retry/corpus.jsonl"
DEFAULT_CAPTURE = ROOT / "tests/corpus/a6"
# a3-v1-20-*: aislamiento con TEAM_TOKEN (618 rechazado); no es reproducible con BB_TOKEN.
DEFAULT_PATTERNS = ("a3-v1-[0-9]*", "a4-v1-*", "a5-c0[1-3]-*")
EXCLUDED = ("a3-v1-20-*", "*-r")
PREFIX_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
MAX_REQUESTS = 1000


def _check_rows(name: str, rows: list[dict]) -> None:
    if not rows or rows[0].get("path") != "/__reset":
        raise ValueError(f"{name}: la secuencia debe empezar con reset")
    for row in rows:
        if row.get("outcome") != "completed" or row.get("infrastructure"):
            raise ValueError(f"{name}: ID {row.get('id')} no es evidencia completa")
        if row.get("response_b64") is None or "request_b64" not in row:
            raise ValueError(f"{name}: ID {row.get('id')} no tiene bytes capturados")


def load_sources(log_path: Path = DEFAULT_LOG, a2_capture: Path | None = DEFAULT_A2,
                 patterns: tuple[str, ...] = DEFAULT_PATTERNS,
                 only: tuple[str, ...] = ()) -> list[tuple[str, list[dict]]]:
    """Return (source_seq, rows) with the reset first; `id` of each row is its base evidence.

    The base is v1 except the A5 characterization (a5-c0*), recorded after 15:43 as a witness.
    """
    sources: list[tuple[str, list[dict]]] = []
    if a2_capture is not None:
        grouped: dict[str, list[dict]] = {}
        for row in read_jsonl(a2_capture):
            grouped.setdefault(row["seq"], []).append(row)
        sources.extend(grouped.items())
    grouped = {}
    for row in read_jsonl(log_path):
        seq = row.get("seq", "")
        if any(fnmatch.fnmatchcase(seq, p) for p in patterns) and \
                not any(fnmatch.fnmatchcase(seq, p) for p in EXCLUDED):
            grouped.setdefault(seq, []).append(row)
    sources.extend((seq, sorted(rows, key=lambda r: r["id"])) for seq, rows in grouped.items())
    if only:
        sources = [(s, r) for s, r in sources if any(fnmatch.fnmatchcase(s, p) for p in only)]
    if not sources:
        raise ValueError("no hay secuencias fuente")
    names = [s for s, _ in sources]
    if len(set(names)) != len(names):
        raise ValueError("secuencias fuente duplicadas")
    for name, rows in sources:
        _check_rows(name, rows)
    return sources


def _call_kwargs(row: dict) -> dict:
    """Resend the exact captured bytes; request_b64 null means no body at all."""
    kwargs = {"auth": row.get("auth", "valid"), "content_type": row.get("content_type")}
    if row["request_b64"] is not None:
        kwargs["raw_body_b64"] = row["request_b64"]
    return kwargs


def _delta(source_seq: str, n: int, expected: dict, actual: dict) -> dict:
    return {"source_seq": source_seq, "n": n, "base_id": expected["id"], "v2_id": actual["id"],
            "method": expected.get("method"), "path": expected.get("path"),
            "auth": expected.get("auth"), "request": expected.get("request"),
            "base_status": expected.get("status"), "v2_status": actual.get("status"),
            "base_raw": base64.b64decode(expected["response_b64"]).decode("utf-8", "replace"),
            "v2_raw": base64.b64decode(actual["response_b64"]).decode("utf-8", "replace"),
            "contract_equal": _contract_match(expected, actual)}


def replay(sources: list[tuple[str, list[dict]]], *, epoch: str, prefix: str,
           max_requests: int = MAX_REQUESTS, client: Client | None = None,
           capture_dir: Path = DEFAULT_CAPTURE, label: str = "A6",
           expectation: str = "salvo delta de FR-0153") -> tuple[dict, int]:
    """`label` y `expectation` solo cambian el texto de hipótesis y conclusiones (A7 reusa esto)."""
    if not epoch or not prefix or set(prefix) - PREFIX_CHARS or prefix in (".", "..") \
            or not 1 <= max_requests <= MAX_REQUESTS:
        raise ValueError(f"epoch y prefix son obligatorios; max-requests entre 1 y {MAX_REQUESTS}")
    count = sum(len(rows) for _, rows in sources)
    if count > max_requests:
        raise ValueError(f"el replay requiere {count} requests y supera max-requests={max_requests}")
    cl = client or Client(epoch=epoch)
    used = cl.used_today()
    cap = min(cl.daily_cap, used + max_requests)
    if used + count > cap:
        raise ValueError(f"cuota insuficiente: usados={used}, necesarios={count}, techo={cap}")
    cl.daily_cap = cap  # transient guard on this Client only
    cl.epoch = epoch
    for source_seq, _ in sources:
        name = f"{prefix}-{source_seq}"
        if cl.seq_steps(name) or cl.pending_steps(name):
            raise ValueError(f"la secuencia {name!r} ya existe; usa otro --prefix")

    out = capture_dir / prefix
    out.mkdir(parents=True, exist_ok=False)
    report = {"epoch": epoch, "prefix": prefix, "expected_requests": count, "request_count": 0,
              "sequences": {}, "contract_deltas": 0, "raw_deltas": 0, "deltas": [],
              "new_evidence_ids": [], "incomplete": False}
    captures: list[dict] = []

    def save() -> None:
        (out / "corpus.jsonl").write_text("".join(
            json.dumps(row, ensure_ascii=False) + "\n" for row in captures))
        (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")

    def compare(source_seq: str, n: int, expected: dict, entry: dict) -> tuple[dict, bool]:
        actual = _captured(entry, expected["id"])
        actual["base_id"] = actual.pop("source_id")
        captures.append(actual)
        report["request_count"] += 1
        same_bytes = bool(_byte_match(expected, actual))
        if not same_bytes:
            delta = _delta(source_seq, n, expected, actual)
            report["raw_deltas"] += 1
            report["contract_deltas"] += 0 if delta["contract_equal"] else 1
            report["deltas"].append(delta)
        return actual, same_bytes

    for source_seq, rows in sources:
        seq_name = f"{prefix}-{source_seq}"
        done: list[tuple[int, dict, bool]] = []
        try:
            reset_hip = f"{label} {epoch}: reset; replay de {source_seq} (base ID {rows[0]['id']})"
            with cl.sequence(seq_name, reset_hip, no_cache=True) as sequence:
                sequence.flush()
                observed = cl.seq_steps(seq_name)
                if not observed or observed[-1].get("path") != "/__reset":
                    raise RuntimeError(f"{seq_name}: no se registró el reset inicial")
                actual, same = compare(source_seq, 0, rows[0], observed[-1])
                done.append((actual["id"], rows[0], same))
                save()
                for n, expected in enumerate(rows[1:], 1):
                    kwargs = _call_kwargs(expected)
                    hip = (f"{label} {epoch}: igual que base ID {expected['id']} {expectation} "
                           f"({source_seq} paso {n})")
                    result = sequence.call(expected.get("method", "POST"),
                                           expected.get("path", "/msg"), None, hip, **kwargs)
                    actual, same = compare(source_seq, n, expected, result.entry)
                    done.append((actual["id"], expected, same))
                    save()
        except Exception as exc:
            report["incomplete"] = True
            report["error_type"] = type(exc).__name__
            report["incomplete_reason"] = f"{seq_name}: {exc}"
        for evidence_id, expected, same in done:
            try:
                cl.conclude(evidence_id, f"{label} replay {epoch}; base ID {expected['id']}; "
                            f"bytes={'iguales' if same else 'delta'}")
                report["new_evidence_ids"].append(evidence_id)
            except Exception as exc:
                report["incomplete"] = True
                report["error_type"] = type(exc).__name__
                report["incomplete_reason"] = "no se pudo concluir evidencia capturada"
        report["sequences"][source_seq] = {"replay_seq": seq_name, "count": len(done),
                                           "base_ids": [e["id"] for _, e, _ in done]}
        save()
        if report["incomplete"]:
            return report, 2
    if report["request_count"] != count:
        report["incomplete"] = True
        save()
        return report, 2
    return report, 1 if report["raw_deltas"] else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--epoch", required=True)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--only", action="append", default=[],
                        help="patrón fnmatch de secuencias fuente (repetible)")
    parser.add_argument("--max-requests", type=int, default=MAX_REQUESTS)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--a2-capture", type=Path, default=DEFAULT_A2)
    parser.add_argument("--capture-dir", type=Path, default=DEFAULT_CAPTURE)
    parser.add_argument("--dry-run", action="store_true", help="lista fuentes y conteo; cero requests")
    args = parser.parse_args(argv)
    sources = load_sources(args.log, args.a2_capture, only=tuple(args.only))
    if args.dry_run:
        for name, rows in sources:
            print(f"{name}\t{len(rows)}\tbase IDs {rows[0]['id']}–{rows[-1]['id']}")
        print(f"total\t{sum(len(r) for _, r in sources)} requests\t{len(sources)} secuencias")
        return 0
    report, code = replay(sources, epoch=args.epoch, prefix=args.prefix,
                          max_requests=args.max_requests, capture_dir=args.capture_dir)
    print(json.dumps({k: v for k, v in report.items() if k not in ("deltas", "new_evidence_ids",
                                                                   "sequences")},
                     ensure_ascii=False))
    for d in report["deltas"]:
        print(f"Δ {d['source_seq']}#{d['n']} base={d['base_id']} v2={d['v2_id']} "
              f"{d['base_status']}→{d['v2_status']} contrato={'=' if d['contract_equal'] else '≠'}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
