import os, time, math, traceback
from collections import deque
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

# Scalping defaults (تقدر تغيّرها من Environment)
BUY_USDT = float(os.getenv("BUY_USDT", "12"))
TP_PCT = float(os.getenv("TP_PCT", "0.6"))   # take profit % (scalp)
SL_PCT = float(os.getenv("SL_PCT", "0.6"))   # stop loss % (scalp)
CHECK_INTERVAL = float(os.getenv("CHECK_INTERVAL", "10"))

MIN_USDT_FREE_TO_BUY = float(os.getenv("MIN_USDT_FREE_TO_BUY", "15"))
MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", "2"))
COOLDOWN_SEC = int(os.getenv("COOLDOWN_SEC", "45"))

# Dust ignore
DUST_IGNORE = os.getenv("DUST_IGNORE", "1").strip()  # 1=ignore
DUST_IGNORE_BUFFER = float(os.getenv("DUST_IGNORE_BUFFER", "0.3"))

# Heartbeat
HEARTBEAT_SEC = int(os.getenv("HEARTBEAT_SEC", "30"))

# Indicators (Scalping)
KLINES_INTERVAL = os.getenv("KLINES_INTERVAL", "1m").strip()   # 1m recommended
KLINES_LIMIT = int(os.getenv("KLINES_LIMIT", "80"))            # enough for RSI/EMA
KLINES_REFRESH_SEC = int(os.getenv("KLINES_REFRESH_SEC", "45"))# refresh candles every 45s

EMA_FAST = int(os.getenv("EMA_FAST", "9"))
EMA_SLOW = int(os.getenv("EMA_SLOW", "21"))
RSI_PERIOD = int(os.getenv("RSI_PERIOD", "14"))

# Filters to avoid bad entries
RSI_BUY_MIN = float(os.getenv("RSI_BUY_MIN", "48"))
RSI_BUY_MAX = float(os.getenv("RSI_BUY_MAX", "68"))

# Extra exit rules
EXIT_ON_EMA_CROSSDOWN = os.getenv("EXIT_ON_EMA_CROSSDOWN", "1").strip()  # 1=yes
EXIT_RSI_OVERBOUGHT = float(os.getenv("EXIT_RSI_OVERBOUGHT", "75"))      # if RSI too high -> take profit earlier

# ================== Telegram (DEBUG) ==================
def tg_send(msg: str):
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
    c.ping()
    return c

def get_price(client: Client, symbol: str) -> float:
    return float(client.get_symbol_ticker(symbol=symbol)["price"])

def base_asset(symbol: str) -> str:
    return symbol[:-4] if symbol.endswith("USDT") else symbol

def get_balance_free(client: Client, asset: str) -> float:
    b = client.get_asset_balance(asset=asset)
    return float(b["free"]) if b else 0.0

def format_qty(q: float) -> str:
    s = f"{q:.8f}".rstrip("0").rstrip(".")
    return s if s else "0"

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

# ================== Indicators ==================
def ema(prev_ema: float, price: float, period: int) -> float:
    k = 2 / (period + 1)
    return price * k + prev_ema * (1 - k)

def calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return 0.0
    gains = 0.0
    losses = 0.0
    for i in range(-period, 0):
        diff = closes[i] - closes[i - 1]
        if diff >= 0:
            gains += diff
        else:
            losses += (-diff)
    if losses == 0:
        return 100.0
    rs = gains / losses
    return 100.0 - (100.0 / (1.0 + rs))

def get_klines_interval():
    # map env to binance constants
    m = {
        "1m": Client.KLINE_INTERVAL_1MINUTE,
        "3m": Client.KLINE_INTERVAL_3MINUTE,
        "5m": Client.KLINE_INTERVAL_5MINUTE,
    }
    return m.get(KLINES_INTERVAL, Client.KLINE_INTERVAL_1MINUTE)

# ================== Risk / State ==================
POSITIONS = {}       # sym -> {"entry": float}
LAST_TRADE_TS = {}   # sym -> ts
STATE = {}           # sym -> indicator state

def in_cooldown(sym: str) -> bool:
    last_ts = int(LAST_TRADE_TS.get(sym, 0) or 0)
    return (time.time() - last_ts) < COOLDOWN_SEC

def mark_trade(sym: str):
    LAST_TRADE_TS[sym] = int(time.time())

def is_dust(qty: float, price: float, min_notional: float) -> bool:
    if qty <= 0 or min_notional <= 0:
        return False
    return (qty * price) < (min_notional - DUST_IGNORE_BUFFER)

def count_open_positions_wallet(client: Client) -> int:
    cnt = 0
    for sym in SYMBOLS:
        asset = base_asset(sym)
        qty = get_balance_free(client, asset)
        if qty > 0:
            cnt += 1
    return cnt

def refresh_indicators(client: Client, sym: str):
    now = int(time.time())
    st = STATE.setdefault(sym, {
        "closes": deque(maxlen=300),
        "last_klines_ts": 0,
        "ema_fast": 0.0,
        "ema_slow": 0.0,
        "prev_ema_fast": 0.0,
        "prev_ema_slow": 0.0,
        "rsi": 0.0,
        "last_close": 0.0,
        "warm": False
    })

    if (now - st["last_klines_ts"]) < KLINES_REFRESH_SEC and st["warm"]:
        return st

    interval = get_klines_interval()
    kl = client.get_klines(symbol=sym, interval=interval, limit=KLINES_LIMIT)
    closes = [float(k[4]) for k in kl]  # close price
    st["closes"].clear()
    for c in closes:
        st["closes"].append(c)

    st["last_close"] = st["closes"][-1] if st["closes"] else 0.0
    st["rsi"] = calc_rsi(list(st["closes"]), RSI_PERIOD)

    # EMA init
    if len(st["closes"]) >= EMA_SLOW:
        # initialize with simple average for stability
        fast_init = sum(list(st["closes"])[-EMA_FAST:]) / EMA_FAST
        slow_init = sum(list(st["closes"])[-EMA_SLOW:]) / EMA_SLOW
        st["prev_ema_fast"] = st["ema_fast"] or fast_init
        st["prev_ema_slow"] = st["ema_slow"] or slow_init
        st["ema_fast"] = st["prev_ema_fast"]
        st["ema_slow"] = st["prev_ema_slow"]

        # run EMA forward over last closes for accurate current EMA
        ef = st["ema_fast"]
        es = st["ema_slow"]
        for p in list(st["closes"])[-EMA_SLOW:]:
            ef = ema(ef, p, EMA_FAST)
            es = ema(es, p, EMA_SLOW)
        st["prev_ema_fast"] = st["ema_fast"]
        st["prev_ema_slow"] = st["ema_slow"]
        st["ema_fast"] = ef
        st["ema_slow"] = es
        st["warm"] = True

    st["last_klines_ts"] = now
    return st

# ================== Scalp Strategy ==================
def should_buy_scalp(st) -> bool:
    if not st.get("warm"):
        return False

    ef = st["ema_fast"]
    es = st["ema_slow"]
    pef = st["prev_ema_fast"]
    pes = st["prev_ema_slow"]
    rsi = st["rsi"]
    close = st["last_close"]

    # Cross up: fast crosses above slow
    cross_up = (pef <= pes) and (ef > es)

    # Avoid buying in extreme zones
    rsi_ok = (RSI_BUY_MIN <= rsi <= RSI_BUY_MAX)

    # confirmation: close above fast EMA
    momentum_ok = close >= ef

    return cross_up and rsi_ok and momentum_ok

def should_exit_early(st) -> bool:
    if not st.get("warm"):
        return False
    if EXIT_ON_EMA_CROSSDOWN == "1":
        pef = st["prev_ema_fast"]
        pes = st["prev_ema_slow"]
        ef = st["ema_fast"]
        es = st["ema_slow"]
        cross_down = (pef >= pes) and (ef < es)
        if cross_down:
            return True
    if st["rsi"] >= EXIT_RSI_OVERBOUGHT:
        return True
    return False

def pnl_pct(entry: float, price: float) -> float:
    if entry <= 0:
        return 0.0
    return (price - entry) / entry * 100.0

def safe_buy(client: Client, sym: str, price: float) -> bool:
    if MODE != "live":
        qty_paper = BUY_USDT / price
        POSITIONS[sym] = {"entry": price}
        add_trade(sym, "BUY", qty_paper, price, "PAPER scalp buy")
        tg_send(f"🟢 PAPER BOUGHT {sym} qty={qty_paper:.6f}")
        return True

    step, min_qty, min_notional = get_lot_step(client, sym)
    # add buffer for fees/slippage
    if min_notional > 0 and BUY_USDT < (min_notional + 1.0):
        tg_send(f"⚠️ BUY blocked {sym}: BUY_USDT too small vs minNotional")
        return False

    usdt_free = get_balance_free(client, "USDT")
    if usdt_free < max(MIN_USDT_FREE_TO_BUY, BUY_USDT):
        tg_send(f"⚠️ Not enough USDT to buy {sym}: free={usdt_free:.2f}")
        return False

    tg_send(f"🟢 SCALP BUY {sym} amount={BUY_USDT:.2f} USDT (MODE=live)")
    market_buy(client, sym, BUY_USDT)
    time.sleep(1)

    asset = base_asset(sym)
    qty_new = get_balance_free(client, asset)
    if qty_new <= 0:
        tg_send(f"⚠️ BUY sent but balance not updated yet for {sym}")
        return False

    POSITIONS[sym] = {"entry": price}
    add_trade(sym, "BUY", qty_new, price, "LIVE scalp buy")
    tg_send(f"✅ BOUGHT {sym} qty={qty_new:.6f}")
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
        tg_send(f"⚠️ SELL blocked {sym}: minQty")
        return False

    if min_notional > 0 and notional < min_notional:
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

# ================== Main ==================
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
                # refresh indicators (1m)
                st_ind = refresh_indicators(client, sym)

                price = get_price(client, sym)
                asset = base_asset(sym)
                qty_wallet = get_balance_free(client, asset)
                step, min_qty, min_notional = get_lot_step(client, sym)

                # dust ignore => treat as no position for buy logic
                if DUST_IGNORE == "1" and is_dust(qty_wallet, price, min_notional):
                    qty_effective = 0.0
                else:
                    qty_effective = qty_wallet

                entry = float(POSITIONS.get(sym, {}).get("entry", 0.0))
                p = pnl_pct(entry, price) if qty_effective > 0 else 0.0

                set_status(
                    mode=MODE,
                    last_heartbeat=int(time.time()),
                    symbol=sym,
                    price=price,
                    pnl=round(p, 4),
                    position_qty=qty_effective,
                    position_entry=entry,
                    last_action=f"tick usdt_free={usdt_free:.2f} open_pos={open_pos} rsi={st_ind.get('rsi',0):.1f}",
                    last_error=""
                )

                # ================== SELL ==================
                if qty_effective > 0:
                    if not in_cooldown(sym):
                        # hard TP/SL
                        if p >= TP_PCT:
                            tg_send(f"✅ TP hit {sym} pnl={p:.2f}% -> SELL (scalp)")
                            if safe_sell(client, sym, price, f"SCALP TP {p:.2f}%"):
                                mark_trade(sym)
                                time.sleep(1)
                            continue

                        if p <= -SL_PCT:
                            tg_send(f"🛑 SL hit {sym} pnl={p:.2f}% -> SELL (scalp)")
                            if safe_sell(client, sym, price, f"SCALP SL {p:.2f}%"):
                                mark_trade(sym)
                                time.sleep(1)
                            continue

                        # early exit if signal flips (EMA crossdown / RSI too high)
                        if should_exit_early(st_ind):
                            tg_send(f"⚡ Early exit {sym} pnl={p:.2f}% (signal flip) -> SELL")
                            if safe_sell(client, sym, price, f"SCALP early-exit pnl={p:.2f}%"):
                                mark_trade(sym)
                                time.sleep(1)
                            continue

                    # holding
                    continue

                # ================== BUY ==================
                open_pos = count_open_positions_wallet(client)
                if open_pos >= MAX_OPEN_POSITIONS:
                    continue
                if usdt_free < MIN_USDT_FREE_TO_BUY:
                    continue
                if in_cooldown(sym):
                    continue

                # Buy only if scalping signal
                if should_buy_scalp(st_ind):
                    tg_send(
                        f"🟢 SCALP SIGNAL {sym} | rsi={st_ind['rsi']:.1f} "
                        f"ema9={st_ind['ema_fast']:.6f} ema21={st_ind['ema_slow']:.6f}"
                    )
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
