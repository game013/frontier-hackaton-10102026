# Estrategia de descubrimiento y fuzzing (análisis inicial)

Estado: borrador, 0 requests gastados al original. Todo lo que sigue sale del enunciado y de
`docs/old-system/pruebas/ejemplos.jsonl` (E1..E20 = líneas del corpus). Nada está confirmado
todavía: estas son hipótesis para planificar los experimentos.

## 1. Qué sabemos y qué falta

**Superficie conocida**

- Rutas: `POST /msg`, `POST /__reset`, `GET /health`. El contrato exige replicar también
  "cualquier otra ruta, incluidas las que no existen", así que hay que sondear rutas y métodos.
- Comandos vistos: `PING`, `ALTA`, `CONSULTA`, `DEPOSITO`, `TRANSFER`, `ANULA`.
- Errores vistos: `E201` control mal formado, `E202` control inválido, `E301` comando
  desconocido (con espacio final), `E302` aridad inválida, `E401` cuenta inexistente,
  `E506` límite excedido, `E507` saldo insuficiente.

**Lo más probable es que existan más.** Hay tres señales:

1. La numeración tiene huecos por familia: E1xx no aparece (¿sobre/JSON/auth?), E203+, E303+,
   E402+ (¿operación inexistente?) y E501–E505. Cada hueco es una regla que buscar.
2. El dominio está incompleto. Hay depósito pero no retiro, alta pero no baja, y no hay forma de
   listar operaciones. Un servicio bancario de 10 años suele tener más comandos.
3. `"comando desconocido "` termina en espacio. Puede ser una plantilla
   `"comando desconocido " + X` donde X a veces va vacío, y conviene ver cuándo no lo está.

Otros detalles que hay que tener en cuenta: `CONSULTa` (E11) se acepta con el mismo control que
`CONSULTA`, así que el comando no distingue mayúsculas o se normaliza antes del control. La clave
de CONSULTA es `cuenta_id`, en snake_case, y la de ALTA es `cuentaId`. `recieved` está mal escrito
a propósito. Además, el header `X-Req` es desconocido: puede ser un contador por token y no
sabemos si cuenta los resets.

## 2. El cuello de botella: el dígito de control

Todo depende de esto. Si no sabemos calcular el control, cada sonda tiene que barrer hasta 100
valores. Un comando candidato costaría ~50 requests de media en lugar de 1.

**Análisis offline ya hecho (0 requests):** con los 17 pares (cuerpo, control) del corpus:

- Ninguna de estas fórmulas encaja: suma, XOR, suma ponderada, polinómica (k<300), CRC32, Adler,
  MD5/SHA mod 100/97/99/101, con o sin `;`, con mayúsculas o solo argumentos.
- **Descartado: cualquier función lineal sobre bytes mod 100.** Entre E9 y E10 solo cambia un
  `2` por un `0` (Δbyte=2) y el control pasa de 55 a 12 (Δ=43). `2w ≡ 43 (mod 100)` no tiene
  solución.
- **Pista: mod 97.** CONSULTA AC-0001→14, AC-0002→11, AC-0009→87. Un peso de −3 sobre el
  último dígito da 14−24 = −10 ≡ 87 (mod 97). Encaja con un esquema tipo ISO 7064 / IBAN
  (mod 97). Es una hipótesis que hay que probar.

**Plan para descifrarlo (presupuesto ≤ 400 req):**

1. Usar un "oráculo" barato y sin estado: `CONSULTA;AC-NNNN;c`. Si el control es válido
   responde 404 `E401`; si no, 400 `E202`. E15 sugiere que el control se valida antes que la
   existencia, y lo primero es confirmarlo.
2. Hacer pares mínimos: cambiar un solo carácter y medir Δcontrol. Antes de barrer, predecir
   el valor con la hipótesis mod 97. Un acierto cuesta 1 request y un fallo pasa a barrido.
3. Si hay que barrer, ordenar los candidatos por probabilidad (los vecinos mod 97 primero) y
   parar en el primer acierto.
4. Comprobar si el control cubre el nombre del comando, los separadores, la caja de los
   argumentos y los ceros a la izquierda (`007` vs `7`).
5. Ver si `5X` (E17), `-1`, `100`, `064`, ` 64` y el campo vacío dan E201 o E202.

## 3. Precedencia de errores: lo primero que hay que medir

El orden de validación define cuánto cuesta descubrir comandos:

- Si `E301` (comando desconocido) se evalúa **antes** que el control, cada nombre candidato
  cuesta 1 request con cualquier control. E12 (`SALDOS;…;38`) lo sugiere, pero el 38 podía ser
  válido por casualidad.
- Lo mismo con `E302` (aridad, E20).

Experimento: el mismo comando desconocido con dos controles distintos, y ALTA con aridad
incorrecta y dos controles. Son ~6 requests y deciden toda la fase siguiente.

## 4. Descubrimiento de comandos y rutas

**Comandos** (cuando sepamos si E301 va antes que el control, o tengamos la fórmula):

- Diccionario español bancario, ~80–150 nombres: `RETIRO`, `EXTRACCION`, `BAJA`, `CIERRE`,
  `SALDO`, `MOVIMIENTOS`, `HISTORIAL`, `EXTRACTO`, `LISTA`, `CUENTAS`, `OPERACION`, `ESTADO`,
  `BLOQUEO`, `DESBLOQUEO`, `LIMITE`, `PAGO`, `REVERSA`, `AYUDA`, `HELP`, `VERSION`, `INFO`,
  `ECHO`, `RESET`, `STATS`, y variantes en inglés.
- Variantes de los conocidos: minúsculas, prefijos (`CONS`, `CONSULT`), espacios, comando vacío,
  `;` inicial o final, separadores alternativos.
- Cualquier respuesta distinta de `E301` cuenta como hallazgo y se investiga aparte.

**Rutas y sobre (~100 req, una sola secuencia sin estado):**

- Métodos en `/msg`, `/__reset` y `/health` (GET/PUT/DELETE/OPTIONS/HEAD). `/msg/`, `/MSG`,
  rutas típicas (`/`, `/api`, `/admin`, `/debug`, `/version`, `/metrics`, `/docs`) y 404 aleatorios.
- Auth: sin header, `Bearer` vacío, token inválido, esquema distinto. Ojo: esto tampoco es un
  token real, nunca hay que loguear el token verdadero.
- Cuerpo: JSON inválido, vacío, sin `m`, `m` no string, campos extra, `Content-Type` distinto,
  Unicode, `m` muy largo, muchos `;`.

## 5. Semántica de comandos (presupuesto ~1.500 req)

Por comando: aridad exacta, tipos y formato de argumentos, efecto en el estado y respuesta.
Técnicas para ahorrar:

- **Búsqueda binaria para umbrales.** El límite de E506 está entre 100.000 y 120.000 (E9/E10), y
  puede ser por operación o acumulado. Se resuelve en ~17 requests, frente a miles con un barrido.
- **Valores frontera, no cartesianos:** 0, 1, negativo, decimal, `1e3`, ceros a la izquierda,
  máximo int, cuenta propia (`TRANSFER A;A`), formato de ID (`AC-1`, `ac-0001`, `AC-00001`).
- **Pares mínimos de estado:** ANULA sobre DEPOSITO frente a TRANSFER, ANULA que deja saldo
  negativo, ANULA de un OP inexistente, contadores AC/OP tras error o tras anulación (¿se
  consume el número?).

## 6. Cómo ahorrar llamadas

1. **Primero offline.** Agotar hipótesis contra el corpus y contra lo ya registrado antes de
   gastar requests.
2. **Caché determinista.** La clave es (prefijo de secuencia desde reset, request). Si ya se
   observó, no se repite. Solo se repite a propósito, para confirmar (2 veces = confirmado) o
   para detectar el cambio de las 15:30.
3. **Agrupar las sondas sin estado** en una sola secuencia larga tras un único reset (errores de
   control, rutas, comandos desconocidos). Así no se paga un reset por sonda.
4. **Predecir antes de enviar.** El modelo local (el futuro reemplazo) predice cada respuesta.
   Si la predicción falla, el request era informativo. Si acierta, sube la confianza. Cuando
   el modelo acierte de forma consistente, dejar de explorar esa zona.
5. **Fuzzing diferencial al final:** generar secuencias aleatorias de 2–12 pasos con la mezcla
   del set de evaluación (40/45/15), ejecutarlas en local y luego en el original, y priorizar
   las regiones donde fallan.
6. **Un solo token por ahora.** Las fases son secuenciales y comparten los 8.000 requests. Si
   luego hay más tokens, se reparten así: control y sobre; comandos y semántica; regresión y 15:30.
7. **Limitador en el cliente** a ~8 req/s y contador persistente por token y día. Las
   respuestas con `X-Frontier-Infra: rate-limit` se descartan, no se registran como evidencia y
   se reintentan con backoff.

## 7. Presupuesto propuesto (por token, 8.000/día)

| Fase | Requests | Salida |
| --- | ---: | --- |
| 0. Análisis offline del corpus | 0 | hipótesis de control |
| 1. Replay del corpus (baseline) | 21 | comprobar determinismo, ver `X-Req` |
| 2. Precedencia E301/E302/E202 | ~10 | coste real de las fases siguientes |
| 3. Fórmula de control | ≤ 400 | generador de control local |
| 4. Rutas, sobre y auth | ~100 | sección 1 de la spec |
| 5. Descubrimiento de comandos | ~300 | lista cerrada de comandos |
| 6. Semántica y estado | ~1.500 | secciones 3 y 4 |
| 7. Errores y su orden | ~600 | sección 5 |
| 8. Corpus de regresión (antes de 15:30 Bogotá) | ~300 | baseline para comparar |
| 9. Re-ejecución tras 15:30 y diff | ~300 + exploración del delta ~800 | sección 6 |
| 10. Fuzzing diferencial | ~1.500 | cerrar huecos |
| Reserva | ~2.000 | imprevistos y cambio de la tarde |

**Horario** (Bogotá UTC−5, CDMX UTC−6):

| Hito | Bogotá | CDMX | UTC |
| --- | --- | --- | --- |
| Corpus de regresión listo y ejecutado | 15:00 | 14:00 | 20:00 |
| Cambio del servicio | 15:30 | 14:30 | 20:30 |
| Entrega; los tokens dejan de funcionar | 20:00 | 19:00 | 01:00 (+1 día) |

## 8. Qué necesitamos construir primero

La exploración se hace en Python y el reemplazo en Go.

1. **Cliente instrumentado** en Python (única vía al original). Debe exigir `hipotesis` y
   registrar en `experimentos.jsonl` todos los requests, incluidos `/__reset` y las sondas
   de rutas y auth (`id`, `seq`, `x_req`, `request`, `status`, `response`, `conclusion`).
   También aplica el rate limit, lleva el contador y la caché, y nunca escribe el token.
2. **Generador de control** local que se pueda probar con el corpus.
3. **Runner de secuencias** (reset + N pasos) que sirva tanto para el original como para el
   reemplazo, y que compare con las reglas del evaluador (JSON sin orden de claves, texto exacto).
4. **Corpus de regresión** versionado que crece con cada hallazgo confirmado.

## 9. Decisiones y pendientes

1. Tokens: uno solo por ahora. Decidido.
2. Se registran todos los requests, incluidos `/__reset` y las sondas de rutas y auth. Decidido.
3. Las horas del reto son de Bogotá (UTC−5); el usuario está en CDMX (UTC−6). Decidido.
4. Exploración en Python. Decidido.
5. Pendiente: tope de gasto para descifrar el control y qué hacer si se alcanza (ver abajo).

**Pendiente 5.** El reemplazo tiene que calcular el control para responder `E202` igual que el
original, así que la fórmula hace falta sí o sí. La duda es cuánto gastar en ella de entrada:

- **A. Control primero, con tope de 400.** Si se descifra, todo lo demás cuesta 1 request por
  prueba. Si se llega a 400 sin fórmula, se para, se pasa a comandos y se retoma más tarde con
  los datos acumulados.
- **B. Comandos primero, si la fase 2 muestra que "comando desconocido" se valida antes que el
  control.** Se buscan comandos con 1 request cada uno sin conocer la fórmula, y el control se
  ataca después con más ejemplos válidos a mano.

Propuesta: medir primero la precedencia (~10 requests) y aplicar B si es posible, si no A.
