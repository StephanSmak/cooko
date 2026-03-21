"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

interface SearchBarProps {
  initialQuery?: string;
  autoFocus?: boolean;
  size?: "lg" | "md";
}

export function SearchBar({
  initialQuery = "",
  autoFocus = false,
  size = "md",
}: SearchBarProps) {
  const [value, setValue] = useState(initialQuery);
  const router = useRouter();
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (value === initialQuery) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);

    if (!value.trim()) {
      debounceRef.current = setTimeout(() => {
        router.push("/");
      }, 300);
      return;
    }

    debounceRef.current = setTimeout(() => {
      router.push(`/search?q=${encodeURIComponent(value.trim())}`);
    }, 300);

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (value.trim()) {
      router.push(`/search?q=${encodeURIComponent(value.trim())}`);
    }
  }

  const isLarge = size === "lg";

  return (
    <form
      role="search"
      onSubmit={handleSubmit}
      className="relative w-full"
    >
      {/* Search icon */}
      <div
        className="pointer-events-none absolute inset-y-0 left-0 flex items-center"
        style={{ paddingLeft: isLarge ? "20px" : "14px" }}
      >
        <svg
          width={isLarge ? 20 : 16}
          height={isLarge ? 20 : 16}
          viewBox="0 0 20 20"
          fill="none"
          aria-hidden="true"
          style={{ color: "#9ca3af" }}
        >
          <path
            d="M17.5 17.5L13.875 13.875M15.8333 9.16667C15.8333 12.8486 12.8486 15.8333 9.16667 15.8333C5.48477 15.8333 2.5 12.8486 2.5 9.16667C2.5 5.48477 5.48477 2.5 9.16667 2.5C12.8486 2.5 15.8333 5.48477 15.8333 9.16667Z"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </div>

      <input
        type="search"
        aria-label="Zoek naar producten"
        placeholder="Zoek naar melk, brood, cola…"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        autoFocus={autoFocus}
        autoComplete="off"
        spellCheck={false}
        className="w-full rounded-xl border bg-white transition-shadow outline-none"
        style={{
          paddingLeft: isLarge ? "52px" : "40px",
          paddingRight: value ? (isLarge ? "48px" : "40px") : (isLarge ? "20px" : "14px"),
          paddingTop: isLarge ? "16px" : "10px",
          paddingBottom: isLarge ? "16px" : "10px",
          fontSize: isLarge ? "18px" : "15px",
          borderColor: "#e5e7eb",
          color: "#111827",
          fontFamily: "var(--font-dm-sans)",
          boxShadow: "0 1px 3px rgba(0,0,0,0.05)",
        }}
        onFocus={(e) => {
          e.target.style.borderColor = "#22c55e";
          e.target.style.boxShadow = "0 0 0 3px rgba(34,197,94,0.12)";
        }}
        onBlur={(e) => {
          e.target.style.borderColor = "#e5e7eb";
          e.target.style.boxShadow = "0 1px 3px rgba(0,0,0,0.05)";
        }}
      />

      {/* Clear button */}
      {value && (
        <button
          type="button"
          aria-label="Wis zoekopdracht"
          onClick={() => setValue("")}
          className="absolute inset-y-0 right-0 flex items-center transition-opacity hover:opacity-70"
          style={{ paddingRight: isLarge ? "16px" : "12px" }}
        >
          <svg
            width="16"
            height="16"
            viewBox="0 0 16 16"
            fill="none"
            style={{ color: "#9ca3af" }}
          >
            <path
              d="M12 4L4 12M4 4L12 12"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
            />
          </svg>
        </button>
      )}
    </form>
  );
}
