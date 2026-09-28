"""
trade_logger.py
----------------
Har trade (buy, sell, stop-adjust) ko CSV file mein record karta hai.
"""

import csv
import os
from datetime import datetime, timezone, timedelta
import config

_HEADERS = [
    "timestamp_utc", "action", "symbol", "price",
    "qty", "stop_price", "pnl_usdt", "reason",
]


def log_trade(action, symbol, price, qty=None, stop_price=None, pnl_usdt=None, reason=""):
    """Ek row add karta hai trade_log.csv mein."""
    file_exists = os.path.exists(config.TRADE_LOG_FILE)

    with open(config.TRADE_LOG_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(_HEADERS)
        writer.writerow([
            datetime.now(timezone.utc).isoformat(),
            action,
            symbol,
            price,
            qty if qty is not None else "",
            stop_price if stop_price is not None else "",
            pnl_usdt if pnl_usdt is not None else "",
            reason,
        ])


def trim_old_entries(days_to_keep=None):
    """
    Purani trade log entries hata deta hai (sirf recent data rakhta hai),
    taake file bahut badi na ho jaye. Default: config.LOG_RETENTION_DAYS
    (abhi 1 din — hume sirf "aaj ka hisaab" chahiye, purani kahani nahi).
    """
    if days_to_keep is None:
        days_to_keep = config.LOG_RETENTION_DAYS

    if not os.path.exists(config.TRADE_LOG_FILE):
        return

    cutoff = datetime.now(timezone.utc) - timedelta(days=days_to_keep)

    with open(config.TRADE_LOG_FILE, "r", newline="") as f:
        reader = csv.reader(f)
        rows = list(reader)

    if not rows:
        return

    header, data_rows = rows[0], rows[1:]
    kept_rows = []

    for row in data_rows:
        try:
            row_time = datetime.fromisoformat(row[0])
            if row_time >= cutoff:
                kept_rows.append(row)
        except (ValueError, IndexError):
            kept_rows.append(row)  # corrupt row ho to bhi rakh lo, delete mat karo

    with open(config.TRADE_LOG_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(kept_rows)

    print(f"[LOG] Trade log trimmed, {len(kept_rows)} rows kept (last {days_to_keep} days).")
