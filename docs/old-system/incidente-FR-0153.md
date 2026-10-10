# Incidente FR-0153 · versión 2 del servicio

Transcripción literal del ticket publicado en la plataforma del reto (pestaña «Incidente»). Es
fuente del enunciado, igual que el [README](README.md); no es evidencia de comportamiento.

- **Ticket:** #FR-0153 · prioridad alta
- **Abierto:** 15:30 · Proveedor del servicio caja negra
- **Título:** El proveedor desplegó la versión 2 del servicio sin avisar

| Campo | Texto del ticket |
| --- | --- |
| Qué pasó | La caja negra ahora responde como versión 2. Nadie avisó qué cambió. |
| Qué cambió | 3 comportamientos del servicio cambiaron. El resto se mantiene igual que en la versión 1. |
| Qué esperamos | Que descubran qué cambió y que su reemplazo se comporte como la versión 2. |
| Cómo se evalúa | Cuenta en el criterio «Respuesta al incidente» de Ejecución: que encuentren los 3 cambios, los registren en el log de experimentos y los expliquen en el debrief. Los tests de conformidad corren contra la versión 2. |

## Consecuencias para el proyecto

- El objetivo de conformidad es la **versión 2**. La versión 1 solo sirve como línea base para
  encontrar los deltas.
- Hay que encontrar **exactamente 3 deltas de comportamiento**. Si aparecen más o menos, se revisa
  la evidencia: replay incompleto, caché, rate-limit de infraestructura, estado sin reset o
  diferencias que no cuentan, como el orden de claves JSON.
- Cada delta tiene que quedar en tres sitios: en `experimentos.jsonl`, con `hipotesis` y
  `conclusion`, que cite los IDs `v1` y `v2`; en la [especificación §6](../specification.md#6-cambios-durante-el-día);
  y en el debrief.
- El reemplazo implementa la versión 2 con `BEHAVIOR_VERSION=v2`. Nunca se selecciona por reloj.
