// Thin wrapper over the Trendlens API. URLs are relative; Vite proxies
// /api and /uploads to the FastAPI backend in development.

export function imageUrl(image) {
  return `/uploads/${image.filename}`;
}

export async function fetchImages(filters = {}, q = "") {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  for (const [key, value] of Object.entries(filters)) {
    if (value !== null && value !== undefined && value !== "") {
      params.set(key, value);
    }
  }
  const res = await fetch(`/api/images?${params.toString()}`);
  if (!res.ok) throw new Error(`failed to load images (${res.status})`);
  return res.json();
}

export async function fetchFilters(filters = {}, q = "") {
  // facets co-narrow with the active selection, so they take the same params
  // as the image query
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  for (const [key, value] of Object.entries(filters)) {
    if (value !== null && value !== undefined && value !== "") {
      params.set(key, value);
    }
  }
  const res = await fetch(`/api/filters?${params.toString()}`);
  if (!res.ok) throw new Error(`failed to load filters (${res.status})`);
  return res.json();
}

export async function fetchImageDetail(id) {
  const res = await fetch(`/api/images/${id}`);
  if (!res.ok) throw new Error(`failed to load image ${id} (${res.status})`);
  return res.json();
}

export async function uploadImage(file, designer) {
  const body = new FormData();
  body.append("file", file);
  if (designer) body.append("designer", designer);
  const res = await fetch("/api/images", { method: "POST", body });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || `upload failed (${res.status})`);
  }
  return res.json();
}

export async function retryClassification(id) {
  const res = await fetch(`/api/images/${id}/retry`, { method: "POST" });
  if (!res.ok) throw new Error(`retry failed (${res.status})`);
  return res.json();
}

export async function addAnnotation(id, kind, content) {
  const res = await fetch(`/api/images/${id}/annotations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind, content }),
  });
  if (!res.ok) throw new Error(`failed to add annotation (${res.status})`);
  return res.json();
}
