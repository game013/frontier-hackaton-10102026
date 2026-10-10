# Arnés diferencial

Reproduce secuencias grabadas del original contra el reemplazo, sobre un
`httptest.Server` y un archivo SQLite temporal nuevos por secuencia, sin red externa
ni llamadas al original. El servidor se detiene antes de cerrar la base. Esta suite
usa siempre SQLite, independientemente de `STORAGE` del entorno.
Por cada paso compara **status y bytes exactos** del cuerpo. Los headers, `X-Req`
y `ts` no se comparan. Si los bytes difieren, el mensaje también dice si el JSON
es equivalente según el criterio del evaluador (orden de claves libre, arrays en
orden, números por su texto). Así se ve si la diferencia es solo de serialización.

```sh
make differential                          # BEHAVIOR_VERSION=v1 por defecto
make differential BEHAVIOR_VERSION=v2      # falla si v2 no está en config.Versions o no tiene v2.json
go test ./tests/differential -run 'TestCorpus/a3-v1r-17' -v
go test ./tests/differential -run TestCorpus -update-pending   # regenera pending-<version>.txt
```

Cada paso tiene 5 segundos, cuerpo incluido, igual que en la evaluación. Si se
pasa, es un fallo de la secuencia.

`go test ./...` (y `make test-go`) lo incluye.

## Archivos

- `<version>.json`: suite de la versión. Cada fuente es un JSONL de registros de
  evidencia de `bb.py` (`experimentos.jsonl` o el `corpus.jsonl` de un replay) y
  una lista de patrones `path.Match` sobre `seq`. Rutas relativas a la raíz.
- `pending-<version>.txt`: por secuencia, los pasos que el reemplazo todavía no
  reproduce: `<seq> <pasos>`, con pasos como `1-6,8` (posición en la secuencia;
  0 es el reset; `#` comenta). Funciona como trinquete. Falla si difiere un paso
  fuera de la lista (regresión), si un paso listado ya coincide o si la lista
  nombra una secuencia que no está en la suite. Tras avanzar en B3/B4, regenerar
  con `-update-pending` y revisar el diff: solo deben desaparecer pasos.
  `-update-pending` no escribe si se combinó con un filtro `-run` o si alguna
  secuencia falló, para no borrar pendientes de lo que no se comparó.
- `testdata/`: evidencia sintética para las pruebas del propio arnés.

## Reglas sobre la evidencia

- Los registros se agrupan por `seq` en orden de archivo. Las respuestas de
  infraestructura (`rate-limit`) se descartan, porque `bb.py` reintenta.
- Una secuencia es inválida, y el test falla, si algún intento quedó sin
  respuesta (`transport_error`, `pending`), si un registro no tiene
  `request_b64`/`response_b64` (IDs 1–50 históricos) o si no empieza con
  `POST /__reset` autenticado.
- El request se rearma como lo envía `bb.py`: cuerpo de `request_b64` (`null` =
  sin cuerpo), `Content-Type` del registro o `application/json`, y `Authorization`
  según la etiqueta `valid`/`none`/`empty`/`invalid`/`scheme`. Aquí `valid` usa el
  token de prueba del reemplazo.

## Suite `v1`

- Replay sin caché de A2 (`a2-baseline-20261010-retry`, IDs 227–450): diez
  secuencias, que incluyen los ejemplos, s001–s003 y A1.
- Repetición sin caché de A3 (`a3-v1r-*`, IDs 671–886). La primera corrida
  (`a3-v1-*`) dio los mismos bytes y no se duplica. `a3-v1-20-aislamiento-*`
  usa dos tokens y queda fuera.
- Repetición sin caché de A4 (`a4r-v1-*`, secuencias 01–18) y pasada única de
  19–20 (`a4-v1-19-*`, `a4-v1-20-*`), que no se repitieron. La primera corrida
  de 01–18 (`a4-v1-01`…`18`) dio los mismos bytes y no se duplica.

## Suite `v2`

Objetivo de conformidad (incidente FR-0153). Todo corrió contra `v2` en A6:

- Replay sin caché de toda la base v1 (`tests/corpus/a6/a6-v2/corpus.jsonl`,
  IDs 2020–2744): A2, A3 (sin `20-aislamiento`), A4 y la caracterización A5 de
  NOTAS/HALT. 58 secuencias, 725 pasos.
- Repetición sin caché de las sondas de aislamiento (`a6-v2r-sonda-*`,
  IDs 2862–2978). La primera corrida (`a6-v2-sonda-*`) dio los mismos bytes.
- Repetición sin caché de las sondas A7 del bloqueo E510 (`a7-v2r-sonda-*`,
  IDs 3054–3128): fallos que cuentan, orden de E510 e `intentos` tras rebloqueo.
  La primera corrida (`a7-v2-sonda-01-e304-racha`…`07-deposito-fallido`, IDs
  2979–3053) dio los mismos bytes. El replay final A7 (IDs 3129–3970) repitió
  byte a byte las fuentes anteriores y no se añade.

`pending-v2.txt` se generó con `v2` añadida a `config.Versions` solo en local:
hoy el reemplazo responde como v1 (B4, sin pendientes en `v1`), así que lista
exactamente los pasos de los tres deltas (CAM-V2-1…3) y sus cascadas: en el
replay son los mismos 78 pasos que encontró A6, más las sondas. Añadir
`v2` a `config.Versions` le toca a B7: cambia la versión por defecto. Hasta entonces,
`make differential BEHAVIOR_VERSION=v2` falla con «versión desconocida».

Para añadir corpus nuevo, agregar una fuente o un patrón a la suite y regenerar
`pending-<version>.txt` con `-update-pending`.
