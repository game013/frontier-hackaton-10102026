# Debrief

Notas para el debrief del reto 2. Por ahora solo tiene la respuesta al incidente; las demás
secciones se agregan cuando cierren sus pasos.

## Respuesta al incidente FR-0153 (versión 2)

**Qué pasó.** El proveedor desplegó la versión 2 sin avisar. Según el ticket, cambiaron tres
comportamientos y el resto quedó igual. Los tests de conformidad corren contra v2.

**Cómo lo detectamos.** Ya teníamos grabada la base v1 completa, con bytes exactos: las
respuestas de A2, A3, A4 y la caracterización de A5. La repetimos entera contra el servicio
nuevo: 58 secuencias y 725 requests, cada una desde reset, sin caché y con los mismos bytes de
request. Comparamos status y bytes paso a paso. De 725 pasos cambiaron 78. Agrupados por causa
salen exactamente tres reglas; el resto son efectos en cascada de esas reglas. Después fijamos
cada regla con sondas mínimas (117 requests) y las repetimos sin caché, con resultado idéntico.
Todo está en `experimentos.jsonl` (IDs 1999–2978, 980 requests): cada request lleva su
hipótesis, y cada delta, una conclusión con su causa y los IDs v1/v2.

**Los tres cambios.**

1. **El saldo se muestra como dinero.** CONSULTA ya no devuelve el entero (`"saldo":40000`):
   devuelve un string con dos decimales, el entero entre 100 (`"saldo":"400.00"`). Así, `5`
   pasa a `"0.05"` y `-800` a `"-8.00"`. Los montos que se envían no cambian de unidad.
   v1 ID 235 → v2 ID 2028.
2. **El límite por transferencia baja a la mitad.** E506 salta con montos > 50000; antes era
   con montos > 100000. 50000 pasa y 50001 falla. v1 ID 237 (100000 → 200) → v2 ID 2030
   (→ 422 E506).
3. **Bloqueo de cuenta tras tres transferencias fallidas.** Tres TRANSFER fallidos seguidos
   desde una cuenta (por límite o por saldo) la bloquean como origen. Sus siguientes TRANSFER
   responden 423 `E510 cuenta bloqueada` con un contador `intentos` que sube. Solo un depósito
   a esa cuenta la libera. CONSULTA y recibir transferencias siguen funcionando. v1 ID 544 →
   v2 ID 2337.

**Revisión de que son exactamente tres.** El replay quedó completo (725/725), sin caché, sin
rate limits de infraestructura y con reset por secuencia. Ningún delta es solo de orden de
claves. Ninguna respuesta sin estado cambió: PING, errores del sobre, validación, NOTAS y HALT.
Las 14 diferencias restantes son cascadas del cambio 2: una transferencia rechazada no consume
número de operación ni mueve saldo, y eso cambia los pasos siguientes.

**Lo que no sabemos con certeza.**

- Que el bloqueo (cambio 3) no existiera en v1 es una inferencia. E510 no aparece en ninguna de
  las 1.381 respuestas v1, pero la base v1 nunca intentó una cuarta transferencia tras tres
  fallidas seguidas. Es el único comportamiento nuevo que aparece y el ticket fija tres cambios.
- La hora exacta del cambio. El ticket dice 15:30, pero el servicio todavía respondía v1 a las
  15:48:49 (ID 1996). Ya respondía v2 a las 16:24:51 (ID 2004).

**Lección.** La etiqueta de versión del log la ponía el cliente según el reloj y el ticket, no
la medía. Por eso el descubrimiento de comandos de A5 (15:43–15:48) quedó etiquetado `v2`
aunque el servicio seguía en v1. Lo detectó el testigo incluido en el replay, y se corrigió en
la especificación (CAM-04) y en el informe A5. Para A7, la versión se
comprueba con un canario (el formato de `saldo` en CONSULTA), no con la hora anunciada.

**En el reemplazo.** Las reglas v2 se activarán con `BEHAVIOR_VERSION=v2` al arrancar (B7),
nunca por reloj. La suite `tests/differential/v2.json` contiene el replay v2 y las sondas como pruebas de
regresión.

Detalle: [informe A6](research/deltas-a6.md) y [especificación §6](specification.md#6-cambios-durante-el-día).
