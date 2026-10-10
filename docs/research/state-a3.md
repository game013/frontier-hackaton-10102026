# A3 · Estado del servicio (`v1`)

**Ventana:** 10 de octubre, 15:11–15:13 de Bogotá, antes del cambio anunciado de las 15:30.
**Log:** IDs 451–886. Primera pasada 451–670; repetición completa sin caché 671–886
(216/216 iguales en status y bytes). Consumo: 436 requests de un techo de 800.
**Corpus:** `tests/corpus/a3/` (25 secuencias, generadas por `tools/explorer/a3_battery.py`).
A6 debe repetirlo tras el cambio con `BB_EPOCH=v2`.

## Hallazgos

| Tema | Resultado | Spec |
| --- | --- | --- |
| Consumo de IDs | AC y OP son contadores separados; solo ALTA, DEPOSITO y TRANSFER exitosos consumen. Ningún error, ANULA, PING ni CONSULTA consume. | MEM-01 |
| Anulación | Revierte depósitos y transferencias sin comprobar saldo ni límite; los saldos pueden quedar negativos. | CMD-ANULA, MEM-04, RIE-01 |
| ANULA inexistente | Coincidencia exacta del texto `OP-NNNN`; cualquier otra forma (incluido `AC-…`) → E402. | ERR-402 |
| Alcance del reset | Borra todo y reinicia los contadores; solo `POST /__reset` autenticado; ignora el cuerpo. | MEM-02, ENT-09 |
| E506 | Por operación, solo en TRANSFER: monto > 100000. No acumulado, no por cuenta. Gana sobre E507. | ERR-506 |
| Errores nuevos | E104 «segmento vacío» (antes que cualquier otro error de mensaje) y E304 «origen y destino iguales». | INT-09, ERR-104, ERR-304, ERR-ORD |
| Aislamiento por token | No medible: el original rechaza TEAM_TOKEN con 401 E001 (log 618). Queda como supuesto del contrato. | ENT-08, MEM-06 |

## Pendiente para otros pasos

- Comando vacío (`;…`), monto 0 o negativo y otros formatos numéricos: A4.
- Orden de E104 frente a E100/E102 y auth: A4.
- Vigencia tras el cambio: A6 repite este corpus.
