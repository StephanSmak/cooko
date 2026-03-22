"""
apply_brand_classifications.py — Past AI-classificaties toe op de database.

Leest data/brand_classifications.json en update retailer_products:
  - a-merk  → brand_raw, brand_type, brand_id
  - geen_merk bij Aldi  → brand_raw = "Aldi (huismerk)", brand_type = "huismerk"
  - geen_merk bij Lidl  → brand_raw = "Lidl (huismerk)", brand_type = "huismerk"
  - geen_merk overig    → brand_raw = "geen_merk", brand_type = "geen_merk"
  - is_food = false     → is_available = False
"""

import json
import re
from collections import defaultdict
from config import supabase

CACHE_PATH = "data/brand_classifications.json"
BATCH_SIZE = 500
PAGE_SIZE = 1000


# ---------------------------------------------------------------------------
# Hulpfuncties (zelfde logica als detect_brands.py)
# ---------------------------------------------------------------------------

def _make_slug(brand_name: str) -> str:
    slug = brand_name.lower()
    slug = re.sub(r"['\"]", "", slug)
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def _ensure_brand(brand_name: str, is_store_brand: bool, retailer_id, cache: dict) -> str:
    """Zorg dat merk in brands tabel staat. Retourneert brand_id."""
    key = brand_name.lower()
    if key in cache:
        return cache[key]["id"]

    slug = _make_slug(brand_name)
    r = (
        supabase.table("brands")
        .upsert(
            {
                "name": brand_name,
                "slug": slug,
                "is_store_brand": is_store_brand,
                "retailer_id": retailer_id,
            },
            on_conflict="slug",
        )
        .execute()
    )
    brand_id = r.data[0]["id"]
    cache[key] = {"id": brand_id, "name": brand_name, "slug": slug}
    return brand_id


def _get_existing_brands() -> dict:
    brands = {}
    offset = 0
    while True:
        r = (
            supabase.table("brands")
            .select("id, name, slug")
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        for row in r.data:
            brands[row["name"].lower()] = row
        if len(r.data) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return brands


def _get_unknown_products() -> list:
    """Haal alle retailer_products op waar brand_raw = 'unknown'."""
    products = []
    offset = 0
    while True:
        r = (
            supabase.table("retailer_products")
            .select("*")
            .eq("brand_raw", "unknown")
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        products.extend(r.data)
        if len(r.data) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return products


def _get_brand_totals() -> dict:
    """Haal na de update de aantallen per retailer op (voor samenvatting)."""
    totals = {}
    r = supabase.table("retailers").select("id, slug").execute()
    id_to_slug = {row["id"]: row["slug"] for row in r.data}

    # Tel per brand_type per retailer
    r = (
        supabase.table("retailer_products")
        .select("retailer_id, brand_type")
        .eq("is_available", True)
        .execute()
    )
    counts = defaultdict(lambda: defaultdict(int))
    for row in r.data:
        slug = id_to_slug.get(row["retailer_id"], "?")
        counts[slug][row["brand_type"] or "null"] += 1
    return counts


# ---------------------------------------------------------------------------
# Hoofdfunctie
# ---------------------------------------------------------------------------

def main():
    print("Laden brand_classifications.json...")
    with open(CACHE_PATH, encoding="utf-8") as f:
        classifications: dict = json.load(f)
    print(f"  {len(classifications)} classificaties geladen\n")

    print("Ophalen retailers...")
    r = supabase.table("retailers").select("id, slug").execute()
    id_to_slug = {row["id"]: row["slug"] for row in r.data}
    slug_to_id = {row["slug"]: row["id"] for row in r.data}
    print(f"  {len(id_to_slug)} retailers\n")

    print("Ophalen bestaande merken...")
    brand_cache = _get_existing_brands()
    print(f"  {len(brand_cache)} merken in brands tabel\n")

    print("Ophalen producten met brand_raw = 'unknown'...")
    products = _get_unknown_products()
    print(f"  {len(products)} producten te verwerken\n")

    if not products:
        print("Niets te doen.")
        return

    # Zorg dat Aldi / Lidl generieke huismerk-entries bestaan in brands tabel
    aldi_brand_id = _ensure_brand(
        "Aldi (huismerk)", True, slug_to_id.get("aldi"), brand_cache
    )
    lidl_brand_id = _ensure_brand(
        "Lidl (huismerk)", True, slug_to_id.get("lidl"), brand_cache
    )

    updates = []
    stats = defaultdict(lambda: {
        "total": 0, "a_merk": 0, "huismerk": 0,
        "geen_merk": 0, "non_food": 0, "not_in_cache": 0,
    })

    for prod in products:
        slug = id_to_slug.get(prod["retailer_id"], "unknown")
        key = prod["name"].strip().lower()
        s = stats[slug]
        s["total"] += 1

        clf = classifications.get(key)
        if clf is None:
            s["not_in_cache"] += 1
            continue  # niet in cache → ongewijzigd laten

        is_food = clf.get("is_food", True)
        brand_type = clf.get("brand_type", "geen_merk")
        brand_name = clf.get("brand_name", "GEEN")

        row = dict(prod)

        # --- Non-food (cadeaukaarten, vouchers, etc.) → verberg product ---
        if not is_food:
            row["is_available"] = False
            s["non_food"] += 1
            updates.append(row)
            continue

        # --- A-merk ---
        if brand_type == "a-merk" and brand_name and brand_name != "GEEN":
            brand_id = _ensure_brand(brand_name, False, None, brand_cache)
            row.update({
                "brand_raw": brand_name,
                "brand_type": "a-merk",
                "brand_id": brand_id,
            })
            s["a_merk"] += 1
            updates.append(row)
            continue

        # --- Geen merk ---
        if brand_type == "geen_merk":
            if slug == "aldi":
                row.update({
                    "brand_raw": "Aldi (huismerk)",
                    "brand_type": "huismerk",
                    "brand_id": aldi_brand_id,
                })
                s["huismerk"] += 1
            elif slug == "lidl":
                row.update({
                    "brand_raw": "Lidl (huismerk)",
                    "brand_type": "huismerk",
                    "brand_id": lidl_brand_id,
                })
                s["huismerk"] += 1
            else:
                row.update({
                    "brand_raw": "geen_merk",
                    "brand_type": "geen_merk",
                })
                s["geen_merk"] += 1
            updates.append(row)
            continue

        # --- Huismerk (AI vond een huismerk dat detect_brands.py miste) ---
        if brand_type == "huismerk" and brand_name and brand_name != "GEEN":
            brand_id = _ensure_brand(
                brand_name, True, slug_to_id.get(slug), brand_cache
            )
            row.update({
                "brand_raw": brand_name,
                "brand_type": "huismerk",
                "brand_id": brand_id,
            })
            s["huismerk"] += 1
            updates.append(row)
            continue

        # Vangnet: merk is "GEEN" of onbekend type → geen_merk
        row.update({"brand_raw": "geen_merk", "brand_type": "geen_merk"})
        s["geen_merk"] += 1
        updates.append(row)

    # --- Batch upsert ---
    print(f"Schrijven {len(updates)} updates naar database...")
    for i in range(0, len(updates), BATCH_SIZE):
        batch = updates[i : i + BATCH_SIZE]
        supabase.table("retailer_products").upsert(batch, on_conflict="id").execute()
        done = min(i + BATCH_SIZE, len(updates))
        print(f"  ... {done}/{len(updates)}")

    # --- Samenvatting: deze run ---
    print(f"\n{'=' * 72}")
    print("DEZE RUN — VERWERKTE PRODUCTEN")
    print(f"{'=' * 72}")
    print(
        f"{'Supermarkt':<15} {'Totaal':>7} {'A-merk':>7} {'Huismrk':>8} "
        f"{'GeenMrk':>8} {'Non-food':>9} {'N/A cache':>10}"
    )
    print("-" * 72)

    run_totals = defaultdict(int)
    for slug in sorted(stats.keys()):
        s = stats[slug]
        print(
            f"{slug:<15} {s['total']:>7} {s['a_merk']:>7} {s['huismerk']:>8} "
            f"{s['geen_merk']:>8} {s['non_food']:>9} {s['not_in_cache']:>10}"
        )
        for k, v in s.items():
            run_totals[k] += v

    print("-" * 72)
    print(
        f"{'TOTAAL':<15} {run_totals['total']:>7} {run_totals['a_merk']:>7} "
        f"{run_totals['huismerk']:>8} {run_totals['geen_merk']:>8} "
        f"{run_totals['non_food']:>9} {run_totals['not_in_cache']:>10}"
    )

    # --- Samenvatting: totale DB-stand ---
    print(f"\n{'=' * 72}")
    print("TOTALE MERKDEKKING IN DATABASE (is_available = true)")
    print(f"{'=' * 72}")
    print(f"{'Supermarkt':<15} {'a-merk':>8} {'huismerk':>9} {'geen_merk':>10} "
          f"{'unknown':>8} {'null':>6} {'Totaal':>8}")
    print("-" * 72)

    db_counts = _get_brand_totals()
    grand = defaultdict(int)
    for slug in sorted(db_counts.keys()):
        c = db_counts[slug]
        total = sum(c.values())
        a = c.get("a-merk", 0)
        huis = c.get("huismerk", 0)
        geen = c.get("geen_merk", 0)
        unk = c.get("unknown", 0)
        null = c.get("null", 0)
        print(
            f"{slug:<15} {a:>8} {huis:>9} {geen:>10} {unk:>8} {null:>6} {total:>8}"
        )
        grand["a_merk"] += a
        grand["huismerk"] += huis
        grand["geen_merk"] += geen
        grand["unknown"] += unk
        grand["null"] += null
        grand["total"] += total

    print("-" * 72)
    print(
        f"{'TOTAAL':<15} {grand['a_merk']:>8} {grand['huismerk']:>9} "
        f"{grand['geen_merk']:>10} {grand['unknown']:>8} {grand['null']:>6} "
        f"{grand['total']:>8}"
    )

    known = grand["a_merk"] + grand["huismerk"] + grand["geen_merk"]
    if grand["total"]:
        pct = known * 100 / grand["total"]
        print(f"\nMerkdekking (excl. unknown/null): {known}/{grand['total']} ({pct:.1f}%)")


if __name__ == "__main__":
    main()
