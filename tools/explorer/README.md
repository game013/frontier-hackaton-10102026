# Cliente instrumentado

`bb.py` es la única vía permitida hacia el servicio original. Usa solo la librería estándar.

## Ejecución con Make

Desde la raíz del repositorio:

```sh
make explore                         # ayuda; no contacta al original
make explore ARGS="budget"           # cuota local; no contacta al original
make explore ARGS="run s-001 tmp/sondas.jsonl --no-cache"
make explore ARGS='conclude 2 "pong confirmado"'
make test-explorer               # pruebas contra un servidor simulado en localhost
```

`make explore` ejecuta `python3 tools/explorer/bb.py` con los argumentos de `ARGS`.
Puedes elegir el intérprete con `PYTHON=/ruta/python3`. La CLI directa es equivalente:

```sh
python3 tools/explorer/bb.py run s-001 tmp/sondas.jsonl --no-cache
python3 tools/explorer/bb.py run --help
```

El archivo JSONL contiene un objeto por paso, en orden. El runner valida el archivo completo,
adquiere el lock del token, envía `POST /__reset` con autenticación válida y ejecuta los pasos.
No incluyas el reset en el archivo. Usa un nombre nuevo de secuencia en cada ejecución.
Por ejemplo, crea localmente `tmp/sondas.jsonl` con:

```jsonl
{"request":{"m":"PING;64"},"hipotesis":"PING responde sin estado"}
{"method":"GET","path":"/nada","hipotesis":"Respuesta de ruta inexistente"}
{"method":"POST","path":"/msg","raw_body_b64":"/wCA","content_type":"application/octet-stream","hipotesis":"Entrada de bytes no UTF-8"}
```

Ese ejemplo ilustra el formato; ejecutarlo sí consume cuota y registra requests al original.
Los valores por defecto son `method: POST`, `path: /msg` y `auth: valid`. Cada paso requiere
`hipotesis`. Los demás campos permitidos son `request` (cuerpo JSON), `raw_body` (texto UTF-8),
`raw_body_b64` (bytes en base64), `content_type`, `confirm` (booleano) y `conclusion`.
Los tres campos de cuerpo son excluyentes. Las variantes de `auth` son `valid`, `none`, `empty`,
`invalid` y `scheme`; nunca pongas el token en el archivo.

`--no-cache` evita toda consulta a caché durante la secuencia: cada paso se envía realmente.
Sin esa opción, los aciertos se indican como `(cache)` y se materializan antes del primer paso
nuevo o al final del runner, dejando evidencia propia de la secuencia. Usa `--no-cache` para
confirmaciones, líneas base y detección de cambios. `confirm: true` fuerza un paso individual.
`--hip` cambia la hipótesis del reset inicial.

Los comandos sueltos `reset`, `msg` y `http` se retiraron: entre procesos separados no podían
conservar la propiedad de la secuencia. La CLI los rechaza antes de enviar. `Client.resume()`
también rechaza retomar una secuencia después de liberar el lock; empieza otra desde reset.

## Uso como librería

```python
from tools.explorer.bb import Client

client = Client()
with client.sequence("s-002", "estado limpio para probar PING", no_cache=True) as sequence:
    sequence.flush()  # envía el reset; el contexto por sí solo no hace requests
    result = sequence.msg("PING;64", "PING sin estado")
    print(result)
```

El lock se conserva durante todo el bloque, incluidas esperas, caché y reenvíos. `call`, `msg`,
`flush` y el envío público exigen el contexto propietario. Una excepción aborta el bloque y la
salida libera el lock; una caída del proceso también lo libera. No retomes una secuencia incierta.
La salida normal materializa automáticamente los aciertos pendientes antes de liberar el lock.
La salida con excepción y `close()` explícito abortan sin reenviar pendientes. Si falla un envío,
el contexto queda abortado aunque captures la excepción dentro del bloque.

## Registro, bytes y coordinación

- Cada intento se registra en `experimentos.jsonl` **antes** de abrir la conexión, incluido el
  reset, con su `hipotesis`. Un corte queda como `outcome: transport_error` sin respuesta.
  Los rate limits se marcan como infraestructura, se reintentan y se excluyen de evidencia y caché.
- Además del contrato se guardan `method`, `path`, `auth` (variante, nunca credencial), `raw`,
  `epoch`, `ts`, `token_tag`, `request_b64` y `response_b64`. Los campos base64 representan los
  bytes del cuerpo enviados y recibidos, sin decodificación UTF-8 intermedia. `request_b64: null`
  significa cuerpo ausente; `""` significa cuerpo vacío. Una respuesta vacía también es `""`.
  `raw` y `response` siguen disponibles para lectura; `raw` puede tener caracteres de reemplazo,
  por lo que para fidelidad de bytes se debe decodificar `response_b64`.
- El token se lee de `BB_TOKEN` en el entorno o `.env`, y nunca se registra como autorización.
  No incluyas secretos en cuerpos, hipótesis, conclusiones o nombres de secuencia.
- Las líneas históricas se conservan intactas; no se inventan bytes para respuestas antiguas.
  La caché solo reutiliza líneas con bytes capturados, la misma etiqueta de token y `BB_EPOCH`.
  Su clave incluye prefijo desde reset, método, ruta, auth, cuerpo y Content-Type efectivo.
  Los pendientes se guardan en `.explore/pending.jsonl`; sirven dentro del contexto activo,
  y no permiten recuperar propiedad después de cerrar o morir.
- El coordinador común vive por defecto en `.explore/` de la **raíz del repo**, incluso usando
  logs en carpetas distintas. `BB_COORD_DIR` o `Client(coord_dir=...)` permiten cambiarlo; todos
  los procesos que compartan token deben usar el mismo directorio en esta máquina.
  `sequence-<etiqueta>.lock` conserva PID, secuencia e inicio, sin el token. No se roba por timeout
  ni se elimina el archivo del lock. Tokens distintos usan locks independientes.
- El lock de secuencia es distinto de los locks breves de log y cuota. La cuota atómica vive en
  `quota.json`, protegida por `quota.lock` en ese mismo coordinador. Ritmo: 8 req/s;
  `BB_DAILY_CAP`: 7.800 por defecto, frente al límite remoto de 8.000 por token y día de Bogotá.
  Al inicializar la cuota del día se cuentan únicamente entradas con el mismo `token_tag`
  y fecha, tanto en el log principal como en el lateral de rate limits, evitando duplicados.
  Las entradas históricas sin etiqueta quedan sin atribuir; pueden representar consumo remoto
  adicional que el contador local no conoce. Las cuotas ya persistidas conservan sus reservas.
  El ritmo se mide al reclamar el turno antes de conectar; una pausa entre turno y socket puede
  acercar envíos. Un rate limit de infraestructura consume presupuesto aunque no sea evidencia.
- El lock es local a esta máquina. En varios hosts usa tokens distintos o centraliza las llamadas.
  Tras el cambio de las 15:30 usa `BB_EPOCH=v2` y repite sin caché.

## Validación y versionado

`make test-explorer` levanta un servidor simulado efímero para verificar bytes, caché, cuota y
exclusión entre procesos. No valida reglas de negocio del original ni utiliza el token real.

`experimentos.jsonl` es un entregable en la raíz y **no** va en `.gitignore`. Tras cada bloque,
con ningún `bb.py` en ejecución, valida el log y commitéalo aparte con
`git add experimentos.jsonl` explícito (nunca `git add .`), en un commit `docs:`.
Los locks, `.explore/` y archivos bajo `tmp/` siguen ignorados.

## A1: calcular y buscar controles

La fórmula y su alcance están en `docs/research/control-a1.md`, con evidencia
repetida y fixtures en `tests/corpus/a1/`. El generador es completamente offline:

```sh
python3 tools/explorer/control.py 'ALTA;Lucia'  # imprime 82; cero requests
```

Recibe el mensaje anterior al último `;control`. No valida aridad, montos ni
sintaxis del campo control; devuelve el decimal canónico que debe enviarse.
PING no sirve como oráculo porque puede omitir integridad.

El escáner sí contacta al original, exclusivamente mediante `bb.py`:

```sh
python3 tools/explorer/control_probe.py 'CONSULTA;AC-0017' \
  --seq a1-nueva --start 0 --stop 98 --log experimentos.jsonl
```

Empieza desde reset, conserva el lock y usa `no_cache=True`. Detiene el barrido
ante la primera respuesta compatible con pasar integridad; un error posterior
como E401 no significa éxito del comando. E201 aborta; auth, PING y respuestas
no reconocidas quedan `unexpected`. Códigos de salida: 0 control compatible,
1 rango agotado sin coincidencia, 2 respuesta mal formada o inesperada.

El rango por defecto 0–98 permite 99 sondas más el reset, antes de reintentos.
Si 0–98 no produce coincidencia y se necesita continuar hasta 99, usar otra secuencia con
`--start 99 --stop 99`. Vigilar cuota antes/después y no lanzar barridos si la
fórmula ya permite predecir la respuesta.

**Worktrees:** pasar `--coord-dir /ruta/checkout-principal/.explore` o definir
`BB_COORD_DIR` para compartir locks y cuota con los demás procesos del token.
Usar explícitamente el log de la raíz de la rama de exploración y conservar todo
su historial. No iniciar un coordinador nuevo para el mismo token.

`make test-explorer` descubre todas las pruebas del cliente, fórmula, escáner y
trazabilidad. Solo usa un servidor simulado local, nunca el original.

## A2: línea base histórica y replay

El snapshot se construye offline a partir de IDs 1–50 y 52–225. Conserva diez secuencias,
incluidos los resets originales, y verifica que los 20 requests de `ejemplos.jsonl` ya estén en
`s001-corpus`. No rellena bytes que faltan en los registros históricos. ID 51, fallo de transporte,
queda fuera. El reset sin autenticación ID 50 se conserva como último paso de `s003-sobre`.

```sh
make corpus ARGS="build"
make corpus ARGS="replay --epoch v1 --prefix a2-v1-10102026"
```

`build` escribe `tests/corpus/v1-historical/` con diez JSONL y `manifest.json`. `replay` valida el
corpus completo antes de conectarse y usa `bb.Client` con `no_cache=True`, reset y lock por cada
secuencia. No repitas un `--prefix`: cada replay debe tener nombres nuevos. La captura resultante y
el informe se guardan en `tests/corpus/v1-replays/<prefix>/`. El replay limita esta instancia del
cliente a `min(tope configurado, cuota usada + max-requests)`; por defecto reserva como máximo 250
requests. Los retries de rate limit cuentan en la cuota real del cliente.

El informe separa comparación de bytes crudos (solo cuando la fuente tiene `response_b64`) y
comparación del contrato: status más JSON con tipos exactos, objetos sin orden significativo y
arrays ordenados; texto se compara literalmente. `request_b64` se envía sin decodificar a texto,
`raw_body` se preserva para casos históricos como el cuerpo `{`, y cada captura nueva conserva
`source_id`. Salida 0 significa sin deltas de contrato, 1 indica deltas y 2 indica replay incompleto.

## A3: batería de estado

`a3_battery.py` genera offline `tests/corpus/a3/*.jsonl`, una secuencia por hipótesis de estado
(consumo de IDs, anulación, alcance del reset, límite E506 y orden de errores). Los controles salen
de `control.py`; `bad()` fuerza E202 a propósito. El runner añade el reset inicial; los resets
intermedios del archivo son parte del experimento.

```sh
python3 tools/explorer/a3_battery.py          # regenera; cero requests
for f in tests/corpus/a3/*.jsonl; do
  python3 tools/explorer/bb.py run "a3-<epoch>-$(basename $f .jsonl)" "$f" --no-cache
done
```

Tras el cambio de versión, repetir con `BB_EPOCH=v2` y nombres nuevos para detectar deltas de
estado. `a3_isolation.py` intentó medir el aislamiento con `TEAM_TOKEN`, pero el original lo
rechaza con 401 E001 (log 618): no se vuelve a ejecutar.
