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
MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", "2"))
COOLDOWN_SEC = int(os.getenv("COOLDOWN_SEC", "30"))

# ===== Auto top-up for dust sells =====
AUTO_TOPUP_DUST = os.getenv("AUTO_TOPUP_DUST", "1").strip()  # 1=enabled
DUST_SELL_TARGET_USDT = float(os.getenv("DUST_SELL_TARGET_USDT", "7"))   # target > 5 to be safe
DUST_TOPUP_MAX_USDT = float(os.getenv("DUST_TOPUP_MAX_USDT", "20"))      # safety cap per topup
DUST_TOPUP_COOLDOWN_SEC = int(os.getenv("DUST_TOPUP_COOLDOWN_SEC", "900"))  # 15min

# ================== Anti-spam ==================
WARNED = set()
LAST_NOTICE_TS = {}  # key -> ts
NOTICE_COOLDOWN = 60  # seconds

def notice_once(key: str, msg: str):
    now = int(time.time())
    last = int(LAST_NOTICE_TS.get(key, 0))
    if now - last < NOTICE_COOLDOWN:
        return
    LAST_NOTICE_TS[key] = now
    print(msg)
    tg_send(msg)

# ================== Telegram ==================
def tg_send(msg: str):
    if not TG_TOKEN or not TG_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        requests.post(url, timeout=10, data={"chat_id": TG_ID, "text": msg})
    except Exception:
        pass

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
    step = 0.0
    min_qty = 0.0
    min_notional = 0.0
    for f in info.get("filters", []):
        if f.get("filterType") == "LOT_SIZE":
            step = float(f.get("stepSize", 0) or 0)
            min_qty = float(f.get("minQty", 0) or 0)
        if f.get("filterType") in ("MIN_NOTIONAL", "NOTIONAL"):
            mn = f.get("minNotional") or f.get("notional") or 0
            try:
                min_notional = float(mn)
            except Exception:
                min_notional = 0.0
    return step, min_qty, min_notional

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
    return True

def pnl_pct(entry: float, price: float) -> float:
    if entry <= 0:
        return 0.0
    return (price - entry) / entry * 100.0

# ================== Position tracking ==================
POSITIONS = {}       # symbol -> {"qty": float, "entry": float}
LAST_TRADE_TS = {}   # symbol -> int timestamp
LAST_TOPUP_TS = {}   # symbol -> int timestamp

def count_open_positions():
    return sum(1 for _, v in POSITIONS.items() if float(v.get("qty", 0)) > 0)

def in_cooldown(sym: str) -> bool:
    last_ts = int(LAST_TRADE_TS.get(sym, 0) or 0)
    return (time.time() - last_ts) < COOLDOWN_SEC

def mark_trade(sym: str):
    LAST_TRADE_TS[sym] = int(time.time())

def can_topup(sym: str) -> bool:
    last_ts = int(LAST_TOPUP_TS.get(sym, 0) or 0)
    return (time.time() - last_ts) > DUST_TOPUP_COOLDOWN_SEC

def mark_topup(sym: str):
    LAST_TOPUP_TS[sym] = int(time.time())

def safe_sell(client: Client, sym: str, price: float, reason: str) -> bool:
    """
    Sell safely:
    - refresh qty from wallet
    - check minQty/minNotional after rounding
    - if blocked and AUTO_TOPUP_DUST=1 => buy extra to reach target then sell
    - never send an order that will hit -1013 NOTIONAL
    """
    asset = base_asset(sym)
    qty_wallet = get_balance_free(client, asset)
    if qty_wallet <= 0:
        return False

    step, min_qty, min_notional = get_lot_step(client, sym)

    def compute_sell_qty(q):
        sq = round_step(q, step)
        return sq, sq * price

    sell_qty, notional = compute_sell_qty(qty_wallet)

    # If already sellable -> sell
    if sell_qty >= min_qty and (min_notional <= 0 or notional >= min_notional):
        market_sell(client, sym, sell_qty)
        add_trade(sym, "SELL", sell_qty, price, reason)
        tg_send(f"✅ SOLD {sym} qty={sell_qty} notional={notional:.2f} ({reason})")
        return True

    # If blocked -> try top-up
    if MODE == "live" and AUTO_TOPUP_DUST == "1" and can_topup(sym):
        target = max(DUST_SELL_TARGET_USDT, (min_notional + 1.0) if min_notional > 0 else DUST_SELL_TARGET_USDT)
        need = target - (qty_wallet * price)
        need = max(0.0, min(need, DUST_TOPUP_MAX_USDT))

        usdt_free = get_balance_free(client, "USDT")
        if need > 0 and usdt_free >= need:
            tg_send(f"🧩 Top-up {sym} +{need:.2f} USDT to pass minNotional then SELL")
            add_trade(sym, "BUY", 0, price, f"TOPUP +{need:.2f} USDT (enable sell)")
            market_buy(client, sym, need)
            mark_topup(sym)
            time.sleep(2)

            # refresh after top-up
            qty_wallet = get_balance_free(client, asset)
            sell_qty, notional = compute_sell_qty(qty_wallet)

            if sell_qty >= min_qty and (min_notional <= 0 or notional >= min_notional):
                market_sell(client, sym, sell_qty)
                add_trade(sym, "SELL", sell_qty, price, f"{reason} (after topup)")
                tg_send(f"✅ SOLD {sym} after top-up qty={sell_qty} notional={notional:.2f}")
                return True
        else:
            notice_once(f"{sym}-topup-no-usdt", f"⚠️ No USDT to top-up {sym}: need={need:.2f}, free={usdt_free:.2f}")

    # Still not sellable -> skip without API error
    notice_once(f"{sym}-dust-skip", f"⚠️ SELL blocked {sym}: notional={notional:.4f} < minNotional={min_notional} (dust). Skipping.")
    return False

def main():
    init_db()
    tg_send(f"🤖 Bot worker started. MODE={MODE}")
    print("🤖 BOT WORKER STARTED", "MODE=", MODE)

    client = make_client()

    while True:
        try:
            usdt_free = get_balance_free(client, "USDT")

            for sym in SYMBOLS:
                price = get_price(client, sym)
                asset = base_asset(sym)

                # ✅ Always refresh wallet qty each tick (fixes stale qty issues)
                wallet_qty = get_balance_free(client, asset)

                pos = POSITIONS.get(sym, {"qty": 0.0, "entry": 0.0})
                entry = float(pos.get("entry", 0.0))

                # Update position qty from wallet
                if wallet_qty > 0:
                    POSITIONS.setdefault(sym, {"qty": wallet_qty, "entry": entry})
                    POSITIONS[sym]["qty"] = wallet_qty
                else:
                    # no holding
                    POSITIONS.setdefault(sym, {"qty": 0.0, "entry": entry})
                    POSITIONS[sym]["qty"] = 0.0

                qty = POSITIONS[sym]["qty"]

                # entry baseline / avg entry
                if qty > 0 and entry <= 0:
                    avg = 0.0
                    if MODE == "live":
                        try:
                            avg = get_avg_entry_from_trades(client, sym)
                        except Exception:
                            avg = 0.0
                    if avg > 0:
                        POSITIONS[sym]["entry"] = avg
                        entry = avg
                        tg_send(f"📌 Holding {sym} qty={qty:.6f}. Avg entry={avg:.6f}")
                    else:
                        POSITIONS[sym]["entry"] = price
                        entry = price
                        tg_send(f"📌 Holding {sym} qty={qty:.6f}. Entry unknown, baseline={price:.6f}")

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

                # ---------- SELL ----------
                if qty > 0:
                    if p >= TP_PCT:
                        # لا نكرر الرسالة كل ثانية بدون تنفيذ
                        if not in_cooldown(sym):
                            tg_send(f"✅ TP reached {sym} pnl={p:.2f}% -> TRY SELL")
                        if MODE == "live":
                            sold = safe_sell(client, sym, price, f"TP {p:.2f}%")
                            if sold:
                                mark_trade(sym)
                                usdt_free = get_balance_free(client, "USDT")
                                POSITIONS[sym]["qty"] = get_balance_free(client, asset)
                        else:
                            add_trade(sym, "SELL", qty, price, f"PAPER TP {p:.2f}%")
                            POSITIONS[sym]["qty"] = 0.0
                            mark_trade(sym)
                        continue

                    if p <= -SL_PCT:
                        if not in_cooldown(sym):
                            tg_send(f"🛑 SL hit {sym} pnl={p:.2f}% -> TRY SELL")
                        if MODE == "live":
                            sold = safe_sell(client, sym, price, f"SL {p:.2f}%")
                            if sold:
                                mark_trade(sym)
                                usdt_free = get_balance_free(client, "USDT")
                                POSITIONS[sym]["qty"] = get_balance_free(client, asset)
                        else:
                            add_trade(sym, "SELL", qty, price, f"PAPER SL {p:.2f}%")
                            POSITIONS[sym]["qty"] = 0.0
                            mark_trade(sym)
                        continue

                    # holding
                    continue

                # ---------- BUY ----------
                if count_open_positions() >= MAX_OPEN_POSITIONS:
                    continue
                if usdt_free < MIN_USDT_FREE_TO_BUY:
                    continue
                if in_cooldown(sym):
                    continue

                if should_buy(sym, price):
                    if MODE == "live":
                        step, min_qty, min_notional = get_lot_step(client, sym)
                        if min_notional > 0 and BUY_USDT < min_notional:
                            notice_once(f"{sym}-buy-too-small", f"⚠️ Can't BUY {sym}: BUY_USDT={BUY_USDT} < minNotional={min_notional}")
                            continue

                        market_buy(client, sym, BUY_USDT)
                        time.sleep(1)
                        qty_new = get_balance_free(client, asset)
                        POSITIONS[sym] = {"qty": qty_new, "entry": price}
                        add_trade(sym, "BUY", qty_new, price, "LIVE market buy")
                        mark_trade(sym)
                        usdt_free = get_balance_free(client, "USDT")
                        tg_send(f"🟢 BOUGHT {sym} qty={qty_new:.6f} (~{BUY_USDT}$)")
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
