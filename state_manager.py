"""
state_manager.py
-----------------
Ye file teen kaam karti hai:
1. Duplicate-run rokna (lock file) — agar bot pehle se chal raha ho, dobara na chale
2. Crash-recovery — agar bot beech mein band ho jaye, restart hone par yaad rahe
   ke kya position khuli thi
3. Manual PAUSE switch — ek file bana do to bot khud ruk jaye
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta
import config


# ============================================================
# LOCK FILE — duplicate runs rokne ke liye
# ============================================================

def acquire_lock():
    """
    Agar lock file pehle se maujood ho, matlab ek copy pehle se chal rahi hai.
    Is soorat mein script khud exit ho jati hai.

    STALE LOCK PROTECTION: Agar lock file bahut PURANI hai (25+ minute
    se zyada — ek poore cycle, 20 min, se zyada), iska matlab hai ke
    purana process ACHI TARAH crash hua tha (bijli jana, force-kill)
    bina lock hataye — is soorat mein purani lock ko "stale" maan kar
    hata dete hain aur khud continue karte hain, warna bot HAMESHA
    "already running" bolta rehta bina kabhi dobara chale.
    """
    if os.path.exists(config.LOCK_FILE):
        lock_age_seconds = datetime.now(timezone.utc).timestamp() - os.path.getmtime(config.LOCK_FILE)
        if lock_age_seconds < 1500:  # 25 minute — ek cycle (20 min) se zyada
            print("[LOCK] Bot already running (lock file exists). Exiting to avoid duplicate run.")
            sys.exit(0)
        else:
            print(f"[LOCK] Purani lock file mili ({lock_age_seconds/60:.0f} minute purani) — stale samajh kar hata rahe hain.")
            os.remove(config.LOCK_FILE)

    with open(config.LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))


def release_lock():
    """Script band hone se pehle lock file hatati hai."""
    if os.path.exists(config.LOCK_FILE):
        os.remove(config.LOCK_FILE)


# ============================================================
# PAUSE SWITCH
# ============================================================

def is_paused():
    """Agar PAUSE.txt file maujood ho, to bot ko rukna chahiye."""
    return os.path.exists(config.PAUSE_FILE)


# ============================================================
# POSITION STATE — crash recovery ke liye
# ============================================================

def _default_state():
    return {
        # open_positions: list of dicts, har ek mein: symbol, entry_price,
        # qty, stop_price, take_profit_price, take_profit_pct, peak_price,
        # peak_rsi, oco_order_list_id
        "open_positions": [],
        "daily_pnl_usdt": 0.0,
        "daily_reset_date": None,  # ISO date string, jab last reset hua
        "cooldowns": {},           # {symbol: iso_timestamp_of_last_loss}
        "last_summary_date": None,  # ISO date string, jab last daily summary bheji
        "last_seen_announcement": None,
        "day_start_capital": None,  # roz ka asal account capital (daily limits ke liye)
        "capital_date": None,       # kis din ka snapshot hai
        "watchlist": {},            # {symbol: {"score": change_24h_pct, "added": iso}} — subah watch kiye coins
        "watchlist_date": None,     # kis din ki watchlist hai (naye din khud saaf hoti hai)  # Binance ka last-dekha hua Telegram announcement (naye check karne ke liye)
    }


def load_state():
    """Position state file se load karta hai. Agar na ho, default (khali) state deta hai."""
    if not os.path.exists(config.STATE_FILE):
        return _default_state()
    try:
        with open(config.STATE_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"[ERROR] State file corrupt ({e}), starting fresh.")
        return _default_state()


def save_state(state):
    """Position state ko file mein save karta hai."""
    with open(config.STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def maybe_reset_daily_counters(state):
    """
    Agar Pakistan time 1 AM cross ho chuka ho aur aaj reset nahi hua,
    to daily P/L counter reset kar deta hai. Trading khud nahi rukti,
    sirf counter reset hota hai.
    """
    pkt_now = datetime.now(timezone.utc) + timedelta(hours=5)
    today_str = pkt_now.strftime("%Y-%m-%d")

    should_reset = False
    if state.get("daily_reset_date") != today_str and pkt_now.hour >= config.DAILY_RESET_HOUR_PKT:
        should_reset = True

    if should_reset:
        print(f"[RESET] Daily counters reset for {today_str}")
        state["daily_pnl_usdt"] = 0.0
        state["daily_reset_date"] = today_str

    return state
