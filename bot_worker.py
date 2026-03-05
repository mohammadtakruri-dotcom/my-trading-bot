import os, time, math, traceback
from collections import deque
import requests
from binance.client import Client
from binance.exceptions import BinanceAPIException
from db import init_db, set_status, add_trade

# ================== Safe ENV Parsers ==================
def getenv_str(name: str, default: str = "") -> str:
    v = os.getenv(name)
    if v is None:
        return default
    v = v.strip()
    return v if v != "" else default

def getenv_float(name: str, default: float) -> float:
    v = os.getenv(name)
    if v is None:
        return float(default)
    v = v.strip()
    if v == "":
        return float(default)
    try:
        return float(v)
    except Exception:
        return float(default)

def getenv_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None:
        return int(default)
    v = v.strip()
    if v == "":
        return int(default)
    try:
        return int(float(v))
    except Exception:
        return int(default)

# ================== ENV ==================
BINANCE_API_KEY = getenv_str("BINANCE_API_KEY", "")
BINANCE_API_SECRET = getenv_str("BINANCE_API_SECRET", "")

TG_TOKEN = getenv_str("TG_TOKEN", "")
TG_ID = getenv_str("TG_ID", "")

ENABLE_TRADING = getenv_str("ENABLE_TRADING", "0")
LIVE_TRADING = getenv_str("LIVE_TRADING", "0")
MODE = "live" if (ENABLE_TRADING == "1" or LIVE_TRADING == "1") else "paper"

SYMBOLS = getenv_str("SYMBOLS", getenv_str("SYMBOL", "BTCUSDT"))
SYMBOLS = [s.strip().upper() for s in SYMBOLS.split(",") if s.strip()]

# Scalping defaults (تقدر تغيّرها من Environment)
BUY_USDT = getenv_float("BUY_USDT", 12.0)
TP_PCT = getenv_float("TP_PCT", 0.6)   # gross take profit %
SL_PCT = getenv_float("SL_PCT", 0.6)   # gross stop loss %
CHECK_INTERVAL = getenv_float("CHECK_INTERVAL", 10.0)

MIN_USDT_FREE_TO_BUY = getenv_float("MIN_USDT_FREE_TO_BUY", 15.0)
MAX_OPEN_POSITIONS = getenv_int("MAX_OPEN_POSITIONS", 2)
COOLDOWN_SEC = getenv_int("COOLDOWN_SEC", 45)

# --- Fees / slippage controls (NEW) ---
# fee per trade in percent (e.g. 0.10 means 0.10%)
FEE_PCT = getenv_float("FEE_PCT", 0.10)
# extra buffer for spread/slippage in percent (e.g. 0.15)
SLIPPAGE_PCT = getenv_float("SLIPPAGE_PCT", 0.15)
# minimum net profit after fees+slippage to allow SELL in percent (e.g. 0.25)
MIN_NET_PROFIT_PCT = getenv_float("MIN_NET_PROFIT_PCT", 0.25)

BREAKEVEN_PCT = (2.0 * FEE_PCT) + SLIPPAGE_PCT
REQUIRED_GROSS_TP_PCT = max(TP_PCT, BREAKEVEN_PCT + MIN_NET_PROFIT_PCT)

# Dust ignore
DUST_IGNORE = getenv_str("DUST_IGNORE", "1")  # 1=ignore
DUST_IGNORE_BUFFER = getenv_float("DUST_IGNORE_BUFFER", 0.3)

# Heartbeat
HEARTBEAT_SEC = getenv_int("HEARTBEAT_SEC", 30)

# Indicators (Scalping)
KLINES_INTERVAL = getenv_str("KLINES_INTERVAL", "1m")    # 1m recommended
KLINES_LIMIT = getenv_int("KLINES_LIMIT", 80)            # enough for RSI/EMA
KLINES_REFRESH_SEC = getenv_int("KLINES_REFRESH_SEC", 45)# refresh candles every 45s

EMA_FAST = getenv_int("EMA_FAST", 9)
EMA_SLOW = getenv_int("EMA_SLOW", 21)
RSI_PERIOD = getenv_int("RSI_PERIOD", 14)

# Filters to avoid bad entries
RSI_BUY_MIN = getenv_float("RSI_BUY_MIN", 48.0)
RSI_BUY_MAX = getenv_float("RSI_BUY_MAX", 68.0)

# Extra exit rules
EXIT_ON_EMA_CROSSDOWN = getenv_str("EXIT_ON_EMA_CROSSDOWN", "1")  # 1=yes
EXIT_RSI_OVERBOUGHT = getenv_float("EXIT_RSI_OVERBOUGHT", 75.0)   # if RSI too high -> exit earlier

# ================== Telegram (DEBUG) ==================
def tg_send(msg: str):
    if not TG_TOKEN or not TG_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        requests.post(url, timeout=15, data={"chat_id": TG_ID, "text": msg})
    except Exception:
        pass

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

    if len(st["closes"]) >= EMA_SLOW:
        fast_init = sum(list(st["closes"])[-EMA_FAST:]) / EMA_FAST
        slow_init = sum(list(st["closes"])[-EMA_SLOW:]) / EMA_SLOW
        st["prev_ema_fast"] = st["ema_fast"] or fast_init
        st["prev_ema_slow"] = st["ema_slow"] or slow_init
        st["ema_fast"] = st["prev_ema_fast"]
        st["ema_slow"] = st["prev_ema_slow"]

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

    cross_up = (pef <= pes) and (ef > es)
    rsi_ok = (RSI_BUY_MIN <= rsi <= RSI_BUY_MAX)
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

def gross_pnl_pct(entry: float, price: float) -> float:
    if entry <= 0:
        return 0.0
    return (price - entry) / entry * 100.0

def net_pnl_pct(gross_pnl: float) -> float:
    # subtract fees+slippage buffers (round-trip)
    return gross_pnl - BREAKEVEN_PCT

def safe_buy(client: Client, sym: str, price: float) -> bool:
    if MODE != "live":
        qty_paper = BUY_USDT / price
        POSITIONS[sym] = {"entry": price}
        add_trade(sym, "BUY", qty_paper, price, "PAPER scalp buy")
        tg_send(f"🟢 PAPER BOUGHT {sym} qty={qty_paper:.6f}")
        return True

    step, min_qty, min_notional = get_lot_step(client, sym)
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
        POSITIONS.pop(sym, None)
        return True

    market_sell(client, sym, sell_qty)
    add_trade(sym, "SELL", sell_qty, price, reason)
    tg_send(f"✅ SOLD {sym} qty={sell_qty} notional={notional:.2f} ({reason})")

    # clear local entry to avoid wrong pnl on tiny dust
    POSITIONS.pop(sym, None)
    return True

# ================== Main ==================
def main():
    init_db()

    print(f"🤖 BOT WORKER STARTED MODE={MODE}")
    tg_send(f"🤖 Bot worker started. MODE={MODE}")

    # warn if TP is too small to beat fees
    if TP_PCT < (BREAKEVEN_PCT + MIN_NET_PROFIT_PCT):
        tg_send(
            f"⚠️ TP_PCT={TP_PCT:.2f}% is too small. "
            f"Breakeven≈{BREAKEVEN_PCT:.2f}%, MinNet={MIN_NET_PROFIT_PCT:.2f}%. "
            f"RequiredGrossTP≈{REQUIRED_GROSS_TP_PCT:.2f}% (I will use this)."
        )

    client = make_client()
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
                st_ind = refresh_indicators(client, sym)

                price = get_price(client, sym)
                asset = base_asset(sym)
                qty_wallet = get_balance_free(client, asset)
                step, min_qty, min_notional = get_lot_step(client, sym)

                if DUST_IGNORE == "1" and is_dust(qty_wallet, price, min_notional):
                    qty_effective = 0.0
                else:
                    qty_effective = qty_wallet

                entry = float(POSITIONS.get(sym, {}).get("entry", 0.0))
                gross = gross_pnl_pct(entry, price) if qty_effective > 0 else 0.0
                net = net_pnl_pct(gross) if qty_effective > 0 else 0.0

                # Save NET pnl in db to reflect true outcome
                set_status(
                    mode=MODE,
                    last_heartbeat=int(time.time()),
                    symbol=sym,
                    price=price,
                    pnl=round(net, 4),
                    position_qty=qty_effective,
                    position_entry=entry,
                    last_action=(
                        f"tick usdt_free={usdt_free:.2f} open_pos={open_pos} "
                        f"rsi={st_ind.get('rsi',0):.1f} gross={gross:.2f}% net={net:.2f}% "
                        f"reqTP≈{REQUIRED_GROSS_TP_PCT:.2f}%"
                    ),
                    last_error=""
                )

                # ================== SELL ==================
                if qty_effective > 0:
                    if not in_cooldown(sym):
                        # TP: require gross >= REQUIRED and net >= MIN_NET_PROFIT_PCT
                        if gross >= REQUIRED_GROSS_TP_PCT and net >= MIN_NET_PROFIT_PCT:
                            tg_send(
                                f"✅ TP {sym} gross={gross:.2f}% net={net:.2f}% "
                                f"(fees≈{BREAKEVEN_PCT:.2f}%) -> SELL"
                            )
                            if safe_sell(client, sym, price, f"SCALP TP gross={gross:.2f}% net={net:.2f}%"):
                                mark_trade(sym)
                                time.sleep(1)
                            continue

                        # SL (gross)
                        if gross <= -SL_PCT:
                            tg_send(f"🛑 SL {sym} gross={gross:.2f}% net={net:.2f}% -> SELL")
                            if safe_sell(client, sym, price, f"SCALP SL gross={gross:.2f}% net={net:.2f}%"):
                                mark_trade(sym)
                                time.sleep(1)
                            continue

                        # Early exit only if net is not negative (avoid selling at loss due to fees)
                        if should_exit_early(st_ind) and net >= 0:
                            tg_send(f"⚡ Early exit {sym} gross={gross:.2f}% net={net:.2f}% -> SELL")
                            if safe_sell(client, sym, price, f"SCALP early-exit gross={gross:.2f}% net={net:.2f}%"):
                                mark_trade(sym)
                                time.sleep(1)
                            continue

                    continue  # holding

                # ================== BUY ==================
                open_pos = count_open_positions_wallet(client)
                if open_pos >= MAX_OPEN_POSITIONS:
                    continue
                if usdt_free < MIN_USDT_FREE_TO_BUY:
                    continue
                if in_cooldown(sym):
                    continue

                if should_buy_scalp(st_ind):
                    tg_send(
                        f"🟢 SCALP SIGNAL {sym} | rsi={st_ind['rsi']:.1f} "
                        f"ema{EMA_FAST}={st_ind['ema_fast']:.6f} ema{EMA_SLOW}={st_ind['ema_slow']:.6f} "
                        f"reqTP≈{REQUIRED_GROSS_TP_PCT:.2f}% (net target={MIN_NET_PROFIT_PCT:.2f}%)"
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
