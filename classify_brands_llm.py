"""
classify_brands_llm.py — Classificeert onbekende producten via OpenAI of Gemini.

Leest data/unknowns.json, stuurt producten in batches van 10 naar het model,
en slaat resultaten op in data/brand_classifications.json.

Providers:
  openai  (default) — gpt-4.1-nano, geen daglimiet, 0.5s tussen requests
  gemini             — gemini-2.5-flash, 20 requests/dag gratis tier

Gebruik:
  python3 classify_brands_llm.py                        # OpenAI, start of hervat
  python3 classify_brands_llm.py --provider gemini      # gebruik Gemini
  python3 classify_brands_llm.py --resume               # expliciet hervat vanuit cache
  python3 classify_brands_llm.py --test                 # verwerk 1 batch, sla NIET op
"""

import json
import os
import re
import sys
import time
from collections import Counter
from datetime import date

from dotenv import load_dotenv
load_dotenv()

INPUT_PATH = "data/unknowns.json"
CACHE_PATH = "data/brand_classifications.json"
STATE_PATH = "data/gemini_state.json"

BATCH_SIZE = 10
PROGRESS_EVERY = 50

# Provider-specifieke instellingen
PROVIDER_CONFIG = {
    "openai": {
        "model": "gpt-4.1-nano",
        "min_interval": 0.2,
        "requests_per_day": None,   # geen daglimiet
        "api_key_env": "OPENAI_API_KEY",
    },
    "gemini": {
        "model": "gemini-2.5-flash",
        "min_interval": 6.5,
        "requests_per_day": 20,
        "api_key_env": "GEMINI_API_KEY",
    },
}

SYSTEM_PROMPT = """\
Je analyseert Nederlandse supermarktproductnamen. Geef per product een JSON object terug met deze velden:

- brand_name: merknaam uit de productnaam, of "GEEN" als er geen herkenbaar merk is
- brand_type: "a-merk" (nationaal/internationaal merk zoals Heineken, Calvé, Douwe Egberts), "huismerk" (supermarkt-eigen merk), of "geen_merk"
- category_l1: één van: AGF, Zuivel & Eieren, Vlees & Vis, Dranken, Brood & Bakkerij, Houdbaar, Snacks, Diepvries, Kant-en-klaar, Sauzen & Kruiden, Ontbijt & Beleg, Huishouden, Verzorging, Baby, Diervoeding, Non-food
- category_l2: subcategorie, consistent (bijv. altijd "Melk", nooit "Melkproducten" voor hetzelfde type)
- category_l3: verdere specificatie, of null als niet te bepalen
- normalized_name: productnaam zonder merk en verpakkingsgrootte, lowercase
- is_bio: true als de naam "bio", "biologisch", "organic" of "eko" bevat
- is_vegan: true alleen als dit duidelijk uit de naam blijkt
- is_vegetarian: true alleen als dit duidelijk uit de naam blijkt
- is_lactose_free: true alleen als dit duidelijk uit de naam blijkt
- is_gluten_free: true alleen als dit duidelijk uit de naam blijkt
- is_food: false voor cadeaukaarten, telefoonkaarten, non-food en kleding
- allergens: lijst van allergenen die duidelijk uit de naam blijken (bijv. ["gluten", "melk", "noten"]), anders []

Je krijgt per aanroep tot 10 producten tegelijk. Antwoord ALLEEN met een JSON array. Geen uitleg.

Voorbeelden:
"AH Biologisch Halfvolle Melk 1L" → {"brand_name":"AH","brand_type":"huismerk","category_l1":"Zuivel & Eieren","category_l2":"Melk","category_l3":"Halfvolle melk","normalized_name":"halfvolle melk","is_bio":true,"is_vegan":false,"is_vegetarian":true,"is_lactose_free":false,"is_gluten_free":true,"is_food":true,"allergens":["melk"]}
"Lay's Naturel Chips 225g" → {"brand_name":"Lay's","brand_type":"a-merk","category_l1":"Snacks","category_l2":"Chips","category_l3":"Naturel chips","normalized_name":"naturel chips","is_bio":false,"is_vegan":true,"is_vegetarian":true,"is_lactose_free":true,"is_gluten_free":false,"is_food":true,"allergens":["gluten"]}
"Heineken 0.0 Bier 6x330ml" → {"brand_name":"Heineken","brand_type":"a-merk","category_l1":"Dranken","category_l2":"Bier","category_l3":"Alcoholvrij bier","normalized_name":"0.0 bier","is_bio":false,"is_vegan":true,"is_vegetarian":true,"is_lactose_free":true,"is_gluten_free":false,"is_food":true,"allergens":["gluten"]}
"Google Play €25" → {"brand_name":"Google","brand_type":"a-merk","category_l1":"Non-food","category_l2":"Cadeaukaarten","category_l3":null,"normalized_name":"play cadeaukaart","is_bio":false,"is_vegan":false,"is_vegetarian":false,"is_lactose_free":false,"is_gluten_free":false,"is_food":false,"allergens":[]}
"Milbona Halfvolle Melk 1L" → {"brand_name":"Milbona","brand_type":"huismerk","category_l1":"Zuivel & Eieren","category_l2":"Melk","category_l3":"Halfvolle melk","normalized_name":"halfvolle melk","is_bio":false,"is_vegan":false,"is_vegetarian":true,"is_lactose_free":false,"is_gluten_free":true,"is_food":true,"allergens":["melk"]}\
"""

# Velden die een volledige cache-entry moet bevatten — entries zonder deze velden worden opnieuw geclassificeerd
REQUIRED_FIELDS = {
    "brand_name", "brand_type", "category_l1", "category_l2", "category_l3",
    "normalized_name", "is_bio", "is_vegan", "is_vegetarian", "is_lactose_free",
    "is_gluten_free", "is_food", "allergens",
}


# ---------------------------------------------------------------------------
# Cache en state
# ---------------------------------------------------------------------------

def load_cache() -> dict:
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(cache: dict) -> None:
    os.makedirs("data", exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def load_state() -> dict:
    """Laad dagelijkse request-teller. Reset automatisch op een nieuwe dag."""
    today = date.today().isoformat()
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, encoding="utf-8") as f:
            state = json.load(f)
        if state.get("date") == today:
            return state
    return {"date": today, "requests_today": 0}


def save_state(state: dict) -> None:
    os.makedirs("data", exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f)


# ---------------------------------------------------------------------------
# API-aanroepen
# ---------------------------------------------------------------------------

def _build_user_message(names: list) -> str:
    numbered = "\n".join(f'{i + 1}. "{name}"' for i, name in enumerate(names))
    return (
        f"Analyseer de volgende {len(names)} producten. "
        "Geef een JSON array terug met één object per product, in dezelfde volgorde.\n\n"
        f"Producten:\n{numbered}"
    )


def _parse_json_array(text: str) -> list:
    start = text.find("[")
    end = text.rfind("]") + 1
    if start == -1 or end == 0:
        raise ValueError(f"Geen JSON array in response: {text[:300]}")
    return json.loads(text[start:end])


def classify_batch_openai(client, names: list) -> list:
    """Stuur een batch productnamen naar OpenAI; geeft een lijst dicts terug."""
    response = client.chat.completions.create(
        model="gpt-4.1-nano",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_message(names)},
        ],
        temperature=0,
    )
    return _parse_json_array(response.choices[0].message.content)


def classify_batch_gemini(client, names: list) -> list:
    """Stuur een batch productnamen naar Gemini; geeft een lijst dicts terug."""
    from google.genai import types
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
        contents=_build_user_message(names),
    )
    return _parse_json_array(response.text)


# ---------------------------------------------------------------------------
# Hulpfuncties
# ---------------------------------------------------------------------------

def format_eta(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s"
    m, s = divmod(int(seconds), 60)
    if m < 60:
        return f"{m}m{s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}u{m:02d}m"


def print_summary(cache: dict, state: dict, provider: str) -> None:
    all_results = list(cache.values())
    brand_types = Counter(r["brand_type"] for r in all_results)
    non_food_count = sum(1 for r in all_results if not r.get("is_food", True))
    a_merk_names = sorted(
        {r["brand_name"] for r in all_results
         if r["brand_type"] == "a-merk" and r["brand_name"] != "GEEN"}
    )
    cfg = PROVIDER_CONFIG[provider]
    day_limit = cfg["requests_per_day"] or "∞"

    print(f"\n{'=' * 57}")
    print("SAMENVATTING")
    print(f"{'=' * 57}")
    print(f"Totaal geclassificeerd:  {len(all_results)}")
    print(f"  A-merken:              {brand_types.get('a-merk', 0)}")
    print(f"  Huismerken:            {brand_types.get('huismerk', 0)}")
    print(f"  Geen merk:             {brand_types.get('geen_merk', 0)}")
    print(f"  Non-food (is_food=F):  {non_food_count}")
    print(f"\nUnieke A-merknamen gevonden: {len(a_merk_names)}")
    if a_merk_names:
        print("  " + ", ".join(a_merk_names[:40]))
        if len(a_merk_names) > 40:
            print(f"  ... en {len(a_merk_names) - 40} meer")
    print(f"\nCache: {CACHE_PATH}")
    print(f"Provider: {provider} ({cfg['model']})")
    print(f"Requests vandaag ({state['date']}): "
          f"{state['requests_today']}/{day_limit}")


# ---------------------------------------------------------------------------
# Hoofdfunctie
# ---------------------------------------------------------------------------

def main() -> None:
    resume = "--resume" in sys.argv
    test_mode = "--test" in sys.argv

    provider = "openai"
    if "--provider" in sys.argv:
        idx = sys.argv.index("--provider")
        if idx + 1 < len(sys.argv):
            provider = sys.argv[idx + 1]
    if provider not in PROVIDER_CONFIG:
        print(f"FOUT: onbekende provider '{provider}'. Kies 'openai' of 'gemini'.")
        sys.exit(1)

    cfg = PROVIDER_CONFIG[provider]
    min_interval = cfg["min_interval"]
    requests_per_day = cfg["requests_per_day"]

    print(f"Provider: {provider} ({cfg['model']})")
    print("Laden unknowns.json...")
    with open(INPUT_PATH, encoding="utf-8") as f:
        unknowns = json.load(f)
    print(f"  {len(unknowns)} unieke productnamen")

    cache = load_cache()
    state = load_state()
    requests_today = state["requests_today"]

    print(f"  Cache: {len(cache)} bestaande classificaties")
    if requests_per_day:
        remaining_quota = requests_per_day - requests_today
        print(f"  Requests vandaag: {requests_today}/{requests_per_day} "
              f"({remaining_quota} resterend)\n")
        if remaining_quota <= 0:
            print("Daglimiet bereikt, hervat morgen met:")
            print(f"  python3 classify_brands_llm.py --provider {provider} --resume")
            return
    else:
        print(f"  Requests vandaag: {requests_today} (geen daglimiet)\n")
        remaining_quota = None

    # Producten die nog niet gecached zijn of een onvolledige entry hebben
    def needs_classification(name: str) -> bool:
        entry = cache.get(name.lower())
        if entry is None:
            return True
        return not REQUIRED_FIELDS.issubset(entry.keys())

    to_classify = [u for u in unknowns if needs_classification(u["name"])]
    incomplete = sum(1 for u in unknowns
                     if u["name"].lower() in cache and needs_classification(u["name"]))
    print(f"Te classificeren: {len(to_classify)} producten "
          f"({incomplete} onvolledige cache-entries inbegrepen)")

    if remaining_quota is not None and len(to_classify) > remaining_quota * BATCH_SIZE:
        print(f"  (daglimiet laat nog max. {remaining_quota * BATCH_SIZE} producten toe "
              f"in {remaining_quota} requests)")

    if resume:
        print("  --resume: ga verder vanuit bestaande cache")
    if test_mode:
        print("  --test: verwerkt 1 batch, resultaat wordt NIET opgeslagen")
    print()

    if not to_classify:
        print("Niets te doen.")
        print_summary(cache, state, provider)
        return

    api_key = os.getenv(cfg["api_key_env"])
    if not api_key:
        print(f"FOUT: {cfg['api_key_env']} niet gevonden in environment.")
        sys.exit(1)

    if provider == "openai":
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        classify_batch = lambda names: classify_batch_openai(client, names)
    else:
        from google import genai
        client = genai.Client(api_key=api_key)
        classify_batch = lambda names: classify_batch_gemini(client, names)

    # --- Test mode: één batch, print resultaat, stop ---
    if test_mode:
        batch = to_classify[:BATCH_SIZE]
        names = [u["name"] for u in batch]
        print(f"Test batch ({len(names)} producten):\n")
        for idx, name in enumerate(names, 1):
            print(f"  {idx:>2}. {name}")
        print()
        results = classify_batch(names)
        print("Resultaat:\n")
        for name, result in zip(names, results):
            print(json.dumps({"name": name, **result}, ensure_ascii=False))
        print("\n(Niet opgeslagen in cache)")
        return

    last_request_time = 0.0
    classified = 0
    errors = 0
    batches_done = 0
    recent_durations = []   # voor ETA (rolling window van 10)
    last_progress_at = 0
    retry_counts = {}       # name -> aantal pogingen gedaan

    i = 0
    while i < len(to_classify):
        # Daglimiet check vóór elke batch (alleen voor Gemini)
        if requests_per_day and requests_today >= requests_per_day:
            save_cache(cache)
            save_state(state)
            print(f"\nDaglimiet bereikt ({requests_per_day} requests/dag).")
            print(f"Hervat morgen met:")
            print(f"  python3 classify_brands_llm.py --provider {provider} --resume")
            print_summary(cache, state, provider)
            return

        batch = to_classify[i : i + BATCH_SIZE]
        names = [u["name"] for u in batch]

        # Rate limiting
        elapsed = time.monotonic() - last_request_time
        if elapsed < min_interval and last_request_time > 0:
            time.sleep(min_interval - elapsed)

        t0 = time.monotonic()
        try:
            results = classify_batch(names)
            duration = time.monotonic() - t0
            last_request_time = time.monotonic()

            received = len(results)
            expected = len(names)
            if received < expected:
                print(f"  WAARSCHUWING: {received}/{expected} resultaten — "
                      f"{expected - received} product(en) toegevoegd aan retry")
                for name in names[received:]:
                    retry_counts.setdefault(name, 0)

            for name, result in zip(names, results):
                cache[name.lower()] = {
                    "name": name,
                    "brand_name": result.get("brand_name", "GEEN"),
                    "brand_type": result.get("brand_type", "geen_merk"),
                    "category_l1": result.get("category_l1"),
                    "category_l2": result.get("category_l2"),
                    "category_l3": result.get("category_l3"),
                    "normalized_name": result.get("normalized_name"),
                    "is_bio": result.get("is_bio", False),
                    "is_vegan": result.get("is_vegan", False),
                    "is_vegetarian": result.get("is_vegetarian", False),
                    "is_lactose_free": result.get("is_lactose_free", False),
                    "is_gluten_free": result.get("is_gluten_free", False),
                    "is_food": result.get("is_food", True),
                    "allergens": result.get("allergens", []),
                }
            classified += received
            requests_today += 1
            batches_done += 1
            state["requests_today"] = requests_today

            recent_durations.append(duration + min_interval)
            if len(recent_durations) > 10:
                recent_durations.pop(0)

            i += BATCH_SIZE

        except Exception as exc:
            last_request_time = time.monotonic()
            exc_str = str(exc)

            # Gemini: dagquota-overschrijding → stop direct
            if "GenerateRequestsPerDayPerProjectPerModel" in exc_str:
                save_cache(cache)
                save_state(state)
                print(f"\nDagquota bereikt ({requests_today} requests gebruikt).")
                print(f"Hervat morgen met:")
                print(f"  python3 classify_brands_llm.py --provider {provider} --resume")
                print_summary(cache, state, provider)
                return

            # 429 met retryDelay → wacht en retry dezelfde batch
            m = re.search(r"retryDelay.*?(\d+)s", exc_str)
            if m:
                retry_delay = int(m.group(1)) + 2
                print(f"  Rate limit (429), wacht {retry_delay}s en probeer opnieuw...")
                time.sleep(retry_delay)
                continue  # i niet opgehoogd

            errors += len(batch)
            print(f"  ERROR batch {batches_done + 1}: {exc}")
            i += BATCH_SIZE

        # Voortgangsupdate elke PROGRESS_EVERY producten
        done = i
        if done - last_progress_at >= PROGRESS_EVERY or done >= len(to_classify):
            last_progress_at = done
            pct = done * 100 // len(to_classify)

            if requests_per_day:
                remaining_quota_now = requests_per_day - requests_today
                remaining_batches = (len(to_classify) - done + BATCH_SIZE - 1) // BATCH_SIZE
                if recent_durations and done < len(to_classify):
                    avg = sum(recent_durations) / len(recent_durations)
                    effective_batches = min(remaining_batches, remaining_quota_now)
                    eta_str = format_eta(effective_batches * avg)
                    if remaining_batches > remaining_quota_now:
                        eta_str += " (daglimiet bereikt daarna)"
                else:
                    eta_str = "—"
                quota_str = f"{requests_today}/{requests_per_day}"
            else:
                remaining_batches = (len(to_classify) - done + BATCH_SIZE - 1) // BATCH_SIZE
                if recent_durations and done < len(to_classify):
                    avg = sum(recent_durations) / len(recent_durations)
                    eta_str = format_eta(remaining_batches * avg)
                else:
                    eta_str = "—"
                quota_str = str(requests_today)

            print(
                f"  {done:>5}/{len(to_classify)} ({pct:>3}%) | "
                f"requests: {quota_str} | "
                f"ETA: {eta_str}"
            )

        # Cache + state periodiek opslaan (elke 10 batches)
        if batches_done > 0 and batches_done % 10 == 0:
            save_cache(cache)
            save_state(state)

    # ---------------------------------------------------------------------------
    # Retry-loop: producten die de LLM miste, in batches van 5, max 3 pogingen
    # ---------------------------------------------------------------------------
    RETRY_BATCH = 5
    MAX_RETRIES = 3

    pending = [name for name in retry_counts if name.lower() not in cache]
    if pending:
        print(f"\nRetry: {len(pending)} product(en) opnieuw proberen (batches van {RETRY_BATCH})...")

    while pending:
        next_pending = []
        i = 0
        while i < len(pending):
            retry_batch = pending[i : i + RETRY_BATCH]

            elapsed = time.monotonic() - last_request_time
            if elapsed < min_interval and last_request_time > 0:
                time.sleep(min_interval - elapsed)

            try:
                results = classify_batch(retry_batch)
                last_request_time = time.monotonic()
                received = len(results)

                for name, result in zip(retry_batch, results):
                    cache[name.lower()] = {
                        "name": name,
                        "brand_name": result.get("brand_name", "GEEN"),
                        "brand_type": result.get("brand_type", "geen_merk"),
                        "category_l1": result.get("category_l1"),
                        "category_l2": result.get("category_l2"),
                        "category_l3": result.get("category_l3"),
                        "normalized_name": result.get("normalized_name"),
                        "is_bio": result.get("is_bio", False),
                        "is_vegan": result.get("is_vegan", False),
                        "is_vegetarian": result.get("is_vegetarian", False),
                        "is_lactose_free": result.get("is_lactose_free", False),
                        "is_gluten_free": result.get("is_gluten_free", False),
                        "is_food": result.get("is_food", True),
                        "allergens": result.get("allergens", []),
                    }
                    classified += 1

                for name in retry_batch[received:]:
                    retry_counts[name] += 1
                    if retry_counts[name] >= MAX_RETRIES:
                        print(f"  WAARSCHUWING: '{name}' na {MAX_RETRIES}x gemist — opgeslagen als unclassified")
                        cache[name.lower()] = {
                            "name": name,
                            "brand_name": "GEEN",
                            "brand_type": "geen_merk",
                            "category_l1": None,
                            "category_l2": None,
                            "category_l3": None,
                            "normalized_name": None,
                            "is_bio": False,
                            "is_vegan": False,
                            "is_vegetarian": False,
                            "is_lactose_free": False,
                            "is_gluten_free": False,
                            "is_food": True,
                            "allergens": [],
                            "unclassified": True,
                        }
                    else:
                        next_pending.append(name)

                requests_today += 1
                state["requests_today"] = requests_today
                i += RETRY_BATCH  # volgende mini-batch

            except Exception as exc:
                last_request_time = time.monotonic()
                exc_str = str(exc)

                if "GenerateRequestsPerDayPerProjectPerModel" in exc_str:
                    save_cache(cache)
                    save_state(state)
                    print(f"\nDagquota bereikt tijdens retries.")
                    print_summary(cache, state, provider)
                    return

                m = re.search(r"retryDelay.*?(\d+)s", exc_str)
                if m:
                    retry_delay = int(m.group(1)) + 2
                    print(f"  Rate limit (429), wacht {retry_delay}s...")
                    time.sleep(retry_delay)
                    continue  # i niet opgehoogd, zelfde mini-batch opnieuw

                print(f"  ERROR retry batch: {exc}")
                for name in retry_batch:
                    retry_counts[name] += 1
                    if retry_counts[name] >= MAX_RETRIES:
                        cache[name.lower()] = {
                            "name": name,
                            "brand_name": "GEEN",
                            "brand_type": "geen_merk",
                            "category_l1": None,
                            "category_l2": None,
                            "category_l3": None,
                            "normalized_name": None,
                            "is_bio": False,
                            "is_vegan": False,
                            "is_vegetarian": False,
                            "is_lactose_free": False,
                            "is_gluten_free": False,
                            "is_food": True,
                            "allergens": [],
                            "unclassified": True,
                        }
                    else:
                        next_pending.append(name)
                i += RETRY_BATCH

        pending = [name for name in next_pending if name.lower() not in cache]

    save_cache(cache)
    save_state(state)
    print(f"\nGeclassificeerd: {classified}  |  Fouten: {errors}")
    print_summary(cache, state, provider)


if __name__ == "__main__":
    main()
