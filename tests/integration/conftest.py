"""Integration fixtures: a TestClient backed by a throwaway SQLite file plus a
seed helper that writes classified images straight through the db layer.

No model is involved here - these tests exercise the read/query/annotation
surface over known data, so seeding bypasses the classifier entirely.
"""

import pytest
from fastapi.testclient import TestClient

from app.backend import db
from app.backend.main import app, get_db
from app.backend.schemas import (
    GarmentAttributes,
    GarmentType,
    LocationContext,
    Occasion,
    Season,
)


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test.db"


@pytest.fixture
def client(db_path):
    def override_get_db():
        conn = db.get_connection(db_path)
        try:
            yield conn
        finally:
            conn.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def make_attrs(**overrides) -> GarmentAttributes:
    base = dict(
        description="a plain garment for seeding",
        garment_type=GarmentType.JACKET,
        style="streetwear",
        material="denim",
        color_palette=["indigo", "white"],
        pattern="solid",
        season=Season.FALL,
        occasion=Occasion.CASUAL,
        consumer_profile="seed profile",
        trend_notes="seed notes",
        location_context=LocationContext(),
    )
    base.update(overrides)
    return GarmentAttributes(**base)


@pytest.fixture
def seed(db_path):
    """Insert one classified image; returns its id. `year`/`month` override the
    upload timestamp columns so time-based filtering can be tested."""
    counter = {"n": 0}

    def _seed(designer=None, year=None, month=None, **attr_overrides):
        conn = db.get_connection(db_path)
        counter["n"] += 1
        image_id = db.insert_image(conn, f"img{counter['n']}.jpg", designer)
        db.update_image_classification(conn, image_id, make_attrs(**attr_overrides))
        if year is not None or month is not None:
            conn.execute(
                "UPDATE images SET year = COALESCE(?, year), "
                "month = COALESCE(?, month) WHERE id = ?",
                (year, month, image_id),
            )
            conn.commit()
        conn.close()
        return image_id

    return _seed
