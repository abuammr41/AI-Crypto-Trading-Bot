"""
main.py
-------
Poora bot yahan se chalta hai. Ye script ek dafa chalti hai (ek cycle),
aur bahar se loop mein baar baar call hoti hai.

Har cycle mein:
1. Lock check (duplicate-run rokna)
2. PAUSE check
3. Purani state load karna (crash-recovery)
4. Open position manage karna: trailing stop, momentum exit, take-profit
5. Daily limits check karna (flexible 4-5% profit target / 2% max loss)
6. Market-crash check
7. Agar koi position na ho, naya coin dhoondhna (RSI, MFI, support/
   resistance, order book, buyer/seller ratio sab ek call mein, phir Gemini)
8. Roz ek dafa Telegram par summary bhejna, purana log data trim karna
9. State save karna
"""

import traceback
import time
from datetime import datetime, timezone, timedelta

import config
import state_manager
import binance_helper
import gemini_helper
import telegram_helper
import trade_logger
import news_helper
import channel_monitor
import watch_logger
import dynamic_priority


def run_cycle():
    state_manager.acquire_lock()

    try:
        if state_manager.is_paused():
            print("[PAUSE] PAUSE.txt file mila, bot ruka hua hai. Kuch nahi karega.")
            return

        state = state_manager.load_state()
        state = state_manager.maybe_reset_daily_counters(state)
        state.setdefault("cooldowns", {})

        client = binance_helper.get_client()

        # ---- Existing position manage karna (agar koi hai) ----
        state["open_positions"] = _manage_open_positions(client, state["open_positions"], state)

        # Aaj ke din ka asal capital snapshot (daily limits isi par lagti hain).
        # Position-management ke BAAD liya jata hai — taake agar koi position
        # bot band hone ke dauran exchange par bik chuki ho, uski value
        # (USDT + purani position) do dafa count na ho.
        _ensure_day_start_capital(client, state)

        # ---- Daily limits check ----
        if state["daily_pnl_usdt"] <= -_daily_loss_limit_usdt(state):
            print("[LIMIT] Daily max loss hit. Naya trade nahi lenge is round.")
            _maybe_send_daily_summary(state, client)
            state_manager.save_state(state)
            return

        if state["daily_pnl_usdt"] >= _daily_profit_target_usdt(state, use_max=True):
            print("[LIMIT] Daily profit ceiling (5%) hit. Naya trade nahi lenge.")
            _maybe_send_daily_summary(state, client)
            state_manager.save_state(state)
            return

        # ---- Market-crash check ----
        btc_change = binance_helper.get_btc_1h_change_pct(client)
        if btc_change <= -config.BTC_CRASH_THRESHOLD_PCT:
            print(f"[CRASH] BTC {btc_change:.1f}% in 1h — naya trade nahi lenge.")
            _maybe_send_daily_summary(state, client)
            state_manager.save_state(state)
            return

        # ---- Naya trade dhoondna (sirf agar koi position khuli nahi hai) ----
        if len(state["open_positions"]) < config.MAX_OPEN_POSITIONS:
            _try_new_trade(client, state)

        _maybe_send_daily_summary(state, client)
        state_manager.save_state(state)

    except Exception as e:
        print(f"[FATAL] Unexpected error in cycle: {e}")
        traceback.print_exc()
        telegram_helper.send_message(f"⚠️ Bot error this cycle:\n{e}")

    finally:
        state_manager.release_lock()


# ============================================================
# CAPITAL & DAILY LIMIT HELPERS
# ============================================================

def _daily_loss_limit_usdt(state):
    return _approx_total_capital(state) * (config.DAILY_MAX_LOSS_PCT / 100)


def _daily_profit_target_usdt(state, use_max=False):
    pct = config.DAILY_PROFIT_TARGET_MAX_PCT if use_max else config.DAILY_PROFIT_TARGET_MIN_PCT
    return _approx_total_capital(state) * (pct / 100)


def _notify_close(client, state, symbol, exit_price, pnl, note=""):
    """
    Trade close hone par Telegram par DOLLARS mein poora hisaab bhejta hai:
    is trade ka P/L, aaj ka shuru capital, aaj ka total P/L, aur ab ka
    asal capital (live Binance balance se). Percent ki jagah seedha $.
    """
    emoji = "🟢" if pnl >= 0 else "🔴"
    label = "Profit" if pnl >= 0 else "Loss"
    daily = state.get("daily_pnl_usdt", 0.0)

    start_cap = None
    if state.get("capital_date") == state.get("daily_reset_date"):
        start_cap = state.get("day_start_capital")

    now_cap = None
    try:
        free_usdt = binance_helper.get_free_usdt_balance(client)
        if free_usdt is not None:
            others = sum(p["entry_price"] * p["qty"] for p in state.get("open_positions", []) if p["symbol"] != symbol)
            now_cap = free_usdt + others
    except Exception:
        now_cap = None
    if now_cap is None and start_cap:
        now_cap = start_cap + daily

    lines = [
        f"{emoji} Position closed: {symbol} ({label})",
        f"Exit ~{exit_price:.10g}",
        f"Is trade ka P/L: {pnl:+.4f} USDT",
    ]
    if start_cap:
        lines.append(f"Aaj ka shuru capital: {start_cap:.2f} USDT")
    lines.append(f"Aaj ka total P/L: {daily:+.4f} USDT")
    if now_cap is not None:
        lines.append(f"Ab capital: ~{now_cap:.2f} USDT")
    if note:
        lines.append(note)
    telegram_helper.send_message("\n".join(lines))


def _ensure_day_start_capital(client, state):
    """
    Roz (daily reset ke baad) EK dafa poore account ka asal capital
    snapshot leta hai: free USDT + khuli positions ki value. Daily
    profit-target aur max-loss isi fixed number ke % par lagte hain —
    taake position close hote hi capital "gir" na jaye (pehle bug:
    position close hone par capital sirf $6 maan liya jata tha, jisse
    chhoti si loss par bhi poora din band ho jata tha).
    """
    if state.get("capital_date") == state.get("daily_reset_date") and state.get("day_start_capital"):
        return  # aaj ka snapshot already hai

    try:
        free_usdt = binance_helper.get_free_usdt_balance(client)
    except Exception as e:
        print(f"[WARN] Capital snapshot: balance fetch fail hua: {e}")
        free_usdt = None
    if free_usdt is None:
        return  # network issue — agle cycle dobara try, tab tak purana fallback chalega

    in_positions = sum(p["entry_price"] * p["qty"] for p in state["open_positions"])
    state["day_start_capital"] = free_usdt + in_positions
    state["capital_date"] = state.get("daily_reset_date")
    print(f"[CAPITAL] Aaj ka capital snapshot: {state['day_start_capital']:.4f} USDT")


def _approx_total_capital(state):
    cap = state.get("day_start_capital")
    if cap and cap > 0:
        return cap
    # Fallback (sirf agar snapshot abhi tak nahi bana): purana tarika
    total = 0.0
    for pos in state["open_positions"]:
        total += pos["entry_price"] * pos["qty"]
    return max(total, config.MIN_ORDER_SIZE_USDT)


# ============================================================
# POSITION MANAGEMENT (trailing stop + momentum exit + take-profit)
# ============================================================

def _ensure_position_protected(client, pos):
    """
    AUTOMATIC SAFETY CHECK. Verify karta hai ke position ka OCO order
    Binance par ASAL mein active hai ya nahi (sirf state file par
    bharosa nahi karta).

    Agar koi protection na mile, BOT KHUD turant naya OCO laga deta hai.

    Return: "protected" (pehle se hai ya abhi laga di),
            "dust" (asal coins already ja chuke, sirf bekar dust bacha
            hai — is position ko state se hata dena chahiye),
            "failed" (protect nahi ho saka, Telegram par URGENT alert
            ja chuki hai).
    """
    symbol = pos["symbol"]

    try:
        open_orders = client.get_open_orders(symbol=symbol)
    except Exception as e:
        print(f"[WARN] {symbol} open orders check fail hua: {e}")
        return "protected"  # network issue ho sakta hai — agle cycle try karenge, abhi panic mat karo

    if open_orders:
        return "protected"  # protection already hai, kuch nahi karna

    # Koi protection nahi mili — BOT KHUD turant lagane ki koshish karega
    print(f"[AUTO-PROTECT] {symbol} unprotected mila — khud protect kar rahe hain.")

    base_asset = symbol.replace("USDT", "")
    try:
        balance = client.get_asset_balance(asset=base_asset)
        qty = float(balance["free"])
    except Exception as e:
        print(f"[ERROR] {symbol} balance check fail hua: {e}")
        telegram_helper.send_message(
            f"🚨 URGENT: {symbol} unprotected hai aur balance check bhi fail ho raha — Binance app mein turant check karo!"
        )
        return "failed"

    if qty <= 0:
        print(f"[INFO] {symbol} balance 0 hai — asal position already bik chuki (dust bhi nahi bacha).")
        return "dust"

    # Agar balance itna chhota hai ke koi valid order bhi nahi ban
    # sakta (sirf "dust" — bacha hua chhota sa amount), iska matlab
    # ASAL position already kisi aur tarah bik chuki hai (purani OCO
    # se, ya kisi purani manual action se) — ye position ab "khatam"
    # hai, isko state mein "active" rakhna galat hoga (aage jaa kar
    # trailing-stop update jaisi cheezein bhi fail hongi is dust par).
    price = binance_helper.get_current_price(client, symbol)
    if price and (qty * price) < (config.MIN_ORDER_SIZE_USDT * 0.5):
        print(f"[INFO] {symbol} balance sirf dust hai (~{qty * price:.4f} USDT) — asal position already close ho chuki, state se hata rahe hain.")
        return "dust"

    order = binance_helper.place_oco_sell(client, symbol, qty, pos["take_profit_price"], pos["stop_price"])
    if order:
        pos["oco_order_list_id"] = order.get("orderListId")
        pos["qty"] = qty
        telegram_helper.send_message(
            f"✅ Auto-protected: {symbol}\nStop: {pos['stop_price']:.10f}\nTake-profit: {pos['take_profit_price']:.10f}\n"
            f"(Bot ne khud detect kar ke fix kiya — koi manual kaam nahi karna pada)"
        )
        print(f"[AUTO-PROTECT] {symbol} successfully protect ho gaya.")
        return "protected"

    telegram_helper.send_message(
        f"🚨 URGENT: {symbol} unprotected hai aur auto-protect bhi fail ho gaya — Binance app mein TURANT check karo!"
    )
    return "failed"


def _manage_open_positions(client, positions, state):
    updated_positions = []

    for pos in positions:
        symbol = pos["symbol"]

        price = binance_helper.get_current_price(client, symbol)
        if price is None:
            updated_positions.append(pos)
            continue

        # ---- 0. SABSE PEHLE check karo: kya OCO already execute ho
        # chuki hai (position genuinely close ho chuki)? Ye check
        # "unprotected hai kya" wale check se PEHLE hona ZAROORI hai —
        # warna already-closed position ko "unprotected" samajh ke bot
        # uska bacha hua "dust" balance protect karne ki koshish karta
        # rehta, jo hamesha "Invalid quantity" fail hota (kyunke dust
        # itna chhota hota hai ke koi order valid nahi banta).
        if pos.get("oco_order_list_id"):
            status = binance_helper.get_order_list_status(client, symbol, pos["oco_order_list_id"])
            if status == "ALL_DONE":
                pnl = (price - pos["entry_price"]) * pos["qty"]
                state["daily_pnl_usdt"] += pnl

                if pnl < 0:
                    state["cooldowns"][symbol] = datetime.now(timezone.utc).isoformat()
                    state_manager.save_state(state)  # turant save, crash-safety

                trade_logger.log_trade(
                    "CLOSED", symbol, price,
                    qty=pos["qty"], pnl_usdt=pnl,
                    reason="OCO order executed on exchange (stop-loss or take-profit)",
                )
                _notify_close(client, state, symbol, price, pnl, "(Stop-loss ya take-profit exchange par hit hua)")
                print(f"[CLOSED] {symbol} closed, P/L: {pnl:+.2f}")
                continue  # is position ka kaam khatam, agli position par jao

        # ---- 1. Ab hi "unprotected" check karo (position genuinely
        # abhi bhi khuli hai, close nahi hui) ----
        protection_status = _ensure_position_protected(client, pos)

        if protection_status == "dust":
            # Asal position already bik chuki hai (kisi purani wajah se) —
            # ab Binance ki trade-history se ASAL exit price dhoondh kar
            # sahi P/L record karte hain, guess nahi karte.
            exit_price = binance_helper.get_recent_exit_price(client, symbol, pos["qty"])

            if exit_price is not None:
                pnl = (exit_price - pos["entry_price"]) * pos["qty"]
                state["daily_pnl_usdt"] += pnl

                if pnl < 0:
                    state["cooldowns"][symbol] = datetime.now(timezone.utc).isoformat()
                    state_manager.save_state(state)

                trade_logger.log_trade(
                    "CLOSED", symbol, exit_price,
                    qty=pos["qty"], pnl_usdt=pnl,
                    reason="Position dust ke through detect hui, trade-history se exit price nikala",
                )
                _notify_close(client, state, symbol, exit_price, pnl, "(Trade-history se exact exit price nikala)")
                print(f"[CLOSED] {symbol} closed (dust-detected), P/L: {pnl:+.4f}")
            else:
                # Trade history se bhi exit price nahi mila — purana
                # fallback (bina P/L ke, sirf state se hatao)
                print(f"[INFO] {symbol} ko state se hata rahe hain (dust-only, exit price bhi nahi mila).")
                telegram_helper.send_message(
                    f"ℹ️ {symbol} ko tracking se hata diya — asal coins already bik chuke the, "
                    f"exact P/L record nahi ho saka. Binance app mein trade history check kar sakte ho."
                )
            continue  # is position ko updated_positions mein wapas nahi daalna — khatam

        if protection_status == "failed":
            updated_positions.append(pos)
            continue

        if price > pos["peak_price"]:
            pos["peak_price"] = price

        current_rsi = binance_helper.calculate_rsi(client, symbol)
        if current_rsi is not None and current_rsi > pos.get("peak_rsi", 0):
            pos["peak_rsi"] = current_rsi

        # ---- 2. Momentum exit check (RSI kamzor ho raha ho) ----
        # Take-profit ab humara loop check nahi karta — OCO order khud
        # exchange par (24/7) dekhta hai. Momentum exit is se alag hai
        # (RSI-based), isliye ye hamara apna proactive check rehta hai.
        peak_rsi = pos.get("peak_rsi")
        if current_rsi is not None and peak_rsi is not None:
            rsi_drop = peak_rsi - current_rsi
            if rsi_drop >= config.MOMENTUM_RSI_DROP_THRESHOLD and price > pos["entry_price"]:
                _close_position(
                    client, pos, price, state,
                    reason=f"Momentum exit — RSI dropped {rsi_drop:.1f} points from peak",
                )
                continue

        # ---- 3. Trailing stop update (OCO replace, kabhi gap nahi aata) ----
        new_stop = pos["peak_price"] * (1 - config.TRAILING_STOP_PCT / 100)

        # Sirf tab update karo jab meaningful move ho — chhoti fluctuations
        # par baar baar Binance ko call nahi jani chahiye (ek call mein
        # jitna kaam ho sake, utna karo, baar baar chhote updates nahi)
        stop_increase_pct = ((new_stop - pos["stop_price"]) / pos["stop_price"]) * 100
        if stop_increase_pct >= config.MIN_TRAIL_UPDATE_PCT:
            success = _update_oco_protection(client, pos, new_stop, pos["take_profit_price"])
            if success:
                pos["stop_price"] = new_stop
                trade_logger.log_trade(
                    "ADJUST_STOP", symbol, price,
                    qty=pos["qty"], stop_price=new_stop,
                    reason=f"Trailing stop raised to {new_stop:.10f}",
                )
                print(f"[TRAIL] {symbol} stop raised to {new_stop:.10f}")

        updated_positions.append(pos)

    return updated_positions


def _update_oco_protection(client, pos, new_stop_price, take_profit_price):
    """
    Purana OCO cancel karke naya lagata hai (naya stop, wahi take-profit).
    Binance mein locked coins ka naya order nahi lag sakta jab tak purana
    cancel na ho — isliye "pehle naya, phir purana cancel" mumkin nahi.

    Iski jagah: cancel karo, naya lagane ki 3 baar koshish karo (retry).
    Agar sab fail ho jayein, EMERGENCY FALLBACK — purani values (jo
    already kaam kar rahi thi) se dobara order lagao, taake position
    KABHI bhi bilkul unprotected na rahe.
    """
    symbol = pos["symbol"]
    old_list_id = pos.get("oco_order_list_id")

    if old_list_id:
        cancelled = binance_helper.cancel_oco_order(client, symbol, old_list_id)
        if not cancelled:
            # Cancel fail hua (ya order already gone) — retry ek baar
            time.sleep(2)
            cancelled = binance_helper.cancel_oco_order(client, symbol, old_list_id)
            if not cancelled:
                print(f"[WARN] {symbol}: purani OCO cancel nahi ho payi, naya order lagane ki koshish phir bhi karenge.")

    for attempt in range(3):
        order = binance_helper.place_oco_sell(client, symbol, pos["qty"], take_profit_price, new_stop_price)
        if order:
            pos["oco_order_list_id"] = order.get("orderListId")
            return True
        time.sleep(2)

    # Naya lagane mein 3 baar fail ho gaya — purani values se restore karo
    print(f"[EMERGENCY] {symbol}: naya stop nahi laga, purani protection restore kar rahe hain.")
    fallback = binance_helper.place_oco_sell(client, symbol, pos["qty"], take_profit_price, pos["stop_price"])
    if fallback:
        pos["oco_order_list_id"] = fallback.get("orderListId")
        return False  # trailing update fail hui, lekin protection restore ho gayi

    # Ye worst case hai — dono fail. Turant alert karo.
    telegram_helper.send_message(
        f"🚨 URGENT: {symbol} position UNPROTECTED ho sakti hai — Binance app mein turant check karo!"
    )
    return False


def _close_position(client, pos, price, state, reason):
    """Position ko turant market price par band karta hai (momentum exit ke liye)."""
    symbol = pos["symbol"]

    cancelled = True
    if pos.get("oco_order_list_id"):
        cancelled = binance_helper.cancel_oco_order(client, symbol, pos["oco_order_list_id"])

    if not cancelled:
        # Cancel fail hua — ho sakta hai OCO already khud execute ho chuki ho
        # (race condition: momentum-exit aur OCO ek sath trigger hue).
        # Agla cycle isko "ALL_DONE" check se normally handle kar lega,
        # abhi kuch aur karne ki zaroorat nahi.
        status = binance_helper.get_order_list_status(client, symbol, pos.get("oco_order_list_id"))
        if status == "ALL_DONE":
            print(f"[INFO] {symbol} OCO already executed (race with momentum-exit) — agle cycle mein close hoga.")
            return

    order = binance_helper.market_sell_all(client, symbol, pos["qty"])
    if order is None:
        # Sell fail hui — coins ab unprotected hain (OCO cancel ho chuka).
        # Emergency: purani protection wapas laga do, taake naked na rahe.
        print(f"[ERROR] Could not close {symbol}, restoring protection instead.")
        fallback = binance_helper.place_oco_sell(
            client, symbol, pos["qty"], pos["take_profit_price"], pos["stop_price"]
        )
        if fallback:
            pos["oco_order_list_id"] = fallback.get("orderListId")
        else:
            telegram_helper.send_message(
                f"🚨 URGENT: {symbol} position UNPROTECTED ho sakti hai — Binance app mein turant check karo!"
            )
        return

    fills = order.get("fills", [])
    exit_price = float(fills[0]["price"]) if fills else price

    pnl = (exit_price - pos["entry_price"]) * pos["qty"]
    state["daily_pnl_usdt"] += pnl

    if pnl < 0:
        state["cooldowns"][symbol] = datetime.now(timezone.utc).isoformat()
        state_manager.save_state(state)  # turant save, crash-safety ke liye

    trade_logger.log_trade(
        "CLOSED", symbol, exit_price,
        qty=pos["qty"], pnl_usdt=pnl, reason=reason,
    )
    _notify_close(client, state, symbol, exit_price, pnl, f"Reason: {reason}")
    print(f"[CLOSED] {symbol} closed, P/L: {pnl:+.2f}, reason: {reason}")


# ============================================================
# NEW TRADE LOGIC
# ============================================================

def _is_in_cooldown(symbol, state):
    last_loss_iso = state.get("cooldowns", {}).get(symbol)
    if not last_loss_iso:
        return False

    last_loss_time = datetime.fromisoformat(last_loss_iso)
    elapsed_minutes = (datetime.now(timezone.utc) - last_loss_time).total_seconds() / 60
    return elapsed_minutes < config.COOLDOWN_AFTER_LOSS_MINUTES


def _has_promising_signal(analysis):
    """
    Sirf BINANCE data (koi Gemini call nahi) se cheap check — kya ye
    coin itna promising hai ke Gemini ko poochne layak hai? Agar koi
    bhi acha signal na mile, Gemini call waste nahi karte.

    Kam az kam EK cheez honi chahiye:
    - Trend (1h ya 4h ya 1d) bullish ho, YA
    - Candle pattern "hammer" ho, YA
    - Volume spike ho, YA
    - Accumulation pattern ho
    """
    if analysis.get("trend_1h") == "bullish":
        return True
    if analysis.get("trend_4h") == "bullish":
        return True
    if analysis.get("trend_1d") == "bullish":
        return True
    if analysis.get("candle_pattern") in ("hammer", "bullish_engulfing"):
        return True
    if analysis.get("volume_spike"):
        return True
    if analysis.get("accumulation_pattern"):
        return True
    return False


def _trading_mode():
    """
    Pakistan time dekh kar batata hai bot abhi kis mode mein hai:
    "watch" — subah (reset se TRADING_START tak): sirf dekhna, khareedna nahi
    "trade" — active market (TRADING_START se TRADING_END tak): trade karna
    "sleep" — raat (TRADING_END ke baad, reset se pehle): naya scan nahi
    """
    hour = (datetime.now(timezone.utc) + timedelta(hours=5)).hour
    if config.TRADING_START_HOUR_PKT <= hour < config.TRADING_END_HOUR_PKT:
        return "trade"
    if config.DAILY_RESET_HOUR_PKT <= hour < config.TRADING_START_HOUR_PKT:
        return "watch"
    return "sleep"


def _update_watchlist(state, promising_candidates):
    """Promising coins ko watchlist mein daalta hai, max WATCHLIST_MAX_SIZE (sabse strong) rakhta hai."""
    wl = state.setdefault("watchlist", {})
    now_iso = datetime.now(timezone.utc).isoformat()
    for c in promising_candidates:
        sym = c["symbol"]
        score = c.get("change_24h_pct", 0) or 0
        if sym in wl:
            wl[sym]["score"] = score
        else:
            wl[sym] = {"score": score, "added": now_iso}
    # Sirf sabse strong N rakho
    top = sorted(wl.items(), key=lambda kv: kv[1].get("score", 0), reverse=True)[:config.WATCHLIST_MAX_SIZE]
    state["watchlist"] = dict(top)


def _try_new_trade(client, state):
    mode = _trading_mode()
    if mode == "sleep":
        print("[SLEEP] Raat ka waqt — naya scan/trade nahi, sirf khuli position manage hoti hai.")
        return

    # Watchlist har naye din khud saaf ho jati hai
    if state.get("watchlist_date") != state.get("daily_reset_date"):
        state["watchlist"] = {}
        state["watchlist_date"] = state.get("daily_reset_date")

    free_usdt = binance_helper.get_free_usdt_balance(client)
    if mode == "trade" and (free_usdt is None or free_usdt < config.MIN_ORDER_SIZE_USDT):
        print(f"[SKIP] Free balance ${free_usdt} below minimum order size.")
        return

    # Pehle priority tokens (established chains: Ethereum/BNB/Solana)
    # check karo. Ye list ROZ CoinGecko se khud-ba-khud fetch hoti hai
    # (cached, taake rate-limit na lage) — agar wo kisi wajah se fail
    # ho, static fallback list use hoti hai.
    all_symbols = binance_helper.get_all_usdt_symbols(client)
    dynamic_list = dynamic_priority.get_dynamic_priority_symbols(all_symbols)
    priority_symbols = dynamic_list if dynamic_list else config.PRIORITY_TOKENS

    priority = binance_helper.get_priority_tickers(client, priority_symbols, min_volume_usdt=config.MIN_VOLUME_USDT)
    gainers_extra = binance_helper.get_top_gainers(client, limit=5, min_volume_usdt=config.MIN_VOLUME_USDT)

    # Watchlist wale coins har cycle (watch + trade dono mode) mein check
    # hote hain — taake unki 20-minute history record hoti rahe, aur
    # trade-mode mein ye SABSE PEHLE consider hon
    watched = []
    if state.get("watchlist"):
        watched = binance_helper.get_priority_tickers(
            client, list(state["watchlist"].keys()), min_volume_usdt=config.MIN_VOLUME_USDT
        )

    # Duplicates hatao (watchlist → priority → top-gainers, is order mein)
    gainers = []
    seen_symbols = set()
    for g in watched + priority + gainers_extra:
        if g["symbol"] not in seen_symbols:
            gainers.append(g)
            seen_symbols.add(g["symbol"])

    # Pehle SAARE candidates ki analysis jama karo (Binance calls) —
    # Gemini ko abhi kuch nahi poochte.
    candidates = []
    for gainer in gainers:
        symbol = gainer["symbol"]
        if symbol[:-4] in config.STABLECOINS:
            continue

        if _is_in_cooldown(symbol, state):
            print(f"[COOLDOWN] {symbol} abhi cooldown mein hai (recent loss), skip.")
            continue

        price = float(gainer["lastPrice"])
        if price > config.MAX_COIN_PRICE_USDT or price < config.MIN_COIN_PRICE_USDT:
            print(f"[SKIP] {symbol} price ${price} target range se bahar hai.")
            continue

        # Ek coin ka data slow/fail ho (network timeout) to SIRF wo coin
        # skip — poora cycle band nahi hona chahiye
        try:
            analysis = binance_helper.analyze_token(client, symbol, ticker_data=gainer)
        except Exception as e:
            print(f"[WARN] {symbol} ka data nahi mila (network?), is coin ko skip: {str(e)[:120]}")
            continue
        candidates.append(analysis)

    if not candidates:
        print("[INFO] Koi candidate coin nahi mila is cycle mein (cooldown/price filter).")
        return

    # Pre-filter: sirf Binance data (free, no Gemini call) se dekho koi
    # candidate GENUINELY promising lagta hai ya nahi. Agar kisi mein bhi
    # koi accha signal na ho, Gemini ko is cycle mein bilkul mat poocho —
    # Gemini calls limited/costly hain, har cycle mein waste nahi karne.
    promising = [c for c in candidates if _has_promising_signal(c)]

    # WATCH mode: khareedna nahi — sirf promising coins ko watchlist mein
    # daal do (koi Gemini call nahi, quota bachta hai)
    if mode == "watch":
        _update_watchlist(state, promising)
        watch_logger.log_snapshot([c for c in candidates if c["symbol"] in state["watchlist"]])
        wl_list = ", ".join(state["watchlist"].keys()) or "khali"
        print(f"[WATCH] Subah ka waqt — khareed nahi rahe, sirf dekh rahe hain. Watchlist: {wl_list}")
        return

    # News calls kam karne ke liye — sirf TOP 2 promising candidates
    # (sabse zyada 24h gain wale) ke liye news fetch karo, baaki ke liye
    # nahi. Gemini ko phir bhi sirf inhi 2 (ya kam) ka data jayega.
    # Watchlist wale coins (subah se promising the) ko pehli priority,
    # phir 24h gain ke hisaab se
    wl_syms = state.get("watchlist", {})
    promising.sort(key=lambda c: (c["symbol"] in wl_syms, c.get("change_24h_pct", 0) or 0), reverse=True)
    promising = promising[:2]

    if not promising:
        print("[INFO] Koi candidate promising nahi laga (Binance data se hi pata chal gaya) — Gemini call skip.")
        return

    # Trade mode mein bhi watchlist coins ka record jaari rakho
    watch_logger.log_snapshot([c for c in candidates if c["symbol"] in state.get("watchlist", {})])

    # Watchlist coins ki subah se ab tak ki CHHOTI summary Gemini ko do
    for c in promising:
        if c["symbol"] in state.get("watchlist", {}):
            hist = watch_logger.get_summary(c["symbol"], state.get("daily_reset_date"))
            if hist:
                c["watch_history"] = hist

    # News sirf promising candidates ke liye fetch karo (chhota sa aur
    # save, kyunke ab kam coins hain is stage tak pohonchne wale)
    for c in promising:
        coin_base = news_helper.get_coin_base_symbol(c["symbol"])
        c["recent_news"] = news_helper.get_recent_news(coin_base)

    # Ab EK HI Gemini call — sirf promising candidates ek sath, Gemini
    # khud inme se best (ya koi nahi) choose karta hai.
    decision = gemini_helper.ask_best_trade(promising)
    print(f"[GEMINI] -> {decision['symbol']} {decision['action']}: {decision['reason']}")

    if decision["action"] == "BUY" and decision["symbol"]:
        _execute_buy(client, decision["symbol"], free_usdt, decision, state)
        state.get("watchlist", {}).pop(decision["symbol"], None)
    else:
        print("[INFO] Koi valid trade nahi mila is cycle mein.")


def _get_tiered_position_pct(total_balance):
    """
    Total balance ke hisaab se, is trade mein kitna % use karna hai —
    config.POSITION_SIZE_TIERS se. Jaise jaise balance barhta hai,
    percentage kam hoti jati hai (risk-management).
    """
    for threshold, pct in config.POSITION_SIZE_TIERS:
        if total_balance <= threshold:
            return pct
    return config.POSITION_SIZE_TIERS[-1][1]  # fallback: sabse aakhri tier


def _execute_buy(client, symbol, free_usdt, decision, state):
    # 1. Pehle tiered % apply karo (balance ke hisaab se)
    tier_pct = _get_tiered_position_pct(free_usdt)
    amount_to_use = free_usdt * (tier_pct / 100)

    # 2. Phir agar absolute cap (MAX_POSITION_SIZE_USDT) bhi set hai,
    # usse bhi zyada kabhi mat lagao
    if config.MAX_POSITION_SIZE_USDT is not None:
        amount_to_use = min(amount_to_use, config.MAX_POSITION_SIZE_USDT)

    # 3. Safety: agar tiered amount MIN_ORDER_SIZE se bhi kam ho jaye
    # (chhota balance, thodi si tier-cut ki wajah se), poora balance
    # use karo warna order fail ho jayega
    if amount_to_use < config.MIN_ORDER_SIZE_USDT:
        amount_to_use = free_usdt

    order = binance_helper.place_market_buy(client, symbol, amount_to_use)
    if order is None:
        print(f"[ERROR] Buy failed for {symbol}")
        return

    fills = order.get("fills", [])
    if not fills:
        print(f"[ERROR] No fill data for {symbol}, skipping state update.")
        return

    entry_price = float(fills[0]["price"])

    # ZAROORI: order["executedQty"] "gross" quantity hai (fee minus
    # hone se PEHLE) — Binance fee ko khareede hue coin mein se hi
    # kaatta hai (jab tak BNB se fee pay na ho rahi ho). Agar hum
    # executedQty seedha OCO mein use karein, wo ASAL free balance se
    # thora zyada hoga, aur "insufficient balance" error aayega.
    # Isliye ASAL free balance Binance se khud check karte hain.
    base_asset = symbol.replace("USDT", "")
    try:
        balance = client.get_asset_balance(asset=base_asset)
        qty = float(balance["free"])
    except Exception as e:
        print(f"[WARN] {symbol} asal balance check fail hua, executedQty use kar rahe hain: {e}")
        qty = float(order["executedQty"])

    # HYBRID STOP-LOSS: fixed % ki jagah, is coin ki apni support-level
    # aur volatility (ATR) dekh kar stop decide karte hain — jo bhi
    # teeno (min-floor, support-based, ATR-based) mein sabse "wide/safe"
    # ho, wahi use hota hai, MAX_LOSS_PER_TRADE_PCT (1.8%) tak capped.
    sr = binance_helper.get_support_resistance(client, symbol)
    atr = binance_helper.calculate_atr(client, symbol)
    support_price = sr["support"] if sr else None
    hybrid_stop_pct = binance_helper.calculate_hybrid_stop_pct(entry_price, support_price, atr)

    # Fees minus ki hui hain — taake NET loss (fees ke baad) kabhi
    # hybrid_stop_pct se zyada na ho
    stop_price = entry_price * (1 - (hybrid_stop_pct - config.ROUND_TRIP_FEE_PCT) / 100)
    # Take-profit price mein fees add ki hui hain — taake NET profit
    # (fees ke baad) hamesha take_profit_pct ke barabar mile
    take_profit_price = entry_price * (1 + (decision["take_profit_pct"] + config.ROUND_TRIP_FEE_PCT) / 100)

    # EK HI CALL mein stop-loss aur take-profit dono lag jate hain (OCO).
    # Exchange khud 24/7 dekhta hai konsa pehle hit hota hai.
    oco_order = binance_helper.place_oco_sell(client, symbol, qty, take_profit_price, stop_price)
    oco_list_id = oco_order.get("orderListId") if oco_order else None

    if oco_order is None:
        print(f"[ERROR] OCO protection failed for {symbol} after buy — retrying once.")
        time.sleep(2)
        oco_order = binance_helper.place_oco_sell(client, symbol, qty, take_profit_price, stop_price)
        oco_list_id = oco_order.get("orderListId") if oco_order else None

    if oco_order is None:
        telegram_helper.send_message(
            f"🚨 URGENT: {symbol} khareeda gaya lekin protection nahi lagi — Binance app mein turant check karo!"
        )

    entry_rsi = binance_helper.calculate_rsi(client, symbol)

    state["open_positions"].append({
        "symbol": symbol,
        "entry_price": entry_price,
        "qty": qty,
        "stop_price": stop_price,
        "take_profit_price": take_profit_price,
        "peak_price": entry_price,
        "peak_rsi": entry_rsi if entry_rsi is not None else 0,
        "take_profit_pct": decision["take_profit_pct"],
        "oco_order_list_id": oco_list_id,
    })

    trade_logger.log_trade(
        "BUY", symbol, entry_price, qty=qty, stop_price=stop_price,
        reason=f"{decision['reason']} (take-profit target: {decision['take_profit_pct']:.1f}%)",
    )
    telegram_helper.send_message(
        f"🟢 New position: {symbol}\nEntry: {entry_price:.10f}\nQty: {qty}\n"
        f"Stop: {stop_price:.10f}\nTake-profit: {take_profit_price:.10f} ({decision['take_profit_pct']:.1f}%)\n"
        f"Reason: {decision['reason']}"
    )
    print(f"[BUY] {symbol} at {entry_price:.10f}, stop at {stop_price:.10f}, "
          f"take-profit target {decision['take_profit_pct']:.1f}%")


# ============================================================
# DAILY SUMMARY (Telegram) + LOG TRIMMING
# ============================================================

def _maybe_send_daily_summary(state, client):
    pkt_now = datetime.now(timezone.utc) + timedelta(hours=5)
    today_str = pkt_now.strftime("%Y-%m-%d")

    if state.get("last_summary_date") == today_str:
        return

    if pkt_now.hour < config.DAILY_SUMMARY_HOUR_PKT:
        return

    open_count = len(state["open_positions"])
    pnl = state["daily_pnl_usdt"]

    summary = (
        f"📊 Daily Summary ({today_str})\n"
        f"Net P/L today: {pnl:+.2f} USDT\n"
        f"Open positions: {open_count}\n"
    )
    for pos in state["open_positions"]:
        summary += f"  • {pos['symbol']}: entry {pos['entry_price']:.10f}, stop {pos['stop_price']:.10f}\n"

    telegram_helper.send_message(summary)
    state["last_summary_date"] = today_str
    print("[SUMMARY] Daily summary sent.")

    trade_logger.trim_old_entries()
    watch_logger.trim_old_entries()

    # Roz ek dafa dust cleanup bhi karo (Binance ka apna rule: 6 ghante
    # mein ek baar allowed hai, roz ek baar isliye bilkul safe hai)
    binance_helper.cleanup_dust_to_usdt(client)

    # Roz ek dafa Binance ke official Telegram announcement channel
    # ko bhi check karo — agar API mein koi naya change/update ho
    # (jaisa OCO format wala change), turant pata chal jaye
    new_announcements = channel_monitor.get_new_announcements(state)
    if new_announcements:
        summary_text = "\n\n".join(new_announcements[:3])  # max 3 dikhao
        telegram_helper.send_message(
            f"📢 Binance API Update(s) mile:\n\n{summary_text}\n\n"
            f"Agar isse hamare bot par asar par sakta hai, Claude ko bata dena."
        )
        print(f"[ANNOUNCEMENTS] {len(new_announcements)} naye Binance updates mile.")


if __name__ == "__main__":
    run_cycle()