# Arnés diferencial

Reproduce secuencias grabadas del original contra el reemplazo, sobre un
`httptest.Server` nuevo por secuencia, sin red externa ni llamadas al original.
Por cada paso compara **status y bytes exactos** del cuerpo. Los headers, `X-Req`
y `ts` no se comparan. Si los bytes difieren, el mensaje también dice si el JSON
es equivalente según el criterio del evaluador (orden de claves libre, arrays en
orden, números por su texto). Así se ve si la diferencia es solo de serialización.

```sh
make differential                          # BEHAVIOR_VERSION=v1 por defecto
make differential BEHAVIOR_VERSION=v2      # skip si no existe v2.json
go test ./tests/differential -run 'TestCorpus/a3-v1r-17' -v
```

`go test ./...` (y `make test-go`) lo incluye.

## Archivos

- `<version>.json`: suite de la versión. Cada fuente es un JSONL de registros de
  evidencia de `bb.py` (`experimentos.jsonl` o el `corpus.jsonl` de un replay) y
  una lista de patrones `path.Match` sobre `seq`. Rutas relativas a la raíz.
- `pending-<version>.txt`: secuencias que el reemplazo todavía no reproduce, una
  por línea (`#` comenta). Se ejecutan y su primer desacuerdo sale con `-v`, sin
  fallar. Si una ya coincide en todos sus pasos, o si la lista nombra una que no
  está en la suite, el test falla: hay que quitarla de la lista.
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

Para añadir corpus nuevo (A4, A5, `v2` de A6), agregar una fuente o un patrón a
la suite y las secuencias que aún no pasen a `pending-<version>.txt`.
