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

ENABLE_TRADING = os.getenv("ENABLE_TRADING", "0").strip()  # 1 = REAL trading
MODE = "live" if ENABLE_TRADING == "1" else "paper"

# ---- Auto symbol picker ----
AUTO_PICK = os.getenv("AUTO_PICK", "1").strip()           # 1 = pick top movers automatically
TOP_N = int(os.getenv("TOP_N", "6"))                      # how many symbols to trade
SYMBOL_REFRESH_SEC = int(os.getenv("SYMBOL_REFRESH_SEC", "600"))  # refresh top symbols every 10min

# Optional manual override (if AUTO_PICK=0)
SYMBOLS = os.getenv("SYMBOLS", os.getenv("SYMBOL", "BTCUSDT,ETHUSDT")).strip()
SYMBOLS = [s.strip().upper() for s in SYMBOLS.split(",") if s.strip()]

# ---- Trading controls ----
BUY_USDT = float(os.getenv("BUY_USDT", "10"))             # per trade
TP_PCT = float(os.getenv("TP_PCT", "0.5"))                # scalp TP %
SL_PCT = float(os.getenv("SL_PCT", "0.6"))                # scalp SL %
CHECK_INTERVAL = float(os.getenv("CHECK_INTERVAL", "5"))  # seconds

MIN_USDT_FREE_TO_BUY = float(os.getenv("MIN_USDT_FREE_TO_BUY", "10"))
MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", "5"))
COOLDOWN_SEC = int(os.getenv("COOLDOWN_SEC", "20"))

# ---- Strategy (EMA+RSI) ----
TIMEFRAME = os.getenv("TIMEFRAME", "1m").strip()          # 1m scalping
KLINES_LIMIT = int(os.getenv("KLINES_LIMIT", "120"))      # candles to compute indicators

EMA_FAST = int(os.getenv("EMA_FAST", "5"))
EMA_SLOW = int(os.getenv("EMA_SLOW", "13"))
RSI_PERIOD = int(os.getenv("RSI_PERIOD", "14"))

# More trades = relax RSI a bit
RSI_BUY_MIN = float(os.getenv("RSI_BUY_MIN", "45"))       # allow buy if RSI >= 45
RSI_BUY_MAX = float(os.getenv("RSI_BUY_MAX", "72"))       # and <= 72
RSI_SELL_MIN = float(os.getenv("RSI_SELL_MIN", "55"))     # sell helper (optional)
RSI_SELL_MAX = float(os.getenv("RSI_SELL_MAX", "90"))

# ---- Market filters for auto-pick ----
MIN_QUOTE_VOL = float(os.getenv("MIN_QUOTE_VOL", "15000000"))  # 24h quoteVolume in USDT
MIN_PRICE = float(os.getenv("MIN_PRICE", "0.03"))              # ignore micro-price pairs
EXCLUDE = os.getenv("EXCLUDE", "USDCUSDT,BUSDUSDT,TUSDUSDT,FDUSDUSDT,USDPUSDT,DAIUSDT").upper()
EXCLUDE = set([x.strip() for x in EXCLUDE.split(",") if x.strip()])

# ================== Telegram ==================
_last_tg = {}
def tg_send(msg: str, key: str = "", cooldown: int = 20):
    if not TG_TOKEN or not TG_ID:
        return
    try:
        if key:
            now = time.time()
            if key in _last_tg and (now - _last_tg[key]) < cooldown:
                return
            _last_tg[key] = now

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

def get_balance_free(client: Client, asset: str) -> float:
    b = client.get_asset_balance(asset=asset)
    return float(b["free"]) if b else 0.0

def base_asset(symbol: str) -> str:
    return symbol[:-4] if symbol.endswith("USDT") else symbol

def format_qty(q: float) -> str:
    s = f"{q:.8f}".rstrip("0").rstrip(".")
    return s if s else "0"

def round_step(qty: float, step: float) -> float:
    if step == 0:
        return qty
    return math.floor(qty / step) * step

def get_filters(client: Client, symbol: str):
    info = client.get_symbol_info(symbol)
    if not info:
        raise RuntimeError(f"symbol info not found: {symbol}")

    step = 0.0
    min_qty = 0.0
    min_notional = 0.0

    for f in info.get("filters", []):
        t = f.get("filterType")
        if t == "LOT_SIZE":
            step = float(f.get("stepSize", "0") or 0)
            min_qty = float(f.get("minQty", "0") or 0)
        if t in ("MIN_NOTIONAL", "NOTIONAL"):
            # Binance sometimes uses NOTIONAL filter
            mn = f.get("minNotional") or f.get("notional") or f.get("minNotional", "0")
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
def ema(values, period: int):
    if len(values) < period:
        return None
    k = 2 / (period + 1)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1 - k)
    return e

def rsi(values, period: int):
    if len(values) < period + 1:
        return None
    gains = 0.0
    losses = 0.0
    for i in range(-period, 0):
        diff = values[i] - values[i-1]
        if diff >= 0:
            gains += diff
        else:
            losses += -diff
    if losses == 0:
        return 100.0
    rs = gains / losses
    return 100 - (100 / (1 + rs))

def fetch_closes(client: Client, symbol: str, interval: str, limit: int):
    kl = client.get_klines(symbol=symbol, interval=interval, limit=limit)
    closes = [float(k[4]) for k in kl]  # close price
    return closes

# ================== Auto Pick Top Movers ==================
def is_good_symbol(sym: str) -> bool:
    if not sym.endswith("USDT"):
        return False
    if sym in EXCLUDE:
        return False
    # exclude leveraged tokens
    bad = ("UPUSDT", "DOWNUSDT", "BULLUSDT", "BEARUSDT")
    if any(sym.endswith(x) for x in bad):
        return False
    return True

def pick_symbols(client: Client) -> list:
    """
    Pick TOP_N symbols by (quoteVolume + abs priceChangePercent),
    with filters to avoid low-liquidity.
    """
    tickers = client.get_ticker_24hr()  # list
    candidates = []
    for t in tickers:
        sym = t.get("symbol", "")
        if not is_good_symbol(sym):
            continue
        try:
            last_price = float(t.get("lastPrice", "0") or 0)
            qv = float(t.get("quoteVolume", "0") or 0)
            ch = float(t.get("priceChangePercent", "0") or 0)
        except Exception:
            continue

        if last_price < MIN_PRICE:
            continue
        if qv < MIN_QUOTE_VOL:
            continue

        score = (qv / 1_000_000) + abs(ch)  # simple combined score
        candidates.append((score, qv, abs(ch), sym))

    candidates.sort(reverse=True)
    picked = [c[3] for c in candidates[:TOP_N]]
    # fallback if empty
    if not picked:
        return ["BTCUSDT", "ETHUSDT"]
    return picked

# ================== Position tracking ==================
POSITIONS = {}       # symbol -> {"qty": float, "entry": float}
LAST_TRADE_TS = {}   # symbol -> ts
LAST_SYMBOL_PICK = 0
ACTIVE_SYMBOLS = []

def count_open_positions():
    return sum(1 for _, v in POSITIONS.items() if float(v.get("qty", 0)) > 0)

def in_cooldown(sym: str) -> bool:
    last_ts = int(LAST_TRADE_TS.get(sym, 0) or 0)
    return (time.time() - last_ts) < COOLDOWN_SEC

def mark_trade(sym: str):
    LAST_TRADE_TS[sym] = int(time.time())

def pnl_pct(entry: float, price: float) -> float:
    if entry <= 0:
        return 0.0
    return (price - entry) / entry * 100.0

def refresh_positions_from_wallet(client: Client, symbols: list):
    """
    Keeps POSITIONS synced with real wallet amounts in live mode
    so bot doesn't 'think' it still holds after selling.
    """
    for sym in symbols:
        asset = base_asset(sym)
        qty = get_balance_free(client, asset)
        if qty > 0:
            POSITIONS.setdefault(sym, {"qty": qty, "entry": 0.0})
            POSITIONS[sym]["qty"] = qty
        else:
            if sym in POSITIONS:
                POSITIONS[sym]["qty"] = 0.0

# ================== Strategy logic ==================
def should_buy_signal(client: Client, sym: str):
    closes = fetch_closes(client, sym, TIMEFRAME, KLINES_LIMIT)
    efast = ema(closes[-EMA_FAST*3:], EMA_FAST)  # small slice is enough
    eslow = ema(closes[-EMA_SLOW*3:], EMA_SLOW)
    rr = rsi(closes, RSI_PERIOD)
    if efast is None or eslow is None or rr is None:
        return False, {"efast": efast, "eslow": eslow, "rsi": rr}

    # Scalping entry: trend + not too overbought
    buy = (efast > eslow) and (RSI_BUY_MIN <= rr <= RSI_BUY_MAX)
    return buy, {"efast": efast, "eslow": eslow, "rsi": rr}

def should_sell_helper(client: Client, sym: str):
    closes = fetch_closes(client, sym, TIMEFRAME, KLINES_LIMIT)
    efast = ema(closes[-EMA_FAST*3:], EMA_FAST)
    eslow = ema(closes[-EMA_SLOW*3:], EMA_SLOW)
    rr = rsi(closes, RSI_PERIOD)
    if efast is None or eslow is None or rr is None:
        return False
    # exit helper: fast drops below slow or RSI too high
    return (efast < eslow) or (rr >= RSI_SELL_MIN and rr <= RSI_SELL_MAX)

# ================== Main ==================
def main():
    global LAST_SYMBOL_PICK, ACTIVE_SYMBOLS

    init_db()
    tg_send(f"🤖 Bot worker started. MODE={MODE}", key="start", cooldown=3)
    print(f"🤖 BOT WORKER STARTED MODE={MODE}")

    client = make_client()
    tg_send("✅ Binance client OK. Entering main loop.", key="init", cooldown=3)

    while True:
        try:
            # -------- pick symbols periodically --------
            now = time.time()
            if AUTO_PICK == "1" and (now - LAST_SYMBOL_PICK) > SYMBOL_REFRESH_SEC:
                picked = pick_symbols(client)
                ACTIVE_SYMBOLS = picked
                LAST_SYMBOL_PICK = now
                tg_send("📈 Auto-picked symbols:\n" + ",".join(picked), key="pick", cooldown=10)
            if AUTO_PICK != "1":
                ACTIVE_SYMBOLS = SYMBOLS

            # -------- balances --------
            usdt_free = get_balance_free(client, "USDT")

            # live: keep wallet sync
            if MODE == "live":
                refresh_positions_from_wallet(client, ACTIVE_SYMBOLS)

            open_pos = count_open_positions()

            # heartbeat log (no spam on TG)
            print(f"❤️ HEARTBEAT {int(time.time())} | USDT={usdt_free:.2f} | open_pos={open_pos} | symbols={','.join(ACTIVE_SYMBOLS)}")

            for sym in ACTIVE_SYMBOLS:
                price = get_price(client, sym)

                pos = POSITIONS.get(sym, {"qty": 0.0, "entry": 0.0})
                qty = float(pos.get("qty", 0.0))
                entry = float(pos.get("entry", 0.0))

                # if we hold but entry unknown, set baseline to current price (safe)
                if qty > 0 and entry <= 0:
                    POSITIONS.setdefault(sym, {"qty": qty, "entry": price})
                    POSITIONS[sym]["entry"] = price
                    entry = price
                    tg_send(f"📌 Holding {sym} qty={qty:.6f}. Set entry baseline={price:.6f}", key=f"hold-{sym}", cooldown=300)

                p = pnl_pct(entry, price) if qty > 0 else 0.0

                set_status(
                    mode=MODE,
                    last_heartbeat=int(time.time()),
                    symbol=sym,
                    price=price,
                    pnl=round(p, 4),
                    position_qty=qty,
                    position_entry=entry,
                    last_action=f"tick usdt_free={usdt_free:.2f} open_pos={open_pos} symbols={len(ACTIVE_SYMBOLS)}",
                    last_error=""
                )

                # ================= SELL =================
                if qty > 0:
                    # take profit / stop loss
                    hit_tp = p >= TP_PCT
                    hit_sl = p <= -SL_PCT
                    helper_exit = should_sell_helper(client, sym)

                    if hit_tp or hit_sl or helper_exit:
                        reason = "TP" if hit_tp else ("SL" if hit_sl else "HELPER_EXIT")
                        msg = f"✅ SELL signal {sym} reason={reason} pnl={p:.2f}%"
                        print(msg)
                        tg_send(msg, key=f"sell-sig-{sym}", cooldown=15)

                        if MODE == "live":
                            step, min_qty, min_notional = get_filters(client, sym)
                            sell_qty = round_step(qty, step)
                            notional = sell_qty * price

                            if sell_qty <= 0 or sell_qty < min_qty:
                                tg_send(f"⚠️ SELL blocked {sym}: qty<{min_qty} (dust). Skipping.", key=f"dust1-{sym}", cooldown=600)
                                continue
                            if min_notional > 0 and notional < min_notional:
                                tg_send(f"⚠️ SELL blocked {sym}: notional={notional:.2f} < minNotional={min_notional} (dust). Skipping.", key=f"dust2-{sym}", cooldown=600)
                                continue

                            market_sell(client, sym, sell_qty)
                            add_trade(sym, "SELL", sell_qty, price, f"{reason} pnl={p:.2f}%")
                            mark_trade(sym)

                            # refresh wallet qty
                            asset = base_asset(sym)
                            POSITIONS.setdefault(sym, {"qty": 0.0, "entry": 0.0})
                            POSITIONS[sym]["qty"] = get_balance_free(client, asset)
                            usdt_free = get_balance_free(client, "USDT")

                            tg_send(f"✅ SOLD {sym} qty={sell_qty} @ {price:.6f}", key=f"sold-{sym}", cooldown=5)
                        else:
                            add_trade(sym, "SELL", qty, price, f"PAPER {reason} pnl={p:.2f}%")
                            POSITIONS[sym]["qty"] = 0.0
                            mark_trade(sym)

                        continue

                    # holding
                    print(f"⏳ HOLD {sym} price={price:.6f} pnl={p:.2f}% qty={qty:.6f}")
                    continue

                # ================= BUY =================
                open_pos = count_open_positions()

                if open_pos >= MAX_OPEN_POSITIONS:
                    continue
                if usdt_free < MIN_USDT_FREE_TO_BUY:
                    continue
                if in_cooldown(sym):
                    continue
                if BUY_USDT > usdt_free:
                    continue

                ok, info = should_buy_signal(client, sym)
                if not ok:
                    continue

                msg = f"🟢 BUY signal {sym} (EMA {EMA_FAST}/{EMA_SLOW}, RSI={info.get('rsi'):.1f}) buy_usdt={BUY_USDT} mode={MODE}"
                print(msg)
                tg_send(msg, key=f"buy-sig-{sym}", cooldown=15)

                if MODE == "live":
                    step, min_qty, min_notional = get_filters(client, sym)

                    # Respect minNotional
                    if min_notional > 0 and BUY_USDT < min_notional:
                        tg_send(f"⚠️ BUY blocked {sym}: BUY_USDT={BUY_USDT} < minNotional={min_notional}", key=f"buy-small-{sym}", cooldown=600)
                        continue

                    market_buy(client, sym, BUY_USDT)
                    time.sleep(1.5)

                    asset = base_asset(sym)
                    qty_new = get_balance_free(client, asset)
                    if qty_new <= 0:
                        tg_send(f"⚠️ BUY failed {sym}: qty_new=0", key=f"buy-fail-{sym}", cooldown=60)
                        continue

                    POSITIONS[sym] = {"qty": qty_new, "entry": price}
                    add_trade(sym, "BUY", qty_new, price, "LIVE market buy")
                    mark_trade(sym)
                    usdt_free = get_balance_free(client, "USDT")
                    tg_send(f"✅ BOUGHT {sym} qty={qty_new:.6f} @ {price:.6f}", key=f"bought-{sym}", cooldown=5)

                else:
                    qty_paper = BUY_USDT / price
                    POSITIONS[sym] = {"qty": qty_paper, "entry": price}
                    add_trade(sym, "BUY", qty_paper, price, "PAPER buy")
                    mark_trade(sym)

                time.sleep(0.2)

            time.sleep(CHECK_INTERVAL)

        except BinanceAPIException as e:
            err = f"Binance API Error: {e}"
            print("❌", err)
            tg_send("❌ " + err, key="apierr", cooldown=20)
            set_status(last_error=err, last_action="error")
            time.sleep(5)

        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            print("❌", err)
            print(traceback.format_exc())
            tg_send("❌ " + err, key="err", cooldown=20)
            set_status(last_error=err, last_action="error")
            time.sleep(5)

if __name__ == "__main__":
    main()
