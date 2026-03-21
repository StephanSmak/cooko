interface PriceBadgeProps {
  price: number;
  isCheapest: boolean;
  pricePerUnit: number | null;
  unit: string | null;
  baseUnit?: string | null;
}

function formatPrice(price: number) {
  return price.toLocaleString("nl-NL", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: 2,
  });
}

function formatPricePerUnit(
  pricePerUnit: number,
  unit: string | null,
  baseUnit?: string | null
) {
  const displayUnit = baseUnit ?? unit ?? "stuk";
  // price_per_unit is per single unit (1g, 1ml, 1 stuks)
  // Show per 100g / 100ml for small units
  let multiplier = 1;
  let label = displayUnit;
  if (displayUnit === "g" || displayUnit === "ml") {
    multiplier = 100;
    label = `100${displayUnit}`;
  } else if (displayUnit === "stuks") {
    label = "stuk";
  }
  const scaledPrice = pricePerUnit * multiplier;
  return `${scaledPrice.toLocaleString("nl-NL", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })} / ${label}`;
}

export function PriceBadge({
  price,
  isCheapest,
  pricePerUnit,
  unit,
  baseUnit,
}: PriceBadgeProps) {
  return (
    <div className="text-right">
      <div
        className="tabular-nums font-mono text-base font-semibold"
        style={{ color: isCheapest ? "#1a6b3c" : "#1a1a1a" }}
      >
        {formatPrice(price)}
        {isCheapest && (
          <span
            className="ml-2 inline-flex items-center rounded-full px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide"
            style={{ backgroundColor: "#dcfce7", color: "#15803d" }}
          >
            Goedkoopst
          </span>
        )}
      </div>
      {pricePerUnit != null && (
        <div className="mt-0.5 text-xs" style={{ color: "#9ca3af" }}>
          {formatPricePerUnit(pricePerUnit, unit, baseUnit)}
        </div>
      )}
    </div>
  );
}
