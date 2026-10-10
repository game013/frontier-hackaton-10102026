# B5 · almacenamiento y recuperación

El reemplazo selecciona `STORAGE=sqlite|memory` una sola vez al arrancar. SQLite es
el valor predeterminado y persiste en `STATE_PATH` (`var/state.db` por defecto).
Memoria es una alternativa local volátil solicitada por el usuario; sustituye la
restricción inicial de un único adaptador. No hay reglas de negocio duplicadas.

## Contrato y transacciones

`engine.Store` conserva `Update(func(*state.State) error)` y `Reset() error`.
SQLite usa un mutex, una conexión, transacciones `IMMEDIATE`, WAL,
`synchronous=FULL`, claves foráneas y `busy_timeout=1000ms`. El driver Go puro
`modernc.org/sqlite` está fijado a v1.39.1, compatible con Go 1.24 del proyecto.
Opciones de conexión: [documentación del driver](https://pkg.go.dev/modernc.org/sqlite@v1.39.1#Driver.Open).

El esquema original de B5 (versión 1) contiene `accounts`, `operations`, `operation_deltas` con
posición explícita, y una fila `counters`. Saldos y contadores son enteros exactos
`int64`; no hay restricciones de saldo positivo. Nombres e IDs se conservan sin
normalización. El adaptador guarda la representación de State; no inventa campos
de operación que el motor actual no necesita.

B7 migra transaccionalmente al esquema 2: añade `transfer_failures` y
`blocked_attempts` por cuenta, inicializados en cero. La validación y actualización
de `user_version` participan en la misma transacción; un fallo revierte incluso
los ALTER. Bases nuevas y ambas versiones de comportamiento usan el esquema 2.
El rollback admitido es configurar `v1` en el binario actual, no abrir esta base
con el binario B5 anterior. Detalle: [B7](behavior-b7.md#persistencia-y-rollback-de-comportamiento).

Cada Update carga el estado dentro de la transacción, entrega una copia aislada
al callback, y escribe solo entidades cambiadas y contadores antes de confirmar.
Un error del callback, escritura o commit se devuelve al motor; nunca se reintenta
el callback. Los errores previos al commit descartan los cambios. Si un commit
falla, no se promete exactamente una vez: no se añade deduplicación ni reintentos.
Consultas y reset se serializan con las mutaciones. Reset borra deltas, operaciones,
cuentas y reinicia ambos contadores en una transacción. El adaptador de memoria
clona antes y después del callback para ofrecer rollback y aislamiento de punteros.
El estado del callback no debe escapar de él.

El esquema se inicializa en una transacción y se comprueba al abrir. Una versión
incompatible, tablas ausentes, contadores ausentes o archivo inaccesible impiden
arrancar; nunca se borra una base para recuperarse automáticamente. Solo se escucha
tras abrir almacenamiento y captura. SIGTERM/SIGINT hacen shutdown del servidor
antes de cerrar la base. Un fallo de almacenamiento durante un comando o reset da
500 `{"error":"E500","mensaje":"error interno"}` (supuesto MEM-07).

## Validación local

- `internal/storage/sqlite`: reapertura con nombres Unicode, espacios y NUL,
  valores exactos hasta int64, deltas ordenados, saldos negativos, anulaciones y
  siguientes IDs, incluida la frontera AC/OP-9999 → AC/OP-10000 tras
  reapertura. Rollback tras callback que muta y falla y fallo SQL inyectado;
  reset fallido sin borrado parcial y reset exitoso persistente.
- `internal/engine`: reglas existentes sobre SQLite temporal, incluida concurrencia
  de 50 altas, orden de errores y overflow sin consumir OP ni mover saldo.
- `internal/app`: selección SQLite/memoria, diferencias de persistencia y errores
  de apertura/Store. `internal/httpadapter`: reset fallido devuelve E500.
- `cmd/replacement`: proceso real de la composición, SIGKILL después de respuestas,
  nuevo proceso que conserva saldos/deltas/anulaciones/IDs; reset, SIGTERM y otro
  proceso que observa estado vacío y AC/OP desde 0001.
- `tests/differential`: 55 secuencias v1 existentes sobre SQLite temporal, status
  y bytes exactos, sin agregar pendientes ni modificar evidencia.

Estos tests validan el reemplazo; no son experimentos ni evidencia del ciclo de
vida del original. B7 implementa los deltas medidos por A6 y añade pruebas de
migración, contadores persistentes, bloqueo, desbloqueo, concurrencia y reinicio
real de procesos. Ambas suites diferenciales pasan sin pendientes: v1 con
55 secuencias/694 requests y v2 con 65 secuencias/842 requests. La conformidad
pública y el replay final contra el original siguen siendo pasos separados.

## Límites operativos

Una instancia y un volumen persistente. Todos los auxiliares SQLite quedan junto
al archivo de estado; no copiar una base abierta sin backup SQLite. Un bloqueo
externo que exceda 1 segundo puede dar E500. No se promete coordinación entre
réplicas ni ejecución exactamente una vez frente a una respuesta perdida.

El contrato actual exige cargar/copiar el estado completo en cada comando con
estado: el coste crece con el historial. Las escrituras sí son incrementales.
B5 valida el corpus y las secuencias actuales; no promete latencia constante con
historial ilimitado. Una API de cambios por entidad queda fuera del alcance.

El directorio de estado nuevo se crea con modo 0700 y archivo nuevo 0600, sin
truncar archivos existentes. Los permisos de archivos preexistentes no se cambian.
`var/` y extensiones SQLite convencionales están ignorados; una ruta personalizada
sin esas extensiones debe vivir fuera del checkout o tener su propia exclusión.
Tokens y temporales quedan fuera de Git. B5 no consulta al original.
