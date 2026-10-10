# Caja negra: especificación incremental

**Versión observada:** `v1`, revalidada en A2 el 10 de octubre entre 15:00:19 y 15:00:56 de Bogotá, antes del cambio anunciado. Evidencia: `experimentos.jsonl`, IDs 1–450. El replay completo (IDs 227–450) repitió diez secuencias desde reset sin caché: 224 respuestas coinciden según el contrato, y las 174 con bytes históricos coinciden byte a byte. Los intentos 51 y 226 fallaron sin respuesta y no prueban comportamiento del servicio. Los IDs 1–50 no tenían bytes capturados; A2 captura los nuevos sin inventar los antiguos. Las filas conservan su confianza indicada y añaden evidencia de repetición. Este documento no afirma vigencia después del cambio; A6 sigue pendiente. Ver [informe A2](research/baseline-a2.md).

**A3 (estado), `v1`:** IDs 451–886, 10 de octubre entre 15:11 y 15:13 de Bogotá, antes del cambio anunciado. Primera pasada 451–670 y repetición completa sin caché 671–886: 216/216 respuestas iguales en status y bytes. En las filas, «A3r» es la repetición: el ID de la primera pasada +220 (secuencias de 451–614) o +216 (de 619–670). Ver [informe A3](research/state-a3.md).

Cada fila observada cita IDs reales del log. Las decisiones del reemplazo llevan **supuesto** y no se presentan como evidencia del original. Tras cada cambio, repetir todas las reglas que se entreguen como vigentes y anotar IDs y versión nuevos; retirar de esa entrega las filas históricas que no se revaliden.

**A4 (sobre y números), `v1`:** IDs 887–1381, 10 de octubre entre 15:25:11 y 15:28:23 de Bogotá, antes del cambio anunciado. Secuencias 01–13 (887–1090) repetidas sin caché en 1091–1294 (ID +204) y 14–18 (1295–1331) en 1340–1376 (ID +45): 241/241 iguales en status y bytes. Las secuencias 19–20 (1332–1339, 1377–1381) tienen una sola pasada. «A4r» cita la repetición. Ver [informe A4](research/envelope-a4.md).

### 1. Entrada

| ID | Comportamiento | Evidencia | Confianza |
| --- | --- | --- | --- |
| ENT-01 | `POST /msg` requiere JSON con `m` string. `{}` y `m` numérico dan E102; campos extra y Content-Type text/plain se aceptan en PING. | log 2-21, 46-49; A2 log 228–247, 272–275 | probable |
| ENT-02 | Sin auth, auth vacía, token inválido o esquema Basic: 401 `{"error":"E001","mensaje":"no autorizado"}`. Health y reset también requieren auth. | log 36-40, 50; A2 log 262–266, 276 | probable |
| ENT-04 | Token distinto de TEAM_TOKEN: el reemplazo responderá 401 E001. No se conoce el conjunto de tokens válidos del original; el aislamiento de estado entre tokens se toma del contrato, porque solo hay un token válido contra el original (ver ENT-08). | Decisión; contrato; A3 log 618 | supuesto |
| ENT-03 | GET /health y POST /__reset autenticados: 200 `{"ok":true}`. Cualquier otro método o ruta → 404 E404 sin redirect: GET /msg, POST /health, OPTIONS, PUT, DELETE y PATCH (incluido `/__reset`, que no resetea). `HEAD` en cualquier ruta, incluida `/health`, → 404 con cuerpo vacío. | log 34-35, 41-44; A2 log 260–261, 267–270; A4 log 892, 894, 909, 914–930; A4r 1096, 1098, 1113, 1118–1134 | confirmado |
| ENT-05 | Orden del sobre: método+ruta → auth → tamaño → JSON → `m`. Ruta o método desconocidos dan 404 E404 aunque falte la auth o sea inválida; con ruta válida, sin auth → 401 aunque el cuerpo sea `{`, `{}` o supere el tope; una ruta desconocida con cuerpo `{` o grande → 404. | A4 log 888–893, 896, 925–926, 1300–1301, 1329–1331; A4r 1092–1097, 1100, 1129–1130, 1345–1346, 1374–1376 | confirmado |
| ENT-06 | Enrutado por comparación exacta de la ruta cruda, sin decodificar escapes, normalizar puntos o barras ni ignorar caja; la query se ignora (`/msg?x=1`, `/msg?`, `/health?x=1` funcionan). 404 E404: `/%6dsg`, `/msg/`, `/MSG`, `/./msg`, `/x/../msg`, `/msg%2F`, `/msg;x`, `/health/`, `/HEALTH`, `//health`, `/`, `/%68ealth`. | log 44; A4 log 899–913; A4r 1103–1117 | confirmado |
| ENT-07 | Cuerpo de `/msg`: JSON estricto → si no, E100 (vacío, basura o segundo valor tras el objeto, truncado, comillas simples, coma final, `NaN`, BOM UTF-8, formulario, control literal sin escapar en un string). Se toleran espacios alrededor. JSON válido que no es objeto, o `m` ausente, `null`, no string o solo como `M` → E102. `m` duplicada: gana la última. Content-Type se ignora. Los escapes JSON se decodifican antes de partir `m` (`\u003b` separa). | log 45-47; A4 log 932–938, 940–953, 955–957, 960–962, 1306; A4r 1136–1142, 1144–1157, 1159–1161, 1164–1166, 1351 | confirmado |
| ENT-08 | El original rechaza TEAM_TOKEN (el token del equipo para el reemplazo): `POST /__reset` → 401 E001. No es una regla a copiar: el contrato exige que el reemplazo acepte TEAM_TOKEN. | A3 log 618 | probable |
| ENT-09 | `/__reset` solo resetea con `POST` exacto y auth válida: sin auth o con token inválido → 401 E001; `GET`/`PUT /__reset` y `POST /__reset/` → 404 E404; ninguno altera el estado (la cuenta sigue y el contador continúa en AC-0002). El cuerpo se ignora (`{"m":"PING;64"}` → 200 `{"ok":true}`) y dos resets seguidos responden igual. | A3 log 598–604, 606–607; A3r 818–824, 826–827 | confirmado |
| ENT-10 | Tope del cuerpo: 8192 bytes pasan, 8193 → 413 `{"error":"E101","mensaje":"cuerpo demasiado grande"}` (también 70 KB y una ALTA de 10000 caracteres). Se evalúa tras ruta y auth (ENT-05). | A4 log 958, 1087, 1296–1299; A4r 1162, 1291, 1341–1344 | confirmado |
| ENT-11 | Auth exacta: solo `Bearer <token>` con un espacio; `bearer <token>`, `Bearer  <token>` y el token sin esquema → 401 E001, también en `/health`. | A4 log 971–976; A4r 1175–1180 | confirmado |

### 2. Integridad

| ID | Comportamiento | Evidencia | Confianza |
| --- | --- | --- | --- |
| INT-01 | Control: usar el texto anterior al último `;control`; conservar solo `[A-Za-z0-9]` antes de convertir caja, mapear letras a A=1…Z=26, conservar dígitos y concatenar las representaciones decimales; añadir `00`, calcular resto módulo 97 y devolver `98 − resto`, **sin módulo final** (rango 2–98). Modelo confirmado en los dominios sondeados; alcance y fixtures en [informe A1](research/control-a1.md). | log 53–60, 124, 126–144, 149–161, 163–199, 201–225; A2 log 278–285, 349, 351–369, 374–386, 388–424, 426–450 | confirmado |
| INT-02 | Forma del control: bien formado = uno o dos dígitos ASCII; cualquier otra forma → E201 (espacios, signo, `82.0`, `8.2e1`, `0x52`, dígitos no ASCII, tres o más dígitos como `062`, `082`, `100`, `82\n`). Con uno o dos dígitos y valor distinto → E202, incluidos `0`, `00`, `03`, `05`, `1`, `99`. Ninguna variante consume AC. | log 145, 153–155, 211–214, 221; A2 log 370, 378–380, 436–439, 446; A4 log 978–995, 1339; A4r 1182–1199 | confirmado |
| INT-04 | Plan B no activado: A1 confirmó la fórmula. El fallback histórico del diseño queda reservado a un corte explícito si una versión posterior invalida la investigación; no describe al original. | Decisión A1; fórmula y validación en INT-01 | supuesto |
| INT-03 | Los separadores no contribuyen al checksum pero sí a la aridad: `ALTA;A;B;23` da E302, mientras `ALTA;AB;23` y `ALTA;A-B;23` crean cuentas. `ALTA;Q;R;65` repite E302 y su vecino 66 da E202: integridad precede aridad. | log 131–132, 138, 179–180, 198–199, 216–217, 220; A2 log 356–357, 363, 404–405, 423–424, 441–442, 445 | confirmado |
| INT-05 | No se desacentúa ni se aplica casing expansivo al Unicode antes de filtrar: `Ána` usa checksum de `na` (61), `A`+U+0308+`na` conserva A (50); `ßa` e `ıa` usan checksum de `a` (62), no de SSA/IA. UTF-8 reservado `Zoë` (90) y A+U+0301 (62) confirman la generalización. Solo se describe el cálculo, no una normalización del nombre almacenado. | log 139–144, 149–152, 163–166, 182–185, 201–206, 215; A2 log 364–369, 374–377, 388–391, 407–410, 426–431, 440 | confirmado |
| INT-06 | Los ceros de los IDs participan como texto: AC-0001→14, AC-00001→61; AC-0042→85, AC-00042→35. No canonicalizar IDs antes del checksum. | log 135–136, 167–168, 177–178, 186–187, 196–197; A2 log 360–361, 392–393, 402–403, 411–412, 421–422 | confirmado |
| INT-07 | DEPOSITO con monto 7 usa control10 y monto 007 control 70; este último llega a E303, su vecino 71 a E202. No canonicalizar cantidades antes del checksum; estos casos se repitieron en A2, pero otros formatos numéricos siguen pendientes de A4. | log 222–225; A2 log 447–450 | probable |
| INT-08 | Controles `5X` y `0062` dan E201 en los casos históricos repetidos en A2. | log 18, 146; A2 log 244, 371 | probable |
| INT-09 | Un segmento vacío en cualquier posición (argumento o control) → 400 `{"error":"E104","mensaje":"segmento vacío"}`, antes que E201 (`ALTA;;5X`), E202 (`ALTA;;84`), E301 (`ZZZ;;53` y `;54`) y E302 (`ALTA;;;85`, `ALTA;Ana;;49`). Control vacío (`ALTA;Ana;`) también da E104. Visto en ALTA, CONSULTA, DEPOSITO, TRANSFER, ANULA. Comando vacío (`;…`) sin sondear. | A3 log 455, 635–640, 666–670; A3r 675, 851–856, 882–886 | confirmado |
| INT-10 | `m` sin ningún `;` (incluida `m` vacía) → 400 `{"error":"E103","mensaje":"falta control"}`, antes que E301: `""`, `PING`, `ALTA`, `ZZZ`. | A4 log 939, 1067, 1303–1304; A4r 1143, 1271, 1348–1349 | confirmado |
| INT-11 | PING no valida el valor del control: cualquier campo no vacío (`XX`, `0`, `100`, `-1`, `062`, `64\n`) da pong. Sí aplica E103, E104 y aridad cero (`PING;1;<control correcto>` → E302). | log 2, 33; A4 log 963–964, 1066–1076, 1325–1327; A4r 1167–1168, 1270–1280, 1370–1372 | confirmado |

### 3. Comandos

Cada fila es el bloque inicial del comando; ampliarlo con argumentos, límites, efectos y
errores una vez medidos. No limitar la exploración a estos seis comandos.

| ID | Comportamiento | Evidencia | Confianza |
| --- | --- | --- | --- |
| CMD-PING | `PING;<control>` → 200 `{"pong":true}` con cualquier control no vacío (INT-11); sin argumentos; comando sin distinguir caja (`ping`, `Ping`). | log 2, 33; A2 log 228, 259; A4 log 1066, 1073–1076; A4r 1270, 1277–1280 | confirmado |
| CMD-ALTA | `ALTA;nombre` → 201 `{"cuentaId":"AC-NNNN"}`, saldo inicial 0. Numeración consecutiva desde AC-0001 tras reset; solo las altas exitosas consumen número. Nombre vacío → E104; dos nombres → E302. | log 4-6; A2 log 230–232; A3 log 452–457, 493; A3r 672–677, 713 | confirmado |
| CMD-CONSULTA | Consulta devuelve 200 y claves `cuenta_id`, `saldo`; `CONSULTa` funciona en ese caso. Normalización general pendiente. | log 6, 9, 12, 20; A2 log 232, 235, 238, 246 | probable |
| CMD-DEPOSITO | `DEPOSITO;cuenta;monto` → 200 `{"status":"recieved","operacionId":"OP-NNNN"}` y suma el monto. Sin límite observado hasta 99999999 (saldo 101119999 tras 120000 + 1000000 + 99999999); no aplica E506. Cuenta inexistente → 404 E401; monto `007` → E303 (antes que E401). Se puede depositar en cuenta con saldo negativo. | log 7, 19-20; A2 log 233, 245–246; A3 log 461–465, 548–551, 631, 660–661; A3r 681–685, 768–771, 847, 876–877 | confirmado |
| CMD-TRANSFER | `TRANSFER;origen;destino;monto` → 200 con la forma de operación; resta del origen y suma al destino. Monto > 100000 → 422 E506 (100000 pasa, 100001 falla); el límite es por operación, no acumulado ni compartido entre cuentas. Origen = destino → 400 E304; origen o destino inexistente → 404 E401; saldo del origen < monto (incluido saldo negativo) → 422 E507. Orden en ERR-ORD. | log 8-12; A2 log 234–238; A3 log 466–468, 541–545, 555–557, 563–565, 583–585, 612, 621–633, 659; A3r 686–688, 761–765, 775–777, 783–785, 803–805, 832, 837–849, 875 | confirmado |
| CMD-ANULA | `ANULA;OP-NNNN` → 200 `{"ok":true,"anulada":"OP-NNNN"}` y revierte el efecto: depósito → resta el monto; transferencia → devuelve al origen y quita al destino. No comprueba saldo (puede dejar cuentas en negativo) ni aplica E506 (anula depósitos de 250000). Repetir → 200 `{"ok":false,"motivo":"ya anulada"}`. El ID debe coincidir exactamente: `op-0001`, `OP-1`, `OP-00001`, `OP-0000`, un OP aún no emitido o un `AC-NNNN` → 404 E402. Sin argumento o con dos → E302. | log 14-15, 17, 20; A2 log 240–241, 243, 246; A3 log 482–488, 501–503, 511–517, 521–535, 646–647, 662–664; A3r 702–708, 721–723, 731–737, 741–755, 862–863, 878–880 | confirmado |
| CMD-CAJA | Los comandos no distinguen caja (`alta`, `consulta`, `deposito`, `Transfer`, `anula`, además de `CONSULTa`), pero no se recortan: ` ALTA` y `ALTA ` → E301. Los IDs de cuenta deben coincidir exactamente (`ac-0001`, `AC-1`, `AC-01`, `AC-0001 `, `AC0001`, `AC-0000` → E401). | log 12; A2 log 238; A4 log 967–968, 1056–1063, 1078–1082; A4r 1171–1172, 1260–1267, 1282–1286 | confirmado |
| CMD-NOMBRE | ALTA acepta el nombre tal cual: espacios iniciales o internos, tabulador, acentos, dígitos, surrogate suelto, 1000 caracteres. El límite real lo pone el tamaño del cuerpo (ENT-10). | A4 log 965–966, 969, 1084–1086, 1088–1089; A4r 1169–1170, 1173, 1288–1290, 1292–1293 | confirmado |
| CMD-MONTO | Monto de DEPOSITO y TRANSFER: entero decimal positivo sin signo, ceros iniciales, espacios, decimales ni exponente; si no → E303 sin efecto (`0`, `-1`, `+1`, `01`, `00`, `1.0`, `1e3`, `0x10`, `١`, `1 `, `100000.0`, `0100000`). En TRANSFER, E303 precede a E304 y a E506: un monto de 19 dígitos, que también supera el límite de 100000, da E303 y no E506 (inferido de que E506 no aparece). | A4 log 998–1021, 1032–1049, 1052, 1323; A4r 1202–1225, 1236–1253, 1256, 1368 | confirmado |
| CMD-MONTO-TOPE | Tope de 10 dígitos: `9999999999` se acepta y `10000000000` → E303. Aceptados también `2147483648` y `4294967296`; saldo 3247483647 sin desbordar 32 bits. Rechazados `2^53+1`, `2^63−1` y mayores. | A4 log 1020, 1024, 1026, 1318–1322, 1334–1338, 1379–1381; A4r 1224, 1228, 1230, 1363–1367 | probable |

### 4. Memoria entre requests

| ID | Comportamiento | Evidencia | Confianza |
| --- | --- | --- | --- |
| MEM-01 | Dos contadores por token, AC y OP, consecutivos desde 0001 tras reset. Solo consumen número ALTA exitosa (AC) y DEPOSITO/TRANSFER exitosos (OP). No consumen: errores E104, E201, E202, E302, E303, E304, E401, E402, E506, E507; ANULA (exitosa o no); PING; CONSULTA. | log 4-20, 134–144; A2 log 230–246; A3 log 456–457, 465, 469, 477, 484, 487, 495, 614, 641, 652; A3r 676–677, 685, 689, 697, 704, 707, 715, 834, 857, 868 | confirmado |
| MEM-02 | `POST /__reset` autenticado → 200 `{"ok":true}`; borra cuentas, saldos y operaciones y reinicia AC y OP a 0001, también a mitad de secuencia (la cuenta previa da E401, la operación previa E402). X-Req no se reinicia. Formas que no resetean en ENT-09. | log 1, 22, 34; A2 log 227, 248, 260; A3 log 587–595; A3r 807–815 | confirmado |
| MEM-03 | Persistir estado tras reinicio es una decisión del reemplazo, no una observación del ciclo de vida del original. | Decisión Q5/Q8; prueba de recuperación pendiente | supuesto |
| MEM-04 | Los saldos pueden quedar negativos solo por ANULA (depósito ya gastado → −800; transferencia cuyo receptor ya gastó → −1000). Una cuenta en negativo recibe E507 al transferir y acepta depósitos; anular la transferencia restante la restituye. | A3 log 499–503, 508–517, 656–664; A3r 719–723, 728–737, 872–880 | confirmado |
| MEM-05 | El estado anulada de cada OP persiste dentro de la secuencia (segunda ANULA → `ya anulada`); tras reset la OP deja de existir (MEM-02); una anulación no cambia los IDs ni el límite por operación de transferencias posteriores. | A3 log 485, 572–576; A3r 705, 792–796 | confirmado |
| MEM-06 | Estado aislado por token: tomado del contrato. No medido, porque el único token alternativo (TEAM_TOKEN) es rechazado por el original. | Contrato; A3 log 618 | supuesto |

### 5. Errores

Cuerpos exactos observados; los espacios dentro de strings son significativos. Orden medido: E201 antes de E202, y E202 antes de E301/E302/E401 (log 23-32). El orden del sobre (ruta → auth → tamaño → JSON → `m`) está en ENT-05. Ver ERR-ORD para E104, E303, E304, E401, E506 y E507.

| ID | Comportamiento | Evidencia | Confianza |
| --- | --- | --- | --- |
| ERR-001 | 401, `{"error":"E001","mensaje":"no autorizado"}`. | log 36-40, 50; A2 log 262–266, 276 | probable |
| ERR-100 | 400, `{"error":"E100","mensaje":"json inválido"}` para cuerpo `{`. | log 45; A2 log 271 | probable |
| ERR-101 | 413, `{"error":"E101","mensaje":"cuerpo demasiado grande"}` para cuerpos de más de 8192 bytes (ENT-10). | A4 log 958, 1299; A4r 1162, 1344 | confirmado |
| ERR-102 | 400, `{"error":"E102","mensaje":"falta m"}` para `{}` y `{"m":64}`. | log 46-47; A2 log 272–273 | probable |
| ERR-103 | 400, `{"error":"E103","mensaje":"falta control"}` cuando `m` no contiene `;` (INT-10). | A4 log 939, 1303; A4r 1143, 1348 | confirmado |
| ERR-404 | 404, `{"error":"E404","mensaje":"ruta desconocida"}` para rutas/métodos probados. | log 41-44; A2 log 267–270 | probable |
| ERR-201 | 400, `{"error":"E201","mensaje":"control mal formado"}`; repetido para `062`. | log 18, 145–146, 221; A2 log 244, 370–371, 446 | confirmado |
| ERR-202 | 400, `{"error":"E202","mensaje":"control inválido"}` cuando el control bien formado no coincide con el calculado en los casos medidos; incluye padding03/05. | log 54, 60, 154–161, 164–199, 202–214, 223, 225; A2 log 279, 285, 379–386, 389–424, 427–439, 448, 450 | confirmado |
| ERR-301 | 400, `{"error":"E301","mensaje":"comando desconocido "}`; espacio final. Si el comando es cercano a uno conocido se añade `"sugerencia":"<COMANDO>"` en mayúsculas (` ALTA`, `ALT`, `BLTA`, `ATLA`, `AXXA`, `alt` → ALTA; `CONSULT` → CONSULTA; `TRANSFE` → TRANSFER; `PIN` → PING); `ZZZ` no la lleva. Compatible con distancia de edición ≤ 2 sin distinguir caja; umbral y empates no medidos. | log 13; A2 log 239; A4 log 967–968, 1307–1315; A4r 1171–1172, 1352–1360 | probable |
| ERR-302 | 400, `{"error":"E302","mensaje":"aridad inválida"}`. | log 21; A2 log 247 | probable |
| ERR-401 | 404, `{"error":"E401","mensaje":"cuenta inexistente"}`. | log 16, 167, 177, 186, 196; A2 log 242, 392, 402, 411, 421 | confirmado |
| ERR-303 | 400, `{"error":"E303","mensaje":"monto inválido"}` para DEPOSITO AC-0001 con monto 007 y control 70; vecino 71 produce E202 antes. No generalizar todavía a otros formatos numéricos. | log 224–225; A2 log 449–450 | probable |
| ERR-402 | 404, `{"error":"E402","mensaje":"operación inexistente"}` en ANULA cuando el argumento no coincide exactamente con un OP emitido (incluye `AC-NNNN`, minúsculas, sin ceros o cinco dígitos); E202 se evalúa antes. | log 173–174, 192–193; A2 log 398–399, 417–418; A3 log 486, 521–526, 530–531, 534–535, 592; A3r 706, 741–746, 750–751, 754–755, 812 | confirmado |
| ERR-506 | 422, `{"error":"E506","mensaje":"límite excedido"}` en TRANSFER con monto > 100000, por operación; no se acumula ni aplica a DEPOSITO o ANULA. | log 10; A2 log 236; A3 log 476, 541–545, 549, 557, 563–565, 646; A3r 696, 761–765, 769, 777, 783–785, 862 | confirmado |
| ERR-507 | 422, `{"error":"E507","mensaje":"saldo insuficiente"}` en TRANSFER cuando el saldo del origen es menor que el monto (incluido saldo 0 o negativo). | log 17; A2 log 243; A3 log 466, 556, 649, 651, 659; A3r 686, 776, 865, 867, 875 | confirmado |
| ERR-104 | 400, `{"error":"E104","mensaje":"segmento vacío"}`; alcance y orden en INT-09. | A3 log 455, 635–640, 666–670; A3r 675, 851–856, 882–886 | confirmado |
| ERR-304 | 400, `{"error":"E304","mensaje":"origen y destino iguales"}` en TRANSFER con origen = destino, aunque la cuenta no exista. | A3 log 612, 621–623, 633; A3r 832, 837–839, 849 | confirmado |
| ERR-ORD | Orden observado: ruta → E001 → E101 → E100 → E102 → E103 → E104 → E201 → E202 → (E301 \| E302); en TRANSFER, tras integridad y aridad: E303 → E304 → E401 (origen o destino) → E506 → E507; en DEPOSITO: E303 → E401. Ejemplos: `TRANSFER;AC-0001;AC-0001;007` → E303; mismo origen/destino con 200000 o sin saldo → E304; `AC-0009` con 120000 → E401; 120000 sin saldo → E506. | log 23-32, 224–225; A3 log 555, 621–633, 635–640, 666–670; A3r 775, 837–849, 851–856, 882–886; A4 log 888–896, 1300–1304; A4r 1092–1100, 1345–1349 | confirmado |

### 6. Cambios durante el día

| ID | Comportamiento | Evidencia | Confianza |
| --- | --- | --- | --- |
| CAM-01 | Incidente FR-0153, abierto a las 15:30: el original responde como versión 2. Cambiaron exactamente 3 comportamientos y el resto es igual que en v1. Los tests de conformidad corren contra v2. Los deltas se registran en el log y se explican en el debrief. | [Ticket FR-0153](old-system/incidente-FR-0153.md) (enunciado, no observación) | confirmado |
| CAM-02 | Anotar versión/corpus, primer timestamp observado y IDs antes/después; sin sondeo continuo no afirmar el instante exacto del cambio. | Decisión Q6/Q10; [informe A2](research/baseline-a2.md); detección posterior pendiente en A6 | supuesto |
| CAM-V2-1 | Delta 1 de 3: pendiente de A6. | — | pendiente |
| CAM-V2-2 | Delta 2 de 3: pendiente de A6. | — | pendiente |
| CAM-V2-3 | Delta 3 de 3: pendiente de A6. | — | pendiente |
| CAM-03 | A2 repite íntegramente la línea base antes de las 15:30 anunciadas: ningún delta de contrato en 224 respuestas ni de bytes en las 174 comparables. Solo confirma los casos sondeados durante 15:00:19–15:00:56 de Bogotá; no descarta cambios posteriores ni fija su instante. | log 227–450; [informe A2](research/baseline-a2.md) | confirmado |

### 7. Riesgos

| ID | Comportamiento | Evidencia | Confianza |
| --- | --- | --- | --- |
| RIE-01 | ANULA no comprueba saldo: permite saldos negativos y anular un depósito ya transferido (MEM-04). Un cliente nuevo no debería heredarlo: exigir saldo suficiente o una contrapartida explícita, registrar quién anula y limitar la anulación a operaciones recientes. El reemplazo lo conserva por fidelidad. | A3 log 501–503, 511–513; A3r 721–723, 731–733 | confirmado |
| RIE-02 | No cambiar mensajes inconsistentes (`recieved`, claves heterogéneas, espacios) durante el reto. Un cliente nuevo usaría un contrato versionado. | log 4, 6-8, 13; A2 log 230, 232–234, 239 | probable |
| RIE-03 | Reinicios, volumen mal montado, cuota agotada o pérdida de red pueden hacer fallar evaluación. Verificar recuperación, persistencia y endpoint público antes de entregar. | Decisiones Q5/Q9; pruebas pendientes | supuesto |
| RIE-04 | Un fallback desconocido puede reducir puntaje. No inventar comportamiento silenciosamente: medirlo o documentar explícitamente status/cuerpo y confianza antes de implementar. | Regla del contrato; fallback explícito en INT-04, sin implementación | supuesto |
| RIE-05 | La ruta se evalúa antes que la auth: un cliente sin credenciales distingue rutas existentes (401) de inexistentes (404), y E301 con `sugerencia` revela los comandos válidos. Un servicio nuevo autenticaría primero y respondería igual a todo lo no autorizado. El reemplazo lo conserva por fidelidad. | A4 log 888–890, 1307; A4r 1092–1094, 1352 | confirmado |
| RIE-06 | `HEAD /health` da 404: un balanceador que sondee con HEAD marcaría el servicio como caído. Un servicio nuevo respondería HEAD como GET sin cuerpo. | A4 log 921; A4r 1125 | confirmado |

