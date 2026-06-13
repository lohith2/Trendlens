# Evaluation

Measures the classifier's per-attribute accuracy against hand-labeled ground
truth, split by image difficulty (street vs studio) and across two models
(`gpt-4o-mini` vs `gpt-4o`).

## Label schema (what `run_eval.py` expects)

Each entry in `test_set/labels.json` is keyed by image filename and has exactly
these fields. `build_label_stub.py` writes blank stubs in this shape; you fill
them in by hand.

```jsonc
"street_10365761.jpg": {
  "source": "street",          // "street" | "studio". Set by the stub generator — do not edit.
  "garment_type": "dress",     // exactly ONE value from GarmentType (app/backend/schemas.py)
  "season": "summer",          // exactly ONE value from Season
  "occasion": "casual",        // exactly ONE value from Occasion
  "style": ["bohemian", "boho"],   // list of acceptable answers (synonyms encouraged)
  "material": ["denim", "cotton"], // list of acceptable answers
  "color": ["indigo", "cream"],    // list of dominant color words
  "location_context": {
    "continent": null,         // string ONLY if clearly evidenced in the image, else null
    "country": null,           // string ONLY if clearly evidenced, else null
    "city": null               // recorded but NOT scored
  }
}
```

Rules for the labeler:

- **Enums** (`garment_type`, `season`, `occasion`): the single best value, spelled
  exactly as in `app/backend/schemas.py`. The harness validates these on load and
  **aborts with the filename and bad value** on any typo — empty `""` is allowed and
  means "not yet labeled" (that image is skipped, not scored).
- **`garment_type` is the labeled-gate:** an entry is treated as labeled (and thus
  classified + scored) the moment `garment_type` is non-empty. Leave it `""` to defer.
- **Free-text** (`style`, `material`): a *list* of acceptable answers. Add every
  reasonable synonym you'd accept as correct — the more complete the list, the fairer
  the score. An empty list means "unscored for this image."
- **`color`**: list of dominant color words. Empty list = unscored.
- **`location_context`**: fill `continent`/`country` only when the image genuinely
  shows it (signage, landmark, etc.). Leave `null` otherwise — the harness *requires*
  the model to also say null there, so a confabulated location is penalized.

## Matching rules (how `run_eval.py` scores each field)

| Field | Type | Rule |
|---|---|---|
| `garment_type`, `season`, `occasion` | enum | normalized **exact** match (lowercase + strip) |
| `style`, `material` | free text | prediction matches if, normalized, it equals **or** is a substring of **or** contains any acceptable answer in the label list |
| `color` | list | **overlap**: correct if any predicted color fuzzy-matches any labeled color (not exact set equality) |
| `continent`, `country` | location | scored separately; null label ⇒ prediction must also be null (confabulation penalized); non-null label ⇒ fuzzy match |

"Fuzzy" throughout means normalized equality or substring containment in either
direction (`"denim"` ≈ `"denim jacket"`). Substring is deliberately lenient: free-text
attributes have no closed vocabulary, so phrasing differences shouldn't read as errors.

## Test set

~70 images under `test_set/images/`, unified by one labeling schema in
`test_set/labels.json` and tagged `source: street | studio`.

| Tier | Count | Origin | Labels |
|---|---|---|---|
| street | ~45 | Pexels API (in-the-wild, varied regions/lighting) | hand-labeled |
| studio | ~25 | Pexels API (plain-background product/model shots) | hand-labeled |

Two natural difficulty tiers: studio shots are clean and isolated; street shots
add occlusion, layering, and ambiguous material — the interesting failure modes.
Both tiers come from Pexels (different query sets) so the set rebuilds with one
API key and no manual dataset download.

## Rebuilding the test set

Set `PEXELS_API_KEY` in `.env`, then fetch each tier (separate query sets):

```bash
PYTHONPATH=. .venv/bin/python eval/fetch_pexels.py --source street --target 45
PYTHONPATH=. .venv/bin/python eval/fetch_pexels.py --source studio --target 25
```

Idempotent (skips photos already fetched by id, across both tiers) and writes
attribution to `test_set/sources.json`, as the Pexels API terms require. Files
are named `<tier>_<pexels-id>.jpg` and tagged with their source tier.

## Labeling

```bash
PYTHONPATH=. .venv/bin/python eval/build_label_stub.py
```

Creates/tops up `test_set/labels.json` with a blank entry per image in the shape
documented under [Label schema](#label-schema-what-run_evalpy-expects) above.
Fill the fields **by hand** — do not pre-label with the model, which would bias
the eval.

## Running the eval

```bash
# needs OPENAI_API_KEY; runs every image through both models (~2x the image count in calls)
PYTHONPATH=. .venv/bin/python eval/run_eval.py
```

Writes the per-attribute accuracy table (street vs studio, mini vs flagship) and
the failure analysis to `eval/results.md`, and reports the observed
validation-retry rate.
