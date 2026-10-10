# Corpus del servicio original

El corpus conserva el orden de cada secuencia y su reset inicial. No se pueden
mezclar o deduplicar pasos con estado aunque sus requests coincidan.

- `a1/`: siete secuencias originales de A1, con bytes capturados y evidencia
  IDs 52–225. El intento 51 no recibió respuesta y queda solo en la auditoría.
- `v1-historical/`: snapshot completo de los IDs 1–50 y 52–225, diez secuencias
  y 224 respuestas. `source_id` referencia `experimentos.jsonl`; `n` es la
  posición en la secuencia. Los veinte ejemplos ya están en `s001-corpus`.
- `v1-replays/PREFIJO/`: `corpus.jsonl` contiene las nuevas respuestas del replay,
  agrupables por `seq`, con el reset como primer paso de cada grupo. `id` apunta
  a la nueva evidencia; `source_id` a la respuesta histórica comparada.
  `request_display` permite leer la entrada histórica; `request_b64` describe
  los bytes realmente enviados. `report.json` registra cobertura y diferencias.

Los IDs 1–50 carecen de bytes históricos: no se fabrican `request_b64` ni
`response_b64`. El replay captura los bytes nuevos, compara su contrato con el
texto histórico y deja esa limitación indicada en el informe. Para A1 también
compara los bytes exactos. La comparación del contrato ignora el orden de claves
JSON; conserva el orden de arrays, tipos y contenido de strings. Para cuerpos
que no sean JSON, conserva la comparación exacta de bytes cuando están disponibles.

El reset sin autenticación del ID 50 es una prueba negativa al final de
`s003-sobre`, no el inicio de otra secuencia.

Construcción offline y replay instrumentado:

```sh
make corpus ARGS="build"
make explore ARGS="budget"
make corpus ARGS="replay --epoch v1 --prefix PREFIJO_UNICO --max-requests 250"
```

El replay siempre usa `bb.py` y no consulta caché. Cada prefijo debe ser nuevo.
Salida 0: replay completo sin deltas de contrato; 1: completo con deltas;
2: incompleto. Revisar también `raw_deltas`: pueden mostrar diferencias de
serialización que el evaluador acepta. Una ejecución incompleta no confirma
ninguna línea base completa. Una etiqueta `epoch` identifica la corrida y no
demuestra por sí sola la versión del servicio.

No ejecutar el replay del corpus como parte de las pruebas locales: consume cuota
y modifica el estado del token. Los tests del reemplazo deben usar estas respuestas
grabadas sin contactar al original.
