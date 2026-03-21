"use client";

import { useState } from "react";
import type { ProductGroupResult, ProductInGroup } from "@/lib/types";
import { SupermarketBadge } from "./SupermarketBadge";
import { PriceBadge } from "./PriceBadge";

const MATCH_TYPE_LABELS: Record<string, string> = {
  a_brand_exact: "A-merk",
  a_brand_fuzzy: "A-merk (fuzzy)",
  huismerk_equivalent: "Huismerk",
};

function DebugPanel({ product, group }: { product: ProductInGroup; group: ProductGroupResult }) {
  const rows: [string, string | number | null | boolean][] = [
    ["id", product.id],
    ["supermarket_id", product.supermarket_id],
    ["raw_name", product.raw_name],
    ["name_normalized", product.name_normalized],
    ["product_description", product.product_description],
    ["brand", product.brand],
    ["is_huismerk", product.is_huismerk],
    ["raw_size", product.raw_size],
    ["quantity", product.quantity],
    ["unit", product.unit],
    ["multiplier", product.multiplier],
    ["total_amount", product.total_amount],
    ["price", product.price],
    ["price_per_unit", product.price_per_unit],
    ["link", product.link],
    ["group.match_type", group.match_type],
    ["group.base_unit", group.base_unit],
    ["group.base_amount", group.base_amount],
  ];

  return (
    <div
      className="px-5 py-3"
      style={{ backgroundColor: "#fafafa", borderTop: "1px dashed #e5e7eb" }}
    >
      <table className="w-full text-xs" style={{ fontFamily: "var(--font-dm-mono)" }}>
        <tbody>
          {rows.map(([key, val]) => (
            <tr key={key}>
              <td
                className="whitespace-nowrap py-0.5 pr-4 align-top font-medium"
                style={{ color: "#9ca3af", width: "180px" }}
              >
                {key}
              </td>
              <td
                className="break-all py-0.5 align-top"
                style={{
                  color: val === null || val === undefined ? "#d1d5db" : "#374151",
                }}
              >
                {val === null || val === undefined
                  ? "null"
                  : typeof val === "boolean"
                    ? val ? "true" : "false"
                    : String(val)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

interface ProductGroupCardProps {
  group: ProductGroupResult;
}

export function ProductGroupCard({ group }: ProductGroupCardProps) {
  const [expandedId, setExpandedId] = useState<number | null>(null);

  if (!group.products || group.products.length === 0) return null;

  const sorted = [...group.products].sort((a, b) => a.price - b.price);
  const cheapestPrice = sorted[0].price;
  const matchLabel = MATCH_TYPE_LABELS[group.match_type] ?? group.match_type;
  const isHuismerk = group.match_type === "huismerk_equivalent";

  return (
    <article
      className="overflow-hidden rounded-xl border"
      style={{
        borderColor: "#e5e7eb",
        backgroundColor: "#ffffff",
        boxShadow: "0 1px 3px rgba(0,0,0,0.04), 0 1px 2px rgba(0,0,0,0.06)",
      }}
    >
      {/* Card header */}
      <div
        className="flex items-start justify-between gap-3 px-5 py-4"
        style={{ borderBottom: "1px solid #f3f4f6" }}
      >
        <div className="min-w-0 flex-1">
          <h3
            className="truncate text-sm font-semibold leading-snug"
            style={{ color: "#111827", fontFamily: "var(--font-dm-sans)" }}
            title={group.canonical_name}
          >
            {group.canonical_name}
          </h3>
          {group.base_amount && group.base_unit && (
            <p className="mt-0.5 text-xs" style={{ color: "#9ca3af" }}>
              {group.base_unit === "g" || group.base_unit === "ml"
                ? `${group.base_amount}${group.base_unit}`
                : `${group.base_amount} ${group.base_unit}`}
            </p>
          )}
        </div>
        <span
          className="mt-0.5 shrink-0 rounded px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide"
          style={
            isHuismerk
              ? { backgroundColor: "#fef3c7", color: "#92400e" }
              : { backgroundColor: "#eff6ff", color: "#1d4ed8" }
          }
        >
          {matchLabel}
        </span>
      </div>

      {/* Price rows */}
      <div>
        {sorted.map((product, i) => {
          const isCheapest = product.price === cheapestPrice;
          const isExpanded = expandedId === product.id;

          return (
            <div key={product.id}>
              <button
                type="button"
                onClick={() => setExpandedId(isExpanded ? null : product.id)}
                className="flex w-full items-center gap-3 px-5 py-3 text-left transition-colors hover:bg-gray-50"
                style={{
                  borderLeft: isCheapest
                    ? "3px solid #22c55e"
                    : "3px solid transparent",
                  backgroundColor: isExpanded
                    ? "#f3f4f6"
                    : i === 0
                      ? "#f9fffe"
                      : "transparent",
                  borderTop: i > 0 ? "1px solid #f9fafb" : undefined,
                  cursor: "pointer",
                }}
              >
                {/* Supermarket badge */}
                <div className="w-28 shrink-0">
                  <SupermarketBadge
                    id={product.supermarket_id}
                    name={product.supermarket_name}
                    logoUrl={product.supermarket_logo_url}
                    size="sm"
                  />
                </div>

                {/* Product name */}
                <div className="min-w-0 flex-1">
                  <p
                    className="truncate text-xs"
                    style={{ color: "#6b7280" }}
                    title={product.raw_name}
                  >
                    {product.raw_name}
                  </p>
                </div>

                {/* Expand indicator */}
                <div
                  className="shrink-0 text-xs transition-transform"
                  style={{
                    color: "#d1d5db",
                    transform: isExpanded ? "rotate(90deg)" : "rotate(0deg)",
                  }}
                >
                  ▸
                </div>

                {/* Price */}
                <div className="shrink-0">
                  <PriceBadge
                    price={product.price}
                    isCheapest={isCheapest}
                    pricePerUnit={product.price_per_unit}
                    unit={product.unit}
                    baseUnit={group.base_unit}
                  />
                </div>
              </button>

              {/* Debug panel */}
              {isExpanded && <DebugPanel product={product} group={group} />}
            </div>
          );
        })}
      </div>

      {/* Savings callout when multiple supermarkets */}
      {sorted.length > 1 &&
        (() => {
          const mostExpensive = sorted[sorted.length - 1].price;
          const saving = mostExpensive - cheapestPrice;
          if (saving < 0.01) return null;
          return (
            <div
              className="px-5 py-2.5 text-xs"
              style={{
                backgroundColor: "#f0fdf4",
                borderTop: "1px solid #dcfce7",
                color: "#15803d",
              }}
            >
              Bespaar{" "}
              <strong>
                {saving.toLocaleString("nl-NL", {
                  style: "currency",
                  currency: "EUR",
                  minimumFractionDigits: 2,
                })}
              </strong>{" "}
              t.o.v. de duurste optie
            </div>
          );
        })()}
    </article>
  );
}
