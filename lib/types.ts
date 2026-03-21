// Raw JSON structure from supermarkets.json
export interface RawSupermarket {
  n: string; // id: 'ah', 'jumbo', etc.
  d: RawProduct[];
  c: string; // display name: 'AH', 'Jumbo'
  u: string; // base URL for product links
  i: string; // logo URL
}

export interface RawProduct {
  n: string; // product name
  l: string; // link/identifier
  p: number; // price
  s: string; // size string
}

// Parsed/normalized structures
export interface ParsedSize {
  quantity: number | null;
  unit: string | null; // 'ml', 'g', 'stuks'
  multiplier: number;
  totalAmount: number | null; // quantity * multiplier
}

export interface NormalizedProduct {
  supermarketId: string;
  rawName: string;
  nameNormalized: string;
  link: string;
  price: number;
  rawSize: string;
  quantity: number | null;
  unit: string | null;
  multiplier: number;
  totalAmount: number | null;
  pricePerUnit: number | null;
  isHuismerk: boolean;
  brand: string | null;
  productDescription: string; // name without brand/supermarket prefix
}

export interface ProductGroup {
  id: number;
  canonicalName: string;
  matchType: "a_brand_exact" | "a_brand_fuzzy" | "huismerk_equivalent";
  baseUnit: string | null;
  baseAmount: number | null;
}

// UI types for the frontend
export interface ProductInGroup {
  id: number;
  supermarket_id: string;
  supermarket_name: string;
  supermarket_logo_url: string | null;
  raw_name: string;
  price: number;
  price_per_unit: number | null;
  unit: string | null;
  total_amount: number | null;
  link: string | null;
  is_huismerk: boolean;
  // Debug / raw fields
  name_normalized: string | null;
  raw_size: string | null;
  quantity: number | null;
  multiplier: number | null;
  brand: string | null;
  product_description: string | null;
}

export interface ProductGroupResult {
  id: number;
  canonical_name: string;
  match_type: string;
  base_unit: string | null;
  base_amount: number | null;
  products: ProductInGroup[];
}
