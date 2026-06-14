"""Launch the Trendlens API for end-to-end tests: fresh seeded DB, stubbed
classifier, real HTTP server.

Playwright's webServer starts this. It points TRENDLENS_DB / TRENDLENS_UPLOADS
at a throwaway directory (recreated on every start, so each run is
deterministic), seeds a known set of classified images straight through the db
layer, and monkeypatches the vision classifier so the upload flow exercises the
full upload -> classify -> persist -> grid path without calling OpenAI.

The classifier is patched here, in the test launcher, rather than behind a flag
in production code: process_classification() looks the name up on the module at
call time, so reassigning app.backend.main.classify_image is enough.

Run indirectly via `npm test` in this directory; or directly:
    .venv/bin/python tests/e2e/serve.py
"""
import os
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

TMP = Path(__file__).resolve().parent / ".tmp"
shutil.rmtree(TMP, ignore_errors=True)
(TMP / "uploads").mkdir(parents=True)

os.environ["TRENDLENS_DB"] = str(TMP / "e2e.db")
os.environ["TRENDLENS_UPLOADS"] = str(TMP / "uploads")
os.environ.pop("OPENAI_API_KEY", None)  # never reach for a real key

from app.backend import db, main  # noqa: E402  (import after env is set)
from app.backend.schemas import (  # noqa: E402
    GarmentAttributes,
    GarmentType,
    LocationContext,
    Occasion,
    Season,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sample.jpg"

# (filename, designer, attribute overrides). Chosen so each read test has an
# unambiguous target: one dress, one denim "jacket" description, two by "Lia".
SEED = [
    ("denim_jacket.jpg", "Lia", dict(
        description="a boxy cropped denim jacket with a raw hem",
        garment_type=GarmentType.JACKET, style="streetwear", material="denim",
        color_palette=["indigo", "white"], season=Season.FALL,
        occasion=Occasion.CASUAL)),
    ("summer_dress.jpg", "Mara", dict(
        description="a flowing red cotton summer maxi dress",
        garment_type=GarmentType.DRESS, style="bohemian", material="cotton",
        color_palette=["red"], season=Season.SUMMER, occasion=Occasion.CASUAL)),
    ("wool_coat.jpg", "Lia", dict(
        description="a tailored grey wool overcoat",
        garment_type=GarmentType.COAT, style="minimalist", material="wool",
        color_palette=["grey"], season=Season.WINTER,
        occasion=Occasion.BUSINESS)),
]


def _attrs(**overrides) -> GarmentAttributes:
    base = dict(
        description="garment", garment_type=GarmentType.OTHER, style="casual",
        material="cotton", color_palette=["black"], pattern="solid",
        season=Season.ALL_SEASON, occasion=Occasion.CASUAL,
        consumer_profile="profile", trend_notes="notes",
        location_context=LocationContext(),
    )
    base.update(overrides)
    return GarmentAttributes(**base)


def seed() -> None:
    uploads = Path(os.environ["TRENDLENS_UPLOADS"])
    conn = db.get_connection()
    for filename, designer, overrides in SEED:
        shutil.copyfile(FIXTURE, uploads / filename)
        image_id = db.insert_image(conn, filename, designer)
        db.update_image_classification(conn, image_id, _attrs(**overrides))
    conn.close()


def fake_classify(image_path, client=None, model=None) -> GarmentAttributes:
    """Deterministic stand-in for the OpenAI vision call. Returns a 'top' so an
    uploaded card is visibly distinct from the seeded jacket/dress/coat."""
    return _attrs(
        description="an uploaded ribbed cotton top",
        garment_type=GarmentType.TOP, style="minimalist", material="cotton",
        color_palette=["beige"], season=Season.SUMMER, occasion=Occasion.CASUAL,
    )


seed()
main.classify_image = fake_classify

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(main.app, host="127.0.0.1", port=8000, log_level="warning")
