# Progreso · diseño y reemplazo de caja negra

## Objetivo y entregables

- [x] Acordar el alcance y las decisiones del diseño mediante entrevista.
- [x] Redactar en Markdown el documento único de diseño y especificación, conciso y sin límite de una página impresa.
- [x] Construir el diagrama de arquitectura coherente con el documento.
- [ ] Revisar ambos entregables con el equipo.
- [x] Convertir el diseño inicial acordado a PDF; generar también HTML autónomo local.
- [x] Desglosar la implementación a partir del diseño acordado.

## Estado actual

Fase: diseño inicial entregado; entrevista cerrada por confirmación del usuario (Q11).
Servicio Go pendiente de implementación. Cliente de exploración existente del frente pi.
Se leyó `AGENTS.md` y `docs/old-system/README.md` antes de modificar archivos.
En la inspección inicial solo había instrucciones, enunciado y corpus, sin repositorio Git.
Durante el trabajo paralelo se inicializó Git y pi creó `tools/explorer/bb.py` y su estrategia.
Codex no hizo solicitudes al servicio original; conserva todo el presupuesto para exploración.
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
- La entrega del reto es a las 20:00 contra la versión vigente. El README no indica zona;
  el frente pi registra decisión del usuario: Bogotá UTC-5. Cambio: 20:30 UTC/14:30 CDMX;
  entrega: 01:00 UTC del día siguiente/19:00 CDMX. No hay sondeo automático programado.
- El documento único incorporará diseño y las siete secciones de especificación del reto;
  `experimentos.jsonl` seguirá siendo un artefacto separado. «Una página» significa una
  página web, no una página impresa: preservar concisión sin omitir información necesaria.
- Los tokens permanecen fuera de documentos, logs y commits.

## Árbol de decisiones

1. Alcance: investigación, validación y reemplazo. Aceptado por usuario (Q1).
2. Documentación: documento único de longitud flexible, preferiblemente corto; una página
   web es una forma válida de entrega. Aceptado por usuario (Q2).
3. Lenguaje: Go preferido por experiencia del usuario; libertad de tecnología. Aceptado
   por usuario (Q3). Hosting resuelto en Q9.
4. Presupuesto: hasta una hora para crear y entregar diseño inicial; terminar antes deja
   más tiempo para implementar. Prioridad: consistencia y buen puntaje. Aceptado (Q4).
   Referencia de reloj al registrar respuestas: 2026-10-10 15:50 UTC.
5. Estado: memoria permitida inicialmente; persistencia obligatoria en entrega final.
   Aceptado (Q5). Mecanismo resuelto en Q8; SQLite sí es transaccional, aunque local.
6. Investigación: cliente/corpus, gramática/control, estado, límites/errores, repetición.
   Aceptado (Q6). Cambios del original se investigan mediante procesos repetibles y se
   incorporan estáticamente al código, con redespliegue; no autoadaptación en runtime.
7. Diagrama: fuente Mermaid separada y SVG o PNG, referenciado desde Markdown.
   Aceptado (Q7).
8. Persistencia final: SQLite con interfaz de almacenamiento; memoria inicial permitida.
   Aceptado (Q8). SQLite es transaccional y local; no requiere servidor de base de datos.
9. Hosting: Railway con una réplica, Serverless desactivado y volumen para SQLite;
   local + ngrok como respaldo. Aceptado (Q9). Elegibilidad/créditos pendientes de comprobar.
10. Detección: un comando manual establece referencia y repite corpus después del cambio
    de las 15:30 y antes de entrega; reset por secuencia, log y reporte de diferencias.
    Correcciones estáticas y redespliegue. Aceptado (Q10).
11. Arquitectura consolidada y criterio de cierre aceptados: «De acuerdo» (Q11).
12. Capas, responsabilidades, dependencias y árbol de directorios incluidos por petición
    posterior del usuario. Fuente: `docs/system-design.md`.

## Hosting: investigación preliminar

Documentación oficial consultada por `hosting_facts`:

- Railway: trial de $5/30 días, una réplica, Serverless configurable y volumen hasta
  0,5 GB en Trial/Free. Validar elegibilidad de la cuenta y presupuesto antes de desplegar.
  Fuentes: https://docs.railway.com/pricing/free-trial,
  https://docs.railway.com/pricing/plans,
  https://docs.railway.com/deployments/serverless.
- Local + ngrok Free: 20.000 requests/mes, 1 GB/mes; el endpoint no tiene timeout de
  duración. Depende del equipo y red local; persistencia requiere almacenamiento local.
  Fuente: https://ngrok.com/docs/pricing-limits/free-plan-limits.
- Render Free: suspensión tras 15 minutos y arranque de alrededor de un minuto; no
  permite disco persistente gratuito. Riesgo frente al máximo de 5 segundos por paso.
  Fuente: https://render.com/docs/free.
- Fly Trial: 2 VM-horas o 7 días; detención automática tras 5 minutos durante trial.
  Fuente: https://fly.io/docs/about/free-trial/.

Decisión aceptada: Railway con una réplica, Serverless desactivado y volumen;
local + ngrok como alternativa. Un filesystem efímero no cumple persistencia final.

Las preguntas de comportamiento pendientes se resuelven con experimentos, no con supuestos
de arquitectura: control, precedencia, alcance de reset, números, límites y anulaciones.

## Coordinación

| Responsable | Trabajo | Estado | Salida |
| --- | --- | --- | --- |
| Agente principal + usuario | Entrevista y decisiones | Completado | Diseño inicial acordado |
| Codex | Documento, capas, árbol, diagrama y exportación | Completado | Markdown, Mermaid, SVG, HTML y PDF |
| Agente `design_facts` | Inspección de corpus y archivos, solo lectura | Completado | Hechos y vacíos incorporados aquí |
| Agente `hosting_facts` | Comparar hosting con fuentes oficiales actuales | Completado | Comparación incorporada aquí |

Para continuar: leer este archivo y el README; distinguir hechos, recomendaciones y
decisiones aceptadas. Registrar decisiones con su razón y actualizar tareas y bloqueos.
La confirmación para cerrar la entrevista ya llegó. Continuar implementación según el
desglose siguiente y coordinarse con pi antes de cualquier consulta al original.

## Entregables y reproducción

- Diseño y especificación incremental: `docs/system-design.md`.
- Diagrama: `docs/architecture.mmd` y `docs/architecture.svg`.
- Entregable PDF: `output/pdf/system-design.pdf` (9 páginas A4 tras correcciones).
- Página HTML local autónoma: `docs/system-design.html` (no publicada).
- Regenerar todos: `python3 scripts/export_design_pdf.py`.
- Dependencias de exportación: Python/PyQt6, Pandoc, Graphviz y librsvg. SVG generado
  sin red desde el subconjunto Mermaid utilizado; no requiere descargar Mermaid CLI.
- Verificación: enlaces locales válidos, diagrama revisado visualmente, PDF renderizado
  a PNG y revisado, siete secciones presentes. No se afirma compatibilidad ejecutable.

## Implementación: tareas y dependencias

| Tarea | Responsable propuesto | Depende de | Criterio de salida | Estado |
| --- | --- | --- | --- | --- |
| I1. Replay de referencia y precedencia | pi | Cliente instrumentado existente | Secuencias registradas con reset, hipótesis e IDs | Pendiente según sección pi |
| I2. Esqueleto Go por capas y HTTP | Codex | Diseño acordado; evidencia para comportamiento HTTP | Composición y adaptadores separados, sin acceso al original | Pendiente |
| I3. Gramática y control | pi evidencia / Codex implementación | I1 | Fórmula repetida en sondas nuevas y reglas citadas | Pendiente |
| I4. Motor y comandos | Codex | I3 + evidencia de estado | Corpus ampliado pasa; orden de validaciones observado | Pendiente |
| I5. SQLite y reset | Codex | I2 + alcance del estado observado | Reinicio conserva cuentas/operaciones/IDs; reset atómico | Pendiente |
| I6. CLI único de replay/diff | Coordinar con pi | I1 + formato de corpus | Baseline/replay/diff; caché desactivada para cambio; salida no exitosa si incompleto | Pendiente |
| I7. Detección del cambio | pi con operador | I6 + referencia anterior | Delta reproducido e IDs incorporados a sección 6 | Pendiente |
| I8. Despliegue y entrega | Codex + usuario para cuenta si necesario | I4/I5 + cuenta/créditos Railway | Endpoint público, volumen persistente, menos de 5 s por paso | Pendiente |

## Mensajes de Codex para coordinación

- [codex] pi: diseño cerrado; reutilizaremos `tools/explorer/bb.py`, no crearemos otra
  vía al original. El runtime será Go sin `BB_TOKEN` ni importaciones del explorador.
- [codex] pi: el árbol propuesto agrega `tools/explorer/cli.py`, `sequences.py`, `probes/`
  y `compare.py`. Coordinar esos archivos antes de implementar para evitar duplicación.
- [codex] pi: el contrato del diseño requiere conservar también intentos de infraestructura
  y fallos de transporte fuera de la evidencia válida; revisar garantías del cliente existente.
  La detección del cambio debe evitar caché y reportar ejecución incompleta explícitamente.

## Registro

- 2026-10-10: iniciada entrevista con skill `grilling`; creada bitácora de coordinación.
  Inspección del corpus delegada. Pendiente primera ronda de decisiones del usuario.
- 2026-10-10: respuestas Q1–Q4 incorporadas. Go preferido; documento de longitud flexible;
  alcance integral y una hora para diseño inicial. Investigación de hosting delegada.
- 2026-10-10: respuestas Q5–Q7 incorporadas: persistencia final obligatoria, proceso de
  adaptación estático y repetible, diagrama separado. Comparación de hosting completada.
- 2026-10-10: respuestas Q8–Q10 aceptadas: SQLite, Railway con volumen/ngrok como respaldo,
  y detección manual con un comando. Preparada revisión consolidada para cerrar entrevista.
- [codex] 2026-10-10: Q11 confirmado. Usuario pidió capas y árbol del repositorio;
  incluidos en diseño y entregables. Frente pi incorporado como fuente de coordinación.
- [codex] 2026-10-10: creados Markdown, Mermaid/SVG y HTML autónomo; PDF de 7 páginas
  generado y revisado visualmente. Desglosada implementación; servicio Go aún pendiente.

## Correcciones de diseño y exportación PNG

- [codex] 2026-10-10: atendidos los hallazgos documentales prioritarios H-01/H-02/H-04/H-05, G-04 y O-01..O-03; estado detallado y pendientes en `tmp/hallazgos-diseno.md`, sección 7.
- [codex] Especificación separada en `docs/specification.md` con IDs 1-50 de la evidencia v1. Esto actualiza la decisión previa de documento único: PDF/HTML reúnen diseño y especificación; fuentes Markdown separadas para revisión.
- [codex] Diagrama PNG reproducible en `output/png/architecture.png`; fuente única Mermaid y SVG actualizados. Runtime Go, hosting y replay posterior al cambio siguen pendientes.

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
- [x] Cliente instrumentado en Python: `tools/explorer/bb.py` con 10 pruebas contra un
  servidor falso (commit `40a9552`). Uso en `tools/explorer/README.md`. Aún sin llamadas reales.
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
- [pi] 2026-10-10: cliente listo: log con hipótesis, rate limit, tope diario, caché por
  prefijo y epoch, y descarte de rate-limit de infraestructura. Pendiente: confirmar el token
  de exploración antes de la fase 1.
