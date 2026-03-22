# Opdracht voor Claude Code

Lees eerst PLAN.md voor context.

We gaan classify_brands_llm.py fundamenteel aanpassen. Stop het huidige script als het draait.

## Wat verandert

Het script classificeert nu ALLE producten uit Supabase, niet alleen unknowns. En het haalt per product veel meer informatie op: merk, categorie, bio, vegan, allergenen, ingrediënt-status, match key voor productmatching, en meer.

## 1. Data ophalen uit Supabase in plaats van unknowns.json

Haal alle retailer_products op waar is_available = true uit Supabase (via config.py). Per product heb je nodig: id, retailer_id, external_id, name, size_raw, en de retailer slug (join met retailers tabel). Sla op als lijst van dicts.

## 2. Cache key wordt `retailer_slug:external_id`

Zodat hetzelfde product bij verschillende supermarkten apart behandeld wordt. De bestaande cache (data/brand_classifications.json) kan weg — we beginnen opnieuw voor alle producten. Maak een nieuw cache bestand: `data/full_classifications.json`. Sla na elke batch op.

## 3. BATCH_SIZE = 10

Vanwege de grotere output per product.

## 4. Provider blijft OpenAI GPT-4.1 Nano

Delay 0.2 seconden tussen requests. Geen daglimiet.

## 5. User prompt per batch

Stuur per product de retailer slug, productnaam, en size_raw mee zodat de LLM weet bij welke supermarkt een product hoort en de hoeveelheid kan parsen:

```
["ah: AH Halfvolle Melk [1,5 l]", "lidl: Milbona Halfvolle Melk [1 l]", "aldi: Hamburgers [4 stuks]", "ah: Google Play €25 []"]
```

Formaat: `"retailer_slug: productnaam [size_raw]"`. Als size_raw leeg of null is, gebruik `[]`.

## 6. System prompt (gebruik deze letterlijk)

```
Je classificeert Nederlandse supermarktproducten. Je krijgt per product de supermarkt, productnaam, en verpakkingsgrootte.

Per product geef je een JSON object met EXACT deze velden:

- brand_name: de merknaam uit de productnaam. "GEEN" als er geen merk herkenbaar is.
- brand_type: "a-merk" (nationaal/internationaal merk zoals Heineken, Calvé, Coca-Cola), "huismerk" (supermarkt-eigen merk zoals AH, Jumbo, Milbona, g'woon, 1 de Beste), of "geen_merk" (geen merk herkenbaar — bij Aldi en Lidl zijn producten zonder merknaam meestal huismerken)
- category_l1: hoofdcategorie, MOET een van deze zijn: AGF, Zuivel & Eieren, Vlees & Vis, Dranken, Brood & Bakkerij, Houdbaar, Snacks, Diepvries, Kant-en-klaar, Sauzen & Kruiden, Ontbijt & Beleg, Huishouden, Verzorging, Baby, Diervoeding, Non-food
- category_l2: subcategorie (bijv. Melk, Frisdrank, Chips, Pasta, Wasmiddel). Wees consistent: gebruik altijd dezelfde term voor dezelfde productsoort.
- category_l3: specifiekere subcategorie, of null als niet te bepalen
- normalized_name: productnaam zonder merk en zonder verpakkingsgrootte, lowercase, alleen het product zelf
- is_bio: true als het product biologisch/organic/eko is
- is_vegan: true als dit duidelijk uit de productnaam blijkt
- is_vegetarian: true als dit duidelijk uit de productnaam blijkt. Zuivel, eieren, brood, groente, fruit zijn vegetarisch. Vlees en vis niet.
- is_lactose_free: true als "lactosevrij" of "lactose free" in de naam staat
- is_gluten_free: true als "glutenvrij" of "gluten free" in de naam staat
- is_food: true voor voeding en dranken, false voor cadeaukaarten, telefoonkaarten, kleding, elektronica
- allergens: lijst van allergenen die duidelijk uit de naam blijken: "melk", "gluten", "noten", "pinda", "soja", "ei", "vis", "schaaldieren", "selderij", "mosterd", "sesam", "lupine". Lege lijst als niet te bepalen uit de naam.
- quantity_amount: numerieke hoeveelheid uit de verpakkingsgrootte, bijv. 1.5. null als niet te parsen.
- quantity_unit: een van "g", "kg", "ml", "l", "stuk". null als niet te parsen.
- quantity_count: multipack count, 1 als geen multipack. Bijv. 6 bij "6x330ml". null als niet van toepassing.
- is_ingredient: true als het product een los ingrediënt is dat je gebruikt om te koken (kipfilet, uien, melk, boter, pasta, rijst, bloem, olie, kruiden, kaas, eieren). false als het een bereide/kant-en-klare maaltijd, snack, drank, schoonmaakmiddel, of non-food is.
- match_key: een generieke productnaam die IDENTIEK moet zijn voor hetzelfde product bij elke supermarkt. Zonder supermarktnaam. Voor huismerken: alleen productnaam + hoeveelheid lowercase. Voor A-merken: merknaam + productnaam + hoeveelheid lowercase. Voorbeelden: "AH Halfvolle Melk 1,5L" en "Jumbo Halfvolle Melk 1,5L" → "halfvolle melk 1.5l". "Coca-Cola Zero 6x330ml" bij AH en "Coca-Cola Zero Sugar 6x330ml" bij Jumbo → "coca-cola zero 6x330ml". null voor non-food.
- storage_type: een van "koelkast", "vriezer", "kamertemperatuur". Leid af uit het producttype. null voor non-food.

Antwoord ALLEEN met een JSON array. Geen uitleg, geen markdown.

Voorbeelden:

Input: ["ah: AH Biologisch Halfvolle Melk [1,5 l]", "ah: Lay's Naturel Chips [225 g]", "ah: Google Play €25 []", "aldi: Hamburgers [4 stuks]", "lidl: Milbona Halfvolle Melk [1 l]"]

Output:
[
  {"brand_name":"AH","brand_type":"huismerk","category_l1":"Zuivel & Eieren","category_l2":"Melk","category_l3":"Halfvolle melk","normalized_name":"halfvolle melk","is_bio":true,"is_vegan":false,"is_vegetarian":true,"is_lactose_free":false,"is_gluten_free":true,"is_food":true,"allergens":["melk"],"quantity_amount":1.5,"quantity_unit":"l","quantity_count":1,"is_ingredient":true,"match_key":"halfvolle melk 1.5l","storage_type":"koelkast"},
  {"brand_name":"Lay's","brand_type":"a-merk","category_l1":"Snacks","category_l2":"Chips","category_l3":"Naturel chips","normalized_name":"naturel chips","is_bio":false,"is_vegan":true,"is_vegetarian":true,"is_lactose_free":true,"is_gluten_free":false,"is_food":true,"allergens":[],"quantity_amount":225,"quantity_unit":"g","quantity_count":1,"is_ingredient":false,"match_key":"lays naturel chips 225g","storage_type":"kamertemperatuur"},
  {"brand_name":"Google","brand_type":"a-merk","category_l1":"Non-food","category_l2":"Cadeaukaarten","category_l3":null,"normalized_name":"play cadeaukaart","is_bio":false,"is_vegan":false,"is_vegetarian":false,"is_lactose_free":false,"is_gluten_free":false,"is_food":false,"allergens":[],"quantity_amount":null,"quantity_unit":null,"quantity_count":null,"is_ingredient":false,"match_key":null,"storage_type":null},
  {"brand_name":"GEEN","brand_type":"huismerk","category_l1":"Vlees & Vis","category_l2":"Rundvlees","category_l3":"Hamburgers","normalized_name":"hamburgers","is_bio":false,"is_vegan":false,"is_vegetarian":false,"is_lactose_free":true,"is_gluten_free":false,"is_food":true,"allergens":["gluten"],"quantity_amount":4,"quantity_unit":"stuk","quantity_count":1,"is_ingredient":true,"match_key":"hamburgers 4st","storage_type":"koelkast"},
  {"brand_name":"Milbona","brand_type":"huismerk","category_l1":"Zuivel & Eieren","category_l2":"Melk","category_l3":"Halfvolle melk","normalized_name":"halfvolle melk","is_bio":false,"is_vegan":false,"is_vegetarian":true,"is_lactose_free":false,"is_gluten_free":true,"is_food":true,"allergens":["melk"],"quantity_amount":1.0,"quantity_unit":"l","quantity_count":1,"is_ingredient":true,"match_key":"halfvolle melk 1l","storage_type":"koelkast"}
]
```

## 7. Response parsing

Parse de JSON array uit het antwoord. Als het aantal resultaten niet overeenkomt met het aantal input producten, match op volgorde en voeg missende producten toe aan een retry lijst. Retry aan het eind in batches van 5, max 3 pogingen per product. Behandel mismatches als warning, niet als error.

## 8. --resume flag

Leest data/full_classifications.json en skipt producten die al gecached zijn (op basis van cache key `retailer_slug:external_id`).

## 9. --test flag

Verwerkt 1 batch van 10, print volledig resultaat naar terminal, slaat NIET op in cache.

## 10. Voortgang

Print elke 100 producten een update met: aantal gedaan, percentage, totaal requests, geschatte ETA, en geschatte kosten tot nu toe (tel input en output tokens bij en reken met $0.10/M input en $0.40/M output).

## 11. apply_full_classifications.py

Schrijf een apart script `apply_full_classifications.py` dat:

1. `data/full_classifications.json` leest

2. De volgende kolommen toevoegt aan `retailer_products` als ze niet bestaan:
   - category_l1 TEXT
   - category_l2 TEXT
   - category_l3 TEXT
   - is_bio BOOLEAN DEFAULT FALSE
   - is_vegan BOOLEAN DEFAULT FALSE
   - is_vegetarian BOOLEAN DEFAULT FALSE
   - is_lactose_free BOOLEAN DEFAULT FALSE
   - is_gluten_free BOOLEAN DEFAULT FALSE
   - is_food BOOLEAN DEFAULT TRUE
   - allergens TEXT[]
   - is_ingredient BOOLEAN DEFAULT FALSE
   - match_key TEXT
   - storage_type TEXT

3. Per product alle velden terugschrijft naar `retailer_products` (update op basis van retailer_id + external_id):
   - brand_raw, brand_type, name_normalized
   - category_l1, category_l2, category_l3
   - is_bio, is_vegan, is_vegetarian, is_lactose_free, is_gluten_free
   - is_food, allergens
   - is_ingredient, match_key, storage_type
   - Voor quantity_amount, quantity_unit, quantity_count: schrijf ALLEEN als de LLM-waarde niet null is EN de bestaande waarde in de database null is. Behoud de waarde van normalize_units.py als die al succesvol was.
   - classification_source = 'llm'

4. Nieuwe merken toevoegt aan de `brands` tabel (als brand_name niet "GEEN" is en het merk nog niet bestaat)

5. brand_id koppelt in retailer_products

6. Een samenvatting print:
   - Totaal bijgewerkt
   - Per supermarkt: aantal producten, % met merk, % met categorie
   - Per category_l1: aantal producten
   - Hoeveel bio, vegan, vegetarisch, lactosevrij, glutenvrij
   - Hoeveel ingrediënten vs. niet-ingrediënten
   - Hoeveel non-food (is_food = false)
   - Top 20 meest voorkomende match_keys
