from __future__ import annotations
from pathlib import Path
import sqlite3
import fitz  # PyMuPDF
from .db import deserialize_bbox


def export_crops(db_path: str, out_dir: str, zoom: float = 2.0):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, pdf_path, page_index, bbox_norm FROM problems ORDER BY pdf_path, page_index, id")
        rows = cur.fetchall()
        current_pdf = None
        doc = None
        for pid, pdf_path, page_index, bbox_norm in rows:
            if current_pdf != pdf_path:
                if doc is not None:
                    doc.close()
                doc = fitz.open(pdf_path)
                current_pdf = pdf_path
            page = doc[page_index]
            x0,y0,x1,y1 = deserialize_bbox(bbox_norm)
            # rasterize and crop
            mat = fitz.Matrix(zoom, zoom)
            rect = fitz.Rect(x0*page.rect.width, y0*page.rect.height, x1*page.rect.width, y1*page.rect.height)
            pix = page.get_pixmap(matrix=mat, clip=rect, alpha=False)
            base = Path(pdf_path).stem
            fname = f"{base}_p{page_index:03d}_prob{pid:06d}.png"
            pix.save(str(out / fname))
        if doc is not None:
            doc.close()
    finally:
        conn.close()
