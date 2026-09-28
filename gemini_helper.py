"""
gemini_helper.py
-----------------
Gemini ko EK HI call mein SAARE candidate coins ek sath diye jate hain
(alag alag calls nahi, taake baar baar API hit na ho aur error/timeout
ka chance kam ho). Gemini khud inme se BEST coin choose karta hai (ya
kisi mein bhi entry na le), aur agar BUY choose kare to take-profit %
bhi suggest karta hai.

Gemini kabhi order size, stop-loss %, ya koi HARD risk rule decide nahi
karta — wo sab config.py mein fixed hai.

Gemini ka jawab hamesha VALIDATE hota hai. Agar jawab expected format mein
na ho, to use ignore kar diya jata hai (safe default: skip).
"""

from datetime import datetime, timezone

import google.genai as genai
import config

_client = genai.Client(api_key=config.GEMINI_API_KEY)
_MODEL_NAME = "gemini-3.5-flash-lite"  # budget tier — behtar free-tier limit "gemini-3.6-flash" (sirf 20/din) se

VALID_ACTIONS = {"BUY", "SKIP"}

# Agar web-search quota khatam ho ya search support na ho, us din ke
# liye search khud band ho jati hai (har cycle bekaar fail na ho)
_search_off_date = None

_INSTRUCTIONS = """BUY sirf tab likhna jab kisi EK coin ka setup genuinely acha ho — clear
uptrend, achi volume, support ke qareeb ya resistance se dur. RSI/MFI
overbought (70-80+, 80-85+, ya isse zyada) hona apne aap mein SKIP ki
wajah NAHI — high-volatility coins (jo aksar hamare price range mein
hote hain) mein RSI/MFI 85-95 tak bhi normal hai jab tak wo genuinely
strong momentum ke sath upar bhaag rahe hon (achi volume, buyers
active, koi reversal candle na ho). Sirf tab ehtiyaat karo jab RSI/MFI
bahut extreme (95+) ho AUR sath mein koi reversal signal bhi ho
(jaise shooting_star candle, ya momentum kamzor padna) — tab dono
milkar risky hote hain, akela high RSI/MFI nahi. Buyer/seller ratio
bhi ek factor hai, hard rule nahi. Candle pattern dekho: "hammer" ya
"bullish_engulfing" bullish reversal signal hain (achi baat, especially
support ke qareeb), "shooting_star" ya "bearish_engulfing" bearish
reversal hain (ehtiyaat karo). Multi-timeframe
trend (1h/4h/1d) dekho — agar 1D/4H bullish hain lekin 1H thoda
bearish/neutral hai, ye PULLBACK ho sakta hai (bara trend ke andar
chhoti dip) — achi entry ho sakti hai agar price support/hammer ke
qareeb ruk raha ho. Lekin agar SAB teeno timeframes bearish hain ya
momentum tezi se neeche ja raha ho, zyada ehtiyaat rakho — normally
aisi soorat mein SKIP behtar hai, lekin agar koi BAHUT strong reversal
signal ho (jaise perfect hammer, ya bahut mazboot support par bounce,
sath volume spike bhi ho), to entry consider kar sakte ho — final
faisla overall confluence dekh kar khud karo. Volume
spike aur accumulation pattern "smart money" active hone ka acha
signal hain. Agar koi recent_news di gayi hai, use bhi dekho. Agar
"watch_history" diya hai (coin subah se watch ho raha tha — subah se ab
tak ka chhota summary), use zaroor dekho: jo coin subah se LAGATAR
stable/upar ja raha ho us par zyada bharosa rakho; jo subah gira aur
abhi achanak uchla ho us par ehtiyaat (aksar fake move hota hai). Overall
market strong ho to thoda flexible
raho, lekin bilkul weak/risky setup wale coin ko mat chuno.

Agar EK SE ZYADA coins achhe lagein, sabse BEHTAR wala choose karo
(sabse zyada confluence — trend, volume, candle, news, sab match kare).
Agar KOI bhi coin genuinely acha nahi lagta, SKIP likhna (symbol khali
chhod do)."""


_SEARCH_NOTE = """

WEB SEARCH: Tumhare paas Google Search hai. Har candidate coin ke baare
mein PICHLE 24 GHANTE ki news dhoondo (listing/delisting, hack, token
unlock, partnership, Binance announcement, bara crash/pump ki wajah).
Crypto Craft, CoinDesk, Cointelegraph, The Block, Binance announcements
jaise bharosemand sources ko tarjeeh do. Buri news (hack, delisting,
bara unlock) ho to us coin ko SKIP karo. Agar kuch khaas news na mile
to sirf technical data par faisla karo. Jawab PHIR BHI sirf upar wali
char lines (ACTION/SYMBOL/REASON/TAKE_PROFIT) mein dena."""


def ask_best_trade(candidates):
    """
    Gemini ko EK HI call mein saare candidate coins deta hai, wo inme
    se BEST choose karta hai (ya kisi mein bhi entry na le).

    candidates: list of dicts, har ek binance_helper.analyze_token() se
                (plus "recent_news") — jitne bhi coins is cycle mein
                check karne layak the (cooldown/price-range filter ke baad).

    Return: dict jaisa:
        {
            "action": "BUY" / "SKIP",
            "symbol": "AVAXUSDT" ya None,
            "reason": "...",
            "take_profit_pct": float (sirf agar action == BUY),
        }
    """
    candidates_text = "\n\n".join(
        f"--- Candidate {i+1}: {c['symbol']} ---\n{c}"
        for i, c in enumerate(candidates)
    )

    prompt = f"""Tum ek crypto trading assistant ho. Yeh {len(candidates)} candidate
coins ka data hai, in sabme se BEST ek choose karo (ya kisi mein bhi
entry mat lo):

{candidates_text}

Sirf yeh char lines mein jawab do, aur kuch mat likhna:
ACTION: <BUY ya SKIP>
SYMBOL: <agar BUY hai to jis coin ko choose kiya uska exact symbol
(jaise AVAXUSDT), agar SKIP hai to NONE>
REASON: <ek chhota jumla, kyun ye coin (ya kyun koi nahi)>
TAKE_PROFIT: <ek number, e.g. 8, agar ACTION BUY hai — is coin ki
volatility dekh kar kitna % upar jaane par profit book karna chahiye.
Agar ACTION BUY nahi hai, yahan 0 likho>

{_INSTRUCTIONS}

Koi extra text, markdown, ya explanation mat dena."""

    global _search_off_date
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    use_search = config.ENABLE_GEMINI_WEB_SEARCH and _search_off_date != today

    base_cfg = {"http_options": {"timeout": config.CALL_TIMEOUT_SECONDS * 1000}}  # ms mein
    search_prompt = prompt + _SEARCH_NOTE

    # Pehli koshish: web search ke sath (agar on hai). Fail ho to bina
    # search ke. Wo bhi fail ho to SKIP — trading kabhi nahi rukti.
    attempts = []
    if use_search:
        attempts.append(("search", search_prompt, {**base_cfg, "tools": [{"google_search": {}}]}))
    attempts.append(("plain", prompt, base_cfg))
    if not use_search:
        attempts.append(("plain", prompt, base_cfg))  # purana behaviour: ek retry

    last_err = None
    for kind, p, cfg in attempts:
        try:
            response = _client.models.generate_content(model=_MODEL_NAME, contents=p, config=cfg)
            if kind == "search":
                n = _search_query_count(response)
                print(f"[GEMINI] Web search: {'haan (' + str(n) + ' searches)' if n else 'nahi hua (Gemini ne khud zaroorat nahi samjhi)'}")
            return _parse_response(response.text or "", candidates)
        except Exception as e:
            last_err = e
            if kind == "search":
                msg = str(e).upper()
                if any(k in msg for k in ("429", "RESOURCE_EXHAUSTED", "QUOTA", "NOT SUPPORTED", "PERMISSION", "INVALID_ARGUMENT", "400")):
                    _search_off_date = today
                    print(f"[WARN] Gemini web search aaj ke liye band (quota/support masla): {e}")
                else:
                    print(f"[WARN] Gemini search wali call fail, bina search dobara try: {e}")
            else:
                print(f"[WARN] Gemini call failed: {e}")

    print(f"[ERROR] Gemini ki saari koshishein fail: {last_err}")
    return {"action": "SKIP", "symbol": None, "reason": f"Gemini error: {last_err}", "take_profit_pct": None}


def _search_query_count(response):
    """Gemini ne asal mein Google search kiya ya nahi — kitni searches (0 = nahi)."""
    try:
        gm = response.candidates[0].grounding_metadata
        queries = getattr(gm, "web_search_queries", None) if gm else None
        return len(queries) if queries else 0
    except (AttributeError, IndexError, TypeError):
        return 0


def _parse_response(text, candidates):
    """
    Gemini ke text jawab ko safely parse karta hai.
    Agar format expected na ho, ya symbol candidates mein na mile,
    SKIP return karta hai (safe default).
    """
    action = None
    symbol = None
    reason = "no reason given"
    take_profit_pct = None

    valid_symbols = {c["symbol"] for c in candidates}

    for line in text.strip().splitlines():
        # Search ke sath Gemini kabhi "**ACTION:** BUY" jaisa markdown likh
        # deta hai — usko saaf kar ke parse karte hain
        line = line.replace("**", "").strip().lstrip("*#- ").strip()
        if line.upper().startswith("ACTION:"):
            candidate = line.split(":", 1)[1].strip().upper()
            if candidate in VALID_ACTIONS:
                action = candidate
        elif line.upper().startswith("SYMBOL:"):
            raw_symbol = line.split(":", 1)[1].strip().upper()
            if raw_symbol in valid_symbols:
                symbol = raw_symbol
        elif line.upper().startswith("REASON:"):
            reason = line.split(":", 1)[1].strip()
        elif line.upper().startswith("TAKE_PROFIT:"):
            raw_value = line.split(":", 1)[1].strip()
            try:
                take_profit_pct = float(raw_value)
            except ValueError:
                take_profit_pct = None

    if action is None or (action == "BUY" and symbol is None):
        # Gemini ne kuch ajeeb bola ya invalid symbol diya — safe side lo
        return {"action": "SKIP", "symbol": None, "reason": "could not parse Gemini response", "take_profit_pct": None}

    if action == "BUY":
        if take_profit_pct is None:
            take_profit_pct = config.TAKE_PROFIT_MIN_PCT  # safe default
        take_profit_pct = max(config.TAKE_PROFIT_MIN_PCT, min(take_profit_pct, config.TAKE_PROFIT_MAX_PCT))

    return {"action": action, "symbol": symbol, "reason": reason, "take_profit_pct": take_profit_pct}
