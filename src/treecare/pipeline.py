from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Any, List
from tqdm import tqdm
from .config import settings
from .db import init_db, get_conn, serialize_bbox
from .docai import process_pdf, normalized_bbox_from_layout, to_xyxy, layout_to_text
from .segment import segment_page
import fitz  # PyMuPDF
import tempfile
import os


def extract_blocks(doc) -> List[Dict[str, Any]]:
    blocks: List[Dict[str, Any]] = []
    for p_idx, page in enumerate(doc.pages):
        # Use detected blocks: paragraphs, tables, figures
        # Gather: paragraphs
        for para in page.paragraphs:
            text = layout_to_text(doc, para.layout)
            blocks.append({
                "page_index": p_idx,
                "text": text or "",
                "bbox": normalized_bbox_from_layout(para.layout),
                "type": "paragraph"
            })
        # Lines (useful to catch A) .. E) when paragraphs are fragmented)
        for line in getattr(page, 'lines', []):
            text = layout_to_text(doc, line.layout)
            blocks.append({
                "page_index": p_idx,
                "text": text or "",
                "bbox": normalized_bbox_from_layout(line.layout),
                "type": "line"
            })
        # Tables
        for table in getattr(page, 'tables', []):
            blocks.append({
                "page_index": p_idx,
                "text": "",  # structure not needed here
                "bbox": normalized_bbox_from_layout(table.layout),
                "type": "table"
            })
        # Figures (detected images)
        for figure in getattr(page, 'figures', []):
            blocks.append({
                "page_index": p_idx,
                "text": "",
                "bbox": normalized_bbox_from_layout(figure.layout),
                "type": "figure"
            })
    return blocks


def run_pipeline(input_dir: str, db_path: str, forced_columns: int | None = None, exception_pages: str | None = None):
    init_db(db_path)
    pdf_paths = sorted(Path(input_dir).glob('**/*.pdf'))
    if not pdf_paths:
        print(f"No PDFs found in {input_dir}")
        return
    for pdf_path in tqdm(pdf_paths, desc="Processing PDFs"):
        # Determine total pages
        with fitz.open(str(pdf_path)) as src_doc:
            total_pages = len(src_doc)
        # Upsert into pdfs table (once per original)
        with get_conn(db_path) as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT OR IGNORE INTO pdfs(path, pages, processed_at, processor_id) VALUES (?,?,datetime('now'),?)",
                (str(pdf_path), total_pages, settings.processor_id)
            )

        # Prepare chunks (<=30 pages) due to Document AI sync page limit
        max_pages = 30
        chunks: List[tuple[str, int, int]] = []  # (chunk_path, start_idx, count)
        with fitz.open(str(pdf_path)) as src:
            start = 0
            while start < total_pages:
                end = min(start + max_pages, total_pages)
                chunk_doc = fitz.open()
                chunk_doc.insert_pdf(src, from_page=start, to_page=end - 1)
                tmp_dir = Path(tempfile.mkdtemp(prefix="treecare_chunks_"))
                chunk_path = tmp_dir / f"{Path(pdf_path).stem}_p{start:03d}-{end-1:03d}.pdf"
                chunk_doc.save(str(chunk_path))
                chunk_doc.close()
                chunks.append((str(chunk_path), start, end - start))

        # Process each chunk and map page indices back to original
        try:
            for chunk_path, offset, count in chunks:
                doc = process_pdf(settings.project_id, settings.location, settings.processor_id, chunk_path)
                pages: Dict[int, List[Dict[str, Any]]] = {}
                blocks = extract_blocks(doc)
                for b in blocks:
                    # Remap page index with offset
                    b_idx = b["page_index"] + offset
                    b["page_index"] = b_idx
                    pages.setdefault(b_idx, []).append(b)
                # Segment per page
                with get_conn(db_path) as conn:
                    # Parse exceptions into a set of 1-based pages for this PDF
                    ex_pages = set()
                    if exception_pages:
                        for part in exception_pages.split(','):
                            p = part.strip()
                            if p.isdigit():
                                ex_pages.add(int(p))
                    for page_idx, page_blocks in pages.items():
                        # Decide columns for this page
                        page_num_1b = page_idx + 1
                        fc = forced_columns
                        if forced_columns in (1,2) and page_num_1b in ex_pages:
                            fc = 2 if forced_columns == 1 else 1
                        problems = segment_page(page_blocks, page_index=page_idx, forced_columns=fc)
                        for pb in problems:
                            bbox_xyxy = pb["bbox"]
                            bbox_norm = serialize_bbox(bbox_xyxy)
                            header_text = (pb["header"].get("text") or "").strip()
                            body_text_first = (pb["body"][0].get("text") or "").strip() if pb.get("body") else ""
                            choice_text_first = (pb["choices"][0].get("text") or "").strip() if pb.get("choices") else ""
                            sample_text = (body_text_first + " " + choice_text_first).strip()
                            needs_review = 1 if pb.get("needs_review") else 0
                            cur = conn.cursor()
                            cur.execute(
                                "INSERT INTO problems(pdf_path, page_index, bbox_norm, header_text, sample_text, needs_review) VALUES (?,?,?,?,?,?)",
                                (str(pdf_path), page_idx, bbox_norm, header_text, sample_text, needs_review)
                            )
                            problem_id = cur.lastrowid
                            # choices
                            for ch in pb["choices"]:
                                txt = (ch.get("text") or "").strip()
                                label = txt[:1] if txt else ""
                                ch_bbox = from_bbox(ch["bbox"])  # xyxy
                                cur.execute(
                                    "INSERT INTO choices(problem_id, label, text, bbox_norm) VALUES (?,?,?,?)",
                                    (problem_id, label, txt, serialize_bbox(ch_bbox))
                                )
                            # figures
                            for fg in pb["figures"]:
                                fg_bbox = from_bbox(fg["bbox"])  # xyxy
                                cur.execute(
                                    "INSERT INTO figures(problem_id, bbox_norm, caption_text) VALUES (?,?,?)",
                                    (problem_id, serialize_bbox(fg_bbox), (fg.get("text") or "").strip())
                                )
        finally:
            # Cleanup chunk files and directories
            for chunk_path, _, _ in chunks:
                try:
                    os.remove(chunk_path)
                    # Remove temp dir if empty
                    tmp_dir = Path(chunk_path).parent
                    tmp_dir.rmdir()
                except Exception:
                    pass

# helpers to convert list of points to xyxy tuple

def from_bbox(b):
    xs = [v["x"] for v in b]
    ys = [v["y"] for v in b]
    return (min(xs), min(ys), max(xs), max(ys))
