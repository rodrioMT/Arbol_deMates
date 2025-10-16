import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Optional, Tuple

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS pdfs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    pages INTEGER,
    processed_at TEXT,
    processor_id TEXT
);
CREATE TABLE IF NOT EXISTS problems (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pdf_path TEXT NOT NULL,
    page_index INTEGER NOT NULL,
    bbox_norm TEXT NOT NULL,
    header_text TEXT,
    sample_text TEXT,
    needs_review INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS choices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    problem_id INTEGER NOT NULL REFERENCES problems(id) ON DELETE CASCADE,
    label TEXT NOT NULL,
    text TEXT,
    bbox_norm TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS figures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    problem_id INTEGER NOT NULL REFERENCES problems(id) ON DELETE CASCADE,
    bbox_norm TEXT NOT NULL,
    caption_text TEXT
);
"""

@contextmanager
def get_conn(db_path: str):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db(db_path: str):
    with get_conn(db_path) as conn:
        conn.executescript(SCHEMA)

# Helper serialization for normalized boxes: (x0,y0,x1,y1)

def serialize_bbox(b: Tuple[float, float, float, float]) -> str:
    return ",".join(f"{v:.6f}" for v in b)

def deserialize_bbox(s: str) -> Tuple[float, float, float, float]:
    x0, y0, x1, y1 = map(float, s.split(","))
    return x0, y0, x1, y1
