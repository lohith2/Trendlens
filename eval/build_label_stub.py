"""Scaffold (or top up) eval/test_set/labels.json with one blank entry per image.

Idempotent and non-destructive: existing entries are preserved exactly, so
re-running after adding studio images never overwrites hand-entered labels - it
only appends stubs for images that don't have an entry yet.

Source tier comes from sources.json (street, from Pexels). Any image not in
sources.json defaults to source="studio" (the Kaggle additions).

Labels are filled in BY HAND. Do not auto-label with the model - that would
bias the eval against the thing it measures.

Usage:
    PYTHONPATH=. .venv/bin/python eval/build_label_stub.py
"""

import json
from pathlib import Path

TEST_SET = Path(__file__).parent / "test_set"
IMAGES_DIR = TEST_SET / "images"
SOURCES_PATH = TEST_SET / "sources.json"
LABELS_PATH = TEST_SET / "labels.json"

# only the fields the eval measures; see eval/README.md for the matching rules
STUB = {
    "source": "studio",
    "garment_type": "",     # enum, see app/backend/schemas.py
    "season": "",           # enum
    "occasion": "",         # enum
    "style": [],            # list of acceptable answers (synonyms ok)
    "material": [],         # list of acceptable answers (synonyms ok)
    "color": [],            # list of color words
    "location_context": {"continent": None, "country": None, "city": None},
}


def main() -> None:
    sources = json.loads(SOURCES_PATH.read_text()) if SOURCES_PATH.exists() else {}
    labels = json.loads(LABELS_PATH.read_text()) if LABELS_PATH.exists() else {}

    added = 0
    for path in sorted(IMAGES_DIR.glob("*")):
        if path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
            continue
        name = path.name
        if name in labels:
            continue  # preserve hand-entered labels untouched
        entry = dict(STUB)
        entry["location_context"] = dict(STUB["location_context"])
        entry["color"] = []
        entry["style"] = []
        entry["material"] = []
        entry["source"] = sources.get(name, {}).get("source", "studio")
        labels[name] = entry
        added += 1

    LABELS_PATH.write_text(json.dumps(labels, indent=2, sort_keys=True) + "\n")
    filled = sum(1 for v in labels.values() if v["garment_type"])
    print(f"{LABELS_PATH}: {len(labels)} entries (+{added} new), {filled} labeled.")
    print("Fill the blank fields by hand, then run eval/run_eval.py.")


if __name__ == "__main__":
    main()
