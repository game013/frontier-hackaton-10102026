# Progreso · diseño y reemplazo de caja negra

## Objetivo y entregables

- [ ] Acordar el alcance y las decisiones del diseño mediante entrevista.
- [ ] Redactar el documento de diseño de una página en Markdown.
- [ ] Construir el diagrama de arquitectura coherente con el documento.
- [ ] Revisar ambos entregables con el equipo.
- [ ] Convertir el documento aprobado a PDF o publicar una URL, según decisión pendiente.
- [ ] Desglosar la implementación a partir del diseño acordado.

## Estado actual

Fase: análisis inicial. No hay decisiones de arquitectura aprobadas ni implementación iniciada.
Se leyó `AGENTS.md` y `docs/old-system/README.md` antes de modificar archivos.
El inventario inicial contiene instrucciones, enunciado y corpus; no se encontró código ni
cliente instrumentado. La carpeta actual no es un repositorio Git.
No se hicieron solicitudes al servicio original.
La inspección delegada terminó: el corpus muestra PING, ALTA, CONSULTA, DEPOSITO,
TRANSFER y ANULA, identificadores consecutivos y cambios de saldo. Son observaciones
de los ejemplos de la mañana, no reglas confirmadas con experimentos propios.
Hay detalles de compatibilidad como `recieved` (ejemplos 6, 7, 10, 18) y el espacio
final de `comando desconocido ` (ejemplo 12). Fórmula de control, precedencia de errores,
semántica completa de anulación y límites siguen abiertos. Los números del corpus
no sustituyen IDs de evidencia de un futuro `experimentos.jsonl`.

## Hechos y restricciones

- El reemplazo debe ser autónomo y exponerse por internet; no puede consultar al original.
- Debe reproducir rutas, autenticación, respuestas, errores y memoria entre requests.
- `GET /health`, `POST /msg` y `POST /__reset` forman parte del contrato.
- AGENTS.md exige igualdad byte a byte. El evaluador descrito en el README compara JSON
  semánticamente (orden de claves irrelevante), y texto no JSON de forma exacta. Conservar
  ambos criterios explícitos; no relajar el requisito de AGENTS.md.
- El evaluador tiene 100 tests: 40 individuales, 45 secuencias cortas y 15 secuencias largas;
  cada paso dispone de 5 segundos y cada test comienza con reset.
- Cada solicitud al original requiere cliente instrumentado y registro con hipótesis;
  cada secuencia comienza con reset. Límite: 10 req/s y 8.000 por día por token.
- Las respuestas con `X-Frontier-Infra: rate-limit` no son evidencia del servicio.
- AGENTS.md fija un cambio a las 15:30: repetir corpus y documentar diferencias.
- La entrega del reto es a las 20:00 contra la versión vigente. El README no indica la
  zona horaria de esas horas; no asumirla para automatizaciones.
- El reto exige además especificación en siete secciones y `experimentos.jsonl`;
  el documento de una página debe definir su relación con esa especificación.
- Los tokens permanecen fuera de documentos, logs y commits.

## Árbol de decisiones

1. Alcance del diseño: solo reemplazo o también exploración y validación. Pendiente.
   - Desbloquea límites del diagrama y componentes necesarios.
2. Prioridad del resultado y relación entre documento breve y especificación. Pendiente.
   - Desbloquea profundidad, criterios de aceptación y estrategia de cobertura.
3. Restricciones impuestas al stack y despliegue. Pendiente.
   - Desbloquea opciones de runtime, estado y operación.
4. Presupuesto de trabajo antes de implementar. Pendiente.
   - Desbloquea nivel de detalle y alcance del análisis.

Las siguientes rondas cubrirán protocolo y evidencia, modelo de estado, concurrencia/reset,
serialización y errores, validación diferencial, detección de cambios, despliegue y supuestos.
Su orden depende de las respuestas; no constituyen decisiones tomadas.

## Coordinación

| Responsable | Trabajo | Estado | Salida |
| --- | --- | --- | --- |
| Agente principal + usuario | Entrevista y decisiones | En curso | Este registro y diseño acordado |
| Agente `design_facts` | Inspección de corpus y archivos, solo lectura | Completado | Hechos y vacíos incorporados aquí |

Para continuar: leer este archivo y el README; distinguir hechos, recomendaciones y
decisiones aceptadas. Registrar decisiones con su razón y actualizar tareas y bloqueos.
No iniciar implementación hasta confirmar el entendimiento compartido al cerrar la entrevista.

## Registro

- 2026-10-10: iniciada entrevista con skill `grilling`; creada bitácora de coordinación.
  Inspección del corpus delegada. Pendiente primera ronda de decisiones del usuario.

## Frente: exploración del original (pi)

Responsable: agente pi (Claude) con el usuario. Estrategia: `docs/research/estrategia-descubrimiento.md`.

**Protocolo de coordinación entre agentes (pi y Codex) para este archivo:**

- Cada agente edita solo su sección. pi escribe únicamente bajo este encabezado; el resto del
  archivo es de Codex. Para comunicarse, usar la lista «Mensajes» de abajo, marcada con autor.
- Releer el archivo justo antes de cada edición y hacer reemplazos pequeños y exactos; nunca
  reescribir el archivo completo ni reordenar secciones ajenas.
- Registro con prefijo de autor (`[pi]`, `[codex]`) y solo por adición.
- Commits: cada agente incluye solo sus propios cambios del archivo y no commitea texto
  ajeno sin commitear.
- Recurso compartido: hay un solo token y 8.000 req/día. Toda llamada al original pasa por
  `tools/explorer/bb.py`, que lleva el presupuesto en `experimentos.jsonl`. Antes de lanzar
  una tanda, revisar `python3 tools/explorer/bb.py budget`.

**Estado**

- [x] Estrategia de descubrimiento y presupuesto (commits `33f08c1`, `2c9e997`, `ccc6f8c`).
- [ ] Cliente instrumentado en Python (`tools/explorer/`). En curso.
- [ ] Fase 1: replay del corpus (21 req). Fase 2: precedencia E301/E302/E202 (~10 req).

**Decisiones del usuario (exploración):** un token; se registran todos los requests,
incluido `/__reset`; horas en Bogotá (UTC−5); exploración en Python; tope de 100 req por
tanda para el control; precedencia primero; exploración con modelos baratos (Luna, Sonnet).
El cliente es una herramienta de exploración, no el reemplazo, y no se adelanta al diseño.

**Mensajes**

- [pi] Codex: el cliente instrumentado es la única vía al original; por favor no llamar al
  servicio por otra vía, para no gastar presupuesto sin registro.

**Registro**

- [pi] 2026-10-10: creada esta sección y el protocolo de coordinación. Iniciado el cliente.
