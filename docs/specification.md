# Caja negra: especificación incremental

**Versión observada:** `v1`. Evidencia: `experimentos.jsonl`, IDs 1-50, tres secuencias con reset. El corpus entregado se reprodujo una vez; se conserva confianza **probable** hasta una confirmación independiente. Este documento no afirma vigencia después del cambio. No hay delta observado aún.

Cada fila observada cita IDs reales del log. Las decisiones del reemplazo llevan **supuesto** y no se presentan como evidencia del original. Tras cada cambio, repetir todas las reglas que se entreguen como vigentes y anotar IDs y versión nuevos; retirar de esa entrega las filas históricas que no se revaliden.

### 1. Entrada

| ID | Comportamiento | Evidencia | Confianza |
| --- | --- | --- | --- |
| ENT-01 | `POST /msg` requiere JSON con `m` string. `{}` y `m` numérico dan E102; campos extra y Content-Type text/plain se aceptan en PING. | log 2-21, 46-49 | probable |
| ENT-02 | Sin auth, auth vacía, token inválido o esquema Basic: 401 `{"error":"E001","mensaje":"no autorizado"}`. Health y reset también requieren auth. | log 36-40, 50 | probable |
| ENT-04 | Token distinto de TEAM_TOKEN: el reemplazo responderá 401 E001. No se conoce el conjunto de tokens válidos del original. | Decisión; sin prueba | supuesto |
| ENT-03 | GET /health y POST /__reset autenticados: 200 `{"ok":true}`. GET /msg, rutas inexistentes y POST //msg: 404 E404, sin redirect. HEAD, OPTIONS y precedencia auth/ruta pendientes. | log 34-35, 41-44 | probable |

### 2. Integridad

| ID | Comportamiento | Evidencia | Confianza |
| --- | --- | --- | --- |
| INT-01 | `ALTA;Lucia;83` da E202 y `ALTA;Lucia;82` crea cuenta. Fórmula y cobertura del control desconocidas. | log 3-4 | probable |
| INT-02 | Control `5X` en el depósito observado da E201. Rango, espacios y representación pendientes. | log 18 | probable |
| INT-04 | Sin fórmula al corte: validar valores conocidos; para mensajes nuevos aceptar control ASCII de 1-2 dígitos 0-99, resto E201. Se omite E202 desconocido; puede alterar estado. No describe al original. | Plan B del diseño; sin prueba | supuesto |
| INT-03 | `ALTA;Lucia;Gomez;11` da E302. E202 precede E302 para controles inválidos probados (log 26-28). | log 21 | probable |

### 3. Comandos

Cada fila es el bloque inicial del comando; ampliarlo con argumentos, límites, efectos y
errores una vez medidos. No limitar la exploración a estos seis comandos.

| ID | Comportamiento | Evidencia | Confianza |
| --- | --- | --- | --- |
| CMD-PING | `PING;64` y `PING;1` → 200, `{"pong":true}`; no basta para afirmar que PING ignora cualquier control. | log 2, 33 | probable |
| CMD-ALTA | Alta de Lucia/Mateo → 201, `{"cuentaId":"AC-0001"}` / `AC-0002`; las cuentas observadas arrancan con saldo 0. | log 4-6 | probable |
| CMD-CONSULTA | Consulta devuelve 200 y claves `cuenta_id`, `saldo`; `CONSULTa` funciona en ese caso. Normalización general pendiente. | log 6, 9, 12, 20 | probable |
| CMD-DEPOSITO | Depósitos observados afectan saldo y devuelven 200, `{"status":"recieved","operacionId":"OP-NNNN"}`. | log 7, 19-20 | probable |
| CMD-TRANSFER | Transferencias observadas mueven saldo y devuelven la misma forma de operación; límites no generalizados. | log 8-12 | probable |
| CMD-ANULA | Primera anulación: 200, `{"ok":true,"anulada":"OP-0003"}`. Repetición: 200, `{"ok":false,"motivo":"ya anulada"}`. Reversión y otros tipos pendientes. | log 14-15, 17, 20 | probable |

### 4. Memoria entre requests

| ID | Comportamiento | Evidencia | Confianza |
| --- | --- | --- | --- |
| MEM-01 | Saldos, cuentas y operaciones afectan requests posteriores; IDs observados consecutivos. Consumo de IDs ante errores pendiente. | log 4-20 | probable |
| MEM-02 | Reset inicia las secuencias observadas; X-Req no se reinicia. Alcance completo e aislamiento por token pendientes. | log 1, 22, 34; contrato | supuesto |
| MEM-03 | Persistir estado tras reinicio es una decisión del reemplazo, no una observación del ciclo de vida del original. | Decisión Q5/Q8; prueba de recuperación pendiente | supuesto |

### 5. Errores

Cuerpos exactos observados; los espacios dentro de strings son significativos. Orden medido: E201 antes de E202, y E202 antes de E301/E302/E401 (log 23-32). El orden entre errores de comando/estado y auth/ruta sigue pendiente.

| ID | Comportamiento | Evidencia | Confianza |
| --- | --- | --- | --- |
| ERR-001 | 401, `{"error":"E001","mensaje":"no autorizado"}`. | log 36-40, 50 | probable |
| ERR-100 | 400, `{"error":"E100","mensaje":"json inválido"}` para cuerpo `{`. | log 45 | probable |
| ERR-102 | 400, `{"error":"E102","mensaje":"falta m"}` para `{}` y `{"m":64}`. | log 46-47 | probable |
| ERR-404 | 404, `{"error":"E404","mensaje":"ruta desconocida"}` para rutas/métodos probados. | log 41-44 | probable |
| ERR-201 | 400, `{"error":"E201","mensaje":"control mal formado"}`. | log 18 | probable |
| ERR-202 | 400, `{"error":"E202","mensaje":"control inválido"}`. | log 3 | probable |
| ERR-301 | 400, `{"error":"E301","mensaje":"comando desconocido "}`; espacio final. | log 13 | probable |
| ERR-302 | 400, `{"error":"E302","mensaje":"aridad inválida"}`. | log 21 | probable |
| ERR-401 | 404, `{"error":"E401","mensaje":"cuenta inexistente"}`. | log 16 | probable |
| ERR-506 | 422, `{"error":"E506","mensaje":"límite excedido"}` al transferir 120000 en esa secuencia. | log 10 | probable |
| ERR-507 | 422, `{"error":"E507","mensaje":"saldo insuficiente"}` al transferir 50000 tras anulación. | log 17 | probable |

### 6. Cambios durante el día

| ID | Comportamiento | Evidencia | Confianza |
| --- | --- | --- | --- |
| CAM-01 | Se anuncia un cambio a las 15:30; la evaluación usa la versión vigente a las 20:00. No hay delta observado aún. | AGENTS.md y contrato; replay pendiente | supuesto |
| CAM-02 | Anotar versión/corpus, primer timestamp observado y IDs antes/después; sin sondeo continuo no afirmar el instante exacto del cambio. | Decisión Q6/Q10; informe pendiente | supuesto |

### 7. Riesgos

| ID | Comportamiento | Evidencia | Confianza |
| --- | --- | --- | --- |
| RIE-01 | La anulación observada no equivale a un diseño bancario seguro; investigar negativos, duplicados y operaciones inexistentes antes de describirlos. Un sistema nuevo requeriría reglas explícitas y auditoría. | log 14-17; sondas pendientes | probable |
| RIE-02 | No cambiar mensajes inconsistentes (`recieved`, claves heterogéneas, espacios) durante el reto. Un cliente nuevo usaría un contrato versionado. | log 4, 6-8, 13 | probable |
| RIE-03 | Reinicios, volumen mal montado, cuota agotada o pérdida de red pueden hacer fallar evaluación. Verificar recuperación, persistencia y endpoint público antes de entregar. | Decisiones Q5/Q9; pruebas pendientes | supuesto |
| RIE-04 | Un fallback desconocido puede reducir puntaje. No inventar comportamiento silenciosamente: medirlo o documentar explícitamente status/cuerpo y confianza antes de implementar. | Regla del contrato; fallback explícito en INT-04, sin implementación | supuesto |

