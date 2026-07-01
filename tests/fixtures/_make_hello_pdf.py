"""Regenerate tests/fixtures/hello.pdf. Requires reportlab (dev dep)."""
from pathlib import Path
from reportlab.pdfgen import canvas

out = Path(__file__).parent / "hello.pdf"
c = canvas.Canvas(str(out))
for text in ("page one alpha", "page two beta", "page three gamma"):
    c.drawString(100, 700, text)
    c.showPage()
c.save()
print(f"wrote {out}")
