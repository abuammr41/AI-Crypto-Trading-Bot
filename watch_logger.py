"""
watch_logger.py
----------------
Watchlist wale coins ka har cycle (20 min) ka record rakhta hai
(watchlist_log.csv), aur us record se har coin ki CHHOTI summary banata
hai (subah se ab tak kya hua) — jo 3 baje trade-mode mein Gemini ko
bheji jati hai.

Summary jaan-boojh kar chhoti rakhi hai (2-3 line) — bari history bhejne
se Gemini prompt bara hota hai aur timeout/504 errors aate hain.

GENERIC hai — kisi coin ka naam hardcode nahi. Koi bhi file error aaye
to crash nahi karta, sirf warning print karta hai (history optional hai).
"""

import csv
import os
from datetime import datetime, timezone, timedelta

import config

_HEADERS = [
    "timestamp_utc", "symbol", "price", "change_24h_pct", "rsi", "mfi",
    "volume_usdt", "trend_1h", "trend_4h", "trend_1d", "candle_pattern",
]


def _fmt(value):
    return "" if value is None else value


def log_snapshot(analyses):
    """Har analysis (watchlist coin) ki ek line CSV mein add karta hai."""
    if not analyses:
        return
    try:
        file_exists = os.path.exists(config.WATCH_LOG_FILE)
        now = datetime.now(timezone.utc).isoformat()
        with open(config.WATCH_LOG_FILE, "a", newline="") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(_HEADERS)
            for a in analyses:
                writer.writerow([
                    now, a.get("symbol"), _fmt(a.get("price")), _fmt(a.get("change_24h_pct")),
                    _fmt(a.get("rsi")), _fmt(a.get("mfi")), _fmt(a.get("volume_usdt")),
                    _fmt(a.get("trend_1h")), _fmt(a.get("trend_4h")), _fmt(a.get("trend_1d")),
                    _fmt(a.get("candle_pattern")),
                ])
    except OSError as e:
        print(f"[WARN] Watch log likhne mein masla: {e}")


def _today_start_utc(daily_reset_date):
    """Aaj ke trading-day (PKT reset) ka shuru waqt, UTC mein."""
    try:
        day = datetime.strptime(daily_reset_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc) - timedelta(hours=24)
    return day + timedelta(hours=config.DAILY_RESET_HOUR_PKT - 5)


def _read_rows(symbol, since_utc):
    if not os.path.exists(config.WATCH_LOG_FILE):
        return []
    rows = []
    try:
        with open(config.WATCH_LOG_FILE, "r", newline="") as f:
            for r in csv.DictReader(f):
                if r.get("symbol") != symbol:
                    continue
                try:
                    if datetime.fromisoformat(r["timestamp_utc"]) >= since_utc:
                        rows.append(r)
                except (KeyError, ValueError):
                    continue
    except OSError as e:
        print(f"[WARN] Watch log padhne mein masla: {e}")
    return rows


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def get_summary(symbol, daily_reset_date):
    """
    Aaj subah se ab tak ki CHHOTI summary (string). Kam az kam 2
    readings chahiye, warna None (summary ka faida nahi).
    """
    rows = _read_rows(symbol, _today_start_utc(daily_reset_date))
    if len(rows) < 2:
        return None

    prices = [p for p in (_num(r.get("price")) for r in rows) if p]
    if len(prices) < 2:
        return None

    first_p, last_p = prices[0], prices[-1]
    change = ((last_p - first_p) / first_p) * 100 if first_p else 0.0
    first_time = rows[0]["timestamp_utc"]
    try:
        first_pkt = (datetime.fromisoformat(first_time) + timedelta(hours=5)).strftime("%H:%M")
    except ValueError:
        first_pkt = "?"

    bull_1h = sum(1 for r in rows if r.get("trend_1h") == "bullish")
    rsi_vals = [v for v in (_num(r.get("rsi")) for r in rows) if v is not None]
    vol_vals = [v for v in (_num(r.get("volume_usdt")) for r in rows) if v is not None]

    parts = [
        f"Pehli baar {first_pkt} PKT par dekha: {first_p:.10g} -> ab {last_p:.10g} ({change:+.1f}%)",
        f"Watch ke dauran high/low: {max(prices):.10g} / {min(prices):.10g}",
        f"{len(rows)} readings mein 1h trend bullish: {bull_1h}/{len(rows)}",
    ]
    if len(rsi_vals) >= 2:
        parts.append(f"RSI {rsi_vals[0]:.0f} -> {rsi_vals[-1]:.0f}")
    if len(vol_vals) >= 2:
        if vol_vals[-1] > vol_vals[0] * 1.02:
            parts.append("volume barh raha")
        elif vol_vals[-1] < vol_vals[0] * 0.98:
            parts.append("volume kam ho raha")
        else:
            parts.append("volume taqreeban barabar")
    return "; ".join(parts)


def trim_old_entries(hours_to_keep=24):
    """Purana data hata deta hai (sirf pichle 24 ghante rakhta hai)."""
    if not os.path.exists(config.WATCH_LOG_FILE):
        return
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_to_keep)
    try:
        with open(config.WATCH_LOG_FILE, "r", newline="") as f:
            rows = list(csv.reader(f))
        if not rows:
            return
        header, data = rows[0], rows[1:]
        kept = []
        for r in data:
            try:
                if datetime.fromisoformat(r[0]) >= cutoff:
                    kept.append(r)
            except (ValueError, IndexError):
                continue
        with open(config.WATCH_LOG_FILE, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(kept)
    except OSError as e:
        print(f"[WARN] Watch log trim mein masla: {e}")
