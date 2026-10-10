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

## Reglas duras

- El reemplazo es autónomo: no puede llamar al original. Si lo hace, la evaluación vale 0.
- Cada request al original queda registrado en `experimentos.jsonl` con su `hipotesis` (formato en
  el README). Pasa siempre por el cliente instrumentado; la especificación cita esos `id`.
- Cada secuencia empieza con `POST /__reset`. Límite: 10 req/s y 8.000 por día por token. Una
  respuesta con el header `X-Frontier-Infra: rate-limit` viene de la infraestructura, no del servicio:
  descártala.
- A las 15:30 el servicio cambia. Detecta el cambio repitiendo el corpus contra el original y
  documéntalo en la especificación (sección 6).
