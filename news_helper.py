"""
news_helper.py
---------------
cryptocurrency.cv se recent news leta hai — bilkul FREE, koi API key
nahi chahiye. Ek coin ke baare mein recent headlines dhoondh kar
Gemini ko deta hai, taake wo apni analysis mein news bhi shamil kare.
"""

import requests

NEWS_API_URL = "https://cryptocurrency.cv/api/news"
REQUEST_TIMEOUT = 25


def get_recent_news(coin_base_symbol, limit=5):
    """
    Ek coin ke baare mein recent news headlines leta hai.

    coin_base_symbol: jaise "BTC", "ETH" (symbol ka base hissa, "USDT" ke bina)
    limit: kitni headlines chahiye

    Return: list of headline strings, ya khali list agar kuch na mile/error aaye.
    """
    try:
        response = requests.get(NEWS_API_URL, timeout=REQUEST_TIMEOUT)
        if response.status_code != 200:
            print(f"[NEWS] API returned status {response.status_code}")
            return []

        data = response.json()
        articles = data.get("articles") or data.get("data") or data if isinstance(data, list) else []

        matched = []
        coin_upper = coin_base_symbol.upper()

        for article in articles:
            title = article.get("title") or article.get("headline") or ""
            tags = article.get("coins") or article.get("tags") or []
            tags_upper = [str(t).upper() for t in tags] if isinstance(tags, list) else []

            # Match karo agar coin symbol title mein ho, ya tags mein ho
            if coin_upper in title.upper() or coin_upper in tags_upper:
                matched.append(title)

            if len(matched) >= limit:
                break

        return matched

    except requests.RequestException as e:
        print(f"[NEWS] Fetch failed: {e}")
        return []
    except (ValueError, KeyError) as e:
        print(f"[NEWS] Parse failed: {e}")
        return []


def get_coin_base_symbol(binance_symbol):
    """'AVAXUSDT' se 'AVAX' nikalta hai (USDT hata kar)."""
    if binance_symbol.endswith("USDT"):
        return binance_symbol[:-4]
    return binance_symbol
