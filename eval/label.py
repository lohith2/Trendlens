"""Interactive hand-labeling tool for the eval test set.

You make every judgment; this just structures the input so the result always
matches the schema run_eval.py expects. Enums are picked from a numbered list
(no typos like 'athletic' for 'activewear'), free-text/color fields are
comma-separated lists, and labels.json is saved after every image so you can
quit and resume anytime.

This is NOT model labeling — it never looks at or guesses any value. It opens
the image so you can label it yourself.

Usage:
    PYTHONPATH=. .venv/bin/python eval/label.py                 # unlabeled only
    PYTHONPATH=. .venv/bin/python eval/label.py --tier studio   # one tier
    PYTHONPATH=. .venv/bin/python eval/label.py --file street_14558130.jpg   # fix one
    PYTHONPATH=. .venv/bin/python eval/label.py --all           # review/relabel all
    PYTHONPATH=. .venv/bin/python eval/label.py --no-open       # don't auto-open images
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from app.backend.schemas import GarmentType, Occasion, Season

TEST_SET = Path(__file__).parent / "test_set"
IMAGES_DIR = TEST_SET / "images"
LABELS_PATH = TEST_SET / "labels.json"

ENUMS = {
    "garment_type": [m.value for m in GarmentType],
    "season": [m.value for m in Season],
    "occasion": [m.value for m in Occasion],
}


def open_image(path: Path) -> None:
    try:
        subprocess.run(["open", str(path)], check=False)
    except FileNotFoundError:
        pass  # not on macOS; user opens it manually


def prompt_enum(field: str, options: list[str], current: str) -> str | None:
    """Numbered menu. Enter = keep current. 's' = skip image. 'q' = save & quit."""
    cur = f" [current: {current}]" if current else ""
    print(f"\n{field}{cur}")
    for i, opt in enumerate(options, 1):
        print(f"  {i:>2}. {opt}")
    while True:
        raw = input(f"  pick 1-{len(options)} (or name) [s=skip image, q=quit]: ").strip()
        if raw == "":
            if current:
                return current
            print("  required — pick a value.")
            continue
        if raw.lower() == "q":
            return "__QUIT__"
        if raw.lower() == "s":
            return "__SKIP__"
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        if raw.lower() in options:
            return raw.lower()
        print("  invalid — enter a number from the list or the exact name.")


def _as_list(value) -> list[str]:
    """Coerce a field to a list of strings. Tolerates legacy string values
    (e.g. style='sportswear') so 'keep current' returns a clean list, not a
    string iterated character-by-character."""
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    return [str(v).strip() for v in (value or []) if str(v).strip()]


def prompt_list(field: str, current, hint: str = "") -> list[str]:
    """Comma-separated -> list of trimmed strings. Enter = keep current."""
    current = _as_list(current)
    cur = f" [current: {', '.join(current)}]" if current else ""
    extra = f" ({hint})" if hint else ""
    raw = input(f"{field}{extra}{cur}, comma-separated: ").strip()
    if raw == "":
        return current
    return [part.strip() for part in raw.split(",") if part.strip()]


def prompt_optional(field: str, current) -> str | None:
    """Free text; blank = null/None. Enter '-' to clear an existing value."""
    cur = f" [current: {current}]" if current else ""
    raw = input(f"{field}{cur} (blank=null): ").strip()
    if raw == "":
        return current
    if raw == "-":
        return None
    return raw


def label_one(name: str, entry: dict, do_open: bool) -> str:
    """Walk the fields for one image. Returns 'ok', 'skip', or 'quit'."""
    path = IMAGES_DIR / name
    print("\n" + "=" * 64)
    print(f"{name}   (tier: {entry.get('source', '?')})")
    print("=" * 64)
    if do_open:
        open_image(path)

    new: dict = {}
    for field in ("garment_type", "season", "occasion"):
        choice = prompt_enum(field, ENUMS[field], entry.get(field, ""))
        if choice == "__QUIT__":
            return "quit"
        if choice == "__SKIP__":
            return "skip"
        new[field] = choice

    new["style"] = prompt_list("style", entry.get("style") or [], "synonyms ok")
    new["material"] = prompt_list("material", entry.get("material") or [], "synonyms ok")
    new["color"] = prompt_list("color", entry.get("color") or [], "dominant colors")

    loc = dict(entry.get("location_context") or {"continent": None, "country": None, "city": None})
    print("\nlocation — fill ONLY if clearly evidenced in the image, else leave blank (null)")
    loc["continent"] = prompt_optional("  continent", loc.get("continent"))
    loc["country"] = prompt_optional("  country", loc.get("country"))
    loc["city"] = prompt_optional("  city", loc.get("city"))

    # merge: keep source + any untouched keys, overwrite measured fields
    entry.update(new)
    entry["location_context"] = loc
    return "ok"


def select_targets(labels: dict, args) -> list[str]:
    names = sorted(labels)
    if args.file:
        if args.file not in labels:
            sys.exit(f"{args.file} not in labels.json")
        return [args.file]
    if args.tier:
        names = [n for n in names if labels[n].get("source") == args.tier]
    if not args.all:
        names = [n for n in names if not labels[n].get("garment_type")]
    return names


def main() -> None:
    ap = argparse.ArgumentParser(description="Hand-label the eval test set.")
    ap.add_argument("--tier", choices=("street", "studio"), help="only this tier")
    ap.add_argument("--file", help="label a single filename (e.g. to fix one)")
    ap.add_argument("--all", action="store_true", help="include already-labeled (review/relabel)")
    ap.add_argument("--no-open", action="store_true", help="don't auto-open each image")
    args = ap.parse_args()

    if not LABELS_PATH.exists():
        sys.exit(f"{LABELS_PATH} not found; run eval/build_label_stub.py first.")
    labels = json.loads(LABELS_PATH.read_text())

    targets = select_targets(labels, args)
    total = sum(1 for v in labels.values() if v.get("garment_type"))
    if not targets:
        print(f"Nothing to label — {total}/{len(labels)} already labeled. "
              f"Use --all to review, or --file NAME to edit one.")
        return

    print(f"{len(targets)} image(s) to label. {total}/{len(labels)} done so far.")
    print("Enter = keep current value · 's' = skip this image · 'q' = save & quit.\n")

    done = 0
    for i, name in enumerate(targets, 1):
        print(f"\n--- {i}/{len(targets)} ---")
        result = label_one(name, labels[name], do_open=not args.no_open)
        if result == "quit":
            print("\nQuitting (progress saved).")
            break
        if result == "skip":
            print("  skipped.")
            continue
        # save after every completed image so a crash never loses work
        LABELS_PATH.write_text(json.dumps(labels, indent=2, sort_keys=True) + "\n")
        done += 1
        print(f"  saved ✓  ({name})")

    final = sum(1 for v in labels.values() if v.get("garment_type"))
    print(f"\nLabeled {done} this session · {final}/{len(labels)} total.")
    print("Run the eval:  PYTHONPATH=. .venv/bin/python eval/run_eval.py")


if __name__ == "__main__":
    main()
