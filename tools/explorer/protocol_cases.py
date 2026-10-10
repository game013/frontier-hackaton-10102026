#!/usr/bin/env python3
"""Extract stateless protocol cases from the evidence log (offline, no token).

Writes internal/protocol/testdata/log-cases.json: one entry per exact ``m``
whose response does not depend on state (E103, E104, E201, E202, E301, E302 or
pong), with every log ID that produced it. The exact ``m`` comes from
``request_b64``; records without it (IDs 1-50) are skipped. Fails if the same
``m`` produced different responses within the epoch.

Usage: python3 tools/explorer/protocol_cases.py [--epoch v1] [--log experimentos.jsonl] [--out PATH]
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ERR_RE = re.compile(r'^\{"error":"(E10[34]|E20[12]|E30[12])"')
PONG = '{"pong":true}'


def extract(lines, epoch):
    groups: dict[str, dict] = {}
    conflicts = []
    for line in lines:
        r = json.loads(line)
        if (r.get("epoch") != epoch or r.get("method") != "POST" or r.get("path") != "/msg"
                or r.get("auth") != "valid" or r.get("outcome") != "completed"
                or r.get("request_b64") is None or "raw" not in r):
            continue
        try:
            body = json.loads(base64.b64decode(r["request_b64"], validate=True).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            continue
        if not isinstance(body, dict) or not isinstance(body.get("m"), str):
            continue
        raw = r["raw"]
        if raw != PONG and not ERR_RE.match(raw):
            continue
        g = groups.setdefault(body["m"], {"ids": [], "m": body["m"], "status": int(r["status"]), "body": raw})
        if g["status"] != int(r["status"]) or g["body"] != raw:
            conflicts.append((body["m"], g["ids"][0], r["id"]))
        g["ids"].append(str(r["id"]))
    return sorted(groups.values(), key=lambda c: int(c["ids"][0])), conflicts


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--epoch", default="v1")
    p.add_argument("--log", default=ROOT / "experimentos.jsonl", type=Path)
    p.add_argument("--out", default=ROOT / "internal/protocol/testdata/log-cases.json", type=Path)
    a = p.parse_args(argv)
    with a.log.open(encoding="utf-8") as fh:
        cases, conflicts = extract(fh, a.epoch)
    if conflicts:
        for m, first, other in conflicts:
            print(f"conflicto: {m!r} log {first} vs {other}", file=sys.stderr)
        return 1
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(cases, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(cases)} casos en {a.out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
