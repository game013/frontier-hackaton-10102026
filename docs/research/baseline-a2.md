# A2 · línea base completa de v1

El replay sin caché del 10 de octubre de 2026 repitió las diez secuencias
seleccionadas: **224 respuestas coinciden según el contrato**. Las **174 respuestas
con bytes históricos coinciden también byte a byte**. No se observó ningún delta.

La corrida completa ocurrió entre **15:00:19.672 y 15:00:56.998 de Bogotá**
(20:00:19.672–20:00:56.998 UTC), antes de las 15:30 anunciadas. Esto confirma los
casos de la línea base en ese intervalo; no demuestra vigencia después del cambio.
A6 permanece pendiente y reutiliza estas entradas para comparar la versión vigente.

## Alcance y evidencia

| Conjunto | IDs históricos | IDs A2 | Respuestas |
| --- | --- | --- | --- |
| Ejemplos (`s001-corpus`) | 1–21 | 227–247 | 21 |
| Precedencia (`s002-precedencia`) | 22–33 | 248–259 | 12 |
| Sobre HTTP (`s003-sobre`) | 34–50 | 260–276 | 17 |
| Control, siete secuencias A1 | 52–225 | 277–450 | 174 |
| Total | 1–50, 52–225 | 227–450 | 224 |

Los veinte ejemplos ya forman parte de `s001-corpus`; no se ejecutaron dos veces.
Cada secuencia empezó con un reset autenticado, mantuvo su orden y utilizó el lock
del token durante toda su ejecución. El ID 50 (nuevo ID 276) es una prueba negativa
de reset sin autenticación al final de `s003-sobre`: se conserva como paso ordinario,
con status 401. El cuerpo JSON inválido `{` del ID 45 se repitió íntegro en el ID 271.

El ID 51, sin respuesta, no forma parte del corpus histórico. El primer intento A2
falló al enviar el reset por una restricción de red del sandbox: ID 226,
`outcome: transport_error`, `URLError`. Se conserva en el log y en su informe
incompleto; no se usa como evidencia. Tras autorizar la ejecución fuera del sandbox,
se utilizó otro prefijo y se empezó nuevamente desde reset, sin retomar estado incierto.

## Artefactos y reproducción

- [Corpus y formato](../../tests/corpus/README.md).
- [Manifiesto histórico](../../tests/corpus/v1-historical/manifest.json): diez
  secuencias completas, con 224 IDs y sus limitaciones de bytes.
- [Capturas nuevas](../../tests/corpus/v1-replays/a2-baseline-20261010-retry/corpus.jsonl):
  cada fila enlaza `source_id` histórico con `id` nuevo del log; las nuevas entradas
  y respuestas tienen base64 y los datos HTTP necesarios para reproducirlas.
- [Informe completo](../../tests/corpus/v1-replays/a2-baseline-20261010-retry/report.json):
  224 comparaciones de contrato, 174 de bytes, cero deltas, `incomplete: false`.
- [Informe del intento fallido](../../tests/corpus/v1-replays/a2-baseline-20261010/report.json):
  cero respuestas capturadas, error de transporte, `incomplete: true`.

La construcción es offline. El replay usa exclusivamente `bb.py`, siempre sin caché,
y valida el corpus completo antes de enviar. Los códigos de salida son 0 sin deltas
de contrato, 1 con deltas y 2 ante una ejecución incompleta. Un nuevo replay debe usar
otro prefijo y la etiqueta de versión que corresponda; la etiqueta no detecta cambios.

```sh
make corpus ARGS="build"
make explore ARGS="budget"
make corpus ARGS="replay --epoch v1 --prefix NUEVO_PREFIJO --max-requests 250"
```

La cuota inicial era 225/7.800. A2 reservó **225 solicitudes**: una fallida y 224
con respuesta. La cuota final fue **450/7.800**, dentro del techo aprobado de 250
solicitudes adicionales. Tras el fallo, el reintento redujo su máximo a 249 para
conservar el techo absoluto de 475. No hubo respuestas de rate limit.

## Límites y verificación

Los IDs históricos 1–50 no tenían base64 de cuerpos; se comparó su status y el cuerpo
legible registrado según el contrato, sin inventar bytes. Ahora hay captura exacta de
los cuerpos nuevos de esos mismos casos. Para A1 se repitieron exactamente sus bytes
de entrada y se compararon también los bytes de respuesta.

La auditoría independiente verificó 224 enlaces a evidencia completa, las diez
secuencias desde reset, método/ruta/auth/Content-Type, el cuerpo mal formado y el
reset sin autenticación. El log mantiene IDs consecutivos 1–450 y conclusiones para
todas las respuestas A2. Las pruebas locales pasaron: **57 tests Python** y
`go test ./...`; ninguna prueba local consulta al original.

No se amplió la exploración a A3–A5 ni se implementó B2. Se mantiene la confianza
de las reglas anteriores: repetir los mismos casos no prueba dominios nuevos.
La [especificación](../specification.md) añade los IDs nuevos por fila observada y
la sección 6 registra este replay sin afirmar un cambio que no se observó.
