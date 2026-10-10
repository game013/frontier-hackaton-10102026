#!/usr/bin/env python3
"""Genera offline la batería A5 (descubrimiento de comandos) en tests/corpus/a5/.

Cada archivo es una secuencia para ``bb.py run`` (el runner añade el reset inicial).
El barrido manda cada nombre del diccionario sin argumentos y con el control de la
fórmula A1: E301 sin ``sugerencia`` descarta el nombre; cualquier otra respuesta es
un hallazgo. Se ejecuta con ``BB_EPOCH=v2`` (posterior al cambio). No contacta al original.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from control import control  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "tests" / "corpus" / "a5"
DICT = OUT / "diccionario.txt"
KNOWN = {"PING", "ALTA", "CONSULTA", "DEPOSITO", "TRANSFER", "ANULA"}
NAME = re.compile(r"^[A-Z][A-Z_]*$")
CHUNK = 50


def m(base: str, hip: str, **kw) -> dict:
    return {"request": {"m": f"{base};{control(base)}"}, "hipotesis": hip, **kw}


def dictionary() -> list[str]:
    """Nombres del diccionario: mayúsculas ASCII, sin duplicados ni comandos conocidos."""
    seen: list[str] = []
    for line in DICT.read_text().splitlines():
        name = line.strip()
        if not name or name.startswith("#"):
            continue
        if not NAME.match(name):
            raise ValueError(f"nombre fuera de formato: {name!r}")
        if name not in KNOWN and name not in seen:
            seen.append(name)
    return seen


def sweep(names: list[str]) -> dict[str, list[dict]]:
    chunks = [names[i:i + CHUNK] for i in range(0, len(names), CHUNK)]
    return {
        f"barrido-{n:02d}": [
            m(name, f"A5 barrido v2: ¿existe el comando {name}? E301 sin sugerencia lo descarta")
            for name in chunk
        ]
        for n, chunk in enumerate(chunks, 1)
    }


PREVIA = [
    m("PING", "A5 previa v2: PING con control A1 sigue dando pong"),
    m("ALTA;Lucia", "A5 previa v2: ALTA con control A1 crea AC-0001 (fórmula vigente)"),
    m("CONSULTA;AC-0001", "A5 previa v2: CONSULTA de la cuenta recién creada, saldo 0"),
    m("ZZZ", "A5 previa v2: comando lejano da E301 sin sugerencia"),
    m("ALT", "A5 previa v2: comando cercano da E301 con sugerencia ALTA"),
    m("RETIRX", "A5 previa v2: ¿hay un comando oculto a distancia ≤2 de RETIRX (p. ej. RETIRO) que aparezca como sugerencia?"),
]


A = "AC-0001"

# Hallazgos del barrido: NOTAS (200 sin argumentos) y HALT (solo vía sugerencia).
CARACTERIZACION = {
    "c01-notas": [
        m("NOTAS", "NOTAS sin argumentos con estado vacío: lista de notas"),
        m("notas", "NOTAS sin distinguir caja (minúsculas)"),
        m("Notas", "NOTAS sin distinguir caja (mixta)"),
        {"request": {"m": f"NOTAS;{control('NOTAS') % 97 + 1}"}, "hipotesis": "NOTAS con control vecino: E202"},
        m("NOTAS;x", "NOTAS con un argumento: ¿E302 o lo ignora?"),
        m(f"NOTAS;{A}", "NOTAS con un ID de cuenta inexistente: ¿filtra, E302 o E401?"),
        m("ALTA;Lucia", "cuenta AC-0001 para ver si NOTAS cambia con estado"),
        m(f"DEPOSITO;{A};500", "operación OP-0001 para ver si NOTAS cambia con estado"),
        m("NOTAS", "NOTAS tras ALTA y DEPOSITO: ¿mismo contenido?"),
        m(f"NOTAS;{A}", "NOTAS con cuenta existente como argumento: ¿filtra o E302?"),
        m("NOTAS;x;y", "NOTAS con dos argumentos: aridad"),
        m("NOTA", "vecino de NOTAS: E301 con sugerencia NOTAS"),
    ],
    "c02-halt": [
        m("ALTA;Lucia", "cuenta AC-0001 antes de HALT"),
        m(f"DEPOSITO;{A};500", "saldo 500 y OP-0001 antes de HALT"),
        {"request": {"m": f"HALT;{control('HALT') % 97 + 1}"}, "hipotesis": "HALT con control vecino: E202 (integridad antes que el comando)"},
        m("HALT;x", "HALT con un argumento: ¿E302 o se ejecuta?"),
        m("HALT;x;y", "HALT con dos argumentos: aridad"),
        m("HALT", "HALT sin argumentos: usuario autoriza ejecutarlo; ¿qué responde?"),
        m("PING", "PING tras HALT: ¿el servicio sigue respondiendo?"),
        m(f"CONSULTA;{A}", "CONSULTA tras HALT: ¿se conserva el saldo 500?"),
        m("ALTA;Mateo", "ALTA tras HALT: ¿se aceptan escrituras y sigue la numeración (AC-0002)?"),
        m(f"DEPOSITO;{A};1", "DEPOSITO tras HALT: ¿se aceptan operaciones (OP-0002)?"),
        m("HALT", "HALT repetido: ¿misma respuesta?"),
        m("NOTAS", "NOTAS tras HALT"),
    ],
    "c03-tras-halt": [
        m("PING", "tras HALT y reset: PING"),
        m(f"CONSULTA;{A}", "tras HALT y reset: AC-0001 ya no existe (E401) si el reset repara"),
        m("ALTA;Lucia", "tras HALT y reset: la numeración vuelve a AC-0001"),
        m("halt", "HALT sin distinguir caja"),
    ],
}


def sequences() -> dict[str, list[dict]]:
    return {"00-previa": PREVIA, **sweep(dictionary()), **CARACTERIZACION}


SEQUENCES = sequences() if DICT.exists() else {"00-previa": PREVIA}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    total = 0
    for name, steps in SEQUENCES.items():
        path = OUT / f"{name}.jsonl"
        path.write_text("".join(json.dumps(s, ensure_ascii=False) + "\n" for s in steps))
        total += len(steps) + 1
    print(f"{len(SEQUENCES)} secuencias, {total} requests con resets → {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
