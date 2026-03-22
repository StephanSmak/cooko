"""
ingest.py — Leest de JSON feed en synchroniseert producten naar Supabase.

Per supermarkt:
  1. Zoek retailer_id op via slug
  2. Haal bestaande producten op (external_id → id, current_price)
  3. Vergelijk feed met DB:
     - Nieuw product → insert
     - Prijs gewijzigd → update + price_history
     - Prijs gelijk → alleen last_seen_at updaten
  4. Producten in DB maar niet in feed → is_available = false
"""

import json
from datetime import datetime, timezone
from config import supabase

FEED_PATH = "data/supermarkets.json"
BATCH_SIZE = 500  # Supabase max per request


def load_feed():
    with open(FEED_PATH) as f:
        return json.load(f)


def get_retailers():
    """Haal alle retailers op als dict {slug: id}."""
    r = supabase.table("retailers").select("id, slug").execute()
    return {row["slug"]: row["id"] for row in r.data}


def get_existing_products(retailer_id):
    """Haal alle bestaande producten op voor een retailer.
    Returns dict {external_id: {id, current_price, is_available}}.
    Paginates per 1000 rows (Supabase default limit).
    """
    products = {}
    offset = 0
    page_size = 1000
    while True:
        r = (
            supabase.table("retailer_products")
            .select("id, external_id, current_price, is_available")
            .eq("retailer_id", retailer_id)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        for row in r.data:
            products[row["external_id"]] = {
                "id": row["id"],
                "current_price": float(row["current_price"]),
                "is_available": row["is_available"],
            }
        if len(r.data) < page_size:
            break
        offset += page_size
    return products


def batch_upsert(table, rows, on_conflict=None):
    """Upsert in batches van BATCH_SIZE."""
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        if on_conflict:
            supabase.table(table).upsert(batch, on_conflict=on_conflict).execute()
        else:
            supabase.table(table).upsert(batch).execute()


def batch_update(table, rows):
    """Update rows in batches (each row must have its primary key)."""
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        supabase.table(table).upsert(batch).execute()


def process_supermarket(slug, products_feed, retailer_id):
    """Verwerk alle producten van één supermarkt. Returnt stats dict."""
    now = datetime.now(timezone.utc).isoformat()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    existing = get_existing_products(retailer_id)
    feed_external_ids = set()

    new_rows = []
    updated_rows = []
    unchanged_ids = []
    price_history_rows = []

    for product in products_feed:
        ext_id = product["l"]
        name = product["n"]
        price = float(product["p"])
        size_raw = product.get("s", "")
        feed_external_ids.add(ext_id)

        if ext_id in existing:
            ex = existing[ext_id]
            if abs(ex["current_price"] - price) < 0.001:
                # Zelfde prijs → alleen last_seen_at updaten
                unchanged_ids.append(ex["id"])
            else:
                # Prijs gewijzigd → update + price_history
                updated_rows.append(
                    {
                        "id": ex["id"],
                        "current_price": price,
                        "name": name,
                        "size_raw": size_raw,
                        "is_available": True,
                        "last_seen_at": now,
                    }
                )
                price_history_rows.append(
                    {
                        "retailer_product_id": ex["id"],
                        "price": price,
                        "recorded_date": today,
                    }
                )
        else:
            # Nieuw product
            new_rows.append(
                {
                    "retailer_id": retailer_id,
                    "external_id": ext_id,
                    "name": name,
                    "current_price": price,
                    "size_raw": size_raw,
                    "is_available": True,
                }
            )

    # --- Batch writes ---

    # 1. Insert nieuwe producten
    if new_rows:
        batch_upsert("retailer_products", new_rows, on_conflict="retailer_id,external_id")
        print(f"  [{slug}] Inserted {len(new_rows)} new products")

        # Haal IDs op van zojuist ingevoegde producten voor price_history
        new_products = get_existing_products(retailer_id)
        for row in new_rows:
            ext_id = row["external_id"]
            if ext_id in new_products:
                price_history_rows.append(
                    {
                        "retailer_product_id": new_products[ext_id]["id"],
                        "price": row["current_price"],
                        "recorded_date": today,
                    }
                )

    # 2. Update gewijzigde producten
    if updated_rows:
        batch_update("retailer_products", updated_rows)
        print(f"  [{slug}] Updated {len(updated_rows)} products (price changed)")

    # 3. Update last_seen_at voor ongewijzigde producten
    if unchanged_ids:
        for i in range(0, len(unchanged_ids), BATCH_SIZE):
            batch = unchanged_ids[i : i + BATCH_SIZE]
            (
                supabase.table("retailer_products")
                .update({"last_seen_at": now})
                .in_("id", batch)
                .execute()
            )
        print(f"  [{slug}] Touched {len(unchanged_ids)} unchanged products (last_seen_at)")

    # 4. Schrijf price_history
    if price_history_rows:
        batch_upsert("price_history", price_history_rows)
        print(f"  [{slug}] Wrote {len(price_history_rows)} price_history records")

    # 5. Markeer verdwenen producten als niet beschikbaar
    disappeared = [
        eid for eid, data in existing.items()
        if eid not in feed_external_ids and data["is_available"]
    ]
    if disappeared:
        disappeared_ids = [existing[eid]["id"] for eid in disappeared]
        for i in range(0, len(disappeared_ids), BATCH_SIZE):
            batch = disappeared_ids[i : i + BATCH_SIZE]
            (
                supabase.table("retailer_products")
                .update({"is_available": False})
                .in_("id", batch)
                .execute()
            )
        print(f"  [{slug}] Marked {len(disappeared)} products as unavailable")

    return {
        "total": len(products_feed),
        "new": len(new_rows),
        "updated": len(updated_rows),
        "unchanged": len(unchanged_ids),
        "removed": len(disappeared),
    }


def main():
    print("Loading feed...")
    feed = load_feed()
    retailers = get_retailers()

    print(f"Found {len(feed)} supermarkets in feed, {len(retailers)} retailers in DB\n")

    summary = {}
    for supermarket in feed:
        slug = supermarket["n"]
        products = supermarket["d"]

        if slug not in retailers:
            print(f"⚠ WARNING: '{slug}' not found in retailers table — skipping {len(products)} products")
            continue

        retailer_id = retailers[slug]
        print(f"Processing {slug} ({len(products)} products)...")
        stats = process_supermarket(slug, products, retailer_id)
        summary[slug] = stats

    # --- Samenvatting ---
    print("\n" + "=" * 60)
    print("SAMENVATTING")
    print("=" * 60)
    print(f"{'Supermarkt':<15} {'Totaal':>8} {'Nieuw':>8} {'Updated':>8} {'Removed':>8}")
    print("-" * 60)
    for slug, stats in summary.items():
        print(
            f"{slug:<15} {stats['total']:>8} {stats['new']:>8} "
            f"{stats['updated']:>8} {stats['removed']:>8}"
        )
    total = {k: sum(s[k] for s in summary.values()) for k in ["total", "new", "updated", "removed"]}
    print("-" * 60)
    print(
        f"{'TOTAAL':<15} {total['total']:>8} {total['new']:>8} "
        f"{total['updated']:>8} {total['removed']:>8}"
    )


if __name__ == "__main__":
    main()
