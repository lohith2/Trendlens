import { useState } from "react";
import { addAnnotation, imageUrl } from "../api";

// AI-generated fields and designer annotations are deliberately styled
// differently: AI output gets the indigo "AI" treatment, designer input
// the amber "Designer" treatment, so the two are never confused.

function AiField({ label, value }) {
  if (value === null || value === undefined || value === "") return null;
  const display = Array.isArray(value) ? value.join(", ") : String(value);
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-stone-400">
        {label}
      </dt>
      <dd className="text-sm capitalize text-stone-800">
        {display.replace(/_/g, " ")}
      </dd>
    </div>
  );
}

function AnnotationForm({ imageId, onAnnotated }) {
  const [kind, setKind] = useState("tag");
  const [content, setContent] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (!content.trim()) return;
    setBusy(true);
    try {
      await addAnnotation(imageId, kind, content.trim());
      setContent("");
      onAnnotated();
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="flex gap-2">
      <select
        value={kind}
        onChange={(e) => setKind(e.target.value)}
        className="rounded-md border border-stone-300 px-2 py-1.5 text-sm"
      >
        <option value="tag">Tag</option>
        <option value="note">Note</option>
      </select>
      <input
        value={content}
        onChange={(e) => setContent(e.target.value)}
        placeholder="Add a tag or note…"
        className="flex-1 rounded-md border border-stone-300 px-3 py-1.5 text-sm outline-none focus:border-stone-500"
      />
      <button
        type="submit"
        disabled={busy || !content.trim()}
        className="rounded-md bg-amber-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-amber-700 disabled:opacity-40"
      >
        Add
      </button>
    </form>
  );
}

export default function DetailPanel({ image, onClose, onAnnotated }) {
  const attrs = image.attributes || {};
  const loc = attrs.location_context || {};
  const locationParts = [loc.city, loc.country, loc.continent].filter(Boolean);
  const annotations = image.annotations || [];

  return (
    <div
      className="fixed inset-0 z-20 flex justify-end bg-black/40"
      onClick={onClose}
    >
      <div
        className="h-full w-full max-w-lg overflow-y-auto bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-stone-200 px-6 py-4">
          <h2 className="text-lg font-semibold capitalize">
            {image.garment_type
              ? image.garment_type.replace(/_/g, " ")
              : "Image"}
          </h2>
          <button
            onClick={onClose}
            className="text-stone-400 hover:text-stone-700"
          >
            ✕
          </button>
        </div>

        <img
          src={imageUrl(image)}
          alt={image.garment_type || "garment"}
          className="max-h-80 w-full bg-stone-100 object-contain"
        />

        <div className="space-y-6 p-6">
          {/* AI section */}
          <section>
            <div className="mb-3 flex items-center gap-2">
              <span className="rounded bg-indigo-100 px-2 py-0.5 text-xs font-semibold text-indigo-700">
                AI
              </span>
              <h3 className="text-sm font-semibold text-stone-700">
                Model classification
              </h3>
            </div>
            {image.description && (
              <p className="mb-4 text-sm leading-relaxed text-stone-700">
                {image.description}
              </p>
            )}
            <dl className="grid grid-cols-2 gap-3">
              <AiField label="Garment" value={image.garment_type} />
              <AiField label="Style" value={attrs.style} />
              <AiField label="Material" value={attrs.material} />
              <AiField label="Pattern" value={attrs.pattern} />
              <AiField label="Colors" value={attrs.color_palette} />
              <AiField label="Season" value={image.season} />
              <AiField label="Occasion" value={image.occasion} />
              <AiField label="Consumer" value={attrs.consumer_profile} />
              <AiField
                label="Location"
                value={locationParts.length ? locationParts.join(", ") : null}
              />
            </dl>
            {attrs.trend_notes && (
              <div className="mt-3">
                <dt className="text-xs font-medium uppercase tracking-wide text-stone-400">
                  Trend notes
                </dt>
                <dd className="text-sm text-stone-700">{attrs.trend_notes}</dd>
              </div>
            )}
          </section>

          {/* Designer section */}
          <section className="rounded-lg bg-amber-50 p-4">
            <div className="mb-3 flex items-center gap-2">
              <span className="rounded bg-amber-200 px-2 py-0.5 text-xs font-semibold text-amber-800">
                Designer
              </span>
              <h3 className="text-sm font-semibold text-stone-700">
                Annotations
              </h3>
            </div>
            {annotations.length === 0 ? (
              <p className="mb-3 text-sm text-stone-500">
                No annotations yet.
              </p>
            ) : (
              <ul className="mb-3 space-y-2">
                {annotations.map((a) => (
                  <li key={a.id} className="flex items-start gap-2 text-sm">
                    <span
                      className={`rounded px-1.5 py-0.5 text-xs font-medium ${
                        a.kind === "tag"
                          ? "bg-amber-200 text-amber-800"
                          : "bg-stone-200 text-stone-700"
                      }`}
                    >
                      {a.kind}
                    </span>
                    <span className="text-stone-800">{a.content}</span>
                  </li>
                ))}
              </ul>
            )}
            <AnnotationForm imageId={image.id} onAnnotated={onAnnotated} />
          </section>

          <p className="text-xs text-stone-400">
            {image.designer ? `Uploaded by ${image.designer} · ` : ""}
            {image.uploaded_at?.slice(0, 10)}
          </p>
        </div>
      </div>
    </div>
  );
}
