# TreeCare PDF Problem Segmentation

Pipeline to convert mixed PDFs (vector/scanned) of UNI AAH/MAT/SCI exams into a structured problem bank using Google Cloud Document AI (OCR/Layout) with deterministic rules.

## Features
- Ingest PDFs from `pdfs/raw`
- Call Document AI (US region) with Service Account auth
- Segment problems by headers, body, options, and figures using regex + geometric rules
- Store results in SQLite (problems, choices, figures)
- FastAPI `/crop` endpoint to rasterize a page and crop by normalized boxes (WebP)

## Setup
1. Python 3.10+
2. Create and export `GOOGLE_APPLICATION_CREDENTIALS` to a Service Account JSON with access to Document AI.
3. Install deps:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

4. Set env variables (via `.env` or shell):
- `GCP_PROJECT_ID` (required)
- `GCP_LOCATION=us` (default us)
- `DOCAI_PROCESSOR_ID` (Document OCR/Layout processor ID)

## Run
- Batch process PDFs:
```bash
python -m src.treecare.cli process --input pdfs/raw --db data/treecare.sqlite
```
- Serve crop endpoint:
```bash
uvicorn src.treecare.api:app --host 0.0.0.0 --port 8080
```

## Data model
- problems(id, pdf_path, page_index, bbox_norm, header_text, sample_text, needs_review)
- choices(id, problem_id, label, text, bbox_norm)
- figures(id, problem_id, bbox_norm, caption_text)

## Notes
- Costs: ~ $0.01 per page; 360 pages ≈ $3.60 (estimate). See GCP pricing.
- We avoid pure OCR dependence by using Document AI's layout and geometries; works on vector and scanned PDFs.
