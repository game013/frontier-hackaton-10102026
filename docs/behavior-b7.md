# B7 · comportamiento v2 y regresiones

El reemplazo implementa CAM-V2-1…3 del [informe A6](research/deltas-a6.md).
`BEHAVIOR_VERSION` se resuelve una sola vez al arrancar: `v2` por defecto, `v1`
explícita para el contrato histórico; cualquier otro valor impide arrancar antes
de abrir el almacenamiento. El motor recibe la versión explícita y no consulta
el entorno, el reloj ni el original. NOTAS/HALT siguen disponibles en ambas versiones.
`rulesFor` elige el conjunto de políticas una vez en `engine.New`; v2 sobrescribe
el formato, límite y transiciones de bloqueo de v1. Las mutaciones de contadores
se realizan mediante métodos de `state.Account`, no asignaciones desde el motor.

## Reglas implementadas

| Regla | v1 | v2 |
| --- | --- | --- |
| CONSULTA, `saldo` | Entero interno | String del entero/100, exactamente dos decimales |
| E506 en TRANSFER | Monto > 100000 | Monto > 50000 |
| Bloqueo como origen | No se evalúa ni se actualiza | Tres E506/E507 consecutivos; siguientes TRANSFER dan 423 E510 |

Los saldos se formatean sin floats, incluido `MinInt64`, sin cambiar montos ni
unidades internas. El tercer fallo responde E506/E507; no responde E510 hasta el
siguiente intento. E510 contiene `intentos`, desde 1 y creciente. Un TRANSFER
exitoso reinicia la racha del origen; un DEPOSITO exitoso reinicia la racha y los
intentos bloqueados de su cuenta. CONSULTA, ANULA y un TRANSFER entrante no los
reinician. El bloqueo no impide recibir ni consultar.

Los errores E506/E507/E510 no consumen OP ni mueven saldos, pero en v2 sí
modifican contadores. El Store confirma esas mutaciones antes de publicar la
respuesta. Un error interno revierte también los contadores. Reset elimina
cuentas, operaciones, bloqueo y contadores en la misma transacción.

## Supuestos aprobados por el operador

Estas fronteras no se midieron en el original. Las pruebas locales verifican la
implementación elegida; no elevan su confianza a confirmado:

- Orden de negocio en v2: E303 → E304 → E401 → E510 → E506 → E507.
  A6 sí midió que E510 gana sobre E506; no midió las demás combinaciones.
- Solo E506/E507 incrementan la racha. Otros errores de negocio o protocolo no
  incrementan ni reinician la racha y no consumen intentos bloqueados.
- Se comprueba racha ≥ 3. Un depósito exitoso pone ambos contadores en cero;
  tras otro bloqueo, `intentos` vuelve a empezar en 1.
- Saldos negativos entre −99 y −1 se muestran como `"-0.XX"`.
- v1 no aplica bloqueo. Que este sea un delta histórico sigue siendo inferido,
  pendiente de confirmar con conformidad externa (CAM-V2-3).

## Persistencia y rollback de comportamiento

SQLite migra el esquema B5 (versión 1) a versión 2 añadiendo a `accounts`
`transfer_failures` y `blocked_attempts`, enteros con cero predeterminado. ALTER,
`user_version` y validación final están en la misma transacción. No se borran
cuentas, saldos, deltas, anulaciones ni próximos IDs. Una base nueva usa también
el esquema 2. Esquemas desconocidos o incompletos impiden arrancar.

**Decisión de diseño del reemplazo (MEM-08), no parte de la lista de supuestos
aprobados a las 17:10 ni una observación del original:** el rollback admitido es
**configurar v1 en este mismo binario** y reiniciarlo sobre la misma base. v1 ignora y conserva los contadores de bloqueo: volver a v2
retoma esos valores, sin reset implícito. Los saldos, IDs y operaciones siguen
siendo compartidos entre versiones. Usar `/__reset` si se desea comenzar otra
secuencia, no como requisito de migración. **El binario B5 anterior no admite el
esquema 2**; no hay downgrade de esquema ni promesa de rollback a ese artefacto.

Los contadores usan int64, como AC/OP; su overflow queda fuera del alcance
práctico y no se comprueba (MEM-07). Se conserva el límite B5 de cargar/copiar el
historial completo por request con estado, sin nuevas promesas de rendimiento.

## Validación local

- Diferencial v1: **55 secuencias / 694 requests**, incluidos resets.
- Diferencial v2: **65 secuencias / 842 requests**, incluidos resets: replay A6
  de 58 secuencias/725 requests y 7 sondas repetidas/117 requests. El canario
  independiente no se duplica en esta suite.
- Sin `BEHAVIOR_VERSION`, el arnés ejecuta ambas versiones; una variable explícita
  filtra una sola. `-update-pending` exige versión explícita y corrida completa.
  Sus guards se prueban en un subproceso sin permitir cambios en las listas.
- Ambas listas `pending-v1.txt` y `pending-v2.txt` sin pasos pendientes. No se
  modifican corpus, evidencia, status esperados ni comparación de bytes.
- `internal/engine/v2_test.go`: formato y extremos int64, fronteras de límite,
  ciclo de bloqueo/rebloqueo/reset, precedencia supuesta, cuentas independientes,
  rollback ante overflow y 30 intentos bloqueados concurrentes; memoria y SQLite.
- `internal/storage/sqlite/migration_test.go`: migración B5, conservación de
  entidades/IDs, reapertura idempotente, fallo con rollback del esquema,
  persistencia/rollback de contadores y reset durable.
- `internal/app`: composición explícita/default y rechazo de versión inválida
  sin crear el archivo de estado.
- `cmd/replacement/v2_test.go`: procesos reales, SIGKILL con racha parcial,
  bloqueo e intentos persistidos, v2→v1→v2, desbloqueo durable y reset tras reinicio.

Comandos offline:

```sh
go vet ./...
go test -count=1 ./...
go test -race -count=1 ./...
BEHAVIOR_VERSION=v1 go test -count=1 ./tests/differential
BEHAVIOR_VERSION=v2 go test -count=1 ./tests/differential
```

B7 no llama al original ni modifica `experimentos.jsonl`. El despliegue B6,
el replay final A7 y la conformidad pública siguen siendo pasos separados.

## Resolución de la revisión adversaria

Correcciones sobre `feat/b7-v2`, sin cambiar respuestas ni evidencia:

| Hallazgo | Decisión | Motivo / ajuste |
| --- | --- | --- |
| Standards 1: `if e.v2` repetidos | Acatado | `rulesFor` selecciona una vez las políticas; `apply` ejecuta reglas sin nombres de versión. |
| Standards 2: umbrales sin nombre | Acatado | Constantes `transferLimitV1`, `transferLimitV2` y `blockingFailures`, con citas ERR-506/CAM-V2-2/CAM-V2-3. |
| Standards 3: tipo/catálogo único de versiones | Rechazado para B7 | `Load`, `app.New` y `engine.New` admiten entradas independientes: validar sus fronteras es intencional. No hay fallo demostrado. Migrar el tipo y catálogo de configuración, motor y arnés ampliaría las APIs y dependencias del arreglo; se difiere hasta necesitar otra versión. |
| Standards 4: motor modifica campos de contadores | Acatado | Transiciones en `state.Account` para registrar fallos/intentos, reiniciar racha y liberar bloqueo; el motor conserva las decisiones y el orden. |
| Standards 5: nombre `migrateV2` | Acatado | Renombrado a `migrateSchema2`, independiente de la versión de comportamiento. |
| Standards 6: helpers de pruebas repetidos | Rechazado | `run` reproduce secuencias estáticas; el harness v2 inspecciona estado y compone pruebas de concurrencia. Compartir unas pocas líneas de aserción no simplifica esos usos. El cuerpo E510 esperado se mantiene independiente del serializador de producción para detectar regresiones de bytes. |
| Spec a: v1 no corre por defecto | Acatado | Sin variable se recorren todas las versiones; con variable se filtra una. Regenerar pendientes exige versión explícita y corrida completa, con regresiones de los guards. |
| Spec a: ERR-ORD desactualizado | Acatado | La propia fila separa orden v1 y v2, evidencia de E510 ante E506 y las demás precedencias supuestas. |
| Spec b: retorno v2→v1→v2 no aprobado como supuesto | Acatado | Se retira de CAM-V2-SUP y se registra como decisión de diseño del reemplazo en MEM-08 y la sección de rollback; no se atribuye al operador ni al original. |

Se conservan todos los commits anteriores y las pruebas de conformidad locales;
estas correcciones no autorizan integración ni limpieza de rama/worktree.
