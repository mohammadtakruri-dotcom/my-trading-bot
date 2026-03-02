import os
import time
import math
from datetime import datetime, timezone

from binance.client import Client
from binance.enums import SIDE_BUY, SIDE_SELL, ORDER_TYPE_MARKET
from binance.exceptions import BinanceAPIException
from binance.helpers import round_step_size


# =========================
# Config (ENV)
# =========================
MODE = os.getenv("MODE", "paper").strip().lower()         # paper | live
SYMBOLS = [s.strip().upper() for s in os.getenv("SYMBOLS", "BTCUSDT,ETHFIUSDT").split(",") if s.strip()]
TAKE_PROFIT_PCT = float(os.getenv("TAKE_PROFIT_PCT", "2.0"))   # sell when profit >= this %
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", "0"))         # sell when loss >= this % (0 disables)
MIN_USDT_POSITION = float(os.getenv("MIN_USDT_POSITION", "5")) # ignore tiny holdings under this USDT value
SLEEP_SEC = int(os.getenv("SLEEP_SEC", "20"))

API_KEY = os.getenv("BINANCE_API_KEY", "").strip()
API_SECRET = os.getenv("BINANCE_API_SECRET", "").strip()

if not API_KEY or not API_SECRET:
    raise RuntimeError("Missing BINANCE_API_KEY / BINANCE_API_SECRET")

client = Client(API_KEY, API_SECRET)


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def base_asset(symbol: str) -> str:
    # assumes quote is USDT
    if symbol.endswith("USDT"):
        return symbol[:-4]
    # fallback (not perfect)
    return symbol[:-3]


def get_symbol_filters(symbol: str):
    info = client.get_symbol_info(symbol)
    if not info:
        raise RuntimeError(f"Symbol not found: {symbol}")

    lot = next((f for f in info["filters"] if f["filterType"] == "LOT_SIZE"), None)
    min_notional = next((f for f in info["filters"] if f["filterType"] in ("MIN_NOTIONAL", "NOTIONAL")), None)

    step_size = float(lot["stepSize"]) if lot else 0.0
    min_qty = float(lot["minQty"]) if lot else 0.0
    min_notional_val = float(min_notional.get("minNotional", 0.0)) if min_notional else 0.0

    return step_size, min_qty, min_notional_val


def get_price(symbol: str) -> float:
    t = client.get_symbol_ticker(symbol=symbol)
    return float(t["price"])


def safe_qty(symbol: str, qty: float) -> float:
    step, min_qty, _ = get_symbol_filters(symbol)
    if step > 0:
        qty = float(round_step_size(qty, step))
    # floor small rounding noise
    qty = float(max(0.0, qty))
    if qty < min_qty:
        return 0.0
    return qty


def position_value_usdt(symbol: str, qty: float, price: float) -> float:
    return qty * price


def get_free_balance(asset: str) -> float:
    b = client.get_asset_balance(asset=asset)
    if not b:
        return 0.0
    return float(b["free"])


def avg_entry_from_trades(symbol: str, lookback: int = 50):
    """
    Try to compute average entry price from recent BUY trades.
    Works for manual buys too, as long as the API key can read trade history.
    """
    try:
        trades = client.get_my_trades(symbol=symbol, limit=lookback)
        buys = [t for t in trades if t.get("isBuyer") is True]
        if not buys:
            return None
        # weighted average by qty
        total_qty = 0.0
        total_cost = 0.0
        for t in buys[-lookback:]:
            qty = float(t["qty"])
            price = float(t["price"])
            total_qty += qty
            total_cost += qty * price
        if total_qty <= 0:
            return None
        return total_cost / total_qty
    except Exception:
        return None


# in-memory entry snapshot (fallback if no trade history)
ENTRY_SNAPSHOT = {}


def get_entry_price(symbol: str, current_price: float) -> float:
    """
    Priority:
    1) average entry from trades (best)
    2) snapshot from when bot first saw this holding
    """
    e = avg_entry_from_trades(symbol)
    if e:
        return float(e)

    if symbol not in ENTRY_SNAPSHOT:
        ENTRY_SNAPSHOT[symbol] = float(current_price)
    return float(ENTRY_SNAPSHOT[symbol])


def market_sell(symbol: str, qty: float):
    if MODE != "live":
        print(f"🟡 PAPER SELL (no real order) | {symbol} qty={qty}")
        return {"paper": True}

    try:
        order = client.create_order(
            symbol=symbol,
            side=SIDE_SELL,
            type=ORDER_TYPE_MARKET,
            quantity=qty,
        )
        return order
    except BinanceAPIException as e:
        raise


def manage_symbol(symbol: str):
    price = get_price(symbol)
    base = base_asset(symbol)
    qty = get_free_balance(base)
    qty = safe_qty(symbol, qty)

    if qty <= 0:
        # no holding -> nothing to sell/manage
        return

    pos_usdt = position_value_usdt(symbol, qty, price)
    if pos_usdt < MIN_USDT_POSITION:
        # ignore tiny dust
        return

    entry = get_entry_price(symbol, price)
    pnl_pct = ((price - entry) / entry) * 100.0 if entry > 0 else 0.0

    status = f"⏳ alive | {symbol} | mode={MODE} | qty={qty} | entry={entry:.6f} | price={price:.6f} | pnl={pnl_pct:.2f}% | value≈{pos_usdt:.2f} USDT"
    print(status)

    # TP
    if pnl_pct >= TAKE_PROFIT_PCT:
        print(f"✅ TAKE PROFIT hit | {symbol} pnl={pnl_pct:.2f}% >= {TAKE_PROFIT_PCT}% -> SELL")
        try:
            res = market_sell(symbol, qty)
            print(f"✅ SELL DONE | {symbol} qty={qty} | res={('paper' if MODE!='live' else 'live')}")
        except BinanceAPIException as e:
            print(f"❌ Binance API Error on SELL | {symbol} | {e}")
        return

    # SL
    if STOP_LOSS_PCT > 0 and pnl_pct <= -abs(STOP_LOSS_PCT):
        print(f"🛑 STOP LOSS hit | {symbol} pnl={pnl_pct:.2f}% <= -{STOP_LOSS_PCT}% -> SELL")
        try:
            res = market_sell(symbol, qty)
            print(f"🛑 SELL DONE | {symbol} qty={qty} | res={('paper' if MODE!='live' else 'live')}")
        except BinanceAPIException as e:
            print(f"❌ Binance API Error on SELL | {symbol} | {e}")
        return


def main():
    print("🚀 BOT WORKER STARTED")
    print(f"🧩 symbols={SYMBOLS} | mode={MODE} | TP={TAKE_PROFIT_PCT}% | SL={STOP_LOSS_PCT}% | MIN_USDT_POSITION={MIN_USDT_POSITION}")

    while True:
        try:
            for sym in SYMBOLS:
                try:
                    manage_symbol(sym)
                except BinanceAPIException as e:
                    # common errors: invalid API key, IP restriction, permissions
                    print(f"❌ Binance API Error | {sym} | {e}")
                except Exception as e:
                    print(f"❌ Error | {sym} | {e}")

        except Exception as e:
            print(f"❌ Loop error: {e}")

        time.sleep(SLEEP_SEC)


if __name__ == "__main__":
    main()
