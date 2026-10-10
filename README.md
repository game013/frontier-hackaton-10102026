# frontier-hackaton-10102026

Diseño inicial del reemplazo autónomo HTTP en Go, con SQLite y despliegue en Railway.

- [Documento de diseño y especificación incremental](docs/system-design.md): capas,
  dependencias, árbol de directorios, investigación y criterios de entrega.
- [PDF entregable](output/pdf/system-design.pdf) y [página HTML autónoma](docs/system-design.html).
- [Diagrama SVG](docs/architecture.svg) y [fuente Mermaid](docs/architecture.mmd).
- [Progreso y coordinación](PROGRESS.md).
- [Estrategia de descubrimiento](docs/research/estrategia-descubrimiento.md).
- [Cliente instrumentado existente](tools/explorer/README.md): única vía al original.

El servicio Go y el comando de replay descritos en el diseño aún están por implementar.
Las observaciones del corpus no sustituyen evidencia de `experimentos.jsonl`.

Para regenerar los entregables después de editar el Markdown o Mermaid:

```sh
python3 scripts/export_design_pdf.py
```

Requiere Python con PyQt6, Pandoc, Graphviz (`dot`) y librsvg (`rsvg-convert`).
La exportación SVG usa un subconjunto de Mermaid convertido a Graphviz sin red;
no es un renderer general de Mermaid. Alternativamente, renderizar el `.mmd` con Mermaid CLI.
