import { supabaseAdmin } from "@/lib/supabase/server";
import type { ProductGroupResult, ProductInGroup } from "@/lib/types";

type RawProductRow = {
  id: number;
  supermarket_id: string;
  raw_name: string;
  name_normalized: string | null;
  raw_size: string | null;
  price: number;
  price_per_unit: number | null;
  unit: string | null;
  quantity: number | null;
  multiplier: number | null;
  total_amount: number | null;
  link: string | null;
  is_huismerk: boolean;
  brand: string | null;
  product_description: string | null;
  supermarkets: {
    id: string;
    name: string;
    logo_url: string | null;
  } | null;
};

type RawGroupRow = {
  id: number;
  canonical_name: string;
  match_type: string;
  base_unit: string | null;
  base_amount: number | null;
  products: RawProductRow[];
};

function flattenGroup(row: RawGroupRow): ProductGroupResult {
  const products: ProductInGroup[] = (row.products ?? []).map((p) => ({
    id: p.id,
    supermarket_id: p.supermarket_id,
    supermarket_name: p.supermarkets?.name ?? p.supermarket_id,
    supermarket_logo_url: p.supermarkets?.logo_url ?? null,
    raw_name: p.raw_name,
    price: p.price,
    price_per_unit: p.price_per_unit,
    unit: p.unit,
    total_amount: p.total_amount,
    link: p.link,
    is_huismerk: p.is_huismerk,
    name_normalized: p.name_normalized,
    raw_size: p.raw_size,
    quantity: p.quantity,
    multiplier: p.multiplier,
    brand: p.brand,
    product_description: p.product_description,
  }));

  return {
    id: row.id,
    canonical_name: row.canonical_name,
    match_type: row.match_type,
    base_unit: row.base_unit,
    base_amount: row.base_amount,
    products,
  };
}

export async function searchProductGroups(
  query: string
): Promise<ProductGroupResult[]> {
  const { data, error } = await supabaseAdmin
    .from("product_groups")
    .select(
      `
      id, canonical_name, match_type, base_unit, base_amount,
      products (
        id, supermarket_id, raw_name, name_normalized, raw_size,
        price, price_per_unit, unit, quantity, multiplier,
        total_amount, link, is_huismerk, brand, product_description,
        supermarkets ( id, name, logo_url )
      )
    `
    )
    .ilike("canonical_name", `%${query}%`)
    .limit(20);

  if (error) {
    console.error("searchProductGroups error:", error);
    return [];
  }

  return ((data as unknown as RawGroupRow[]) ?? []).map(flattenGroup);
}

export async function getProductGroup(
  id: number
): Promise<ProductGroupResult | null> {
  const { data, error } = await supabaseAdmin
    .from("product_groups")
    .select(
      `
      id, canonical_name, match_type, base_unit, base_amount,
      products (
        id, supermarket_id, raw_name, name_normalized, raw_size,
        price, price_per_unit, unit, quantity, multiplier,
        total_amount, link, is_huismerk, brand, product_description,
        supermarkets ( id, name, logo_url )
      )
    `
    )
    .eq("id", id)
    .single();

  if (error || !data) return null;
  return flattenGroup(data as unknown as RawGroupRow);
}
