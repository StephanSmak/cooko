/**
 * Import supermarket data into Supabase and run the matching pipeline.
 *
 * Usage: npx tsx scripts/import-data.ts
 *
 * Steps:
 *   1. Create tables (if not exist) via direct Postgres connection
 *   2. Import all products with normalized names + parsed sizes
 *   3. Match A-brand products (exact, then fuzzy)
 *   4. Match huismerk products (exact, then fuzzy)
 */

import dotenv from "dotenv";
import { readFileSync } from "fs";
import { join } from "path";

// Load .env.local (Next.js convention) then fall back to .env
const root = process.cwd();
dotenv.config({ path: join(root, ".env.local") });
dotenv.config({ path: join(root, ".env") });

import { createClient } from "@supabase/supabase-js";
import postgres from "postgres";
import { normalizeName, removeStopwords } from "../lib/utils/normalize";
import { parseSize } from "../lib/utils/parse-size";
import type { RawSupermarket } from "../lib/types";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const supabaseKey = process.env.SUPABASE_SERVICE_ROLE_KEY!;

const supabase = createClient(supabaseUrl, supabaseKey);

// Direct Postgres connection for schema setup
// Supabase connection string: postgresql://postgres.[project-ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres
// We derive it from the Supabase URL + service role key
function getConnectionString(): string {
  // Check if DATABASE_URL is set directly
  if (process.env.DATABASE_URL) return process.env.DATABASE_URL;

  // Derive from Supabase URL: https://[ref].supabase.co → ref
  const ref = supabaseUrl.replace("https://", "").replace(".supabase.co", "");
  // Default Supabase pooler connection
  return `postgresql://postgres.${ref}:${process.env.SUPABASE_DB_PASSWORD}@aws-0-eu-central-1.pooler.supabase.com:6543/postgres`;
}

// ─── Schema Setup ───────────────────────────────────────────────────────────

async function setupSchema() {
  console.log("Setting up schema...");

  const connectionString = getConnectionString();

  if (!connectionString || connectionString.includes("undefined")) {
    // No direct DB connection — check if tables exist via Supabase REST
    const { error } = await supabase.from("supermarkets").select("id").limit(1);
    if (!error) {
      console.log("Schema already exists (verified via REST). Skipping setup.");
      return;
    }
    console.warn("\nNo DATABASE_URL and tables don't exist yet.");
    console.warn("Either add DATABASE_URL to .env.local, or run this SQL manually:\n");
    printSchemaSQL();
    process.exit(1);
  }

  const sql = postgres(connectionString, { ssl: "require" });

  try {
    await sql.unsafe(`CREATE EXTENSION IF NOT EXISTS pg_trgm`);
    await sql.unsafe(`CREATE EXTENSION IF NOT EXISTS unaccent`);

    await sql.unsafe(`
      CREATE TABLE IF NOT EXISTS supermarkets (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        logo_url TEXT,
        base_url TEXT
      )
    `);

    await sql.unsafe(`
      CREATE TABLE IF NOT EXISTS product_groups (
        id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        canonical_name TEXT NOT NULL,
        match_type TEXT NOT NULL,
        base_unit TEXT,
        base_amount NUMERIC(10,3)
      )
    `);

    await sql.unsafe(`
      CREATE TABLE IF NOT EXISTS products (
        id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        supermarket_id TEXT NOT NULL REFERENCES supermarkets(id),
        raw_name TEXT NOT NULL,
        name_normalized TEXT NOT NULL,
        link TEXT,
        price NUMERIC(8,2) NOT NULL,
        raw_size TEXT,
        quantity NUMERIC(10,3),
        unit TEXT,
        multiplier INT DEFAULT 1,
        total_amount NUMERIC(10,3),
        price_per_unit NUMERIC(10,4),
        is_huismerk BOOLEAN DEFAULT FALSE,
        brand TEXT,
        product_description TEXT,
        product_group_id BIGINT REFERENCES product_groups(id)
      )
    `);

    await sql.unsafe(`CREATE INDEX IF NOT EXISTS idx_products_normalized_trgm ON products USING GIN (name_normalized gin_trgm_ops)`);
    await sql.unsafe(`CREATE INDEX IF NOT EXISTS idx_products_description_trgm ON products USING GIN (product_description gin_trgm_ops)`);
    await sql.unsafe(`CREATE INDEX IF NOT EXISTS idx_products_group ON products(product_group_id)`);
    await sql.unsafe(`CREATE INDEX IF NOT EXISTS idx_products_supermarket ON products(supermarket_id)`);
    await sql.unsafe(`CREATE INDEX IF NOT EXISTS idx_pg_name_trgm ON product_groups USING GIN (canonical_name gin_trgm_ops)`);

    console.log("Schema ready.");
    await sql.end();
  } catch (err) {
    await sql.end();
    console.error("Schema setup failed:", err);
    console.warn("\nIf the connection fails, add DATABASE_URL to .env.local.");
    console.warn("Find it in: Supabase Dashboard → Settings → Database → Connection string (URI)\n");
    printSchemaSQL();
    process.exit(1);
  }
}

function printSchemaSQL() {
  console.log("--- Run this SQL manually in the Supabase SQL Editor ---\n");
  console.log(`CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;

CREATE TABLE IF NOT EXISTS supermarkets (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, logo_url TEXT, base_url TEXT
);

CREATE TABLE IF NOT EXISTS product_groups (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  canonical_name TEXT NOT NULL, match_type TEXT NOT NULL,
  base_unit TEXT, base_amount NUMERIC(10,3)
);

CREATE TABLE IF NOT EXISTS products (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  supermarket_id TEXT NOT NULL REFERENCES supermarkets(id),
  raw_name TEXT NOT NULL, name_normalized TEXT NOT NULL, link TEXT,
  price NUMERIC(8,2) NOT NULL, raw_size TEXT,
  quantity NUMERIC(10,3), unit TEXT, multiplier INT DEFAULT 1,
  total_amount NUMERIC(10,3), price_per_unit NUMERIC(10,4),
  is_huismerk BOOLEAN DEFAULT FALSE, brand TEXT,
  product_description TEXT, product_group_id BIGINT REFERENCES product_groups(id)
);

CREATE INDEX IF NOT EXISTS idx_products_normalized_trgm ON products USING GIN (name_normalized gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_products_description_trgm ON products USING GIN (product_description gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_products_group ON products(product_group_id);
CREATE INDEX IF NOT EXISTS idx_products_supermarket ON products(supermarket_id);
CREATE INDEX IF NOT EXISTS idx_pg_name_trgm ON product_groups USING GIN (canonical_name gin_trgm_ops);`);
  console.log("\n--- End SQL ---");
}

// ─── Data Import ────────────────────────────────────────────────────────────

async function clearData() {
  console.log("Clearing existing data...");
  await supabase.from("products").delete().neq("id", 0);
  await supabase.from("product_groups").delete().neq("id", 0);
  await supabase.from("supermarkets").delete().neq("id", "");
  console.log("Cleared.");
}

async function importData() {
  const filePath = join(root, "data", "supermarkets.json");
  const rawData: RawSupermarket[] = JSON.parse(readFileSync(filePath, "utf-8"));

  // Import supermarkets
  const supermarkets = rawData.map((sm) => ({
    id: sm.n,
    name: sm.c,
    logo_url: sm.i,
    base_url: sm.u,
  }));

  const { error: smError } = await supabase
    .from("supermarkets")
    .upsert(supermarkets);
  if (smError) throw new Error(`Supermarket import failed: ${smError.message}`);
  console.log(`Imported ${supermarkets.length} supermarkets.`);

  // Import products in batches per supermarket
  let totalProducts = 0;

  for (const sm of rawData) {
    if (sm.d.length === 0) continue;

    const products = sm.d.map((p) => {
      const norm = normalizeName(p.n, sm.n);
      const size = parseSize(p.s);
      const pricePerUnit =
        size.totalAmount && size.totalAmount > 0
          ? Math.round((p.p / size.totalAmount) * 10000) / 10000
          : null;

      return {
        supermarket_id: sm.n,
        raw_name: p.n,
        name_normalized: norm.nameNormalized,
        link: p.l,
        price: p.p,
        raw_size: p.s || null,
        quantity: size.quantity,
        unit: size.unit,
        multiplier: size.multiplier,
        total_amount: size.totalAmount,
        price_per_unit: pricePerUnit,
        is_huismerk: norm.isHuismerk,
        brand: norm.brand,
        product_description: norm.productDescription,
      };
    });

    // Supabase has a limit on batch size, insert in chunks of 500
    const BATCH_SIZE = 500;
    for (let i = 0; i < products.length; i += BATCH_SIZE) {
      const batch = products.slice(i, i + BATCH_SIZE);
      const { error } = await supabase.from("products").insert(batch);
      if (error) {
        console.error(
          `Error importing batch ${i}-${i + BATCH_SIZE} for ${sm.c}:`,
          error.message
        );
        throw error;
      }
    }

    totalProducts += products.length;
    console.log(`  ${sm.c}: ${products.length} products imported.`);
  }

  console.log(`Total: ${totalProducts} products imported.`);
}

// ─── Matching Pipeline ──────────────────────────────────────────────────────

class UnionFind {
  parent: Map<number, number> = new Map();

  find(x: number): number {
    if (!this.parent.has(x)) this.parent.set(x, x);
    if (this.parent.get(x) !== x) {
      this.parent.set(x, this.find(this.parent.get(x)!));
    }
    return this.parent.get(x)!;
  }

  union(a: number, b: number) {
    const ra = this.find(a);
    const rb = this.find(b);
    if (ra !== rb) this.parent.set(ra, rb);
  }

  groups(): Map<number, number[]> {
    const result = new Map<number, number[]>();
    for (const id of this.parent.keys()) {
      const root = this.find(id);
      if (!result.has(root)) result.set(root, []);
      result.get(root)!.push(id);
    }
    return result;
  }
}

interface ProductRow {
  id: number;
  supermarket_id: string;
  name_normalized: string;
  product_description: string;
  unit: string | null;
  total_amount: number | null;
  is_huismerk: boolean;
  raw_name: string;
}

async function fetchAllProducts(): Promise<ProductRow[]> {
  const allProducts: ProductRow[] = [];
  const PAGE_SIZE = 1000;
  let from = 0;

  while (true) {
    const { data, error } = await supabase
      .from("products")
      .select(
        "id, supermarket_id, name_normalized, product_description, unit, total_amount, is_huismerk, raw_name"
      )
      .range(from, from + PAGE_SIZE - 1);

    if (error) throw error;
    if (!data || data.length === 0) break;
    allProducts.push(...data);
    if (data.length < PAGE_SIZE) break;
    from += PAGE_SIZE;
  }

  return allProducts;
}

/** Step C Pass 1: Exact A-brand matching */
async function matchABrandsExact(products: ProductRow[]): Promise<{
  uf: UnionFind;
  matched: Set<number>;
}> {
  console.log("Matching A-brands (exact)...");
  const uf = new UnionFind();
  const matched = new Set<number>();

  const aBrands = products.filter((p) => !p.is_huismerk);

  const groups = new Map<string, ProductRow[]>();
  for (const p of aBrands) {
    const key = `${p.name_normalized}|${p.unit ?? ""}|${p.total_amount ?? ""}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(p);
  }

  let matchCount = 0;
  for (const [, group] of groups) {
    const supermarkets = new Set(group.map((p) => p.supermarket_id));
    if (supermarkets.size < 2) continue;

    for (let i = 1; i < group.length; i++) {
      uf.union(group[0].id, group[i].id);
    }
    for (const p of group) matched.add(p.id);
    matchCount++;
  }

  console.log(`  Found ${matchCount} exact A-brand groups.`);
  return { uf, matched };
}

/** Step C Pass 2: Fuzzy A-brand matching via trigram similarity */
async function matchABrandsFuzzy(
  products: ProductRow[],
  uf: UnionFind,
  matched: Set<number>
): Promise<void> {
  console.log("Matching A-brands (fuzzy)...");

  const unmatched = products.filter(
    (p) => !p.is_huismerk && !matched.has(p.id)
  );

  if (unmatched.length === 0) {
    console.log("  No unmatched A-brands to fuzzy match.");
    return;
  }

  const bySize = new Map<string, ProductRow[]>();
  for (const p of unmatched) {
    if (!p.unit || !p.total_amount) continue;
    const key = `${p.unit}|${p.total_amount}`;
    if (!bySize.has(key)) bySize.set(key, []);
    bySize.get(key)!.push(p);
  }

  let fuzzyMatches = 0;
  for (const [, group] of bySize) {
    if (new Set(group.map((p) => p.supermarket_id)).size < 2) continue;

    for (let i = 0; i < group.length; i++) {
      for (let j = i + 1; j < group.length; j++) {
        if (group[i].supermarket_id === group[j].supermarket_id) continue;
        const sim = trigramSimilarity(
          removeStopwords(group[i].name_normalized),
          removeStopwords(group[j].name_normalized)
        );
        if (sim > 0.6) {
          uf.union(group[i].id, group[j].id);
          matched.add(group[i].id);
          matched.add(group[j].id);
          fuzzyMatches++;
        }
      }
    }
  }

  console.log(`  Found ${fuzzyMatches} fuzzy A-brand pairs.`);
}

/** Step D: Match huismerk products by description + size */
async function matchHuismerken(
  products: ProductRow[],
  uf: UnionFind,
  matched: Set<number>
): Promise<void> {
  console.log("Matching huismerken...");

  const huismerken = products.filter((p) => p.is_huismerk);

  // Pass 1: Exact
  const groups = new Map<string, ProductRow[]>();
  for (const p of huismerken) {
    const key = `${p.product_description}|${p.unit ?? ""}|${p.total_amount ?? ""}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(p);
  }

  let exactMatches = 0;
  let fuzzyMatches = 0;

  for (const [, group] of groups) {
    const supermarkets = new Set(group.map((p) => p.supermarket_id));
    if (supermarkets.size < 2) continue;

    for (let i = 1; i < group.length; i++) {
      uf.union(group[0].id, group[i].id);
    }
    for (const p of group) matched.add(p.id);
    exactMatches++;
  }

  console.log(`  Found ${exactMatches} exact huismerk groups.`);

  // Pass 2: Fuzzy
  const unmatchedHuismerken = huismerken.filter((p) => !matched.has(p.id));
  const bySize = new Map<string, ProductRow[]>();
  for (const p of unmatchedHuismerken) {
    if (!p.unit || !p.total_amount) continue;
    const key = `${p.unit}|${p.total_amount}`;
    if (!bySize.has(key)) bySize.set(key, []);
    bySize.get(key)!.push(p);
  }

  for (const [, group] of bySize) {
    if (new Set(group.map((p) => p.supermarket_id)).size < 2) continue;

    for (let i = 0; i < group.length; i++) {
      for (let j = i + 1; j < group.length; j++) {
        if (group[i].supermarket_id === group[j].supermarket_id) continue;
        const sim = trigramSimilarity(
          removeStopwords(group[i].product_description),
          removeStopwords(group[j].product_description)
        );
        if (sim > 0.7) {
          uf.union(group[i].id, group[j].id);
          matched.add(group[i].id);
          matched.add(group[j].id);
          fuzzyMatches++;
        }
      }
    }
  }

  console.log(`  Found ${fuzzyMatches} fuzzy huismerk pairs.`);
}

// ─── Trigram Similarity ─────────────────────────────────────────────────────

function trigrams(s: string): Set<string> {
  const padded = `  ${s} `;
  const result = new Set<string>();
  for (let i = 0; i < padded.length - 2; i++) {
    result.add(padded.slice(i, i + 3));
  }
  return result;
}

function trigramSimilarity(a: string, b: string): number {
  const ta = trigrams(a);
  const tb = trigrams(b);
  let intersection = 0;
  for (const t of ta) {
    if (tb.has(t)) intersection++;
  }
  const union = ta.size + tb.size - intersection;
  return union === 0 ? 0 : intersection / union;
}

// ─── Save Groups ────────────────────────────────────────────────────────────

async function saveGroups(
  products: ProductRow[],
  uf: UnionFind,
  matched: Set<number>
): Promise<void> {
  console.log("Saving product groups...");

  const productMap = new Map(products.map((p) => [p.id, p]));
  const groups = uf.groups();

  const validGroups: { ids: number[]; products: ProductRow[] }[] = [];
  for (const [, ids] of groups) {
    const prods = ids.map((id) => productMap.get(id)!).filter(Boolean);
    const supermarkets = new Set(prods.map((p) => p.supermarket_id));
    if (supermarkets.size >= 2) {
      validGroups.push({ ids, products: prods });
    }
  }

  console.log(`  ${validGroups.length} valid groups (2+ supermarkets).`);

  const BATCH_SIZE = 200;
  for (let i = 0; i < validGroups.length; i += BATCH_SIZE) {
    const batch = validGroups.slice(i, i + BATCH_SIZE);

    const groupRows = batch.map((g) => {
      const canonical = g.products.reduce((best, p) =>
        p.raw_name.length > best.raw_name.length ? p : best
      );
      const hasHuismerk = g.products.some((p) => p.is_huismerk);
      const sampleProduct = g.products[0];

      return {
        canonical_name: canonical.raw_name,
        match_type: hasHuismerk ? "huismerk_equivalent" : "a_brand_exact",
        base_unit: sampleProduct.unit,
        base_amount: sampleProduct.total_amount,
      };
    });

    const { data: insertedGroups, error: gError } = await supabase
      .from("product_groups")
      .insert(groupRows)
      .select("id");

    if (gError) {
      console.error("Error inserting groups:", gError.message);
      continue;
    }

    for (let j = 0; j < batch.length; j++) {
      const groupId = insertedGroups![j].id;
      const productIds = batch[j].ids;

      for (let k = 0; k < productIds.length; k += 100) {
        const subBatch = productIds.slice(k, k + 100);
        await supabase
          .from("products")
          .update({ product_group_id: groupId })
          .in("id", subBatch);
      }
    }

    if ((i + BATCH_SIZE) % 1000 === 0 || i + BATCH_SIZE >= validGroups.length) {
      console.log(
        `  Saved ${Math.min(i + BATCH_SIZE, validGroups.length)}/${validGroups.length} groups...`
      );
    }
  }

  console.log("Groups saved.");
}

// ─── Main ───────────────────────────────────────────────────────────────────

async function main() {
  console.log("=== Spaartje Data Import ===\n");

  await setupSchema();
  await clearData();
  await importData();

  console.log("\nFetching all products for matching...");
  const products = await fetchAllProducts();
  console.log(`Fetched ${products.length} products.`);

  const { uf, matched } = await matchABrandsExact(products);
  await matchABrandsFuzzy(products, uf, matched);
  await matchHuismerken(products, uf, matched);
  await saveGroups(products, uf, matched);

  // Stats
  const { count: groupCount } = await supabase
    .from("product_groups")
    .select("*", { count: "exact", head: true });
  const { count: matchedCount } = await supabase
    .from("products")
    .select("*", { count: "exact", head: true })
    .not("product_group_id", "is", null);
  const { count: totalCount } = await supabase
    .from("products")
    .select("*", { count: "exact", head: true });

  console.log("\n=== Import Complete ===");
  console.log(`Product groups: ${groupCount}`);
  console.log(`Matched products: ${matchedCount}/${totalCount}`);
  console.log(
    `Match rate: ${((matchedCount! / totalCount!) * 100).toFixed(1)}%`
  );
}

main().catch((err) => {
  console.error("Fatal error:", err);
  process.exit(1);
});
