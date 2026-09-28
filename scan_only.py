"""
READ-ONLY scan: existing binance_helper.py ke signals use karke "abhi pump
hone se pehle" wale candidates dhoondta hai. Koi order/trade nahi lagata,
koi Gemini call nahi. Sirf Binance market data (public + account-read) dekhta hai.
"""

import binance_helper
import config

client = binance_helper.get_client()

print("Scanning top gainers + priority tokens (read-only)...\n")

gainers = binance_helper.get_top_gainers(client, limit=15, min_volume_usdt=config.MIN_VOLUME_USDT)
gainer_symbols = {g["symbol"] for g in gainers}

priority = binance_helper.get_priority_tickers(client, config.PRIORITY_TOKENS, min_volume_usdt=config.MIN_VOLUME_USDT)

candidates = list(gainers) + [p for p in priority if p["symbol"] not in gainer_symbols]

results = []
for t in candidates:
    symbol = t["symbol"]
    try:
        a = binance_helper.analyze_token(client, symbol, ticker_data=t)
    except Exception as e:
        print(f"[skip] {symbol}: {e}")
        continue
    results.append(a)

def score(a):
    s = 0
    if a.get("accumulation_pattern"):
        s += 2
    if a.get("volume_spike"):
        s += 2
    if a.get("taker_buy_ratio_pct") and a["taker_buy_ratio_pct"] >= config.MIN_TAKER_BUY_RATIO_PCT:
        s += 1
    if a.get("trend_1h") == "up":
        s += 1
    if a.get("trend_4h") == "up":
        s += 1
    if a.get("rsi") and a["rsi"] < config.RSI_OVERBOUGHT_THRESHOLD:
        s += 1
    return s

results.sort(key=score, reverse=True)

print(f"{'Symbol':<12}{'Price':<14}{'24hChg%':<10}{'RSI':<8}{'AccumPat':<10}{'VolSpike':<10}{'Taker%':<9}{'Trend1h':<8}{'Score'}")
for a in results[:12]:
    print(
        f"{a['symbol']:<12}{a['price']:<14}{a['change_24h_pct']:<10}"
        f"{(a['rsi'] or 0):<8.1f}{str(a.get('accumulation_pattern')):<10}"
        f"{str(a.get('volume_spike')):<10}{(a.get('taker_buy_ratio_pct') or 0):<9.1f}"
        f"{str(a.get('trend_1h')):<8}{score(a)}"
    )

print("\nNote: Yeh sirf pattern-based signal hai (accumulation + volume spike + trend), guarantee nahi.")
print("AccumPat=True aur VolSpike=True wale coins 'abhi build up ho rahe' lagte hain, pehle se pump nahi hue.")
