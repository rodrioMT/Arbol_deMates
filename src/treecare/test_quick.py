from __future__ import annotations
from pathlib import Path
import sys
import json
import tempfile
import fitz  # PyMuPDF
from google.protobuf.json_format import MessageToDict

from .config import settings
from .docai import process_pdf


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
        doc = fitz.open()
        if n == 0:
            raise ValueError("PDF has 0 pages")
        doc.insert_pdf(src, from_page=0, to_page=n - 1)
        tmp_dir = Path(tempfile.mkdtemp(prefix="treecare_test_"))
        out = tmp_dir / f"{pdf_path.stem}_first3.pdf"
        doc.save(str(out))
        doc.close()
        return out


def count_norm_boxes(doc) -> tuple[int, int]:
    count = 0
    pages = getattr(doc, 'pages', [])
    for page in pages:
        for para in getattr(page, 'paragraphs', []):
            poly = para.layout.bounding_poly
            if poly and getattr(poly, 'normalized_vertices', None) and len(poly.normalized_vertices) > 0:
                count += 1
        for table in getattr(page, 'tables', []):
            poly = table.layout.bounding_poly
            if poly and getattr(poly, 'normalized_vertices', None) and len(poly.normalized_vertices) > 0:
                count += 1
        for figure in getattr(page, 'figures', []):
            poly = figure.layout.bounding_poly
            if poly and getattr(poly, 'normalized_vertices', None) and len(poly.normalized_vertices) > 0:
                count += 1
    return count, len(pages)


def main():
    try:
        pdf_path = find_first_pdf("pdfs/raw")
        test_pdf = make_3page_temp(pdf_path)
        doc = process_pdf(settings.project_id, settings.location, settings.processor_id, str(test_pdf))
        # Write JSON output
        data = MessageToDict(doc._pb, preserving_proto_field_name=True)
        Path("test_output.json").write_text(json.dumps(data, ensure_ascii=False))
        # Check normalized boxes
        boxes, pages = count_norm_boxes(doc)
        if boxes > 0:
            print(f"✅ Works: found {boxes} boxes across {pages} pages.")
        else:
            print("⚠️ No bounding boxes (normalizedVertices) found.")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
