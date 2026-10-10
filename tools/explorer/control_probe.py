#!/usr/bin/env python3
"""Scan candidate integrity controls for one fixed message base.

Append a numeric candidate to the base as ``<base>;<control>``. A passing
probe means only that the response is consistent with passing integrity; the
command may still fail. The default range 0..98 uses 99 probes plus reset.
Probe 99 separately with a fresh sequence if necessary.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:  # package import and direct script execution
    from tools.explorer.bb import Client
except ModuleNotFoundError:  # pragma: no cover - exercised by direct CLI use
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from tools.explorer.bb import Client


def error_code(result) -> str | None:
    response = result.response
    return response.get("error") if isinstance(response, dict) else None


def known_success(result) -> bool:
    """Recognize only success bodies already seen for supported commands."""
    response = result.response
    if result.status == 201 and isinstance(response, dict) \
            and set(response) == {"cuentaId"} \
            and isinstance(response["cuentaId"], str) \
            and re.fullmatch(r"AC-\d{4}", response["cuentaId"]):
        return True
    if result.status == 200 and isinstance(response, dict):
        if set(response) == {"cuenta_id", "saldo"} \
                and isinstance(response["cuenta_id"], str) \
                and isinstance(response["saldo"], (int, float)):
            return True
        if set(response) == {"status", "operacionId"} \
                and response["status"] == "recieved" \
                and isinstance(response["operacionId"], str) \
                and re.fullmatch(r"OP-\d{4}", response["operacionId"]):
            return True
        if set(response) == {"ok", "anulada"} and response["ok"] is True \
                and isinstance(response["anulada"], str) \
                and re.fullmatch(r"OP-\d{4}", response["anulada"]):
            return True
        if response == {"ok": False, "motivo": "ya anulada"}:
            return True
    return False


def exit_status(classification: str) -> int:
    return {"control_passed": 0, "no_match": 1, "malformed": 2, "unexpected": 2}[classification]


def scan(client, base: str, seq: str, start: int = 0, stop: int = 98) -> dict:
    """Run candidates in order; stop on a recognized integrity pass or ambiguity."""
    before = client.used_today()
    probes = []
    reset_id = None
    classification = "no_match"
    with client.sequence(
        seq,
        f"reset inicial para escanear controles de {base!r}",
        no_cache=True,
    ) as sequence:
        sequence.flush()
        reset_steps = client.seq_steps(seq)
        reset_id = reset_steps[-1]["id"] if reset_steps else None
        for control in range(start, stop + 1):
            message = f"{base};{control}"
            result = sequence.msg(
                message,
                f"probar control {control} para base fija {base!r}",
                confirm=True,
            )
            code = error_code(result)
            row = {
                "control": control,
                "id": result.id,
                "status": result.status,
                "response": result.response,
            }
            probes.append(row)
            if result.status == 400 and code == "E202":
                continue
            if result.status == 400 and code == "E201":
                classification = "malformed"
                break
            expected_post_integrity = {
                "E301": 400,
                "E302": 400,
                "E303": 400,
                "E401": 404,
                "E402": 404,
                "E506": 422,
                "E507": 422,
            }
            if known_success(result) or expected_post_integrity.get(code) == result.status:
                classification = "control_passed"
            else:
                classification = "unexpected"
            break
    return {
        "seq": seq,
        "base": base,
        "range": [start, stop],
        "classification": classification,
        "reset_id": reset_id,
        "probes": probes,
        "ids": [p["id"] for p in probes],
        "used_before": before,
        "used_after": client.used_today(),
        "oracle_note": "control_passed indica respuesta compatible con control válido, no éxito del comando",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", help="mensaje antes de ;control; termina en ; para probar campo vacío")
    parser.add_argument("--seq", required=True, help="nombre nuevo y único de secuencia")
    parser.add_argument("--start", type=int, default=0, help="control inicial inclusive (0..99)")
    parser.add_argument("--stop", type=int, default=98,
                        help="control final inclusive (0..99); default 98 deja 99 sondas + reset")
    parser.add_argument("--log", type=Path, help="ruta del log de experimentos")
    parser.add_argument("--coord-dir", type=Path, help="directorio del lock/cuota compartidos")
    args = parser.parse_args(argv)
    if not args.base:
        parser.error("base debe ser no vacía; termina con ; si necesitas probar un campo vacío")
    if not (0 <= args.start <= 99 and 0 <= args.stop <= 99 and args.start <= args.stop):
        parser.error("se requiere 0 <= start <= stop <= 99")
    client = Client(log_path=args.log, coord_dir=args.coord_dir)
    result = scan(client, args.base, args.seq, args.start, args.stop)
    print(json.dumps(result, ensure_ascii=False))
    return exit_status(result["classification"])


if __name__ == "__main__":
    raise SystemExit(main())
