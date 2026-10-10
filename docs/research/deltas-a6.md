# A6 · Deltas de la versión 2 (incidente FR-0153)

**Versión observada:** `v2`, 10 de octubre entre 16:24:50 y 16:46:13 de Bogotá. Evidencia:
`experimentos.jsonl`, IDs 1999–2978 (980 requests de 1.000 aprobadas), todos completos, sin
caché y sin rate limit. Herramientas: `tools/explorer/a6_replay.py` (replay y comparación) y
`tools/explorer/a6_probes.py` (sondas). Ticket: [FR-0153](../old-system/incidente-FR-0153.md).

## Resultado

Hay exactamente **3 deltas** de comportamiento. Explican los 78 pasos que cambiaron en el replay
completo y los 8 del canario. Los otros 647 de 725 pasos del replay responden igual byte a byte.

| ID spec | Qué cambió | v1 | v2 | Par mínimo v1 → v2 |
| --- | --- | --- | --- | --- |
| CAM-V2-1 | Formato de `saldo` en CONSULTA | entero: `"saldo":40000` | string con dos decimales, el entero entre 100: `"saldo":"400.00"` | 235 → 2028; 232 → 2025 (`0` → `"0.00"`) |
| CAM-V2-2 | Umbral de E506 en TRANSFER | monto > 100000 | monto > 50000 | 237 → 2030 (100000: 200 → 422 E506) |
| CAM-V2-3 (pendiente de confirmar) | Bloqueo de cuenta tras fallos | no existe (E510 nunca aparece) | tras 3 TRANSFER fallidos seguidos del mismo origen, sus TRANSFER dan 423 E510 | 544 → 2337 (200 → 423 E510) |

## Método

1. **Canario** (1999–2019, 16:24:50): replay de `s001-corpus`, con los ejemplos del enunciado.
   8 de 21 pasos difieren, así que v2 ya estaba activa. Revela CAM-V2-1 y CAM-V2-2.
2. **Replay completo** (2020–2744, 16:25:12–16:27:54): 58 secuencias y 725 pasos desde reset.
   Las secuencias reproducen los bytes exactos de cada request (`request_b64`) y comparan
   status, contrato JSON y bytes.

   | Base | IDs base | IDs v2 | Pasos | Con delta |
   | --- | --- | --- | --- | --- |
   | A2 (replay de `v1-historical`) | 227–450 | 2020–2243 | 224 | 10 |
   | A3 (estado, sin `20-aislamiento`, que usa dos tokens) | 451–670 | 2244–2459 | 216 | 37 |
   | A4 (sobre y números) | 887–1381 | 2460–2713 | 254 | 30 |
   | A5 caracterización NOTAS/HALT (testigo) | 1935–1965 | 2714–2744 | 31 | 1 |

   El canario repite `s001` en 2020–2040 con los mismos bytes.
3. **Agrupación por causa.** En la conclusión del log, cada uno de los 86 pasos con delta (78 del replay + 8 del canario) lleva su causa:

   | Causa | Pasos |
   | --- | --- |
   | CAM-V2-1 directo: mismo valor, distinto formato | 59 |
   | CAM-V2-2 directo: E506 donde v1 aceptaba | 12 |
   | CAM-V2-3 directo: E510 | 1 |
   | Cascada de CAM-V2-2: un TRANSFER rechazado no consume OP ni mueve saldo; cambian los OP siguientes, ANULA da E402 y los saldos posteriores tienen otro valor | 14 |

   Los 7 saldos de la cascada también cambian de formato. No cambió ninguna respuesta sin estado: PING, errores del sobre, E1xx/E2xx/E3xx, E301 con
   sugerencia, NOTAS ni HALT.
4. **Sondas** (2745–2861) para fijar cada regla, y su **repetición sin caché** (2862–2978):
   117/117 respuestas iguales en status y bytes. En la tabla, «r» es la repetición: ID +117.

## CAM-V2-1 · `saldo` como texto con dos decimales

- CONSULTA responde `{"cuenta_id":"AC-0001","saldo":"<entero/100 con dos decimales>"}`.
  El saldo interno sigue siendo el mismo entero: los montos de DEPOSITO/TRANSFER no cambian
  de unidad. Ejemplos del replay: `0` → `"0.00"`, `1` → `"0.01"`, `7` → `"0.07"`, `501` →
  `"5.01"`, `-800` → `"-8.00"`, `101119999` → `"1011199.99"`, `3247483647` →
  `"32474836.47"`.
- Sonda 01 (2746–2753, r 2863–2870): `0` → `"0.00"` (2747), `5` → `"0.05"` (2749),
  `12345` → `"123.45"` (2751).
- Solo cambia la clave `saldo` de CONSULTA. Las demás respuestas con estado, como
  `{"status":"recieved",…}`, ANULA y los errores, no cambian de forma.

## CAM-V2-2 · Límite de TRANSFER en 50000

- `TRANSFER` con monto > 50000 → 422 `{"error":"E506","mensaje":"límite excedido"}`. Mismo
  cuerpo y misma posición en el orden de errores que en v1 (E303 → E304 → E401 → E506 → E507).
  Solo cambia el umbral.
- Sonda 02 (2755–2770): 50000 → 200 (2758); 60000, 75000, 90000 y 99999 → E506
  (2761, 2764, 2767, 2770). Sonda 06 (2835–2844): 50001, 55000 y 59999 → E506 (2838, 2841,
  2844). Repetición: 2872–2887 y 2952–2961.
- En v1, 100000 pasaba y 100001 fallaba (ERR-506). El replay muestra E506 en 100000
  (2030, 2334–2336, 2365–2366, 2368, 2376–2378, 2623).
- Sigue sin aplicar a DEPOSITO: el replay acepta depósitos de hasta 9999999999 sin cambios.
  Tampoco aplica a ANULA.

## CAM-V2-3 · Bloqueo E510 tras tres TRANSFER fallidos

Regla medida:

- Cada cuenta lleva un contador de **TRANSFER fallidos seguidos como origen**. Cuentan E506 y
  E507 (sondas 03/04). Un TRANSFER exitoso del origen pone el contador a cero (2793–2797:
  E506, E506, 200, E506, 200).
- Con el contador en 3, todo TRANSFER posterior desde esa cuenta →
  423 `{"error":"E510","mensaje":"cuenta bloqueada","intentos":N}`. Esto ocurre aunque el monto
  sea válido (2779, 1000) y aunque supere el límite (2337; 2805, el cuarto TRANSFER de AC-0002 tras
  tres E506). El tercer fallo todavía responde con su propio error (2778, 2800). `N` empieza en 1
  y sube con cada TRANSFER bloqueado: 1→4 en 2818–2821.
- **Solo un DEPOSITO a la cuenta la libera.** Tras el depósito, el TRANSFER siguiente vuelve a
  evaluarse normalmente (2825–2827). Un depósito entre fallos también reinicia el contador antes
  del bloqueo: E506, E506, DEPOSITO, E506, 200 (2857–2861). No liberan: más intentos (2818–2821),
  un TRANSFER entrante (2854–2856) ni ANULA sobre un depósito de la cuenta (2831–2833).
- El bloqueo es por cuenta y solo como origen. Una cuenta bloqueada responde a CONSULTA (2338)
  y recibe TRANSFER sin desbloquearse (2855–2856). También acepta DEPOSITO, que la libera
  (2781, 2826). Las demás cuentas no se ven afectadas: con AC-0003 bloqueada (2801), AC-0002
  necesita sus propios tres fallos para bloquearse (2802–2805).
- E510 no consume OP: el depósito siguiente recibe el número correlativo (2826 → OP-0005).
  `POST /__reset` borra el bloqueo, porque cada secuencia empieza desbloqueada.

**Confianza:** la regla v2 está confirmada y repetida. Como delta queda **pendiente de
confirmar** (decisión del usuario tras la revisión adversaria): las pruebas de conformidad
contra v2 lo dirán. Que no existiera en v1 es **inferido**: E510 no aparece en ninguna de las 1.381 respuestas v1, ni en el enunciado ni en
los ejemplos. La base v1 nunca envió un cuarto TRANSFER tras tres fallidos seguidos del mismo
origen, así que v1 no lo descarta directamente. El único caso del replay (544 → 2337) aparece
porque CAM-V2-2 convirtió en fallos tres transferencias que en v1 pasaban. Es el único
comportamiento nuevo frente a los 725 pasos, y el ticket fija tres cambios.

Sin medir (B7 decide y lo anota como supuesto): si `intentos` vuelve a 1 tras desbloquear y
volver a bloquear; si E401 o E304 en TRANSFER cuentan como fallo; si la regla es «≥ 3» o
«= 3» tras desbloquear; y el orden de E510 frente a E303, E304, E401 y E507. **A7 los midió**
(IDs 2979–3128): ver el [informe A7](replay-a7.md#sondas-nuevas-de-cam-v2-3). Frente a E507
el orden ya se veía en 2801.

## Cuándo cambió y qué pasa con A5

- Última respuesta v1 demostrable: ID 1996, a las 15:48:49 de Bogotá. A5 (1382–1996) devolvía
  `saldo` entero (1385 `0`, 1956 `500`). En v2, esos mismos pasos dan `"0.00"`/`"5.00"`
  (testigo: 1956 → 2735, la única diferencia de A5).
- Primera respuesta v2 demostrable: ID 2004, a las 16:24:51.
- Los IDs 1997–1998 (16:04, `POST /internal/export-docs` → 404) no distinguen versiones. El
  instante del cambio queda entre 15:48:49 y 16:24:51. El ticket dice «Abierto 15:30» y el
  usuario lo recibió a las 15:44, pero A5 todavía respondía como v1.
- **A5 corrió contra v1**, aunque el log lo etiqueta `epoch: v2`. La etiqueta identifica la
  corrida, no la versión (README del corpus). `NOTAS`, `HALT`/E520 y las sugerencias de E301
  ya existían en v1 y no son deltas. El replay A6 los revalida en v2 con los mismos bytes
  (2714–2744).

## Revisión del conteo (¿por qué exactamente 3?)

- **Replay completo:** 725/725 pasos con respuesta; ningún `transport_error` ni rate limit.
- **Caché:** `--no-cache` en todo; cada paso se envió.
- **Estado:** cada secuencia empieza con reset y repite el orden original.
- **Serialización:** se compararon bytes. Ningún delta es solo de orden de claves o de
  espacios: todos cambian el contrato.
- **Cascadas:** los 14 pasos de cascada se explican, paso a paso, porque CAM-V2-2 rechazó una
  operación anterior de la misma secuencia.
- **Fuera de la base:** comandos no caracterizados (el resto del barrido A5) y bordes no
  cubiertos por la base pueden esconder cambios. Ninguna respuesta sin estado cambió, y el
  ticket fija tres cambios.

## Para el reemplazo (B7)

Con `BEHAVIOR_VERSION=v2`:

1. CONSULTA serializa el saldo como string `fmt("%d.%02d")` con signo, el entero entre 100.
   Cuidado con negativos entre −1 y −99: v2 muestra `-8.00` para −800, pero no se observó
   ningún saldo entre −99 y −1. Escribir `-0.50` es un supuesto.
2. E506 si el monto de TRANSFER > 50000, en la misma posición del orden.
3. Contador por cuenta de TRANSFER fallidos seguidos (E506/E507) como origen. Con el contador
   en 3, cualquier TRANSFER de esa cuenta da 423 E510 con `intentos` creciente. Gana sobre
   E506 (2337, 2805); frente a E303, E304, E401 y E507 no se midió. Un DEPOSITO a la cuenta
   pone a cero el contador y el bloqueo; un TRANSFER exitoso de la cuenta pone a cero el
   contador. El reset lo borra todo.

La suite `tests/differential/v2.json` contiene todo lo anterior. `pending-v2.txt` lista los
pasos que faltan.
