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

ENABLE_TRADING = os.getenv("ENABLE_TRADING", "0").strip()
LIVE_TRADING = os.getenv("LIVE_TRADING", "0").strip()
MODE = "live" if (ENABLE_TRADING == "1" or LIVE_TRADING == "1") else "paper"

SYMBOLS = os.getenv("SYMBOLS", os.getenv("SYMBOL", "BTCUSDT")).strip()
SYMBOLS = [s.strip().upper() for s in SYMBOLS.split(",") if s.strip()]

BUY_USDT = float(os.getenv("BUY_USDT", "10"))
TP_PCT = float(os.getenv("TP_PCT", "2"))  # take profit %
SL_PCT = float(os.getenv("SL_PCT", "1"))  # stop loss %
CHECK_INTERVAL = float(os.getenv("CHECK_INTERVAL", "20"))

MIN_USDT_FREE_TO_BUY = float(os.getenv("MIN_USDT_FREE_TO_BUY", "12"))
MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", "2"))
COOLDOWN_SEC = int(os.getenv("COOLDOWN_SEC", "60"))

# عملي: تجاهل dust (حتى لا يمنع الشراء ولا يسبب محاولة بيع متكررة)
DUST_IGNORE = os.getenv("DUST_IGNORE", "1").strip()  # 1 = ignore dust
DUST_IGNORE_BUFFER = float(os.getenv("DUST_IGNORE_BUFFER", "0.3"))  # buffer under minNotional

# Debug / Heartbeat
HEARTBEAT_SEC = int(os.getenv("HEARTBEAT_SEC", "30"))

# ================== Telegram (DEBUG) ==================
def tg_send(msg: str):
    # هذه الدالة تطبع سبب عدم إرسال تلجرام (مهم عندك الآن)
    print("TG_SEND attempt. token?", bool(TG_TOKEN), "id?", TG_ID)
    if not TG_TOKEN or not TG_ID:
        print("TG missing TG_TOKEN/TG_ID")
        return
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        r = requests.post(url, timeout=15, data={"chat_id": TG_ID, "text": msg})
        print("TG status:", r.status_code, "resp:", (r.text or "")[:200])
    except Exception as e:
        print("TG exception:", e)

# ================== Binance Helpers ==================
def make_client():
    if not BINANCE_API_KEY or not BINANCE_API_SECRET:
        raise RuntimeError("Missing BINANCE_API_KEY / BINANCE_API_SECRET")
    c = Client(BINANCE_API_KEY, BINANCE_API_SECRET)
    # اختبار سريع (لو علق هنا ستعرف)
    c.ping()
    return c

def get_price(client: Client, symbol: str) -> float:
    return float(client.get_symbol_ticker(symbol=symbol)["price"])

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
    return symbol[:-4] if symbol.endswith("USDT") else symbol

def get_balance_free(client: Client, asset: str) -> float:
    b = client.get_asset_balance(asset=asset)
    return float(b["free"]) if b else 0.0

def format_qty(q: float) -> str:
    s = f"{q:.8f}".rstrip("0").rstrip(".")
    return s if s else "0"

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
    # Placeholder: always buy when allowed (يمكنك تطويرها لاحقًا)
    return True

def pnl_pct(entry: float, price: float) -> float:
    if entry <= 0:
        return 0.0
    return (price - entry) / entry * 100.0

def is_dust(qty: float, price: float, min_notional: float) -> bool:
    if qty <= 0 or min_notional <= 0:
        return False
    return (qty * price) < (min_notional - DUST_IGNORE_BUFFER)

# ================== State ==================
POSITIONS = {}       # sym -> {"entry": float}
LAST_TRADE_TS = {}   # sym -> ts

def in_cooldown(sym: str) -> bool:
    last_ts = int(LAST_TRADE_TS.get(sym, 0) or 0)
    return (time.time() - last_ts) < COOLDOWN_SEC

def mark_trade(sym: str):
    LAST_TRADE_TS[sym] = int(time.time())

def count_open_positions_wallet(client: Client) -> int:
    cnt = 0
    for sym in SYMBOLS:
        asset = base_asset(sym)
        qty = get_balance_free(client, asset)
        if qty > 0:
            cnt += 1
    return cnt

def safe_buy(client: Client, sym: str, price: float) -> bool:
    if MODE != "live":
        qty_paper = BUY_USDT / price
        POSITIONS[sym] = {"entry": price}
        add_trade(sym, "BUY", qty_paper, price, "PAPER buy")
        tg_send(f"🟢 PAPER BOUGHT {sym} qty={qty_paper:.6f}")
        return True

    step, min_qty, min_notional = get_lot_step(client, sym)

    # هامش أمان للـ notional
    if min_notional > 0 and BUY_USDT < (min_notional + 1.0):
        print(f"BUY blocked {sym}: BUY_USDT={BUY_USDT} < minNotional+1={min_notional+1:.2f}")
        tg_send(f"⚠️ BUY blocked {sym}: BUY_USDT too small vs minNotional")
        return False

    usdt_free = get_balance_free(client, "USDT")
    if usdt_free < max(MIN_USDT_FREE_TO_BUY, BUY_USDT):
        print(f"BUY blocked {sym}: not enough USDT free={usdt_free:.2f}")
        tg_send(f"⚠️ Not enough USDT to buy {sym}: free={usdt_free:.2f}")
        return False

    tg_send(f"🟢 BUY {sym} amount={BUY_USDT:.2f} USDT (MODE=live)")
    market_buy(client, sym, BUY_USDT)
    time.sleep(1)

    asset = base_asset(sym)
    qty_new = get_balance_free(client, asset)
    if qty_new <= 0:
        print(f"BUY sent but qty still 0 for {sym}")
        tg_send(f"⚠️ BUY sent but balance not updated yet for {sym}")
        return False

    POSITIONS[sym] = {"entry": price}
    add_trade(sym, "BUY", qty_new, price, "LIVE market buy")
    tg_send(f"✅ BOUGHT {sym} qty={qty_new:.6f} (~{BUY_USDT}$)")
    return True

def safe_sell(client: Client, sym: str, price: float, reason: str) -> bool:
    asset = base_asset(sym)
    qty_wallet = get_balance_free(client, asset)
    if qty_wallet <= 0:
        return False

    step, min_qty, min_notional = get_lot_step(client, sym)
    sell_qty = round_step(qty_wallet, step)
    notional = sell_qty * price

    if sell_qty < min_qty:
        print(f"SELL blocked {sym}: sell_qty<{min_qty} sell_qty={sell_qty}")
        tg_send(f"⚠️ SELL blocked {sym}: minQty")
        return False

    if min_notional > 0 and notional < min_notional:
        print(f"SELL blocked {sym}: notional={notional:.4f} < minNotional={min_notional} (dust)")
        tg_send(f"⚠️ SELL blocked {sym}: dust notional<{min_notional}. Skipping.")
        return False

    if MODE != "live":
        add_trade(sym, "SELL", sell_qty, price, f"PAPER {reason}")
        tg_send(f"✅ PAPER SOLD {sym} qty={sell_qty} ({reason})")
        return True

    market_sell(client, sym, sell_qty)
    add_trade(sym, "SELL", sell_qty, price, reason)
    tg_send(f"✅ SOLD {sym} qty={sell_qty} notional={notional:.2f} ({reason})")
    return True

def main():
    init_db()
    print(f"🤖 BOT WORKER STARTED MODE={MODE}")
    tg_send(f"🤖 Bot worker started. MODE={MODE}")

    print("✅ INIT: creating Binance client (ping)...")
    client = make_client()
    print("✅ INIT: client ok, entering main loop")
    tg_send("✅ TEST: Worker is running now.")

    last_hb = 0

    while True:
        try:
            now = int(time.time())
            if now - last_hb >= HEARTBEAT_SEC:
                last_hb = now
                usdt_free_dbg = get_balance_free(client, "USDT")
                print(f"💓 HEARTBEAT {now} | USDT_free={usdt_free_dbg:.2f} | symbols={','.join(SYMBOLS)}")

            usdt_free = get_balance_free(client, "USDT")
            open_pos = count_open_positions_wallet(client)

            for sym in SYMBOLS:
                price = get_price(client, sym)
                asset = base_asset(sym)
                qty_wallet = get_balance_free(client, asset)

                step, min_qty, min_notional = get_lot_step(client, sym)

                # Dust ignore: اعتبره لا يوجد صفقة حتى يسمح بالشراء
                if DUST_IGNORE == "1" and is_dust(qty_wallet, price, min_notional):
                    qty_effective = 0.0
                else:
                    qty_effective = qty_wallet

                entry = float(POSITIONS.get(sym, {}).get("entry", 0.0))

                # إذا في holding حقيقي وما عندنا entry -> احسب avg entry
                if qty_effective > 0 and entry <= 0:
                    avg = 0.0
                    if MODE == "live":
                        try:
                            avg = get_avg_entry_from_trades(client, sym)
                        except Exception as e:
                            print("AvgEntry Error:", e)
                            avg = 0.0

                    if avg > 0:
                        POSITIONS[sym] = {"entry": avg}
                        entry = avg
                        tg_send(f"📌 Holding {sym} qty={qty_effective:.6f}. Avg entry={avg:.6f}")
                    else:
                        POSITIONS[sym] = {"entry": price}
                        entry = price
                        tg_send(f"📌 Holding {sym} qty={qty_effective:.6f}. Entry unknown baseline={price:.6f}")

                p = pnl_pct(entry, price) if qty_effective > 0 else 0.0

                set_status(
                    mode=MODE,
                    last_heartbeat=int(time.time()),
                    symbol=sym,
                    price=price,
                    pnl=round(p, 4),
                    position_qty=qty_effective,
                    position_entry=entry,
                    last_action=f"tick usdt_free={usdt_free:.2f} open_pos={open_pos}",
                    last_error=""
                )

                # ============== SELL ==============
                if qty_effective > 0:
                    if (p >= TP_PCT) and (not in_cooldown(sym)):
                        tg_send(f"✅ TP reached {sym} pnl={p:.2f}% -> TRY SELL")
                        if safe_sell(client, sym, price, f"TP {p:.2f}%"):
                            mark_trade(sym)
                            time.sleep(1)
                        continue

                    if (p <= -SL_PCT) and (not in_cooldown(sym)):
                        tg_send(f"🛑 SL hit {sym} pnl={p:.2f}% -> TRY SELL")
                        if safe_sell(client, sym, price, f"SL {p:.2f}%"):
                            mark_trade(sym)
                            time.sleep(1)
                        continue

                    continue  # holding

                # ============== BUY ==============
                open_pos = count_open_positions_wallet(client)
                if open_pos >= MAX_OPEN_POSITIONS:
                    continue
                if usdt_free < MIN_USDT_FREE_TO_BUY:
                    continue
                if in_cooldown(sym):
                    continue

                if should_buy(sym, price):
                    if safe_buy(client, sym, price):
                        mark_trade(sym)
                        usdt_free = get_balance_free(client, "USDT")

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
