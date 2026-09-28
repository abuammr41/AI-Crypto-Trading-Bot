"""
config.py
---------
Yahan sab FIXED rules hain — ye Gemini kabhi change nahi kar sakta.
Gemini sirf reasoning/suggestion deta hai (buy/hold/skip, take-profit %),
lekin har hard limit (stop-loss %, daily limits, position size, take-profit
range) YAHAN se control hota hai, code mein hardcoded.
"""

import os
from dotenv import load_dotenv

load_dotenv()  # .env file se saari secret values load karta hai

# ============================================================
# API KEYS (yeh .env file se aate hain, yahan kabhi mat likhna)
# ============================================================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ============================================================
# RISK RULES (fixed — Gemini in numbers ko change nahi kar sakta)
# ============================================================

# Ek single trade mein max kitna % capital loss allowed hai — ye ab
# ek CEILING hai, fix number nahi. Asal stop-loss har coin ke liye
# uski apni support-level aur volatility (ATR) dekh kar decide hota
# hai (neeche HYBRID STOP-LOSS section), lekin kabhi is se zyada
# neeche nahi jata.
MAX_LOSS_PER_TRADE_PCT = 1.8

# Sabse tight stop bhi kam se kam itna zaroor hoga — taake bohot
# "quiet" coin ke liye bhi stop itna tight na ho jaye ke normal
# fluctuation mein hi hit ho jaye.
MIN_STOP_LOSS_PCT = 0.6

# Poore din mein max kitna % loss allowed hai (hit hote hi trading band).
# ZAROORI: Ye MAX_LOSS_PER_TRADE_PCT (1.8%) se JAAN-BOOJH KAR zyada
# rakha hai — taake agar EK trade apna poora max-loss (1.8%) bhi khaye,
# phir bhi thoda "margin" bacha rahe (0.8%) taake us din ek aur
# (chhoti) trade ka mauka mil sake, poora din turant band na ho jaye.
DAILY_MAX_LOSS_PCT = 2.6

# ============================================================
# HYBRID STOP-LOSS (support-level + volatility ka combination)
# ============================================================
# Fixed % ki jagah, stop ab teen tareekon mein se "sabse wide/safe"
# wala use karta hai:
# 1. MIN_STOP_LOSS_PCT (upar) — kabhi is se tight nahi
# 2. Support-level se thoda neeche (SUPPORT_BUFFER_PCT wala buffer)
# 3. ATR (volatility) se — coin ki apni "normal" movement
# Jo bhi teeno mein se sabse "door" (wide) ho, wahi final stop banta
# hai — lekin MAX_LOSS_PER_TRADE_PCT (1.8%) se kabhi zyada nahi.

# Support level se stop nikalte waqt itna EXTRA buffer neeche rakho
# (taake "stop hunting" — exact obvious level par stop lagana — se
# bacha ja sake)
SUPPORT_STOP_BUFFER_PCT = 0.5

# ATR period (kitne candles ka average) aur multiplier (ATR ko kitne
# guna kar ke stop-distance banana hai — professional standard 1.5-2x hai)
ATR_PERIOD = 14
ATR_MULTIPLIER = 1.5

# Daily profit target ab ek RANGE hai, fix number nahi:
# - 4% ke baad se flexible exit theek hai (agar acha exit signal mile)
# - 5% HARD CEILING hai — isse zyada kabhi nahi, chahe market kitni achi lage
DAILY_PROFIT_TARGET_MIN_PCT = 4.0
DAILY_PROFIT_TARGET_MAX_PCT = 5.0

# Trailing stop: peak price se kitna % neeche stop rakhna hai
TRAILING_STOP_PCT = 1.5

# Trailing stop sirf tab update (Binance ko naya call) hoga jab naya stop
# purane se kam se kam itna % zyada ho — chhoti chhoti fluctuations par
# baar baar cancel/replace nahi karte, taake Binance calls kam lagein aur
# "gap window" (cancel se naya lagne tak) bhi kam baar aaye.
MIN_TRAIL_UPDATE_PCT = 0.3

# Take-profit range — Gemini khud suggest karta hai kitna % target rakhna
# hai (har coin ki volatility dekh kar), lekin code isko is range mein
# bound karta hai, taake AI ka koi ajeeb number bhi safe rahe.
TAKE_PROFIT_MIN_PCT = 3.0
TAKE_PROFIT_MAX_PCT = 15.0

# Binance trading fee (roughly 0.1% per trade, buy aur sell dono par lagti
# hai — matlab total ~0.2% round-trip). Take-profit aur stop-loss calculate
# karte waqt is fee ko add kiya jata hai, taake target "net" (fees ke baad)
# ka ho, "gross" nahi — warna asal profit hamesha target se kam milta.
BINANCE_FEE_PCT = 0.1  # per trade (buy ya sell, ek taraf)
ROUND_TRIP_FEE_PCT = BINANCE_FEE_PCT * 2  # buy + sell dono milakar

# Momentum exit: agar RSI apne peak se itne points (ya zyada) neeche gir
# jaye, matlab momentum kamzor ho raha hai — bot samajhdari se pehle hi
# exit kar sakta hai, trailing stop ka wait kiye bina.
MOMENTUM_RSI_DROP_THRESHOLD = 15

# Ek waqt mein max kitni open positions — SIRF EK (simplicity, kam bugs,
# poora capital ek best opportunity mein). Ye ab practically hamesha 1 hai.
MAX_OPEN_POSITIONS = 1

# Ek trade loss mein close hone ke baad, usi coin mein dobara turant entry
# mat lo — itni der (minutes) wait karo pehle
COOLDOWN_AFTER_LOSS_MINUTES = 60

# Binance ka minimum order size (roughly, coin ke hisaab se badal sakta hai)
MIN_ORDER_SIZE_USDT = 6.0

# Ek trade mein max kitna USDT lagana hai (absolute cap) — chahe total
# balance kitna bhi bara ho jaye. None = koi absolute cap nahi.
MAX_POSITION_SIZE_USDT = None

# TIERED POSITION SIZING: balance jitna barhega, per-trade % utna kam
# hoga — taake bara capital kabhi ek hi trade mein poora risk mein na
# aaye. Har tuple (balance_upto, percentage) hai — total balance jis
# pehle tier mein fit ho, wahi % use hoti hai.
# $0-200: 100% (chhote balance mein poora lagana zaroori hai, warna
#         Binance ka minimum order size $6 bhi poora na ho)
# $200-500: 45%
# $500+: 40%
POSITION_SIZE_TIERS = [
    (200.0, 100.0),
    (500.0, 45.0),
    (float("inf"), 40.0),
]

# Sirf inn price range wale coins target karo — chhoti price wale coins mein
# chhote capital ke liye % moves zyada aur jaldi milte hain.
# Bohot chhoti price wale naye tokens (0.0000x jaise) bhi allowed hain,
# bas bilkul zero ke qareeb (dust/illiquid) wale avoid karte hain.
MAX_COIN_PRICE_USDT = 5.0
MIN_COIN_PRICE_USDT = 0.0000001  # sirf bilkul dust-level price avoid karne ke liye

# Minimum 24h trading volume (USDT) — liquidity check.
MIN_VOLUME_USDT = 1_000_000  # thoda relax kiya, zyada opportunities ke liye

# ============================================================
# PRIORITY TOKENS — established/strong chains (Ethereum, BNB, Solana)
# ============================================================
# Ye coins pehle check hote hain (har cycle mein), phir baaki "top
# gainers" scan hoti hai. Wajah: bare, established chains ke tokens
# generally zyada reliable/liquid hote hain naye/anjaan coins se.
# NOTE: Ye "priority" hai, hard-requirement nahi — agar in mein se
# koi promising na nikle, bot phir bhi normal gainers scan karta hai.
PRIORITY_TOKENS = [
    # Ethereum chain
    "UNIUSDT",       # Uniswap
    # BNB chain
    "CAKEUSDT",      # PancakeSwap
    "INJUSDT",       # Injective
    "MANAUSDT",      # Decentraland
    "PENDLEUSDT",    # Pendle
    "KAVAUSDT",      # Kava
    "TWTUSDT",        # Trust Wallet Token
    "SFPUSDT",        # SafePal
    "MARSCOINUSDT",  # MarsCoin (Binance "Seed" tag — thoda zyada risky)
    # Solana chain
    "JUPUSDT",       # Jupiter
    "ENAUSDT",       # Ethena
    "RENDERUSDT",    # Render
    "BDXUSDT",       # Beldex
]

# RSI (Relative Strength Index) settings — overbought coins avoid karne ke liye
RSI_PERIOD = 14
RSI_OVERBOUGHT_THRESHOLD = 80  # relax kiya

# MFI (Money Flow Index) — RSI jaisa hi, lekin volume ko bhi shamil karta hai
MFI_PERIOD = 14
MFI_OVERBOUGHT_THRESHOLD = 85  # thoda relax kiya, zyada opportunities ke liye

# Buyer/Seller activity — taker buy volume ka % total volume mein se.
# Isse zyada ho to matlab buyers active hain (bullish signal).
MIN_TAKER_BUY_RATIO_PCT = 45.0  # thoda relax kiya, zyada opportunities ke liye

# ============================================================
# MULTI-TIMEFRAME ANALYSIS (1H entry precision, 4H confirmation, 1D bara trend)
# ============================================================

# Agar Daily trend aur 1H trend SAAF conflict karein (ek upar, ek neeche),
# to entry skip kar do — "timeframe conflict" wale trades risky hote hain.
ENABLE_MULTI_TIMEFRAME_CHECK = True

# Trend nikalne ke liye kitne candles ka average dekhna hai (simple SMA jaisa)
TREND_LOOKBACK_CANDLES = 10

# ============================================================
# VOLUME SPIKE & ACCUMULATION DETECTION (Smart Money signals)
# ============================================================

# Current candle ka volume, average se kitna guna zyada ho to "spike" mana jaye
VOLUME_SPIKE_MULTIPLIER = 2.0

# Accumulation pattern: price kitne % range mein "flat" raha ho (pichle N candles),
# jabke volume badh raha ho — ye "chup-chap khareed rahe hain" ka signal hai
ACCUMULATION_PRICE_RANGE_PCT = 3.0

# ============================================================
# TRADING HOURS + WATCHLIST (Pakistan time, 24-hour format)
# ============================================================
# Subah market "thin/quiet" hoti hai (kam liquidity, ajeeb upar-neeche
# swings) — us waqt khareedne se false stop-outs hote hain. Isliye:
# - DAILY_RESET_HOUR_PKT se TRADING_START_HOUR_PKT tak: WATCH mode —
#   bot sirf promising coins ko Watchlist mein daalta hai, khareedta nahi
# - TRADING_START_HOUR_PKT se TRADING_END_HOUR_PKT tak: TRADE mode —
#   pehle Watchlist wale coins check hote hain, phir naye gainers
# - TRADING_END_HOUR_PKT ke baad (raat): koi naya scan/trade nahi, sirf
#   khuli position manage hoti hai
TRADING_START_HOUR_PKT = 15   # 3 PM
TRADING_END_HOUR_PKT = 23     # 11 PM
WATCHLIST_MAX_SIZE = 5        # ek waqt mein max kitne coins watch hon
STABLECOINS = ["USDC", "FDUSD", "TUSD", "USDP", "DAI", "BUSD", "USDE", "PYUSD", "USD1", "RLUSD", "EURI", "AEUR", "EUR", "XUSD", "BFUSD", "USDS"]

# Gemini khud Google Search se coin ki taaza news dhoonde (sirf trade
# mode 3 PM-11 PM mein, kyunki Gemini call sirf tab hoti hai). Agar
# search wali call fail ho, bot khud bina search ke dobara try karta hai.
# Band karna ho to False kar do.
ENABLE_GEMINI_WEB_SEARCH = False

# ============================================================
# LOOP TIMING
# ============================================================

# Har kitni der (seconds) mein ek check-in cycle chalega
CHECK_INTERVAL_SECONDS = 20 * 60  # 20 minutes (load kam rakhne ke liye)

# Ek Gemini/Binance call ko max kitna time (seconds) milega, warna skip
CALL_TIMEOUT_SECONDS = 120  # bara prompt (multiple candidates), zyada time chahiye

# ============================================================
# FILES (state, logs, safety switches)
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

LOCK_FILE = os.path.join(BASE_DIR, "bot.lock")            # duplicate-run rokta hai
STATE_FILE = os.path.join(BASE_DIR, "position_state.json") # crash-recovery
TRADE_LOG_FILE = os.path.join(BASE_DIR, "trade_log.csv")   # har trade ka record
WATCH_LOG_FILE = os.path.join(BASE_DIR, "watchlist_log.csv")  # watchlist coins ka har-cycle record
PAUSE_FILE = os.path.join(BASE_DIR, "PAUSE.txt")           # ye file bana do to bot ruk jata hai

# ============================================================
# MARKET SAFETY
# ============================================================

# Agar BTC itne % se zyada gir jaye 1 ghante mein, to nayi trade mat lo
BTC_CRASH_THRESHOLD_PCT = 10.0

# Trading day reset time (Pakistan time, 24-hour format) — sirf counter reset ke liye
DAILY_RESET_HOUR_PKT = 5  # Binance ki 1D candle bhi isi waqt (UTC midnight = 5 AM PKT) close hoti hai

# ============================================================
# DAILY TELEGRAM SUMMARY + DATA RETENTION
# ============================================================

# Roz is waqt (Pakistan time, 24-hour) ek summary Telegram par bhej di jaati hai.
# DAILY_RESET_HOUR_PKT ke saath sync rakha hai — taake summary, profit/loss
# reset, aur log cleanup sab ek hi waqt par ho, koi confusion na ho.
DAILY_SUMMARY_HOUR_PKT = DAILY_RESET_HOUR_PKT

# Trade log mein sirf itne din ka data rakhna hai — purana turant delete.
# Hume sirf "abhi ka" (24 ghante) hisaab chahiye, purani kahani ki zaroorat nahi.
LOG_RETENTION_DAYS = 1
