"""
export_unknowns.py — Exporteert producten zonder herkend merk naar data/unknowns.json.

Haalt alle retailer_products op waar brand_raw = 'unknown', dedupliceert op
productnaam (case-insensitive), en sorteert op frequentie (vaakst voorkomend eerst).
"""

import json
import os
from collections import defaultdict
from config import supabase

OUTPUT_PATH = "data/unknowns.json"
PAGE_SIZE = 1000


def _get_retailers():
    """Haal alle retailers op als dict {id: slug}."""
    r = supabase.table("retailers").select("id, slug").execute()
    return {row["id"]: row["slug"] for row in r.data}


def _fetch_unknowns():
    """Haal alle producten op waar brand_raw = 'unknown', gepagineerd."""
    rows = []
    offset = 0
    while True:
        r = (
            supabase.table("retailer_products")
            .select("retailer_id, name, size_raw")
            .eq("brand_raw", "unknown")
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        rows.extend(r.data)
        if len(r.data) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return rows


def main():
    print("Fetching retailers...")
    id_to_slug = _get_retailers()

    print("Fetching unknown products...")
    rows = _fetch_unknowns()
    print(f"Total rows: {len(rows)}")

    # Groepeer per genormaliseerde productnaam
    # key = naam lowercase, value = {"name": origineel, "count": int, "retailers": set, "sizes": list}
    groups = defaultdict(lambda: {"name": "", "count": 0, "retailers": set(), "sizes": []})

    for row in rows:
        key = row["name"].strip().lower()
        g = groups[key]
        g["count"] += 1
        if not g["name"]:
            g["name"] = row["name"].strip()
        retailer_slug = id_to_slug.get(row["retailer_id"], row["retailer_id"])
        g["retailers"].add(retailer_slug)
        size = row.get("size_raw", "") or ""
        if size and size not in g["sizes"]:
            g["sizes"].append(size)

    # Sorteer op aantal retailers (primair) en totaal count (secundair)
    sorted_groups = sorted(
        groups.values(),
        key=lambda g: (len(g["retailers"]), g["count"]),
        reverse=True,
    )

    # Serialize (sets → lists)
    output = [
        {
            "name": g["name"],
            "count": g["count"],
            "retailer_count": len(g["retailers"]),
            "retailers": sorted(g["retailers"]),
            "sizes": g["sizes"],
        }
        for g in sorted_groups
    ]

    os.makedirs("data", exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Unieke productnamen: {len(output)}")
    print(f"Totaal rijen:        {len(rows)}")
    print(f"Geschreven naar:     {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
