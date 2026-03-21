/**
 * Product name normalization and huismerk detection for Dutch supermarkets.
 */

/** Known supermarket huismerk prefixes, ordered longest-first to avoid partial matches */
const HUISMERK_PREFIXES: { prefix: string; supermarkets: string[] }[] = [
  { prefix: "Poiesz Noordertrots", supermarkets: ["poiesz"] },
  { prefix: "1 de Beste", supermarkets: ["dirk", "dekamarkt"] },
  { prefix: "AH Excellent", supermarkets: ["ah"] },
  { prefix: "AH Biologisch", supermarkets: ["ah"] },
  { prefix: "AH Basic", supermarkets: ["ah"] },
  { prefix: "AH Terra", supermarkets: ["ah"] },
  { prefix: "G'woon", supermarkets: ["dekamarkt", "hoogvliet", "spar", "poiesz", "vomar"] },
  { prefix: "g'woon", supermarkets: ["dekamarkt", "hoogvliet", "spar", "poiesz", "vomar"] },
  { prefix: "PLUS", supermarkets: ["plus"] },
  { prefix: "Jumbo", supermarkets: ["jumbo"] },
  { prefix: "Spar", supermarkets: ["spar"] },
  { prefix: "AH", supermarkets: ["ah"] },
];

/** No shared brands — g'woon is treated as huismerk across all chains. */
const SHARED_BRANDS: string[] = [];

/**
 * Dutch stopwords to strip before fuzzy matching.
 * These add noise to trigram similarity without contributing to meaning.
 */
const STOPWORDS = new Set([
  "de", "het", "een", "van", "met", "en", "in", "op", "voor", "aan",
  "te", "of", "uit", "bij", "om", "door", "over", "per", "tot", "naar",
  "zonder", "plus", "extra", "new", "new", "original",
]);

/**
 * Common Dutch abbreviations found in supermarket product names.
 * Applied before other normalization steps.
 */
const ABBREVIATIONS: [RegExp, string][] = [
  [/\bhalfv\b\.?/g, "halfvolle"],
  [/\bvollev\b\.?/g, "volle"],
  [/\bnat\b\.?/g, "naturel"],
  [/\bsinaasapp\b\.?/g, "sinaasappel"],
  [/\bsinas\b/g, "sinaasappel"],
  [/\bappels\b/g, "appel"],
  [/\bstraw\b\.?/g, "aardbei"],
  [/\bchoc\b\.?/g, "chocolade"],
  [/\bvanill\b\.?/g, "vanille"],
  [/\bfraich\b\.?/g, "frais"],
  [/\bfr\b\.?/g, "frais"],
  [/\bjogh\b\.?/g, "yoghurt"],
  [/\byog\b\.?/g, "yoghurt"],
  [/\bkip\b/g, "kip"],
  [/\bkipfil\b\.?/g, "kipfilet"],
  [/\bmin\b\.?(?=\s|$)/g, "minuten"],
  [/\bmg\b/g, "mg"],
  [/\bvrij\b/g, "vrij"],
  [/\bo\.a\b\.?/g, ""],
  [/\bca\b\.?/g, ""],
];

interface NormalizationResult {
  nameNormalized: string;
  isHuismerk: boolean;
  brand: string | null;
  productDescription: string;
}

/** Strip diacritics from a string */
function unaccent(s: string): string {
  return s.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
}

/** Expand known abbreviations */
function expandAbbreviations(s: string): string {
  let result = s;
  for (const [pattern, replacement] of ABBREVIATIONS) {
    result = result.replace(pattern, replacement);
  }
  return result;
}

/**
 * Normalize hoeveelheidsnotaties in productnamen zodat variaties consistent zijn.
 * Bijv: "6x33cl" → "6 x 33 cl", "2x200gr" → "2 x 200 gr"
 */
function normalizeQuantityNotation(s: string): string {
  return s
    // "6x33" → "6 x 33"
    .replace(/(\d+)\s*x\s*(\d)/gi, "$1 x $2")
    // "500ml" → "500 ml", "1kg" → "1 kg" (number directly followed by unit)
    .replace(/(\d)(ml|cl|dl|l|gr|g|kg|stuks?|st|m)\b/gi, "$1 $2");
}

/** Clean up a name: lowercase, unaccent, normalize whitespace */
function cleanName(s: string): string {
  return unaccent(s)
    .toLowerCase()
    .replace(/[''`]/g, "'")      // normalize quotes
    .replace(/[-–—]/g, " ")      // dashes to spaces
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * Remove stopwords from a string.
 * Used for fuzzy matching keys, NOT stored in the database.
 */
export function removeStopwords(s: string): string {
  return s
    .split(" ")
    .filter((w) => w.length > 0 && !STOPWORDS.has(w))
    .join(" ");
}

/**
 * Try to detect and strip a huismerk prefix from the product name.
 * Returns the prefix if found, or null.
 */
function detectHuismerkPrefix(
  rawName: string
): { prefix: string; isSharedBrand: boolean } | null {
  for (const { prefix } of HUISMERK_PREFIXES) {
    if (rawName.startsWith(prefix + " ") || rawName === prefix) {
      const isSharedBrand = SHARED_BRANDS.includes(prefix);
      return { prefix, isSharedBrand };
    }
  }
  return null;
}

/**
 * Normalize a product name and detect if it's a huismerk.
 *
 * For A-brand products:
 *   - nameNormalized = cleaned full name
 *   - brand = null (populated during matching phase)
 *   - productDescription = cleaned full name
 *
 * For huismerk products:
 *   - nameNormalized = cleaned full name (including prefix, for exact matching within same chain)
 *   - brand = null
 *   - productDescription = cleaned name WITHOUT supermarket prefix (for cross-chain matching)
 */
export function normalizeName(rawName: string): NormalizationResult {
  const trimmed = rawName.trim();

  // Apply abbreviation expansion and quantity notation normalization before cleaning
  const expanded = expandAbbreviations(normalizeQuantityNotation(trimmed));
  const cleaned = cleanName(expanded);

  // Check for huismerk prefix (on original trimmed name, before expansion)
  const huismerkMatch = detectHuismerkPrefix(trimmed);

  if (huismerkMatch) {
    const descriptionRaw = trimmed.slice(huismerkMatch.prefix.length).trim();
    const description = cleanName(expandAbbreviations(normalizeQuantityNotation(descriptionRaw)));

    if (huismerkMatch.isSharedBrand) {
      return {
        nameNormalized: cleaned,
        isHuismerk: false,
        brand: cleanName(huismerkMatch.prefix),
        productDescription: description,
      };
    }

    return {
      nameNormalized: cleaned,
      isHuismerk: true,
      brand: null,
      productDescription: description,
    };
  }

  return {
    nameNormalized: cleaned,
    isHuismerk: false,
    brand: null,
    productDescription: cleaned,
  };
}
