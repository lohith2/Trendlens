"""Trendlens API. Run from the repo root: uvicorn app.backend.main:app"""
from dotenv import load_dotenv

load_dotenv()
import os
import sqlite3
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile

from app.backend import db
from app.backend.classifier import ClassificationError, classify_image

UPLOADS_DIR = Path(os.environ.get("TRENDLENS_UPLOADS", "uploads"))
ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}

app = FastAPI(title="Trendlens")


def get_db():
    conn = db.get_connection()
    try:
        yield conn
    finally:
        conn.close()


def process_classification(
    conn: sqlite3.Connection, image_id: int, image_path: Path, client=None
) -> dict:
    """Classify and persist. A failed model call never loses the upload:
    the row survives with status=failed and can be retried."""
    try:
        attrs = classify_image(image_path, client=client)
    except ClassificationError:
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
