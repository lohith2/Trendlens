"""SQLite persistence with an FTS5 full-text index.

AI output lives only in `images`; designer input lives only in `annotations`.
The separate tables ARE the AI-vs-designer distinction the product requires,
rather than a source flag on shared rows.
"""

import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.backend.schemas import GarmentAttributes

DEFAULT_DB_PATH = Path(os.environ.get("TRENDLENS_DB", "trendlens.db"))

# Columns the listing endpoint can filter on by equality. Fixed allowlist,
# never user-supplied, so interpolating a name into SQL is safe here.
FILTER_FIELDS = (
    "garment_type",
    "season",
    "occasion",
    "style",
    "material",
    "pattern",
    "designer",
    "continent",
    "country",
    "city",
    "year",
    "month",
)

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
    style TEXT,
    material TEXT,
    pattern TEXT,
    color_palette TEXT,
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
            style = ?,
            material = ?,
            pattern = ?,
            color_palette = ?,
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
            attrs.style,
            attrs.material,
            attrs.pattern,
            ",".join(c.strip().lower() for c in attrs.color_palette),
            loc.continent,
            loc.country,
            loc.city,
            image_id,
        ),
    )
    # refresh this image's model-text rows in the search index. The rich
    # free-text fields (description, consumer_profile, trend_notes) are all
    # searchable; discrete attributes are reached via filters instead. Annotation
    # rows (tag/note) are keyed by their own kinds and left untouched.
    conn.execute(
        "DELETE FROM images_fts WHERE image_id = ? AND kind IN "
        "('description', 'consumer_profile', 'trend_notes')",
        (image_id,),
    )
    for kind, content in (
        ("description", attrs.description),
        ("consumer_profile", attrs.consumer_profile),
        ("trend_notes", attrs.trend_notes),
    ):
        if content and content.strip():
            conn.execute(
                "INSERT INTO images_fts (content, image_id, kind) VALUES (?, ?, ?)",
                (content, image_id, kind),
            )
    conn.commit()


def mark_image_failed(conn: sqlite3.Connection, image_id: int) -> None:
    conn.execute("UPDATE images SET status = 'failed' WHERE id = ?", (image_id,))
    conn.commit()


def _row_to_image(row: sqlite3.Row) -> dict:
    record = dict(row)
    if record.get("attributes"):
        record["attributes"] = json.loads(record["attributes"])
    return record


def get_image(conn: sqlite3.Connection, image_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM images WHERE id = ?", (image_id,)).fetchone()
    return _row_to_image(row) if row is not None else None


def _build_fts_match(q: str) -> str:
    """Turn free user text into a safe FTS5 MATCH expression.

    Tokens are reduced to word characters and given a prefix wildcard, so
    "embroider" finds "embroidered" and stray punctuation can't produce a
    MATCH syntax error. Multiple tokens are implicitly ANDed by FTS5.
    """
    tokens = re.findall(r"\w+", q.lower())
    return " ".join(f"{token}*" for token in tokens)


def query_images(
    conn: sqlite3.Connection,
    filters: dict | None = None,
    q: str | None = None,
) -> list[dict]:
    filters = filters or {}
    where: list[str] = []
    params: list = []

    for field in FILTER_FIELDS:
        value = filters.get(field)
        if value is not None and value != "":
            where.append(f"{field} = ?")
            params.append(value)

    color = filters.get("color")
    if color:
        # color_palette is a comma-joined lowercase string; pad with commas so
        # the match is on a whole token, not a substring ("red" != "redwood")
        where.append("(',' || color_palette || ',') LIKE ?")
        params.append(f"%,{color.lower()},%")

    if q:
        match = _build_fts_match(q)
        if match:
            where.append(
                "id IN (SELECT image_id FROM images_fts WHERE images_fts MATCH ?)"
            )
            params.append(match)

    sql = "SELECT * FROM images"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY uploaded_at DESC, id DESC"
    return [_row_to_image(row) for row in conn.execute(sql, params)]


def get_filter_facets(conn: sqlite3.Connection) -> dict[str, list]:
    """Distinct values per filterable field, generated from the data itself.

    New attribute values become filter options automatically; nothing here
    is hardcoded.
    """
    facets: dict[str, list] = {}
    for field in FILTER_FIELDS:
        rows = conn.execute(
            f"SELECT DISTINCT {field} FROM images "
            f"WHERE {field} IS NOT NULL AND {field} != '' ORDER BY {field}"
        ).fetchall()
        facets[field] = [row[0] for row in rows]

    colors: set[str] = set()
    for (palette,) in conn.execute(
        "SELECT color_palette FROM images "
        "WHERE color_palette IS NOT NULL AND color_palette != ''"
    ):
        colors.update(c for c in palette.split(",") if c)
    facets["color"] = sorted(colors)
    return facets


def add_annotation(
    conn: sqlite3.Connection, image_id: int, kind: str, content: str
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT INTO annotations (image_id, kind, content, created_at)"
        " VALUES (?, ?, ?, ?)",
        (image_id, kind, content, now),
    )
    conn.execute(
        "INSERT INTO images_fts (content, image_id, kind) VALUES (?, ?, ?)",
        (content, image_id, kind),
    )
    conn.commit()
    return {
        "id": cur.lastrowid,
        "image_id": image_id,
        "kind": kind,
        "content": content,
        "created_at": now,
    }


def get_annotations(conn: sqlite3.Connection, image_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM annotations WHERE image_id = ? ORDER BY created_at, id",
        (image_id,),
    ).fetchall()
    return [dict(row) for row in rows]
