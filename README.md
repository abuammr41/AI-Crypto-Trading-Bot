# AI-Assisted Crypto Trading Bot (Binance Spot)

Autonomous spot-trading bot for Binance: scans the market for promising USDT
pairs, opens positions with automatic risk management, and manages/exits them
on its own — with Telegram alerts and an optional Gemini-powered news/sanity
check before every trade.

## What it does

- **Scanning** — pulls top gainers + a priority watchlist, then scores each
  candidate using RSI, MFI, ATR, support/resistance, order-book pressure,
  multi-timeframe trend (1h/4h/1d), volume-spike and accumulation detection,
  and candlestick pattern recognition (`binance_helper.py`).
- **Risk management** — every position is protected by an OCO order
  (take-profit + stop-loss) the moment it's opened. Stop-loss is a **hybrid**
  of a fixed floor, distance to support, and ATR-based volatility — capped by
  a hard max-loss-per-trade percentage (`config.py`).
- **Position sizing** — tiered position sizing based on account balance, with
  a daily loss limit and daily profit target that pause new trades once hit.
- **News/sanity check** — optional Gemini call cross-checks a candidate
  against recent news before entry (listings/delistings, hacks, token
  unlocks) (`gemini_helper.py`, `news_helper.py`).
- **Monitoring** — Telegram alerts on entry/exit and daily summaries
  (`telegram_helper.py`); a read-only Telegram channel monitor for external
  signals (`channel_monitor.py`).
- **State & logging** — trades and watchlist activity are logged to CSV;
  bot state (open position, daily P/L) persists across restarts
  (`state_manager.py`, `trade_logger.py`, `watch_logger.py`).

## Run it

```
py -m pip install -r requirements.txt
py scan_only.py          # read-only market scan, no trading — safe to try
py run_loop.py           # runs main.py's cycle every CHECK_INTERVAL_SECONDS
py check_position.py     # check current open position
py view_history.py       # view trade history from trade_log.csv
py sell_now.py           # manual emergency exit of the current position
```

Needs a `.env` file (see `SECURITY.md`) with `BINANCE_API_KEY`,
`BINANCE_API_SECRET`, and optionally `GEMINI_API_KEY`,
`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`. **Never commit this file** —
see `SECURITY.md` for the full security checklist before running with
real funds.

## Scope & risk

This is a **personal-use spot trading bot**, not a licensed financial
product. Crypto trading is high-risk; only trade money you can afford to
lose. Past signals/behavior are not a guarantee of future performance.

## License

All Rights Reserved — shared publicly for portfolio/demonstration purposes only.
See [LICENSE](LICENSE). No reuse, copying, or redistribution without permission.
