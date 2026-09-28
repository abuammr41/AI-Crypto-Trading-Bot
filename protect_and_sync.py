"""
protect_and_sync.py
--------------------
GENERIC script — kisi bhi coin ke liye kaam karta hai, hardcoded nahi.

Kab use karo: agar kabhi koi position "unprotected" reh jaye (OCO lagane
mein error aaye), ye script:
1. State file se us position ki details (entry_price, stop_price,
   take_profit_price) khud nikalta hai
2. Binance se ASAL free balance khud check karta hai (guess nahi karta)
3. OCO protection laga deta hai
4. State file ko naye OCO ID ke sath sync kar deta hai (taake bot ko
   pata chale protection already hai, dobara koshish na kare)

Use karne ka tarika:
    py protect_and_sync.py SYMBOLUSDT

Misal:
    py protect_and_sync.py MUBARAKUSDT
    py protect_and_sync.py AVAXUSDT
"""

import sys
from dotenv import load_dotenv
import binance_helper
import state_manager

load_dotenv()


def main():
    if len(sys.argv) != 2:
        print("Use: py protect_and_sync.py SYMBOLUSDT")
        print("Misal: py protect_and_sync.py MUBARAKUSDT")
        return

    symbol = sys.argv[1].upper()
    base_asset = symbol.replace("USDT", "")

    state = state_manager.load_state()
    pos = None
    for p in state["open_positions"]:
        if p["symbol"] == symbol:
            pos = p
            break

    if pos is None:
        print(f"[ERROR] {symbol} state mein nahi mila. position_state.json check karo.")
        return

    client = binance_helper.get_client()

    # ASAL free balance Binance se lo, guess/hardcode mat karo
    balance = client.get_asset_balance(asset=base_asset)
    qty = float(balance["free"])

    if qty <= 0:
        print(f"[ERROR] {symbol} ka free balance 0 hai — shayad already protected ya sold ho chuka.")
        return

    stop_price = pos["stop_price"]
    take_profit_price = pos["take_profit_price"]

    print(f"Placing OCO for {symbol}: qty={qty}, stop={stop_price}, take_profit={take_profit_price}")

    order = binance_helper.place_oco_sell(client, symbol, qty, take_profit_price, stop_price)

    if order is None:
        print(f"[FAILED] OCO nahi lag saka {symbol} ke liye. Manually Binance app mein check karo.")
        return

    print("OCO placed successfully:", order)

    # State sync karo naye OCO ID ke sath
    pos["oco_order_list_id"] = order.get("orderListId")
    pos["qty"] = qty  # asal balance se update, taake future trailing updates sahi hon
    state_manager.save_state(state)
    print(f"[DONE] {symbol} state mein sync ho gaya. Bot ab dobara duplicate nahi banayega.")


if __name__ == "__main__":
    main()
