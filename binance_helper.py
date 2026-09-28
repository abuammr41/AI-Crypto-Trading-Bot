"""
binance_helper.py
------------------
Binance se saara lena-dena isi file se hota hai:
- balance check karna
- price lena
- top gainers dhoondhna
- order place karna (market buy, stop-market sell)

Yahan bhi safety checks hain (jaise price sanity check) taake
koi glitch data se galat trade na ho jaye.
"""

from binance.client import Client
from binance.exceptions import BinanceAPIException
import config
import re
from datetime import datetime, timezone


def get_client():
    """Binance client banata hai, API keys config.py se leta hai.
    Timeout 25 second rakha hai (default 10 se zyada) — slow network
    mein bhi request fail hone se pehle thoda zyada wait kare."""
    return Client(config.BINANCE_API_KEY, config.BINANCE_API_SECRET, requests_params={"timeout": 25})


def get_free_usdt_balance(client):
    """Available (free) USDT balance return karta hai."""
    try:
        balance = client.get_asset_balance(asset="USDT")
        return float(balance["free"])
    except Exception as e:  # network timeout bhi (sirf Binance error nahi)
        print(f"[ERROR] Balance fetch failed: {e}")
        return None


def get_current_price(client, symbol):
    """
    Ek coin ka current price leta hai.
    Sanity check: agar price 0 ya negative ho (glitch), None return karta hai.
    """
    try:
        ticker = client.get_symbol_ticker(symbol=symbol)
        price = float(ticker["price"])
        if price <= 0:
            print(f"[WARNING] Sanity check fail: {symbol} price = {price}, ignoring.")
            return None
        return price
    except Exception as e:  # network timeout bhi (sirf Binance error nahi)
        print(f"[ERROR] Price fetch failed for {symbol}: {e}")
        return None


def get_btc_1h_change_pct(client):
    """
    BTC ka pichle 1 ghante ka % change nikalta hai.
    Market-crash rule ke liye use hota hai.
    """
    try:
        klines = client.get_klines(symbol="BTCUSDT", interval="1h", limit=2)
        if len(klines) < 2:
            return 0.0
        open_price = float(klines[-1][1])
        current_price = float(klines[-1][4])
        change_pct = ((current_price - open_price) / open_price) * 100
        return change_pct
    except BinanceAPIException as e:
        print(f"[ERROR] BTC change fetch failed: {e}")
        return 0.0


def get_recent_exit_price(client, symbol, expected_qty, lookback=20):
    """
    Jab koi position "dust" ki wajah se close detect ho (matlab asal
    OCO fill humne miss kar li), ye function Binance ki apni TRADE
    HISTORY se dhoondh kar asal exit price nikalta hai — taake exact
    guess ki bajaye SAHI P/L record ho sake.

    Recent SELL trades (is symbol ke) ko time ke hisaab se (naye se
    purane) jama karta hai jab tak cumulative quantity expected_qty
    ke qareeb na pahunch jaye — phir un trades ka weighted-average
    price deta hai.

    Return: average exit price (float), ya None agar na mil sake
            (is soorat mein purana "unknown P/L" wala fallback chalega).
    """
    try:
        trades = client.get_my_trades(symbol=symbol, limit=lookback)
    except BinanceAPIException as e:
        print(f"[WARN] Trade history fetch fail hui {symbol} ke liye: {e}")
        return None

    if not trades:
        return None

    # Naye se purane sort karo (Binance usually naye-purane order mein
    # deta hai, lekin pakka karne ke liye khud bhi sort kar lete hain)
    sell_trades = sorted(
        [t for t in trades if not t.get("isBuyer", True)],
        key=lambda t: t["time"],
        reverse=True,
    )

    if not sell_trades:
        return None

    total_qty = 0.0
    total_value = 0.0

    for trade in sell_trades:
        qty = float(trade["qty"])
        price = float(trade["price"])
        total_qty += qty
        total_value += qty * price

        if total_qty >= expected_qty * 0.95:  # 95% tak match ho to kaafi hai
            break

    if total_qty == 0:
        return None

    return total_value / total_qty  # weighted average price


def get_all_usdt_symbols(client):
    """
    Binance par saare TRADING USDT pairs ki list deta hai (jaise
    {"BTCUSDT", "ETHUSDT", ...}) — dynamic priority list ke liye
    zaroori hai, taake sirf wahi coins consider hon jo Binance par
    asal mein trade ho sakte hain.
    """
    try:
        info = client.get_exchange_info()
        symbols = set()
        for s in info["symbols"]:
            if s["quoteAsset"] == "USDT" and s["status"] == "TRADING":
                symbols.add(s["symbol"])
        return symbols
    except Exception as e:  # network timeout bhi (sirf Binance error nahi)
        print(f"[ERROR] get_all_usdt_symbols failed: {e}")
        return set()


def get_priority_tickers(client, symbols, min_volume_usdt=500000):
    """
    Priority list (config.PRIORITY_TOKENS ya dynamic CoinGecko list) ke
    coins ki current ticker data leta hai — sirf wahi jo humari
    price range (config.MIN/MAX_COIN_PRICE_USDT) aur volume filter
    pass karte hon. Ye check GENERIC hai — kisi bhi coin (static list
    ho ya dynamic CoinGecko se aaye) ke liye kaam karta hai, taake
    "bare/mehnge coins" (jaise BTC, ETH) baar baar downstream mein
    "SKIP price range" na banein — yahin pehle hi filter ho jate hain.
    """
    tickers = []
    for symbol in symbols:
        try:
            ticker = client.get_ticker(symbol=symbol)
            price = float(ticker["lastPrice"])

            if price > config.MAX_COIN_PRICE_USDT or price < config.MIN_COIN_PRICE_USDT:
                continue  # range se bahar — kisi bhi coin ke liye generic check

            if float(ticker["quoteVolume"]) >= min_volume_usdt:
                tickers.append(ticker)
        except Exception:  # network timeout bhi — sirf ye coin skip
            continue  # symbol shayad delist ho gaya ho, ya typo ho — skip karo
    return tickers


def get_top_gainers(client, limit=10, min_volume_usdt=500000):
    """
    Top gainer USDT pairs dhoondhta hai, low-liquidity coins aur
    price-range se bahar wale coins chhod kar (generic filter, kisi
    bhi coin ke liye — taake mehnge coins jaise BTC/ETH "top gainer"
    ban kar humari limited slots (jaise top-5) waste na karein).
    """
    try:
        tickers = client.get_ticker()
        usdt_pairs = [
            t for t in tickers
            if t["symbol"].endswith("USDT")
            and float(t.get("quoteVolume", 0)) >= min_volume_usdt
            and config.MIN_COIN_PRICE_USDT <= float(t.get("lastPrice", 0)) <= config.MAX_COIN_PRICE_USDT
        ]
        sorted_pairs = sorted(
            usdt_pairs, key=lambda t: float(t["priceChangePercent"]), reverse=True
        )
        return sorted_pairs[:limit]
    except Exception as e:  # network timeout bhi (sirf Binance error nahi)
        print(f"[ERROR] Top gainers fetch failed: {e}")
        return []


def calculate_atr(client, symbol, period=14, interval="1h"):
    """
    ATR (Average True Range) calculate karta hai — coin ki "normal"
    volatility ka measure. True Range = din ke andar price kitna
    "ghooma" (high-low, ya pichle close se gap). ATR in sabka average hai.

    Zyada ATR = coin zyada "jumpy" hai (wider stop chahiye).
    Kam ATR = coin "quiet" hai (tight stop bhi kaafi hai).

    Return: ATR value (price ki units mein, jaise $0.002), ya None
            agar data na mile.
    """
    try:
        klines = client.get_klines(symbol=symbol, interval=interval, limit=period + 1)
        if len(klines) < period + 1:
            return None

        true_ranges = []
        for i in range(1, len(klines)):
            high = float(klines[i][2])
            low = float(klines[i][3])
            prev_close = float(klines[i - 1][4])

            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close),
            )
            true_ranges.append(tr)

        return sum(true_ranges) / len(true_ranges)
    except BinanceAPIException as e:
        print(f"[ERROR] ATR calculation failed for {symbol}: {e}")
        return None


def calculate_hybrid_stop_pct(entry_price, support_price, atr_value):
    """
    HYBRID STOP-LOSS: teen tareekon mein se sabse "wide" (safe)
    percentage nikalta hai — fixed % ki jagah, har coin ki apni
    support-level aur volatility ke hisaab se.

    1. config.MIN_STOP_LOSS_PCT — hamesha itna to hoga hi (floor)
    2. Support-based — support se config.SUPPORT_STOP_BUFFER_PCT
       aur neeche (stop-hunting se bachne ke liye)
    3. ATR-based — coin ki apni "normal" movement (config.ATR_MULTIPLIER
       guna ATR)

    Result hamesha config.MAX_LOSS_PER_TRADE_PCT se kam ya barabar
    rakha jata hai (hard ceiling, kabhi cross nahi hota).

    Return: final stop-loss percentage (float), config ke MIN aur
            MAX ke beech guaranteed.
    """
    candidates = [config.MIN_STOP_LOSS_PCT]

    if support_price is not None and 0 < support_price < entry_price:
        support_distance_pct = ((entry_price - support_price) / entry_price) * 100
        candidates.append(support_distance_pct + config.SUPPORT_STOP_BUFFER_PCT)

    if atr_value is not None and atr_value > 0 and entry_price > 0:
        atr_distance_pct = (atr_value * config.ATR_MULTIPLIER / entry_price) * 100
        candidates.append(atr_distance_pct)

    widest = max(candidates)
    return min(widest, config.MAX_LOSS_PER_TRADE_PCT)


def calculate_rsi(client, symbol, period=14, interval="1h"):
    """
    RSI (Relative Strength Index) calculate karta hai.
    RSI 0-100 ke beech hota hai. 70+ ka matlab hai "overbought"
    (bohot upar ja chuka, correction ka risk zyada).

    Return: RSI value (float), ya None agar calculate na ho sake.
    """
    try:
        klines = client.get_klines(symbol=symbol, interval=interval, limit=period + 1)
        if len(klines) < period + 1:
            return None

        closes = [float(k[4]) for k in klines]

        gains = []
        losses = []
        for i in range(1, len(closes)):
            change = closes[i] - closes[i - 1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))

        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period

        if avg_loss == 0:
            return 100.0  # sab gains hi the, no losses

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    except BinanceAPIException as e:
        print(f"[ERROR] RSI calculation failed for {symbol}: {e}")
        return None


def calculate_mfi(client, symbol, period=14, interval="1h"):
    """
    MFI (Money Flow Index) calculate karta hai — RSI jaisa hi hai, lekin
    VOLUME ko bhi shamil karta hai. Isse pata chalta hai ke price move
    ke peeche "asli paisa" (volume) bhi hai ya nahi.

    MFI 0-100 ke beech. 80+ = overbought, 20- = oversold.

    Return: MFI value (float), ya None agar calculate na ho sake.
    """
    try:
        klines = client.get_klines(symbol=symbol, interval=interval, limit=period + 1)
        if len(klines) < period + 1:
            return None

        typical_prices = []
        volumes = []
        for k in klines:
            high, low, close, volume = float(k[2]), float(k[3]), float(k[4]), float(k[5])
            typical_price = (high + low + close) / 3
            typical_prices.append(typical_price)
            volumes.append(volume)

        positive_flow = 0.0
        negative_flow = 0.0

        for i in range(1, len(typical_prices)):
            raw_money_flow = typical_prices[i] * volumes[i]
            if typical_prices[i] > typical_prices[i - 1]:
                positive_flow += raw_money_flow
            elif typical_prices[i] < typical_prices[i - 1]:
                negative_flow += raw_money_flow

        if negative_flow == 0:
            return 100.0

        money_flow_ratio = positive_flow / negative_flow
        mfi = 100 - (100 / (1 + money_flow_ratio))
        return mfi
    except BinanceAPIException as e:
        print(f"[ERROR] MFI calculation failed for {symbol}: {e}")
        return None


def calculate_taker_buy_ratio(client, symbol, interval="1h", limit=14):
    """
    Buyer vs Seller activity — kitna % volume "taker buy" (market buy orders)
    se aaya, total volume mein se. Zyada % matlab buyers zyada active hain
    (bullish signal).

    Return: ratio (0-100), ya None agar calculate na ho sake.
    """
    try:
        klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
        if not klines:
            return None

        total_volume = sum(float(k[5]) for k in klines)
        taker_buy_volume = sum(float(k[9]) for k in klines)  # index 9 = taker buy base volume

        if total_volume == 0:
            return None

        return (taker_buy_volume / total_volume) * 100
    except BinanceAPIException as e:
        print(f"[ERROR] Taker buy ratio failed for {symbol}: {e}")
        return None


def get_support_resistance(client, symbol, interval="1h", limit=48):
    """
    Simple support/resistance nikalta hai — pichle N candles ka
    highest high (resistance) aur lowest low (support).

    Return: dict {"support": float, "resistance": float, "distance_to_resistance_pct": float}
            ya None agar data na mile.
    """
    try:
        klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
        if not klines:
            return None

        highs = [float(k[2]) for k in klines]
        lows = [float(k[3]) for k in klines]
        current_price = float(klines[-1][4])

        resistance = max(highs)
        support = min(lows)

        distance_to_resistance_pct = ((resistance - current_price) / current_price) * 100

        return {
            "support": support,
            "resistance": resistance,
            "distance_to_resistance_pct": distance_to_resistance_pct,
        }
    except BinanceAPIException as e:
        print(f"[ERROR] Support/resistance failed for {symbol}: {e}")
        return None


def get_order_book_summary(client, symbol, depth_limit=20):
    """
    Order book depth ka summary — kitna buy vs sell pressure hai
    pending orders mein (abhi tak execute nahi hue, sirf lagaye hue).

    Return: dict {"bid_volume": float, "ask_volume": float, "buy_sell_ratio": float}
            ya None agar data na mile.
    """
    try:
        book = client.get_order_book(symbol=symbol, limit=depth_limit)

        bid_volume = sum(float(qty) for _, qty in book["bids"])
        ask_volume = sum(float(qty) for _, qty in book["asks"])

        if ask_volume == 0:
            buy_sell_ratio = 100.0
        else:
            buy_sell_ratio = (bid_volume / (bid_volume + ask_volume)) * 100

        return {
            "bid_volume": bid_volume,
            "ask_volume": ask_volume,
            "buy_sell_ratio": buy_sell_ratio,  # zyada ho to buy-side zyada mazboot
        }
    except BinanceAPIException as e:
        print(f"[ERROR] Order book fetch failed for {symbol}: {e}")
        return None


def get_trend_direction(client, symbol, interval="1h", lookback=10):
    """
    Simple trend direction nikalta hai ek timeframe par — recent closes ka
    average lekar, kya price us average se upar hai (bullish) ya neeche
    (bearish). Multi-timeframe analysis ke liye use hota hai (1h/4h/1d).

    Return: "bullish", "bearish", ya None agar data na mile.
    """
    try:
        klines = client.get_klines(symbol=symbol, interval=interval, limit=lookback + 1)
        if len(klines) < lookback + 1:
            return None

        closes = [float(k[4]) for k in klines]
        current_price = closes[-1]
        avg_price = sum(closes[:-1]) / len(closes[:-1])

        return "bullish" if current_price >= avg_price else "bearish"
    except BinanceAPIException as e:
        print(f"[ERROR] Trend direction failed for {symbol} ({interval}): {e}")
        return None


def _closed_klines(client, symbol, interval, count):
    """
    Sirf BAND (closed) candles deta hai — abhi ban rahi (adhoori) candle
    hata deta hai. Professional traders ka usool: faisla sirf band candle
    par, kyunki adhoori candle aakhri minute mein palat sakti hai.
    Binance ki aakhri kline aksar abhi khuli hoti hai (close-time future
    mein) — usko close-time dekh kar pehchan kar nikalte hain.
    Return: list (purani se nayi), ya [] agar data na mile.
    """
    klines = client.get_klines(symbol=symbol, interval=interval, limit=count + 1)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    closed = [k for k in klines if int(k[6]) < now_ms]
    return closed[-count:]


def detect_volume_spike(client, symbol, interval="1h", lookback=10, multiplier=2.0):
    """
    Check karta hai ke current candle ka volume, pichle candles ke average se
    "multiplier" guna (ya zyada) hai ya nahi — bara volume spike matlab
    koi bara player (whale/institution) active ho sakta hai.

    Return: True/False, ya None agar data na mile.
    """
    try:
        # Sirf band candles — adhoori candle ka volume hamesha kam hota
        # hai (ghanta abhi poora nahi hua), usse galat natija aata tha
        klines = _closed_klines(client, symbol, interval, lookback + 1)
        if len(klines) < lookback + 1:
            return None

        volumes = [float(k[5]) for k in klines]
        current_volume = volumes[-1]
        avg_volume = sum(volumes[:-1]) / len(volumes[:-1])

        if avg_volume == 0:
            return False

        return current_volume >= (avg_volume * multiplier)
    except BinanceAPIException as e:
        print(f"[ERROR] Volume spike check failed for {symbol}: {e}")
        return None


def detect_accumulation(client, symbol, interval="1h", lookback=10, max_range_pct=3.0):
    """
    Accumulation pattern dhoondta hai — price "flat" (chhoti range mein)
    raha ho pichle N candles mein, jabke volume trend upar ja raha ho.
    Ye "bade log chup-chap khareed rahe hain" ka signal hai.

    Return: True/False, ya None agar data na mile.
    """
    try:
        klines = client.get_klines(symbol=symbol, interval=interval, limit=lookback)
        if len(klines) < lookback:
            return None

        highs = [float(k[2]) for k in klines]
        lows = [float(k[3]) for k in klines]
        volumes = [float(k[5]) for k in klines]

        price_high = max(highs)
        price_low = min(lows)
        price_range_pct = ((price_high - price_low) / price_low) * 100 if price_low > 0 else 999

        # Volume trend: pichla hissa vs agla hissa compare karo
        half = len(volumes) // 2
        first_half_avg = sum(volumes[:half]) / half if half > 0 else 0
        second_half_avg = sum(volumes[half:]) / (len(volumes) - half)

        volume_increasing = second_half_avg > first_half_avg

        return price_range_pct <= max_range_pct and volume_increasing
    except BinanceAPIException as e:
        print(f"[ERROR] Accumulation check failed for {symbol}: {e}")
        return None


def detect_candle_pattern(client, symbol, interval="1h"):
    """
    Recent candle ka pattern dekhta hai — 4 patterns check karta hai:

    Single-candle patterns:
    - Hammer: neeche wala "baal/wick" lamba (bullish reversal)
    - Shooting Star: upar wala wick lamba (bearish reversal)

    Two-candle patterns (pichli aur abhi wali candle compare karta hai):
    - Bullish Engulfing: chhoti laal candle ke baad bari hari candle
      jo pichli ko poori tarah "nigal" (engulf) le — strong upar jane
      ka signal
    - Bearish Engulfing: chhoti hari candle ke baad bari laal candle
      jo pichli ko poori tarah nigal le — strong neeche jane ka signal

    Return: "hammer", "shooting_star", "bullish_engulfing",
            "bearish_engulfing", "neutral", ya None agar data na mile.
    """
    try:
        # Sirf aakhri 2 BAND candles (adhoori candle par pattern pakka nahi hota)
        klines = _closed_klines(client, symbol, interval, 2)
        if len(klines) < 2:
            return None

        prev_k, curr_k = klines[-2], klines[-1]
        prev_open, prev_close = float(prev_k[1]), float(prev_k[4])
        open_p, high, low, close = float(curr_k[1]), float(curr_k[2]), float(curr_k[3]), float(curr_k[4])

        # ---- Pehle Engulfing check karo (do-candle pattern) ----
        prev_is_red = prev_close < prev_open
        prev_is_green = prev_close > prev_open
        curr_is_green = close > open_p
        curr_is_red = close < open_p

        if prev_is_red and curr_is_green and close >= prev_open and open_p <= prev_close:
            return "bullish_engulfing"

        if prev_is_green and curr_is_red and open_p >= prev_close and close <= prev_open:
            return "bearish_engulfing"

        # ---- Phir Hammer/Shooting Star check karo (single-candle) ----
        body = abs(close - open_p)
        upper_wick = high - max(open_p, close)
        lower_wick = min(open_p, close) - low
        total_range = high - low

        if total_range == 0:
            return "neutral"

        # Hammer: lower wick bara (kam se kam 2x body), upper wick chhota
        if lower_wick >= body * 2 and upper_wick <= body * 0.5:
            return "hammer"

        # Shooting star: upper wick bara, lower wick chhota
        if upper_wick >= body * 2 and lower_wick <= body * 0.5:
            return "shooting_star"

        return "neutral"
    except BinanceAPIException as e:
        print(f"[ERROR] Candle pattern check failed for {symbol}: {e}")
        return None


def analyze_token(client, symbol, ticker_data=None):
    """
    EK function jo ek coin ke liye SAARI zaroori cheezein jama kar ke
    EK dictionary mein wapas deta hai — main.py ko har cheez ke liye
    alag alag function call karne ki zaroorat nahi, sirf ye ek call kaafi hai.

    Andar se Binance ko multiple calls lagti hain (Binance ka system aisa
    hi hai), lekin bahar se (main.py ke liye) ye EK hi function call hai.

    Shamil hai: price/volume, RSI, MFI, support/resistance, order book,
    buyer/seller ratio, multi-timeframe trend (1h/4h/1d), volume spike,
    aur accumulation pattern.

    ticker_data: agar already get_top_gainers se ticker mil chuka ho, to
                 dobara Binance call bachane ke liye yahan pass kar sakte ho.

    Return: dict jisme sab kuch shamil hai.
    """
    if ticker_data is None:
        ticker_data = client.get_ticker(symbol=symbol)

    sr = get_support_resistance(client, symbol)
    ob = get_order_book_summary(client, symbol)

    result = {
        "symbol": symbol,
        "price": float(ticker_data["lastPrice"]),
        "change_24h_pct": float(ticker_data["priceChangePercent"]),
        "volume_usdt": float(ticker_data["quoteVolume"]),
        "rsi": calculate_rsi(client, symbol),
        "mfi": calculate_mfi(client, symbol),
        "taker_buy_ratio_pct": calculate_taker_buy_ratio(client, symbol),
        "support": sr["support"] if sr else None,
        "resistance": sr["resistance"] if sr else None,
        "distance_to_resistance_pct": sr["distance_to_resistance_pct"] if sr else None,
        "order_book_buy_sell_ratio_pct": ob["buy_sell_ratio"] if ob else None,
        # Multi-timeframe trend (top-down: 1d bara picture, 4h confirmation, 1h entry timing)
        "trend_1h": get_trend_direction(client, symbol, interval="1h"),
        "trend_4h": get_trend_direction(client, symbol, interval="4h"),
        "trend_1d": get_trend_direction(client, symbol, interval="1d"),
        # Smart-money style signals
        "volume_spike": detect_volume_spike(client, symbol),
        "accumulation_pattern": detect_accumulation(client, symbol),
        "candle_pattern": detect_candle_pattern(client, symbol),
    }
    return result


def get_symbol_step_size(client, symbol):
    """Coin ki quantity kitne decimal places tak allowed hai, ye nikalta hai."""
    try:
        info = client.get_symbol_info(symbol)
        for f in info["filters"]:
            if f["filterType"] == "LOT_SIZE":
                return float(f["stepSize"])
    except Exception as e:
        print(f"[ERROR] Step size fetch failed for {symbol}: {e}")
    return None


from decimal import Decimal


def _decimal_places(step_or_tick):
    """
    Ek tick/step size (jaise 0.00001) se decimal places count karta hai —
    Decimal use karta hai taake scientific notation (1e-05 jaisi values,
    jo bahut chhoti tick size wale coins mein aam hai) sahi handle ho.
    Purana tarika (string split on ".") is se fail ho jata tha, jisse
    price/quantity galti se 0 tak round ho jati thi.
    """
    d = Decimal(str(step_or_tick)).normalize()
    exponent = d.as_tuple().exponent
    return max(0, -exponent) if isinstance(exponent, int) else 0


def round_step_size(quantity, step_size):
    """Quantity ko Binance ke allowed step size ke hisaab se round karta hai."""
    if step_size is None or step_size == 0:
        return quantity
    precision = _decimal_places(step_size)
    return round(quantity - (quantity % step_size), precision)


def _format_decimal(value, step_or_tick):
    """
    Value (quantity ya price) ko EK CLEAN STRING mein convert karta hai,
    step/tick size ke hisaab se sahi decimal places ke sath. Float ko
    seedha Binance ko bhejne se kabhi kabhi "repr" ke chhote farq aa
    sakte hain — explicit string formatting se ye risk hamesha ke liye
    khatam ho jata hai. Ye function saare order-placing calls mein
    consistently use hoti hai (quantity aur price dono ke liye).
    """
    if step_or_tick is None or step_or_tick == 0:
        return str(value)
    rounded = round_step_size(value, step_or_tick)
    precision = _decimal_places(step_or_tick)
    return f"{rounded:.{precision}f}"


def get_symbol_tick_size(client, symbol):
    """Coin ki PRICE tick size nikalta hai (PRICE_FILTER se) — quantity se alag hoti hai."""
    try:
        info = client.get_symbol_info(symbol)
        for f in info["filters"]:
            if f["filterType"] == "PRICE_FILTER":
                return float(f["tickSize"])
    except Exception as e:
        print(f"[ERROR] Tick size fetch failed for {symbol}: {e}")
    return None


def place_market_buy(client, symbol, usdt_amount):
    """
    Market buy order place karta hai, USDT amount ke hisaab se.
    Poore balance ka 99% use karte hain (1% buffer) — taake price
    fetch aur order execute hone ke beech thodi si movement (slippage)
    se order "insufficient balance" ki wajah se fail na ho.
    Return: order dict, ya None agar fail ho.
    """
    try:
        price = get_current_price(client, symbol)
        if price is None:
            return None

        safe_amount = usdt_amount * 0.99  # 1% buffer, slippage ke liye
        step_size = get_symbol_step_size(client, symbol)
        raw_qty = safe_amount / price
        qty_str = _format_decimal(raw_qty, step_size)

        if float(qty_str) <= 0:
            print(f"[ERROR] Calculated quantity is zero for {symbol}, skipping.")
            return None

        order = client.order_market_buy(symbol=symbol, quantity=qty_str)
        return order
    except BinanceAPIException as e:
        print(f"[ERROR] Buy order failed for {symbol}: {e}")
        return None


def place_oco_sell(client, symbol, quantity, take_profit_price, stop_price, stop_limit_price=None):
    """
    OCO (One-Cancels-Other) order — STOP-LOSS aur TAKE-PROFIT EK HI call
    mein lagta hai. Binance khud (exchange par, 24/7) dekhta hai konsa
    pehle hit hota hai — jo bhi pehle hit ho, dusra khud cancel ho jata hai.

    ZAROORI: Binance ne OCO API ka NAYA format laya hai jisme "aboveType"
    aur "belowType" batana MANDATORY hai (kaunsa leg kya type ka hai) —
    purana simple format (sirf price/stopPrice) ab kaam nahi karta.
    Isliye seedha naye endpoint (/api/v3/orderList/oco) ko generic
    signed-request se call kar rahe hain, taake python-binance library
    ke wrapper ki kisi bhi version-inconsistency se na juzein.

    Humari SELL OCO mein:
    - "above" leg = jab price UPAR jaye (take-profit) → LIMIT_MAKER
    - "below" leg = jab price NEECHE jaye (stop-loss) → STOP_LOSS_LIMIT

    stop_limit_price: agar na do, to stop_price se thoda neeche (0.5%)
                       khud calculate ho jata hai (stop-limit ka gap).
    """
    try:
        step_size = get_symbol_step_size(client, symbol)
        qty_str = _format_decimal(quantity, step_size)

        tick_size = get_symbol_tick_size(client, symbol)
        tp_price_str = _format_decimal(take_profit_price, tick_size)
        sl_stop_str = _format_decimal(stop_price, tick_size)

        if stop_limit_price is None:
            stop_limit_price = stop_price * 0.995  # thoda neeche, taake fill ho sake
        sl_limit_str = _format_decimal(stop_limit_price, tick_size)

        order = client._post(
            "orderList/oco",
            True,
            data={
                "symbol": symbol,
                "side": "SELL",
                "quantity": qty_str,
                "aboveType": "LIMIT_MAKER",
                "abovePrice": tp_price_str,
                "belowType": "STOP_LOSS_LIMIT",
                "belowStopPrice": sl_stop_str,
                "belowPrice": sl_limit_str,
                "belowTimeInForce": "GTC",
            },
        )
        return order
    except BinanceAPIException as e:
        print(f"[ERROR] OCO order failed for {symbol}: {e}")
        return None


def cancel_oco_order(client, symbol, order_list_id):
    """
    OCO order (dono legs) ek sath cancel karta hai.

    ZAROORI FIX: OCO cancel karne ka ALAG API endpoint hai
    (DELETE /api/v3/orderList) — normal single-order cancel
    (client.cancel_order) is ke liye kaam NAHI karta, kyunke wo
    /api/v3/order endpoint use karta hai jo "orderListId" parameter
    samajhta hi nahi (isi wajah se "-1104: not all params read" error
    aata tha). Ab client ka generic signed-request method use kar rahe
    hain, taake SAHI endpoint hit ho.

    Agar order already execute ho chuka ho (jaise momentum-exit aur OCO
    ek sath trigger ho jayein), Binance error dega — usko yahan hi
    handle karte hain, taake upar crash na ho.
    """
    try:
        client._delete("orderList", True, data={"symbol": symbol, "orderListId": order_list_id})
        return True
    except BinanceAPIException as e:
        print(f"[INFO] Cancel OCO — order shayad already executed/gone: {e}")
        return False


def get_order_list_status(client, symbol, order_list_id):
    """OCO order list ka status check karta hai (EXECUTING / ALL_DONE / REJECT)."""
    try:
        result = client.get_order_list(orderListId=order_list_id)
        return result.get("listOrderStatus")
    except Exception:
        return None


def cancel_order(client, symbol, order_id):
    """Ek existing order cancel karta hai (jaise purana stop hatana, naya lagane se pehle)."""
    try:
        client.cancel_order(symbol=symbol, orderId=order_id)
        return True
    except BinanceAPIException as e:
        print(f"[ERROR] Cancel order failed: {e}")
        return False


def market_sell_all(client, symbol, quantity):
    """Turant market price par pura position bech deta hai (emergency exit)."""
    try:
        step_size = get_symbol_step_size(client, symbol)
        qty_str = _format_decimal(quantity, step_size)
        order = client.order_market_sell(symbol=symbol, quantity=qty_str)
        return order
    except BinanceAPIException as e:
        print(f"[ERROR] Market sell failed for {symbol}: {e}")
        return None


def cleanup_dust_to_usdt(client, min_dust_usdt=0.01):
    """
    ROZ EK BAAR chalne ke liye (main.py daily-summary ke sath ise call
    karta hai) — pichle trades se bachi hui "dust" (chhoti si leftover
    quantities, jaise 0.03 XNO, 0.009 AVAX) ko automatically saaf karta
    hai:

    1. Saari non-USDT, non-BNB assets dhoondta hai jinki value bohot
       chhoti hai (dust)
    2. Binance ke apne "Dust Transfer" feature se unko EK SATH BNB mein
       convert karta hai (Binance API: POST /sapi/v1/asset/dust)
    3. Phir wo BNB bhi turant market-sell kar ke USDT mein convert kar
       deta hai — taake account mein sirf USDT (aur jo bhi active
       position hai) rahe, bikhri hui dust na rahe

    Binance ka apna rule: dust-transfer sirf har 6 ghante mein EK baar
    ho sakta hai — isliye ye function din mein ek baar hi call karna
    chahiye (jaisa daily-summary ke sath piggyback kiya hai).

    Return: True agar kuch convert hua, False agar kuch nahi tha ya fail hua.
    """
    try:
        account = client.get_account()
    except Exception as e:
        print(f"[WARN] Dust cleanup: account fetch fail hua: {e}")
        return False

    dust_assets = []
    for asset_info in account["balances"]:
        asset = asset_info["asset"]
        free = float(asset_info["free"])

        if asset in ("USDT", "BNB") or free <= 0:
            continue  # USDT already target hai, BNB alag se handle hoga

        price = get_current_price(client, f"{asset}USDT")
        if price is None:
            continue  # is asset ka USDT pair nahi hai, dust-transfer khud sambhal lega ya skip

        value_usdt = free * price
        if 0 < value_usdt < min_dust_usdt * 50:
            # Chhoti value wali assets hi "dust candidates" hain
            # (bohot bara threshold rakha hai taake genuine chhoti
            # positions accidentally na chali jayein — sirf asal
            # "bikhri hui dust" hi pakdi jaye)
            dust_assets.append(asset)

    if not dust_assets:
        print("[DUST] Koi dust nahi mila aaj — account saaf hai.")
        return False

    # "asset" parameter COMMA-SEPARATED STRING hona chahiye (Binance docs).
    # Agar koi EK asset itna chhota ho ke Binance usko bhi reject kare
    # (error -5005, "valuation ... too low"), to poora batch fail ho jata
    # hai. Isliye: jo asset reject ho, usko list se nikal kar baaki ke
    # sath dobara try karte hain (GENERIC — kisi coin ka naam hardcode
    # nahi, Binance ke error message se khud pehchanta hai).
    result = None
    for _attempt in range(5):
        if not dust_assets:
            print("[DUST] Saare dust assets Binance ki minimum limit se bhi chhote hain — skip.")
            return False
        try:
            result = client.transfer_dust(asset=",".join(dust_assets))
            break
        except BinanceAPIException as e:
            rejected = re.search(r"remaining (\w+) assets", str(e.message or ""))
            if e.code == -5005 and rejected and rejected.group(1) in dust_assets:
                print(f"[DUST] {rejected.group(1)} bohot chhota hai (Binance reject), usko chhod kar dobara try.")
                dust_assets.remove(rejected.group(1))
                continue
            print(f"[WARN] Dust transfer fail hua: {e}")
            return False
        except Exception as e:
            print(f"[WARN] Dust transfer fail hua: {e}")
            return False

    if result is None:
        print("[WARN] Dust transfer: kai koshishon ke baad bhi nahi hua.")
        return False

    total_bnb = result.get("totalTransfered", "0")
    print(f"[DUST] {len(dust_assets)} assets ({dust_assets}) BNB mein convert hui: ~{total_bnb} BNB")

    # Ab jo bhi BNB mila (dust se), usko turant USDT mein convert karo
    try:
        bnb_balance = client.get_asset_balance(asset="BNB")
        bnb_qty = float(bnb_balance["free"])
        if bnb_qty > 0:
            sell_order = market_sell_all(client, "BNBUSDT", bnb_qty)
            if sell_order:
                print(f"[DUST] {bnb_qty} BNB bhi USDT mein convert ho gaya.")
    except Exception as e:
        print(f"[WARN] BNB-to-USDT conversion fail hua (dust BNB mein hi rah gaya, koi nuksan nahi): {e}")

    return True