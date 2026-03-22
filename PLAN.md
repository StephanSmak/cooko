# Cooko — Stappenplan & Architectuur

> Dit bestand is de single source of truth voor het project.
> Claude Code: lees dit bestand voor context bij elke taak.

---

## Project overzicht

Cooko is een Nederlandse consumentenapp die supermarktprijzen vergelijkt en koppelt aan maaltijdplanning. De kern is een data pipeline die dagelijks ~90.000 producten van 8+ Nederlandse supermarkten verwerkt, classificeert, en vergelijkbaar maakt.

## Tech stack

- **Database:** Supabase (PostgreSQL + pgvector + pg_trgm)
- **Pipeline:** Python (pandas, rapidfuzz, pint, sentence-transformers)
- **LLM:** OpenAI GPT-4.1 Nano voor classificatie
- **App:** React Native (Expo) — later
- **Orchestratie:** Prefect Cloud (gratis tier) — later

## Databron

Dagelijkse JSON van derde partij. Structuur per supermarkt:

```json
{
  "n": "ah",
  "d": [
    {
      "n": "AH Halfvolle Melk 1,5L",
      "l": "wi12345/ah-halfvolle-melk",
      "p": 1.39,
      "s": "1 l"
    }
  ],
  "u": "https://www.ah.nl/...",
  "c": "AH",
  "i": "https://..."
}
```

Supermarkten: AH, Jumbo, Lidl, Aldi, Dirk, DekaMarkt, Plus, Ekoplaza.

---

## Sprint 1: Data pipeline & classificatie

### Scripts die actief zijn

| Script                          | Doel                                         | Input                      | Output                            |
| ------------------------------- | -------------------------------------------- | -------------------------- | --------------------------------- |
| `config.py`                     | Supabase client + env vars                   | .env                       | Supabase client                   |
| `ingest.py`                     | JSON feed → retailer_products                | data/\*.json               | Supabase retailer_products        |
| `normalize_units.py`            | Eenheden parsen, unit_price                  | retailer_products.size_raw | unit_price, quantity_amount, etc. |
| `classify_brands_llm.py`        | Alles in één pass via GPT-4.1 Nano           | retailer_products.name     | full_classifications.json         |
| `apply_full_classifications.py` | LLM resultaten → Supabase                    | full_classifications.json  | retailer_products.\*              |
| `generate_rules.py`             | Regels extraheren uit LLM output             | full_classifications.json  | rules/\*.json                     |
| `classify_rules.py`             | Regelgebaseerde classificatie (snel, gratis) | product name               | merk, categorie, flags            |
| `run_pipeline.py`               | Dagelijkse orchestratie                      | -                          | -                                 |

### Scripts die NIET meer nodig zijn

- `detect_brands.py` → vervangen door LLM + regelextractie
- `normalize_names.py` → LLM levert normalized_name
- `export_unknowns.py` → LLM draait op alles
- `inspect_classifications.py` → samenvatting zit in apply script

### Stappen

#### ✅ Stap 1: Supabase schema

Schema geladen via 001_schema.sql. Retailers tabel gevuld.

#### ✅ Stap 2: JSON ingestie

ingest.py laadt ~90.000 producten in retailer_products.

#### ✅ Stap 3: Eenheidsnormalisatie

normalize_units.py parseert size_raw → unit_price. Parse rate >85%.

#### 🔄 Stap 4: LLM classificatie (ALLES in één pass)

classify_brands_llm.py classificeert alle ~90.000 producten via GPT-4.1 Nano.
Per product: merk, categorie (3 niveaus), bio, vegan, vegetarisch, lactosevrij, glutenvrij, allergenen, normalized_name, is_food.
Kosten: ~€8-9 eenmalig. Cache: data/full_classifications.json.

#### ⏳ Stap 5: Resultaten terugschrijven

```bash
python3 apply_full_classifications.py
```

Voegt kolommen toe aan retailer_products en schrijft alles terug.

#### ⏳ Stap 6: Regels extraheren uit LLM output

```bash
python3 generate_rules.py
```

Leest full_classifications.json en genereert:

- `rules/brands.json` — alle ~2000+ merknamen met type en frequentie
- `rules/categories.json` — keyword → categorie mapping per l1/l2/l3
- `rules/flags.json` — keywords voor bio, vegan, lactosevrij, etc.

#### ⏳ Stap 7: Regelgebaseerde classifier bouwen

```bash
# classify_rules.py — puur deterministische classificatie
```

Gebruikt rules/\*.json om producten te classificeren zonder LLM.
Verwachte hit rate: 90-95% van alle producten.
Producten die niet matchen gaan naar classify_brands_llm.py.

#### ⏳ Stap 8: Pipeline runner aanpassen

run_pipeline.py wordt:

1. `ingest.py` — JSON laden
2. `normalize_units.py` — eenheden parsen
3. `classify_rules.py` — regelgebaseerd (gratis, instant, 90-95%)
4. `classify_brands_llm.py --resume` — LLM fallback (alleen nieuwe/onbekende, ~€0.01-0.03/dag)
5. `apply_full_classifications.py` — terugschrijven
6. `generate_rules.py` — regels updaten met nieuwe LLM output (feedback loop)

#### ⏳ Stap 9: Validatie

SQL queries om te controleren:

- Categorieverdeling per l1
- Merkdetectie percentage per supermarkt
- Bio/vegan aantallen
- Non-food filtering
- Prijsvergelijkingen met categorieën

---

## Sprint 2: Product matching across supermarkten

> Oorspronkelijk Sprint 3, naar voren geschoven omdat LLM-classificatie al in Sprint 1 zit.

### Doel

Koppel hetzelfde product bij verschillende supermarkten zodat je kunt zeggen: "AH Halfvolle Melk = Jumbo Halfvolle Melk = Milbona Halfvolle Melk".

### Twee typen matching

**A-merken (exact match):** Coca-Cola bij AH = Coca-Cola bij Jumbo.
Match op: brand_name + normalized_name + quantity_amount + quantity_unit.

**Huismerken (equivalent match):** AH Halfvolle Melk ≈ Milbona Halfvolle Melk.
Match op: category_l3 + normalized_name (fuzzy) + quantity vergelijking.

### Tools

- pg_trgm voor fuzzy matching in PostgreSQL
- Splink voor probabilistic record linkage
- sentence-transformers (multilingual-e5-large) voor embedding matching
- pgvector voor vector similarity queries

### Schema

Matches komen in de `product_matches` tabel (al aangemaakt in Sprint 1).
Materialized view `mv_product_comparisons` voor snelle vergelijkingsqueries.

---

## Sprint 3: React Native app

- Expo + Supabase SDK
- Zoeken, vergelijken, filteren op categorie/merk/dieet
- PWA als bonus voor SEO

---

## Dagelijkse pipeline kosten (na Sprint 1)

| Onderdeel                                | Kosten/dag       |
| ---------------------------------------- | ---------------- |
| Supabase Pro                             | ~€0.80           |
| OpenAI (alleen nieuwe producten via LLM) | ~€0.01-0.03      |
| Railway (pipeline compute)               | ~€0.15-0.60      |
| **Totaal**                               | **~€1-1.50/dag** |

---

## Belangrijke paden

```
cooko/
├── .env                          # SUPABASE_URL, SUPABASE_SERVICE_KEY, OPENAI_API_KEY, GEMINI_API_KEY
├── PLAN.md                       # DIT BESTAND
├── config.py                     # Supabase client
├── ingest.py                     # JSON → Supabase
├── normalize_units.py            # Eenheden parsen
├── classify_brands_llm.py        # LLM classificatie (OpenAI/Gemini)
├── apply_full_classifications.py # LLM resultaten → Supabase
├── generate_rules.py             # Regels extraheren
├── classify_rules.py             # Regelgebaseerde classificatie
├── run_pipeline.py               # Dagelijkse orchestratie
├── data/
│   ├── *.json                    # Ruwe JSON feeds
│   ├── full_classifications.json # LLM classificatie cache
│   └── brand_classifications.json # Oude cache (kan weg na migratie)
└── rules/
    ├── brands.json               # Merknamen + type
    ├── categories.json           # Keyword → categorie
    └── flags.json                # Keywords voor bio, vegan, etc.
```

---

## Supabase retailer_products kolommen

```
id, retailer_id, product_id, external_id, name, name_normalized, size_raw,
current_price, original_price, unit_price, unit_price_unit,
quantity_amount, quantity_unit, quantity_count,
brand_id, brand_raw, brand_type,
category_l1, category_l2, category_l3,
is_bio, is_vegan, is_vegetarian, is_lactose_free, is_gluten_free,
is_food, allergens,
is_on_sale, sale_label, product_url,
classification_source, is_available, first_seen_at, last_seen_at
```
