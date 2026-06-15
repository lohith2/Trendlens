// Filter options are rendered entirely from /api/filters facets, so the
// sidebar only ever shows values that exist in the data - nothing hardcoded.

const FIELD_ORDER = [
  ["garment_type", "Garment type"],
  ["style", "Style"],
  ["material", "Material"],
  ["pattern", "Pattern"],
  ["color", "Color"],
  ["season", "Season"],
  ["occasion", "Occasion"],
  ["designer", "Designer"],
  ["continent", "Continent"],
  ["country", "Country"],
  ["city", "City"],
  ["year", "Year"],
  ["month", "Month"],
];

export default function FilterSidebar({ facets, active, onChange }) {
  const setField = (field, value) => {
    const next = { ...active };
    if (value === "") delete next[field];
    else next[field] = value;
    onChange(next);
  };

  const hasAny = FIELD_ORDER.some(([f]) => (facets[f] || []).length > 0);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-stone-500">
          Filters
        </h2>
        {Object.keys(active).length > 0 && (
          <button
            onClick={() => onChange({})}
            className="text-xs text-stone-500 underline hover:text-stone-800"
          >
            Clear
          </button>
        )}
      </div>

      {!hasAny && (
        <p className="text-sm text-stone-400">
          Filters appear as images are classified.
        </p>
      )}

      {FIELD_ORDER.map(([field, label]) => {
        const options = facets[field] || [];
        const selected = active[field];
        // self-exclusion should keep a selected value in its own options, but
        // if it ever isn't, still render it so the selection doesn't silently
        // reset out from under the user
        const opts =
          selected != null &&
          selected !== "" &&
          !options.some((o) => String(o) === String(selected))
            ? [...options, selected]
            : options;
        if (opts.length === 0) return null;
        return (
          <div key={field}>
            <label className="mb-1 block text-xs font-medium text-stone-600">
              {label}
            </label>
            <select
              value={active[field] ?? ""}
              onChange={(e) => setField(field, e.target.value)}
              data-testid={`filter-${field}`}
              className="w-full rounded-md border border-stone-300 bg-white px-2 py-1.5 text-sm outline-none focus:border-stone-500"
            >
              <option value="">All</option>
              {opts.map((opt) => (
                <option key={opt} value={opt}>
                  {String(opt).replace(/_/g, " ")}
                </option>
              ))}
            </select>
          </div>
        );
      })}
    </div>
  );
}
