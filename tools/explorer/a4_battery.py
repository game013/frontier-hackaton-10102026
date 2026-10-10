#!/usr/bin/env python3
"""Genera offline la batería A4 (sobre HTTP y números) en tests/corpus/a4/.

Cada archivo es una secuencia para ``bb.py run`` (el runner añade el reset inicial).
Los controles se calculan con la fórmula A1 (``control.py``); ``ctl`` arma un mensaje con
un campo de control arbitrario. Los cuerpos que JSON no puede expresar van en ``raw_body``
o ``raw_body_b64``. No contacta al original.
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from control import control  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "tests" / "corpus" / "a4"
PING = '{"m":"PING;64"}'


def m(base: str, hip: str, **kw) -> dict:
    return {"request": {"m": f"{base};{control(base)}"}, "hipotesis": hip, **kw}


def ctl(base: str, field: str, hip: str) -> dict:
    return {"request": {"m": f"{base};{field}"}, "hipotesis": hip}


def raw(body: str, hip: str, **kw) -> dict:
    return {"raw_body": body, "hipotesis": hip, **kw}


def b64(data: bytes, hip: str, **kw) -> dict:
    return {"raw_body_b64": base64.b64encode(data).decode(), "hipotesis": hip, **kw}


def http(method: str, path: str, hip: str, **kw) -> dict:
    return {"method": method, "path": path, "hipotesis": hip, **kw}


def ping_at(method: str, path: str, hip: str, **kw) -> dict:
    return http(method, path, hip, raw_body=PING, **kw)


A, B = "AC-0001", "AC-0002"


def montos_deposito(amounts: list[str]) -> list[dict]:
    steps = [m("ALTA;Lucia", "cuenta AC-0001 para depósitos")]
    for x in amounts:
        steps.append(m(f"DEPOSITO;{A};{x}", f"DEPOSITO con monto {x!r}: ¿E303 o se acepta y cómo se interpreta?"))
        steps.append(m(f"CONSULTA;{A}", f"saldo tras DEPOSITO {x!r}: valor numérico efectivo"))
    return steps


def montos_transfer(amounts: list[str]) -> list[dict]:
    steps = [m("ALTA;Lucia", "origen AC-0001"), m("ALTA;Mateo", "destino AC-0002"),
             m(f"DEPOSITO;{A};1000000", "saldo inicial del origen: 1000000")]
    for x in amounts:
        steps.append(m(f"TRANSFER;{A};{B};{x}", f"TRANSFER con monto {x!r}: E303, E506 o éxito"))
        steps.append(m(f"CONSULTA;{A}", f"saldo del origen tras TRANSFER {x!r}"))
    return steps


SEQUENCES: dict[str, list[dict]] = {
    "01-precedencia": [
        http("POST", "/no-existe", "sin auth a ruta inexistente: ¿401 o 404?", auth="none"),
        http("GET", "/no-existe", "sin auth, GET a ruta inexistente: ¿401 o 404?", auth="none"),
        http("POST", "/msg", "sin auth y cuerpo `{`: ¿401 o E100?", auth="none", raw_body="{"),
        http("POST", "/msg", "sin auth y cuerpo `{}`: ¿401 o E102?", auth="none", raw_body="{}"),
        http("GET", "/msg", "token inválido con GET /msg: ¿401 o 404?", auth="invalid"),
        http("POST", "/no-existe", "auth válida y cuerpo `{` a ruta inexistente: ¿404 o E100?", raw_body="{"),
        http("POST", "/health", "POST /health autenticado: ¿404 o 200?", raw_body=PING),
        http("GET", "/health", "GET /health con token inválido: 401", auth="invalid"),
        http("POST", "/msg", "auth vacía y cuerpo `{`: ¿401 o E100?", auth="empty", raw_body="{"),
        http("POST", "/msg", "esquema Basic y m válida: 401", auth="scheme", raw_body=PING),
    ],
    "02-rutas": [
        ping_at("POST", "/%6dsg", "ruta con escape %6d: ¿se decodifica a /msg?"),
        ping_at("POST", "/msg/", "barra final en /msg/"),
        ping_at("POST", "/msg?x=1", "query en /msg se ignora"),
        ping_at("POST", "/msg?", "query vacía en /msg"),
        ping_at("POST", "/MSG", "caja de la ruta: /MSG"),
        ping_at("POST", "/./msg", "segmento punto: /./msg"),
        ping_at("POST", "/x/../msg", "segmento punto-punto: /x/../msg"),
        ping_at("POST", "/msg%2F", "barra escapada al final"),
        ping_at("POST", "/msg;x", "parámetro de ruta con ;"),
        http("GET", "/health/", "barra final en /health/"),
        http("GET", "/health?x=1", "query en /health"),
        http("GET", "/HEALTH", "caja de la ruta: /HEALTH"),
        http("GET", "//health", "doble barra en /health"),
        http("GET", "/", "raíz"),
        http("GET", "/%68ealth", "escape en /health"),
    ],
    "03-metodos": [
        m("ALTA;Lucia", "estado previo: AC-0001 para ver si algún método resetea"),
        http("HEAD", "/msg", "HEAD /msg"),
        http("OPTIONS", "/msg", "OPTIONS /msg"),
        ping_at("PUT", "/msg", "PUT /msg con m válida"),
        http("DELETE", "/msg", "DELETE /msg"),
        ping_at("PATCH", "/msg", "PATCH /msg con m válida"),
        http("HEAD", "/health", "HEAD /health"),
        http("OPTIONS", "/health", "OPTIONS /health"),
        http("HEAD", "/nada", "HEAD a ruta inexistente"),
        http("OPTIONS", "/nada", "OPTIONS a ruta inexistente"),
        http("OPTIONS", "/msg", "OPTIONS sin auth (preflight CORS)", auth="none"),
        http("HEAD", "/msg", "HEAD sin auth", auth="none"),
        http("HEAD", "/__reset", "HEAD /__reset no debería resetear"),
        http("OPTIONS", "/__reset", "OPTIONS /__reset no debería resetear"),
        http("DELETE", "/__reset", "DELETE /__reset no debería resetear"),
        m("ALTA;Mateo", "si nada reseteó, la siguiente cuenta es AC-0002"),
    ],
    "04-cuerpos": [
        raw("", "cuerpo vacío: ¿E100 o E102?"),
        raw("[]", "array JSON: ¿E102?"),
        raw("null", "null JSON: ¿E102?"),
        raw('"PING;64"', "string JSON en la raíz"),
        raw("1", "número JSON en la raíz"),
        raw('{"m":null}', "m null: ¿E102?"),
        raw('{"M":"PING;64"}', "clave M mayúscula: ¿E102?"),
        raw('{"m":""}', "m vacía: ¿E102, E104 u otro?"),
        raw('{"m":["PING;64"]}', "m array: ¿E102?"),
        raw('{"m":true}', "m booleana: ¿E102?"),
        raw('{"m":{}}', "m objeto: ¿E102?"),
        raw('{"m":"PING;64"} x', "basura tras el objeto: ¿E100?"),
        raw('{"m":"PING;64"}{}', "dos objetos concatenados"),
        raw('{"m":"PING;64"}\n', "salto de línea tras el objeto"),
        raw('  {"m":"PING;64"}', "espacios antes del objeto"),
        raw('{"m":"PING;64"', "objeto truncado: E100"),
        raw("{'m':'PING;64'}", "comillas simples: E100"),
        raw('{"m":"PING;64",}', "coma final: E100"),
        raw('{"m":"PING;64","m":64}', "m duplicada (string luego número): ¿gana la última?"),
        raw('{"m":64,"m":"PING;64"}', "m duplicada (número luego string): ¿gana la última?"),
        raw('{"m":"PING;64","x":NaN}', "NaN en otro campo"),
        b64(b"\xef\xbb\xbf" + PING.encode(), "BOM UTF-8 antes del objeto"),
        b64(b'{"m":"\xff"}', "byte no UTF-8 dentro de m"),
        raw(PING, "Content-Type form con JSON válido", content_type="application/x-www-form-urlencoded"),
        raw("m=PING;64", "cuerpo de formulario: E100", content_type="application/x-www-form-urlencoded"),
        raw(PING, "sin Content-Type explícito útil", content_type="application/octet-stream"),
        raw('{"m":"PING;64"}' + " " * 70000, "cuerpo de ~70 KB (espacios finales): ¿límite de tamaño?"),
    ],
    "05-escapes": [
        raw('{"m":"PING\\u003b64"}', "separador escapado \\u003b equivale a ;"),
        raw('{"m":"\\u0050ING;64"}', "comando con letra escapada"),
        raw('{"m":"PING;6\\u0034"}', "control con dígito escapado"),
        raw('{"m":"PING;64\\n"}', "salto de línea tras el control"),
        raw('{"m":"PING;64\\u0000"}', "NUL tras el control"),
        raw('{"m":"ALTA;\\ud800;' + str(control("ALTA;")) + '"}', "surrogate suelto como nombre"),
        m("ALTA;Ana\tMaria", "tabulador dentro del nombre (no cuenta en el control)"),
        m(" ALTA;Lucia", "espacio antes del comando"),
        m("ALTA ;Lucia", "espacio tras el comando"),
        m("ALTA; Lucia", "espacio antes del nombre"),
    ],
    "06-auth-formas": [
        ping_at("POST", "/msg", "esquema en minúscula: bearer", auth="lower"),
        ping_at("POST", "/msg", "dos espacios tras Bearer", auth="spaces"),
        ping_at("POST", "/msg", "token sin esquema", auth="bare"),
        http("GET", "/health", "health con bearer en minúscula", auth="lower"),
        http("GET", "/health", "health con dos espacios", auth="spaces"),
        http("GET", "/health", "health con token sin esquema", auth="bare"),
    ],
    "07-control-formas": [
        ctl("ALTA;Lucia", " 82", "espacio antes del control (82 canónico)"),
        ctl("ALTA;Lucia", "82 ", "espacio tras el control"),
        ctl("ALTA;Lucia", "+82", "signo + en el control"),
        ctl("ALTA;Lucia", "-82", "signo - en el control"),
        ctl("ALTA;Lucia", "82.0", "control decimal 82.0"),
        ctl("ALTA;Lucia", "8.2e1", "control en notación científica"),
        ctl("ALTA;Lucia", "0x52", "control hexadecimal"),
        ctl("ALTA;Lucia", "٨٢", "dígitos arábigo-índicos"),
        ctl("ALTA;Lucia", "８２", "dígitos de ancho completo"),
        ctl("ALTA;Lucia", "0", "control 0 (fuera del rango 2–98)"),
        ctl("ALTA;Lucia", "00", "control 00"),
        ctl("ALTA;Lucia", "1", "control 1"),
        ctl("ALTA;Lucia", "99", "control 99"),
        ctl("ALTA;Lucia", "100", "control de tres dígitos sin cero inicial"),
        ctl("ALTA;Lucia", "9223372036854775808", "control mayor que int64"),
        ctl("ALTA;Lucia", "082", "padding de tres dígitos (062 dio E201)"),
        ctl("ALTA;Lucia", "82;", "control seguido de segmento vacío"),
        m("ALTA;Lucia", "control canónico: ninguna variante anterior consumió AC (esperado AC-0001)"),
    ],
    "08-montos-deposito": montos_deposito(
        ["0", "-1", "+1", "01", "1.0", "1e3", "-0", "00", "0x10", "١", "1 ",
         "9223372036854775807", "1", "9223372036854775808", "99999999999999999999"]),
    "09-montos-transfer": montos_transfer(
        ["0", "-1", "-100000", "+1", "01", "1.0", "100000.0", "0100000", "1e5", "100000",
         "9223372036854775808"]),
    "10-ids-cuenta": [
        m("ALTA;Lucia", "AC-0001"),
        m("CONSULTA;ac-0001", "ID de cuenta en minúscula"),
        m("CONSULTA;AC-1", "ID de cuenta sin ceros"),
        m("CONSULTA;AC-01", "ID de cuenta con dos dígitos"),
        m("CONSULTA;AC-0001 ", "espacio tras el ID de cuenta"),
        m("CONSULTA;AC0001", "ID de cuenta sin guion"),
        m("CONSULTA;AC-0000", "AC-0000"),
        m("CONSULTA;AC-+001", "signo dentro del número de cuenta"),
        m("DEPOSITO;ac-0001;10", "DEPOSITO a cuenta en minúscula"),
        m("CONSULTA;AC-0001", "saldo de AC-0001 tras los intentos"),
    ],
    "11-ping": [
        ctl("PING", "XX", "PING con control no numérico"),
        raw('{"m":"PING"}', "PING sin control"),
        raw('{"m":"PING;"}', "PING con control vacío: ¿E104?"),
        ctl("PING", "0", "PING control 0"),
        ctl("PING", "100", "PING control 100"),
        ctl("PING", "-1", "PING control -1"),
        ctl("PING", "062", "PING control con padding"),
        ctl("PING;1", "2", "PING con argumento extra"),
        ctl("ping", "64", "ping en minúscula"),
        ctl("Ping", "64", "Ping mezclado"),
        ctl("PING", str(control("PING")), "PING con el control de la fórmula"),
    ],
    "12-comandos-caja": [
        m("alta;Lucia", "comando en minúscula: alta"),
        m("consulta;AC-0001", "consulta en minúscula"),
        m("deposito;AC-0001;50", "deposito en minúscula"),
        m("Transfer;AC-0001;AC-0002;10", "Transfer mezclado (AC-0002 inexistente)"),
        m("anula;OP-0001", "anula en minúscula"),
    ],
    "13-nombre-largo": [
        m("ALTA;Ana Maria", "nombre con espacio interno"),
        m("ALTA;" + "A" * 100, "nombre de 100 caracteres"),
        m("ALTA;" + "B" * 1000, "nombre de 1000 caracteres"),
        m("ALTA;" + "C" * 10000, "nombre de 10000 caracteres"),
        m("ALTA;Zoë", "nombre con acento"),
        m("ALTA;123", "nombre numérico"),
        m("CONSULTA;AC-0006", "la sexta cuenta existe si todas las altas pasaron"),
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
