# Cliente instrumentado

`bb.py` es la única vía permitida hacia el servicio original. Usa solo la librería estándar.

- Registra cada intento en `experimentos.jsonl` **antes** de abrir la conexión, incluido
  `/__reset`, con su `hipotesis`. Un corte de transporte queda como `outcome: transport_error`
  sin respuesta; los rate limits se marcan como infraestructura y se excluyen de la evidencia.
  Además de los campos del contrato agrega `method`, `path`, `auth`, `raw` (cuerpo exacto),
  `epoch` y `ts`.
- Lee el token de `BB_TOKEN` (en el entorno o en `.env`) y nunca lo escribe.
- Coordina entre procesos el ritmo a 8 req/s y `BB_DAILY_CAP` (7.800 por defecto) por token y
  día de Bogotá. La reserva atómica vive en `.explore/quota.json` y solo guarda una etiqueta
  derivada del token, nunca su valor. Las respuestas `X-Frontier-Infra: rate-limit` se descartan,
  se reintentan y consumen presupuesto.
- Caché: la clave incluye el prefijo desde reset, método, ruta, autenticación, cuerpo crudo y el
  `Content-Type` efectivo, siempre dentro de la misma `BB_EPOCH`. Los aciertos pendientes se
  guardan en `.explore/pending.jsonl`; otra ejecución puede restaurarlos y reenviarlos antes del
  primer fallo de caché. `--confirm` o `confirm=True` fuerza la repetición. Tras el cambio de las
  15:30 hay que usar `BB_EPOCH=v2`.
- Versionado: `experimentos.jsonl` es un entregable y vive en la raíz; **no** va en `.gitignore`.
  Tras cada bloque de experimentos, con ningún `bb.py` en ejecución, valida el log y commitéalo
  aparte con `git add experimentos.jsonl` explícito (nunca `git add .`), en un commit `docs:`. El
  `.lock`, el `.tmp` y `.explore/` siguen ignorados.

```sh
python3 tools/explorer/bb.py budget
python3 tools/explorer/bb.py reset s-001
python3 tools/explorer/bb.py msg s-001 "PING;64" --hip "PING responde sin estado"
python3 tools/explorer/bb.py http s-001 GET /nada --hip "404 de ruta inexistente"
python3 tools/explorer/bb.py conclude 2 "pong confirmado"
python3 -m unittest tools/explorer/test_bb.py
```
