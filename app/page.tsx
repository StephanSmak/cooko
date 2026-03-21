import { SearchBar } from "@/components/search/SearchBar";

const EXAMPLE_SEARCHES = [
  "melk",
  "boter",
  "cola",
  "eieren",
  "kaas",
  "brood",
];

export default function Home() {
  return (
    <div
      className="flex flex-1 flex-col items-center justify-center px-4 py-16"
      style={{ backgroundColor: "#f9fafb" }}
    >
      {/* Logo / brand */}
      <div className="mb-10 text-center">
        <div className="mb-3 inline-flex items-center justify-center">
          <span
            className="text-5xl font-bold tracking-tight"
            style={{
              fontFamily: "var(--font-dm-sans)",
              color: "#111827",
              letterSpacing: "-0.03em",
            }}
          >
            cooko
          </span>
          <span
            className="ml-1 text-5xl"
            style={{ lineHeight: 1 }}
            aria-hidden="true"
          >
            🌿
          </span>
        </div>
        <p className="text-base" style={{ color: "#6b7280" }}>
          Vergelijk supermarktprijzen in één oogopslag
        </p>
      </div>

      {/* Search bar */}
      <div className="w-full max-w-xl">
        <SearchBar size="lg" autoFocus />
      </div>

      {/* Example searches */}
      <div className="mt-6 flex flex-wrap justify-center gap-2">
        {EXAMPLE_SEARCHES.map((term) => (
          <a
            key={term}
            href={`/search?q=${encodeURIComponent(term)}`}
            className="rounded-full border px-4 py-1.5 text-sm transition-colors hover:border-green-400 hover:bg-green-50 hover:text-green-700"
            style={{
              borderColor: "#e5e7eb",
              color: "#6b7280",
              backgroundColor: "#ffffff",
            }}
          >
            {term}
          </a>
        ))}
      </div>

      {/* Feature callout */}
      <div
        className="mt-16 grid max-w-lg grid-cols-3 gap-4 text-center"
      >
        {[
          { icon: "🏪", title: "9 supermarkten", desc: "AH, Jumbo, PLUS en meer" },
          { icon: "💰", title: "Beste prijs", desc: "Altijd de goedkoopste optie" },
          { icon: "📋", title: "Recepten", desc: "Binnenkort beschikbaar" },
        ].map(({ icon, title, desc }) => (
          <div key={title} className="flex flex-col items-center gap-1">
            <span className="text-2xl">{icon}</span>
            <span
              className="text-xs font-semibold"
              style={{ color: "#111827", fontFamily: "var(--font-dm-sans)" }}
            >
              {title}
            </span>
            <span className="text-xs" style={{ color: "#9ca3af" }}>
              {desc}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
