# bot_worker.py
import os
import time
import math
from datetime import datetime

from binance.client import Client
from binance.exceptions import BinanceAPIException

from db import init_db, set_status, get_position, open_position, close_position, add_trade

SYMBOL = os.environ.get("SYMBOL", "BTCUSDT").upper()
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "20"))
BUY_USDT = float(os.environ.get("BUY_USDT", "5"))  # ابدأ صغير
TP_PCT = float(os.environ.get("TP_PCT", "0.7"))    # 0.7% Take Profit
SL_PCT = float(os.environ.get("SL_PCT", "0.7"))    # 0.7% Stop Loss
ENABLE_TRADING = os.environ.get("ENABLE_TRADING", "0") == "1"  # 1 = LIVE
MODE = "live" if ENABLE_TRADING else "paper"

API_KEY = os.environ.get("BINANCE_API_KEY", "")
API_SECRET = os.environ.get("BINANCE_API_SECRET", "")

def _client():
    if not API_KEY or not API_SECRET:
        raise RuntimeError("Missing BINANCE_API_KEY / BINANCE_API_SECRET")
    return Client(API_KEY, API_SECRET)

def _get_price(client: Client) -> float:
    t = client.get_symbol_ticker(symbol=SYMBOL)
    return float(t["price"])

def _get_usdt_free(client: Client) -> float:
    bal = client.get_asset_balance(asset="USDT")
    return float(bal["free"]) if bal and bal.get("free") else 0.0

def _filters(client: Client):
    info = client.get_symbol_info(SYMBOL)
    if not info:
        raise RuntimeError(f"Symbol not found: {SYMBOL}")

    lot = next((f for f in info["filters"] if f["filterType"] == "LOT_SIZE"), None)
    min_notional = next((f for f in info["filters"] if f["filterType"] in ("MIN_NOTIONAL", "NOTIONAL")), None)

    step_size = float(lot["stepSize"]) if lot else 0.0
    min_qty = float(lot["minQty"]) if lot else 0.0
    min_notional_val = float(min_notional.get("minNotional", 0.0)) if min_notional else 0.0

    return step_size, min_qty, min_notional_val

def _round_step(qty: float, step: float) -> float:
    if step <= 0:
        return qty
    precision = int(round(-math.log(step, 10), 0))
    # floor to step
    floored = math.floor(qty / step) * step
    return float(f"{floored:.{precision}f}")

def _market_buy(client: Client, usdt_amount: float):
    """
    Prefer quoteOrderQty (buy by USDT amount). If not allowed, fallback to qty calc.
    """
    step, min_qty, min_notional = _filters(client)
    price = _get_price(client)

    if usdt_amount < max(min_notional, 0.0):
        raise RuntimeError(f"BUY_USDT too small. Need >= MIN_NOTIONAL ({min_notional}).")

    # Try quoteOrderQty
    try:
        order = client.create_order(
            symbol=SYMBOL,
            side="BUY",
            type="MARKET",
            quoteOrderQty=str(usdt_amount),
        )
        return order
    except BinanceAPIException:
        # Fallback to qty
        qty = usdt_amount / price
        qty = max(qty, min_qty)
        qty = _round_step(qty, step)
        if qty < min_qty:
            raise RuntimeError(f"Qty {qty} < minQty {min_qty}")
        order = client.create_order(
            symbol=SYMBOL,
            side="BUY",
            type="MARKET",
            quantity=str(qty),
        )
        return order

def _market_sell(client: Client, qty: float):
    step, min_qty, _ = _filters(client)
    qty = _round_step(qty, step)
    if qty < min_qty:
        raise RuntimeError(f"Sell qty {qty} < minQty {min_qty}")

    order = client.create_order(
        symbol=SYMBOL,
        side="SELL",
        type="MARKET",
        quantity=str(qty),
    )
    return order

def _filled_avg_price(order) -> float:
    # Binance returns fills list for MARKET orders
    fills = order.get("fills") or []
    if not fills:
        # fallback to cummulativeQuoteQty / executedQty
        eq = float(order.get("executedQty", 0) or 0)
        cq = float(order.get("cummulativeQuoteQty", 0) or 0)
        return (cq / eq) if eq > 0 else 0.0
    total_qty = sum(float(f["qty"]) for f in fills)
    total_quote = sum(float(f["qty"]) * float(f["price"]) for f in fills)
    return (total_quote / total_qty) if total_qty > 0 else 0.0

def _executed_qty(order) -> float:
    return float(order.get("executedQty", 0) or 0)

def main():
    init_db()
    client = _client()

    print("🚀 BOT WORKER STARTED")
    print(f"symbol={SYMBOL} mode={MODE} tp={TP_PCT}% sl={SL_PCT}% buy_usdt={BUY_USDT}")

    while True:
        try:
            price = _get_price(client)
            usdt_free = _get_usdt_free(client)

            pos = get_position()

            # تحديث الحالة
            set_status(MODE, usdt_free, price, last_error="", notes="alive")

            # لا يوجد مركز مفتوح => شراء
            if pos.get("is_open", 0) == 0:
                if ENABLE_TRADING:
                    if usdt_free >= BUY_USDT:
                        order = _market_buy(client, BUY_USDT)
                        avg_price = _filled_avg_price(order)
                        qty = _executed_qty(order)
                        open_position(SYMBOL, "LONG", qty, avg_price)
                        add_trade(SYMBOL, "BUY", qty, avg_price, note="market buy")
                        print(f"✅ BUY filled qty={qty} avg={avg_price}")
                    else:
                        print(f"⏳ waiting | mode=live | price={price} | usdt={usdt_free} (need {BUY_USDT})")
                else:
                    print(f"🧪 paper | price={price} | usdt={usdt_free}")
            else:
                # يوجد مركز مفتوح => تحقق TP/SL
                entry = float(pos["entry_price"])
                qty = float(pos["qty"])
                if entry <= 0 or qty <= 0:
                    # حماية
                    close_position()
                else:
                    pnl_pct = (price - entry) / entry * 100.0
                    if pnl_pct >= TP_PCT or pnl_pct <= -SL_PCT:
                        if ENABLE_TRADING:
                            order = _market_sell(client, qty)
                            avg_price = _filled_avg_price(order)
                            sold_qty = _executed_qty(order)
                            add_trade(SYMBOL, "SELL", sold_qty, avg_price, note=f"tp/sl hit pnl={pnl_pct:.3f}%")
                            close_position()
                            print(f"✅ SELL filled qty={sold_qty} avg={avg_price} pnl={pnl_pct:.3f}%")
                        else:
                            print(f"🧪 paper SELL signal pnl={pnl_pct:.3f}%")
                    else:
                        print(f"📌 holding | entry={entry} now={price} pnl={pnl_pct:.3f}% | usdt={usdt_free}")

        except Exception as e:
            set_status(MODE, 0, 0, last_error=str(e), notes="error")
            print("❌ ERROR:", e)

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
