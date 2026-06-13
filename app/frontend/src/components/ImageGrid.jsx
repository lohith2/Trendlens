import { useState } from "react";
import { imageUrl, retryClassification } from "../api";

function StatusBadge({ status }) {
  const styles = {
    classified: "bg-emerald-100 text-emerald-800",
    processing: "bg-amber-100 text-amber-800",
    failed: "bg-red-100 text-red-800",
  };
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs font-medium ${styles[status] || "bg-stone-100 text-stone-600"}`}
    >
      {status}
    </span>
  );
}

function ImageCard({ image, onSelect, onChanged }) {
  const [retrying, setRetrying] = useState(false);

  const retry = async (e) => {
    e.stopPropagation();
    setRetrying(true);
    try {
      await retryClassification(image.id);
      onChanged();
    } finally {
      setRetrying(false);
    }
  };

  return (
    <button
      onClick={() => onSelect(image)}
      className="group flex flex-col overflow-hidden rounded-lg border border-stone-200 bg-white text-left transition hover:shadow-md"
    >
      <div className="aspect-square overflow-hidden bg-stone-100">
        <img
          src={imageUrl(image)}
          alt={image.garment_type || "garment"}
          className="h-full w-full object-cover transition group-hover:scale-105"
          loading="lazy"
        />
      </div>
      <div className="flex flex-1 flex-col gap-1.5 p-3">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium capitalize">
            {image.garment_type
              ? image.garment_type.replace(/_/g, " ")
              : "—"}
          </span>
          <StatusBadge status={image.status} />
        </div>
        {image.description && (
          <p className="line-clamp-2 text-xs text-stone-500">
            {image.description}
          </p>
        )}
        {image.status === "failed" && (
          <span
            onClick={retry}
            className="mt-1 cursor-pointer rounded-md bg-stone-900 px-2 py-1 text-center text-xs font-medium text-white hover:bg-stone-700"
          >
            {retrying ? "Retrying…" : "Retry classification"}
          </span>
        )}
      </div>
    </button>
  );
}

export default function ImageGrid({ images, onSelect, onChanged }) {
  if (images.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-stone-300 py-20 text-center text-sm text-stone-400">
        No images match. Upload a garment photo to get started.
      </div>
    );
  }
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
      {images.map((image) => (
        <ImageCard
          key={image.id}
          image={image}
          onSelect={onSelect}
          onChanged={onChanged}
        />
      ))}
    </div>
  );
}
