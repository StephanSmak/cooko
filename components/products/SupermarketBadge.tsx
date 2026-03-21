const SUPERMARKET_COLORS: Record<string, { bg: string; text: string }> = {
  ah: { bg: "#00a950", text: "#ffffff" },
  jumbo: { bg: "#ffc712", text: "#1a1a1a" },
  plus: { bg: "#e31837", text: "#ffffff" },
  dirk: { bg: "#e31837", text: "#ffffff" },
  dekamarkt: { bg: "#003087", text: "#ffffff" },
  spar: { bg: "#00883a", text: "#ffffff" },
  poiesz: { bg: "#003087", text: "#ffffff" },
  vomar: { bg: "#e31837", text: "#ffffff" },
  hoogvliet: { bg: "#e31837", text: "#ffffff" },
};

interface SupermarketBadgeProps {
  id: string;
  name: string;
  logoUrl: string | null;
  size?: "sm" | "md";
}

export function SupermarketBadge({
  id,
  name,
  logoUrl,
  size = "md",
}: SupermarketBadgeProps) {
  const colors = SUPERMARKET_COLORS[id.toLowerCase()] ?? {
    bg: "#6b7280",
    text: "#ffffff",
  };

  const imgSize = size === "sm" ? 16 : 20;

  return (
    <span
      className="inline-flex items-center gap-1.5 rounded font-medium"
      style={{
        backgroundColor: colors.bg,
        color: colors.text,
        fontSize: size === "sm" ? "11px" : "12px",
        padding: size === "sm" ? "2px 7px" : "3px 8px",
        letterSpacing: "0.03em",
      }}
    >
      {logoUrl && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={logoUrl}
          alt=""
          width={imgSize}
          height={imgSize}
          className="rounded-sm object-contain"
          style={{ width: imgSize, height: imgSize }}
        />
      )}
      {name}
    </span>
  );
}
