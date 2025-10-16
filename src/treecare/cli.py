from __future__ import annotations
import argparse
from .pipeline import run_pipeline
from .config import settings
from .export import export_crops
from google.cloud import documentai_v1 as documentai
import os


def main():
    parser = argparse.ArgumentParser(description="TreeCare PDF segmentation pipeline")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("process", help="Process PDFs and persist to SQLite")
    p.add_argument("--input", default="pdfs/raw", help="Input directory of PDFs")
    p.add_argument("--db", default=settings.db_path, help="SQLite DB path")
    p.add_argument("--columns", choices=["s","d"], help="Force single (s) or double (d) column layout for this batch")
    p.add_argument("--exceptions", help="Comma-separated page numbers that use the opposite layout (1-based)")

    e = sub.add_parser("export", help="Export problem crops as WebP for QA")
    e.add_argument("--db", default=settings.db_path, help="SQLite DB path")
    e.add_argument("--out", default="data/crops", help="Output directory")
    e.add_argument("--zoom", type=float, default=2.0, help="Rasterization zoom")

    c = sub.add_parser("check", help="Validate GCP credentials and Document AI processor access")
    c.add_argument("--project", default=settings.project_id)
    c.add_argument("--location", default=settings.location)
    c.add_argument("--processor", default=settings.processor_id)

    args = parser.parse_args()
    if args.cmd == "process":
        # Interactive prompts if not provided
        cols = args.columns
        if not cols:
            cols = input("Column layout? Single (s) or Double (d): ").strip().lower()
            while cols not in ("s","d"):
                cols = input("Please enter 's' for Single or 'd' for Double: ").strip().lower()
        ex = args.exceptions
        if ex is None:
            yn = input("Are there any exceptions (pages using the opposite layout)? (y/n): ").strip().lower()
            if yn == 'y':
                while True:
                    raw = input("List pages as comma-separated numbers (e.g., 1,2,3): ").strip()
                    parts = [p.strip() for p in raw.split(',') if p.strip()]
                    if all(part.isdigit() for part in parts):
                        ex = ','.join(parts)
                        print(f"Exceptions set to pages: {ex}")
                        break
                    else:
                        print("Invalid input. Please enter only numbers separated by commas.")
            else:
                ex = ""
        run_pipeline(args.input, args.db, forced_columns=1 if cols=='s' else 2, exception_pages=ex)
    elif args.cmd == "export":
        export_crops(args.db, args.out, args.zoom)
    elif args.cmd == "check":
        sa = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if not sa or not os.path.exists(sa):
            print("GOOGLE_APPLICATION_CREDENTIALS not set or file not found. Set it to your Service Account JSON path.")
            return
        print(f"Using Service Account JSON: {sa}")
        client = documentai.DocumentProcessorServiceClient()
        name = client.processor_path(args.project, args.location, args.processor)
        try:
            proc = client.get_processor(name=name)
            print(f"Processor OK: {proc.display_name} (state={proc.state.name})")
        except Exception as e:
            msg = str(e)
            if "NotFound" in msg or "404" in msg:
                print("Processor not found. Check processor ID and location (should be 'us').")
            elif "PermissionDenied" in msg or "403" in msg:
                print("Permission denied. Ensure the Service Account has Document AI roles and processor access.")
            elif "Unauthenticated" in msg or "401" in msg:
                print("Unauthenticated. Set GOOGLE_APPLICATION_CREDENTIALS to your Service Account JSON and ensure it's valid.")
            else:
                print(f"Unexpected error: {msg}")


if __name__ == "__main__":
    main()
