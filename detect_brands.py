"""
detect_brands.py — Merkdetectie voor Nederlandse supermarktproducten.

Detecteert merken in productnamen via drie niveaus:
  1. Prefix-matching: huismerken die als prefix in de naam staan (AH, Jumbo, etc.)
  2. Standalone huismerken: retailer-specifieke merken (Milbona, g'woon, etc.)
  3. A-merken: bekende nationale/internationale merken (Coca-Cola, Heineken, etc.)

Vereiste DB-kolommen op retailer_products:
  - brand_raw (text)        — gedetecteerd merknaam
  - brand_type (text)       — 'huismerk' of 'a-merk'
  - brand_id (uuid, FK)     — verwijst naar brands.id

Vereiste brands tabel:
  - id (uuid, PK, auto)
  - name (text, unique)
  - brand_type (text)
"""

import re
from typing import Optional
from config import supabase

BATCH_SIZE = 500


# ---------------------------------------------------------------------------
# 1. STORE_PREFIX_BRANDS — merken die als prefix in de productnaam staan
# ---------------------------------------------------------------------------
# (prefix_lower, brand_name, brand_type) — wordt gesorteerd langste eerst
_PREFIX_BRANDS_RAW = [
    # AH sub-brands
    ("ah biologisch ", "AH Biologisch", "huismerk"),
    ("ah excellent ", "AH Excellent", "huismerk"),
    ("ah terra ", "AH Terra", "huismerk"),
    ("ah prijsfavorieten ", "AH Prijsfavorieten", "huismerk"),
    ("ah ", "AH", "huismerk"),
    # Jumbo
    ("jumbo's ", "Jumbo's", "huismerk"),
    ("jumbo ", "Jumbo", "huismerk"),
    # Plus
    ("plus ", "Plus", "huismerk"),
    # Ekoplaza
    ("ekoplaza ", "Ekoplaza", "huismerk"),
    # Superunie-formules (prefix)
    ("dekamarkt ", "Dekamarkt", "huismerk"),
    ("hoogvliet ", "Hoogvliet", "huismerk"),
    ("poiesz ", "Poiesz", "huismerk"),
    ("spar ", "Spar", "huismerk"),
    ("vomar ", "Vomar", "huismerk"),
]
# Sorteer langste prefix eerst voor correcte matching
STORE_PREFIX_BRANDS = sorted(_PREFIX_BRANDS_RAW, key=lambda x: len(x[0]), reverse=True)


# ---------------------------------------------------------------------------
# 2. STANDALONE_STORE_BRANDS — huismerken per retailer (keten)
# ---------------------------------------------------------------------------

LIDL_BRANDS = [
    "Milbona", "Freeway", "Solevita", "Snack Day", "Combino", "Kania",
    "Freshona", "Baresa", "Chef Select", "Deluxe", "Favorina", "Dulano",
    "Bellarom", "Sondey", "Crownfield", "Belbake", "Fin Carré",
    "J.D. Gross", "Mister Choc", "Alesto", "Ocean Sea", "Nixe",
    "Trattoria Alfredo", "Vitasia", "Eridanous", "McEnnedy", "El Tequito",
    "Lord Nelson", "Perlenbacher", "Gelatelli", "Vemondo", "Cien", "W5",
    "Formil", "Floralys", "Dentalux", "Pilos", "Biotrend", "Vita D'or",
    "Oaklands", "Lupilu", "Silvercrest", "Parkside", "Crivit", "Riviera",
]

ALDI_BRANDS = [
    "Milsani", "Molenland", "Golden Mill", "River", "Golden Power",
    "Schultenbräu", "Lacura", "Biocura", "Ombia", "Mamia", "Bebino",
    "Choceur", "Moser Roth", "Specially Selected", "Bakkersgoud",
    "Goud Gebakken", "Heerlijck Banket", "Grandessa", "Snackrite",
    "Snackfan", "Casa Barelli", "Cucina", "UNA", "Barissimo", "Moreno",
    "Cowbelle", "Nature's Pick", "The Fishmonger", "Golden Seafood",
    "Ashfield Farm", "MYVAY", "Gut Bio", "Freshlife", "All Seasons",
    "Mama Mancini", "Goedland", "Kraax", "FAIR",
]

DIRK_BRANDS = ["1 de Beste", "Vleeschmeesters", "Wijko"]

DEKAMARKT_BRANDS = ["1 de Beste", "DekaVers"]

# Superunie shared brands (g'woon, Melkan, etc.)
SUPERUNIE_BRANDS = [
    "g'woon", "Melkan", "First Choice", "Bio+", "Bonbébé", "Sum & Sam",
    "Daily Chef",
]

AH_STANDALONE_BRANDS = [
    "Perla", "Delicata", "De Zaanse Hoeve", "AH Zaanlander", "Brouwers", "Care",
]

JUMBO_STANDALONE_BRANDS = [
    "Euromerk", "La Place", "Veggie Chef", "Dors",
]

# Retailer-specifieke merken
_RETAILER_BRANDS = {
    "lidl": LIDL_BRANDS,
    "aldi": ALDI_BRANDS,
    "dirk": DIRK_BRANDS,
    "dekamarkt": DEKAMARKT_BRANDS,
    "ah": AH_STANDALONE_BRANDS,
    "jumbo": JUMBO_STANDALONE_BRANDS,
}

SUPERUNIE_SLUGS = {
    "plus", "dirk", "dekamarkt", "hoogvliet", "vomar", "poiesz", "spar",
}


# ---------------------------------------------------------------------------
# 3. A_MERKEN — bekende nationale/internationale merken
# ---------------------------------------------------------------------------
A_MERKEN = [
    # Frisdrank & dranken
    "Coca-Cola", "Pepsi", "Fanta", "Sprite", "Schweppes", "Fernandes",
    "Ranja", "Rivella", "Red Bull", "Monster", "Appelsientje", "Spa", "Sourcy",
    # Bier — Nederlands
    "Heineken", "Hertog Jan", "Grolsch", "Amstel", "Brand", "Jupiler",
    "Bavaria", "Alfa", "Jopen", "Texels", "De Klok", "Gulpener",
    # Bier — Belgisch & speciaal
    "Leffe", "Affligem", "Karmeliet", "Duvel", "La Chouffe", "Chouffe",
    "Hoegaarden", "Liefmans", "Chimay", "Omer", "Vedett", "Palm",
    "Brugse Zot", "La Trappe", "Gulden Draak", "Brewdog",
    "Straffe Hendrik",
    # Bier — Internationaal
    "Birra Moretti", "Desperados", "Stella Artois", "Corona", "Budweiser",
    "Bud", "Heineken", "Carlsberg",
    # Frisdrank & dranken
    "Coca-Cola", "Pepsi", "Fanta", "Sprite", "7Up", "7-Up", "Schweppes",
    "Fernandes", "Ranja", "Rivella", "Red Bull", "Monster", "Fuze Tea",
    "Arizona", "Appelsientje", "Spa", "Sourcy", "Sisi", "Taksi",
    "Apple Bandit", "Crystal Clear", "AA Drink", "Dr Pepper",
    "Innocent", "Tropicana", "CoolBest", "Go-Tan", "Oasis", "Sportlife",
    # Water & mixers
    "Evian", "Bar-le-duc", "Royal Club", "Fever-Tree", "San Pellegrino",
    # Sterke drank & wijn
    "Bacardi", "Malibu", "Jägermeister", "Jagermeister", "Baileys", "Bailey's",
    "Jameson", "Jack Daniel's", "Johnnie Walker", "Smirnoff", "Absolut",
    "Captain Morgan", "Famous Grouse", "Glen Talloch", "Ballantine's",
    "Disaronno", "Sonnema", "Licor 43", "Starbucks",
    # Wijn (premium labels)
    "Antinori", "Marqués de Caceres",
    # Koffie & thee
    "Douwe Egberts", "Nescafé", "Senseo", "L'OR", "Lavazza", "Illy",
    "Van Nelle", "Lipton", "Clipper",
    # Zuivel & vegan zuivel
    "Campina", "Melkunie", "Optimel", "Chocomel", "Friesche Vlag", "Vifit",
    "Almhof", "Danone", "Activia", "Actimel", "Alpro", "Oatly", "Beemster",
    "Arla", "Dodoni", "Fristi", "Skyr",
    # Margarine/vetten & olijfolie
    "Blue Band", "Becel", "Bertolli", "Carapelli", "Carbonell",
    # Chips & snacks
    "Lay's", "Doritos", "Pringles", "Cheetos", "Duyvis", "TUC",
    "Chio", "Croky",
    # Koek & chocolade & snoep & ijs
    "Bolletje", "Peijnenburg", "Verkade", "Liga", "Sultana", "Lu", "Lotus",
    "Sondey", "Nutella", "Milka", "Toblerone", "Haribo", "Venco", "Klene",
    "Tony's Chocolonely", "Duo Penotti", "Heks'nkaas", "M&M's", "M&M",
    "Skittles", "Twix", "Snickers", "Mars", "Bounty", "Kinder",
    "Ben & Jerry's", "Mentos", "Katja", "Celebrations",
    # Ontbijt & beleg & babyvoeding
    "De Ruijter", "Venz", "Kellogg's", "Nestlé", "Nutrilon", "Olvarit",
    "Organix",
    # Sauzen & kruidenierswaren
    "Heinz", "Remia", "Gouda's Glorie", "Devos & Lemmens", "Tabasco",
    "Calvé", "Knorr", "Honig", "Maggi", "Grand'Italia", "Grand' Italia", "Grand Italia",
    "Chicken Tonight", "Conimex", "Koopmans", "Hero", "Dr. Oetker",
    "Hellmann's", "Bonduelle", "Kikkoman", "Hela", "Del Monte",
    "Kühne", "Van Gilse", "Rio Mare",
    # Kruiden & specerijen & sauzen
    "Silvo", "Verstegen", "Inproba", "Go-Tan",
    # Vlees & vis & vleeswaren
    "Mora", "Kwekkeboom", "Van Dobben", "Struik", "Hak", "Iglo", "Aviko",
    "McCain", "Johma", "Unox", "Kips",
    # Kaas & smeerkaas
    "Leerdammer", "Old Amsterdam", "Apetina", "Boursin", "Brie",
    "Président", "Philadelphia",
    # Vega
    "Vivera", "De Vegetarische Slager", "Garden Gourmet", "Beyond Meat",
    # Huisdierenvoer
    "Whiskas", "Gourmet", "Felix", "Pedigree", "Purina", "Friskies", "Iams",
    # Huishouden
    "Robijn", "Ariel", "Persil", "Dreft", "Vanish", "Glorix", "Ajax", "CIF",
    "Biotex", "Finish", "Domestos", "Dettol", "Lenor", "Ambi Pur", "Bolsius",
    "Sun", "Witte Reus", "Air Wick", "Airwick", "Astonish", "Page", "Zewa",
    # Persoonlijke verzorging & farmaceutisch
    "Pampers", "Gillette", "Always", "Oral-B", "Dove", "Andrélon", "Nivea",
    "Zwitsal", "Head & Shoulders", "L'Oréal", "Tena", "Rennie",
    "Hansaplast", "Axe", "Fixodent", "Imodium", "Canesten", "Bepanthen",
    # Techniek & overig
    "Varta",
]
# Sorteer langste eerst voor correcte matching
A_MERKEN.sort(key=len, reverse=True)


# ---------------------------------------------------------------------------
# Brand → owning retailer mapping (voor brands.retailer_id)
# ---------------------------------------------------------------------------

def _get_brand_retailer_slug(brand_name):
    """Retourneert de eigenaar-retailer slug van een merk, of None als gedeeld/a-merk."""
    # Prefix brands: slug afleiden uit prefix
    for prefix, name, _ in STORE_PREFIX_BRANDS:
        if name == brand_name:
            first_word = prefix.strip().split()[0]
            return first_word  # "ah", "jumbo", "plus", "spar", etc.

    # Gedeelde Superunie merken → geen enkele eigenaar
    if brand_name in SUPERUNIE_BRANDS:
        return None

    # Retailer-specifieke standalone merken
    for slug, brands in _RETAILER_BRANDS.items():
        if brand_name in brands:
            return slug  # "lidl", "aldi", "dirk", "ah", "jumbo"

    return None  # A-merk of onbekend


def _make_slug(brand_name):
    """Genereert een URL-vriendelijke slug van een merknaam."""
    slug = brand_name.lower()
    slug = re.sub(r"['\"]", "", slug)           # apostrof / aanhalingstekens verwijderen
    slug = re.sub(r"[^a-z0-9]+", "-", slug)    # niet-alphanumeriek → koppelteken
    return slug.strip("-")


# ---------------------------------------------------------------------------
# Tekst-normalisatie — curly quotes → standaard apostrof
# ---------------------------------------------------------------------------
_APOS_TABLE = str.maketrans({
    '\u2019': "'",   # ' rechts enkel aanhalingsteken
    '\u2018': "'",   # ' links enkel aanhalingsteken
    '\u02bc': "'",   # ʼ modifier letter apostrophe
    '\u0060': "'",   # ` grave accent
    '\u00b4': "'",   # ´ acute accent
})


def _normalize(text):
    """Vervangt curly apostrofen door standaard apostrof."""
    return text.translate(_APOS_TABLE)


# ---------------------------------------------------------------------------
# Pattern cache — compileert regex patronen eenmalig
# ---------------------------------------------------------------------------
_PATTERN_CACHE = {}


def _get_pattern(brand_name):
    """Geeft een gecompileerd regex patroon voor woordgrens-matching."""
    if brand_name not in _PATTERN_CACHE:
        escaped = re.escape(brand_name)
        # Als merk eindigt op niet-woordkarakter (bv. Bio+), gebruik lookahead
        if not re.match(r'\w', brand_name[-1]):
            pattern = re.compile(r'\b' + escaped + r'(?=\s|$)', re.IGNORECASE)
        else:
            pattern = re.compile(r'\b' + escaped + r'\b', re.IGNORECASE)
        _PATTERN_CACHE[brand_name] = pattern
    return _PATTERN_CACHE[brand_name]


def _get_store_brands(retailer_slug):
    """Geeft de lijst standalone huismerken voor een retailer (langste eerst)."""
    brands = list(_RETAILER_BRANDS.get(retailer_slug, []))
    if retailer_slug in SUPERUNIE_SLUGS:
        brands.extend(SUPERUNIE_BRANDS)
    # Sorteer langste eerst (meer specifiek matcht eerder)
    brands.sort(key=len, reverse=True)
    return brands


# ---------------------------------------------------------------------------
# Detectiefunctie
# ---------------------------------------------------------------------------

def detect_brand(product_name, retailer_slug):
    """Detecteert het merk in een productnaam.

    Args:
        product_name: Volledige productnaam (bijv. "AH Biologisch Halfvolle Melk")
        retailer_slug: Retailer slug (bijv. "ah", "lidl", "jumbo")

    Returns:
        {'brand_name': str|None, 'brand_type': 'huismerk'|'a-merk'|'unknown',
         'confidence': float}
    """
    if not product_name or not product_name.strip():
        return {"brand_name": None, "brand_type": "unknown", "confidence": 0.0}

    # Normaliseer curly apostrofen (bv. Ben & Jerry's → Ben & Jerry's)
    product_name = _normalize(product_name.strip())
    name_lower = product_name.lower()

    # 1. Prefix-matching (langste prefix eerst)
    for prefix, brand_name, brand_type in STORE_PREFIX_BRANDS:
        if name_lower.startswith(prefix):
            return {
                "brand_name": brand_name,
                "brand_type": brand_type,
                "confidence": 1.0,
            }

    # 2. Standalone huismerken (retailer-specifiek)
    for brand in _get_store_brands(retailer_slug):
        m = _get_pattern(brand).search(product_name)
        if m:
            confidence = 0.95 if m.start() == 0 else 0.8
            return {
                "brand_name": brand,
                "brand_type": "huismerk",
                "confidence": confidence,
            }

    # 3. A-merken
    for brand in A_MERKEN:
        m = _get_pattern(brand).search(product_name)
        if m:
            confidence = 0.9 if m.start() == 0 else 0.7
            return {
                "brand_name": brand,
                "brand_type": "a-merk",
                "confidence": confidence,
            }

    return {"brand_name": None, "brand_type": "unknown", "confidence": 0.0}


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _get_products_without_brand():
    """Haal alle producten op waar brand_raw IS NULL of 'unknown' (herverwerking na uitbreiding)."""
    products = []
    offset = 0
    page_size = 1000
    while True:
        r = (
            supabase.table("retailer_products")
            .select("*")
            .or_("brand_raw.is.null,brand_raw.eq.unknown")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        products.extend(r.data)
        if len(r.data) < page_size:
            break
        offset += page_size
    return products


def _get_existing_brands():
    """Haal alle merken op uit de brands tabel als {name_lower: row}."""
    brands = {}
    offset = 0
    page_size = 1000
    while True:
        r = (
            supabase.table("brands")
            .select("id, name, slug")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        for row in r.data:
            brands[row["name"].lower()] = row
        if len(r.data) < page_size:
            break
        offset += page_size
    return brands


def _ensure_brand(brand_name, brand_type, slug_to_retailer_id, cache):
    """Zorg dat een merk in de brands tabel staat. Retourneert brand_id."""
    key = brand_name.lower()
    if key in cache:
        return cache[key]["id"]

    # Owning retailer opzoeken
    owner_slug = _get_brand_retailer_slug(brand_name)
    retailer_id = slug_to_retailer_id.get(owner_slug) if owner_slug else None
    is_store_brand = brand_type == "huismerk"
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


# ---------------------------------------------------------------------------
# Hoofdfunctie: update alle merken
# ---------------------------------------------------------------------------

def update_all_brands():
    """Detecteer merken voor alle producten zonder brand_raw en schrijf naar DB."""
    print("Ophalen retailers...")
    r = supabase.table("retailers").select("id, slug").execute()
    retailer_map = {row["id"]: row["slug"] for row in r.data}
    slug_to_retailer_id = {row["slug"]: row["id"] for row in r.data}
    print(f"  {len(retailer_map)} retailers gevonden\n")

    print("Ophalen bestaande merken...")
    brand_cache = _get_existing_brands()
    print(f"  {len(brand_cache)} merken in brands tabel\n")

    print("Ophalen producten zonder merk...")
    products = _get_products_without_brand()
    print(f"  {len(products)} producten te verwerken\n")

    if not products:
        print("Niets te doen.")
        return

    updates = []
    no_brand_rows = []  # producten zonder merk → brand_raw = 'unknown'
    stats = {}  # {slug: {"total": int, "detected": int, "undetected_names": [str]}}

    for prod in products:
        slug = retailer_map.get(prod["retailer_id"], "unknown")
        if slug not in stats:
            stats[slug] = {"total": 0, "detected": 0, "undetected_names": []}
        stats[slug]["total"] += 1

        result = detect_brand(prod["name"], slug)

        if result["brand_name"]:
            brand_id = _ensure_brand(
                result["brand_name"], result["brand_type"],
                slug_to_retailer_id, brand_cache
            )
            row = dict(prod)
            row.update({
                "brand_raw": result["brand_name"],
                "brand_type": result["brand_type"],
                "brand_id": brand_id,
            })
            updates.append(row)
            stats[slug]["detected"] += 1
        else:
            # Markeer als verwerkt met 'unknown' zodat we niet steeds opnieuw scannen
            row = dict(prod)
            row.update({
                "brand_raw": "unknown",
                "brand_type": "unknown",
            })
            no_brand_rows.append(row)
            stats[slug]["undetected_names"].append(prod["name"])

    # Batch upsert — producten met merk
    all_rows = updates + no_brand_rows
    print(f"Schrijven {len(all_rows)} updates naar database...")
    for i in range(0, len(all_rows), BATCH_SIZE):
        batch = all_rows[i : i + BATCH_SIZE]
        supabase.table("retailer_products").upsert(batch, on_conflict="id").execute()
        done = min(i + BATCH_SIZE, len(all_rows))
        print(f"  ... {done}/{len(all_rows)}")

    # --- Samenvatting ---
    print(f"\n{'=' * 65}")
    print("SAMENVATTING MERKDETECTIE")
    print(f"{'=' * 65}")
    print(
        f"{'Supermarkt':<15} {'Totaal':>8} {'Merk':>8} {'Geen':>8} {'%':>7}"
    )
    print("-" * 65)

    total_all = 0
    detected_all = 0
    for slug in sorted(stats.keys()):
        s = stats[slug]
        total = s["total"]
        detected = s["detected"]
        undetected = total - detected
        pct = (detected / total * 100) if total > 0 else 0
        print(f"{slug:<15} {total:>8} {detected:>8} {undetected:>8} {pct:>6.1f}%")
        total_all += total
        detected_all += detected

    pct_all = (detected_all / total_all * 100) if total_all > 0 else 0
    print("-" * 65)
    print(
        f"{'TOTAAL':<15} {total_all:>8} {detected_all:>8} "
        f"{total_all - detected_all:>8} {pct_all:>6.1f}%"
    )

    # Top 20 producten zonder merk per supermarkt
    print(f"\n{'=' * 65}")
    print("TOP 20 PRODUCTEN ZONDER MERK (per supermarkt)")
    print(f"{'=' * 65}")
    for slug in sorted(stats.keys()):
        names = stats[slug]["undetected_names"]
        if not names:
            continue
        print(f"\n  [{slug}] ({len(names)} zonder merk)")
        from collections import Counter
        top = Counter(names).most_common(20)
        for name, count in top:
            if count > 1:
                print(f"    {count:>3}x  {name}")
            else:
                print(f"         {name}")


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

def _test_detector():
    """Test de merkdetectie met voorbeelden."""
    test_cases = [
        # (product_name, retailer_slug, expected_brand, expected_type)

        # --- Prefix brands ---
        ("AH Halfvolle Melk", "ah", "AH", "huismerk"),
        ("AH Biologisch Scharreleieren", "ah", "AH Biologisch", "huismerk"),
        ("AH Excellent Parmigiano Reggiano", "ah", "AH Excellent", "huismerk"),
        ("AH Terra Plantaardige Schnitzel", "ah", "AH Terra", "huismerk"),
        ("AH Prijsfavorieten Penne", "ah", "AH Prijsfavorieten", "huismerk"),
        ("Jumbo Halfvolle Melk", "jumbo", "Jumbo", "huismerk"),
        ("Jumbo's Verse Jus d'Orange", "jumbo", "Jumbo's", "huismerk"),
        ("Plus Appelsap", "plus", "Plus", "huismerk"),
        ("Ekoplaza Volkoren Pasta", "ekoplaza", "Ekoplaza", "huismerk"),
        ("Spar Halfvolle Melk", "spar", "Spar", "huismerk"),
        ("Hoogvliet Pindakaas", "hoogvliet", "Hoogvliet", "huismerk"),
        ("Vomar Pindakaas", "vomar", "Vomar", "huismerk"),
        ("Dekamarkt Halfvolle Melk", "dekamarkt", "Dekamarkt", "huismerk"),

        # --- Standalone store brands ---
        ("Formil Black 1L", "lidl", "Formil", "huismerk"),
        ("Cien Nature douchegel", "lidl", "Cien", "huismerk"),
        ("Molenland kaas 48+ jong", "aldi", "Molenland", "huismerk"),
        ("Moser Roth chocolade", "aldi", "Moser Roth", "huismerk"),
        ("1 de Beste Pindakaas", "dirk", "1 de Beste", "huismerk"),
        ("g'woon Appelmoes", "dekamarkt", "g'woon", "huismerk"),
        ("g'woon Halfvolle Melk", "poiesz", "g'woon", "huismerk"),
        ("G'woon Aardappelkroketjes 750g", "vomar", "g'woon", "huismerk"),
        ("Melkan Halfvolle Yoghurt", "spar", "Melkan", "huismerk"),
        ("Perla Koffiepads", "ah", "Perla", "huismerk"),
        ("Euromerk Suiker", "jumbo", "Euromerk", "huismerk"),
        ("Bio+ Halfvolle Melk", "plus", "Bio+", "huismerk"),

        # --- A-merken ---
        ("Coca-Cola Zero Sugar", "ah", "Coca-Cola", "a-merk"),
        ("Heineken Premium Pilsener", "ah", "Heineken", "a-merk"),
        ("Douwe Egberts Aroma Rood", "jumbo", "Douwe Egberts", "a-merk"),
        ("Lay's Naturel Chips", "ah", "Lay's", "a-merk"),
        ("Robijn Wasmiddel Color", "plus", "Robijn", "a-merk"),
        ("Tony's Chocolonely Melk", "ah", "Tony's Chocolonely", "a-merk"),
        ("Dr. Oetker Ristorante Pizza", "jumbo", "Dr. Oetker", "a-merk"),
        ("Head & Shoulders Shampoo", "ah", "Head & Shoulders", "a-merk"),
        ("De Vegetarische Slager Shoarma", "ah", "De Vegetarische Slager", "a-merk"),
        ("Campina Halfvolle Melk", "ah", "Campina", "a-merk"),
        ("Spa Rood 1,5L", "plus", "Spa", "a-merk"),

        # --- Unknown ---
        ("Verse Aardbeien 400g", "ah", None, "unknown"),
        ("Bananen", "jumbo", None, "unknown"),
        ("Witte Druiven Pitloos", "lidl", None, "unknown"),
    ]

    print("Running brand detection tests...\n")
    passed = 0
    failed = 0

    for product_name, retailer_slug, expected_brand, expected_type in test_cases:
        result = detect_brand(product_name, retailer_slug)
        ok = (result["brand_name"] == expected_brand
              and result["brand_type"] == expected_type)
        status = "OK" if ok else "FAIL"
        if not ok:
            print(f"  {status}  {product_name!r} [{retailer_slug}]")
            print(f"         expected: {expected_brand} ({expected_type})")
            print(
                f"         got:      {result['brand_name']} "
                f"({result['brand_type']}) conf={result['confidence']}"
            )
            failed += 1
        else:
            conf = result["confidence"]
            brand_str = result["brand_name"] or "—"
            print(
                f"  {status}  {product_name!r:50s} → {brand_str} "
                f"({result['brand_type']}, {conf})"
            )
            passed += 1

    print(f"\n{passed} passed, {failed} failed")

    # --- Dry run op feed data ---
    print("\n\nDry run op feed data (zonder DB)...\n")
    import json
    try:
        with open("data/supermarkets.json") as f:
            feed_data = json.load(f)
    except FileNotFoundError:
        print("  data/supermarkets.json niet gevonden, skip dry run.")
        return failed == 0

    for sm in feed_data:
        slug = sm["n"]
        products = sm["d"]
        if not products:
            continue
        detected = 0
        for p in products:
            r = detect_brand(p["n"], slug)
            if r["brand_name"]:
                detected += 1
        total = len(products)
        pct = (detected / total * 100) if total > 0 else 0
        print(f"  {slug:<15} {detected:>6}/{total:<6} ({pct:>5.1f}%) merk gedetecteerd")

    return failed == 0


if __name__ == "__main__":
    import sys
    if "--update" in sys.argv:
        update_all_brands()
    else:
        _test_detector()
