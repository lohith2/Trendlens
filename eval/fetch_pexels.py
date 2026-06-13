"""Download eval test-set images from the Pexels API, by difficulty tier.

Reads PEXELS_API_KEY from the environment (.env). Idempotent: photos already
present (by Pexels photo id, across both tiers) are skipped, so re-running tops
up the set without duplicating. Records attribution in sources.json (required
by the Pexels API terms) and tags every image with its source tier.

Two tiers, two query sets:
- street: in-the-wild fashion (occlusion, layering, varied light) — the hard tier
- studio: clean, isolated, plain-background product/model shots — the easy tier

Usage:
    PYTHONPATH=. .venv/bin/python eval/fetch_pexels.py --source street --target 45
    PYTHONPATH=. .venv/bin/python eval/fetch_pexels.py --source studio --target 25
"""

import argparse
import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

IMAGES_DIR = Path(__file__).parent / "test_set" / "images"
SOURCES_PATH = Path(__file__).parent / "test_set" / "sources.json"
API = "https://api.pexels.com/v1/search"

# Per-tier query sets. Street is ordered so a spread of regions and garments
# comes first, then a deliberate hard-case tail (layering, occlusion, ambiguous
# material) that drives the failure analysis. Studio targets clean catalog-style
# shots on plain backgrounds — the easy tier that isolates model perception from
# scene noise.
SOURCE_QUERIES = {
    "street": [
        "street fashion",
        "japanese street style",
        "african print fashion",
        "indian traditional outfit",
        "winter coat outerwear",
        "summer dress outdoor",
        "menswear tailoring",
        "athleisure activewear",
        "layered outfit autumn",       # hard: layering
        "person walking back view",    # hard: occlusion / partial garment
    ],
    "studio": [
        "dress white background",
        "clothing product photography",
        "fashion studio plain background",
        "jacket isolated white background",
        "apparel flat lay",
        "shirt product shot white background",
        "model studio neutral background",
        "folded clothes white background",
    ],
}


def load_sources() -> dict:
    if SOURCES_PATH.exists():
        return json.loads(SOURCES_PATH.read_text())
    return {}


def fetch(target: int, per_query: int, source: str) -> None:
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        sys.exit("PEXELS_API_KEY not set. Add it to .env (see .env.example).")
    if source not in SOURCE_QUERIES:
        sys.exit(f"unknown source {source!r}; choose from {list(SOURCE_QUERIES)}.")

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    sources = load_sources()
    have_ids = {v["pexels_id"] for v in sources.values()}  # dedupe across tiers
    headers = {"Authorization": key}

    def tier_count() -> int:
        return sum(1 for v in sources.values() if v["source"] == source)

    with httpx.Client(timeout=30) as client:
        for query in SOURCE_QUERIES[source]:
            if tier_count() >= target:
                break
            resp = client.get(
                API,
                headers=headers,
                params={"query": query, "per_page": per_query, "orientation": "portrait"},
            )
            resp.raise_for_status()
            for photo in resp.json().get("photos", []):
                if tier_count() >= target:
                    break
                pid = photo["id"]
                if pid in have_ids:
                    continue
                filename = f"{source}_{pid}.jpg"
                img = client.get(photo["src"]["large"])
                img.raise_for_status()
                (IMAGES_DIR / filename).write_bytes(img.content)
                sources[filename] = {
                    "source": source,
                    "pexels_id": pid,
                    "query": query,
                    "photographer": photo.get("photographer"),
                    "url": photo.get("url"),
                }
                have_ids.add(pid)
                print(f"  + {filename}  ({query})")

    SOURCES_PATH.write_text(json.dumps(sources, indent=2) + "\n")
    print(f"\n{tier_count()} {source} images in {IMAGES_DIR} (target {target}).")
    print(f"Attribution written to {SOURCES_PATH}.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=list(SOURCE_QUERIES), default="street")
    ap.add_argument("--target", type=int, default=45, help="images for this tier")
    ap.add_argument("--per-query", type=int, default=8)
    fetch(**vars(ap.parse_args()))
