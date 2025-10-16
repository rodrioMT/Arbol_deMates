from __future__ import annotations
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from google.cloud import documentai_v1 as documentai

@dataclass
class PageBlock:
    page_index: int
    text: str
    bbox: List[Dict[str, float]]  # normalized vertices x,y in [0,1]
    type: str | None = None


def process_pdf(project_id: str, location: str, processor_id: str, file_path: str) -> documentai.Document:
    client = documentai.DocumentProcessorServiceClient()
    name = client.processor_path(project_id, location, processor_id)
    with open(file_path, "rb") as f:
        raw_document = documentai.RawDocument(content=f.read(), mime_type="application/pdf")
    request = documentai.ProcessRequest(name=name, raw_document=raw_document)
    result = client.process_document(request=request)
    return result.document


def normalized_bbox_from_layout(layout: documentai.Document.Page.Layout) -> List[Dict[str, float]]:
    # Document AI provides normalizedBoundingPoly for layout bounds
    poly = layout.bounding_poly
    if poly is None or poly.normalized_vertices is None or len(poly.normalized_vertices) == 0:
        # Fallback to non-normalized
        vertices = poly.vertices if poly else []
        # Convert by assuming page size 1x1
        return [{"x": v.x or 0.0, "y": v.y or 0.0} for v in vertices]
    return [{"x": v.x or 0.0, "y": v.y or 0.0} for v in poly.normalized_vertices]


def to_xyxy(bbox: List[Dict[str, float]]):
    xs = [v["x"] for v in bbox]
    ys = [v["y"] for v in bbox]
    return min(xs), min(ys), max(xs), max(ys)


def text_from_anchor(doc: documentai.Document, text_anchor: Optional[documentai.Document.TextAnchor]) -> str:
    if not text_anchor or not text_anchor.text_segments:
        return ""
    # Concatenate segments from the global doc.text
    chunks: List[str] = []
    for seg in text_anchor.text_segments:
        start = int(seg.start_index) if seg.start_index is not None else 0
        end = int(seg.end_index) if seg.end_index is not None else start
        chunks.append(doc.text[start:end])
    return "".join(chunks)


def layout_to_text(doc: documentai.Document, layout: documentai.Document.Page.Layout) -> str:
    return text_from_anchor(doc, layout.text_anchor)
