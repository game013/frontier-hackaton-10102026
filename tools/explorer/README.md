# Cliente instrumentado

`bb.py` es la única vía permitida hacia el servicio original. Usa solo la librería estándar.

- Registra cada request en `experimentos.jsonl`, incluido `/__reset`, con su `hipotesis`.
  Además de los campos del contrato agrega `method`, `path`, `auth`, `raw` (cuerpo exacto),
  `epoch` y `ts`.
- Lee el token de `BB_TOKEN` (en el entorno o en `.env`) y nunca lo escribe.
- Limita el ritmo a 8 req/s y para al llegar a `BB_DAILY_CAP`, por defecto 7.800, contado por
  día de Bogotá. Las respuestas con `X-Frontier-Infra: rate-limit` se descartan, se reintentan y
  se cuentan en `.explore/rate_limited.jsonl`.
- Caché: si el mismo prefijo desde el reset y el mismo paso ya se observaron en la misma
  `BB_EPOCH`, devuelve el resultado sin llamar. Ante un fallo de caché reenvía primero el prefijo
  pendiente. `--confirm` o `confirm=True` fuerza la repetición. Tras el cambio de las 15:30 hay
  que usar `BB_EPOCH=v2`.

```sh
python3 tools/explorer/bb.py budget
python3 tools/explorer/bb.py reset s-001
python3 tools/explorer/bb.py msg s-001 "PING;64" --hip "PING responde sin estado"
python3 tools/explorer/bb.py http s-001 GET /nada --hip "404 de ruta inexistente"
python3 tools/explorer/bb.py conclude 2 "pong confirmado"
python3 -m unittest tools/explorer/test_bb.py
```
