# Caja negra · lenguaje de evidencia

Vocabulario para distinguir las observaciones del servicio de su revalidación.

## Lenguaje

**Línea base histórica**:
Conjunto de respuestas observadas en una versión, con el orden y el estado inicial necesarios para reproducirlas. Conservarla no demuestra que siga vigente.

**Replay completo**:
Repetición de todas las secuencias seleccionadas desde sus resets, sin reutilizar respuestas de caché. Un replay interrumpido no confirma la línea base.

**Delta de comportamiento**:
Diferencia de status o cuerpo según el contrato del evaluador entre una observación histórica y su repetición. Una diferencia de orden de claves JSON por sí sola no es un delta de comportamiento.

**Versión 1 / versión 2 (v1, v2)**:
Comportamiento del original antes y después del incidente FR-0153, abierto a las 15:30. v2 es el objetivo de conformidad; v1 solo es la línea base contra la que se miden los deltas.

**Delta del incidente**:
Uno de los 3 comportamientos que, según FR-0153, cambiaron de v1 a v2. Solo cuenta si un replay completo lo reproduce en v2 con evidencia v1 comparable. El rate-limit de infraestructura, la caché y el estado sin reset no cuentan como deltas.

**Evidencia de bytes**:
Cuerpo original capturado sin decodificación intermedia. Una respuesta histórica legible sin esa captura no demuestra sus bytes originales.
