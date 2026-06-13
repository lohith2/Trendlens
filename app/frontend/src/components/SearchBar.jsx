import { useEffect, useState } from "react";

// Debounced full-text search box. Mirrors the q= param the backend runs
// against the FTS5 index over descriptions and annotations.
export default function SearchBar({ value, onSearch }) {
  const [text, setText] = useState(value);

  useEffect(() => {
    const id = setTimeout(() => onSearch(text.trim()), 300);
    return () => clearTimeout(id);
  }, [text, onSearch]);

  return (
    <input
      type="search"
      value={text}
      onChange={(e) => setText(e.target.value)}
      placeholder="Search descriptions, tags, notes…"
      className="w-full rounded-md border border-stone-300 bg-white px-3 py-2 text-sm outline-none focus:border-stone-500"
    />
  );
}
