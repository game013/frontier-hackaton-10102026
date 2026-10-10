# Caja negra: especificación incremental

**Versión observada:** `v1`, revalidada en A2 el 10 de octubre entre 15:00:19 y 15:00:56 de Bogotá, antes del cambio anunciado. Evidencia: `experimentos.jsonl`, IDs 1–450. El replay completo (IDs 227–450) repitió diez secuencias desde reset sin caché: 224 respuestas coinciden según el contrato, y las 174 con bytes históricos coinciden byte a byte. Los intentos 51 y 226 fallaron sin respuesta y no prueban comportamiento del servicio. Los IDs 1–50 no tenían bytes capturados; A2 captura los nuevos sin inventar los antiguos. Las filas conservan su confianza indicada y añaden evidencia de repetición. Este documento no afirma vigencia después del cambio; A6 sigue pendiente. Ver [informe A2](research/baseline-a2.md).

Cada fila observada cita IDs reales del log. Las decisiones del reemplazo llevan **supuesto** y no se presentan como evidencia del original. Tras cada cambio, repetir todas las reglas que se entreguen como vigentes y anotar IDs y versión nuevos; retirar de esa entrega las filas históricas que no se revaliden.

### 1. Entrada

| ID | Comportamiento | Evidencia | Confianza |
| --- | --- | --- | --- |
| ENT-01 | `POST /msg` requiere JSON con `m` string. `{}` y `m` numérico dan E102; campos extra y Content-Type text/plain se aceptan en PING. | log 2-21, 46-49; A2 log 228–247, 272–275 | probable |
| ENT-02 | Sin auth, auth vacía, token inválido o esquema Basic: 401 `{"error":"E001","mensaje":"no autorizado"}`. Health y reset también requieren auth. | log 36-40, 50; A2 log 262–266, 276 | probable |
| ENT-04 | Token distinto de TEAM_TOKEN: el reemplazo responderá 401 E001. No se conoce el conjunto de tokens válidos del original. | Decisión; sin prueba | supuesto |
| ENT-03 | GET /health y POST /__reset autenticados: 200 `{"ok":true}`. GET /msg, rutas inexistentes y POST //msg: 404 E404, sin redirect. HEAD, OPTIONS y precedencia auth/ruta pendientes. | log 34-35, 41-44; A2 log 260–261, 267–270 | probable |
| ENT-05 | Orden de evaluación del reemplazo: auth (E001) antes que método/ruta (E404) y que JSON (E100/E102). Sin auth válida, cualquier ruta o cuerpo da 401. | Decisión B1; sin prueba de combinaciones (sonda pendiente en A4) | supuesto |
| ENT-06 | El reemplazo enruta por la ruta cruda del request sin query: no decodifica escapes (`/%6dsg` → 404), no limpia barras ni acepta barra final (`/msg/` → 404); la query se ignora (`/msg?x=1` = `/msg`). | Decisión B1; solo `//msg` observado (log 44, A2 log 270) | supuesto |
| ENT-07 | Cuerpo de `/msg`: si no es JSON válido (incluido vacío o con basura tras el valor) → E100; si es JSON válido pero no objeto, o `m` falta, es `null`, no es string o solo existe como `M` → E102. | Decisión B1; observados `{`, `{}` y `{"m":64}` (log 45-47, A2 log 271–273) | supuesto |

### 2. Integridad

| ID | Comportamiento | Evidencia | Confianza |
| --- | --- | --- | --- |
| INT-01 | Control: usar el texto anterior al último `;control`; conservar solo `[A-Za-z0-9]` antes de convertir caja, mapear letras a A=1…Z=26, conservar dígitos y concatenar las representaciones decimales; añadir `00`, calcular resto módulo 97 y devolver `98 − resto`, **sin módulo final** (rango 2–98). Modelo confirmado en los dominios sondeados; alcance y fixtures en [informe A1](research/control-a1.md). | log 53–60, 124, 126–144, 149–161, 163–199, 201–225; A2 log 278–285, 349, 351–369, 374–386, 388–424, 426–450 | confirmado |
| INT-02 | Forma y valor se separan: control `062` da E201; `03` y `05` llegan a E202 aunque el valor canónico esperado sea 3/5. No basta comparar enteros: en estos casos se exige representación decimal sin padding. Otras formas léxicas y espacios del control pendientes de A4. | log 145, 153–155, 211–214, 221; A2 log 370, 378–380, 436–439, 446 | confirmado |
| INT-04 | Plan B no activado: A1 confirmó la fórmula. El fallback histórico del diseño queda reservado a un corte explícito si una versión posterior invalida la investigación; no describe al original. | Decisión A1; fórmula y validación en INT-01 | supuesto |
| INT-03 | Los separadores no contribuyen al checksum pero sí a la aridad: `ALTA;A;B;23` da E302, mientras `ALTA;AB;23` y `ALTA;A-B;23` crean cuentas. `ALTA;Q;R;65` repite E302 y su vecino 66 da E202: integridad precede aridad. | log 131–132, 138, 179–180, 198–199, 216–217, 220; A2 log 356–357, 363, 404–405, 423–424, 441–442, 445 | confirmado |
| INT-05 | No se desacentúa ni se aplica casing expansivo al Unicode antes de filtrar: `Ána` usa checksum de `na` (61), `A`+U+0308+`na` conserva A (50); `ßa` e `ıa` usan checksum de `a` (62), no de SSA/IA. UTF-8 reservado `Zoë` (90) y A+U+0301 (62) confirman la generalización. Solo se describe el cálculo, no una normalización del nombre almacenado. | log 139–144, 149–152, 163–166, 182–185, 201–206, 215; A2 log 364–369, 374–377, 388–391, 407–410, 426–431, 440 | confirmado |
| INT-06 | Los ceros de los IDs participan como texto: AC-0001→14, AC-00001→61; AC-0042→85, AC-00042→35. No canonicalizar IDs antes del checksum. | log 135–136, 167–168, 177–178, 186–187, 196–197; A2 log 360–361, 392–393, 402–403, 411–412, 421–422 | confirmado |
| INT-07 | DEPOSITO con monto 7 usa control10 y monto 007 control 70; este último llega a E303, su vecino 71 a E202. No canonicalizar cantidades antes del checksum; estos casos se repitieron en A2, pero otros formatos numéricos siguen pendientes de A4. | log 222–225; A2 log 447–450 | probable |
| INT-08 | Controles `5X` y `0062` dan E201 en los casos históricos repetidos en A2. | log 18, 146; A2 log 244, 371 | probable |

### 3. Comandos

Cada fila es el bloque inicial del comando; ampliarlo con argumentos, límites, efectos y
errores una vez medidos. No limitar la exploración a estos seis comandos.

| ID | Comportamiento | Evidencia | Confianza |
| --- | --- | --- | --- |
| CMD-PING | `PING;64` y `PING;1` → 200, `{"pong":true}`; no basta para afirmar que PING ignora cualquier control. | log 2, 33; A2 log 228, 259 | probable |
| CMD-ALTA | Alta de Lucia/Mateo → 201, `{"cuentaId":"AC-0001"}` / `AC-0002`; las cuentas observadas arrancan con saldo 0. | log 4-6; A2 log 230–232 | probable |
| CMD-CONSULTA | Consulta devuelve 200 y claves `cuenta_id`, `saldo`; `CONSULTa` funciona en ese caso. Normalización general pendiente. | log 6, 9, 12, 20; A2 log 232, 235, 238, 246 | probable |
| CMD-DEPOSITO | Depósitos observados afectan saldo y devuelven 200, `{"status":"recieved","operacionId":"OP-NNNN"}`. | log 7, 19-20; A2 log 233, 245–246 | probable |
| CMD-TRANSFER | Transferencias observadas mueven saldo y devuelven la misma forma de operación; límites no generalizados. | log 8-12; A2 log 234–238 | probable |
| CMD-ANULA | Primera anulación: 200, `{"ok":true,"anulada":"OP-0003"}`. Repetición: 200, `{"ok":false,"motivo":"ya anulada"}`. Reversión y otros tipos pendientes. | log 14-15, 17, 20; A2 log 240–241, 243, 246 | probable |

### 4. Memoria entre requests

| ID | Comportamiento | Evidencia | Confianza |
| --- | --- | --- | --- |
| MEM-01 | Saldos, cuentas y operaciones afectan requests posteriores; IDs observados consecutivos. Consumo de IDs ante errores pendiente. | log 4-20; A2 log 230–246 | probable |
| MEM-02 | Reset inicia las secuencias observadas; X-Req no se reinicia. Alcance completo e aislamiento por token pendientes. | log 1, 22, 34; contrato; A2 log 227, 248, 260 | supuesto |
| MEM-03 | Persistir estado tras reinicio es una decisión del reemplazo, no una observación del ciclo de vida del original. | Decisión Q5/Q8; prueba de recuperación pendiente | supuesto |

### 5. Errores

Cuerpos exactos observados; los espacios dentro de strings son significativos. Orden medido: E201 antes de E202, y E202 antes de E301/E302/E401 (log 23-32). El orden entre errores de comando/estado y auth/ruta sigue pendiente.

| ID | Comportamiento | Evidencia | Confianza |
| --- | --- | --- | --- |
| ERR-001 | 401, `{"error":"E001","mensaje":"no autorizado"}`. | log 36-40, 50; A2 log 262–266, 276 | probable |
| ERR-100 | 400, `{"error":"E100","mensaje":"json inválido"}` para cuerpo `{`. | log 45; A2 log 271 | probable |
| ERR-102 | 400, `{"error":"E102","mensaje":"falta m"}` para `{}` y `{"m":64}`. | log 46-47; A2 log 272–273 | probable |
| ERR-404 | 404, `{"error":"E404","mensaje":"ruta desconocida"}` para rutas/métodos probados. | log 41-44; A2 log 267–270 | probable |
| ERR-201 | 400, `{"error":"E201","mensaje":"control mal formado"}`; repetido para `062`. | log 18, 145–146, 221; A2 log 244, 370–371, 446 | confirmado |
| ERR-202 | 400, `{"error":"E202","mensaje":"control inválido"}` cuando el control bien formado no coincide con el calculado en los casos medidos; incluye padding03/05. | log 54, 60, 154–161, 164–199, 202–214, 223, 225; A2 log 279, 285, 379–386, 389–424, 427–439, 448, 450 | confirmado |
| ERR-301 | 400, `{"error":"E301","mensaje":"comando desconocido "}`; espacio final. | log 13; A2 log 239 | probable |
| ERR-302 | 400, `{"error":"E302","mensaje":"aridad inválida"}`. | log 21; A2 log 247 | probable |
| ERR-401 | 404, `{"error":"E401","mensaje":"cuenta inexistente"}`. | log 16, 167, 177, 186, 196; A2 log 242, 392, 402, 411, 421 | confirmado |
| ERR-303 | 400, `{"error":"E303","mensaje":"monto inválido"}` para DEPOSITO AC-0001 con monto 007 y control 70; vecino 71 produce E202 antes. No generalizar todavía a otros formatos numéricos. | log 224–225; A2 log 449–450 | probable |
| ERR-402 | 404, `{"error":"E402","mensaje":"operación inexistente"}` para ANULA OP-0042 con control 46 tras reset; vecino 47 produce E202 antes. | log 173–174, 192–193; A2 log 398–399, 417–418 | confirmado |
| ERR-506 | 422, `{"error":"E506","mensaje":"límite excedido"}` al transferir 120000 en esa secuencia. | log 10; A2 log 236 | probable |
| ERR-507 | 422, `{"error":"E507","mensaje":"saldo insuficiente"}` al transferir 50000 tras anulación. | log 17; A2 log 243 | probable |

### 6. Cambios durante el día

| ID | Comportamiento | Evidencia | Confianza |
| --- | --- | --- | --- |
| CAM-01 | Se anuncia un cambio a las 15:30; la evaluación usa la versión vigente a las 20:00. No hay delta observado aún. | AGENTS.md y contrato; replay posterior al cambio pendiente en A6 | supuesto |
| CAM-02 | Anotar versión/corpus, primer timestamp observado y IDs antes/después; sin sondeo continuo no afirmar el instante exacto del cambio. | Decisión Q6/Q10; [informe A2](research/baseline-a2.md); detección posterior pendiente en A6 | supuesto |
| CAM-03 | A2 repite íntegramente la línea base antes de las 15:30 anunciadas: ningún delta de contrato en 224 respuestas ni de bytes en las 174 comparables. Solo confirma los casos sondeados durante 15:00:19–15:00:56 de Bogotá; no descarta cambios posteriores ni fija su instante. | log 227–450; [informe A2](research/baseline-a2.md) | confirmado |

### 7. Riesgos

| ID | Comportamiento | Evidencia | Confianza |
| --- | --- | --- | --- |
| RIE-01 | La anulación observada no equivale a un diseño bancario seguro; investigar negativos, duplicados y operaciones inexistentes antes de describirlos. Un sistema nuevo requeriría reglas explícitas y auditoría. | log 14-17; sondas pendientes; A2 log 240–243 | probable |
| RIE-02 | No cambiar mensajes inconsistentes (`recieved`, claves heterogéneas, espacios) durante el reto. Un cliente nuevo usaría un contrato versionado. | log 4, 6-8, 13; A2 log 230, 232–234, 239 | probable |
| RIE-03 | Reinicios, volumen mal montado, cuota agotada o pérdida de red pueden hacer fallar evaluación. Verificar recuperación, persistencia y endpoint público antes de entregar. | Decisiones Q5/Q9; pruebas pendientes | supuesto |
| RIE-04 | Un fallback desconocido puede reducir puntaje. No inventar comportamiento silenciosamente: medirlo o documentar explícitamente status/cuerpo y confianza antes de implementar. | Regla del contrato; fallback explícito en INT-04, sin implementación | supuesto |

