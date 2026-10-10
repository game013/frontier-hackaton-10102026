# A7 · Replay final sin caché de la versión vigente (v2)

**Versión observada:** `v2`, 10 de octubre entre 17:20:27 y 17:24:59 de Bogotá. Evidencia:
`experimentos.jsonl`, IDs 2979–3970 (992 requests de 1.000 aprobadas), todos completos, sin
caché y sin rate limit. Herramientas: `tools/explorer/a7_replay.py` (replay sobre la evidencia
v2 de A6, con la mecánica de `a6_replay.py`) y `tools/explorer/a7_probes.py` (sondas).
Captura y reporte: `tests/corpus/a7/a7-v2/`; sondas: `tests/corpus/a7/probes/`.

## Resultado

- **El servicio sigue en la misma v2 que midió A6.** Las 842 respuestas del replay final
  coinciden en status y bytes exactos con su evidencia A6: 0 deltas de bytes y 0 de contrato.
  No hay otro cambio de versión entre las 16:46 (fin de A6) y las 17:24.
- **CAM-V2-3 queda acotado en los puntos que A6 dejó sin medir.** Las sondas nuevas (75
  requests) se repitieron sin caché (75) con resultado idéntico: 75/75 iguales.

| Bloque | IDs | Requests | Comparación |
| --- | --- | --- | --- |
| Sondas nuevas de CAM-V2-3 | 2979–3053 | 75 | Primera pasada |
| Repetición de las sondas | 3054–3128 | 75 | 75/75 iguales a ID − 75 |
| Replay de A6 (base v1 contra v2) | 3129–3853 | 725 | 725/725 iguales a 2020–2744 |
| Replay de las sondas A6 | 3854–3970 | 117 | 117/117 iguales a 2745–2861 |

Nombres en el log: el replay es `a7-v2-<fuente A6 sin el prefijo a6-v2->`. Las sondas A6
repetidas se llaman `a7-v2-sonda-01-saldo-formato`…`07-desbloqueo-entrante`. Las sondas nuevas
son `a7-v2-sonda-01-e304-racha`…`07-deposito-fallido`, y su repetición es `a7-v2r-sonda-*`.
Las distingue el nombre completo o el rango de IDs.

## Replay final

`a7_replay.py` toma como fuentes las 58 secuencias de `tests/corpus/a6/a6-v2/corpus.jsonl`
y las 7 sondas `a6-v2-sonda-*` del log: 65 secuencias y 842 requests, IDs 2020–2861. No usa
la repetición `a6-v2r-*`, que tiene los mismos bytes. Cada secuencia se reenvía desde reset
con los bytes exactos del request (`request_b64`) y `no_cache=True`. Cada paso lleva la
hipótesis «igual que base ID N (v2 vigente; se espera sin delta)», y su conclusión cita el
ID A6 comparado. `report.json`: `request_count` 842, `raw_deltas` 0, `contract_deltas` 0,
`incomplete` false. El replay corrió en el mismo orden que la evidencia A6, así que cada ID
A7 es el ID A6 + 1109. Por ejemplo, 2028 → 3137 (`"saldo":"400.00"`), 2030 → 3139 (E506 con
100000), 2337 → 3446 (E510) y 2801 → 3910.

Esto repite en una sola pasada los tres deltas de A6 (CAM-V2-1…3) y todo lo que no cambió:
el sobre, la integridad, los comandos, NOTAS/HALT y las sondas de saldo, umbral y bloqueo.

## Sondas nuevas de CAM-V2-3

Las siete empiezan igual: reset, `ALTA Lucia` (AC-0001), `ALTA Mateo` (AC-0002) y un
depósito de 1000000 a AC-0001. Un E506 es `TRANSFER AC-0001→AC-0002` de 60000 (> 50000, con
fondos). «r» indica la repetición: ID + 75.

| Pregunta (A6: sin medir) | Sonda | Respuestas | Conclusión |
| --- | --- | --- | --- |
| ¿E304 cuenta como fallo o reinicia la racha? | 01: E506, E506, E304, E506, válido | 2985 E304; 2986 E506; 2987 E510 `intentos` 1 | Neutro: ni cuenta ni reinicia |
| ¿E401 (destino inexistente)? | 02: igual con `AC-0099` | 2994 E401; 2995 E506; 2996 E510 | Neutro |
| ¿E303 (monto `007`)? | 03: igual con `007` | 3003 E303; 3004 E506; 3005 E510 | Neutro |
| ¿Otros comandos en mitad de la racha? | 04: E506, E506, CONSULTA, ALTA, DEPOSITO a AC-0002, E506, válido | 3012 `"10000.00"`; 3013 AC-0003; 3014 OP-0002; 3015 E506; 3016 E510 | CONSULTA, ALTA y DEPOSITO a otra cuenta no rompen la racha |
| Orden de E510 frente a E304, E401 y E303 | 05: bloqueada, luego E304, E401, E303 y válido | 3024 E304; 3025 E401; 3026 E303; 3027 E510 `intentos` 1 | Los tres se evalúan antes que E510 y no suben `intentos` |
| ¿`intentos` vuelve a 1 al rebloquear? ¿El DEPOSITO pone la racha a cero? | 06: bloqueo, 2 × E510, DEPOSITO, E506, E506, válido, 3 × E506, válido | 3035–3036 E510 1, 2; 3037 OP-0002; 3038–3039 E506; 3040 200 OP-0003; 3041–3043 E506; 3044 E510 `intentos` 1 | El DEPOSITO libera y pone la racha a cero: hacen falta 3 fallos nuevos. `intentos` vuelve a empezar en 1 |
| ¿Un DEPOSITO fallido libera? | 07: bloqueada, `DEPOSITO;AC-0001;007`, válido | 3052 E303; 3053 E510 `intentos` 1 | No: solo un DEPOSITO exitoso libera |

Repetición: 3054–3128, 75/75 iguales en status y bytes.

Frente a E507 el orden ya estaba medido en A6: con AC-0003 sin fondos y bloqueada por tres
E507, el cuarto TRANSFER de 100 responde E510 (2801; r 2918). Frente a E506 también (2805).

### Regla v2 completa del bloqueo

- Contador por cuenta de TRANSFER fallidos seguidos como origen. **Solo suman E506 y E507.**
  E303, E304 y E401 son neutros: ni suman ni reinician. Tampoco reinician CONSULTA, ALTA,
  DEPOSITO a otra cuenta, TRANSFER entrante (A6 2855) ni ANULA (A6 2832).
- Un TRANSFER exitoso del origen pone el contador a cero (A6 2795). Un DEPOSITO exitoso a la
  cuenta pone a cero el contador y quita el bloqueo (A6 2826, 2859; A7 3037–3040). Un DEPOSITO
  con error no hace nada (3052–3053).
- Con el contador en 3, TRANSFER desde la cuenta → 423
  `{"error":"E510","mensaje":"cuenta bloqueada","intentos":N}`. `N` cuenta las respuestas
  E510 desde el último bloqueo y empieza en 1. Un nuevo bloqueo vuelve a empezar en 1 (3044).
- Orden en TRANSFER v2: E303 → E304 → E401 → **E510** → E506 → E507 (3024–3027, A6 2801,
  2805). E510 no consume OP.

### Sin medir

- E401 por **origen** inexistente sobre una cuenta bloqueada no es posible: una cuenta
  bloqueada existe. E401 de destino sí está medido (3025).
- E202 y E302 sobre una cuenta bloqueada: la integridad y la aridad se evalúan antes del
  motor (ERR-ORD), así que se suponen anteriores a E510 y neutros. No se sondeó.
- Si `intentos` tiene tope o se reinicia con el tiempo: nunca superó 4 (A6 2821).

## Conclusión para B7

Las reglas del [informe A6](deltas-a6.md#para-el-reemplazo-b7) siguen vigentes sin cambios.
A7 añade el orden E303 → E304 → E401 → E510 → E506 → E507, los errores que son neutros para el
contador, que el DEPOSITO fallido no libera y que `intentos` vuelve a empezar en 1. La suite
`tests/differential/v2.json` incluye la repetición de las sondas (`a7-v2r-sonda-*`), y sus
pasos pendientes están en `pending-v2.txt`. El replay final no se añade porque repite byte a
byte las fuentes que ya están en la suite.
