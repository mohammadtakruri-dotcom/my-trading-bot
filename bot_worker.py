import os, time, math, traceback
import requests
from binance.client import Client
from binance.exceptions import BinanceAPIException
from db import init_db, set_status, add_trade

# ================== ENV ==================
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "").strip()
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "").strip()

TG_TOKEN = os.getenv("TG_TOKEN", "").strip()
TG_ID = os.getenv("TG_ID", "").strip()

ENABLE_TRADING = os.getenv("ENABLE_TRADING", "0").strip()  # 1 = real trading
LIVE_TRADING = os.getenv("LIVE_TRADING", "0").strip()      # alias
MODE = "live" if (ENABLE_TRADING == "1" or LIVE_TRADING == "1") else "paper"

SYMBOLS = os.getenv("SYMBOLS", os.getenv("SYMBOL", "BTCUSDT")).strip()
SYMBOLS = [s.strip().upper() for s in SYMBOLS.split(",") if s.strip()]

BUY_USDT = float(os.getenv("BUY_USDT", "5"))
TP_PCT = float(os.getenv("TP_PCT", "0.7"))   # take profit %
SL_PCT = float(os.getenv("SL_PCT", "0.7"))   # stop loss %
CHECK_INTERVAL = float(os.getenv("CHECK_INTERVAL", "20"))

MIN_USDT_FREE_TO_BUY = float(os.getenv("MIN_USDT_FREE_TO_BUY", "3"))

# Risk controls
MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", "2"))  # max symbols with positions

# Cooldown to avoid instant re-buy loops (seconds)
COOLDOWN_SEC = int(os.getenv("COOLDOWN_SEC", "30"))

# Prevent telegram spam for dust/minNotional warnings
WARNED_DUST = set()

# ================== Telegram ==================
def tg_send(msg: str):
    if not TG_TOKEN or not TG_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        r = requests.post(url, timeout=10, data={"chat_id": TG_ID, "text": msg})
        if r.status_code != 200:
            print("TG ERROR:", r.status_code, (r.text or "")[:200])
    except Exception as e:
        print("TG EXC:", e)

# ================== Binance Helpers ==================
def make_client():
    if not BINANCE_API_KEY or not BINANCE_API_SECRET:
        raise RuntimeError("Missing BINANCE_API_KEY / BINANCE_API_SECRET")
    return Client(BINANCE_API_KEY, BINANCE_API_SECRET)

def get_price(client: Client, symbol: str) -> float:
    p = client.get_symbol_ticker(symbol=symbol)
    return float(p["price"])

def round_step(qty: float, step: float) -> float:
    if step == 0:
        return qty
    return math.floor(qty / step) * step

def get_lot_step(client: Client, symbol: str):
    info = client.get_symbol_info(symbol)
    if not info:
        raise RuntimeError(f"symbol info not found: {symbol}")
    step = None
    min_qty = None
    min_notional = None
    for f in info["filters"]:
        if f["filterType"] == "LOT_SIZE":
            step = float(f["stepSize"])
            min_qty = float(f["minQty"])
        if f["filterType"] in ("MIN_NOTIONAL", "NOTIONAL"):
            mn = f.get("minNotional") or f.get("notional") or f.get("minNotional", "0")
            try:
                min_notional = float(mn)
            except Exception:
                min_notional = 0.0
    return step or 0.0, min_qty or 0.0, min_notional or 0.0

def base_asset(symbol: str) -> str:
    if symbol.endswith("USDT"):
        return symbol[:-4]
    return symbol

def get_balance_free(client: Client, asset: str) -> float:
    b = client.get_asset_balance(asset=asset)
    return float(b["free"]) if b else 0.0

def market_buy(client: Client, symbol: str, usdt_amount: float):
    return client.create_order(
        symbol=symbol,
        side="BUY",
        type="MARKET",
        quoteOrderQty=f"{usdt_amount:.2f}",
    )

def market_sell(client: Client, symbol: str, qty: float):
    return client.create_order(
        symbol=symbol,
        side="SELL",
        type="MARKET",
        quantity=format_qty(qty),
    )

def format_qty(q: float) -> str:
    s = f"{q:.8f}".rstrip("0").rstrip(".")
    return s if s else "0"

def get_avg_entry_from_trades(client: Client, symbol: str, lookback: int = 500) -> float:
    trades = client.get_my_trades(symbol=symbol, limit=lookback)
    buy_qty = 0.0
    buy_cost = 0.0
    for t in trades:
        if t.get("isBuyer"):
            q = float(t["qty"])
            p = float(t["price"])
            buy_qty += q
            buy_cost += q * p
    return (buy_cost / buy_qty) if buy_qty > 0 else 0.0

# ================== Strategy ==================
def should_buy(symbol: str, price: float) -> bool:
    # Placeholder: always True (you can replace later)
    return True

def pnl_pct(entry: float, price: float) -> float:
    if entry <= 0:
        return 0.0
    return (price - entry) / entry * 100.0

# ================== Positions (in memory) ==================
POSITIONS = {}       # symbol -> {"qty": float, "entry": float}
LAST_TRADE_TS = {}   # symbol -> int timestamp (cooldown)

def load_positions_from_wallet(client: Client):
    for sym in SYMBOLS:
        asset = base_asset(sym)
        qty = get_balance_free(client, asset)
        if qty > 0:
            POSITIONS.setdefault(sym, {"qty": qty, "entry": 0.0})
            LAST_TRADE_TS.setdefault(sym, 0)

def count_open_positions():
    return sum(1 for s, v in POSITIONS.items() if float(v.get("qty", 0)) > 0)

def in_cooldown(sym: str) -> bool:
    last_ts = int(LAST_TRADE_TS.get(sym, 0) or 0)
    return (time.time() - last_ts) < COOLDOWN_SEC

def mark_trade(sym: str):
    LAST_TRADE_TS[sym] = int(time.time())

def warn_dust_once(sym: str, notional: float, min_notional: float, qty: float, price: float):
    key = f"{sym}-dust"
    if key in WARNED_DUST:
        return
    WARNED_DUST.add(key)
    msg = f"⚠️ Can't trade {sym}: notional {notional:.4f} < minNotional {min_notional}. Position is too small (dust)."
    print(msg)
    tg_send(msg)
    add_trade(sym, "INFO", qty, price, f"DUST notional {notional:.4f} < {min_notional}")

def main():
    init_db()
    tg_send("🤖 Bot worker started.")
    print("🤖 BOT WORKER STARTED")

    client = make_client()

    # Load existing holdings into positions (for auto-sell/TP/SL)
    load_positions_from_wallet(client)

    while True:
        try:
            usdt_free = get_balance_free(client, "USDT")

            for sym in SYMBOLS:
                price = get_price(client, sym)
                pos = POSITIONS.get(sym, {"qty": 0.0, "entry": 0.0})
                qty = float(pos.get("qty", 0.0))
                entry = float(pos.get("entry", 0.0))

                # If holding exists but entry unknown => compute avg entry from trades
                if qty > 0 and entry <= 0:
                    avg = 0.0
                    if MODE == "live":
                        try:
                            avg = get_avg_entry_from_trades(client, sym)
                        except Exception as e:
                            print("AvgEntry Error:", e)

                    if avg > 0:
                        POSITIONS[sym]["entry"] = avg
                        entry = avg
                        tg_send(f"📌 Detected holding {sym} qty={qty:.6f}. Avg entry={avg:.6f}")
                    else:
                        POSITIONS[sym]["entry"] = price
                        entry = price
                        tg_send(f"📌 Detected holding {sym} qty={qty:.6f}. Entry unknown, baseline={price:.6f}")

                p = pnl_pct(entry, price) if qty > 0 else 0.0
                open_pos = count_open_positions()

                set_status(
                    mode=MODE,
                    last_heartbeat=int(time.time()),
                    symbol=sym,
                    price=price,
                    pnl=round(p, 4),
                    position_qty=qty,
                    position_entry=entry,
                    last_action=f"tick usdt_free={usdt_free:.4f} open_pos={open_pos}",
                    last_error=""
                )

                # ---------- SELL logic ----------
                if qty > 0:
                    # Take Profit
                    if p >= TP_PCT:
                        msg = f"✅ TP reached {sym} pnl={p:.2f}% -> SELL"
                        print(msg)
                        tg_send(msg)

                        if MODE == "live":
                            step, min_qty, min_notional = get_lot_step(client, sym)
                            sell_qty = round_step(qty, step)
                            notional = sell_qty * price

                            if sell_qty < min_qty:
                                # qty too small, treat as dust and skip
                                warn_dust_once(sym, notional, min_notional or 0.0, qty, price)
                                continue

                            if min_notional > 0 and notional < min_notional:
                                warn_dust_once(sym, notional, min_notional, qty, price)
                                continue

                            market_sell(client, sym, sell_qty)
                            add_trade(sym, "SELL", sell_qty, price, f"TP {p:.2f}%")
                            POSITIONS[sym]["qty"] = max(0.0, qty - sell_qty)
                            mark_trade(sym)

                            # refresh USDT after trade
                            usdt_free = get_balance_free(client, "USDT")
                        else:
                            add_trade(sym, "SELL", qty, price, f"PAPER TP {p:.2f}%")
                            POSITIONS[sym]["qty"] = 0.0
                            mark_trade(sym)

                        continue

                    # Stop Loss
                    if p <= -SL_PCT:
                        msg = f"🛑 SL hit {sym} pnl={p:.2f}% -> SELL"
                        print(msg)
                        tg_send(msg)

                        if MODE == "live":
                            step, min_qty, min_notional = get_lot_step(client, sym)
                            sell_qty = round_step(qty, step)
                            notional = sell_qty * price

                            if sell_qty < min_qty:
                                warn_dust_once(sym, notional, min_notional or 0.0, qty, price)
                                continue

                            if min_notional > 0 and notional < min_notional:
                                warn_dust_once(sym, notional, min_notional, qty, price)
                                continue

                            market_sell(client, sym, sell_qty)
                            add_trade(sym, "SELL", sell_qty, price, f"SL {p:.2f}%")
                            POSITIONS[sym]["qty"] = max(0.0, qty - sell_qty)
                            mark_trade(sym)

                            # refresh USDT after trade
                            usdt_free = get_balance_free(client, "USDT")
                        else:
                            add_trade(sym, "SELL", qty, price, f"PAPER SL {p:.2f}%")
                            POSITIONS[sym]["qty"] = 0.0
                            mark_trade(sym)

                        continue

                    print(f"⏳ {sym} holding | price={price:.6f} pnl={p:.2f}% qty={qty:.6f}")
                    continue

                # ---------- BUY logic ----------
                open_pos = count_open_positions()

                if open_pos >= MAX_OPEN_POSITIONS:
                    print(f"⚠️ Max positions reached ({MAX_OPEN_POSITIONS}). Skip buy {sym}")
                    continue

                if usdt_free < MIN_USDT_FREE_TO_BUY:
                    print(f"⚠️ USDT free too low: {usdt_free:.4f}. Skip buy {sym}")
                    continue

                if in_cooldown(sym):
                    print(f"⏳ Cooldown active for {sym} ({COOLDOWN_SEC}s). Skip buy.")
                    continue

                if should_buy(sym, price):
                    msg = f"🟢 BUY signal {sym} buy_usdt={BUY_USDT} mode={MODE}"
                    print(msg)
                    tg_send(msg)

                    if MODE == "live":
                        step, min_qty, min_notional = get_lot_step(client, sym)
                        if min_notional > 0 and BUY_USDT < min_notional:
                            # Can't buy because BUY_USDT too small -> warn once and skip
                            warn_dust_once(sym, BUY_USDT, min_notional, 0.0, price)
                            continue

                        market_buy(client, sym, BUY_USDT)

                        asset = base_asset(sym)
                        qty_new = get_balance_free(client, asset)

                        POSITIONS[sym] = {"qty": qty_new, "entry": price}
                        add_trade(sym, "BUY", qty_new, price, "LIVE market buy")
                        mark_trade(sym)

                        usdt_free = get_balance_free(client, "USDT")
                    else:
                        qty_paper = BUY_USDT / price
                        POSITIONS[sym] = {"qty": qty_paper, "entry": price}
                        add_trade(sym, "BUY", qty_paper, price, "PAPER buy")
                        mark_trade(sym)

                time.sleep(1)

            time.sleep(CHECK_INTERVAL)

        except BinanceAPIException as e:
            err = f"Binance API Error: {e}"
            print("❌", err)
            tg_send("❌ " + err)
            set_status(last_error=err, last_action="error")
            time.sleep(10)

        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            print("❌", err)
            print(traceback.format_exc())
            tg_send("❌ " + err)
            set_status(last_error=err, last_action="error")
            time.sleep(10)

if __name__ == "__main__":
    main()
