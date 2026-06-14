"""Score the classifier against hand-labeled ground truth, per attribute.

Reuses app/backend/classifier.classify_image, so the eval measures the exact
production path (same prompt, same schema, same validation-retry loop). The
only model calls are the classifications themselves; scoring is pure string
comparison.

Pipeline:
    load labels.json  ->  validate enum labels (fail loud on typos)  ->
    classify each labeled image under each model  ->  per-attribute match  ->
    write eval/results.md (accuracy split by street/studio, per model).

Predictions are cached per model in eval/test_set/predictions_<model>.json,
keyed by filename, because a prediction depends only on (image, model) and not
on the labels. Re-scoring after editing labels is therefore free; pass
--refresh to re-classify from scratch.

Usage:
    PYTHONPATH=. .venv/bin/python eval/run_eval.py                  # both models
    PYTHONPATH=. .venv/bin/python eval/run_eval.py --models gpt-4o-mini
    PYTHONPATH=. .venv/bin/python eval/run_eval.py --limit 5 --refresh

Needs OPENAI_API_KEY in the environment (or .env).
"""

from __future__ import annotations

import argparse
import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from app.backend.classifier import ClassificationError, classify_image
from app.backend.schemas import GarmentType, Occasion, Season

TEST_SET = Path(__file__).parent / "test_set"
IMAGES_DIR = TEST_SET / "images"
LABELS_PATH = TEST_SET / "labels.json"
RESULTS_PATH = Path(__file__).parent / "results.md"

DEFAULT_MODELS = ["gpt-4o-mini", "gpt-4o"]
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}

# Enum label fields and their backing schema enum. A label value for one of
# these must be exactly one of the enum's string values.
ENUM_FIELDS = {
    "garment_type": GarmentType,
    "season": Season,
    "occasion": Occasion,
}

# Attribute rows in the results table, in display order. continent/country are
# the two scored components of location_context (city is recorded but not
# scored: it is too sparse to measure and not a stated requirement).
ATTRIBUTES = [
    "garment_type",
    "season",
    "occasion",
    "style",
    "material",
    "color",
    "continent",
    "country",
]


# --------------------------------------------------------------------------- #
# Normalization + matching rules (see eval/README.md for the documented rules)
# --------------------------------------------------------------------------- #
def _norm(value) -> str:
    return (value or "").strip().lower() if isinstance(value, str) else ""


def _as_list(value) -> list[str]:
    """Coerce a label/prediction field to a list of non-empty strings.

    Tolerates a bare string (treated as a one-item list) so older single-value
    labels still load.
    """
    if isinstance(value, str):
        return [value] if value.strip() else []
    return [str(v) for v in (value or []) if str(v).strip()]


def _fuzzy_eq(a: str, b: str) -> bool:
    """Normalized equality OR substring containment in either direction.

    "denim" matches "denim jacket" (label contained in prediction) and
    "light denim" matches "denim" (prediction contained in label). Substring
    containment is deliberately lenient: free-text attributes have no closed
    vocabulary, so a stricter rule would penalize correct-but-phrased-differently
    answers more than it would catch genuine errors.
    """
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return False
    return a == b or a in b or b in a


def match_enum(pred: str, label: str) -> bool:
    """Exact match on the normalized enum value."""
    return _norm(pred) == _norm(label)


def match_freetext(pred: str, label_list) -> bool | None:
    """style / material: label is a list of acceptable answers.

    The prediction matches if, normalized, it is fuzzy-equal (see _fuzzy_eq)
    to ANY acceptable answer. Returns None when the label list is empty, which
    means "unscored for this image" (the labeler had no confident answer).
    """
    accepts = _as_list(label_list)
    if not accepts:
        return None
    pred = _norm(pred)
    if not pred:
        return False
    return any(_fuzzy_eq(pred, a) for a in accepts)


# Color spelling/shade equivalences applied before fuzzy matching. Substring
# replacements so compounds normalize too ("light gray" -> "light grey"). Kept
# deliberately tight: only same-color spelling variants (grey/gray) and shades
# used interchangeably in fashion tagging (burgundy/maroon) — not perceptual
# neighbors like beige/cream, which the model should still be expected to tell
# apart.
_COLOR_CANON = {
    "gray": "grey",
    "burgundy": "maroon",
}


def _canon_color(value: str) -> str:
    out = _norm(value)
    for variant, canon in _COLOR_CANON.items():
        out = out.replace(variant, canon)
    return out


def match_color(pred_list, label_list) -> bool | None:
    """color_palette: correct if the predicted and labeled color sets overlap.

    Overlap (not exact set equality) because a garment's palette is fuzzy:
    crediting the model for finding the labeled colors, without penalizing it
    for naming an extra shade, is the fairer measure. Spelling/shade variants
    are canonicalized first (see _COLOR_CANON). Returns None when the label has
    no colors (unscored).
    """
    labels = _as_list(label_list)
    if not labels:
        return None
    preds = _as_list(pred_list)
    if not preds:
        return False
    return any(_fuzzy_eq(_canon_color(p), _canon_color(l)) for p in preds for l in labels)


def match_location(pred_value, label_value) -> bool:
    """continent / country, scored independently.

    Null label (no location evidenced) is correct ONLY if the model also
    returns null/empty: a confabulated location is penalized. A non-null label
    is matched fuzzily against the prediction.
    """
    pred, label = _norm(pred_value), _norm(label_value)
    if not label:
        return not pred  # honest "unknown" required; confabulation is wrong
    if not pred:
        return False
    return _fuzzy_eq(pred, label)


# --------------------------------------------------------------------------- #
# Loading + validation
# --------------------------------------------------------------------------- #
def load_labels() -> dict:
    if not LABELS_PATH.exists():
        raise SystemExit(f"{LABELS_PATH} not found; run eval/build_label_stub.py first.")
    return json.loads(LABELS_PATH.read_text())


def validate_labels(labels: dict) -> None:
    """Fail loudly on enum typos before spending any API budget.

    Every non-empty garment_type/season/occasion must be a real enum member.
    Empty ("") means not-yet-labeled and is allowed (that image is skipped).
    """
    errors: list[str] = []
    for name, label in labels.items():
        for field_name, enum in ENUM_FIELDS.items():
            value = label.get(field_name, "")
            if value == "" or value is None:
                continue
            allowed = {m.value for m in enum}
            if value not in allowed:
                errors.append(
                    f"  {name}: {field_name}={value!r} is not a valid "
                    f"{enum.__name__}. Allowed: {sorted(allowed)}"
                )
        source = label.get("source")
        if source not in ("street", "studio"):
            errors.append(f"  {name}: source={source!r} must be 'street' or 'studio'")
    if errors:
        raise SystemExit(
            "Label validation failed (fix eval/test_set/labels.json):\n"
            + "\n".join(errors)
        )


def is_labeled(label: dict) -> bool:
    """An entry counts as labeled once its garment_type is filled in. This is
    the single gate for whether the image is classified and scored."""
    return bool(label.get("garment_type"))


def discover_images(labels: dict, limit: int | None) -> list[tuple[str, Path]]:
    """Labeled entries that have a matching image file, in sorted order."""
    pairs: list[tuple[str, Path]] = []
    for name in sorted(labels):
        if not is_labeled(labels[name]):
            continue
        path = IMAGES_DIR / name
        if path.suffix.lower() not in IMAGE_SUFFIXES or not path.exists():
            continue
        pairs.append((name, path))
    return pairs[:limit] if limit else pairs


# --------------------------------------------------------------------------- #
# Classification (with retry counting + per-model prediction cache)
# --------------------------------------------------------------------------- #
class _RetryCounter(logging.Handler):
    """Counts validation-retry warnings emitted by the classifier."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.count = 0

    def emit(self, record: logging.LogRecord) -> None:
        if "failed validation" in record.getMessage():
            self.count += 1


def predictions_path(model: str) -> Path:
    safe = model.replace("/", "_")
    return TEST_SET / f"predictions_{safe}.json"


def get_predictions(
    images: list[tuple[str, Path]], model: str, refresh: bool
) -> tuple[dict, int, int]:
    """Classify each image under `model`, caching results to disk.

    Returns (predictions, retries_observed, failures). `retries_observed` only
    reflects images classified on THIS run (cache hits do not re-call the API).
    A failed classification is stored as {"__failed__": <reason>}.
    """
    cache_path = predictions_path(model)
    cache: dict = {}
    if cache_path.exists() and not refresh:
        cache = json.loads(cache_path.read_text())

    counter = _RetryCounter()
    clf_logger = logging.getLogger("app.backend.classifier")
    clf_logger.addHandler(counter)
    prev_level = clf_logger.level
    clf_logger.setLevel(logging.WARNING)

    failures = 0
    try:
        for name, path in images:
            if name in cache:
                if "__failed__" in cache[name]:
                    failures += 1
                continue
            print(f"  [{model}] classifying {name} ...", flush=True)
            try:
                attrs = classify_image(path, model=model)
                cache[name] = attrs.model_dump(mode="json")
            except ClassificationError as exc:
                cache[name] = {"__failed__": str(exc)}
                failures += 1
                print(f"    FAILED: {exc}", flush=True)
            cache_path.write_text(json.dumps(cache, indent=2) + "\n")
    finally:
        clf_logger.removeHandler(counter)
        clf_logger.setLevel(prev_level)

    return cache, counter.count, failures


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
@dataclass
class Tally:
    correct: int = 0
    total: int = 0

    def add(self, ok: bool | None) -> None:
        if ok is None:
            return  # unscored for this image
        self.total += 1
        self.correct += int(ok)

    @property
    def pct(self) -> float | None:
        return (100.0 * self.correct / self.total) if self.total else None


@dataclass
class Miss:
    image: str
    attribute: str
    predicted: str
    expected: str


@dataclass
class ModelResult:
    model: str
    # scores[tier][attribute] -> Tally ; tier in {street, studio, overall}
    scores: dict[str, dict[str, Tally]] = field(
        default_factory=lambda: defaultdict(lambda: defaultdict(Tally))
    )
    misses: list[Miss] = field(default_factory=list)
    retries: int = 0
    failures: int = 0
    classified: int = 0


def _score_image(result: ModelResult, name: str, tier: str, pred: dict, label: dict) -> None:
    loc_pred = pred.get("location_context") or {}
    loc_label = label.get("location_context") or {}

    checks: dict[str, bool | None] = {
        "garment_type": match_enum(pred.get("garment_type"), label.get("garment_type")),
        "season": match_enum(pred.get("season"), label.get("season")),
        "occasion": match_enum(pred.get("occasion"), label.get("occasion")),
        "style": match_freetext(pred.get("style"), label.get("style")),
        "material": match_freetext(pred.get("material"), label.get("material")),
        "color": match_color(pred.get("color_palette"), label.get("color")),
        "continent": match_location(loc_pred.get("continent"), loc_label.get("continent")),
        "country": match_location(loc_pred.get("country"), loc_label.get("country")),
    }

    for attr, ok in checks.items():
        result.scores[tier][attr].add(ok)
        result.scores["overall"][attr].add(ok)
        if ok is False:
            result.misses.append(
                Miss(
                    image=name,
                    attribute=attr,
                    predicted=_render_pred(attr, pred),
                    expected=_render_label(attr, label),
                )
            )


def _render_pred(attr: str, pred: dict) -> str:
    if attr in ("continent", "country"):
        return str((pred.get("location_context") or {}).get(attr))
    if attr == "color":
        return str(pred.get("color_palette"))
    return str(pred.get(attr))


def _render_label(attr: str, label: dict) -> str:
    if attr in ("continent", "country"):
        return str((label.get("location_context") or {}).get(attr))
    return str(label.get(attr))


def score_model(model: str, images, labels, refresh) -> ModelResult:
    predictions, retries, failures = get_predictions(images, model, refresh)
    result = ModelResult(model=model, retries=retries, failures=failures)
    for name, _path in images:
        pred = predictions.get(name)
        if not pred or "__failed__" in pred:
            continue  # failed classifications are reported, not scored
        result.classified += 1
        tier = labels[name].get("source", "studio")
        _score_image(result, name, tier, pred, labels[name])
    return result


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #
def _cell(tally: Tally) -> str:
    if tally.total == 0:
        return "—"
    return f"{tally.pct:.0f}% ({tally.correct}/{tally.total})"


def render_results(results: list[ModelResult], labels: dict) -> str:
    n_labeled = sum(1 for v in labels.values() if is_labeled(v))
    tiers = {"street": 0, "studio": 0}
    for v in labels.values():
        if is_labeled(v):
            tiers[v.get("source", "studio")] = tiers.get(v.get("source", "studio"), 0) + 1

    lines: list[str] = []
    lines.append("# Evaluation Results")
    lines.append("")
    lines.append(
        f"_Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')} "
        f"over {n_labeled} labeled images "
        f"(street: {tiers.get('street', 0)}, studio: {tiers.get('studio', 0)})._"
    )
    lines.append("")
    lines.append(
        "Matching rules per attribute are documented in `eval/README.md`. "
        "Cells show `accuracy (correct/scored)`; an attribute is *scored* only "
        "for images whose label provides a ground-truth value for it."
    )
    lines.append("")

    for res in results:
        lines.append(f"## {res.model}")
        lines.append("")
        lines.append(
            f"Classified {res.classified} images · "
            f"{res.failures} classification failure(s) · "
            f"{res.retries} validation retr{'y' if res.retries == 1 else 'ies'} "
            f"observed (fresh classifications only; cache hits do not re-call)."
        )
        lines.append("")
        lines.append("| Attribute | Street | Studio | Overall |")
        lines.append("|---|---|---|---|")
        for attr in ATTRIBUTES:
            street = res.scores["street"][attr]
            studio = res.scores["studio"][attr]
            overall = res.scores["overall"][attr]
            lines.append(
                f"| {attr} | {_cell(street)} | {_cell(studio)} | {_cell(overall)} |"
            )
        lines.append("")

    # mini vs flagship overall delta, if more than one model ran
    if len(results) > 1:
        base = results[0]
        lines.append("## Overall accuracy by model")
        lines.append("")
        header = "| Attribute | " + " | ".join(r.model for r in results) + " |"
        lines.append(header)
        lines.append("|" + "---|" * (len(results) + 1))
        for attr in ATTRIBUTES:
            cells = " | ".join(_cell(r.scores["overall"][attr]) for r in results)
            lines.append(f"| {attr} | {cells} |")
        lines.append("")
        _ = base  # reserved for an explicit delta column if needed later

    # per-image misses for the failure analysis
    for res in results:
        if not res.misses:
            continue
        lines.append(f"<details><summary>{res.model}: {len(res.misses)} per-attribute misses</summary>")
        lines.append("")
        lines.append("| Image | Attribute | Predicted | Expected |")
        lines.append("|---|---|---|---|")
        for m in res.misses:
            lines.append(f"| {m.image} | {m.attribute} | {m.predicted} | {m.expected} |")
        lines.append("")
        lines.append("</details>")
        lines.append("")

    lines.append("## Analysis")
    lines.append("")
    lines.append(_preserved_analysis())
    lines.append("")
    return "\n".join(lines)


def _preserved_analysis() -> str:
    """Carry a hand-written Analysis section across re-runs.

    The tables above are always regenerated, but the narrative below them is
    written by hand. Re-read the previous results.md and keep its Analysis body
    unless it is still the placeholder, so re-scoring never clobbers the writeup.
    """
    placeholder = "> TODO after reviewing the table and misses above."
    if RESULTS_PATH.exists():
        prev = RESULTS_PATH.read_text()
        _, _, after = prev.partition("\n## Analysis\n")
        body = after.strip()
        if body and placeholder not in body:
            return body
    return placeholder


# --------------------------------------------------------------------------- #
# Entrypoint
# --------------------------------------------------------------------------- #
def main() -> None:
    parser = argparse.ArgumentParser(description="Score the classifier on the eval set.")
    parser.add_argument(
        "--models",
        default=",".join(DEFAULT_MODELS),
        help="comma-separated model ids (default: gpt-4o-mini,gpt-4o)",
    )
    parser.add_argument("--limit", type=int, default=None, help="score only the first N labeled images")
    parser.add_argument("--refresh", action="store_true", help="ignore cached predictions and re-classify")
    args = parser.parse_args()

    load_dotenv()
    models = [m.strip() for m in args.models.split(",") if m.strip()]

    labels = load_labels()
    validate_labels(labels)  # fail loud on typos before any API spend

    images = discover_images(labels, args.limit)
    if not images:
        n = len(labels)
        raise SystemExit(
            f"0 of {n} entries are labeled (need a garment_type). "
            f"Fill eval/test_set/labels.json by hand, then re-run.\n"
            f"Schema and matching rules: eval/README.md."
        )

    print(f"Scoring {len(images)} labeled image(s) across models: {', '.join(models)}")
    results = [score_model(m, images, labels, args.refresh) for m in models]

    RESULTS_PATH.write_text(render_results(results, labels) + "\n")
    print(f"\nWrote {RESULTS_PATH}")
    for res in results:
        overall = res.scores["overall"]["garment_type"]
        gt = f"{overall.pct:.0f}%" if overall.total else "n/a"
        print(
            f"  {res.model}: {res.classified} classified, {res.failures} failed, "
            f"{res.retries} retries · garment_type {gt}"
        )


if __name__ == "__main__":
    main()
