#!/usr/bin/env python3
"""A7: replay final sin caché de la versión vigente (v2) contra la evidencia v2 de A6.

Las fuentes ya son v2: la captura del replay A6 (`tests/corpus/a6/a6-v2/corpus.jsonl`, IDs
2020–2744) y las sondas A6 del log (`a6-v2-sonda-*`, IDs 2745–2861). Cada secuencia se reenvía
desde reset con los bytes exactos, sin caché, y se compara status, contrato JSON y bytes. Se
espera cero deltas: cualquiera indicaría otro cambio de versión o una respuesta no determinista.
Reutiliza la mecánica de `a6_replay.replay`.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
from pathlib import Path

try:
    from .a6_replay import _check_rows, replay
    from .corpus import read_jsonl
except ImportError:  # direct script execution from tools/explorer
    from a6_replay import _check_rows, replay
    from corpus import read_jsonl

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOG = ROOT / "experimentos.jsonl"
DEFAULT_A6_CAPTURE = ROOT / "tests/corpus/a6/a6-v2/corpus.jsonl"
DEFAULT_CAPTURE = ROOT / "tests/corpus/a7"
DEFAULT_PATTERNS = ("a6-v2-sonda-*",)
A6_PREFIX = "a6-v2-"
MAX_REQUESTS = 1000
LABEL = "A7"
EXPECTATION = "(v2 vigente; se espera sin delta)"


def _source_name(seq: str) -> str:
    return seq[len(A6_PREFIX):] if seq.startswith(A6_PREFIX) else seq


def load_sources(a6_capture: Path | None = DEFAULT_A6_CAPTURE, log_path: Path = DEFAULT_LOG,
                 patterns: tuple[str, ...] = DEFAULT_PATTERNS,
                 only: tuple[str, ...] = ()) -> list[tuple[str, list[dict]]]:
    """(nombre fuente, filas) con el reset primero; `id` de cada fila es la evidencia v2 de A6.

    El nombre quita el prefijo `a6-v2-` para que el replay quede como `<prefix>-<fuente>`.
    """
    grouped: dict[str, list[dict]] = {}
    if a6_capture is not None:
        for row in read_jsonl(a6_capture):
            grouped.setdefault(_source_name(row["seq"]), []).append(row)
    from_log: dict[str, list[dict]] = {}
    for row in read_jsonl(log_path):
        seq = row.get("seq", "")
        if any(fnmatch.fnmatchcase(seq, p) for p in patterns):
            from_log.setdefault(_source_name(seq), []).append(row)
    for name, rows in from_log.items():
        if name in grouped:
            raise ValueError(f"secuencias fuente duplicadas: {name}")
        grouped[name] = sorted(rows, key=lambda r: r["id"])
    sources = list(grouped.items())
    if only:
        sources = [(s, r) for s, r in sources if any(fnmatch.fnmatchcase(s, p) for p in only)]
    if not sources:
        raise ValueError("no hay secuencias fuente")
    for name, rows in sources:
        _check_rows(name, rows)
    return sources


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--epoch", required=True)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--only", action="append", default=[],
                        help="patrón fnmatch de secuencias fuente (repetible)")
    parser.add_argument("--max-requests", type=int, default=MAX_REQUESTS)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--a6-capture", type=Path, default=DEFAULT_A6_CAPTURE)
    parser.add_argument("--capture-dir", type=Path, default=DEFAULT_CAPTURE)
    parser.add_argument("--dry-run", action="store_true", help="lista fuentes y conteo; cero requests")
    args = parser.parse_args(argv)
    sources = load_sources(args.a6_capture, args.log, only=tuple(args.only))
    if args.dry_run:
        for name, rows in sources:
            print(f"{name}\t{len(rows)}\tA6 IDs {rows[0]['id']}–{rows[-1]['id']}")
        print(f"total\t{sum(len(r) for _, r in sources)} requests\t{len(sources)} secuencias")
        return 0
    report, code = replay(sources, epoch=args.epoch, prefix=args.prefix,
                          max_requests=args.max_requests, capture_dir=args.capture_dir,
                          label=LABEL, expectation=EXPECTATION)
    print(json.dumps({k: v for k, v in report.items() if k not in ("deltas", "new_evidence_ids",
                                                                   "sequences")},
                     ensure_ascii=False))
    for d in report["deltas"]:
        print(f"Δ {d['source_seq']}#{d['n']} a6={d['base_id']} a7={d['v2_id']} "
              f"{d['base_status']}→{d['v2_status']} contrato={'=' if d['contract_equal'] else '≠'}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
