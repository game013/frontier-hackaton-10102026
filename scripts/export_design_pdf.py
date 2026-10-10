"""Regenera SVG, HTML autónomo y PDF del diseño. Requiere Graphviz, librsvg,
Pandoc y PyQt6. El renderer Qt funciona sin navegador ni acceso a red.
"""
import os
from pathlib import Path
import sys
import subprocess

os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PyQt6.QtCore import QMarginsF, QUrl
from PyQt6.QtGui import QFont, QGuiApplication, QImage, QPageLayout, QPageSize, QPdfWriter, QTextDocument, QTextBlockFormat, QTextCursor
import re

root = Path(__file__).resolve().parents[1]
(root / "tmp/pdfs").mkdir(parents=True, exist_ok=True)
(root / "output/pdf").mkdir(parents=True, exist_ok=True)
subprocess.run([sys.executable, str(root / "scripts/render_architecture.py")], check=True)
subprocess.run([sys.executable, str(root / "scripts/render_architecture.py"), "--format", "png"], check=True)
diagram = root / "tmp/pdfs/diagram.png"
subprocess.run(["rsvg-convert", str(root / "docs/architecture.svg"), "-o", str(diagram)], check=True)
subprocess.run(["pandoc", "docs/system-design.md", "docs/specification.md", "--standalone", "--embed-resources",
                "--resource-path=docs:.", "--css=docs/design.css", "--metadata",
                "pagetitle=Caja negra: diseño del reemplazo HTTP", "-o", "docs/system-design.html"], cwd=root, check=True)
app = QGuiApplication(sys.argv)
output = root / "output/pdf/system-design.pdf"
html = (root / "docs/system-design.html").read_text()
diagram_image = QImage(str(diagram))
diagram_width = 600
diagram_height = round(diagram_width * diagram_image.height() / diagram_image.width())
html = re.sub(r'<img[^>]+>', f'<img src="{diagram.as_uri()}" width="{diagram_width}" height="{diagram_height}" />', html)
html = re.sub(r'<style.*?</style>', '', html, flags=re.S)
html = html.replace('<head>', '''<head><style>
body { color: #172b40; font-size: 10pt; }
h1 { font-size: 21pt; color: #123a60; }
h2 { font-size: 15pt; color: #123a60; }
h3 { font-size: 12pt; }
table { border-collapse: collapse; font-size: 8.5pt; }
td, th { padding: 5px; border: 1px solid #d8e2ec; }
th { background-color: #e9f3ff; }
pre { font-family: Menlo; font-size: 7pt; background-color: #f3f6fa; }
code { font-family: Menlo; font-size: 8pt; }
</style>''')
doc = QTextDocument()
doc.setDefaultFont(QFont("Arial", 10))
doc.setBaseUrl(QUrl.fromLocalFile(str(root / "docs") + "/"))
doc.setDocumentMargin(0)
doc.setHtml(html)
# Separar bloques extensos y evitar encabezados huérfanos.
block = doc.begin()
break_before = {
    "Capas y dependencias", "Árbol de directorios propuesto",
    "Matriz de cierre HTTP, siempre mediante el cliente instrumentado y reset por secuencia:",
    "Plan de implementación y aceptación",
    "Caja negra: especificación incremental", "3. Comandos",
}
while block.isValid():
    cursor = QTextCursor(block)
    fmt = block.blockFormat()
    if block.text() in break_before:
        fmt.setPageBreakPolicy(QTextBlockFormat.PageBreakFlag.PageBreak_AlwaysBefore)
    cursor.setBlockFormat(fmt)
    block = block.next()
writer = QPdfWriter(str(output))
writer.setResolution(96)
writer.setTitle("Caja negra: diseño del reemplazo HTTP")
writer.setPageLayout(QPageLayout(QPageSize(QPageSize.PageSizeId.A4), QPageLayout.Orientation.Portrait, QMarginsF(15, 16, 15, 16)))
doc.print(writer)
print(f"PDF generado: {output}")
