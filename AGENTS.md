# Caja negra · reemplazo de un servicio sin documentación

Hackathon, reto 2. Hacemos ingeniería inversa de un servicio HTTP (por observación) y construimos un
reemplazo que responde **byte a byte igual**, errores incluidos. Enunciado completo, contrato y
formatos de entrega: `docs/old-system/README.md`. Léelo antes de tocar algo.

- **Protocolo:** `POST /msg` con `{"m": "CMD;arg1;...;control"}`. El último campo es un dígito de
  control (0–99) cuya fórmula todavía no conocemos. Hay estado por token (cuentas `AC-NNNN`,
  operaciones `OP-NNNN`); `POST /__reset` lo reinicia.
- **Ejemplos grabados:** `docs/old-system/pruebas/ejemplos.jsonl`.
- **Tokens:** `.env` (`BB_TOKEN`, `TEAM_TOKEN`). Fuera de git, y fuera de logs y commits.

## Commits

Cada vez que completes un paso, haz un commit **atómico, transaccional y convencional**:

- **Atómico:** un solo cambio lógico por commit; no mezcles temas.
- **Transaccional:** el repo queda consistente y funcional tras cada commit (todo o nada); no dejes
  trabajo a medias ni commits que rompan lo anterior.
- **Convencional:** formato Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`, `test:`,
  `refactor:`), con asunto corto en imperativo.
- Nunca incluyas `.env`, tokens ni secretos.

## Archivos temporales: exclusión obligatoria

- Mantén `tmp/` (también `TMP/` y cualquier variante de mayúsculas) y todo su contenido
  exclusivamente en disco local, fuera del índice de Git, de los commits y del remoto.
- Esta exclusión es permanente: nunca uses `git add -f` ni retires la regla de `.gitignore`
  para incluir archivos temporales. Añade los entregables mediante sus rutas explícitas.
- Antes de cada commit, verifica que `git ls-files | rg -i '(^|/)tmp(/|$)'` no devuelva
  ninguna ruta. Si devuelve rutas, quita únicamente su seguimiento con `git rm --cached`
  (con `-r` para carpetas), conservando los archivos locales. `.gitignore` no deja de seguir
  archivos que ya estaban versionados.
- Revisa `git diff --cached --name-status`: las únicas entradas permitidas bajo `tmp/`
  son eliminaciones del índice para corregir una inclusión previa; nunca altas ni modificaciones.

## Reglas duras

- El reemplazo es autónomo: no puede llamar al original. Si lo hace, la evaluación vale 0.
- Cada request al original queda registrado en `experimentos.jsonl` con su `hipotesis` (formato en
  el README). Pasa siempre por el cliente instrumentado; la especificación cita esos `id`.
- Cada secuencia empieza con `POST /__reset`. Límite: 10 req/s y 8.000 por día por token. Una
  respuesta con el header `X-Frontier-Infra: rate-limit` viene de la infraestructura, no del servicio:
  descártala.
- `experimentos.jsonl` es un entregable: va versionado en la raíz, nunca en `.gitignore`. Tras cada
  bloque de experimentos (sin `bb.py` en ejecución) commitéalo aparte con `git add experimentos.jsonl`
  explícito. Detalle en `tools/explorer/README.md`.
- **Incidente FR-0153 (activo desde las 15:30):** el original responde como **versión 2**. Cambiaron
  exactamente **3 comportamientos**; el resto es igual que en v1. Los tests de conformidad corren
  contra v2, así que el reemplazo debe comportarse como v2 (`BEHAVIOR_VERSION=v2`, nunca por reloj).
  Detecta los deltas repitiendo el corpus `v1` contra el original. Si salen más o menos de 3, revisa
  la evidencia antes de concluir. Cada delta va en `experimentos.jsonl` (con `hipotesis` e IDs
  v1/v2), en la especificación (sección 6) y en el debrief. Ticket transcrito:
  `docs/old-system/incidente-FR-0153.md`.
