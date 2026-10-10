#!/usr/bin/env python3
"""Genera offline la batería A3 (estado) en tests/corpus/a3/.

Cada archivo es una secuencia para ``bb.py run`` (el runner añade el reset inicial).
Los controles se calculan con la fórmula A1; ``bad`` fuerza E202 a propósito.
No contacta al original.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from control import control  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "tests" / "corpus" / "a3"


def m(base: str, hip: str) -> dict:
    return {"request": {"m": f"{base};{control(base)}"}, "hipotesis": hip}


def bad(base: str, hip: str) -> dict:
    c = control(base)
    return {"request": {"m": f"{base};{c - 1 if c > 2 else c + 1}"}, "hipotesis": hip}


def raw(m_full: str, hip: str) -> dict:
    return {"request": {"m": m_full}, "hipotesis": hip}


def http(method: str, path: str, hip: str, **kw) -> dict:
    return {"method": method, "path": path, "hipotesis": hip, **kw}


def alta(name: str, hip: str = "ALTA válida asigna el siguiente AC") -> dict:
    return m(f"ALTA;{name}", hip)


def dep(acc: str, amount: str, hip: str) -> dict:
    return m(f"DEPOSITO;{acc};{amount}", hip)


def tr(src: str, dst: str, amount: str, hip: str) -> dict:
    return m(f"TRANSFER;{src};{dst};{amount}", hip)


def con(acc: str, hip: str) -> dict:
    return m(f"CONSULTA;{acc}", hip)


def anula(op: str, hip: str) -> dict:
    return m(f"ANULA;{op}", hip)


A, B, C = "AC-0001", "AC-0002", "AC-0003"

SEQUENCES: dict[str, list[dict]] = {
    "01-ids-alta-errores": [
        bad("ALTA;Ana", "ALTA con E202 no debería asignar AC"),
        raw("ALTA;Ana;5X", "ALTA con E201 no debería asignar AC"),
        m("ALTA;Ana;Lopez", "ALTA con E302 no debería asignar AC"),
        m("ALTA;", "ALTA con nombre vacío: ¿error o alta? ¿consume AC?"),
        alta("Ana", "primera ALTA válida tras errores: ¿AC-0001 o salta?"),
        alta("Beto", "segunda ALTA válida: consecutiva"),
    ],
    "02-ids-op-errores": [
        alta("Ana"), alta("Beto"),
        dep(A, "1000", "primer depósito: OP-0001"),
        dep("AC-0009", "1000", "DEPOSITO a cuenta inexistente E401: ¿consume OP?"),
        dep(A, "007", "DEPOSITO con monto 007 E303: ¿consume OP?"),
        bad(f"DEPOSITO;{A};1000", "DEPOSITO con E202: ¿consume OP?"),
        dep(A, "1000", "depósito tras errores: ¿OP-0002 o salta?"),
        tr(B, A, "500", "TRANSFER con E507 (B sin saldo): ¿consume OP?"),
        tr(A, "AC-0009", "100", "TRANSFER a destino inexistente E401: ¿consume OP?"),
        tr("AC-0009", A, "100", "TRANSFER desde origen inexistente: ¿E401?"),
        dep(A, "1000", "depósito tras errores de TRANSFER: ¿siguiente OP sin saltos?"),
        con(A, "saldo A = 3000: los fallidos no movieron saldo"),
        con(B, "saldo B = 0"),
    ],
    "03-ids-e506": [
        alta("Ana"), alta("Beto"),
        dep(A, "250000", "fondos para probar E506: OP-0001"),
        tr(A, B, "120000", "TRANSFER 120000 → E506: ¿consume OP?"),
        tr(A, B, "1000", "TRANSFER válida tras E506: ¿OP-0002 o OP-0003?"),
        con(A, "saldo A = 249000: E506 no movió saldo"),
    ],
    "04-anula-deposito-ids": [
        alta("Ana"),
        dep(A, "1000", "depósito OP-0001"),
        anula("OP-0001", "ANULA de un depósito: ¿ok y revierte saldo?"),
        con(A, "saldo tras anular depósito: ¿0?"),
        dep(A, "500", "depósito tras ANULA: ¿ANULA consume OP (OP-0003) o no (OP-0002)?"),
        anula("OP-0001", "segunda ANULA del mismo depósito: ya anulada"),
        anula("OP-0009", "ANULA inexistente E402: ¿consume OP?"),
        dep(A, "1", "depósito tras E402: ¿siguiente OP sin salto?"),
        con(A, "saldo final A = 501"),
    ],
    "05-ids-ping-consulta": [
        m("PING", "PING no debería consumir IDs"),
        con(A, "CONSULTA a inexistente tras reset: E401"),
        alta("Ana", "ALTA tras PING y CONSULTA fallida: AC-0001"),
        con(A, "CONSULTA de cuenta nueva: saldo 0"),
        alta("Beto", "ALTA tras CONSULTA exitosa: AC-0002"),
        dep(B, "10", "primer depósito: OP-0001 (CONSULTA/ALTA no consumen OP)"),
    ],
    "06-anula-deposito-gastado": [
        alta("Ana"), alta("Beto"),
        dep(A, "1000", "depósito OP-0001"),
        tr(A, B, "800", "transferir 800 de lo depositado: OP-0002"),
        anula("OP-0001", "ANULA de depósito ya gastado: ¿ok con saldo negativo, E507 u otro?"),
        con(A, "saldo de A tras anular depósito gastado"),
        con(B, "saldo de B intacto"),
    ],
    "07-anula-transfer-gastada": [
        alta("Ana"), alta("Beto"), alta("Caro"),
        dep(A, "1000", "depósito OP-0001"),
        tr(A, B, "1000", "A→B 1000: OP-0002"),
        tr(B, C, "1000", "B→C 1000: OP-0003 (B queda en 0)"),
        anula("OP-0002", "ANULA de transferencia cuyo receptor ya gastó: ¿ok, negativo o error?"),
        con(A, "saldo A tras anular OP-0002"),
        con(B, "saldo B tras anular OP-0002"),
        con(C, "saldo C intacto"),
        anula("OP-0003", "ANULA de la segunda transferencia"),
        con(B, "saldo B tras anular OP-0003"),
        con(C, "saldo C tras anular OP-0003"),
    ],
    "08-anula-formatos": [
        alta("Ana"),
        dep(A, "100", "depósito OP-0001"),
        anula(A, "ANULA con ID de cuenta: ¿E402, E401 u otro?"),
        anula("op-0001", "ANULA con prefijo en minúsculas"),
        anula("OP-1", "ANULA sin ceros a la izquierda"),
        anula("OP-00001", "ANULA con cinco dígitos"),
        anula("OP-0000", "ANULA OP-0000"),
        anula("OP-0002", "ANULA del siguiente OP aún no emitido"),
        anula("OP-0001", "ANULA canónica: ok si los formatos anteriores no anularon"),
        con(A, "saldo tras anulación canónica"),
    ],
    "09-anula-sin-operaciones": [
        anula("OP-0001", "ANULA OP-0001 sin operaciones tras reset: E402"),
        anula("AC-0001", "ANULA con AC inexistente: ¿E402 o E401?"),
        m("ANULA;OP-0001;OP-0002", "ANULA con dos argumentos: E302"),
        m("ANULA", "ANULA sin argumentos: E302"),
        bad("ANULA;OP-0042", "E202 antes que E402 (repetición)"),
        anula("OP-9999", "ANULA OP-9999: E402"),
    ],
    "10-e506-acumulado": [
        alta("Ana"), alta("Beto"),
        dep(A, "250000", "fondos OP-0001"),
        dep(A, "250000", "fondos OP-0002"),
        tr(A, B, "100000", "1.ª transferencia de 100000"),
        tr(A, B, "100000", "2.ª de 100000: si falla, el límite es acumulado"),
        tr(A, B, "100000", "3.ª de 100000"),
        tr(A, B, "100000", "4.ª de 100000"),
        con(A, "saldo A según cuántas pasaron"),
    ],
    "11-e506-deposito": [
        alta("Ana"),
        dep(A, "120000", "DEPOSITO 120000: ¿aplica E506 a depósitos?"),
        dep(A, "1000000", "DEPOSITO 1000000"),
        dep(A, "99999999", "DEPOSITO 99999999"),
        con(A, "saldo tras depósitos grandes"),
    ],
    "12-e506-vs-e507": [
        alta("Ana"), alta("Beto"),
        tr(A, B, "120000", "TRANSFER 120000 sin saldo: ¿E506 o E507 primero?"),
        tr(A, B, "100", "TRANSFER 100 sin saldo: E507"),
        tr(A, B, "100001", "TRANSFER 100001 sin saldo"),
    ],
    "13-e506-umbral-grueso": [
        alta("Ana"), alta("Beto"),
        dep(A, "250000", "fondos"), dep(A, "250000", "fondos"),
        tr(A, B, "100001", "TRANSFER 100001: ¿E506? (borde superior de 100000)"),
        tr(A, B, "110000", "TRANSFER 110000"),
        tr(A, B, "119999", "TRANSFER 119999"),
        con(A, "saldo A"),
    ],
    "14-e506-anula-restaura": [
        alta("Ana"), alta("Beto"),
        dep(A, "250000", "fondos OP-0001"), dep(A, "250000", "fondos OP-0002"),
        tr(A, B, "100000", "OP-0003"),
        tr(A, B, "100000", "OP-0004 (o E506 si es acumulado)"),
        anula("OP-0003", "ANULA de transferencia"),
        tr(A, B, "100000", "tras ANULA: ¿recupera capacidad si el límite es acumulado?"),
        con(A, "saldo A"),
    ],
    "15-e506-por-cuenta": [
        alta("Ana"), alta("Beto"), alta("Caro"),
        dep(A, "250000", "fondos A"), dep(C, "250000", "fondos C"),
        tr(A, B, "100000", "A→B 100000"),
        tr(C, B, "100000", "C→B 100000: ¿límite compartido entre cuentas?"),
        tr(A, C, "100000", "A→C 100000: ¿límite por destino?"),
        con(B, "saldo B"),
    ],
    "16-reset-alcance": [
        alta("Ana"),
        dep(A, "500", "OP-0001 antes del reset intermedio"),
        http("POST", "/__reset", "reset intermedio con auth válida: respuesta"),
        con(A, "tras reset la cuenta ya no existe: E401"),
        anula("OP-0001", "tras reset la operación ya no existe: E402"),
        alta("Beto", "tras reset el contador de AC vuelve a AC-0001"),
        dep(A, "7", "tras reset el contador de OP vuelve a OP-0001"),
        con(A, "saldo de la cuenta nueva: 7"),
    ],
    "17-reset-auth-metodo": [
        alta("Ana"),
        http("POST", "/__reset", "reset sin auth: 401 y no resetea", auth="none"),
        http("POST", "/__reset", "reset con token inválido: 401 y no resetea", auth="invalid"),
        http("GET", "/__reset", "GET /__reset: ¿404 y no resetea?"),
        http("PUT", "/__reset", "PUT /__reset: ¿404 y no resetea?"),
        http("POST", "/__reset/", "POST /__reset/ con barra final: ¿404 o reset?"),
        con(A, "la cuenta sigue: ningún reset anterior surtió efecto"),
        alta("Beto", "contador intacto: AC-0002 (o AC-0001 si /__reset/ reseteó)"),
    ],
    "18-reset-doble-cuerpo": [
        http("POST", "/__reset", "segundo reset consecutivo: misma respuesta"),
        http("POST", "/__reset", "reset con cuerpo JSON arbitrario", request={"m": "PING;64"}),
        alta("Ana", "tras resets: AC-0001"),
    ],
    "19-transfer-misma-cuenta": [
        alta("Ana"),
        dep(A, "1000", "OP-0001"),
        tr(A, A, "500", "TRANSFER a la misma cuenta: ¿ok, error o consume OP?"),
        con(A, "saldo tras auto-transferencia"),
        dep(A, "1", "siguiente OP tras auto-transferencia"),
    ],
    # Fase 2: orden de errores alrededor de E104/E304 y ANULA de montos sobre el límite.
    "21-orden-e304": [
        alta("Ana"),
        tr(A, A, "200000", "E304 frente a E506 (misma cuenta, monto sobre límite)"),
        tr(A, A, "100", "E304 frente a E507 (misma cuenta sin saldo)"),
        tr("AC-0009", "AC-0009", "100", "E304 frente a E401 (misma cuenta inexistente)"),
        tr(A, A, "007", "E304 frente a E303 (monto inválido)"),
        bad(f"TRANSFER;{A};{A};100", "E202 antes que E304"),
    ],
    "22-orden-e401-e506-e507": [
        alta("Ana"),
        tr(A, "AC-0009", "120000", "E401 (destino) frente a E506"),
        tr("AC-0009", A, "120000", "E401 (origen) frente a E506"),
        tr(A, "AC-0009", "100", "E401 (destino) frente a E507 (origen sin saldo)"),
        dep("AC-0009", "007", "E401 frente a E303 en DEPOSITO"),
        tr(A, "AC-0009", "007", "E401 frente a E303 en TRANSFER"),
        tr(A, A, "120000", "repetición E304 frente a E506"),
    ],
    "23-orden-e104": [
        bad("ALTA;", "E104 frente a E202 (segmento vacío con control incorrecto)"),
        m("CONSULTA;", "CONSULTA con segmento vacío: E104"),
        m(f"DEPOSITO;{A};", "DEPOSITO con monto vacío: ¿E104 antes que E401?"),
        m(f"TRANSFER;{A};;100", "TRANSFER con destino vacío: E104"),
        m("ALTA;;", "ALTA con dos vacíos: ¿E104 o E302 primero?"),
        m("ANULA;", "ANULA vacío: E104"),
        alta("Ana", "tras E104 la primera alta es AC-0001"),
    ],
    "24-anula-sobre-limite": [
        alta("Ana"), alta("Beto"),
        dep(A, "250000", "depósito sobre el límite de transferencia OP-0001"),
        anula("OP-0001", "ANULA de depósito de 250000: ¿E506 o ok?"),
        con(A, "saldo 0 tras anular depósito grande"),
        dep(B, "100", "OP-0002"),
        tr(A, B, "50", "cuenta en 0 transfiere: E507"),
        anula("OP-0002", "anular depósito de B"),
        tr(B, A, "1", "B en 0 tras anulación: E507"),
        dep(A, "5", "OP-0003 tras E507 y ANULA"),
    ],
    "25-saldo-negativo": [
        alta("Ana"), alta("Beto"),
        dep(A, "1000", "OP-0001"),
        tr(A, B, "1000", "OP-0002"),
        anula("OP-0001", "A queda en -1000"),
        tr(A, B, "1", "cuenta con saldo negativo transfiere: E507"),
        dep(A, "500", "depósito en cuenta negativa: OP-0003"),
        con(A, "saldo -500"),
        anula("OP-0002", "anular la transferencia restituye A: 500, B: 0"),
        con(A, "saldo de A tras anular la transferencia"),
        con(B, "saldo de B tras anular la transferencia"),
    ],
    "26-orden-e104-integridad": [
        raw("ALTA;;5X", "E104 frente a E201 (control mal formado)"),
        bad("ZZZ;", "E104 frente a E301 con control incorrecto"),
        m("ZZZ;", "E104 frente a E301 con control correcto"),
        bad("ALTA;Ana;", "E104 frente a E302 con segmento vacío al final"),
        raw("ALTA;Ana;", "control vacío: ¿E104 o E201?"),
    ],
}


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
