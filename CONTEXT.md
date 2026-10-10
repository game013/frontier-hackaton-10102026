# Caja negra · lenguaje de evidencia

Vocabulario para distinguir las observaciones del servicio de su revalidación.

## Lenguaje

**Línea base histórica**:
Conjunto de respuestas observadas en una versión, con el orden y el estado inicial necesarios para reproducirlas. Conservarla no demuestra que siga vigente.

**Replay completo**:
Repetición de todas las secuencias seleccionadas desde sus resets, sin reutilizar respuestas de caché. Un replay interrumpido no confirma la línea base.

**Delta de comportamiento**:
Diferencia de status o cuerpo según el contrato del evaluador entre una observación histórica y su repetición. Una diferencia de orden de claves JSON por sí sola no es un delta de comportamiento.

**Evidencia de bytes**:
Cuerpo original capturado sin decodificación intermedia. Una respuesta histórica legible sin esa captura no demuestra sus bytes originales.
