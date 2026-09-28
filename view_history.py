"""
view_history.py
----------------
Poori account history aur balance dekhne ke liye:
    py view_history.py

Dikhata hai:
- Overall account balance (USDT + jo bhi coin abhi khareeda hua hai)
- Trade log ka poora record (kab, kaunsa coin, kis waqt khareeda/becha)
- Summary stats: total trades, win rate, total profit/loss
- Abhi ka open position (agar koi hai)

Protection (agar koi position unprotected reh jaye) ab main.py mein
khud-ba-khud hoti hai har cycle mein.

Turant kisi coin ko bechna ho, to sell_now.py use karo (alag file).
"""

import csv
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

import config
import binance_helper
import state_manager
import watch_logger

load_dotenv()


def main():
    print("=" * 60)
    print("ACCOUNT OVERVIEW — Al-Hasan Bot")
    print("=" * 60)

    _show_overall_balance()
    print()
    _show_trade_log()
    print()
    _show_summary_stats()
    print()
    _show_current_position()
    print()
    _show_watchlist_history()


def _show_overall_balance():
    """USDT balance aur jo bhi coin abhi khareeda hua hai, uski value dikhata hai."""
    print("\n--- Overall Account Balance ---")
    client = binance_helper.get_client()

    try:
        account = client.get_account()
    except Exception as e:
        print(f"Balance fetch nahi ho saka: {e}")
        return

    total_value_usdt = 0.0

    for asset_info in account["balances"]:
        asset = asset_info["asset"]
        free = float(asset_info["free"])
        locked = float(asset_info["locked"])
        total = free + locked

        if total <= 0:
            continue

        if asset == "USDT":
            print(f"USDT: {total:.4f}  (free: {free:.4f}, locked: {locked:.4f})")
            total_value_usdt += total
        else:
            symbol = f"{asset}USDT"
            price = binance_helper.get_current_price(client, symbol)
            if price:
                value = total * price
                total_value_usdt += value
                print(f"{asset}: {total:.6f}  (~{value:.4f} USDT at current price)")

    print(f"\nTotal estimated account value: ~{total_value_usdt:.4f} USDT")


def _show_trade_log():
    if not os.path.exists(config.TRADE_LOG_FILE):
        print("Abhi tak koi trade record nahi hai.")
        return

    with open(config.TRADE_LOG_FILE, "r", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        print("Trade log khali hai.")
        return

    print(f"\n--- Poora Trade Record ({len(rows)} entries) ---\n")
    for row in rows:
        raw_ts = row.get("timestamp_utc", "")
        timestamp_display = raw_ts
        try:
            utc_time = datetime.fromisoformat(raw_ts)
            pkt_time = utc_time + timedelta(hours=5)
            timestamp_display = pkt_time.strftime("%Y-%m-%d %I:%M %p") + " PKT"
        except (ValueError, TypeError):
            pass

        action = row.get("action", "")
        symbol = row.get("symbol", "")
        price = row.get("price", "")
        pnl = row.get("pnl_usdt", "")
        reason = row.get("reason", "")

        line = f"{timestamp_display} | {action:12} | {symbol:12} | price: {price}"
        if pnl:
            try:
                pnl_val = float(pnl)
                emoji = "🟢" if pnl_val >= 0 else "🔴"
                line += f" | P/L: {emoji} {pnl_val:+.4f} USDT"
            except ValueError:
                pass
        print(line)
        if reason:
            print(f"    Reason: {reason}")


def _show_summary_stats():
    if not os.path.exists(config.TRADE_LOG_FILE):
        return

    with open(config.TRADE_LOG_FILE, "r", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    closed_trades = [r for r in rows if r.get("action") == "CLOSED" and r.get("pnl_usdt")]

    if not closed_trades:
        print("--- Summary Stats ---")
        print("Abhi tak koi trade close nahi hui, stats available nahi.")
        return

    total_pnl = 0.0
    wins = 0
    losses = 0

    for row in closed_trades:
        try:
            pnl = float(row["pnl_usdt"])
            total_pnl += pnl
            if pnl >= 0:
                wins += 1
            else:
                losses += 1
        except ValueError:
            continue

    total_closed = wins + losses
    win_rate = (wins / total_closed * 100) if total_closed > 0 else 0

    print("--- Summary Stats ---")
    print(f"Total closed trades: {total_closed}")
    print(f"Wins: {wins}  |  Losses: {losses}")
    print(f"Win rate: {win_rate:.1f}%")
    print(f"Total P/L: {total_pnl:+.4f} USDT")


def _show_current_position():
    print("--- Abhi Ka Open Position ---")

    state = state_manager.load_state()
    positions = state.get("open_positions", [])

    if not positions:
        print("Koi open position nahi hai abhi.")
        return

    client = binance_helper.get_client()

    for pos in positions:
        symbol = pos["symbol"]
        current_price = binance_helper.get_current_price(client, symbol)

        print(f"\nSymbol: {symbol}")
        print(f"Entry: {pos['entry_price']:.10f}")
        if current_price:
            pnl_pct = ((current_price - pos["entry_price"]) / pos["entry_price"]) * 100
            print(f"Current: {current_price:.10f}  ({pnl_pct:+.2f}%)")
        print(f"Stop-loss: {pos['stop_price']:.10f}")
        tp = pos.get('take_profit_price')
        print(f"Take-profit: {tp:.10f}" if isinstance(tp, (int, float)) else f"Take-profit: {tp}")



def _show_watchlist_history():
    """Aaj ki watchlist ke har coin ki subah se ab tak ki chhoti summary."""
    print("--- Aaj Ki Watchlist (subah se ab tak) ---")
    state = state_manager.load_state()
    watchlist = state.get("watchlist", {})
    if not watchlist:
        print("Watchlist abhi khali hai.")
        return
    for symbol in watchlist:
        summary = watch_logger.get_summary(symbol, state.get("daily_reset_date"))
        print(f"\n{symbol}:")
        print(f"  {summary}" if summary else "  Abhi kaafi readings nahi (kam az kam 2 chahiye).")

if __name__ == "__main__":
    main()
