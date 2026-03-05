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
TP_PCT = float(os.getenv("TP_PCT", "2"))
SL_PCT = float(os.getenv("SL_PCT", "1"))
CHECK_INTERVAL = float(os.getenv("CHECK_INTERVAL", "20"))

MIN_USDT_FREE_TO_BUY = float(os.getenv("MIN_USDT_FREE_TO_BUY", "12"))
MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", "2"))
COOLDOWN_SEC = int(os.getenv("COOLDOWN_SEC", "60"))  # عملي: دقيقة

# Dust behavior (عملي)
DUST_IGNORE = os.getenv("DUST_IGNORE", "1").strip()          # 1 = اعتبر الـ dust كأنه لا يوجد صفقة (يسمح بالشراء)
DUST_IGNORE_BUFFER = float(os.getenv("DUST_IGNORE_BUFFER", "0.3"))  # هامش أمان تحت minNotional

# Auto top-up (اختياري)
AUTO_TOPUP_DUST = os.getenv("AUTO_TOPUP_DUST", "0").strip()  # عملياً: 0 أفضل حتى لا يستهلك USDT
DUST_SELL_TARGET_USDT = float(os.getenv("DUST_SELL_TARGET_USDT", "7"))
DUST_TOPUP_MAX_USDT = float(os.getenv("DUST_TOPUP_MAX_USDT", "20"))
DUST_TOPUP_COOLDOWN_SEC = int(os.getenv("DUST_TOPUP_COOLDOWN_SEC", "900"))

# ================== Anti-spam ==================
LAST_NOTICE_TS = {}
NOTICE_COOLDOWN = 45

def notice(key: str, msg: str):
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
        symbol=symbol, side="BUY", type="MARKET",
        quoteOrderQty=f"{usdt_amount:.2f}",
    )

def market_sell(client: Client, symbol: str, qty: float):
    return client.create_order(
        symbol=symbol, side="SELL", type="MARKET",
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
    # عملي: الآن نشتري فقط عند عدم وجود صفقة (وسيتم ذلك في المنطق أدناه)
    return True

def pnl_pct(entry: float, price: float) -> float:
    if entry <= 0:
        return 0.0
    return (price - entry) / entry * 100.0

# ================== State ==================
POSITIONS = {}      # symbol -> {"qty": float, "entry": float}
LAST_TRADE_TS = {}  # symbol -> ts
LAST_TOPUP_TS = {}  # symbol -> ts

def in_cooldown(sym: str) -> bool:
    last_ts = int(LAST_TRADE_TS.get(sym, 0) or 0)
    return (time.time() - last_ts) < COOLDOWN_SEC

def mark_trade(sym: str):
    LAST_TRADE_TS[sym] = int(time.time())

def count_open_positions(client: Client) -> int:
    # يعتمد على المحفظة، مش الذاكرة
    cnt = 0
    for sym in SYMBOLS:
        asset = base_asset(sym)
        qty = get_balance_free(client, asset)
        if qty > 0:
            cnt += 1
    return cnt

def can_topup(sym: str) -> bool:
    last_ts = int(LAST_TOPUP_TS.get(sym, 0) or 0)
    return (time.time() - last_ts) > DUST_TOPUP_COOLDOWN_SEC

def mark_topup(sym: str):
    LAST_TOPUP_TS[sym] = int(time.time())

def is_dust(qty: float, price: float, min_notional: float) -> bool:
    if qty <= 0 or min_notional <= 0:
        return False
    notional = qty * price
    return notional < (min_notional - DUST_IGNORE_BUFFER)

def safe_buy(client: Client, sym: str, price: float) -> bool:
    if MODE != "live":
        # paper buy
        qty_paper = BUY_USDT / price
        POSITIONS[sym] = {"qty": qty_paper, "entry": price}
        add_trade(sym, "BUY", qty_paper, price, "PAPER buy")
        tg_send(f"🟢 PAPER BOUGHT {sym} qty={qty_paper:.6f}")
        return True

    step, min_qty, min_notional = get_lot_step(client, sym)

    # هامش أمان: لازم BUY_USDT يكون >= minNotional + 1
    if min_notional > 0 and BUY_USDT < (min_notional + 1.0):
        notice(f"{sym}-buy-too-small",
               f"⚠️ BUY blocked {sym}: BUY_USDT={BUY_USDT} < minNotional+1={min_notional+1:.2f}")
        return False

    usdt_free = get_balance_free(client, "USDT")
    if usdt_free < max(MIN_USDT_FREE_TO_BUY, BUY_USDT):
        notice(f"{sym}-no-usdt",
               f"⚠️ Not enough USDT to buy {sym}: free={usdt_free:.2f}")
        return False

    tg_send(f"🟢 BUY {sym} amount={BUY_USDT:.2f} USDT (MODE=live)")
    market_buy(client, sym, BUY_USDT)
    time.sleep(1)

    asset = base_asset(sym)
    qty_new = get_balance_free(client, asset)
    if qty_new <= 0:
        notice(f"{sym}-buy-no-fill",
               f"⚠️ BUY sent but balance not updated yet for {sym}.")
        return False

    POSITIONS[sym] = {"qty": qty_new, "entry": price}
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

    # إذا Dust: عملياً نتجاهله (ولا top-up)
    if min_notional > 0 and notional < min_notional:
        notice(f"{sym}-dust-skip",
               f"⚠️ SELL blocked {sym}: notional={notional:.4f} < minNotional={min_notional} (dust). Skipping.")
        return False

    if sell_qty < min_qty:
        notice(f"{sym}-minqty",
               f"⚠️ SELL blocked {sym}: sell_qty={sell_qty} < minQty={min_qty}")
        return False

    if MODE != "live":
        add_trade(sym, "SELL", sell_qty, price, f"PAPER {reason}")
        tg_send(f"✅ PAPER SOLD {sym} qty={sell_qty} ({reason})")
        POSITIONS[sym]["qty"] = 0.0
        return True

    market_sell(client, sym, sell_qty)
    add_trade(sym, "SELL", sell_qty, price, reason)
    tg_send(f"✅ SOLD {sym} qty={sell_qty} notional={notional:.2f} ({reason})")
    return True

def main():
    init_db()
    tg_send(f"🤖 Bot worker started. MODE={MODE}")
    print("🤖 BOT WORKER STARTED MODE=", MODE)

    client = make_client()

    while True:
        try:
            usdt_free = get_balance_free(client, "USDT")

            for sym in SYMBOLS:
                price = get_price(client, sym)
                asset = base_asset(sym)

                # ✅ تحديث الكمية من المحفظة كل مرة
                wallet_qty = get_balance_free(client, asset)
                step, min_qty, min_notional = get_lot_step(client, sym)

                # entry tracking
                pos = POSITIONS.get(sym, {"qty": 0.0, "entry": 0.0})
                entry = float(pos.get("entry", 0.0))

                # إذا عندي holding لكن Dust و DUST_IGNORE=1 => اعتبره صفر حتى يسمح بالشراء
                if DUST_IGNORE == "1" and is_dust(wallet_qty, price, min_notional):
                    POSITIONS[sym] = {"qty": 0.0, "entry": 0.0}
                    wallet_qty_effective = 0.0
                else:
                    POSITIONS.setdefault(sym, {"qty": wallet_qty, "entry": entry})
                    POSITIONS[sym]["qty"] = wallet_qty
                    wallet_qty_effective = wallet_qty

                # إذا holding حقيقي و entry غير معروف
                if wallet_qty_effective > 0 and entry <= 0:
                    avg = 0.0
                    if MODE == "live":
                        try:
                            avg = get_avg_entry_from_trades(client, sym)
                        except Exception:
                            avg = 0.0
                    if avg > 0:
                        POSITIONS[sym]["entry"] = avg
                        entry = avg
                        tg_send(f"📌 Holding {sym} qty={wallet_qty_effective:.6f}. Avg entry={avg:.6f}")
                    else:
                        POSITIONS[sym]["entry"] = price
                        entry = price
                        tg_send(f"📌 Holding {sym} qty={wallet_qty_effective:.6f}. Entry unknown baseline={price:.6f}")

                p = pnl_pct(entry, price) if wallet_qty_effective > 0 else 0.0
                open_pos = count_open_positions(client)

                set_status(
                    mode=MODE,
                    last_heartbeat=int(time.time()),
                    symbol=sym,
                    price=price,
                    pnl=round(p, 4),
                    position_qty=wallet_qty_effective,
                    position_entry=entry,
                    last_action=f"tick usdt_free={usdt_free:.2f} open_pos={open_pos}",
                    last_error=""
                )

                # ---------- SELL ----------
                if wallet_qty_effective > 0:
                    if p >= TP_PCT and not in_cooldown(sym):
                        tg_send(f"✅ TP reached {sym} pnl={p:.2f}% -> TRY SELL")
                        if safe_sell(client, sym, price, f"TP {p:.2f}%"):
                            mark_trade(sym)
                            time.sleep(1)
                        continue

                    if p <= -SL_PCT and not in_cooldown(sym):
                        tg_send(f"🛑 SL hit {sym} pnl={p:.2f}% -> TRY SELL")
                        if safe_sell(client, sym, price, f"SL {p:.2f}%"):
                            mark_trade(sym)
                            time.sleep(1)
                        continue

                    # holding
                    continue

                # ---------- BUY ----------
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
