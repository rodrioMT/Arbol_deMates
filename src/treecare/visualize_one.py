from __future__ import annotations
import argparse
from pathlib import Path
import tempfile
import fitz  # PyMuPDF

from .config import settings
from .docai import process_pdf
from .pipeline import extract_blocks
from .segment import segment_page


def find_pdf(input_path: str) -> Path:
    p = Path(input_path)
    if p.exists():
        return p
    # Search in pdfs/raw by name
    root = Path("pdfs/raw")
    for cand in root.glob("**/*.pdf"):
        if cand.name == input_path or cand.stem == Path(input_path).stem:
            return cand
    raise FileNotFoundError(f"PDF not found: {input_path}")


def make_single_page(pdf_path: Path, page_index_1b: int) -> Path:
    with fitz.open(str(pdf_path)) as src:
        idx0 = page_index_1b - 1
        if idx0 < 0 or idx0 >= len(src):
            raise ValueError(f"Page out of range: {page_index_1b}")
        doc = fitz.open()
        doc.insert_pdf(src, from_page=idx0, to_page=idx0)
        tmp_dir = Path(tempfile.mkdtemp(prefix="treecare_one_"))
        out = tmp_dir / f"{pdf_path.stem}_p{page_index_1b:03d}.pdf"
        doc.save(str(out))
        doc.close()
        return out


def main():
    ap = argparse.ArgumentParser(description="Visualize crops for one PDF page with forced columns")
    ap.add_argument("--pdf", required=True, help="PDF path or name under pdfs/raw")
    ap.add_argument("--page", type=int, required=True, help="1-based page number")
    ap.add_argument("--columns", choices=["s","d"], required=True, help="Force single (s) or double (d) column")
    ap.add_argument("--out", default="data/crops_quick", help="Output directory for PNG crops")
    args = ap.parse_args()

    pdf_path = find_pdf(args.pdf)
    one_pdf = make_single_page(pdf_path, args.page)

    # Process via Document AI
    doc = process_pdf(settings.project_id, settings.location, settings.processor_id, str(one_pdf))

    # Extract blocks and segment
    blocks = extract_blocks(doc)
    pages = {}
    for b in blocks:
        pages.setdefault(b["page_index"], []).append(b)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    fc = 1 if args.columns == 's' else 2

    # Open original page image (for correct geometry)
    with fitz.open(str(one_pdf)) as src:
        for page_idx, page_blocks in pages.items():
            problems = segment_page(page_blocks, page_index=page_idx, forced_columns=fc)
            page = src[page_idx]
            for i, pb in enumerate(problems, start=1):
                x0n, y0n, x1n, y1n = pb["bbox"]
                rect = fitz.Rect(
                    x0n * page.rect.width,
                    y0n * page.rect.height,
                    x1n * page.rect.width,
                    y1n * page.rect.height,
                )
                pix = page.get_pixmap(matrix=fitz.Matrix(2,2), clip=rect, alpha=False)
                fname = f"{pdf_path.stem}_p{args.page:03d}_prob{i:02d}.png"
                pix.save(str(out_dir / fname))
            print(f"Saved {len(problems)} crops to {out_dir}")


if __name__ == "__main__":
    main()
