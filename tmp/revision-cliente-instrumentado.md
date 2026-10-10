# Revisión del cliente instrumentado

**Estado: falta cerrar el límite de ritmo; todavía no hay OK global.**

Seguimiento de los hallazgos originales (`ccc6f8c...c6b351c`), sin revisión desde cero.
Correcciones contrastadas: `ecac9e7` y `64da75a`; estado revisado hasta `caadf07`.

## Cerrados y validados

| Tema | Solución comprobada |
| --- | --- |
| Cuota diaria compartida (parte del P1 original) | Reserva persistente y atómica bajo bloqueo; dos clientes comparten el último cupo. El ritmo sigue abierto abajo. |
| Requests sin registro (P1 original) | El intento se escribe antes del envío; un fallo de transporte conserva el registro y queda como `transport_error`. |
| Prefijo cacheado perdido en la CLI (P1 original) | Los pasos pendientes sobreviven entre ejecuciones y se reenvían en orden antes del primer fallo de caché. |
| `Content-Type` fuera de la caché (P2 original) | La clave distingue `text/plain`; `application/json` explícito coincide con el implícito. |
| Construcción duplicada del paso (recomendación original) | Log, caché y prefijo utilizan `step_key` / `_step_key`. |
| Reanudar un intento incierto `pending` (P1 adicional) | `64da75a` hace que `resume()` rechace tanto `pending` como `transport_error`; exige otra secuencia desde reset. |
| Pendientes huérfanos al reutilizar una secuencia (P2 adicional) | `64da75a` persiste también el reset, restaura secuencias totalmente cacheadas y rechaza reutilizar nombres con pendientes. |
| Rate-limit visible temporalmente como evidencia (P1 adicional) | `64da75a` clasifica la respuesta de infraestructura en una sola actualización; no publica su `status` ni `response` en el log principal. |

## Abierto: P1 — el límite de ritmo permite ráfagas

**Es la parte aún incompleta del hallazgo original de límites compartidos.**
La cuota y los turnos se reservan bajo bloqueo, pero el turno no se revalida al enviar:
`_reserve_request()` asigna un horario; después `execute()` espera y obtiene el bloqueo del log.
Si ese bloqueo o una pausa del proceso retrasan el envío, varios turnos vencidos salen juntos.
Referencias: [bb.py](../tools/explorer/bb.py), líneas 177–190 y 318–335.

**Reproducción confirmada:** 11 llamadas concurrentes con el mismo cliente y log, intervalo de
0,125 s. Retener el bloqueo del log durante 1,6 s acumula los turnos; al liberarlo se producen
**11 envíos en aproximadamente 0,002 s**, por encima de los 10 req/s permitidos. La cuota sí
contabiliza correctamente las 11 solicitudes.

**Falta:** coordinar el inicio real de cada envío, revalidando el turno tras cualquier demora;
los turnos vencidos no deben convertirse en una ráfaga. Añadir una prueba concurrente que
retenga el bloqueo y compruebe los tiempos efectivos de envío, no solo las reservas de cuota.

## Validación y alcance

**16 pruebas pasan** contra un servidor falso local. Las reproducciones adicionales usaron
transporte falso; no se llamó al original. Las pruebas actuales no cubren la ráfaga descrita.
La coordinación comprobada utiliza la misma ruta de log y directorio `.explore`.

Este archivo es el seguimiento actualizado. El PDF exportado anteriormente no se actualizó
en esta edición. Conservar el informe hasta validar y cerrar el punto abierto.
