#!/usr/bin/env python3
"""Genera offline las sondas A6 (deltas de FR-0153) en tests/corpus/a6/probes/.

Cada archivo es una secuencia para ``bb.py run`` (el runner añade el reset inicial).
Los controles se calculan con la fórmula A1. No contacta al original.
Candidatos tras el replay A6: saldo como texto con dos decimales, umbral E506 más bajo y
bloqueo E510 de la cuenta tras varios E506.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from control import control  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "tests" / "corpus" / "a6" / "probes"


def m(base: str, hip: str) -> dict:
    return {"request": {"m": f"{base};{control(base)}"}, "hipotesis": hip}


def ac(n: int) -> str:
    return f"AC-{n:04d}"


def tr(src: int, dst: int, amount: int, hip: str) -> dict:
    return m(f"TRANSFER;{ac(src)};{ac(dst)};{amount}", hip)


def dep(acc: int, amount: int, hip: str = "depósito válido, fondos para la sonda") -> dict:
    return m(f"DEPOSITO;{ac(acc)};{amount}", hip)


def consulta(acc: int, hip: str) -> dict:
    return m(f"CONSULTA;{ac(acc)}", hip)


def alta(name: str) -> dict:
    return m(f"ALTA;{name}", "ALTA válida asigna el siguiente AC")


def saldo_formato() -> list[dict]:
    return [
        alta("Lucia"),
        consulta(1, "CAM-V2 saldo: v2 da saldo 0 como texto \"0.00\" (v1: número 0)"),
        dep(1, 5, "depósito de 5 unidades mínimas"),
        consulta(1, "CAM-V2 saldo: 5 se muestra \"0.05\" (centésimas, dos decimales)"),
        dep(1, 12340, "depósito de 12340"),
        consulta(1, "CAM-V2 saldo: 12345 se muestra \"123.45\""),
        alta("Mateo"),
        consulta(2, "CAM-V2 saldo: otra cuenta en cero también \"0.00\""),
    ]


def umbral(amounts: list[int]) -> list[dict]:
    """Un origen distinto por monto: ningún origen acumula E506 (evita el bloqueo)."""
    steps = [alta("Destino")]
    for i, amount in enumerate(amounts, 2):
        steps += [alta(f"Origen{i}"), dep(i, 1000000),
                  tr(i, 1, amount, f"CAM-V2 umbral: TRANSFER de {amount} (v1 aceptaba hasta 100000); "
                                   "200 si está bajo el nuevo umbral, 422 E506 si lo supera")]
    return steps


def bloqueo_base() -> list[dict]:
    return [
        alta("Lucia"), alta("Mateo"), dep(1, 1000000), dep(2, 5000),
        tr(1, 2, 100000, "E506 #1 del origen AC-0001"),
        tr(1, 2, 100000, "E506 #2 del origen AC-0001"),
        tr(1, 2, 100000, "E506 #3 del origen AC-0001; v2 ¿todavía E506?"),
        tr(1, 2, 1000, "CAM-V2 bloqueo: tras 3 E506 un TRANSFER válido del origen da 423 E510"),
        tr(1, 2, 1000, "CAM-V2 bloqueo: segundo intento bloqueado; ¿intentos crece a 2?"),
        dep(1, 100, "CAM-V2 bloqueo: ¿DEPOSITO a la cuenta bloqueada también da E510?"),
        consulta(1, "CAM-V2 bloqueo: CONSULTA de la cuenta bloqueada (replay: no bloquea)"),
        tr(2, 1, 1000, "CAM-V2 bloqueo: ¿la cuenta bloqueada puede recibir como destino?"),
        m("ANULA;OP-0001", "CAM-V2 bloqueo: ¿ANULA del depósito de la cuenta bloqueada?"),
        tr(1, 2, 1000, "CAM-V2 bloqueo: tercer intento; ¿intentos crece?"),
        consulta(1, "saldo final del origen bloqueado"),
        consulta(2, "saldo final del destino"),
    ]


def bloqueo_conteo() -> list[dict]:
    return [
        alta("Lucia"), alta("Mateo"), alta("Ana"), dep(1, 1000000),
        tr(1, 2, 100000, "E506 #1 de AC-0001"),
        tr(1, 2, 100000, "E506 #2 de AC-0001"),
        tr(1, 2, 1000, "TRANSFER válido entre E506: ¿reinicia el conteo?"),
        tr(1, 2, 100000, "E506 #3 de AC-0001 (no consecutivo)"),
        tr(1, 2, 1000, "CAM-V2 bloqueo: E510 si cuenta el total; 200 si solo consecutivos"),
        tr(3, 2, 100, "E507 #1 de AC-0003 (sin fondos)"),
        tr(3, 2, 100, "E507 #2 de AC-0003"),
        tr(3, 2, 100, "E507 #3 de AC-0003"),
        tr(3, 2, 100, "CAM-V2 bloqueo: ¿E507 repetidos también bloquean? (E510 o E507)"),
        tr(2, 1, 100000, "E506 #1 de AC-0002 (sin fondos: ¿E506 antes que E507?)"),
        tr(2, 1, 100000, "E506 #2 de AC-0002"),
        tr(2, 1, 100000, "E506 #3 de AC-0002"),
        tr(2, 1, 100000, "CAM-V2 bloqueo: cuarto TRANSFER sobre límite del origen sin fondos"),
    ]


def desbloqueo() -> list[dict]:
    """Tres orígenes bloqueados: intentos seguidos, depósito propio y ANULA propia."""
    steps = [alta("Destino"), alta("A"), alta("B"), alta("C"),
             dep(2, 1000000), dep(3, 1000000), dep(4, 1000000), dep(4, 500, "depósito para anular")]
    for src in (2, 3, 4):
        steps += [tr(src, 1, 100000, f"E506 #{i} de {ac(src)}") for i in (1, 2, 3)]
        steps.append(tr(src, 1, 1000, f"{ac(src)} bloqueada: E510 intentos 1"))
        if src == 2:
            steps += [tr(2, 1, 1000, f"CAM-V2 bloqueo: intento {i}; ¿sigue E510 o se libera solo?")
                      for i in (2, 3, 4)]
        elif src == 3:
            steps += [dep(3, 100, "depósito a la cuenta bloqueada"),
                      tr(3, 1, 1000, "CAM-V2 bloqueo: ¿el depósito propio libera la cuenta?")]
        else:
            steps += [m("ANULA;OP-0004", "anula el depósito de 500 de la cuenta bloqueada"),
                      tr(4, 1, 1000, "CAM-V2 bloqueo: ¿ANULA sobre la cuenta la libera?")]
    return steps


def desbloqueo_entrante() -> list[dict]:
    """Entrante sobre cuenta bloqueada y depósito entre fallos antes del bloqueo."""
    return [
        alta("Destino"), alta("A"), alta("B"), dep(2, 1000000), dep(3, 1000000),
        tr(2, 1, 100000, "E506 #1 de AC-0002"), tr(2, 1, 100000, "E506 #2 de AC-0002"),
        tr(2, 1, 100000, "E506 #3 de AC-0002"),
        tr(2, 1, 1000, "AC-0002 bloqueada: E510 intentos 1"),
        tr(3, 2, 1000, "TRANSFER entrante a la cuenta bloqueada"),
        tr(2, 1, 1000, "CAM-V2 bloqueo: ¿el TRANSFER entrante libera la cuenta?"),
        tr(3, 1, 100000, "E506 #1 de AC-0003"), tr(3, 1, 100000, "E506 #2 de AC-0003"),
        dep(3, 100, "depósito entre fallos, antes del bloqueo"),
        tr(3, 1, 100000, "E506 #3 de AC-0003 (tras el depósito)"),
        tr(3, 1, 1000, "CAM-V2 bloqueo: 200 si el depósito reinició el conteo; E510 si no"),
    ]


SEQUENCES = {
    "01-saldo-formato": saldo_formato,
    "02-umbral-grueso": lambda: umbral([50000, 60000, 75000, 90000, 99999]),
    "03-bloqueo-base": bloqueo_base,
    "04-bloqueo-conteo": bloqueo_conteo,
    "05-desbloqueo": desbloqueo,
    "06-umbral-fino": lambda: umbral([50001, 55000, 59999]),
    "07-desbloqueo-entrante": desbloqueo_entrante,
}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, build in SEQUENCES.items():
        steps = build()
        (OUT / f"{name}.jsonl").write_text(
            "".join(json.dumps(s, ensure_ascii=False) + "\n" for s in steps))
        print(f"{name}: {len(steps)} pasos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
