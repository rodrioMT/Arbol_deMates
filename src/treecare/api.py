from __future__ import annotations
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from pathlib import Path
import fitz  # PyMuPDF
from typing import Tuple
import base64

app = FastAPI(title="TreeCare Crop API")

class CropRequest(BaseModel):
    pdf_path: str
    page_index: int
    bbox_norm: tuple[float, float, float, float]  # x0,y0,x1,y1 in [0,1]
    scale: float | None = None  # optional DPI scale
    format: str | None = None  # 'png' or 'jpeg'


def clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


def to_pixels(rect: Tuple[float, float, float, float], width: int, height: int):
    x0, y0, x1, y1 = rect
    return (
        int(clamp01(x0) * width),
        int(clamp01(y0) * height),
        int(clamp01(x1) * width),
        int(clamp01(y1) * height),
    )


@app.post("/crop")
def crop(req: CropRequest):
    pdf_path = Path(req.pdf_path)
    if not pdf_path.exists():
        raise HTTPException(404, detail="PDF not found")
    doc = fitz.open(pdf_path)
    if req.page_index < 0 or req.page_index >= len(doc):
        raise HTTPException(400, detail="Invalid page index")
    page = doc[req.page_index]
    # Rasterize page
    zoom = req.scale if req.scale else 2.0
    mat = fitz.Matrix(zoom, zoom)
    # Compute clip rect in page coordinates
    x0n, y0n, x1n, y1n = req.bbox_norm
    rect = fitz.Rect(
        x0n * page.rect.width,
        y0n * page.rect.height,
        x1n * page.rect.width,
        y1n * page.rect.height,
    )
    # Rasterize with clip
    cropped = page.get_pixmap(matrix=mat, clip=rect, alpha=False)
    # Return as WebP bytes
    fmt = (req.format or "png").lower()
    if fmt not in ("png", "jpeg", "jpg"):
        fmt = "png"
    fmt = "jpeg" if fmt == "jpg" else fmt
    data = cropped.tobytes(fmt)
    return {
        "width": cropped.width,
        "height": cropped.height,
        "format": fmt,
        "data_base64": base64.b64encode(data).decode("ascii"),
    }
