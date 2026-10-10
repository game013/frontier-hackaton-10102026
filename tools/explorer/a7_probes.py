#!/usr/bin/env python3
"""Genera offline las sondas A7 de CAM-V2-3 (bloqueo E510) en tests/corpus/a7/probes/.

Cierran lo que A6 dejó sin medir: qué errores de TRANSFER cuentan como fallo (E304, E401,
E303), qué requests intermedios no rompen la racha, el orden de E510 frente a E304/E401/E303,
el valor de `intentos` tras desbloquear y volver a bloquear, y si un DEPOSITO fallido libera.
Cada archivo es una secuencia para ``bb.py run`` (el runner añade el reset). Cero requests.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from a6_probes import alta, consulta, dep, m, tr  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "tests" / "corpus" / "a7" / "probes"
SETUP_FUNDS = 1000000


def setup() -> list[dict]:
    """AC-0001 con fondos (origen) y AC-0002 (destino)."""
    return [alta("Lucia"), alta("Mateo"), dep(1, SETUP_FUNDS)]


def e506(n: int, extra: str = "") -> dict:
    return tr(1, 2, 60000, f"E506 #{n} de AC-0001{extra}")


def block() -> list[dict]:
    return [e506(1), e506(2), e506(3, "; queda bloqueada (CAM-V2-3)")]


def racha(code: str, step: dict) -> list[dict]:
    """E506, E506, <error candidato>, E506, válido: tres resultados distinguibles.

    Si el candidato cuenta como fallo, el cuarto TRANSFER ya da E510. Si es neutro, el cuarto
    da E506 (tercer fallo) y el válido da E510. Si reinicia la racha, el válido da 200.
    """
    return setup() + [
        e506(1), e506(2), step,
        tr(1, 2, 60000, f"CAM-V2-3 racha: E510 si {code} contó como fallo; E506 si no"),
        tr(1, 2, 1000, f"CAM-V2-3 racha: E510 si {code} es neutro; 200 si reinició la racha"),
    ]


def e304_racha() -> list[dict]:
    return racha("E304", tr(1, 1, 1000, "E304 (origen = destino) en mitad de la racha"))


def e401_racha() -> list[dict]:
    return racha("E401", tr(1, 99, 1000, "E401 (destino inexistente) en mitad de la racha"))


def e303_racha() -> list[dict]:
    return racha("E303", m("TRANSFER;AC-0001;AC-0002;007", "E303 (monto 007) en mitad de la racha"))


def neutros() -> list[dict]:
    return setup() + [
        e506(1), e506(2),
        consulta(1, "CONSULTA del origen en mitad de la racha"),
        alta("Ana"),
        dep(2, 100, "DEPOSITO a otra cuenta en mitad de la racha"),
        e506(3, "; E506 si CONSULTA/ALTA/DEPOSITO ajeno no cuentan"),
        tr(1, 2, 1000, "CAM-V2-3: E510 si CONSULTA, ALTA y DEPOSITO a otra cuenta son neutros; "
                       "200 si alguno reinició la racha"),
    ]


def orden() -> list[dict]:
    return setup() + block() + [
        tr(1, 1, 1000, "ERR-ORD v2: cuenta bloqueada con origen = destino, ¿E304 o E510?"),
        tr(1, 99, 1000, "ERR-ORD v2: cuenta bloqueada con destino inexistente, ¿E401 o E510?"),
        m("TRANSFER;AC-0001;AC-0002;007", "ERR-ORD v2: cuenta bloqueada con monto 007, ¿E303 o E510?"),
        tr(1, 2, 1000, "CAM-V2-3: E510; `intentos` = 1 + número de E510 previos de esta sonda"),
    ]


def rebloqueo() -> list[dict]:
    return setup() + block() + [
        tr(1, 2, 1000, "bloqueada: E510 intentos 1"),
        tr(1, 2, 1000, "bloqueada: E510 intentos 2"),
        dep(1, 100, "DEPOSITO a la cuenta bloqueada: la libera (A6)"),
        e506(1, " tras desbloquear"),
        e506(2, " tras desbloquear"),
        tr(1, 2, 1000, "CAM-V2-3: 200 si el DEPOSITO puso la racha a cero; E510 si conserva 3"),
        e506(1, " tras el TRANSFER exitoso"),
        e506(2, " tras el TRANSFER exitoso"),
        e506(3, "; nuevo bloqueo"),
        tr(1, 2, 1000, "CAM-V2-3: en el segundo bloqueo, ¿`intentos` vuelve a 1 o sigue en 3?"),
    ]


def deposito_fallido() -> list[dict]:
    return setup() + block() + [
        m("DEPOSITO;AC-0001;007", "DEPOSITO fallido (E303) a la cuenta bloqueada"),
        tr(1, 2, 1000, "CAM-V2-3: E510 si un DEPOSITO fallido no libera; 200 si libera"),
    ]


SEQUENCES = {
    "01-e304-racha": e304_racha,
    "02-e401-racha": e401_racha,
    "03-e303-racha": e303_racha,
    "04-neutros": neutros,
    "05-orden": orden,
    "06-rebloqueo": rebloqueo,
    "07-deposito-fallido": deposito_fallido,
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
