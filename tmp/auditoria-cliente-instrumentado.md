# Auditoría acotada del cliente instrumentado

Fecha: 2026-10-10. Estado examinado: `ffd2c86`.

Las correcciones son pertinentes, pero no se valida el cierre global del informe
`revision-cliente-instrumentado.md`: persisten tres casos reproducibles en los cambios.
El arreglo de ritmo sí supera la reproducción del bloqueo previo al envío.

## Alcance y validación

Se revisó `git diff ecac9e7^...ffd2c86 -- tools/explorer`, centrado en las correcciones
`ecac9e7`, `64da75a` y `ffd2c86` que enumera el informe, y su documentación. La implementación
inicial se leyó como contexto, sin convertir esta revisión en una auditoría desde cero.
Fuentes: `AGENTS.md`, contrato del reto, README del explorador e informe de seguimiento.

`python3 -m unittest tools/explorer/test_bb.py`: **17 pruebas pasan** en una corrida de
revalidación. Además se ejecutaron tres reproducciones independientes con transporte ficticio,
token ficticio y archivos temporales. No se llamó al original ni se modificó el cliente.

## Standards

### P2 — La cuota compartida usa bloqueos diferentes según el nombre del log

Ubicación: `tools/explorer/bb.py:180–186` y `196–204`; `_locked()` deriva el bloqueo del log.

El README promete coordinación entre procesos por token. Dos clientes con `a.jsonl` y
`b.jsonl` en el mismo directorio comparten `.explore/quota.json` y `quota.tmp`, pero adquieren
`a.lock` y `b.lock`. Las lecturas y escrituras de cuota y turno no quedan mutuamente excluidas.

Reproducción: dos clientes con el mismo token ficticio, logs diferentes y `daily_cap=1`;
una barrera después de `_read_quota()` sincroniza ambas reservas. Resultado: una reserva
termina y la otra lanza `FileNotFoundError` al reemplazar `quota.tmp`; `used` queda en 1.
Según la intercalación también pueden perderse actualizaciones. No es un fallo de la prueba
con el mismo log: es una configuración que la API admite y que esa prueba no cubre.

Pendiente: usar un bloqueo propio del recurso de cuota, con un orden consistente si se
combina con el del log, o rechazar explícitamente logs distintos que compartan ese recurso.
Añadir una prueba concurrente con dos rutas de log.

No se encontraron otros incumplimientos relevantes de estándares ni olores de diseño que
justifiquen ampliar el alcance. `step_key` elimina la duplicación y la persistencia de
pendientes responde a una necesidad real de la CLI.

## Spec

### P1 — Un corte al consumir un pendiente duplica una operación completada

Ubicación: `tools/explorer/bb.py:413–415`, combinado con `resume()` en `261–264`.

El README promete restaurar el prefijo y reenviarlo para que el estado corresponda a la
secuencia lógica. `execute()` persiste la respuesta como `completed`; después `flush()`
elimina el pendiente en otra transacción. Un corte entre esos pasos deja dos representaciones
del mismo paso. `resume()` concatena ambas y vuelve a enviar la operación.

Reproducción: crear la evidencia de `ALTA` en `a`; cachearla en `b`; ejecutar el prefijo de
`b` y simular una interrupción justo antes de eliminar el pendiente de `ALTA`. Un cliente
nuevo reanuda `b` y envía una consulta. Resultado: **dos envíos de ALTA en b**, aunque el
primer ALTA ya figura como `completed`. Puede duplicar cuentas u operaciones y contaminar
el prefijo de caché. No se trata de una respuesta de transporte incierta.

Pendiente: asociar el pendiente con el intento completado mediante una identidad persistente
y reconciliarlo al reanudar, o implementar una confirmación recuperable que consuma el
pendiente y registre la respuesta como una sola operación lógica. Añadir prueba de corte
después de registrar la respuesta y antes de retirar el pendiente.

### P2 — El reset descartado por infraestructura bloquea su propia reanudación

Ubicación: `tools/explorer/bb.py:407–408`.

El contrato descarta respuestas con `X-Frontier-Infra: rate-limit`; el README ofrece
recuperación de pendientes. Tras agotar los reintentos del reset, queda el reset pendiente y
solo hay registros de infraestructura. `resume()` lo admite, pero `flush()` rechaza cualquier
registro previo de la secuencia, incluso esos intentos descartados.

Reproducción: opener ficticio que devuelve cuatro rate limits de infraestructura; capturar
`RateLimited` y ejecutar `resume('s').flush()`. Resultado: `ValueError: la secuencia 's' ya
existe en el log`, sin reintentar el reset. Abrir otra secuencia evita el bloqueo, pero no
cumple la recuperación prevista.

Pendiente: distinguir reset completado, intento incierto e infraestructura descartada en la
comprobación de `flush()`. Añadir prueba de agotamiento de infraestructura y recuperación.

## Cierre del arreglo de ritmo

`ffd2c86` separa cuota y turno y revalida después del bloqueo del log. La nueva prueba
verifica tiempos efectivos en el opener, no solo reservas, y pasa junto con las otras 16.
Se valida el cierre del caso concreto descrito en el informe, bajo su alcance de misma ruta
de log y su límite residual aceptado entre reclamar turno y conectar.

Conviene precisar el texto: `next_at` se calcula al reclamar el turno, antes de persistir
la cuota y abrir la conexión; no se mide el último envío real al socket. La prueba no da
una garantía absoluta ante toda pausa del proceso. Esto no se cuenta como un hallazgo
adicional porque el informe ya acepta esa limitación.

Resultado por eje: Standards, **1 hallazgo P2**; Spec, **2 hallazgos, el mayor P1**.
La afirmación «todos los hallazgos cerrados» debe quedar pendiente hasta resolver estos casos.
