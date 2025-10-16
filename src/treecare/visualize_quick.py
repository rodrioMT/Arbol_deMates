from __future__ import annotations
from pathlib import Path
import tempfile
import fitz  # PyMuPDF
from .config import settings
from .docai import process_pdf
from .pipeline import extract_blocks
from .segment import segment_page


def find_first_pdf(dir_path: str) -> Path:
    d = Path(dir_path)
    for pattern in ("*.pdf", "**/*.pdf"):
        files = sorted(d.glob(pattern))
        if files:
            return files[0]
    raise FileNotFoundError(f"No PDFs found in {dir_path}")


def make_3page_temp(pdf_path: Path) -> Path:
    with fitz.open(str(pdf_path)) as src:
        n = min(3, len(src))
        if n == 0:
            raise ValueError("PDF has 0 pages")
        doc = fitz.open()
        doc.insert_pdf(src, from_page=0, to_page=n - 1)
        tmp_dir = Path(tempfile.mkdtemp(prefix="treecare_quickviz_"))
        out = tmp_dir / f"{pdf_path.stem}_first3.pdf"
        doc.save(str(out))
        doc.close()
        return out


def to_xyxy(norm_bbox):
    # norm bbox is list of vertices or already xyxy tuple
    if isinstance(norm_bbox, tuple) or isinstance(norm_bbox, list) and len(norm_bbox) == 4 and isinstance(norm_bbox[0], (int,float)):
        return tuple(norm_bbox)
    xs = [v["x"] for v in norm_bbox]
    ys = [v["y"] for v in norm_bbox]
    return (min(xs), min(ys), max(xs), max(ys))


def main():
    pdf_path = find_first_pdf("pdfs/raw")
    sample_pdf = make_3page_temp(pdf_path)
    # Process with Document AI
    doc = process_pdf(settings.project_id, settings.location, settings.processor_id, str(sample_pdf))
    # Extract blocks and segment per page
    blocks = extract_blocks(doc)
    pages = {}
    for b in blocks:
        pages.setdefault(b["page_index"], []).append(b)

    out_dir = Path("data/crops_quick")
    out_dir.mkdir(parents=True, exist_ok=True)

    with fitz.open(str(sample_pdf)) as src:
        total = 0
        for page_idx, page_blocks in sorted(pages.items()):
            problems = segment_page(page_blocks)
            page = src[page_idx]
            for i, pb in enumerate(problems, start=1):
                x0n, y0n, x1n, y1n = to_xyxy(pb["bbox"])
                rect = fitz.Rect(
                    x0n * page.rect.width,
                    y0n * page.rect.height,
                    x1n * page.rect.width,
                    y1n * page.rect.height,
                )
                pix = page.get_pixmap(matrix=fitz.Matrix(2,2), clip=rect, alpha=False)
                fname = f"{Path(pdf_path).stem}_p{page_idx+1:03d}_prob{i:02d}.png"
                pix.save(str(out_dir / fname))
                total += 1
        print(f"Saved {total} problem crops to {out_dir}")


if __name__ == "__main__":
    main()
