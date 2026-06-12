"""SQLite persistence with an FTS5 full-text index.

AI output lives only in `images`; designer input lives only in `annotations`.
The separate tables ARE the AI-vs-designer distinction the product requires,
rather than a source flag on shared rows.
"""

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.backend.schemas import GarmentAttributes

DEFAULT_DB_PATH = Path(os.environ.get("TRENDLENS_DB", "trendlens.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS images (
    id INTEGER PRIMARY KEY,
    filename TEXT NOT NULL,
    uploaded_at TEXT NOT NULL,
    designer TEXT,
    status TEXT NOT NULL DEFAULT 'processing',
    description TEXT,
    attributes TEXT,
    garment_type TEXT,
    season TEXT,
    occasion TEXT,
    continent TEXT,
    country TEXT,
    city TEXT,
    year INTEGER,
    month INTEGER
);

CREATE TABLE IF NOT EXISTS annotations (
    id INTEGER PRIMARY KEY,
    image_id INTEGER NOT NULL REFERENCES images(id),
    kind TEXT NOT NULL CHECK (kind IN ('tag', 'note')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS images_fts USING fts5(
    content,
    image_id UNINDEXED,
    kind UNINDEXED
);
"""


def get_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    # check_same_thread=False: FastAPI resolves the sync connection dependency
    # in a threadpool thread while async endpoints use the event loop thread
    conn = sqlite3.connect(db_path or DEFAULT_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    return conn


def insert_image(
    conn: sqlite3.Connection, filename: str, designer: str | None = None
) -> int:
    now = datetime.now(timezone.utc)
    cur = conn.execute(
        "INSERT INTO images (filename, uploaded_at, designer, status, year, month)"
        " VALUES (?, ?, ?, 'processing', ?, ?)",
        (filename, now.isoformat(), designer, now.year, now.month),
    )
    conn.commit()
    return cur.lastrowid


def update_image_classification(
    conn: sqlite3.Connection, image_id: int, attrs: GarmentAttributes
) -> None:
    loc = attrs.location_context
    conn.execute(
        """
        UPDATE images SET
            status = 'classified',
            description = ?,
            attributes = ?,
            garment_type = ?,
            season = ?,
            occasion = ?,
            continent = ?,
            country = ?,
            city = ?
        WHERE id = ?
        """,
        (
            attrs.description,
            attrs.model_dump_json(),
            attrs.garment_type.value,
            attrs.season.value,
            attrs.occasion.value,
            loc.continent,
            loc.country,
            loc.city,
            image_id,
        ),
    )
    # refresh this image's description row in the search index
    conn.execute(
        "DELETE FROM images_fts WHERE image_id = ? AND kind = 'description'",
        (image_id,),
    )
    conn.execute(
        "INSERT INTO images_fts (content, image_id, kind)"
        " VALUES (?, ?, 'description')",
        (attrs.description, image_id),
    )
    conn.commit()


def mark_image_failed(conn: sqlite3.Connection, image_id: int) -> None:
    conn.execute("UPDATE images SET status = 'failed' WHERE id = ?", (image_id,))
    conn.commit()


def get_image(conn: sqlite3.Connection, image_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM images WHERE id = ?", (image_id,)).fetchone()
    if row is None:
        return None
    record = dict(row)
    if record["attributes"]:
        record["attributes"] = json.loads(record["attributes"])
    return record
