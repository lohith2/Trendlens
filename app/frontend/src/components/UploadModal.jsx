import { useState } from "react";
import { uploadImage } from "../api";

export default function UploadModal({ onClose, onUploaded }) {
  const [file, setFile] = useState(null);
  const [designer, setDesigner] = useState("");
  const [status, setStatus] = useState("idle"); // idle | uploading | error
  const [error, setError] = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    if (!file) return;
    setStatus("uploading");
    setError(null);
    try {
      const result = await uploadImage(file, designer);
      onUploaded();
      onClose();
      // a failed classification still returns 201 with status=failed;
      // surface that so it isn't mistaken for an upload error
      if (result.status === "failed") {
        alert("Image uploaded, but classification failed. Use Retry on the card.");
      }
    } catch (err) {
      setError(err.message);
      setStatus("error");
    }
  };

  return (
    <div
      className="fixed inset-0 z-20 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="mb-4 text-lg font-semibold">Upload garment photo</h2>
        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-stone-600">
              Image
            </label>
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
              className="block w-full text-sm text-stone-600 file:mr-3 file:rounded-md file:border-0 file:bg-stone-900 file:px-3 file:py-1.5 file:text-sm file:text-white"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-stone-600">
              Designer (optional)
            </label>
            <input
              type="text"
              value={designer}
              onChange={(e) => setDesigner(e.target.value)}
              className="w-full rounded-md border border-stone-300 px-3 py-2 text-sm outline-none focus:border-stone-500"
            />
          </div>

          {status === "uploading" && (
            <p className="text-sm text-amber-700">
              Uploading and classifying… this calls the vision model and may
              take a few seconds.
            </p>
          )}
          {error && <p className="text-sm text-red-600">{error}</p>}

          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md px-4 py-2 text-sm text-stone-600 hover:bg-stone-100"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!file || status === "uploading"}
              className="rounded-md bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-700 disabled:opacity-40"
            >
              {status === "uploading" ? "Working…" : "Upload"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
