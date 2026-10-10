# frontier-hackaton-10102026

Reemplazo autónomo HTTP en Go, con SQLite implementado y despliegue en Railway pendiente.

- [Documento de diseño](docs/system-design.md): capas,
  dependencias, árbol de directorios, investigación y criterios de entrega.
- [PDF entregable](output/pdf/system-design.pdf) y [página HTML autónoma](docs/system-design.html).
- [Especificación incremental](docs/specification.md): observaciones, IDs del log y confianza.
- [Diagrama PNG](output/png/architecture.png), [SVG](docs/architecture.svg) y [fuente Mermaid](docs/architecture.mmd).
- [Progreso y coordinación](PROGRESS.md).
- [Estrategia de descubrimiento](docs/research/estrategia-descubrimiento.md).
- [Cliente instrumentado existente](tools/explorer/README.md): única vía al original.

Reemplazo Go: `make serve` (puerto 9900; `TEAM_TOKEN` obligatorio, `BEHAVIOR_VERSION`
por defecto `v1`) y `make test-go`. Cada request recibido, manejado o no, queda en
`CAPTURE_PATH` (por defecto `var/capture.jsonl`) y en stdout como JSONL `"kind":"capture"`;
`make seeds ARGS="<capturas o volcado de logs> -o <destino>"` lo agrupa por secuencia como
semilla de replay local ([tools/capture/seeds.py](tools/capture/seeds.py)). El arnés diferencial local se ejecuta con `make differential`
y compara status y bytes del corpus grabado usando SQLite temporal por secuencia.
Las observaciones del corpus no sustituyen evidencia de `experimentos.jsonl`.

El almacenamiento se selecciona al arrancar con **`STORAGE=sqlite|memory`**. El valor
por defecto es `sqlite`; `STATE_PATH` indica el archivo (por defecto `var/state.db`).
SQLite conserva cuentas, saldos, operaciones, anulaciones y contadores tras reiniciar.
`memory` es una opción volátil para uso local: pierde todo al terminar el proceso y
no usa `STATE_PATH`. Un valor desconocido impide arrancar.

`make serve` lee estas claves de `.env` si no están ya exportadas en el entorno
(valores sin comillas); solo carga `TEAM_TOKEN`, `STORAGE` y `STATE_PATH`, nunca
`BB_TOKEN`. Ejemplo de las claves nuevas, también disponible en [.env.example](.env.example),
sin incluir ningún secreto:

```dotenv
STORAGE=sqlite
STATE_PATH=var/state.db
```

También se puede seleccionar con `make serve STORAGE=memory` o con variables de entorno
al ejecutar el binario. Para Railway, configurar `STORAGE=sqlite` y `STATE_PATH=/data/state.db`
en un volumen persistente, con una sola réplica. El proceso abre y valida el esquema
antes de escuchar; un archivo inaccesible o esquema incompatible impide arrancar.
SIGTERM/SIGINT detienen el servidor y cierran el almacenamiento. Reset es transaccional;
si falla, devuelve 500 E500 (supuesto del reemplazo), sin informar éxito.

Pruebas de persistencia y límites: [almacenamiento B5](docs/storage-b5.md).

Para regenerar los entregables después de editar el Markdown o Mermaid:

```sh
python3 scripts/export_design_pdf.py
```

Para exportar solo el PNG: `python3 scripts/render_architecture.py --format png`.

Requiere Python con PyQt6, Pandoc, Graphviz (`dot`) y librsvg (`rsvg-convert`).
La exportación SVG usa un subconjunto de Mermaid convertido a Graphviz sin red;
no es un renderer general de Mermaid. Alternativamente, renderizar el `.mmd` con Mermaid CLI.

Para ejecutar el explorador: `make explore ARGS="run SEQ tmp/sondas.jsonl --no-cache"`.
Formato de secuencias, opciones y ejemplos: [guía del explorador](tools/explorer/README.md).
`make test-explorer` verifica el cliente con un servidor simulado local, sin consultar el original.
