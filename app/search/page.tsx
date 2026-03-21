import { searchProductGroups } from "@/lib/db/search";
import { ProductGroupCard } from "@/components/products/ProductGroupCard";
import { SearchBar } from "@/components/search/SearchBar";
import Link from "next/link";

export default async function SearchPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const { q } = await searchParams;
  const query = q?.trim() ?? "";

  const groups = query ? await searchProductGroups(query) : [];

  return (
    <div className="mx-auto w-full max-w-2xl px-4 py-8">
      {/* Search bar */}
      <div className="mb-8">
        <SearchBar initialQuery={query} />
      </div>

      {/* Results header */}
      {query && (
        <div className="mb-5 flex items-center justify-between">
          <p className="text-sm" style={{ color: "#6b7280" }}>
            {groups.length === 0 ? (
              <>Geen resultaten voor <strong style={{ color: "#111827" }}>&ldquo;{query}&rdquo;</strong></>
            ) : (
              <>
                <strong style={{ color: "#111827" }}>{groups.length}</strong>{" "}
                {groups.length === 1 ? "product" : "producten"} gevonden voor{" "}
                <strong style={{ color: "#111827" }}>&ldquo;{query}&rdquo;</strong>
              </>
            )}
          </p>
        </div>
      )}

      {/* Empty states */}
      {!query && (
        <div className="py-16 text-center">
          <p className="text-4xl">🔍</p>
          <p className="mt-3 text-sm" style={{ color: "#9ca3af" }}>
            Voer een zoekterm in om producten te vergelijken
          </p>
        </div>
      )}

      {query && groups.length === 0 && (
        <div className="py-16 text-center">
          <p className="text-4xl">🥲</p>
          <p className="mt-3 text-sm" style={{ color: "#9ca3af" }}>
            Geen producten gevonden voor &ldquo;{query}&rdquo;
          </p>
          <Link
            href="/"
            className="mt-4 inline-block text-sm font-medium"
            style={{ color: "#22c55e" }}
          >
            Terug naar home
          </Link>
        </div>
      )}

      {/* Results grid */}
      {groups.length > 0 && (
        <div className="space-y-4">
          {groups.map((group) => (
            <ProductGroupCard key={group.id} group={group} />
          ))}
        </div>
      )}
    </div>
  );
}
