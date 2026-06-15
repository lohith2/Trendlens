"""Trendlens API. Run from the repo root: uvicorn app.backend.main:app"""
from dotenv import load_dotenv

load_dotenv()
import logging
import os
import sqlite3
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.backend import db
from app.backend.classifier import classify_image
from app.backend.schemas import AnnotationIn

logger = logging.getLogger(__name__)

UPLOADS_DIR = Path(os.environ.get("TRENDLENS_UPLOADS", "uploads"))
ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}

app = FastAPI(title="Trendlens")

# the Vite dev server runs on a different origin during local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# uploaded images are served back to the grid as static files
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")


def get_db():
    conn = db.get_connection()
    try:
        yield conn
    finally:
        conn.close()


def process_classification(
    conn: sqlite3.Connection, image_id: int, image_path: Path, client=None
) -> dict:
    """Classify and persist. Any classification failure degrades to
    status=failed (retryable) rather than failing the upload. ClassificationError
    is the expected path; the broad catch also covers the unexpected — a
    misconfigured client, a broken dependency — so an accepted upload is never
    turned into a 500."""
    try:
        attrs = classify_image(image_path, client=client)
    except Exception:  # noqa: BLE001 - deliberate: a stored upload must never 500
        logger.exception("classification failed for image %s", image_id)
        db.mark_image_failed(conn, image_id)
    else:
        db.update_image_classification(conn, image_id, attrs)
    return db.get_image(conn, image_id)


@app.post("/api/images", status_code=201)
async def upload_image(
    file: UploadFile = File(...),
    designer: str | None = Form(None),
    conn: sqlite3.Connection = Depends(get_db),
):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=415,
            detail=f"unsupported file type; expected one of {sorted(ALLOWED_SUFFIXES)}",
        )
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{suffix}"
    dest = UPLOADS_DIR / stored_name
    dest.write_bytes(await file.read())

    image_id = db.insert_image(conn, stored_name, designer)
    return process_classification(conn, image_id, dest)


@app.post("/api/images/{image_id}/retry")
def retry_classification(
    image_id: int, conn: sqlite3.Connection = Depends(get_db)
):
    image = db.get_image(conn, image_id)
    if image is None:
        raise HTTPException(status_code=404, detail="image not found")
    if image["status"] == "classified":
        return image
    image_path = UPLOADS_DIR / image["filename"]
    if not image_path.exists():
        raise HTTPException(status_code=409, detail="stored image file is missing")
    return process_classification(conn, image_id, image_path)


@app.get("/api/images")
def list_images(
    q: str | None = None,
    garment_type: str | None = None,
    season: str | None = None,
    occasion: str | None = None,
    style: str | None = None,
    material: str | None = None,
    pattern: str | None = None,
    color: str | None = None,
    designer: str | None = None,
    continent: str | None = None,
    country: str | None = None,
    city: str | None = None,
    year: int | None = None,
    month: int | None = None,
    conn: sqlite3.Connection = Depends(get_db),
):
    filters = {
        "garment_type": garment_type,
        "season": season,
        "occasion": occasion,
        "style": style,
        "material": material,
        "pattern": pattern,
        "color": color,
        "designer": designer,
        "continent": continent,
        "country": country,
        "city": city,
        "year": year,
        "month": month,
    }
    return db.query_images(conn, filters, q)


@app.get("/api/filters")
def list_filters(conn: sqlite3.Connection = Depends(get_db)):
    return db.get_filter_facets(conn)


@app.get("/api/images/{image_id}")
def get_image_detail(image_id: int, conn: sqlite3.Connection = Depends(get_db)):
    image = db.get_image(conn, image_id)
    if image is None:
        raise HTTPException(status_code=404, detail="image not found")
    image["annotations"] = db.get_annotations(conn, image_id)
    return image


@app.get("/api/images/{image_id}/annotations")
def list_annotations(image_id: int, conn: sqlite3.Connection = Depends(get_db)):
    return db.get_annotations(conn, image_id)


@app.post("/api/images/{image_id}/annotations", status_code=201)
def create_annotation(
    image_id: int,
    payload: AnnotationIn,
    conn: sqlite3.Connection = Depends(get_db),
):
    if db.get_image(conn, image_id) is None:
        raise HTTPException(status_code=404, detail="image not found")
    return db.add_annotation(conn, image_id, payload.kind, payload.content)
