# A4 · Sobre HTTP y números (`v1`)

**Ventana:** 10 de octubre, 15:25:11–15:28:23 de Bogotá, antes del cambio anunciado de las 15:30.
**IDs:** 887–1381 (495 requests: techo aprobado de 500). Cero fallos de transporte y cero rate limits.
**Corpus:** `tests/corpus/a4/` (generador `tools/explorer/a4_battery.py`, sin requests).

| Bloque | Secuencias | Primera pasada | Repetición sin caché | Deltas |
| --- | --- | --- | --- | --- |
| Matriz | 01–13 | 887–1090 | 1091–1294 (ID + 204) | 0 / 204 |
| Seguimiento | 14–18 | 1295–1331 | 1340–1376 (ID + 45) | 0 / 37 |
| Tope fino de montos | 19–20 | 1332–1339, 1377–1381 | sin repetir (cuota) | — |

Las secuencias 19 y 20 tienen una sola pasada: lo que solo apoyan ellas queda como **probable**.

## Hallazgos

### Precedencia del sobre

Orden medido: **método+ruta → auth → tamaño → JSON → `m` → E103 → E104 → E201 → E202 → E301/E302**.

- Una ruta o método desconocido da 404 E404 **aunque falte la auth** o sea inválida: `POST`/`GET /no-existe`
  sin auth (888, 889), `GET /msg` con token inválido (892), `OPTIONS`/`HEAD /msg` sin auth (925, 926),
  `POST /health`, `GET /__reset` y `PUT /msg` sin auth (1329–1331). Esto contradice el supuesto ENT-05 de B1.
- Con ruta válida, auth antes que JSON: `{` o `{}` sin auth o con auth vacía → 401 (890, 891, 896).
- Auth antes que tamaño: cuerpo de 9 KB sin auth → 401 (1300). Ruta antes que tamaño: a `/nada` → 404 (1301).
- Ruta antes que JSON: `{` a `/no-existe` con auth → 404 (893).

### Rutas y métodos

- Comparación exacta sobre la ruta cruda; la query se ignora: `/msg?x=1` y `/msg?` → pong (901, 902), `/health?x=1` → 200 (909).
- 404 E404: `/%6dsg`, `/msg/`, `/MSG`, `/./msg`, `/x/../msg`, `/msg%2F`, `/msg;x`, `/health/`, `/HEALTH`, `//health`, `/`, `/%68ealth` (899–900, 903–908, 910–913).
- `HEAD` en cualquier ruta (incluidas `/health` y `/__reset`, con o sin auth) → 404 con **cuerpo vacío** y sin `X-Req` (campo `x_req` nulo en el log) (916, 921, 923, 926, 927).
- `OPTIONS`, `PUT`, `DELETE`, `PATCH` → 404 E404 (917–920, 922, 924, 925, 928). Ninguno de `HEAD`/`OPTIONS`/`DELETE /__reset` resetea: tras la ALTA inicial (915) la siguiente da AC-0002 (930).

### Auth

Solo `Bearer <token>` exacto: `bearer <token>`, `Bearer  <token>` (dos espacios) y el token sin esquema dan 401, en `/msg` y en `/health` (971–976).

### Cuerpo

- Tope de **8192 bytes**: 8192 pasa (1298), 8193 → 413 `{"error":"E101","mensaje":"cuerpo demasiado grande"}` (1299); también 70 KB (958) y una ALTA con nombre de 10000 caracteres (1087).
- E100: cuerpo vacío (932), basura tras el objeto (943), dos objetos (944), truncado (947), comillas simples (948), coma final (949), `NaN` (952), BOM UTF-8 (953), formulario (956), salto de línea literal dentro del string (1306).
- Se aceptan espacios antes del objeto y un salto de línea después (945, 946).
- E102: `[]`, `null`, string, número (933–936), `m` nula (937), clave `M` (938), `m` array/booleana/objeto (940–942).
- `m` duplicada: gana la **última** aparición (950 → E102; 951 → pong).
- Content-Type se ignora: formulario con JSON y `application/octet-stream` → pong (955, 957).
- Los escapes JSON se decodifican antes de partir `m`: `;` actúa como separador (960–962). Un byte `\xff` dentro de `m` da E103 (954): el texto resultante no tiene `;`.

### Errores nuevos

- **E103** 400 `{"error":"E103","mensaje":"falta control"}`: `m` sin ningún `;`, incluida `m` vacía: `""` (939), `PING` (1067), `ALTA` (1303), `ZZZ` (1304, antes que E301).
- **E101** (arriba).
- **E301 con `sugerencia`**: `{"error":"E301","mensaje":"comando desconocido ","sugerencia":"ALTA"}` cuando el comando es cercano a uno conocido: ` ALTA`, `ALTA ` (967, 968), `ALT`, `BLTA`, `ATLA`, `AXXA` (1307–1310), `CONSULT` → CONSULTA (1311), `TRANSFE` → TRANSFER (1312), `PIN` → PING (1313), `alt` → ALTA (1314). Sin clave `sugerencia` para `ZZZ` (1315). Los casos son compatibles con distancia de edición ≤ 2 sin distinguir caja; no se midió el umbral exacto ni los empates.

### Control

Bien formado = **uno o dos dígitos ASCII**. Todo lo demás da E201: espacio antes o después, `+`/`-`, `82.0`, `8.2e1`, `0x52`, dígitos arábigo-índicos y de ancho completo (978–986), `100`, `9223372036854775808`, `082` (991–993) y `82\n` (1339). Con uno o dos dígitos y valor distinto del esperado: E202, incluidos `0`, `00`, `1`, `99` (987–990). `82;` → E104 (994). Ninguna variante consumió AC (995: AC-0001).

### PING

- No valida el valor del control: `XX`, `0`, `100`, `-1`, `062`, `64\n`, `64\u0000` y el valor de la fórmula → pong (1066, 1069–1072, 1076, 963, 964).
- Sí aplica la forma: `PING` → E103 (1067), `PING;` → E104 (1068), `PING;;1;64` → E104 (1326).
- Aridad cero: `PING;1;2` → E302 (1073), también con el control correcto de la fórmula (1325, 1327).
- Comando sin distinguir caja: `ping`, `Ping` → pong (1074, 1075).

### Comandos y argumentos

- Todos los comandos ignoran la caja: `alta`, `consulta`, `deposito`, `anula` funcionan y `Transfer` se reconoce (1078–1082). El comando no se recorta: ` ALTA` y `ALTA ` → E301 (967, 968).
- El nombre de ALTA se acepta tal cual: con espacio inicial (969), tabulador (966), espacio interno (1084), 100 y 1000 caracteres (1085, 1086), `Zoë` (1088), `123` (1089) y un surrogate suelto (965).
- IDs de cuenta exactos: `ac-0001`, `AC-1`, `AC-01`, `AC-0001 `, `AC0001`, `AC-0000`, `AC-+001` → E401 (1056–1063).

### Montos (DEPOSITO y TRANSFER)

- Formato: entero decimal positivo **sin signo, sin ceros iniciales, sin espacios ni decimales**. E303 para `0`, `-1`, `+1`, `01`, `1.0`, `1e3`, `-0`, `00`, `0x10`, `١`, `1 ` (998–1018) y en TRANSFER para `0`, `-1`, `-100000`, `+1`, `01`, `1.0`, `100000.0`, `0100000`, `1e5` (1032–1048). Los saldos no cambian (999–1021, 1033–1049).
- Tope: hasta **10 dígitos**. Aceptados `100000000`, `999999999`, `2147483648` (1318–1320), `4294967296` (1334) y `9999999999` (1379). E303 para `10000000000`, `99999999999` (1380, 1381), `999999999999`, `999999999999999`, `2^53−1`, `2^53` (1335–1338), `2^53+1` (1321), `2^63−1` (1020) y mayores (1024, 1026). El borde exacto 9999999999/10000000000 tiene una sola pasada.
- El saldo suma sin desbordar 32 bits: 3247483647 (1322).
- En TRANSFER, un monto fuera de rango (19 dígitos, también mayor que 100000) da E303 y no E506 (1052); con origen = destino da E303 y no E304 (1323).

## Deltas para el handler Go (tablero B)

Responsable sugerido: quien tome **B3** (parser) y la fila nueva **B1a** del tablero. El handler de B1 (`internal/httpadapter/handler.go`) hoy:

1. Evalúa auth antes de ruta → **invertir**: método+ruta primero (E404 incluso sin auth), luego auth.
2. No tiene tope de cuerpo → leer como máximo 8193 bytes y responder 413 E101 tras auth.
3. `HEAD`: ya da 404 por no estar en el switch, pero con auth inválida da 401: el reordenamiento lo corrige (cuerpo vacío lo pone net/http).
4. El stub de PING exige control de dos campos exactos; el parser de B3 debe aplicar E103/E104/E302 y aceptar cualquier control no vacío en PING sin calcular integridad.
5. E301 necesita la clave `sugerencia` para comandos cercanos (B3/B4).
6. Ya coinciden: comparación exacta del header, query ignorada, ruta cruda, `M` → E102, `m` duplicada gana la última (Go `map`), BOM → E100, Content-Type ignorado.
