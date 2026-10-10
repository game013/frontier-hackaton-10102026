#!/usr/bin/env python3
"""Exporta el subconjunto Mermaid del diagrama a SVG con Graphviz, sin red.

La fuente única es docs/architecture.mmd. Este exportador admite los nodos,
subgraphs, clases y aristas usados aquí; falla ante sintaxis nueva desconocida.
No reemplaza un renderer general de Mermaid.
"""
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/architecture.mmd"
OUTPUT = ROOT / "docs/architecture.svg"


def quote(value):
    return json.dumps(value, ensure_ascii=False)


def main():
    nodes, groups, edges, classes = {}, {}, [], {}
    active = None
    for raw in SOURCE.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith(("flowchart ", "%%", "classDef ")):
            continue
        match = re.fullmatch(r'subgraph (\w+)\["(.+)"\]', line)
        if match:
            active = match[1]
            groups[active] = {"label": match[2], "nodes": []}
            continue
        if line == "end":
            active = None
            continue
        match = re.fullmatch(r'class ([\w,]+) (\w+);', line)
        if match:
            for node in match[1].split(","):
                classes[node] = match[2]
            continue
        match = re.fullmatch(r'(\w+)\[\(?"(.+)"\)?\]', line)
        if match:
            node, label = match.groups()
            nodes[node] = (label.replace("<br/>", "\n"), "cylinder" if '[("' in line else "box")
            if active:
                groups[active]["nodes"].append(node)
            continue
        match = re.fullmatch(r'(\w+) --> (\w+)', line)
        if match:
            edges.append((*match.groups(), "", False))
            continue
        match = re.fullmatch(r'(\w+) -\. "(.+)" \.-> (\w+)', line)
        if match:
            edges.append((match[1], match[3], match[2], True))
            continue
        raise ValueError(f"Sintaxis no admitida: {line}")
    palette = {
        "runtime": ("#e9f3ff", "#245c91"),
        "research": ("#eef8f1", "#3e7650"),
        "artifact": ("#fff6df", "#a07621"),
    }
    lines = ['digraph Architecture {',
             'graph [rankdir=TB, bgcolor="white", pad=0.35, nodesep=0.32, ranksep=0.65, compound=true, fontname="Helvetica", fontsize=20, outputorder=edgesfirst];',
             'node [fontname="Helvetica", fontsize=14, style="rounded,filled", margin="0.18,0.12", color="#64748b", fillcolor="#f1f5f9", fontcolor="#172b40"];',
             'edge [fontname="Helvetica", fontsize=11, color="#64748b", arrowsize=0.7];']
    for node, (label, shape) in nodes.items():
        fill, stroke = palette.get(classes.get(node), ("#f1f5f9", "#64748b"))
        lines.append(f'{node} [label={quote(label)}, shape={shape}, fillcolor="{fill}", color="{stroke}"];')
    for group, data in groups.items():
        lines.append(f'subgraph cluster_{group} {{ label={quote(data["label"])}; color="#cbd5e1"; style="rounded"; margin=20;')
        lines.extend(f'{node};' for node in data["nodes"])
        # Los ranks pertenecen al cluster para conservar sus límites visuales.
        for row in [("operator", "runner", "client", "original"),
                    ("evidence", "diff", "review"), ("http", "engine", "store", "db"),
                    ("protocol", "state")]:
            if all(node in data["nodes"] for node in row):
                lines.append('{ rank=same; ' + '; '.join(row) + '; }')
                lines.append(' -> '.join(row) + ' [style=invis, weight=100];')
        lines.append('}')
    for start, end, label, dotted in edges:
        if start not in nodes or end not in nodes:
            raise ValueError(f"Arista con nodo inexistente: {start} -> {end}")
        style = 'style=dashed, constraint=false' if dotted else 'style=solid, weight=10'
        lines.append(f'{start} -> {end} [label={quote(label)}, {style}];')
    lines.extend(['review -> evaluator [style=invis];', 'db -> backup [style=invis];', '}'])
    subprocess.run(["dot", "-Tsvg", "-o", str(OUTPUT)], input="\n".join(lines), text=True, check=True)
    print(f"SVG generado: {len(nodes)} nodos, {len(edges)} aristas; {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
