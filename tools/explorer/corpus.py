#!/usr/bin/env python3
"""Build and replay the frozen v1 historical corpus through the instrumented client."""
from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
from typing import Any

try:
    from .bb import Client
except ImportError:  # direct script execution from tools/explorer
    from bb import Client

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOG = ROOT / "experimentos.jsonl"
DEFAULT_EXAMPLES = ROOT / "docs/old-system/pruebas/ejemplos.jsonl"
DEFAULT_OUT = ROOT / "tests/corpus/v1-historical"
DEFAULT_CAPTURE = ROOT / "tests/corpus/v1-replays"
EXPECTED_IDS = set(range(1, 51)) | set(range(52, 226))


def read_jsonl(path: Path) -> list[dict]:
    try:
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"no se pudo leer JSONL válido en {path}: {exc}") from exc


def strict_equal(a: Any, b: Any) -> bool:
    """JSON equality with object order ignored and Python bool/int kept distinct."""
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(strict_equal(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(strict_equal(x, y) for x, y in zip(a, b))
    return a == b


def _check_examples(rows: list[dict], examples_path: Path) -> None:
    examples = read_jsonl(examples_path)
    seq = [r for r in rows if r.get("seq") == "s001-corpus"]
    data = [r for r in seq if r.get("path") != "/__reset"]
    if len(examples) != 20 or len(data) != 20:
        raise ValueError("ejemplos.jsonl y s001-corpus deben contener exactamente 20 requests")
    for index, (example, audit) in enumerate(zip(examples, data), 1):
        if example.get("request") != audit.get("request"):
            raise ValueError(f"s001 no coincide con el request del ejemplo {index}")
        if example.get("status") != audit.get("status") or not strict_equal(
                example.get("response"), audit.get("response")):
            raise ValueError(f"s001 no coincide con la respuesta del ejemplo {index}")


def build(log_path: Path = DEFAULT_LOG, examples_path: Path = DEFAULT_EXAMPLES,
          out_dir: Path = DEFAULT_OUT) -> dict:
    """Snapshot IDs 1–50 and 52–225; never invent historical byte fields."""
    rows = read_jsonl(log_path)
    by_id: dict[int, dict] = {}
    for row in rows:
        rid = row.get("id")
        if isinstance(rid, int) and rid in EXPECTED_IDS:
            if rid in by_id:
                raise ValueError(f"ID duplicado en log: {rid}")
            by_id[rid] = row
    missing = sorted(EXPECTED_IDS - by_id.keys())
    if missing:
        raise ValueError(f"faltan IDs requeridos: {missing[:8]}")
    selected = [by_id[i] for i in sorted(EXPECTED_IDS)]
    if any(r.get("outcome") != "completed" or r.get("infrastructure") for r in selected):
        raise ValueError("el snapshot contiene una respuesta incompleta o de infraestructura")
    _check_examples(selected, examples_path)

    grouped: dict[str, list[dict]] = {}
    for source in selected:
        seq = source.get("seq")
        if not isinstance(seq, str) or not seq:
            raise ValueError(f"ID {source['id']}: secuencia ausente")
        row = {"n": 0, "source_id": source["id"]}
        for key in ("seq", "x_req", "hipotesis", "request", "status", "response", "method",
                    "path", "auth", "epoch", "request_b64", "response_b64", "raw_body_b64",
                    "raw_body", "content_type", "raw"):
            if key in source:
                row[key] = source[key]
        grouped.setdefault(seq, []).append(row)
    if len(grouped) != 10:
        raise ValueError(f"se esperaban 10 secuencias, encontradas {len(grouped)}")
    expected_names = {f"{name}.jsonl" for name in grouped}
    unexpected = {p.name for p in out_dir.glob("*.jsonl")} - expected_names if out_dir.exists() else set()
    if unexpected:
        raise ValueError(f"la salida contiene JSONL ajenos al snapshot: {sorted(unexpected)}")
    for name, steps in grouped.items():
        if (steps[0].get("method") != "POST" or steps[0].get("path") != "/__reset" or
                steps[0].get("auth") != "valid" or steps[0].get("status") != 200):
            raise ValueError(f"{name}: reset inicial ausente o no exitoso")
        for n, step in enumerate(steps, 1):
            step["n"] = n

    out_dir.mkdir(parents=True, exist_ok=True)
    for name, steps in grouped.items():
        (out_dir / f"{name}.jsonl").write_text("".join(
            json.dumps(s, ensure_ascii=False) + "\n" for s in steps))
    manifest = {
        "epoch": "v1", "source": str(log_path.relative_to(ROOT) if log_path.is_relative_to(ROOT) else log_path),
        "ids": sorted(EXPECTED_IDS), "request_count": len(selected),
        "sequence_count": len(grouped), "sequences": {
            name: {"count": len(steps), "source_ids": [s["source_id"] for s in steps],
                   "missing_response_bytes": [s["source_id"] for s in steps if "response_b64" not in s]}
            for name, steps in grouped.items()},
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return manifest


def validate_corpus(corpus_dir: Path) -> tuple[dict, list[tuple[str, list[dict]]]]:
    try:
        manifest = json.loads((corpus_dir / "manifest.json").read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"manifest inválido: {exc}") from exc
    if manifest.get("request_count") != 224 or manifest.get("sequence_count") != 10 or \
            manifest.get("ids") != sorted(EXPECTED_IDS):
        raise ValueError("manifest no describe el snapshot completo de 224 requests/10 secuencias")
    sequences = []
    seen = set()
    for seq, meta in manifest.get("sequences", {}).items():
        rows = read_jsonl(corpus_dir / f"{seq}.jsonl")
        if len(rows) != meta.get("count") or not rows or rows[0].get("path") != "/__reset" or \
                rows[0].get("method") != "POST" or rows[0].get("auth") != "valid" or \
                rows[0].get("status") != 200 or rows[0].get("request") is not None or \
                rows[0].get("raw_body") is not None or rows[0].get("raw_body_b64") is not None or \
                rows[0].get("request_b64") not in (None, ""):
            raise ValueError(f"{seq}: fixture incompleto o sin reset")
        for n, row in enumerate(rows, 1):
            sid = row.get("source_id")
            if row.get("seq") != seq or row.get("n") != n or sid in seen:
                raise ValueError(f"{seq}: orden, secuencia o source_id inválido")
            seen.add(sid)
            if not isinstance(row.get("method"), str) or not isinstance(row.get("path"), str) or \
                    row["method"] != row["method"].upper() or not row["path"].startswith("/") or \
                    row.get("auth") not in ("valid", "none", "empty", "invalid", "scheme") or \
                    not isinstance(row.get("hipotesis"), str) or not row["hipotesis"].strip() or \
                    type(row.get("status")) is not int or "response" not in row or "raw" not in row:
                raise ValueError(f"{seq}: request incompleto o inválido")
            if row.get("raw_body") is not None and not isinstance(row["raw_body"], str):
                raise ValueError(f"{seq}: raw_body debe ser texto o null")
            if row.get("raw_body_b64") is not None:
                if not isinstance(row["raw_body_b64"], str):
                    raise ValueError(f"{seq}: raw_body_b64 debe ser texto o null")
                base64.b64decode(row["raw_body_b64"], validate=True)
            if row.get("content_type") is not None and not isinstance(row["content_type"], str):
                raise ValueError(f"{seq}: content_type debe ser texto o null")
            if row.get("request_b64") is not None:
                base64.b64decode(row["request_b64"], validate=True)
            if row.get("response_b64") is not None:
                base64.b64decode(row["response_b64"], validate=True)
            if "response_b64" in row and row["response_b64"] is None:
                raise ValueError(f"{seq}: response_b64 nulo")
        sequences.append((seq, rows))
    if len(sequences) != 10 or len(seen) != 224:
        raise ValueError("corpus con secuencias o filas faltantes")
    if seen != EXPECTED_IDS:
        raise ValueError("source_id no coincide con el snapshot esperado")
    for seq, rows in sequences:
        if manifest["sequences"].get(seq, {}).get("source_ids") != [r["source_id"] for r in rows]:
            raise ValueError(f"{seq}: source_ids no coincide con el manifest")
    return manifest, sequences


def _contract_match(expected: dict, actual: dict) -> bool:
    if expected.get("status") != actual.get("status"):
        return False
    actual_bytes = base64.b64decode(actual["response_b64"], validate=True)
    if expected.get("response_b64") is not None:
        expected_bytes = base64.b64decode(expected["response_b64"], validate=True)
        try:
            expected_json = json.loads(expected_bytes)
            expected_is_json = True
        except (UnicodeDecodeError, json.JSONDecodeError):
            expected_is_json = False
            expected_json = None
        try:
            actual_json = json.loads(actual_bytes)
            actual_is_json = True
        except (UnicodeDecodeError, json.JSONDecodeError):
            actual_is_json = False
            actual_json = None
        if expected_is_json and actual_is_json:
            return strict_equal(expected_json, actual_json)
        return expected_bytes == actual_bytes
    expected_text = expected.get("raw")
    try:
        expected_json = json.loads(expected_text)
        expected_is_json = True
    except (TypeError, UnicodeDecodeError, json.JSONDecodeError):
        expected_is_json = False
        expected_json = None
    try:
        actual_json = json.loads(actual_bytes)
        actual_is_json = True
    except (UnicodeDecodeError, json.JSONDecodeError):
        actual_is_json = False
        actual_json = None
    if expected_is_json and actual_is_json:
        return strict_equal(expected_json, actual_json)
    return actual.get("raw") == expected_text


def _byte_match(expected: dict, actual: dict) -> bool | None:
    if "response_b64" not in expected:
        return None
    return (expected.get("status") == actual.get("status") and
            base64.b64decode(expected["response_b64"], validate=True) ==
            base64.b64decode(actual["response_b64"], validate=True))


def replay(corpus_dir: Path, *, epoch: str, prefix: str, max_requests: int = 250,
           client: Client | None = None, capture_dir: Path = DEFAULT_CAPTURE) -> tuple[dict, int]:
    if not epoch or not prefix or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for c in prefix) or \
            prefix in (".", "..") or max_requests < 1 or max_requests > 250:
        raise ValueError("epoch y prefix son obligatorios; max-requests debe estar entre 1 y 250")
    manifest, sequences = validate_corpus(corpus_dir)
    count = manifest["request_count"]
    if count > max_requests:
        raise ValueError(f"el replay requiere {count} requests y supera max-requests={max_requests}")
    cl = client or Client(epoch=epoch)
    used = cl.used_today()
    cap = min(cl.daily_cap, used + max_requests)
    if used + count > cap:
        raise ValueError(f"cuota insuficiente: usados={used}, necesarios={count}, techo={cap}")
    cl.daily_cap = cap  # transient guard on this Client only
    if cl.epoch != epoch:
        cl.epoch = epoch
    replay_names = [f"{prefix}-{source_seq}" for source_seq, _ in sequences]
    for name in replay_names:
        if cl.seq_steps(name) or cl.pending_steps(name):
            raise ValueError(f"la secuencia {name!r} ya existe; usa otro --prefix")

    capture_dir = capture_dir / prefix
    capture_dir.mkdir(parents=True, exist_ok=False)
    report = {"epoch": epoch, "prefix": prefix, "request_count": 0, "sequences": {},
              "raw_compared": 0, "raw_deltas": 0, "contract_compared": 0,
              "contract_deltas": 0, "missing_historical_bytes": 0, "new_evidence_ids": [],
              "incomplete": False}
    all_captures = []

    def save_progress() -> None:
        (capture_dir / "corpus.jsonl").write_text("".join(
            json.dumps(row, ensure_ascii=False) + "\n" for row in all_captures))
        (capture_dir / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n")

    for source_seq, expected_rows in sequences:
        seq_name = f"{prefix}-{source_seq}"
        captures = []
        pending_conclusions = []
        reset_actual = None
        reset_row = expected_rows[0]
        try:
            with cl.sequence(seq_name, f"A2 {epoch}: reset para replay {source_seq}", no_cache=True) as sequence:
                sequence.flush()
                observed = cl.seq_steps(seq_name)
                if not observed or observed[-1].get("path") != "/__reset":
                    raise RuntimeError(f"{seq_name}: no se registró el reset inicial")
                actual_reset = observed[-1]
                reset_actual = _captured(actual_reset, reset_row["source_id"])
                if "request" in reset_row:
                    reset_actual["request_display"] = reset_row["request"]
                captures.append(reset_actual)
                all_captures.append(reset_actual)
                report["request_count"] += 1
                report["contract_compared"] += 1
                if not _contract_match(reset_row, reset_actual):
                    report["contract_deltas"] += 1
                raw = _byte_match(reset_row, reset_actual)
                if raw is None:
                    report["missing_historical_bytes"] += 1
                else:
                    report["raw_compared"] += 1
                    if not raw:
                        report["raw_deltas"] += 1
                pending_conclusions.append((actual_reset["id"], reset_row, reset_actual))
                save_progress()
                for expected in expected_rows[1:]:
                    body = expected.get("request")
                    kwargs = {"auth": expected.get("auth", "valid"),
                              "content_type": expected.get("content_type")}
                    if expected.get("request_b64") is not None:
                        kwargs["raw_body_b64"] = expected["request_b64"]
                        body = None
                    elif "raw_body_b64" in expected and expected["raw_body_b64"] is not None:
                        kwargs["raw_body_b64"] = expected["raw_body_b64"]
                        body = None
                    elif "raw_body" in expected and expected["raw_body"] is not None:
                        kwargs["raw_body"] = expected["raw_body"]
                        body = None
                    result = sequence.call(expected.get("method", "POST"), expected.get("path", "/msg"),
                                           body, f"A2 replay: source ID {expected['source_id']}", **kwargs)
                    actual = _captured(result.entry, expected["source_id"])
                    if "request" in expected:
                        actual["request_display"] = expected["request"]
                    captures.append(actual)
                    all_captures.append(actual)
                    report["request_count"] += 1
                    report["contract_compared"] += 1
                    if not _contract_match(expected, actual):
                        report["contract_deltas"] += 1
                    raw = _byte_match(expected, actual)
                    if raw is None:
                        report["missing_historical_bytes"] += 1
                    else:
                        report["raw_compared"] += 1
                        if not raw:
                            report["raw_deltas"] += 1
                    pending_conclusions.append((result.id, expected, actual))
                    save_progress()
        except Exception as exc:
            report["incomplete"] = True
            report["error_type"] = type(exc).__name__
            report["sequences"][source_seq] = {"replay_seq": seq_name, "count": len(captures),
                                               "source_ids": [c["source_id"] for c in captures]}
            for evidence_id, expected, actual in pending_conclusions:
                try:
                    cl.conclude(evidence_id, f"A2 replay {epoch}; source ID {expected['source_id']}; "
                                f"incompleto después de respuesta capturada")
                    report["new_evidence_ids"].append(evidence_id)
                except Exception:
                    pass
            report["incomplete_reason"] = "falló el envío, la comparación o el registro de conclusión"
            save_progress()
            return report, 2
        for evidence_id, expected, actual in pending_conclusions:
            try:
                cl.conclude(evidence_id, f"A2 replay {epoch}; source ID {expected['source_id']}; "
                            f"contrato={'igual' if _contract_match(expected, actual) else 'delta'}")
                report["new_evidence_ids"].append(evidence_id)
            except Exception as exc:
                report["incomplete"] = True
                report["error_type"] = type(exc).__name__
                report["incomplete_reason"] = "no se pudo concluir evidencia capturada"
                save_progress()
                return report, 2
        report["sequences"][source_seq] = {"replay_seq": seq_name, "count": len(captures),
                                           "source_ids": [c["source_id"] for c in captures]}
        save_progress()
    save_progress()
    code = 2 if report["incomplete"] or report["request_count"] != 224 else \
        (1 if report["contract_deltas"] else 0)
    return report, code


def _captured(entry: dict, source_id: int) -> dict:
    row = {"source_id": source_id}
    for key in ("id", "seq", "method", "path", "auth", "request", "request_b64", "raw_body",
                "raw_body_b64", "content_type", "status", "response", "response_b64", "raw",
                "x_req", "epoch", "ts", "outcome"):
        if key in entry:
            row[key] = entry[key]
    return row


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="construye el snapshot offline")
    b.add_argument("--log", type=Path, default=DEFAULT_LOG)
    b.add_argument("--examples", type=Path, default=DEFAULT_EXAMPLES)
    b.add_argument("--out", type=Path, default=DEFAULT_OUT)
    r = sub.add_parser("replay", help="revalida el snapshot contra el original usando bb.Client")
    r.add_argument("corpus", type=Path, nargs="?", default=DEFAULT_OUT)
    r.add_argument("--epoch", required=True)
    r.add_argument("--prefix", required=True)
    r.add_argument("--max-requests", type=int, default=250)
    r.add_argument("--capture-dir", type=Path, default=DEFAULT_CAPTURE)
    args = parser.parse_args(argv)
    if args.command == "build":
        print(json.dumps(build(args.log, args.examples, args.out), ensure_ascii=False, indent=2))
        return 0
    report, code = replay(args.corpus, epoch=args.epoch, prefix=args.prefix,
                          max_requests=args.max_requests, capture_dir=args.capture_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
