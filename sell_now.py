"""
sell_now.py
-----------
GENERIC script — kisi bhi coin ko turant market price par bechne ke liye,
hardcoded nahi. Agar koi OCO/stop-loss order pehle se lagi ho, use pehle
cancel karta hai (taake coins "unlock" hon), phir turant sell karta hai.

Use karne ka tarika:
    py sell_now.py SYMBOLUSDT

Misal:
    py sell_now.py MUBARAKUSDT
    py sell_now.py AVAXUSDT
"""

import sys
from dotenv import load_dotenv
import binance_helper
import state_manager

load_dotenv()


def main():
    if len(sys.argv) != 2:
        print("Use: py sell_now.py SYMBOLUSDT")
        print("Misal: py sell_now.py MUBARAKUSDT")
        return

    symbol = sys.argv[1].upper()
    base_asset = symbol.replace("USDT", "")

    client = binance_helper.get_client()

    # Agar koi open order (OCO/stop) lagi ho, pehle cancel karo taake
    # coins "locked" na rahein
    open_orders = client.get_open_orders(symbol=symbol)
    for order in open_orders:
        if order.get("orderListId", -1) != -1:
            binance_helper.cancel_oco_order(client, symbol, order["orderListId"])
        else:
            binance_helper.cancel_order(client, symbol, order["orderId"])
        print(f"Cancelled order: {order.get('orderId')}")

    balance = client.get_asset_balance(asset=base_asset)
    qty = float(balance["free"])

    if qty <= 0:
        print(f"[ERROR] {symbol} ka free balance 0 hai — bechne ke liye kuch nahi.")
        return

    print(f"Selling quantity: {qty}")
    order = binance_helper.market_sell_all(client, symbol, qty)
    print("Sell result:", order)

    if order is None:
        print("[FAILED] Sell nahi ho saka. Manually Binance app mein check karo.")
        return

    # State se bhi ye position hata do (agar thi)
    state = state_manager.load_state()
    state["open_positions"] = [p for p in state["open_positions"] if p["symbol"] != symbol]
    state_manager.save_state(state)
    print(f"[DONE] {symbol} state se bhi hata diya gaya.")


if __name__ == "__main__":
    main()
