# Progreso · exploración e implementación

Tablero vivo. Lo cerrado sale del tablero y pasa a la [especificación](docs/specification.md)
o al [diseño](docs/system-design.md). Historia de la etapa de diseño (entrevista Q1–Q11,
hosting, coordinación pi/Codex): [docs/archive/progress-diseno.md](docs/archive/progress-diseno.md).

## Estado ahora

- **Fase:** A0, A1 y B1 completados; fórmula del control confirmada. A1 está en rama separada, pendiente de autorización para fast-forward.
- **Versión observada:** `v1`. Último ID del log en la rama A1: 225 (174 respuestas nuevas; intento 51 sin respuesta).
- **Próximo paso:** A2 (línea base completa) y B3 (integridad con fórmula A1); B2 también está desbloqueado por B1.
- **Bloqueos:** ninguno.

## Hitos de hoy (Bogotá, UTC−5)

- [x] 13:15 · A0 listo (completado a las 13:59): cliente con base64, `--no-cache`, runner de secuencias con lock.
- [x] 15:00 · Fórmula del control con candidato validado (A1 completado a las 14:42; objetivo, no corte).
- [ ] 15:20 · **Línea base `v1` completa** en `tests/corpus/` (A2).
- [ ] 15:35 · Primer replay tras el cambio anunciado (A6).
- [ ] 16:35 · Segundo replay (por si la hora del cambio es de CDMX).
- [ ] 18:00 · Corte de la fórmula: si no está confirmada, activar plan B (INT-04).
- [ ] 18:30 · Replay final sin caché sobre la versión vigente (A7).
- [ ] 19:15 · Último despliegue.
- [ ] 19:30 · Congelar código y configuración; smoke test público.
- [ ] 20:00 · Entrega.

## Tablero A · Exploración (Python, `tools/explorer`)

| Paso | Qué | Presupuesto | Depende de | Responsable | Estado | IDs del log |
| --- | --- | --- | --- | --- | --- | --- |
| A0 | Completar `bb.py`: request/response en base64, `--no-cache`, runner de secuencias (reset + lock por token mientras dura la secuencia, entre procesos de esta máquina). | 0 | — | Codex (orquestación), Luna (revisión/pruebas) | Completado | — (0 requests) |
| A1 | **Fórmula del control:** pares mínimos sobre ALTA/CONSULTA que cambien una sola propiedad (longitud, caja, acento, separador, ceros) y búsqueda de candidatos 0–99 con parada al primer control compatible; validar candidatos con mensajes reservados. | ≤100 por tanda | A0 | Codex (orquestación), Luna (análisis/revisión) | Completado | 52–225 (51: fallo DNS sin evidencia) |
| A2 | **Línea base `v1`:** corpus de ejemplos, secuencias 1–50 y lo de A1 en `tests/corpus/`; repetir sin caché. | ~150 | A0 | — | Pendiente | — |
| A3 | **Estado:** consumo de IDs ante errores, anulación de transferencias, ANULA sobre operación inexistente, alcance del reset, naturaleza del límite E506. | ~500 | A0 (mejor con A1) | — | Pendiente | — |
| A4 | **Sobre HTTP y números:** matriz de cierre del diseño (precedencia auth/ruta/JSON, cuerpos, HEAD/OPTIONS, escapes) y bordes (`0`, `-1`, `+1`, `01`, `1.0`, int64). | ~300 | A0 | — | Pendiente | — |
| A5 | **Descubrir comandos** por diccionario (RETIRO, MOVIMIENTOS, CIERRE…). | ~500 | A1 | — | Pendiente | — |
| A6 | **Detección del cambio:** replay contra la base a las 15:35 y 16:35, sondas mínimas por delta, sección 6 de la spec con IDs nuevos. | ~300 | A2 | — | Pendiente | — |
| A7 | Replay final sin caché de la versión vigente. | ~300 | A6 | — | Pendiente | — |

Al cerrar cada tanda: `conclude` en el log, actualizar la fila de la spec con sus IDs y
commit aparte de `experimentos.jsonl` (`git add experimentos.jsonl` explícito, sin `bb.py` corriendo).

## Tablero B · Implementación (Go)

| Paso | Qué | Depende de | Responsable | Estado | Commit |
| --- | --- | --- | --- | --- | --- |
| B1 | `go.mod`, `cmd/replacement`, handler propio: auth, `/health`, `/__reset`, 404 E404, E100/E102 (casos del log 34–50). Captura íntegra de toda request recibida (seed para replay local). | — | claude | Completado | 4a2d32d…fc09d12 |
| B2 | **Arnés diferencial:** test Go que lee secuencias de `tests/corpus/` y compara status y bytes. | B1 | — | Pendiente | — |
| B3 | `internal/protocol`: parser de `m`, E201 y control tras una sola función (primero plan B; luego la fórmula de A1). | B1; A1 | — | Pendiente | — |
| B4 | `internal/engine` + `state`: seis comandos, orden E201→E202→E301/E302/E401, E506/E507, sin corregir `recieved` ni espacios. | B3; A3 | — | Pendiente | — |
| B5 | `internal/storage/sqlite` (`modernc.org/sqlite`): contrato Store, reset atómico, prueba de reinicio. | B4 | — | Pendiente | — |
| B6 | **Exposición:** primero local + ngrok con smoke test público; luego desplegar en Railway (volumen, una réplica, Serverless apagado) y mantenerlo si funciona. | B1 (temprano), B5 (final) | — | Pendiente | — |
| B7 | `BEHAVIOR_VERSION=v2` con el delta de A6 y sus regresiones. | A6 | — | Pendiente | — |
| B8 | Congelar: replay local del corpus vigente, smoke test público, entrega. | todo | — | Pendiente | — |

Cada paso termina con `go test ./...` en verde y commit atómico convencional.

### Diferido (P2, confirmado por el usuario)

Diseñado en `docs/system-design.md`, sin impacto directo en el puntaje; solo si sobra tiempo:
métricas p95 y alertas, rotación del log de captura del evaluador, exportador de
`evidencia.jsonl` con manifiesto y hashes, coordinación del lock entre varias máquinas.
La captura de requests del evaluador sí se hace, en versión simple (JSONL a stdout).

## Hipótesis activas

Se borran cuando pasan a la spec con IDs.

- PING: excepción de integridad pendiente de ampliar en A4 (log 2, 33). La fórmula general ya está confirmada en INT-01; no usar PING como oráculo.
- E506: ¿límite por operación o acumulado? Visto con 120000 (log 10).
- IDs: ¿un comando fallido consume `AC-`/`OP-`?
- Reset: ¿alcance por token?, ¿reinicia contadores a 1?
- Sobre (para A4; supuestos ENT-05..07 de B1, fijados en `internal/httpadapter/handler_test.go`): sin auth a `/no-existe`; sin auth con cuerpo `{` a `/msg`; `Bearer token-invalido` con `GET /msg`; `{` a `/no-existe` con auth; `/%6dsg`, `/msg/`, `/msg?x=1`; cuerpos vacío, `[]`, `{"m":null}`, `{"M":"PING;1"}`, `{"m":"PING;1"} x`, `m` duplicada; `Authorization` duplicado o con espacios extra; `PING;` sin control.

## Decisiones vigentes

- Go con `net/http` y handler propio, un proceso, una réplica. ([diseño](docs/system-design.md#arquitectura-y-decisiones))
- Un solo almacenamiento: SQLite (`STATE_PATH`), contrato Store único.
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

- (vacío)

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
