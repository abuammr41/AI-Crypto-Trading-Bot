"""
dynamic_priority.py
--------------------
Priority tokens (Ethereum/BNB/Solana chains) ab MANUAL list ki jagah
CoinGecko se KHUD-BA-KHUD fetch hote hain — roz naye "top volume" coins
mil jate hain in chains se, purani static list ko manually update nahi
karna padta.

CoinGecko ki free public API use karti hai (koi key nahi chahiye).
Rate-limit se bachne ke liye, list SIRF ROZ EK BAAR fetch hoti hai
(cache file mein save), har 20-minute cycle mein nahi — warna
CoinGecko ka free-tier rate limit jaldi khatam ho jata.
"""

import json
import os
from datetime import datetime, timezone
import requests

import config

CACHE_FILE = os.path.join(config.BASE_DIR, "priority_cache.json")
COINGECKO_URL = "https://api.coingecko.com/api/v3/coins/markets"
REQUEST_TIMEOUT = 20

CHAIN_CATEGORIES = ["ethereum-ecosystem", "binance-smart-chain", "solana-ecosystem"]


MAX_FETCH_ATTEMPTS_PER_DAY = 2  # isse zyada koshish nahi, chahe fail ho jaye


def get_dynamic_priority_symbols(all_binance_symbols, per_chain_limit=15):
    """
    Cache se aaj ki list milti hai agar already fetch ho chuki ho.
    Warna CoinGecko se naye fetch karta hai — lekin din mein sirf
    MAX_FETCH_ATTEMPTS_PER_DAY (2) baar hi koshish karta hai, chahe
    wo fail ho jayein. Isse baar baar timeout/error nahi aata —
    agar CoinGecko down ho, bot khamoshi se static fallback list par
    switch ho jata hai, poore din ke liye.

    all_binance_symbols: set of symbols jo Binance par actually trade
                          ho sakte hain (jaise {"BTCUSDT", "ETHUSDT", ...})
                          — taake sirf wahi tokens list mein aayen jo
                          humara bot asal mein trade kar sakta hai.

    Return: list of symbols jaise ["UNIUSDT", "CAKEUSDT", ...]
            Agar CoinGecko fail ho (ya attempts khatam ho chuke hon),
            khali list deta hai (crash nahi karta) — bot phir static
            fallback list ya normal gainers scan par depend kar leta hai.
    """
    cached = _load_cache()
    if cached is not None:
        return cached

    attempts_today = _get_attempts_today()
    if attempts_today >= MAX_FETCH_ATTEMPTS_PER_DAY:
        # Aaj ke attempts khatam — ab kal tak koshish nahi karenge
        return []

    _record_attempt()
    fresh = _fetch_from_coingecko(all_binance_symbols, per_chain_limit)

    if fresh:  # sirf successful (non-empty) result cache hota hai
        _save_cache(fresh)

    return fresh


def _get_attempts_today():
    """Aaj kitni baar CoinGecko fetch try ho chuka hai (success ya fail, dono count hote hain)."""
    if not os.path.exists(CACHE_FILE):
        return 0
    try:
        with open(CACHE_FILE, "r") as f:
            data = json.load(f)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if data.get("attempts_date") == today:
            return data.get("attempts_count", 0)
        return 0  # naya din, purane attempts count nahi hote
    except (json.JSONDecodeError, KeyError):
        return 0


def _record_attempt():
    """Ek attempt count kar deta hai (chahe result success ho ya fail)."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    existing = {}
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, OSError):
            existing = {}

    if existing.get("attempts_date") != today:
        existing = {"attempts_date": today, "attempts_count": 0}

    existing["attempts_count"] = existing.get("attempts_count", 0) + 1
    existing["attempts_date"] = today

    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(existing, f)
    except OSError as e:
        print(f"[WARN] Attempt tracking save failed: {e}")


def _load_cache():
    """Agar aaj ki cache (successful fetch) maujood hai, use load karta hai. Warna None."""
    if not os.path.exists(CACHE_FILE):
        return None

    try:
        with open(CACHE_FILE, "r") as f:
            data = json.load(f)

        cached_date = data.get("date")
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        if cached_date == today and data.get("symbols"):
            return data.get("symbols", [])
        return None  # purani cache hai ya kabhi successful fetch nahi hua
    except (json.JSONDecodeError, KeyError):
        return None


def _save_cache(symbols):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    existing = {}
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, OSError):
            existing = {}

    existing["date"] = today
    existing["symbols"] = symbols

    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(existing, f)
    except OSError as e:
        print(f"[WARN] Priority cache save failed: {e}")


def _fetch_from_coingecko(all_binance_symbols, per_chain_limit):
    """CoinGecko se har chain ke top-volume coins fetch karta hai."""
    collected = []

    for category in CHAIN_CATEGORIES:
        try:
            response = requests.get(
                COINGECKO_URL,
                params={
                    "vs_currency": "usd",
                    "category": category,
                    "order": "volume_desc",
                    "per_page": per_chain_limit,
                    "page": 1,
                },
                timeout=REQUEST_TIMEOUT,
            )
            if response.status_code != 200:
                print(f"[WARN] CoinGecko {category} fetch failed: status {response.status_code}")
                continue

            coins = response.json()
            for coin in coins:
                symbol = coin.get("symbol", "").upper() + "USDT"
                if symbol in all_binance_symbols and symbol not in collected:
                    collected.append(symbol)

        except requests.RequestException as e:
            print(f"[WARN] CoinGecko {category} fetch failed: {e}")
            continue  # is chain ko skip karo, baaki chains try karo

    return collected
