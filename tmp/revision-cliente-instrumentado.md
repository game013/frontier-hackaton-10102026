# Revisión del cliente instrumentado

Revisé `ccc6f8c...c6b351c`, que contiene exactamente los commits `5ec6e18`, `40a9552` y `c6b351c`. **La base está bien planteada; encontré cuatro problemas funcionales que conviene corregir antes de usarla para producir evidencia.** Las 10 pruebas existentes pasan.

## Standards

**Qué se hizo bien**

- Commits convencionales y separados por propósito: coordinación, cliente y registro de progreso.
- Escritura del log e IDs protegidos mediante `flock`; actualización de conclusiones con archivo temporal.
- Autenticación registrada mediante etiquetas, sin copiar el header con el token.
- Pruebas contra un servidor falso, sin consumir solicitudes al original.

**Hallazgos**

1. **[P1] El limitador no coordina el token compartido.** En [bb.py:212](../tools/explorer/bb.py), cada instancia mantiene su propio reloj; cada ejecución de la CLI empieza de nuevo. Además, la comprobación del presupuesto ocurre fuera del bloqueo. Dos clientes pueden superar conjuntamente el ritmo permitido o consumir simultáneamente el último cupo. `AGENTS.md` exige «10 req/s y 8.000 por día por token». Hace falta coordinar persistentemente el horario y la reserva de presupuesto.

2. **[P1] Un request enviado puede quedar sin registro.** En [bb.py:238](../tools/explorer/bb.py), el log se escribe después de recibir la respuesta completa. Un timeout o desconexión puede dejar una operación procesada por el original sin evidencia ni consumo contabilizado. Contradice «Cada request al original queda registrado […] con su hipótesis». Conviene registrar el intento y completar después la respuesta o marcar el resultado incierto.

**Heurística:** posible *Duplicated Code*: la representación del paso se construye en tres lugares —líneas 174, 297 y 312—. Centralizarla facilitaría mantener consistente la caché; es una recomendación de diseño.

## Spec

**Qué se hizo bien**

- Incluye los campos del contrato, hipótesis y reset.
- Separa respuestas de infraestructura, las cuenta en el presupuesto y reintenta con backoff.
- Conserva JSON y texto, distingue versiones mediante `epoch` y permite confirmar solicitudes.
- Reconstruye correctamente el prefijo cacheado dentro de una misma instancia de `Sequence`.
- Mantiene el alcance del cliente de exploración; el reemplazo pendiente no es un defecto de estos commits.

**Hallazgos**

1. **[P1] La CLI pierde los pasos cacheados entre ejecuciones.** [bb.py:165](../tools/explorer/bb.py) reconstruye únicamente entradas del log; los aciertos de caché permanecen en memoria. Reproduje: `reset b` → `ALTA` cacheado → nueva ejecución con `CONSULTA`. Solo se envía `CONSULTA`, sin ejecutar `ALTA`. Incumple la estrategia §6.2, «prefijo de secuencia desde reset», y puede producir evidencia con un estado distinto del esperado. Hay que persistir y restaurar los pasos pendientes.

2. **[P2] La caché ignora `Content-Type`.** [bb.py:173](../tools/explorer/bb.py) omite ese campo de la clave. Reproduje que cambiar `application/json` por `text/plain` devuelve caché sin enviar la sonda. La estrategia §4 pide explorar «Content-Type distinto». Debe incluirse el valor efectivo en la clave y el prefijo.

Validé las reproducciones con transporte falso; no llamé al original ni modifiqué código. Falta `docs/agents/issue-tracker.md`; la skill indica ejecutar `/setup-matt-pocock-skills`. Para esta revisión utilicé el contrato y la estrategia locales.

**Standards: 2 infracciones y 1 heurística; mayor riesgo: límites compartidos. Spec: 2 hallazgos; mayor riesgo: pérdida del prefijo en la CLI.**

## Decisiones de atención

1. **[Standards P1: límite compartido] Relevante — acatado.** La cuota y el turno se reservan bajo
   bloqueo en estado persistente por etiqueta de token/día; así las instancias de la CLI comparten
   tanto el presupuesto como el espaciado de 8 req/s.
2. **[Standards P1: intento sin registro] Relevante — acatado.** Se crea la entrada del intento
   antes de abrir la conexión y, si falla el transporte, queda marcada sin respuesta en vez de
   desaparecer.
3. **[Standards, heurística: pasos duplicados] Relevante — acatado.** Se centralizó la construcción
   de la clave de paso para que log, caché, prefijos pendientes y reanudación usen la misma forma.
4. **[Spec P1: prefijo cacheado entre ejecuciones] Relevante — acatado.** Los aciertos de caché
   pendientes se persisten por secuencia y `resume` los carga y los reenvía antes del primer miss.
5. **[Spec P2: `Content-Type` fuera de la caché] Relevante — acatado.** La clave usa el
   `Content-Type` efectivo, incluida la variante implícita `application/json`; una sonda con otro
   tipo no reutiliza una respuesta previa.

## Registro de atención - 10 de octubre de 2026

La revisión inicial describe el rango `ccc6f8c...c6b351c`. Las decisiones anteriores ya se implementaron en `ecac9e7`; este registro distingue esa corrección previa de la validación y los ajustes de esta sesión.

| Prioridad | Hallazgo | Atención y verificación | Estado |
| --- | --- | --- | --- |
| P1 | Cuota compartida | Reserva persistente bajo bloqueo; prueba con dos clientes y último cupo. | Corregido previamente y validado |
| P1 | Request sin registro | Intento escrito antes del envío; prueba de fallo de transporte. Ahora se rechaza también reanudar un intento pendiente de resultado incierto. | Validado y reforzado |
| P1 | Prefijo cacheado perdido | Prueba entre instancias. Se corrigió además la reanudación de una secuencia totalmente cacheada: persiste el reset, recupera el prefijo completo y evita reutilizar su nombre. | Validado y reforzado |
| P2 | Content-Type fuera de clave | Prueba que cambia JSON por text/plain y exige envío real. | Corregido previamente y validado |
| Diseño | Construcción duplicada del paso | Clave centralizada en step_key y _step_key. | Corregido previamente |
| P1 adicional | Infraestructura visible como evidencia | Clasificación y actualización en una sola escritura bajo bloqueo; nunca se publica status/response de rate-limit en el log de evidencia. | Corregido en esta sesión |

Validación: **16 pruebas pasan**, contra servidor falso local; `git diff --check` sin errores. No se enviaron solicitudes al original.

Límite de esta validación: la coordinación exige compartir la misma ruta de log y directorio `.explore`; las pruebas no certifican carga multiproceso, separación entre tokens ni recuperación frente a interrupción en cada punto de escritura. La reproducción del corpus a las 15:30 y el registro de cambios del servicio siguen pendientes de su horario y no fueron parte de esta sesión.

Entrega: PDF actualizado en `output/pdf/revision-cliente-instrumentado.pdf`.

## Continuación: diseño y arquitectura

Los hallazgos funcionales de esta revisión ya están atendidos. La siguiente tanda se registra por ID en [hallazgos del diseño](hallazgos-diseno.md), sección 7. Se corrigieron decisiones de arquitectura y entrega, se separó la especificación con IDs reales y se añadió exportación PNG; implementación Go y evidencia posterior al cambio siguen pendientes.
