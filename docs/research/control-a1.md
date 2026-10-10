# A1 · fórmula del control

La fórmula quedó confirmada contra nueve mensajes nuevos reservados, con sus
nueve controles alternativos, en dos secuencias independientes sin caché. Los
bordes y pares mínimos se repitieron también desde otro reset. Observación `v1`;
no se afirma que siga vigente después del cambio anunciado.

## Algoritmo reproducible

1. Separar el último campo `;control`. El cálculo recibe todo el texto anterior,
   incluidos comando y argumentos; no recibe el último separador ni el control.
2. Retener solo caracteres ASCII `[A-Za-z0-9]`. Filtrar antes del casing: no
   normalizar Unicode ni convertir `ß` en SS o `ı` en I.
3. Convertir cada letra ASCII, sin distinguir caja, a su posición A=1…Z=26.
   Conservar cada dígito. Concatenar las representaciones decimales sin padding:
   L aporta `12`, T aporta `20`; no son un solo dígito cada una.
4. Añadir dos ceros a esa cadena decimal y calcular su resto módulo 97.
5. El control es **98 menos el resto**, sin una reducción módulo 97 posterior.
   El resultado está entre 2 y 98. Emitirlo como decimal canónico sin padding.

Ejemplo: `ALTA;A` produce `1122011`; con `00` el resto es 36, y el control es 62.
`ALTA;BZ` requiere 97, no 0; `ALTA;HD` requiere 98, no 1.
`control.py` acumula el resto por dígito, sin construir un entero gigante.

El cálculo no sustituye al parser ni a las validaciones de comandos. Los
separadores pueden producir E302 aunque se ignoren en el checksum; `007` alcanza
E303 con su control válido. La representación del control se valida aparte:
`03`/`05` dan E202 frente a 3/5; `062`/`0062` dan E201. No se deduce una gramática
completa de estos casos. PING no se usa como oráculo de integridad.

## Evidencia y presupuesto

| Tanda | IDs | Reservas nuevas | Resultado |
| --- | --- | ---: | --- |
| Verificación inicial | 51–60 | 10 | 51 falla por DNS; 52 reset y 53–60 confirman controles conocidos/delta −3. |
| Barrido ALTA A | 61–124 | 64 | Primer control aceptado62; intentos 0–61 rechazados. |
| Pares mínimos | 125–147 | 23 | Longitud, caja, separadores, ceros de IDs y acentos. |
| Bordes | 148–161 | 14 | Corrige el candidato: sin módulo final; filtrar antes de casing Unicode. |
| Reservados, dos resets | 162–199 | 38 | Nueve predicciones/vecinos, repetidas sin ajuste de parámetros. |
| Confirmación final | 200–225 | 26 | Repite bordes/pares; 7 y 007 usan controles distintos 10/70. |
| Total A1 | 51–225 | **175** | **174 respuestas completas**, un intento de transporte sin evidencia. |

Cuota local al empezar: 50. Al cerrar: **225/7800**, quedan **7575** bajo el tope
local y 7775 respecto del máximo remoto de 8000. Las reservas conservadoras
incluyen el intento DNS; no se asegura que ese intento haya llegado al servidor.
No hubo respuestas de infraestructura rate-limit en A1.

Todas las llamadas usaron `bb.py`, sin modificarlo. El worktree comparte
`.explore/` del checkout principal como coordinador de cuota y locks, pero su
log canónico está en la raíz del worktree y se versiona en esta rama. Nunca
usar el coordinador separado por defecto del worktree para este token.
Los subagentes Luna analizaron candidatos, implementaron herramientas y revisaron
sondas offline; el agente principal centralizó las solicitudes al original.

## Alcance de la búsqueda 0–99

`0–99` define el espacio de candidatos, con parada al primer control compatible;
no exige probar los cien valores para cada mensaje. Esta política ya estaba
acordada en la [estrategia inicial, sección 2, paso 3](estrategia-descubrimiento.md#2-el-cuello-de-botella-el-dígito-de-control):
ordenar candidatos y parar en el primer acierto. El objetivo de A1 es obtener
una fórmula que acierte mensajes reservados y rechace controles alternativos,
con repetición independiente; ese criterio se cumplió.

Para `ALTA;A`, el barrido probó 0–62: IDs 62–123 rechazados y 124 aceptado.
Se detuvo en 62. El vecino 63 se probó después y dio E202 (ID 147); los valores
64–99 no se probaron para ese mensaje. Esto no constituye una comprobación
exhaustiva de que exista un único control aceptado por cada mensaje. La
confianza se limita a las predicciones y rechazos documentados; no se presenta
el resto del rango como evidencia observada. No se añadieron llamadas para
resolver esta aclaración documental.

## Validación reservada

Los nueve textos se congelaron en `tmp/a1_holdouts.json` antes de hallar la
fórmula completa. Se conserva su copia en `tests/corpus/a1/reserved-bases.json`.
No se ajustaron parámetros con estos resultados.

| Base nueva | Control | Respuesta con control correcto | IDs correcto/vecino, repetición 1 / repetición 2 |
| --- | ---: | --- | --- |
| ALTA;Zoë | 90 | 201, AC-0001 | 163/164 / 182/183 |
| ALTA;A+U+0301 | 62 | 201, AC-0002 | 165/166 / 184/185 |
| CONSULTA;AC-0042 | 85 | 404 E401 | 167/168 / 186/187 |
| DEPOSITO;AC-0001;1234 | 12 | 200, OP-0001 | 169/170 / 188/189 |
| TRANSFER;AC-0002;AC-0001;6789 | 10 | 422 E507 | 171/172 / 190/191 |
| ANULA;OP-0042 | 46 | 404 E402 | 173/174 / 192/193 |
| alta;Iris | 21 | 201, AC-0003 | 175/176 / 194/195 |
| CONSULTA;AC-00042 | 35 | 404 E401 | 177/178 / 196/197 |
| ALTA;Q;R | 65 | 400 E302 | 179/180 / 198/199 |

Todos los vecinos (control correcto+1) dieron 400 E202. Los bytes y status de las
18 respuestas por repetición coinciden entre sí; los resets son 162 y 181.

## Artefactos y límites

- `tools/explorer/control.py`: generador offline sin token ni red, listo para
  portar la fórmula a B3; no se integra aún en el runtime Go.
- `tools/explorer/control_probe.py`: barrido por rangos mediante el cliente
  instrumentado, reset y lock; no confunde PING/auth/respuestas desconocidas con
  aceptación del control. El rango 0–98 son 99 sondas + reset; el 99 se puede sondear
  en otra secuencia. Los reintentos también consumen cuota.
- `tests/corpus/a1/`: siete secuencias con resets, 174 respuestas, IDs y bytes;
  `test_control_evidence.py` comprueba fórmula y trazabilidad contra el log.
- `experimentos.jsonl`: conserva intentos, respuestas y conclusiones; cada
  bloque se commiteó por separado con el explorador detenido.

El tratamiento de los casos sondeados está confirmado; no se pretende cubrir
con A1 todos los límites de entrada, formatos numéricos o excepciones del
protocolo. E303 para monto 007 es una observación única y queda probable. La
semántica de estado permanece en A3 y la gramática general en A4. A2 debe
construir/repetir la línea base completa; A6 detectará los cambios de versión.
