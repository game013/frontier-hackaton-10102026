#!/usr/bin/env python3
"""Convierte capturas del reemplazo en semillas de replay local.

Acepta el JSONL de CAPTURE_PATH o un volcado de logs de la plataforma (líneas
con prefijos de fecha o de servicio): toma de cada línea el JSON que empieza en
el primer '{' y se queda con los registros "kind": "capture". Deduplica por
(boot, n), ordena por ts y escribe una línea por secuencia (delimitada por resets
autenticados; `boot` separa reinicios del proceso), con los requests exactos y la respuesta que dio el reemplazo.

    python3 tools/capture/seeds.py var/capture.jsonl railway.log -o tests/seeds/eval.jsonl
"""
import argparse
import json
import sys

STEP_KEYS = ("n", "ts", "method", "uri", "auth", "headers", "body_b64", "body", "redacted",
             "status", "resp_b64", "resp", "panic")


def records(lines):
    for line in lines:
        start = line.find("{")
        if start < 0:
            continue
        try:
            rec = json.loads(line[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict) and rec.get("kind") == "capture":
            yield rec


def sequences(recs):
    unique = {(r.get("boot", ""), r["n"]): r for r in recs}
    out = {}
    for r in sorted(unique.values(), key=lambda r: (r["ts"], r["n"])):
        key = (r.get("boot", ""), r["seq"])
        seq = out.setdefault(key, {"boot": key[0], "seq": key[1], "version": r.get("version"), "steps": []})
        seq["steps"].append({k: r[k] for k in STEP_KEYS if k in r})
    return list(out.values())


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("inputs", nargs="+", help="JSONL de captura o volcados de log ('-' = stdin)")
    p.add_argument("-o", "--output", help="destino JSONL (por defecto stdout)")
    a = p.parse_args(argv)
    lines = []
    for name in a.inputs:
        with (sys.stdin if name == "-" else open(name, encoding="utf-8", errors="replace")) as f:
            lines.extend(f)
    seqs = sequences(records(lines))
    out = open(a.output, "w", encoding="utf-8") if a.output else sys.stdout
    with out:
        for s in seqs:
            out.write(json.dumps(s, ensure_ascii=False) + "\n")
    print(f"{sum(len(s['steps']) for s in seqs)} requests en {len(seqs)} secuencias", file=sys.stderr)


if __name__ == "__main__":
    main()
