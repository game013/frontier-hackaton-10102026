"""Exporta el informe de revisión a PDF usando Pandoc y Qt sin red."""
import os
from pathlib import Path
import subprocess
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PyQt6.QtCore import QMarginsF
from PyQt6.QtGui import QFont, QGuiApplication, QPageLayout, QPageSize, QPdfWriter, QTextDocument

root = Path(__file__).resolve().parents[1]
source = root / "tmp/revision-cliente-instrumentado.md"
output = root / "output/pdf/revision-cliente-instrumentado.pdf"
output.parent.mkdir(parents=True, exist_ok=True)
html = subprocess.check_output(["pandoc", str(source), "--to=html"], text=True)
html = html.replace("—", "-").replace("–", "-").replace("‑", "-")
app = QGuiApplication(sys.argv)
doc = QTextDocument()
doc.setDefaultFont(QFont("Arial", 10))
doc.setDocumentMargin(0)
doc.setHtml("""<style>
body { color: #172b40; }
h1 { font-size: 20pt; color: #123a60; }
h2 { font-size: 14pt; color: #123a60; margin-top: 16px; }
p, li { line-height: 125%; }
table { border-collapse: collapse; font-size: 8pt; }
th { background-color: #e9f3ff; }
td, th { border: 1px solid #d8e2ec; padding: 5px; }
code { font-family: Menlo; font-size: 8pt; }
a { color: #245c8e; }
</style>""" + html)
writer = QPdfWriter(str(output))
writer.setResolution(96)
writer.setTitle("Revisión del cliente instrumentado - correcciones y validación")
writer.setPageLayout(QPageLayout(QPageSize(QPageSize.PageSizeId.A4),
                    QPageLayout.Orientation.Portrait, QMarginsF(16, 16, 16, 16)))
doc.print(writer)
print(output)
