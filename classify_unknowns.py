"""
classify_unknowns.py — Classificeert onbekende producten via de Anthropic API.

Leest data/unknowns.json, stuurt producten in batches van 20 naar Claude Haiku,
en slaat resultaten op in data/brand_classifications.json.
"""

import json
import os
import time
from collections import Counter

import anthropic

INPUT_PATH = "data/unknowns.json"
CACHE_PATH = "data/brand_classifications.json"
BATCH_SIZE = 20
MAX_REQUESTS_PER_MINUTE = 50
MIN_INTERVAL = 60.0 / MAX_REQUESTS_PER_MINUTE  # 1.2 s between requests

SYSTEM_PROMPT = """\
Je analyseert Nederlandse supermarktproductnamen. Per product, bepaal:
1. brand_name — de merknaam die in de productnaam staat. Als er geen herkenbaar merk in staat, antwoord "GEEN".
2. brand_type — "a-merk" (nationaal/internationaal merk zoals Heineken, Calvé, Douwe Egberts), "huismerk" (supermarkt-eigen merk), of "geen_merk" (geen merk herkenbaar, waarschijnlijk supermarkt eigen product zonder merknaam)
3. is_food — true als het een voedings- of huishoudproduct is, false als het een cadeaukaart, telefoonkaart, non-food, of kleding is.

Antwoord ALLEEN in JSON. Geen uitleg.

Voorbeelden:
"Davitamon Compleet weerstand" → {"brand_name": "Davitamon", "brand_type": "a-merk", "is_food": true}
"Gebroken sperziebonen" → {"brand_name": "GEEN", "brand_type": "geen_merk", "is_food": true}
"Google Play" → {"brand_name": "Google", "brand_type": "a-merk", "is_food": false}
"Côte d'Or Chokotoff" → {"brand_name": "Côte d'Or", "brand_type": "a-merk", "is_food": true}
"Flat chips" → {"brand_name": "GEEN", "brand_type": "geen_merk", "is_food": true}\
"""


def load_cache() -> dict:
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(cache: dict) -> None:
    os.makedirs("data", exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def classify_batch(client: anthropic.Anthropic, names: list[str]) -> list[dict]:
    """Stuur een batch productnamen naar het model; geeft een lijst dicts terug."""
    numbered = "\n".join(f'{i + 1}. "{name}"' for i, name in enumerate(names))
    user_message = (
        f"Analyseer de volgende {len(names)} producten. "
        "Geef een JSON array terug met één object per product, in dezelfde volgorde.\n\n"
        f"Producten:\n{numbered}"
    )

    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=1000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    text = next(b.text for b in response.content if b.type == "text")

    # Extraheer JSON array uit de response
    start = text.find("[")
    end = text.rfind("]") + 1
    if start == -1 or end == 0:
        raise ValueError(f"Geen JSON array in response: {text[:300]}")

    results = json.loads(text[start:end])
    if len(results) != len(names):
        raise ValueError(
            f"Verwacht {len(names)} resultaten, kreeg {len(results)}: {text[:200]}"
        )
    return results


def main() -> None:
    print("Loading unknowns...")
    with open(INPUT_PATH, encoding="utf-8") as f:
        unknowns = json.load(f)
    print(f"Geladen: {len(unknowns)} unieke productnamen")

    cache = load_cache()
    print(f"Cache: {len(cache)} bestaande classificaties")

    # Sla producten over die al gecached zijn (key = naam lowercase)
    to_classify = [u for u in unknowns if u["name"].lower() not in cache]
    print(f"Te classificeren: {len(to_classify)} producten\n")

    if not to_classify:
        print("Niets te doen.")
    else:
        client = anthropic.Anthropic()  # leest ANTHROPIC_API_KEY uit environment

        last_request_time = 0.0
        classified = 0
        errors = 0
        next_milestone = 100  # print elke 100 producten

        for batch_idx, i in enumerate(range(0, len(to_classify), BATCH_SIZE)):
            batch = to_classify[i : i + BATCH_SIZE]
            names = [u["name"] for u in batch]

            # Rate limiting: maximaal 50 requests per minuut
            elapsed = time.monotonic() - last_request_time
            if elapsed < MIN_INTERVAL:
                time.sleep(MIN_INTERVAL - elapsed)

            try:
                results = classify_batch(client, names)
                last_request_time = time.monotonic()

                for name, result in zip(names, results):
                    cache[name.lower()] = {
                        "name": name,
                        "brand_name": result.get("brand_name", "GEEN"),
                        "brand_type": result.get("brand_type", "geen_merk"),
                        "is_food": result.get("is_food", True),
                    }
                classified += len(batch)

            except Exception as exc:
                last_request_time = time.monotonic()
                print(f"  ERROR batch {batch_idx + 1}: {exc}")
                errors += len(batch)

            # Voortgang elke 100 producten
            done = i + len(batch)
            while done >= next_milestone:
                pct = next_milestone * 100 // len(to_classify)
                print(f"  Voortgang: {next_milestone}/{len(to_classify)} ({pct}%)")
                next_milestone += 100

            # Cache opslaan elke 10 batches (~200 producten)
            if batch_idx % 10 == 9:
                save_cache(cache)

        save_cache(cache)
        print(f"\nGeclassificeerd: {classified}  |  Fouten: {errors}")

    # --- Samenvatting ---
    all_results = list(cache.values())
    brand_types = Counter(r["brand_type"] for r in all_results)
    non_food_count = sum(1 for r in all_results if not r.get("is_food", True))
    a_merk_names = sorted(
        {r["brand_name"] for r in all_results
         if r["brand_type"] == "a-merk" and r["brand_name"] != "GEEN"}
    )

    print(f"\n{'=' * 55}")
    print("SAMENVATTING")
    print(f"{'=' * 55}")
    print(f"Totaal geclassificeerd:  {len(all_results)}")
    print(f"  A-merken:              {brand_types.get('a-merk', 0)}")
    print(f"  Huismerken:            {brand_types.get('huismerk', 0)}")
    print(f"  Geen merk:             {brand_types.get('geen_merk', 0)}")
    print(f"  Non-food (is_food=F):  {non_food_count}")
    print(f"\nUnieke A-merknamen gevonden: {len(a_merk_names)}")
    if a_merk_names:
        preview = a_merk_names[:40]
        print("  " + ", ".join(preview))
        if len(a_merk_names) > 40:
            print(f"  ... en {len(a_merk_names) - 40} meer")
    print(f"\nGeschreven naar: {CACHE_PATH}")


if __name__ == "__main__":
    main()
