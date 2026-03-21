import type { ParsedSize } from "../types";

/**
 * Parse a Dutch supermarket size string into structured data.
 *
 * Examples:
 *   "6 x 0,33 l"  → { multiplier: 6, quantity: 330, unit: 'ml', totalAmount: 1980 }
 *   "400 g"        → { multiplier: 1, quantity: 400, unit: 'g', totalAmount: 400 }
 *   "1,5 l"        → { multiplier: 1, quantity: 1500, unit: 'ml', totalAmount: 1500 }
 *   "20 stuks"     → { multiplier: 1, quantity: 20, unit: 'stuks', totalAmount: 20 }
 *   "Per 500 ml"   → { multiplier: 1, quantity: 500, unit: 'ml', totalAmount: 500 }
 *   "1KG"          → { multiplier: 1, quantity: 1000, unit: 'g', totalAmount: 1000 }
 */

const EMPTY: ParsedSize = {
  quantity: null,
  unit: null,
  multiplier: 1,
  totalAmount: null,
};

/** Convert Dutch decimal comma to dot, then parse as float */
function parseNum(s: string): number {
  return parseFloat(s.replace(",", "."));
}

/** Normalize a unit string to base units: ml, g, stuks */
function normalizeUnit(
  raw: string,
  qty: number
): { unit: string; qty: number } {
  const u = raw.toLowerCase().replace(/[.\s]/g, "");
  // Volume
  if (u === "l" || u === "liter" || u === "liters") return { unit: "ml", qty: qty * 1000 };
  if (u === "cl") return { unit: "ml", qty: qty * 10 };
  if (u === "dl") return { unit: "ml", qty: qty * 100 };
  if (u === "ml" || u === "milliliter" || u === "mililiters" || u === "mililiters") return { unit: "ml", qty };
  // Weight
  if (u === "kg" || u === "kilo" || u === "kilogram" || u === "kgrams")
    return { unit: "g", qty: qty * 1000 };
  if (u === "g" || u === "gr" || u === "gram" || u === "grams") return { unit: "g", qty };
  // Count
  if (
    u === "stuks" ||
    u === "stuk" ||
    u === "st" ||
    u === "rollen" ||
    u === "vellen" ||
    u === "zakjes" ||
    u === "capsules" ||
    u === "tabs" ||
    u === "doosjes" ||
    u === "pak"
  )
    return { unit: "stuks", qty };
  // Meters (for things like foil)
  if (u === "m" || u === "meter") return { unit: "m", qty };
  // Unknown
  return { unit: null as unknown as string, qty };
}

export function parseSize(raw: string): ParsedSize {
  if (!raw || !raw.trim()) return EMPTY;

  let s = raw.trim();
  // Remove trailing dots, commas, and extra suffixes like "• Met doos"
  s = s.replace(/•.*$/, "").trim();
  s = s.replace(/,\s*verpakt$/i, "").trim();
  s = s.replace(/[.]+$/, "").trim();

  // Strip leading "Per " (PLUS uses this)
  s = s.replace(/^per\s+/i, "");

  // Pattern: "N x N unit" (multipack) — e.g. "6 x 0,33 l", "4x70 g.", "6x33 cl."
  const multiMatch = s.match(
    /^(\d+)\s*x\s*(\d+(?:[.,]\d+)?)\s*([a-zA-Z.]+)/i
  );
  if (multiMatch) {
    const multiplier = parseInt(multiMatch[1]);
    const qty = parseNum(multiMatch[2]);
    const { unit, qty: normalizedQty } = normalizeUnit(multiMatch[3], qty);
    if (unit) {
      return {
        multiplier,
        quantity: normalizedQty,
        unit,
        totalAmount: Math.round(normalizedQty * multiplier * 100) / 100,
      };
    }
  }

  // Pattern: "N x N stuks" — e.g. "10 x 2 stuks"
  const multiStuks = s.match(/^(\d+)\s*x\s*(\d+)\s*(stuks?|st)/i);
  if (multiStuks) {
    const multiplier = parseInt(multiStuks[1]);
    const qty = parseInt(multiStuks[2]);
    return {
      multiplier,
      quantity: qty,
      unit: "stuks",
      totalAmount: qty * multiplier,
    };
  }

  // Pattern: "N rollen" or similar count units
  const countMatch = s.match(
    /^(\d+)\s*(stuks?|stuk|rollen|vellen|zakjes|capsules|tabs|doosjes|pak)\b/i
  );
  if (countMatch) {
    const qty = parseInt(countMatch[1]);
    return { multiplier: 1, quantity: qty, unit: "stuks", totalAmount: qty };
  }

  // Pattern: "per stuk" / "1 Per stuk" / "1 Stuk"
  if (/^(1\s+)?(per\s+)?stuk$/i.test(s)) {
    return { multiplier: 1, quantity: 1, unit: "stuks", totalAmount: 1 };
  }

  // Pattern: compact Vomar format "330ML", "750G", "1KG", "500GR"
  const compactMatch = s.match(/^(\d+(?:[.,]\d+)?)\s*(ML|GR|G|KG|CL|L)$/i);
  if (compactMatch) {
    const qty = parseNum(compactMatch[1]);
    const { unit, qty: normalizedQty } = normalizeUnit(compactMatch[2], qty);
    if (unit) {
      return {
        multiplier: 1,
        quantity: normalizedQty,
        unit,
        totalAmount: normalizedQty,
      };
    }
  }

  // Pattern: "N,N unit" or "N unit" — e.g. "0,75 l", "400 g", "1.5 liter", "500 milliliter"
  const simpleMatch = s.match(
    /^(\d+(?:[.,]\d+)?)\s+([a-zA-Z]+)/i
  );
  if (simpleMatch) {
    const qty = parseNum(simpleMatch[1]);
    const { unit, qty: normalizedQty } = normalizeUnit(simpleMatch[2], qty);
    if (unit) {
      return {
        multiplier: 1,
        quantity: normalizedQty,
        unit,
        totalAmount: normalizedQty,
      };
    }
  }

  // Pattern: "1 Stuks" (Poiesz style)
  if (/^1\s+stuks?$/i.test(s)) {
    return { multiplier: 1, quantity: 1, unit: "stuks", totalAmount: 1 };
  }

  return EMPTY;
}
