# Corpus de A1 · control

Siete archivos JSONL, uno por secuencia, con 174 respuestas completas de `v1`
(IDs 52–225 de `experimentos.jsonl`). El intento 51 falló por DNS del sandbox:
queda en la auditoría, sin incorporarlo como respuesta del servicio.

Cada archivo conserva el reset como primer paso. `n` es la posición dentro del
archivo; `id` es el ID original de evidencia. `status` y `response_b64` permiten
comparar status y bytes exactos; `response` permite comparar JSON según el contrato.
Se conservan también los bytes de entrada, request, método, ruta, hipótesis,
secuencia y epoch. El reset corresponde a cuerpo POST vacío (`request_b64: ""`),
no a un cuerpo JSON `null`.

`reserved-bases.json` contiene los nueve textos reservados antes de ajustar la
fórmula. Las secuencias `a1-holdouts-r1` y `a1-holdouts-r2` repiten desde resets
independientes sus controles predichos y un vecino inválido por texto.

Estos archivos son fixtures con resultados esperados, no entradas directas de
`bb.py run`. Para replay mediante el cliente instrumentado, extraer los campos
`method`, `path`, `request`, `hipotesis` de los pasos posteriores al reset a un
JSONL en `tmp/` y ejecutar `run NOMBRE_NUEVO archivo --no-cache`; el runner envía
el reset. No mandar los campos de resultado como parte del cuerpo HTTP.

El corpus solo cubre A1. A2 incorpora ejemplos y secuencias históricas, establece
la línea base completa y revalida sin caché. Aquí no se afirma vigencia tras el
cambio anunciado. `make test-explorer` comprueba offline la fórmula y la relación
entre fixtures y auditoría; no contacta al original.
