#!/usr/bin/env python3
"""A3: aislamiento de estado entre BB_TOKEN y TEAM_TOKEN (contacta al original vía bb.py).

Mantiene abierta la secuencia de BB_TOKEN mientras TEAM_TOKEN hace reset y una alta;
luego comprueba que el estado de BB_TOKEN sigue intacto. Cada cliente usa su propio
token_tag, lock y cuota; ningún token se escribe en el log.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bb import Client  # noqa: E402
from control import control  # noqa: E402


def m(base: str) -> str:
    return f"{base};{control(base)}"


def main(prefix: str) -> int:
    bb, team = Client(), Client(token_var="TEAM_TOKEN")
    with bb.sequence(f"{prefix}-bb", "A3 aislamiento: estado limpio de BB_TOKEN", no_cache=True) as s:
        s.flush()
        print(s.msg(m("ALTA;Ana"), "BB_TOKEN crea AC-0001"))
        print(s.msg(m("DEPOSITO;AC-0001;777"), "BB_TOKEN deja saldo 777 en AC-0001"))
        with team.sequence(f"{prefix}-team", "A3 aislamiento: reset de TEAM_TOKEN con BB_TOKEN poblado",
                           no_cache=True) as t:
            t.flush()
            print(t.msg(m("CONSULTA;AC-0001"), "TEAM_TOKEN no ve la cuenta de BB_TOKEN: E401"))
            print(t.msg(m("ALTA;Zoe"), "TEAM_TOKEN numera aparte: AC-0001"))
        print(s.msg(m("CONSULTA;AC-0001"), "reset y alta de TEAM_TOKEN no tocan BB_TOKEN: saldo 777"))
        print(s.msg(m("ALTA;Beto"), "contador de BB_TOKEN intacto: AC-0002"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "a3-v1-20-aislamiento"))
