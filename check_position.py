"""
check_position.py
------------------
Overall account balance (USDT + jo bhi coin khareeda hua hai) aur
KISI BHI khuli hui position ka status batati hai — coin ka naam
hardcode nahi hai, khud state_manager se padh leti hai ke abhi kya
khula hua hai.
"""

from dotenv import load_dotenv
import binance_helper
import state_manager

load_dotenv()
client = binance_helper.get_client()


def show_balance():
    """Poore account ka balance dikhata hai — USDT + jo bhi coin ho."""
    print("=== Account Balance ===")
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


def show_positions():
    """Har open position ka detail status dikhata hai."""
    print("\n=== Open Positions ===")
    state = state_manager.load_state()
    positions = state.get("open_positions", [])

    if not positions:
        print("Abhi koi open position nahi hai state file mein.")
        return

    for pos in positions:
        symbol = pos["symbol"]
        entry_price = pos["entry_price"]
        qty = pos["qty"]
        stop_price = pos["stop_price"]

        current_price = binance_helper.get_current_price(client, symbol)

        if current_price is None:
            print(f"{symbol}: price fetch nahi ho saka.")
            continue

        entry_value = qty * entry_price
        current_value = qty * current_price
        pnl = current_value - entry_value
        pnl_pct = (pnl / entry_value) * 100

        print(f"\n--- {symbol} ---")
        print(f"Quantity: {qty}")
        print(f"Entry price: {entry_price:.10f}")
        print(f"Current price: {current_price:.10f}")
        print(f"Stop-loss: {stop_price:.10f}")
        print(f"Entry value: ${entry_value:.2f}")
        print(f"Current value: ${current_value:.2f}")
        print(f"P/L: ${pnl:+.2f} ({pnl_pct:+.2f}%)")


if __name__ == "__main__":
    show_balance()
    show_positions()