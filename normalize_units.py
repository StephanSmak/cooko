"""
normalize_units.py — Parseert Nederlandse eenheidsnotatie en berekent eenheidsprijzen.

Ondersteunt:
  - Gewicht: "225 g", "1 kg", "500 gr", "1,5 kilo", "200 Gram", "100GR"
  - Volume: "1 l", "330 ml", "75 cl", "0,75 l", "1,5 liter", "500 Milliliter"
  - Multipacks: "4 x 330 ml", "6 x 0,33 l", "6-pack 330 ml"
  - Stuks: "4 stuks", "per stuk", "Per 1 st", "Per 4 st"
  - Per-notatie: "Per 200 g", "Per 500 ml", "Per 1000 ml"
  - Speciaal: "48 wasjes", "30 wasbeurten", "100 capsules", "8 rollen"
  - Nederlandse komma: "1,5" → 1.5
"""

import re
from typing import Optional
from config import supabase

BATCH_SIZE = 500

# ---------------------------------------------------------------------------
# Unit aliases → canonical unit
# ---------------------------------------------------------------------------
UNIT_MAP = {
    # Weight
    "g": "g", "gr": "g", "gram": "g",
    "kg": "kg", "kilo": "kg", "kilogram": "kg",
    # Volume
    "ml": "ml", "milliliter": "ml", "mililiters": "ml", "milliliters": "ml",
    "cl": "cl", "centiliter": "cl",
    "l": "l", "liter": "l", "liters": "l",
    # Pieces
    "stuk": "stuk", "stuks": "stuk", "st": "stuk",
}

# Units that represent countable items → treat as "stuk"
PIECE_UNITS = {
    "wasjes", "wasbeurten", "capsules", "tabletten", "tabs",
    "rollen", "zakjes", "vellen", "plakken", "schijven",
    "doekjes", "pads", "porties", "beurten", "meter",
}

# Conversion factors to standard unit (kg, l, or stuk)
CONVERSIONS = {
    "g": (1 / 1000, "per_kg"),
    "kg": (1, "per_kg"),
    "ml": (1 / 1000, "per_liter"),
    "cl": (1 / 100, "per_liter"),
    "l": (1, "per_liter"),
    "stuk": (1, "per_stuk"),
}


def _parse_number(s: str) -> float:
    """Parse a Dutch-style number: '1,5' → 1.5, '1.5' → 1.5."""
    return float(s.replace(",", "."))


def _clean(text: str) -> str:
    """Strip extra info after •, trailing dots, 'ca.' prefix, and normalise whitespace."""
    text = text.split("•")[0].split("|")[0]
    text = text.strip().rstrip(".")
    # Strip "ca." / "circa" prefix (approximate weights)
    text = re.sub(r"^ca\.?\s*", "", text, flags=re.IGNORECASE)
    return text.strip()


def parse_dutch_quantity(size_text: str) -> Optional[dict]:
    """Parseert Nederlandse eenheidsnotatie.

    Returns: {'count': int, 'per_unit': float, 'total': float, 'unit': str}
    of None als niet te parsen.
    """
    if not size_text or not size_text.strip():
        return None

    text = _clean(size_text).strip()
    if not text:
        return None

    text_lower = text.lower()

    # --- "per stuk" / "per pakket" / "per pak" / "per paar" / "per bos" / "per zak" etc. ---
    if text_lower in ("per stuk", "per pakket", "per pak", "per paar", "per pack",
                       "per bos", "per zak", "heel", "los per kilo"):
        if text_lower == "los per kilo":
            return {"count": 1, "per_unit": 1.0, "total": 1.0, "unit": "kg"}
        return {"count": 1, "per_unit": 1.0, "total": 1.0, "unit": "stuk"}

    # --- "per kilo" / "per kg" / "per liter" / "per l" ---
    if text_lower in ("per kilo", "per kg", "per kilogram"):
        return {"count": 1, "per_unit": 1.0, "total": 1.0, "unit": "kg"}
    if text_lower in ("per liter", "per l"):
        return {"count": 1, "per_unit": 1.0, "total": 1.0, "unit": "l"}

    # --- "Per {amount} {unit}" pattern (e.g. "Per 200 g", "Per 4 st") ---
    m = re.match(
        r"^per\s+(\d+[.,]?\d*)\s*([a-zA-Z]+)$", text_lower
    )
    if m:
        amount = _parse_number(m.group(1))
        raw_unit = m.group(2)
        unit = UNIT_MAP.get(raw_unit)
        if unit:
            return {"count": 1, "per_unit": amount, "total": amount, "unit": unit}

    # --- Multipack: "N x {amount} {unit}" ---
    m = re.match(
        r"^(\d+)\s*[x×]\s*(\d+[.,]?\d*)\s*([a-zA-Z]+)",
        text_lower,
    )
    if m:
        count = int(m.group(1))
        per_unit = _parse_number(m.group(2))
        raw_unit = m.group(3)
        unit = UNIT_MAP.get(raw_unit)
        if unit:
            return {"count": count, "per_unit": per_unit, "total": count * per_unit, "unit": unit}

    # --- "N-pack {amount} {unit}" ---
    m = re.match(
        r"^(\d+)-?pack\s+(\d+[.,]?\d*)\s*([a-zA-Z]+)",
        text_lower,
    )
    if m:
        count = int(m.group(1))
        per_unit = _parse_number(m.group(2))
        raw_unit = m.group(3)
        unit = UNIT_MAP.get(raw_unit)
        if unit:
            return {"count": count, "per_unit": per_unit, "total": count * per_unit, "unit": unit}

    # --- Simple: "{amount} {unit}" or "{amount}{unit}" ---
    m = re.match(
        r"^(\d+[.,]?\d*)\s*([a-zA-Z]+)$", text_lower
    )
    if m:
        amount = _parse_number(m.group(1))
        raw_unit = m.group(2)
        unit = UNIT_MAP.get(raw_unit)
        if unit:
            return {"count": 1, "per_unit": amount, "total": amount, "unit": unit}
        # Check piece units (wasjes, rollen, etc.)
        if raw_unit in PIECE_UNITS:
            return {"count": int(amount), "per_unit": 1.0, "total": int(amount), "unit": "stuk"}

    # --- "{count} {piece_unit}" with space, e.g. "20 zakjes" ---
    m = re.match(r"^(\d+)\s+(\w+)$", text_lower)
    if m:
        count = int(m.group(1))
        raw_unit = m.group(2)
        if raw_unit in PIECE_UNITS:
            return {"count": count, "per_unit": 1.0, "total": float(count), "unit": "stuk"}
        unit = UNIT_MAP.get(raw_unit)
        if unit:
            return {"count": 1, "per_unit": float(count), "total": float(count), "unit": unit}

    return None


def calculate_unit_price(price: float, quantity: dict) -> Optional[dict]:
    """Berekent de prijs per standaardeenheid (kg, liter, of stuk).

    Returns: {'unit_price': float, 'unit_price_unit': str} of None.
    """
    if not quantity or quantity["total"] <= 0:
        return None

    unit = quantity["unit"]
    if unit not in CONVERSIONS:
        return None

    factor, unit_label = CONVERSIONS[unit]
    total_in_standard = quantity["total"] * factor

    if total_in_standard <= 0:
        return None

    unit_price = round(price / total_in_standard, 2)
    return {"unit_price": unit_price, "unit_price_unit": unit_label}


# ---------------------------------------------------------------------------
# Database update
# ---------------------------------------------------------------------------

def _get_unparsed_products():
    """Haal producten op waar unit_price IS NULL en size_raw IS NOT NULL.
    Haalt alle kolommen op zodat we een complete row kunnen upserten.
    """
    products = []
    offset = 0
    page_size = 1000
    while True:
        r = (
            supabase.table("retailer_products")
            .select("*")
            .is_("unit_price", "null")
            .neq("size_raw", "")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        products.extend(r.data)
        if len(r.data) < page_size:
            break
        offset += page_size
    return products


def update_all_unit_prices():
    """Parse alle ongeparsde producten en schrijf unit_price terug naar de DB."""
    print("Fetching unparsed products...")
    products = _get_unparsed_products()
    print(f"Found {len(products)} products to parse\n")

    if not products:
        print("Nothing to do.")
        return

    updates = []
    failed_raw = []
    success = 0
    fail = 0

    for prod in products:
        size_raw = prod["size_raw"]
        price = float(prod["current_price"])
        qty = parse_dutch_quantity(size_raw)

        if qty:
            up = calculate_unit_price(price, qty)
            if up:
                # Merge computed fields into the full row for upsert
                row = dict(prod)
                row.update({
                    "unit_price": up["unit_price"],
                    "unit_price_unit": up["unit_price_unit"],
                    "quantity_amount": qty["per_unit"],
                    "quantity_unit": qty["unit"],
                    "quantity_count": qty["count"],
                })
                updates.append(row)
                success += 1
                continue

        fail += 1
        failed_raw.append(size_raw)

    # Batch upsert met on_conflict=id — bevat alle NOT NULL velden
    print(f"Writing {len(updates)} updates to database...")
    for i in range(0, len(updates), BATCH_SIZE):
        batch = updates[i : i + BATCH_SIZE]
        (
            supabase.table("retailer_products")
            .upsert(batch, on_conflict="id")
            .execute()
        )
        done = min(i + BATCH_SIZE, len(updates))
        print(f"  ... {done}/{len(updates)}")

    # --- Samenvatting ---
    print(f"\nDone!")
    print(f"  Succesvol geparsed: {success}")
    print(f"  Niet geparsed:      {fail}")

    if failed_raw:
        from collections import Counter
        top_failed = Counter(failed_raw).most_common(20)
        print(f"\n  Top 20 ongeparsde size_raw waarden:")
        for val, count in top_failed:
            print(f"    {count:>5}x  {repr(val)}")


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

def _test_parser():
    """Test de parser met voorbeelden."""
    test_cases = [
        ("225 g", {"count": 1, "per_unit": 225.0, "total": 225.0, "unit": "g"}),
        ("1,5 l", {"count": 1, "per_unit": 1.5, "total": 1.5, "unit": "l"}),
        ("4 x 330 ml", {"count": 4, "per_unit": 330.0, "total": 1320.0, "unit": "ml"}),
        ("6 x 25 cl", {"count": 6, "per_unit": 25.0, "total": 150.0, "unit": "cl"}),
        ("per stuk", {"count": 1, "per_unit": 1.0, "total": 1.0, "unit": "stuk"}),
        ("48 wasjes", {"count": 48, "per_unit": 1.0, "total": 48.0, "unit": "stuk"}),
        ("500 gr", {"count": 1, "per_unit": 500.0, "total": 500.0, "unit": "g"}),
        ("75 cl", {"count": 1, "per_unit": 75.0, "total": 75.0, "unit": "cl"}),
        ("1 kg", {"count": 1, "per_unit": 1.0, "total": 1.0, "unit": "kg"}),
        ("", None),
        (None, None),
        # Extra real-world cases
        ("Per 200 g", {"count": 1, "per_unit": 200.0, "total": 200.0, "unit": "g"}),
        ("Per 4 st", {"count": 1, "per_unit": 4.0, "total": 4.0, "unit": "stuk"}),
        ("1 Stuks", {"count": 1, "per_unit": 1.0, "total": 1.0, "unit": "stuk"}),
        ("500 Milliliter", {"count": 1, "per_unit": 500.0, "total": 500.0, "unit": "ml"}),
        ("200 Gram", {"count": 1, "per_unit": 200.0, "total": 200.0, "unit": "g"}),
        ("6 x 0,33 l", {"count": 6, "per_unit": 0.33, "total": 1.98, "unit": "l"}),
        ("100GR", {"count": 1, "per_unit": 100.0, "total": 100.0, "unit": "g"}),
        ("1,5 liter", {"count": 1, "per_unit": 1.5, "total": 1.5, "unit": "l"}),
        ("20 zakjes", {"count": 20, "per_unit": 1.0, "total": 20.0, "unit": "stuk"}),
        ("1 Kilogram", {"count": 1, "per_unit": 1.0, "total": 1.0, "unit": "kg"}),
        ("6 x 750 ml \u2022 Zonder doos", {"count": 6, "per_unit": 750.0, "total": 4500.0, "unit": "ml"}),
        # Edge cases: trailing dot
        ("0.75 l.", {"count": 1, "per_unit": 0.75, "total": 0.75, "unit": "l"}),
        ("200 g.", {"count": 1, "per_unit": 200.0, "total": 200.0, "unit": "g"}),
        ("250 g.", {"count": 1, "per_unit": 250.0, "total": 250.0, "unit": "g"}),
        # Edge cases: "ca." prefix
        ("ca. 120 g", {"count": 1, "per_unit": 120.0, "total": 120.0, "unit": "g"}),
        ("ca. 250 g", {"count": 1, "per_unit": 250.0, "total": 250.0, "unit": "g"}),
        ("ca. 400 g", {"count": 1, "per_unit": 400.0, "total": 400.0, "unit": "g"}),
        # Edge cases: "per kilo" / "per liter"
        ("Per kilo", {"count": 1, "per_unit": 1.0, "total": 1.0, "unit": "kg"}),
        ("per liter", {"count": 1, "per_unit": 1.0, "total": 1.0, "unit": "l"}),
        # Edge case: meal kit → None (not parseable as quantity)
        ("4 pers | 25 min", None),
    ]

    print("Running parser tests...\n")
    passed = 0
    failed = 0
    for text, expected in test_cases:
        result = parse_dutch_quantity(text)
        # Round totals for float comparison
        if result and expected:
            result["total"] = round(result["total"], 4)
            expected["total"] = round(expected["total"], 4)
        ok = result == expected
        status = "OK" if ok else "FAIL"
        if not ok:
            print(f"  {status}  {repr(text)}")
            print(f"         expected: {expected}")
            print(f"         got:      {result}")
            failed += 1
        else:
            print(f"  {status}  {repr(text):40s} → {result}")
            passed += 1

    print(f"\n{passed} passed, {failed} failed\n")

    # Test unit price calculation
    print("Unit price examples:")
    examples = [
        (2.49, "225 g"),
        (1.99, "1,5 l"),
        (5.99, "4 x 330 ml"),
        (3.49, "per stuk"),
        (8.99, "0,75 l"),
        (12.99, "1 kg"),
    ]
    for price, size in examples:
        qty = parse_dutch_quantity(size)
        up = calculate_unit_price(price, qty)
        print(f"  €{price:>6.2f}  {size:20s} → {up}")

    return failed == 0


if __name__ == "__main__":
    import sys
    if "--update" in sys.argv:
        update_all_unit_prices()
    else:
        _test_parser()
