# Hallazgos sobre el diseño del reemplazo

Revisión de `docs/system-design.md` (con `PROGRESS.md`, la estrategia de descubrimiento, el
enunciado, el corpus y `tools/explorer/bb.py` en `ecac9e7`). Cada hallazgo tiene un ID para
resolverlo y marcarlo. Estado inicial de todos: **pendiente**. Para el estado actual,
consultar los registros de atención de las secciones 7 y 8; las tablas iniciales son históricas.

## 0. Priorización (qué corregir si falta tiempo)

Criterio: impacto en el puntaje (100 tests y especificación) frente al costo. Resolver en orden;
dentro de cada nivel, de arriba hacia abajo.

**P0 · Imprescindible: sin esto se pierden muchos puntos o la entrega.**

| Orden | ID | Por qué | Costo |
| --- | --- | --- | --- |
| 1 | H-02 | Si la zona horaria está mal, el cambio pasa sin detectarse y evaluamos contra la versión equivocada. | Una pregunta a los organizadores |
| 2 | G-04 | Sin horas de corte (replay final, último despliegue) se llega tarde a las 20:00. | Minutos |
| 3 | H-01 | Sin fórmula ni default, casi todos los tests fallan. Default: aceptar control numérico de 1–2 dígitos y fijar una hora límite para la fórmula. | Bajo (default) / alto (fórmula) |
| 4 | H-05 | Confirmado: `ServeMux` rompe rutas (`//msg` → 301) y métodos (405). Handler propio con catch-all 404 E404. | Bajo |
| 5 | O-02 | Capturar los tests del evaluador y repetirlos contra el original antes de las 20:00 es la fuente de casos más directa. | Bajo |
| 6 | G-02 | Desplegar pronto un esqueleto da puntaje real con cada validación. | Bajo |
| 7 | H-04 | Toda regla debe valer para la versión vigente; una afirmación falsa resta. | Medio (replay tras el cambio) |

**P1 · Importante: protege la calidad y la entrega.**

| Orden | ID | Por qué |
| --- | --- | --- |
| 8 | O-01 | Volver a `v1` en minutos si `v2` falla, sin recompilar. |
| 9 | H-06 | El servicio debe seguir vivo después de las 20:00 (créditos de Railway, sin redesplegar cerca de una validación). |
| 10 | N-02, G-03 | Auth en `/health` y `/__reset`; supuesto para tokens ajenos. |
| 11 | G-06 | Saldos y montos como enteros; un `40000.0` falla el test. |
| 12 | 6.3 | Sondas baratas pendientes (auth contra ruta, E101, PING, métodos). |
| 13 | H-03 | Evitar evidencia contaminada: lease de secuencia y revisión de `X-Req`. |
| 14 | G-07, G-08 | Especificación separada con IDs del log, y log de entrega filtrado. |
| 15 | O-03 | Contadores y alertas de latencia; la línea por request ya viene con O-02. |

**P2 · Si sobra tiempo.**

| ID | Por qué puede esperar |
| --- | --- |
| A-01 | Simplificar el almacenamiento ahorra tiempo solo si se decide antes de implementar; después, no tocarlo. |
| G-05 | Entra en el trabajo de la fórmula del control (H-01). |
| G-01 | Resuelto en gran parte por la exploración (errores JSON propios). |
| N-01, A-02 | Informativos; no requieren cambios. |
| R-01..R-06 | Limitaciones del cliente que no bloquean la exploración. |

## 1. Riesgos altos

| ID | Hallazgo | Propuesta de resolución |
| --- | --- | --- |
| H-01 | No hay plan B si el dígito de control no se descifra. Sin fórmula, el reemplazo no sabe distinguir E202 de un mensaje válido para requests nuevos, y casi todos los tests usan requests nuevos. | Registrar como **supuesto** un default: aceptar todo control de 1–2 dígitos numéricos (se pierden solo los tests de E202). Fijar una hora de corte para dejar de buscar la fórmula. |
| H-02 | La zona horaria de las 15:30 no está confirmada (diseño, líneas 162-165). Si el evento usa hora de CDMX, el replay "después de las 15:30 Bogotá" (14:30 CDMX) correría **antes** del cambio y no detectaría nada. El enunciado dice "puede cambiar": podría haber más de un cambio. | Confirmar la zona con los organizadores. Mientras tanto, repetir el corpus en ambos momentos (15:30 Bogotá y 15:30 CDMX) y una vez más antes de la entrega. |
| H-03 | Un solo token con estado compartido y varios agentes en paralelo (pi, Codex, modelos baratos). Un reset ajeno a mitad de una secuencia contamina la evidencia sin que nadie lo note. El diseño solo coordina cuota e IDs. | Un candado (lease) de secuencia por token. Detectar interferencia con la continuidad de `X-Req`, si resulta ser un contador por token, y con la contigüidad de IDs dentro de una secuencia. |
| H-04 | La evidencia anterior al cambio puede volverse falsa, y "una afirmación falsa resta". | Toda fila de la especificación debe volver a probarse en la versión vigente o marcarse como reemplazada. El corpus de replay debe incluir rutas, autenticación y sobre HTTP, no solo `/msg`. |
| H-05 | `http.ServeMux` de Go limpia las rutas y redirige con 301 (`//msg`, `/a/../msg`). El servidor de Go además responde por su cuenta a requests mal formados y gestiona HEAD y `Expect`. Rompe "cualquier otra ruta responde igual". | Adaptador HTTP con un `http.Handler` propio que reciba todo, sin mux. Escribirlo en el diseño (capa `httpadapter`). |
| H-06 | La evaluación final corre después de las 20:00, a una hora desconocida. El servicio debe seguir vivo con el mismo estado. El respaldo con laptop + ngrok es frágil, y si recuerdo bien, Railway tiene una caída breve al redesplegar con volumen (verificar en la documentación). | Confirmar créditos de Railway hasta el día siguiente. No redesplegar cerca de una validación. Fijar una hora para el último despliegue. |

## 2. Gaps

| ID | Hallazgo | Propuesta de resolución |
| --- | --- | --- |
| G-01 | Nadie captura headers de respuesta (`Server`, `X-Powered-By`, `Content-Type`). Revelan qué framework genera los 404, 405 y los errores de JSON inválido, que hay que copiar carácter por carácter. | Guardar los headers en el log (campo extra) o deducir el framework por los cuerpos. Ver R-01. |
| G-02 | El diseño no usa `/evento/resultados` como oráculo gratuito de puntaje. | Desplegar pronto un esqueleto y validar el entrypoint a menudo, si validar no tiene límite (confirmar). |
| G-03 | Tokens válidos que no son el del equipo: en el original, el token de un compañero funciona y tiene estado propio. El reemplazo no puede saber cuáles son válidos. | Supuesto documentado (por ejemplo, responder como a un token inválido) y decidir si el estado se separa por token. |
| G-04 | No hay una hora de corte para el último cambio. A las 20:00 caen los tokens y es la entrega. | Por ejemplo: replay final 18:30, último despliegue 19:15, congelado a partir de ahí. |
| G-05 | Control sobre texto UTF-8: con `Lucía`, ¿el control se calcula sobre bytes o sobre caracteres? | Añadir la sonda al plan de control. |
| G-06 | Representación de números: el evaluador exige números idénticos (`40000` ≠ `40000.0`). | Fijar en el diseño enteros de Go para saldos y montos, nunca floats; sondear decimales y notación exponencial. |
| G-07 | Especificación y diseño están mezclados en un mismo documento, y el juez lee la especificación. Las citas E1-E20 no son IDs del log. | Separar la especificación en su propio documento y obtener IDs reales repitiendo el corpus. |
| G-08 | El log que se entrega tendrá líneas que no son requests completos (`outcome` = `pending`, `transport_error`, `infrastructure`) y campos extra. | Definir cómo se filtran o se marcan antes de la entrega. |

## 3. Puntos débiles de la arquitectura

| ID | Hallazgo | Propuesta de resolución |
| --- | --- | --- |
| A-01 | Sobreingeniería para un día de trabajo: seis capas y dos almacenamientos (memoria + SQLite) para un estado que se resetea antes de cada test. | Modelo en memoria y snapshot escrito en el volumen, o SQLite guardando un solo documento. Si se mantiene SQLite, usar `modernc.org/sqlite` (Go puro, sin CGO). |
| A-02 | El cliente se modificó en paralelo durante la revisión del diseño (sin commit y con una prueba fallando en ese momento). | Ya está en `ecac9e7` y las 10 pruebas pasan. Mantener la regla de no editar `bb.py` mientras otro agente lo usa. |

## 3b. Capacidades operativas que faltan en el diseño

Propuestas del equipo, 2026-10-10. Ninguna aparece hoy en `docs/system-design.md`.

| ID | Hallazgo | Propuesta de resolución |
| --- | --- | --- |
| O-01 | **Versionado interno del comportamiento.** No hay forma de volver a la versión de la mañana si la de las 15:30 resulta un error nuestro o del original. La regla de la línea 163 ("no seleccionar una versión por hora") prohíbe elegir por reloj, no por configuración, así que no choca. | Variable `BEHAVIOR_VERSION` (`v1`, `v2`…), leída **solo al arrancar**; sin valor, toma la última. Cada versión es un conjunto de reglas: `v2` hereda de `v1` y sobrescribe solo el delta (mensajes, límites, control), sin duplicar el motor. Mismo esquema SQLite para todas. Rollback = cambiar la variable y reiniciar en Railway, sin recompilar. Nombrar igual que la `epoch` de `bb.py` (`v1`/`v2`) para enlazar evidencia y código. Pruebas del corpus por versión. Nunca exponerla en la URL ni en las respuestas. |
| O-02 | **Captura de lo que envía el evaluador.** Cada validación del entrypoint corre los 100 tests contra nosotros; hoy esos requests se pierden. Es la fuente más valiosa de casos reales. | Guardar cada request entrante tal cual: timestamp, método, ruta, query, headers **sin `Authorization`** (solo una etiqueta: equipo, otro, ausente), cuerpo en bytes exactos, status y cuerpo devueltos, latencia, `BEHAVIOR_VERSION` y si se usó una regla por defecto (supuesto). Un `/__reset` marca el inicio de un test. Destino: JSONL en el volumen (`/data/requests.jsonl`) y la misma línea por stdout (logs de Railway). **No exponer una ruta para descargarlo:** cualquier ruta extra debe responder 404 E404 como el original. Leerlo con los logs o el shell de Railway. Uso clave: **antes de las 20:00**, repetir esas secuencias contra el original con `bb.py` (con hipótesis, dentro de la cuota) para obtener la respuesta correcta y corregir. |
| O-03 | **Monitoreo mínimo.** Solo existe readiness; no hay cómo saber si fallamos, tardamos o caemos en defaults. | Sin herramientas externas: (1) la misma línea por request de O-02, legible en los logs de Railway; (2) contadores en memoria, impresos como resumen cada N requests o cada minuto: total, por status, por código de error, hits de reglas por defecto, latencia máxima y p95, y alertas de pasos > 1 s (límite: 5 s); (3) un log de arranque con versión, ruta del estado y esquema listo; (4) un script local que resuma `requests.jsonl` (tests por validación, defaults, lentos). No añadir `/metrics`: rompería el catch-all 404. `/health` sigue como el original (`{"ok":true}`, 401 sin token). |

Riesgos de O-01..O-03:

- El log no debe contener el token: la redacción del header se prueba.
- El archivo crece; tras 100 tests por validación es pequeño, pero conviene rotarlo por tamaño.
- Escribir el log no debe bloquear ni romper la respuesta: si falla, se registra por stdout y se responde igual.

## 4. Revisión del cliente instrumentado (`bb.py` en `ecac9e7`, sin cambios)

Objetivo: comprobar si puede hacer la exploración mínima recomendada antes de cerrar el diseño
(repetir el corpus, medir precedencia y sondear el sobre HTTP).

**Puede hacerlo:**

- Secuencias con reset perezoso, hipótesis obligatoria, IDs bajo `flock` y registro del intento
  **antes** de enviar. Un fallo de transporte queda marcado como `transport_error` y bloquea
  `resume` de esa secuencia.
- Cuota y ritmo compartidos entre procesos (`.explore/quota.json`, 8 req/s, tope 7.800 por día
  de Bogotá). Las respuestas de rate limit quedan marcadas `infrastructure` y no entran en la caché.
- `http` permite método, ruta, cuerpo JSON o crudo, `Content-Type` y las variantes de
  autenticación `none`, `empty`, `invalid` y `scheme`, sin escribir el token.
- Guarda `x_req`, `status`, `response` (JSON o texto) y `raw`.
- La caché incluye el prefijo desde el reset, el `Content-Type` efectivo y la `epoch`. Los aciertos
  pendientes se persisten y se reenvían en el siguiente miss.

**Limitaciones para esta tarea:**

| ID | Limitación | Impacto |
| --- | --- | --- |
| R-01 | Solo guarda el header `X-Req`. No guarda `Content-Type`, `Server` ni `X-Powered-By`. | No hay fingerprint del framework por headers; habrá que deducirlo de los cuerpos (G-01). |
| R-02 | No permite headers arbitrarios; con un cuerpo siempre envía `Content-Type` (por defecto JSON). | No se puede sondear "sin Content-Type" ni `Expect`. Menor. |
| R-03 | El cuerpo se decodifica con `errors="replace"`. | Se pierden bytes no UTF-8 de la respuesta. Menor. |
| R-04 | No hay candado de secuencia por token (H-03). | Si otro agente usa el token a la vez, la evidencia se contamina. Para esta corrida: verificar que los IDs de cada secuencia sean contiguos. |
| R-05 | Cada request reescribe el log completo varias veces (`_replace_entries`). | O(n) por request; aceptable hasta unos pocos miles de líneas, lento cerca de 8.000. |
| R-06 | Una secuencia que ya existe no se puede reabrir con `reset`: hay que usar otro nombre. | Correcto, pero hay que nombrar las secuencias con cuidado. |

**Veredicto:** sirve para la exploración mínima. Lo único que no cubre es el fingerprint por
headers (R-01), y eso no bloquea.

## 5. Plan de exploración mínima (~50 requests)

Reglas: solo `python3 tools/explorer/bb.py`; nunca leer ni imprimir `.env`; sin `--confirm`; cada
secuencia con nombre nuevo; detenerse ante `transport_error`, `RateLimited` o `BudgetExceeded`.

**S1 `s001-corpus` (21 requests):** reset y los 20 ejemplos en orden. Hipótesis: "reproduce
E<n>: <status> <cuerpo>". Comparar status y cuerpo (y `raw`) con el corpus. Anotar `X-Req`.
Responde: si el servicio es determinista y sigue igual que en la mañana, qué es `X-Req` y da IDs
de log citables.

**S2 `s002-precedencia` (12 requests):** reset y luego:

1. `SALDOS;AC-0001;1`, `SALDOS;AC-0001;50`, `SALDOS;AC-0001;99`: ¿E301 antes que el control?
2. `ALTA;Lucia;Gomez;1`, `ALTA;Lucia;Gomez;50`, `ALTA;Lucia;Gomez;99`: ¿E302 antes que el control?
3. `SALDOS;AC-0001;5X`: ¿E201 o E301 primero?
4. `ALTA;Lucia;Gomez;5X`: ¿E201 o E302 primero?
5. `CONSULTA;AC-0009;1`, `CONSULTA;AC-0009;50`: ¿E202 antes que E401?
6. `PING;1`: ¿PING valida el control?

Interpretación: si los tres controles dan el mismo error, ese error va antes que el control. Si
uno solo da el error y el resto E202, el control va antes (y ese valor es el control válido).

**S3 `s003-sobre` (17 requests):** reset y luego:

1. `GET /health`, `GET /health` sin auth.
2. `POST /msg` con `PING;64` y auth `none`, `empty`, `invalid`, `scheme`.
3. `GET /msg`, `GET /no-existe`, `POST /no-existe`, `POST //msg` (`PING;64`).
4. `POST /msg` con cuerpo crudo `{`, con `{}`, con `{"m":64}` y con `{"m":"PING;64","x":1}`.
5. `POST /msg` con `{"m":"PING;64"}` y `Content-Type: text/plain`.
6. `POST /__reset` sin auth.

Responde: auth, rutas inexistentes, métodos, sobre JSON y forma de health y reset, que deciden
cómo se construye el adaptador HTTP (H-05) y si `net/http` sirve tal cual.

## 6. Observaciones de la ejecución

Corrida del 2026-10-10 hecha por un subagente (Sonnet) con `bb.py`. Fueron 50 requests (presupuesto
usado: 0 → 50): S1 = IDs 1–21, S2 = 22–33, S3 = 34–50. Los IDs salieron contiguos, sin líneas de
otros agentes, y todas las entradas quedaron `completed`, sin transporte fallido ni rate limit. Verifiqué
en `experimentos.jsonl` los IDs 1, 13, 16, 21-23, 29, 33, 34, 36, 41, 44-47, 49 y 50. El log quedó
**sin commit** (untracked).

### 6.1 Resultados

**Corpus (S1).** Los 20 ejemplos se reproducen byte a byte (status y `raw`), incluido el espacio
final de E301. El servicio es determinista y a la hora de la corrida seguía en la versión de la
mañana. Los IDs 2–21 del log equivalen a E1–E20 (ID = n + 1) y ya se pueden citar en la especificación.

**Precedencia (S2).**

- E201 (formato del control) va antes que E301 y E302: IDs 29 y 30.
- E202 (valor del control) va antes que E301, E302 y E401: IDs 23–28, 31 y 32, frente a 13, 16 y 21.
- Orden observado: **E201 → E202 → {E301, E302, E401}**. El orden entre E301, E302 y E401 sigue
  abierto: solo se puede medir con un control válido.
- `PING;1` y `PING;64` responden pong (IDs 33 y 2): PING no valida el control, o lo valida de otra
  forma. Confianza: probable.
- Datos nuevos para la fórmula: `SALDOS;AC-0001` → 38 es válido (ID 13). 1, 50 y 99 son inválidos
  para `SALDOS;AC-0001` y para `ALTA;Lucia;Gomez`. 1 y 50 son inválidos para `CONSULTA;AC-0009`.

**Sobre HTTP (S3).**

| Tema | Observado | IDs |
| --- | --- | --- |
| Auth | 401 `{"error":"E001","mensaje":"no autorizado"}`, idéntico para none, empty, invalid y scheme. `/health` y `/__reset` **también** exigen auth. | 36–40, 50 |
| Rutas | 404 `{"error":"E404","mensaje":"ruta desconocida"}` para ruta inexistente, método incorrecto (`GET /msg`, sin 405) y `//msg` (sin normalizar). | 41–44 |
| JSON | `{` → 400 E100 `json inválido`. `{}` y `{"m":64}` → 400 E102 `falta m`. Campos extra se ignoran. `Content-Type` no se valida. | 45–49 |
| Health y reset | 200 `{"ok":true}` los dos. | 34, 35 |
| `X-Req` | Contador que solo avanza con requests autenticados a `/msg` (incluidos E100 y E102). No lo tocan reset, health, 401 ni 404. **`/__reset` no lo reinicia.** | 2–49 |

### 6.2 Impacto en los hallazgos

| ID | Cambio |
| --- | --- |
| H-01 | **Sube de prioridad.** Como el control se valida antes que el comando, la opción B de la estrategia (descubrir comandos sin la fórmula) no sirve. Toca la opción A: fórmula primero. Sin fórmula, cada comando candidato cuesta un barrido de controles. |
| H-03 | Hay mitigación: `X-Req` es un contador continuo, así que un salto dentro de una secuencia delata requests ajenos a `/msg` con el mismo token. Los resets ajenos no se ven en `X-Req`. |
| H-05 | **Confirmado:** `//msg` da 404 E404 sin redirección. `ServeMux` respondería 301 y fallaría. Además, un método incorrecto da 404, no 405. Se necesita un handler propio con catch-all JSON. |
| G-01 | Resuelto en parte: los errores de sobre y ruta son JSON propios del servicio, no páginas del framework. El fingerprint por headers deja de ser necesario para estos casos. |
| G-07 | Las filas de la especificación ya pueden citar IDs 2–50 en lugar de E1–E20. Para pasar a `confirmado` hay que repetirlas. |
| Nuevo N-01 | Hay estado que `/__reset` no borra (`X-Req`). Vigilar si algún comportamiento depende de un contador global (límites diarios, por ejemplo). El reemplazo no necesita reproducir `X-Req`: los headers no se comparan. |
| Nuevo N-02 | `/health` sin token da 401. Readiness del reemplazo: `GET /health` con token devuelve `{"ok":true}`, sin token 401 E001. |

### 6.3 Sondas pendientes (baratas, sin fórmula)

1. Orden entre auth y ruta: ruta inexistente sin token, ¿401 o 404?
2. Orden entre auth y JSON: cuerpo `{` sin token.
3. E101 (hueco en la numeración): body `[]`, `"x"`, `null`, `{"m":""}` y cuerpo vacío.
4. `PING;5X`, `PING`, `PING;64;1`: ¿PING pasa por E201 o E302?
5. Métodos `HEAD`, `OPTIONS` y `PUT` sobre `/msg` y `/health`.

### 6.4 ¿Se puede cerrar el diseño?

Sí. La exploración respondió las tres preguntas de arquitectura:

- El sobre HTTP es reproducible con un handler propio.
- El servicio es determinista.
- El cuello de botella es la fórmula del control.

Antes de cerrar, falta reflejar en `docs/system-design.md` estos puntos: H-05 confirmado, el orden
E201 → E202 → resto, auth en las tres rutas, el catch-all 404, la prioridad de H-01 y las
capacidades O-01 a O-03. Sigue sin resolverse H-02 (zona horaria).


## 7. Registro de atención de Codex - 10 de octubre de 2026

Se corrige el diseño y se enlaza con evidencia existente; **no se declara implementado el servicio Go**. No se hicieron nuevas solicitudes al original.

| ID | Atención | Estado al cerrar esta tanda |
| --- | --- | --- |
| H-02 | Se preserva la decisión previa del usuario (Bogotá) y se añaden dos replays manuales ante la zona oficial no confirmada; entrega por el plazo más temprano. | Mitigado en diseño; confirmación oficial pendiente |
| G-04 | Corte de fórmula 18:00, replay final 18:30, despliegue 19:15, congelado 19:30 y entrega 20:00 Bogotá, con equivalencias CDMX/UTC. | Resuelto en diseño; ejecución pendiente |
| H-01, G-05 | Se prioriza control tras E201/E202; plan B explícito y supuesto, con corte y sondas UTF-8. | Plan B documentado; fórmula e implementación pendientes |
| H-05 | Handler propio sin ServeMux ni limpieza, 404 E404 con IDs 41-44. HEAD, escapes y transporte siguen abiertos. | Resuelto en diseño; implementación pendiente |
| O-02 | Captura exacta/base64, secuencias, redacción de secretos, rotación y replay por cliente instrumentado antes del corte. | Resuelto en diseño; implementación pendiente |
| G-02 | Validar temprano el esqueleto, revisar límite del evaluador y conservar resultados. | Procedimiento añadido; despliegue pendiente |
| H-04 | Revalidación de todas las filas vigentes por epoch; historial no se presenta como regla actual. Replay incluye sobre HTTP. | Resuelto en procedimiento; replay tras cambio pendiente |
| O-01 | BEHAVIOR_VERSION solo al arrancar, delta v2 sobre v1, rollback sin recompilar y esquema común. | Resuelto en diseño; implementación pendiente |
| H-06 | Mantener servicio hasta conocer evaluación final, revisar créditos y no desplegar durante validación. | Mitigado; cuenta y continuidad sin verificar |
| N-02, G-03 | Auth de health/reset documentada con IDs; supuesto explícito para tokens distintos al equipo. | Resuelto en diseño/spec; implementación pendiente |
| G-06 | int64 y serialización sin .0; decimales, exponentes y overflow pendientes de sondas. | Resuelto en diseño; límites pendientes |
| G-07 | Especificación separada en docs/specification.md, siete secciones y citas de IDs reales 1-50. | Separación y citas resueltas; repetición confirmatoria pendiente |
| G-08 | Auditoría completa y exportación de evidencia válida conservando IDs; intentos inciertos separados y nunca usados como prueba. | Criterio documentado; exportador/criterio organizador pendientes |
| O-03 | Resúmenes internos, p95, defaults y alertas >1 s, sin rutas extra. | Resuelto en diseño; implementación pendiente |
| PNG | Una fuente architecture.mmd encontrada; renderer exporta SVG y PNG reproducibles e incluye configuración/captura. | Generado y revisado visualmente |

Siguientes trabajos que requieren implementación o evidencia nueva: H-03 (exclusión de secuencias por token), las sondas de §6.3, esqueleto desplegable y replay final. La corrección documental no sustituye ninguno de esos trabajos.

Verificación de esta tanda: 20 respuestas del corpus coinciden con el log; todas las citas de IDs existen y corresponden a intentos completed sin infraestructura; cuerpos exactos de errores contrastados con el log. PNG y PDF de 9 páginas revisados visualmente. `git diff --check` sin errores.

## 8. Cierre de decisiones pendientes de diseño

Por indicación del usuario, H-02 queda fuera del trabajo: los tiempos se controlan manualmente.
Se actualiza `docs/system-design.md`, fuente del PDF, con las decisiones siguientes. No se
declara implementado el servicio, ejecutadas las sondas ni verificada la cuenta de hosting.

| Prioridad | Pendiente revisado | Corrección incorporada | Estado |
| --- | --- | --- | --- |
| P0 | H-01, G-05: fórmula del control. | Candidatos explícitos, pares con una sola variación, casos nuevos reservados y UTF-8; confirmación repetida por epoch y fallback activado por operador. | Plan cerrado; fórmula requiere evidencia. |
| P0 | Modelo definitivo de estado. | Esquema de cuentas, operaciones con deltas y contadores; supuestos de IDs/reset y secuencias para errores, anulaciones y reinicios. | Diseño concretado; semántica requiere sondas. |
| P0 | H-04: versión vigente. | Manifiesto por regla, replay sin caché, evidencia nueva, deltas y casos incompletos separados; promoción y rollback por corpus de versión. | Procedimiento cerrado; replay pendiente. |
| P1 | H-03: exclusión de secuencias. | flock por token durante toda la secuencia, runner propietario, recuperación sin robar locks y coordinación entre máquinas. | Diseño cerrado; implementación y prueba pendientes. |
| P1 | §6.3: precedencia y protocolo. | Orden provisional marcado supuesto y matriz de auth, JSON, PING y métodos; no inferir E101 por numeración. | Plan cerrado; respuestas exactas requieren sondas. |
| P1 | H-05: transporte HTTP. | Routing con ruta escapada original, matriz de escapes/HEAD/Expect y captura base64 en cliente; adaptación condicionada a evidencia. | Diseño cerrado; límites requieren verificación. |
| P1 | G-06: números. | Parseo exacto y matriz de formatos/fronteras; overflow previo a escritura y enteros arbitrarios si la evidencia supera int64. | Diseño cerrado; errores y rangos requieren sondas. |
| P1 | H-06, N-02: despliegue. | Gate de volumen, créditos, recuperación y smoke test; readiness autenticado o proceso/TCP sin nueva ruta; respaldo consistente probado. | Procedimiento cerrado; hosting requiere verificación. |
| P1 | G-08: entrega del log. | Auditoría canónica completa conserva ID/línea; evidencia filtrada solo auxiliar, exclusiones y manifiesto; validador de citas/epoch/secuencias/secretos. | Contrato interno cerrado; exportador pendiente. |
| P2 | A-01: almacenamiento. | Un solo adaptador SQLite con modernc.org/sqlite, bases temporales para pruebas y solo interfaz Store. | Decisión cerrada; implementación pendiente. |

Corrección respecto a la sección 7: la exportación filtrada ya no sustituye el log de entrega,
porque dejaría huecos en los IDs y omitiría intentos al original. No se añaden afirmaciones
confirmadas a la especificación sin evidencia nueva. El PDF se regenera desde el diseño y
la especificación actuales, no desde las tablas históricas de esta revisión.
