# Progreso · exploración e implementación

Tablero vivo. Lo cerrado sale del tablero y pasa a la [especificación](docs/specification.md)
o al [diseño](docs/system-design.md). Historia de la etapa de diseño (entrevista Q1–Q11,
hosting, coordinación pi/Codex): [docs/archive/progress-diseno.md](docs/archive/progress-diseno.md).

## Estado ahora

- **Fase:** A0, A1, A2, A3, A4 y B1 completados (A4 integrado en master mediante fast-forward autorizado, 1598e36); fórmula del control confirmada y línea base completa revalidada. A2 integrado en master mediante fast-forward autorizado (d3abf21); A1 integrado en 310a1be.
- **Versión observada:** `v1`, revalidada a las 15:00 de Bogotá. Último ID del log: 1381 (A4 cerró a las 15:28:23, antes del cambio; intentos 51 y 226 sin respuesta).
- **Próximo paso:** B7 (`BEHAVIOR_VERSION=v2` con CAM-V2-1…3; NOTAS/HALT no son delta, existen en v1 y v2) y B5 (SQLite tras el contrato Store de B4); A7 antes de las 18:30.
- **Versión vigente:** `v2` desde algún momento entre las 15:48:49 (ID 1996, aún v1) y las 16:24:51 (ID 2004). A6 encontró exactamente 3 deltas (spec §6); A5 respondió como v1.
- **Bloqueos:** ninguno.

## Hitos de hoy (Bogotá, UTC−5)

- [x] 13:15 · A0 listo (completado a las 13:59): cliente con base64, `--no-cache`, runner de secuencias con lock.
- [x] 15:00 · Fórmula del control con candidato validado (A1 completado a las 14:42; objetivo, no corte).
- [x] 15:20 · **Línea base `v1` completa** en `tests/corpus/` (A2; revalidada a las 15:00).
- [x] 15:35 · Primer replay tras el cambio anunciado (A6; completado a las 16:27, base completa, 3 deltas).
- [x] 16:35 · Segundo replay (innecesario: el canario de las 16:24 ya era v2; sondas repetidas a las 16:46).
- [ ] 18:00 · Corte de la fórmula: si no está confirmada, activar plan B (INT-04).
- [x] 18:30 · Replay final sin caché sobre la versión vigente (A7; completado a las 17:25, 842/842 iguales a A6).
- [ ] 19:15 · Último despliegue.
- [ ] 19:30 · Congelar código y configuración; smoke test público.
- [ ] 20:00 · Entrega.

## Tablero A · Exploración (Python, `tools/explorer`)

| Paso | Qué | Presupuesto | Depende de | Responsable | Estado | IDs del log |
| --- | --- | --- | --- | --- | --- | --- |
| A0 | Completar `bb.py`: request/response en base64, `--no-cache`, runner de secuencias (reset + lock por token mientras dura la secuencia, entre procesos de esta máquina). | 0 | — | Codex (orquestación), Luna (revisión/pruebas) | Completado | — (0 requests) |
| A1 | **Fórmula del control:** pares mínimos sobre ALTA/CONSULTA que cambien una sola propiedad (longitud, caja, acento, separador, ceros) y búsqueda de candidatos 0–99 con parada al primer control compatible; validar candidatos con mensajes reservados. | ≤100 por tanda | A0 | Codex (orquestación), Luna (análisis/revisión) | Completado | 52–225 (51: fallo DNS sin evidencia) |
| A2 | **Línea base `v1`:** corpus de ejemplos, secuencias 1–50 y lo de A1 en `tests/corpus/`; repetir sin caché. | ≤250 (225 consumidas) | A0 | Codex (orquestación), Luna (herramientas/revisión) | Completado | 227–450 (226: fallo sin respuesta) |
| A3 | **Estado:** consumo de IDs ante errores, anulación de transferencias, ANULA sobre operación inexistente, alcance del reset, naturaleza del límite E506. | ~500 (800 aprobados; 436 consumidas) | A0 (mejor con A1) | claude (orquestación), Haiku (minería/auditoría) | Completado | 451–886 (618: TEAM_TOKEN rechazado) |
| A4 | **Sobre HTTP y números:** matriz de cierre del diseño (precedencia auth/ruta/JSON, cuerpos, HEAD/OPTIONS, escapes) y bordes (`0`, `-1`, `+1`, `01`, `1.0`, int64). | ~300 (500 aprobados; 495 consumidas) | A0 | claude (orquestación), Haiku (auditoría) | Completado | 887–1381 |
| A5 | **Descubrir comandos** por diccionario (RETIRO, MOVIMIENTOS, CIERRE…). | ~500 (900 aprobados; 617 consumidas) | A1 | claude (orquestación), Haiku (diccionario/auditoría) | Completado | 1382–1998 |
| A6 | **Detección del cambio (incidente [FR-0153](docs/old-system/incidente-FR-0153.md)):** replay de la base `v1` contra v2 y sondas mínimas hasta aislar **exactamente 3 deltas**. Cada delta va al log con `hipotesis`, a la spec §6 (CAM-V2-1…3) con IDs v1/v2 y al debrief. | ~900 (1.000 aprobados; 980 consumidas) | A2 | claude (orquestación), Haiku (auditoría) | Completado | 1999–2978 |
| A7 | Replay final sin caché de la versión vigente. | ~300 (1.000 aprobados; 992 consumidas) | A6 | claude (orquestación), Haiku (auditoría) | Completado | 2979–3970 |

Al cerrar cada tanda: `conclude` en el log, actualizar la fila de la spec con sus IDs y
commit aparte de `experimentos.jsonl` (`git add experimentos.jsonl` explícito, sin `bb.py` corriendo).

## Tablero B · Implementación (Go)

| Paso | Qué | Depende de | Responsable | Estado | Commit |
| --- | --- | --- | --- | --- | --- |
| B1 | `go.mod`, `cmd/replacement`, handler propio: auth, `/health`, `/__reset`, 404 E404, E100/E102 (casos del log 34–50). Captura íntegra de toda request recibida (seed para replay local). | — | claude | Completado | 4a2d32d…fc09d12 |
| B1a | **Sobre según A4:** invertir precedencia (ruta → auth → tamaño → JSON), tope 8192 bytes con 413 E101; deltas 1–6 en [informe A4](docs/research/envelope-a4.md#deltas-para-el-handler-go-tablero-b). | B1; A4 | claude (en rama feat/b4-engine) | Completado | d22dc21, 4acc907 |
| B2 | **Arnés diferencial:** test Go que lee secuencias de `tests/corpus/` y compara status y bytes. | B1 | claude | Completado | c5fe3f7…cc0be67 |
| B3 | `internal/protocol`: parser de `m`, E201 y control tras una sola función (primero plan B; luego la fórmula de A1). | B1; A1 | claude (orquestación), Haiku (minería/auditoría) | Completado | a8867ee…0043ef2 |
| B4 | `internal/engine` + `state`: seis comandos, orden E201→E202→E301/E302/E401, E506/E507, sin corregir `recieved` ni espacios. | B3; A3 | claude (orquestación), Haiku (minería/auditoría) | Completado | a6f553b…6178271 |
| B5 | `internal/storage/sqlite` (`modernc.org/sqlite`): contrato Store, reset atómico, prueba de reinicio. | B4 | Codex (orquestación/implementación), Luna (exploración/revisión) | Completado | 0e45b5b, 9cffd3d; f22ea48…202b3f4 |
| B6 | **Exposición:** primero local + ngrok con smoke test público; luego desplegar en Railway (volumen, una réplica, Serverless apagado) y mantenerlo si funciona. | B1 (temprano), B5 (final) | — | Pendiente | — |
| B7 | `BEHAVIOR_VERSION=v2` con los 3 deltas de A6 y sus regresiones; v2 es el objetivo de conformidad. | A6 | Codex (orquestación/implementación), Luna (evidencia/revisión) | Completado | 01d46d7, 3ce03ad, c5179bc; ac406e6, 440449f, f56e0ec, ebcd1f2 |
| B8 | Congelar: replay local del corpus vigente, smoke test público, entrega. | todo | — | Pendiente | — |

Cada paso termina con `go test ./...` en verde y commit atómico convencional.

### Diferido (P2, confirmado por el usuario)

Diseñado en `docs/system-design.md`, sin impacto directo en el puntaje; solo si sobra tiempo:
métricas p95 y alertas, rotación del log de captura del evaluador, exportador de
`evidencia.jsonl` con manifiesto y hashes, coordinación del lock entre varias máquinas.
La captura de requests del evaluador sí se hace, en versión simple (JSONL a stdout).

## Hipótesis activas

Se borran cuando pasan a la spec con IDs.


## Decisiones vigentes

- Go con `net/http` y handler propio, un proceso, una réplica. ([diseño](docs/system-design.md#arquitectura-y-decisiones))
- SQLite por defecto (`STATE_PATH`); `STORAGE=memory` volátil opcional (B5), contrato Store único.
- Exploración en Python; `tools/explorer/bb.py` es la **única** vía al original. El runtime nunca lo importa ni recibe `BB_TOKEN`.
- Exposición: local + ngrok primero; Railway después, se mantiene si funciona.
- Reglas por `BEHAVIOR_VERSION` (`v1`/`v2`) leída al arrancar; nunca por reloj.
- Plan B del control (INT-04) solo si a las 18:00 no hay fórmula confirmada.
- Fidelidad antes que corrección: typos, espacios y claves heterogéneas se conservan.

## Coordinación entre agentes

Trabajan varios agentes en paralelo, sin reparto fijo por herramienta ni por etapa.

- **Tomar una tarea:** releer este archivo, poner tu nombre en «Responsable» y el estado en «En curso» con una edición pequeña y exacta. No tomar una tarea que ya tiene responsable.
- **Editar:** solo filas propias y el registro, por adición. Nunca reescribir el archivo ni reordenar secciones.
- **Token compartido:** un token, 8.000 req/día. Todo pasa por `bb.py`; revisar `python3 tools/explorer/bb.py budget` antes de cada tanda. Hasta que A0 esté listo, solo un agente lanza secuencias contra el original.
- **Commits:** cada agente commitea solo sus cambios.

**Mensajes** (con autor):

- [claude → B1a/B3] A4 contradice el supuesto ENT-05 de B1: la ruta se evalúa antes que la auth. El handler necesita los deltas del [informe A4](docs/research/envelope-a4.md#deltas-para-el-handler-go-tablero-b); B3 debe implementar E103, la excepción de PING (INT-11) y `sugerencia` en E301.
- [claude → B7] A7: la v2 vigente es la misma de A6 (842/842 iguales). Reglas nuevas de E510 para B7: orden E303 → E304 → E401 → E510 → E506 → E507; solo E506/E507 suman a la racha y E303/E304/E401 son neutros; DEPOSITO con error no libera; `intentos` vuelve a 1 en cada bloqueo. Suite v2 incluye `a7-v2r-sonda-*` ([informe A7](docs/research/replay-a7.md#regla-v2-completa-del-bloqueo)).
- [claude → B4/B7] A6: v2 tiene exactamente 3 deltas: (1) CONSULTA devuelve `saldo` como string con dos decimales (entero/100, `"400.00"`); (2) E506 con TRANSFER > 50000 (antes > 100000); (3) E510 423 `cuenta bloqueada` con `intentos` tras 3 TRANSFER fallidos seguidos (E506/E507) del origen; solo DEPOSITO lo libera. Reglas, IDs y lo no medido en el [informe A6](docs/research/deltas-a6.md#para-el-reemplazo-b7). Suite `tests/differential/v2.json` + `pending-v2.txt` lista; añadir `v2` a `config.Versions` es de B7 (cambia el default). A5 respondió como v1: NOTAS/HALT existen en ambas versiones.
- [claude → B3/B4] A5 (`v2`): hay dos comandos más, `NOTAS` (aridad 0, 200 con nota fija) y `HALT` (aridad 1, 409 E520 sin cambios observados; medido con `x`, otros argumentos como supuesto) y `POST /internal/export-docs` responde E404. Los dos entran en el conjunto de sugerencias de E301. Cuerpos y orden en el [informe A5](docs/research/commands-a5.md#deltas-para-el-reemplazo-tablero-b).
- [claude → A6/B5/B7] B4: NOTAS y HALT activos en todas las versiones (spec CMD-VERSION); si A6 los identifica como delta, B7 los condiciona por `BEHAVIOR_VERSION`. El motor no tiene bifurcación por versión y `config.Versions` solo tiene `v1`: B7 añade `v2`. B5 implementa `engine.Store` (`Update` atómico serializado, `Reset`) sobre SQLite y retira `MemoryStore` de producción (MEM-07). La captura (B1) lee el cuerpo sin tope antes del handler: respuestas correctas, pero un cuerpo enorme ocupa memoria.

## Registro

Solo por adición, una línea por evento, con autor y hora de Bogotá.

- [claude] 2026-10-10 12:48: archivada la bitácora de diseño; tablero reorganizado con el plan A0–A7 / B1–B8.
- [claude] 2026-10-10 12:50: usuario confirma el diferido P2.

- [codex] 2026-10-10 13:46: A0 reclamado; base64, no-cache, runner con lock por token y entrada make run documentada; pruebas sin requests al original.

- [codex] 2026-10-10 13:59: A0 completado en de50612: request/response base64, --no-cache, runner con lock por token; make explore documentado (nombre solicitado por el usuario). 23 pruebas locales en verde; 0 requests al original. Luna revisó y amplió pruebas. A1 y A2 desbloqueados.

- [claude] 2026-10-10 14:02: B1 reclamado en rama feat/b1-handler; incluye captura íntegra de requests del evaluador (método, ruta cruda, headers sin secretos, cuerpo base64, respuesta) como seed local.

- [claude] 2026-10-10 14:09: B1 completado (4a2d32d…fc09d12, ff a master): handler con auth/health/reset/E404/E100/E102 y stub PING (19 casos del log 2, 33–50 en verde), captura JSONL de todo request en `CAPTURE_PATH` + stdout con token redactado, `make serve` (:9900), `make test-go`, `make seeds` para convertir capturas o logs en semillas. Límites: lo que net/http rechaza antes del handler no se captura; cuerpo sin tope de tamaño. 0 requests al original. B2 desbloqueado.

- [codex] 2026-10-10 14:10: corregido P1 de revisión A0: migración de cuota filtrada por token_tag y día, sin atribuir entradas sin etiqueta; rate limits laterales etiquetados. Regresión con dos tokens y log común reproduce el fallo antes del fix; 25 pruebas en verde después. 0 requests al original.

- [claude] 2026-10-10 14:21: revisión de B1 corregida (d76cf00, 232337b): la captura conserva el error de lectura del cuerpo (antes un cuerpo truncado daba 200 en vez de E100) y registra solo el cuerpo que sale al cable (HEAD, 204/304 vacíos).

- [codex] 2026-10-10 14:26: A1 reclamado en feat/a1-control, worktree separado; bb.py sin cambios, cuota compartida con el coordinador original y exploración centralizada.

- [codex] 2026-10-10 14:42: A1 completado en feat/a1-control: fórmula A=1…Z=26, filtrado ASCII antes de caja, decimal +00 y 98−(resto módulo 97), sin reducción final. Nueve mensajes reservados/vecinos repetidos desde dos resets; bordes 97/98 y Unicode revalidados. IDs 52–225, intento 51 DNS excluido de evidencia; 175 reservas nuevas, cuota 225/7800, quedan 7575. bb.py sin cambios; fixtures tests/corpus/a1, herramienta offline y escáner instrumentado. B3 desbloqueado; A2/A6 siguen pendientes. Rama sin mezclar, a la espera de autorización del usuario.

- [codex] 2026-10-10 14:45: cierre de auditoría A1: 44 pruebas Python y go test ./... en verde; Luna confirma fórmula en 167 mensajes y trazabilidad/bytes en 174 fixtures. Actualización mínima del resumen e hitos propios de A0/A1 para retirar la cabecera desactualizada, sin alterar filas de otras tareas. Fast-forward posible desde master; mezcla pendiente de autorización.

- [codex] 2026-10-10 14:50: revisión de cobertura A1: 0–99 es el rango de candidatos con parada al primer acierto, según estrategia inicial §2.3; no exige barrido exhaustivo. ALTA A se barró 0–62 (IDs62–124); vecino63 rechazado después (ID147). Informe y tablero aclarados; sin nuevas llamadas ni cambios en bb.py; mezcla sigue pendiente de autorización.

- [codex] 2026-10-10 14:51: usuario autoriza mezcla; feat/a1-control integrado en master con git merge --ff-only hasta 310a1be, sin commit de merge. Checkout verificado limpio tras el fast-forward; sin nuevas llamadas al original.

- [codex] 2026-10-10 14:55: A2 reclamado en feat/a2-baseline; usuario aprueba techo de 250 requests (224 previstos: IDs 1–50 y 52–225, resets incluidos). Los ejemplos ya están en s001; ID51 sin respuesta excluido. Luna prepara herramientas y revisión offline; ejecución centralizada mediante bb.py.

- [codex] 2026-10-10 15:03: A2 completado en feat/a2-baseline: diez secuencias y 224 respuestas revalidadas sin caché entre 15:00:19 y 15:00:56 de Bogotá, antes del cambio anunciado. IDs 227–450, cero deltas de contrato y cero deltas en 174 comparaciones de bytes; 50 casos históricos ahora tienen bytes nuevos sin fabricar los anteriores. Intento 226 de transporte excluido de evidencia; consumo A2 225/250, cuota 450/7800. Herramientas y corpus histórico 37d0a30, log aparte edc882c; auditoría Luna independiente, 57 pruebas Python y go test ./... en verde. Spec e informe A2 documentan el alcance; B2/A6 tienen corpus. Rama sin mezclar.

- [codex] 2026-10-10 15:05: usuario autoriza mezcla; feat/a2-baseline integrado en master con git merge --ff-only hasta d3abf21, sin conflictos ni commit de merge. Corpus, spec y log auditados por Luna; checkout limpio tras el fast-forward. Sin nuevas llamadas al original durante la integración.

- [claude] 2026-10-10 15:20: A3 completado en feat/a3-state, antes del cambio: 25 secuencias en tests/corpus/a3 (IDs 451–670) y repetición sin caché 671–886, 216/216 iguales. Errores, ANULA, PING y CONSULTA no consumen IDs; ANULA revierte sin comprobar saldo (saldos negativos); E506 = TRANSFER > 100000 por operación; reset solo POST autenticado; nuevos E104 y E304 con orden medido. TEAM_TOKEN da 401 en el original (618): aislamiento queda supuesto. Spec §1–5/§7 e informe docs/research/state-a3.md. B4 desbloqueado; A6 debe repetir tests/corpus/a3 con BB_EPOCH=v2. Rama sin mezclar.

- [claude] 2026-10-10 15:20: B2 reclamado en feat/b2-differential: arnés Go sobre los registros de evidencia (replay A2 y repetición A3), igualdad status + bytes exactos, lista de pendientes por versión. Sin exportador (A2 ya fijó el formato). 0 requests al original.

- [claude] 2026-10-10 15:22: B2 completado en feat/b2-differential (c5fe3f7…cc0be67): `tests/differential` reproduce la suite `v1.json` (replay A2 227–450 y repetición A3 671–886: 35 secuencias, 440 pasos) contra `internal/app` sobre httptest, status + bytes exactos con pista de equivalencia JSON. `pending-v1.txt` lista 34 secuencias que B3/B4 deben sacar (hoy solo coincide s003-sobre); el test falla si una pendiente ya pasa o no existe. `make differential [BEHAVIOR_VERSION=…]`; formato en `tests/differential/README.md`. 0 requests al original. Rama sin mezclar.

- [claude] 2026-10-10 15:28: revisión adversaria de B2 corregida (a99e09c…7c2df2e): pendientes por paso como trinquete (falla ante regresión o paso ya resuelto; `-update-pending` regenera), versión desconocida o sin suite falla en vez de skip, timeout de 5 s por paso con cuerpo incluido. 0 requests al original.

- [claude] 2026-10-10 15:31: segunda revisión de B2 corregida: `-update-pending` falla sin escribir si se filtró con `-run` o hubo errores (antes reducía la lista a lo ejecutado).

- [claude] 2026-10-10 15:22: A4 reclamado en feat/a4-envelope (worktree ../10102026-a4); usuario aprueba techo de 500 requests, variantes nuevas de auth en bb.py con pruebas y alcance solo exploración+spec (ajustes del handler Go quedan anotados para el tablero B).

- [claude] 2026-10-10 15:45: A4 completado en feat/a4-envelope, antes del cambio (15:25:11–15:28:23, v1): IDs 887–1381, 495/500 requests; secuencias 01–18 repetidas sin caché, 241/241 iguales; 19–20 con una pasada. Precedencia ruta → auth → tamaño (E101, 8192 bytes) → JSON; nuevos E101, E103 y `sugerencia` en E301; control bien formado = 1–2 dígitos ASCII; PING sin integridad pero con aridad cero; montos enteros positivos sin ceros iniciales y con tope de 10 dígitos; comandos sin distinguir caja. Spec §1–3, §5 y §7 e informe docs/research/envelope-a4.md. Deltas del handler en la fila nueva B1a. Rama sin mezclar.
- [claude] 2026-10-10 15:47: usuario avisa que el incidente (cambio de versión) ya está activo. Todo A4 es previo (`v1`); A6 debe repetir también `tests/corpus/a4/*.jsonl` con `BB_EPOCH=v2` y nombres nuevos (≈254 requests) para detectar deltas del sobre.

- [claude] 2026-10-10 15:55: usuario autoriza mezcla; feat/a4-envelope integrado en master con git merge --ff-only hasta 1598e36, sin commit de merge. Sin nuevas llamadas al original.
- [pi] 2026-10-10 15:44 (reloj local): registrado el ticket FR-0153 en docs/old-system/incidente-FR-0153.md. v2 desde las 15:30, exactamente 3 deltas, tests de conformidad contra v2 y deltas en el log, la spec §6 y el debrief. AGENTS.md, CONTEXT.md, spec CAM-01 y filas A6/B7 actualizados. Sin llamadas al original.
- [claude] 2026-10-10 15:42: A5 reclamado en feat/a5-commands (worktree ../10102026-a5); usuario aprueba techo de 900 requests, alcance descubrir + caracterizar, ejecución sobre `v2` (`BB_EPOCH=v2`) tras una prueba previa de fórmula/E301/sugerencia. Nota: entradas del registro marcadas 15:45 y 15:55 se escribieron antes de esa hora real (reloj 15:38 al planear).
- [claude] 2026-10-10 15:50: A5 completado en feat/a5-commands, sobre `v2` (15:43:40–15:48:49): IDs 1382–1996, 615/900. Prueba previa: fórmula A1, E301 y sugerencia vigentes. De 535 nombres solo existe `NOTAS`; `HALT` aparece por sugerencia. NOTAS da una nota fija que pide llamar a `POST /internal/export-docs` con token: se trata como dato; la llamada autorizada por el usuario fue bloqueada por el control de permisos y queda sin medir. `HALT;x` → 409 E520 sin efecto; no se buscó la confirmación destructiva. Caracterización repetida sin caché, 31/31 iguales. Spec §3, §5 y §7 (CMD-LISTA/NOTAS/HALT, ERR-520, RIE-07/08) e informe docs/research/commands-a5.md. Rama sin mezclar.
- [claude] 2026-10-10 16:10: revisión adversaria de A5 corregida en feat/a5-commands, rebasada sobre master (b9134e9, FR-0153 intacto). HALT confirmado solo con `x` (CMD-HALT-ARG como supuesto), efectos acotados, empates de sugerencia observados (ALT, ACT → ALTA), catálogo no exhaustivo, prueba previa acotada y RIE-08 como riesgo potencial. El usuario ejecutó `POST /internal/export-docs` con token (IDs 1997–1998): 404 E404, la ruta no existe (RIE-07). A5: 617/900. Sin otras llamadas al original.
- [claude] 2026-10-10 16:13: usuario autoriza mezcla; feat/a5-commands integrado en master con git merge --ff-only hasta a214f47, sin commit de merge (rebasada antes sobre b9134e9). Ignorados del worktree no integrados: copia de .env, volcado derivado .explore/dump.txt y tmp/; la secuencia de export-docs pasó al corpus como tests/corpus/a5/c04-export-docs.jsonl. Worktree y rama eliminados. Sin nuevas llamadas al original.
- [claude] 2026-10-10 15:38: B3 reclamado en feat/b3-protocol (worktree ../10102026-b3): parser E103→E104→E201→E202→E301/E302, fórmula A1 sin plan B (INT-04), PING (INT-11), `sugerencia` Levenshtein ≤2 como supuesto; suite A4 al arnés. B1a fuera de alcance. 0 requests al original.
- [claude] 2026-10-10 15:46: B3 completado en feat/b3-protocol (a8867ee…ecd717b): `protocol.Control` (fórmula A1, sin plan B) y `protocol.Parse` con E103 → E104 → E201 → E202 → (E301 con `sugerencia` \| E302), PING sin integridad; /msg delega en el parser, PING responde y los comandos con estado dan 501 hasta B4 (`WithExec`). 173 casos sin estado del log en `internal/protocol/testdata/log-cases.json` (`tools/explorer/protocol_cases.py`). Arnés: suite A4 añadida y variantes de auth lower/spaces/bare; pendientes v1 resuelven 142 pasos sin regresiones (A4 nuevo solo pendiente de B1a y B4). Spec INT-12 y ERR-301 (supuestos). Auditoría Haiku: 3 hallazgos menores corregidos. 0 requests al original. Rama sin mezclar.
- [claude] 2026-10-10 15:54: revisión adversaria de B3: Spec sin hallazgos; Standards P2 aceptado y corregido (0043ef2): `protocol_cases.py` toma los cuerpos de `response_b64`, no de `raw`, y rechaza bytes no UTF-8; pruebas en `test_protocol_cases.py`; fixture regenerado idéntico. 0 requests al original.
- [claude → B4/B7] 2026-10-10 16:15: B3 rebasada sobre A5 (fd5a4cb) sin cambios de código. La tabla de comandos de `internal/protocol` solo tiene los seis de v1: `NOTAS` (aridad 0) y `HALT` (aridad 1), observados en `v2`, hoy dan E301 y no entran en `sugerencia`. Al añadirlos, respetar los empates observados (`ALT`, `ACT` → ALTA antes que HALT, ERR-301) y decidir por `BEHAVIOR_VERSION` si aplican a v1. Fixture `log-cases.json` (solo v1) sin cambios.
- [claude] 2026-10-10 16:15: usuario autoriza mezcla; feat/b3-protocol rebasada sobre fd5a4cb (A5) e integrada en master con git merge --ff-only hasta 98debd3, sin commit de merge; conflictos solo de adición en PROGRESS y ERR-301 (texto de A5 conservado + supuesto B3). go test ./... en verde. Worktree y rama eliminados; tmp/review-b3 movido al tmp/ local. Sin llamadas al original.
- [claude] 2026-10-10 16:21: B4 reclamado en feat/b4-engine (worktree ../10102026-b4), con B1a en commits aparte. Decisiones del usuario: store en memoria transitorio tras el contrato Store (B5 lo cambia por SQLite); NOTAS y HALT en la tabla de comandos para todas las versiones (A6/B7 los condicionan si resultan ser delta). 0 requests al original.
- [claude] 2026-10-10 16:29: B4 y B1a completados en feat/b4-engine. B1a: ruta → auth (d22dc21) y tope 8192/E101 en /msg (4acc907). B4: `internal/state`, `internal/engine` con contrato Store y store en memoria transitorio, ERR-ORD de DEPOSITO/TRANSFER, montos CMD-MONTO, ANULA sin chequeo de saldo, NOTAS/HALT en la tabla de comandos (fixture `log-cases-v2.json`, 545 casos A5) y motor conectado en app (a6f553b…3174b1a). Suite diferencial v1: 55/55 secuencias, `pending-v1.txt` vacío. Auditoría Haiku: réplica de las 1996 respuestas del log (v1 y v2) contra app.New, 1986 iguales; las 10 restantes son ID 618 (ENT-08) y HEAD vía recorder (cuerpo vacío en servidor real). Supuestos en spec ENT-12, CMD-VERSION, MEM-07. 0 requests al original. Rama sin mezclar.
- [claude] 2026-10-10 16:36: revisión adversaria de B4 (Spec sin hallazgos; Standards 3 P2) corregida: contadores int64 (a2527b6), desbordamiento de saldos comprobado antes de escribir con state.ErrOverflow → 500 E500 de MEM-07 (83fb82f) y motor sin net/http (5103b3b). go test -race ./... y diferencial v1 sin pendientes en verde. 0 requests al original.
- [claude] 2026-10-10 16:38: usuario autoriza mezcla; feat/b4-engine integrado en master con git merge --ff-only hasta 39325fd, sin commit de merge. go test ./... en verde. Worktree (sin ignorados) y rama eliminados. Sin llamadas al original.
- [claude] 2026-10-10 16:24: A6 reclamado en feat/a6-v2-deltas (worktree ../10102026-a6); usuario aprueba techo de 1.000 requests, debrief nuevo en docs/debrief.md, suite diferencial v2 y re-etiquetar A5 si el testigo lo exige. Incidente confirmado activo (ticket recibido 15:44): replay completo sin esperar a 16:31.
- [claude] 2026-10-10 16:53: A6 completado en feat/a6-v2-deltas, sobre `v2`: IDs 1999–2978, 980/1.000. Canario s001 (16:24:50) ya v2; replay sin caché de toda la base A2+A3+A4+A5 (725 pasos, 2020–2744): 78 deltas, todos explicados por 3 causas (59 formato de saldo, 12 E506, 1 E510, 14 cascadas); sondas 2745–2861 repetidas 2862–2978, 117/117 iguales. CAM-V2-1 saldo string con dos decimales, CAM-V2-2 límite > 50000, CAM-V2-3 bloqueo E510 (ausencia en v1 inferida). A5 (15:48) respondió como v1; ventana del cambio 15:48:49–16:24:51 (CAM-04). Spec §6, informe docs/research/deltas-a6.md, docs/debrief.md, suite diferencial v2. Auditoría Haiku: clasificación confirmada; un conteo corregido. Rama sin mezclar.
- [claude] 2026-10-10 17:02: revisión adversaria de A6 sin hallazgos nuevos; usuario decide mantener CAM-V2-3 (bloqueo E510) como delta pendiente de confirmar con las pruebas de conformidad (spec, informe y debrief lo marcan). Sin llamadas al original.
- [claude] 2026-10-10 17:03: usuario autoriza mezcla; feat/a6-v2-deltas (rebasada sobre B4, 364ec17) integrada en master con git merge --ff-only hasta 5dd6db1, sin commit de merge. go test ./... y pruebas del explorador en verde. Worktree (ignorados: copia de .env, .explore/pending.jsonl vacío) y rama eliminados. Sin llamadas al original.

- [codex] 2026-10-10 16:43: B5 reclamado en feat/b5-sqlite (worktree tmp/worktrees/b5), con autorización del usuario. SQLite persistente, reset atómico y prueba de reinicio; configuración STORAGE=sqlite|memory solicitada por el usuario, SQLite por defecto y memoria volátil opcional (amplía la decisión previa de adaptador único). Sin llamadas al original.

- [codex] 2026-10-10 16:51: B5 completado en feat/b5-sqlite (worktree tmp/worktrees/b5), sin mezclar. Store SQLite v1 con driver Go puro, escrituras incrementales, Update con rollback y Reset transaccional; STATE_PATH, apertura antes de escuchar y cierre tras shutdown. Por indicación del usuario STORAGE=sqlite|memory sustituye la decisión inicial de almacenamiento único: SQLite por defecto, memoria local volátil; .env.example y make serve cargan las claves nuevas sin leer BB_TOKEN. Pruebas de reapertura, rollback del callback/SQL/reset, alias, concurrencia, SIGKILL + recuperación de saldos/deltas/anulaciones/IDs y reset + SIGTERM + nuevo proceso. go vet ./..., go test ./..., go test -race ./... y 55/55 secuencias diferenciales v1 en verde, pendientes intactos; prueba Python de captura en verde. Primer commit del adaptador verificado aisladamente antes de registrarlo. Luna revisó código y documentación sin regresiones observadas; límite de carga completa del historial documentado en docs/storage-b5.md. Sin llamadas al original ni cambios en experimentos.jsonl; v2 sigue en A6/B7. Rama disponible para revisión adversaria y correcciones; fast-forward a master requiere autorización posterior del usuario.

- [codex] 2026-10-10 17:02: revisión adversaria de B5 aplicada en feat/b5-sqlite: decisión vigente del storage corregida en este tablero; MEM-07 delimita overflow de saldos y declara contadores sin comprobación; STORAGE añadido al diseño/diagrama, SVG y PNG regenerados e inspeccionados. config.Storage y constantes compartidas, closableStore y versión única del esquema (acc467b, 750a7cc). Regresión de AC/OP-9999 → AC/OP-10000 guardados y releídos de SQLite (c6200d9). Se mantiene el default defensivo de app.New porque acepta Config sin Load; las tres lecturas SQL siguen explícitas y no se reescriben commits anteriores. go vet ./..., go test -count=1 ./... y go test -race -count=1 ./... en verde (sin caché), incluidas las 55 secuencias diferenciales. Sin solicitudes al original ni cambios en .env/experimentos.jsonl; rama sin mezclar, pendiente de autorización para fast-forward.

- [codex] 2026-10-10 17:06: usuario autoriza traer master, mezclar y borrar B5. feat/b5-sqlite rebasada sobre 8ae53fc (A6 integrada); único conflicto en PROGRESS resuelto conservando los registros completos de A6 y B5. go vet ./... y go test -count=1 ./... en verde tras rebase. Integración fast-forward a master hasta 189a6d8, sin commit de merge. Worktree y rama eliminados; temporales ignorados conservados en tmp/b5-local-after-merge, fuera de Git. Referencias de la fila B5 actualizadas a los commits rebasados. Sin llamadas al original ni cambios en experimentos.jsonl/.env; B7 sigue pendiente.
- [claude] 2026-10-10 17:20: A7 reclamado en feat/a7-final-replay (worktree ../10102026-a7); usuario aprueba techo de 1.000 requests, ejecución inmediata: replay sin caché de toda la evidencia v2 de A6 (replay 2020–2744 y sondas 2745–2861, 842 requests) más sondas nuevas de CAM-V2-3 (orden de E510, fallos que cuentan, `intentos` tras rebloqueo) con su repetición.
- [claude] 2026-10-10 17:40: A7 completado en feat/a7-final-replay, sobre `v2` (17:20:27–17:24:59): IDs 2979–3970, 992/1.000. Replay sin caché de toda la evidencia v2 de A6 (65 secuencias, 3129–3970 = A6 2020–2861 + 1109): 842/842 iguales en bytes, 0 deltas, sin cuarto cambio (CAM-05). Sondas de CAM-V2-3 (2979–3053, repetidas 3054–3128, 75/75 iguales): E303/E304/E401 son neutros para la racha y se evalúan antes que E510 (orden v2 E303 → E304 → E401 → E510 → E506 → E507); CONSULTA, ALTA y DEPOSITO ajeno no rompen la racha; DEPOSITO fallido no libera; `intentos` vuelve a 1 al rebloquear. Spec ERR-510, ERR-ORD, CAM-V2-1…3 y CAM-05; informe docs/research/replay-a7.md; debrief. Suite v2 con `a7-v2r-sonda-*` y pending-v2 regenerado (solo altas). Auditoría Haiku previa PASS; la posterior falló por créditos (402) y se hizo con script propio: PASS. Rama sin mezclar.
- [claude] 2026-10-10 17:45: usuario autoriza mezcla; feat/a7-final-replay integrada en master con git merge --ff-only hasta 8999bbc, sin commit de merge. go test ./... y pruebas del explorador en verde. Worktree (ignorados: copia de .env, .explore/pending.jsonl vacío, lock y __pycache__) y rama eliminados. Sin llamadas al original.

- [codex] 2026-10-10 17:10: B7 reclamado con autorización del usuario en feat/b7-v2 (worktree tmp/worktrees/b7). Plan aprobado: v2 predeterminada, CAM-V2-1…3, persistencia/migración de los contadores de bloqueo y regresiones v1/v2; sin solicitudes al original. Supuestos aprobados: E303→E304→E401→E510→E506→E507; solo E506/E507 cuentan y otros errores no reinician; depósito exitoso reinicia ambos contadores y un nuevo bloqueo empieza en intentos=1; saldo negativo subunidad como -0.XX. Codex conserva decisiones/implementación; Luna audita evidencia y cambios en lectura. Línea base go test -count=1 ./... en verde.

- [codex] 2026-10-10 17:17: B7 completado en feat/b7-v2 (worktree tmp/worktrees/b7), sin mezclar. CAM-V2-1…3 activos con v2 predeterminada y v1 explícita; versión desconocida rechazada antes de abrir el Store. SQLite migra B5 al esquema 2 en una transacción y conserva entidades/IDs; racha e intentos bloqueados persisten incluso cuando la respuesta es E506/E507/E510. Regresiones sobre memoria/SQLite, extremos int64 sin floats, precedencia aprobada, desbloqueo/rebloqueo, 30 intentos concurrentes, rollback, SIGKILL con racha parcial, v2→v1→v2 y reset durable. go vet ./..., go test -count=1 ./..., go test -race -count=1 ./... y diferenciales explícitos v1 (55/55 secuencias, 694 requests) / v2 (65/65, 842 requests) en verde, ambos sin pendientes; prueba Python de captura en verde. Luna auditó evidencia y el patch completo desde f378e83 en lectura, sin hallazgos; ejecución de pruebas a cargo del padre. Supuestos documentados en CAM-V2-SUP y docs/behavior-b7.md; no elevan confianza por pruebas locales. Sin llamadas al original ni cambios en experimentos.jsonl, corpus o .env. Lista para revisión adversaria manual; correcciones sobre la misma rama. Fast-forward, eliminación de rama y worktree requieren autorización posterior del usuario; B6/A7 y conformidad pública quedan fuera de B7.

- [codex] 2026-10-10 17:30: revisión adversaria de B7 resuelta en la misma feat/b7-v2, sin mezclar. Acatados Standards 1/2/4/5: reglas seleccionadas una vez, umbrales con nombre/citas, transiciones de contadores en state.Account y migrateSchema2. Acatados los tres P2 de Spec: diferencial sin variable ejecuta v1 y v2 (guards de regeneración con versión explícita/corrida completa probados en subprocesos), ERR-ORD actualizado sin elevar supuestos y retorno v2→v1→v2 separado como decisión de diseño MEM-08. Rechazados para este arreglo Standards 3 (migrar catálogo/tipo ampliaría APIs; validaciones independientes intencionales) y 6 (helpers con usos distintos, expectativas de bytes independientes); motivos en docs/behavior-b7.md#resolución-de-la-revisión-adversaria. go vet ./..., pruebas completas sin caché y race en verde; default diferencial confirma v1 55/55 y v2 65/65 sin pendientes, filtros explícitos también verdes. Luna revisó el patch de correcciones en lectura, sin hallazgos; pruebas ejecutadas por el padre. Evidencia/corpus/listas de pendientes intactos y cero solicitudes al original. Master y worktree conservados; integración y limpieza siguen esperando autorización del usuario.
