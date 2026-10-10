# Progreso · exploración e implementación

Tablero vivo. Lo cerrado sale del tablero y pasa a la [especificación](docs/specification.md)
o al [diseño](docs/system-design.md). Historia de la etapa de diseño (entrevista Q1–Q11,
hosting, coordinación pi/Codex): [docs/archive/progress-diseno.md](docs/archive/progress-diseno.md).

## Estado ahora

- **Fase:** plan de exploración e implementación acordado; ninguna tarea iniciada.
- **Versión observada:** `v1`. Último ID del log: 50.
- **Próximo paso:** A0 y B1 en paralelo; después A1 (fórmula) y A2 (línea base antes de las 15:20).
- **Bloqueos:** ninguno.

## Hitos de hoy (Bogotá, UTC−5)

- [ ] 13:15 · A0 listo: cliente con base64, `--no-cache`, runner de secuencias con lock.
- [ ] 15:00 · Fórmula del control con candidato validado (objetivo, no corte).
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
| A1 | **Fórmula del control:** pares mínimos sobre ALTA/CONSULTA que cambien una sola propiedad (longitud, caja, acento, separador, ceros) y búsqueda 0–99; validar candidatos con mensajes reservados. | ≤100 por tanda | A0 | — | Pendiente | — |
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
| B1 | `go.mod`, `cmd/replacement`, handler propio: auth, `/health`, `/__reset`, 404 E404, E100/E102 (casos del log 34–50). | — | — | Pendiente | — |
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

- Control: fórmula desconocida. `ALTA;Lucia;82` válido, `83` E202 (log 3–4). PING lo ignora o lo trata aparte (log 2, 33).
- E506: ¿límite por operación o acumulado? Visto con 120000 (log 10).
- IDs: ¿un comando fallido consume `AC-`/`OP-`?
- Reset: ¿alcance por token?, ¿reinicia contadores a 1?

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
