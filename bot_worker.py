import os
import time
from decimal import Decimal, ROUND_DOWN
from datetime import datetime

from binance.client import Client
from binance.exceptions import BinanceAPIException

from db import init_db, set_status

# ==========================
# ENV VARS
# ==========================
SYMBOL = os.environ.get("SYMBOL", "BTCUSDT").upper()

MODE = os.environ.get("MODE", "paper").lower()  # paper / live
LIVE_TRADING = os.environ.get("LIVE_TRADING", "YES").upper()  # YES to allow real orders

BUY_USDT = float(os.environ.get("BUY_USDT", "5.0"))          # كم USDT تشتري به
TP_PCT = float(os.environ.get("TP_PCT", "0.7"))              # Take profit %
SL_PCT = float(os.environ.get("SL_PCT", "0.7"))              # Stop loss %

SLEEP_SECONDS = int(os.environ.get("SLEEP_SECONDS", "20"))

BINANCE_API_KEY = os.environ.get("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.environ.get("BINANCE_API_SECRET", "")

# Testnet (اختياري)
USE_TESTNET = os.environ.get("USE_TESTNET", "NO").upper()  # YES/NO


def now_iso():
    return datetime.utcnow().isoformat()


def log(msg):
    print(msg, flush=True)


def require_keys():
    if MODE == "live" and LIVE_TRADING == "YES":
        if not BINANCE_API_KEY or not BINANCE_API_SECRET:
            raise RuntimeError("Missing BINANCE_API_KEY / BINANCE_API_SECRET")


def make_client():
    client = Client(BINANCE_API_KEY, BINANCE_API_SECRET)
    if USE_TESTNET == "YES":
        # testnet endpoint
        client.API_URL = "https://testnet.binance.vision/api"
    return client


def get_price(client, symbol):
    p = client.get_symbol_ticker(symbol=symbol)["price"]
    return float(p)


def parse_asset(symbol):
    # BTCUSDT -> BTC
    # ملاحظة: هذا تبسيط، يعمل لمعظم أزواج USDT
    if symbol.endswith("USDT"):
        return symbol[:-4]
    return symbol[:-3]


def get_free_balance(client, asset):
    bal = client.get_asset_balance(asset=asset)
    if not bal:
        return 0.0
    return float(bal.get("free", "0"))


def get_lot_step(client, symbol) -> Decimal:
    info = client.get_symbol_info(symbol)
    lot = next(f for f in info["filters"] if f["filterType"] == "LOT_SIZE")
    return Decimal(lot["stepSize"])


def floor_to_step(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step


def to_plain_str(d: Decimal) -> str:
    # يمنع 1E-7
    s = format(d.normalize(), "f")
    # إذا طلع "" بسبب normalize على 0
    return s if s else "0"


def market_buy_usdt(client, symbol, usdt_amount: float):
    """
    أفضل طريقة لتجنب مشاكل quantity:
    BUY MARKET باستخدام quoteOrderQty (USDT)
    """
    if MODE != "live" or LIVE_TRADING != "YES":
        log(f"🟡 PAPER BUY (no real order) usdt={usdt_amount}")
        return {"paper": True, "side": "BUY", "quoteOrderQty": usdt_amount}

    return client.create_order(
        symbol=symbol,
        side="BUY",
        type="MARKET",
        quoteOrderQty=str(usdt_amount)
    )


def market_sell_all(client, symbol):
    """
    SELL MARKET لكمية الرصيد المتاحة من الأصل (BTC مثلا)
    مع قصّها حسب stepSize.
    """
    asset = parse_asset(symbol)
    free_qty = get_free_balance(client, asset)
    if free_qty <= 0:
        return None

    if MODE != "live" or LIVE_TRADING != "YES":
        log(f"🟡 PAPER SELL (no real order) qty={free_qty}")
        return {"paper": True, "side": "SELL", "quantity": free_qty}

    step = get_lot_step(client, symbol)
    qty = floor_to_step(Decimal(str(free_qty)), step)
    qty_str = to_plain_str(qty)

    # إذا أصبحت 0 بعد القصّ
    if Decimal(qty_str) <= 0:
        return None

    return client.create_order(
        symbol=symbol,
        side="SELL",
        type="MARKET",
        quantity=qty_str
    )


def main():
    init_db()

    # الوضع الافتراضي آمن
    set_status(mode=MODE, symbol=SYMBOL, last_action="worker_start", last_error=None, notes="")

    require_keys()
    client = make_client()

    asset = parse_asset(SYMBOL)

    in_position = 0
    entry_price = None
    tp_price = None
    sl_price = None

    log("🚀 BOT WORKER STARTED")

    while True:
        try:
            price = get_price(client, SYMBOL)

            usdt_free = get_free_balance(client, "USDT")
            asset_free = get_free_balance(client, asset)

            # تحديث حالة
            set_status(
                last_price=price,
                usdt_free=usdt_free,
                asset_free=asset_free,
                in_position=in_position,
                entry_price=entry_price,
                tp_price=tp_price,
                sl_price=sl_price,
                last_error=None,
                notes=f"alive | mode={MODE} | price={price} | usdt={usdt_free}"
            )

            log(f"⏳ alive | mode={MODE} | price={price} | usdt={usdt_free}")

            # ==========================
            # STRATEGY (بسيط جدًا):
            # - إذا ما عندنا صفقة -> شراء مرة واحدة بمبلغ BUY_USDT
            # - إذا عندنا صفقة -> بيع عند TP أو SL
            # ==========================

            if in_position == 0:
                # شراء مرة واحدة فقط كاختبار
                if usdt_free >= BUY_USDT or MODE != "live":
                    order = market_buy_usdt(client, SYMBOL, BUY_USDT)
                    entry_price = price
                    tp_price = entry_price * (1 + TP_PCT / 100.0)
                    sl_price = entry_price * (1 - SL_PCT / 100.0)
                    in_position = 1
                    set_status(last_action=f"BUY placed (paper={order.get('paper', False)})")
                    log(f"✅ BUY | entry={entry_price} tp={tp_price} sl={sl_price} buy_usdt={BUY_USDT}")
                else:
                    set_status(last_action="no_usdt_to_buy")
            else:
                # مراقبة TP/SL
                if tp_price and price >= tp_price:
                    sell = market_sell_all(client, SYMBOL)
                    in_position = 0
                    entry_price = None
                    tp_price = None
                    sl_price = None
                    set_status(last_action=f"SELL TP (paper={bool(sell and sell.get('paper', False))})")
                    log("✅ SOLD at TP")
                elif sl_price and price <= sl_price:
                    sell = market_sell_all(client, SYMBOL)
                    in_position = 0
                    entry_price = None
                    tp_price = None
                    sl_price = None
                    set_status(last_action=f"SELL SL (paper={bool(sell and sell.get('paper', False))})")
                    log("🛑 SOLD at SL")
                else:
                    set_status(last_action="holding")

        except BinanceAPIException as e:
            # خطأ من باينانس
            set_status(last_error=f"BinanceAPIException: {e.message}", last_action="error")
            log(f"❌ Binance API Error: {e}")
        except Exception as e:
            set_status(last_error=f"{type(e).__name__}: {str(e)}", last_action="error")
            log(f"❌ ERROR: {type(e).__name__}: {e}")

        time.sleep(SLEEP_SECONDS)


if __name__ == "__main__":
    main()
