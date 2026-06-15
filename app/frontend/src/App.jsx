import { useCallback, useEffect, useState } from "react";
import {
  fetchFilters,
  fetchImageDetail,
  fetchImages,
} from "./api";
import SearchBar from "./components/SearchBar.jsx";
import FilterSidebar from "./components/FilterSidebar.jsx";
import ImageGrid from "./components/ImageGrid.jsx";
import UploadModal from "./components/UploadModal.jsx";
import DetailPanel from "./components/DetailPanel.jsx";

export default function App() {
  const [images, setImages] = useState([]);
  const [facets, setFacets] = useState({});
  const [activeFilters, setActiveFilters] = useState({});
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [selected, setSelected] = useState(null);

  const loadImages = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setImages(await fetchImages(activeFilters, query));
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [activeFilters, query]);

  const loadFacets = useCallback(async () => {
    try {
      // facets co-narrow with the active selection, so they depend on the
      // same filters/query as the grid and refetch whenever those change
      setFacets(await fetchFilters(activeFilters, query));
    } catch {
      /* facets are non-critical; ignore transient failures */
    }
  }, [activeFilters, query]);

  // grid and facets reload together whenever filters or the query change
  useEffect(() => {
    loadImages();
    loadFacets();
  }, [loadImages, loadFacets]);

  // refresh both the grid and the filter options after data changes
  const refreshAll = useCallback(() => {
    loadImages();
    loadFacets();
  }, [loadImages, loadFacets]);

  const openDetail = async (image) => {
    setSelected(await fetchImageDetail(image.id));
  };

  return (
    <div className="min-h-screen bg-stone-50 text-stone-900">
      <header className="sticky top-0 z-10 border-b border-stone-200 bg-white">
        <div className="mx-auto flex max-w-7xl items-center gap-4 px-6 py-4">
          <h1 className="text-xl font-semibold tracking-tight">Trendlens</h1>
          <div className="flex-1">
            <SearchBar value={query} onSearch={setQuery} />
          </div>
          <button
            onClick={() => setUploadOpen(true)}
            className="rounded-md bg-stone-900 px-4 py-2 text-sm font-medium text-white hover:bg-stone-700"
          >
            Upload
          </button>
        </div>
      </header>

      <div className="mx-auto flex max-w-7xl gap-6 px-6 py-6">
        <aside className="w-60 shrink-0">
          <FilterSidebar
            facets={facets}
            active={activeFilters}
            onChange={setActiveFilters}
          />
        </aside>

        <main className="flex-1">
          {error && (
            <div className="mb-4 rounded-md bg-red-50 px-4 py-3 text-sm text-red-700">
              {error}
            </div>
          )}
          <p className="mb-3 text-sm text-stone-500" data-testid="image-count">
            {loading ? "Loading…" : `${images.length} image${images.length === 1 ? "" : "s"}`}
          </p>
          <ImageGrid
            images={images}
            onSelect={openDetail}
            onChanged={refreshAll}
          />
        </main>
      </div>

      {uploadOpen && (
        <UploadModal
          onClose={() => setUploadOpen(false)}
          onUploaded={refreshAll}
        />
      )}
      {selected && (
        <DetailPanel
          image={selected}
          onClose={() => setSelected(null)}
          onAnnotated={async () => {
            setSelected(await fetchImageDetail(selected.id));
            loadFacets();
          }}
        />
      )}
    </div>
  );
}
