import os
import time
import traceback
from datetime import datetime, timezone

import requests
from binance.client import Client

from db import init_db, set_status

def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

def get_env(name, default=None):
    v = os.environ.get(name)
    return v if v is not None and v != "" else default

def tg_send(text: str):
    token = get_env("TG_TOKEN")
    chat_id = get_env("TG_ID")
    if not token or not chat_id:
        return
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=15)
    except Exception:
        pass

def get_price_btcusdt():
    # بدون Binance lib حتى لو API keys ناقصة
    r = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT", timeout=15)
    r.raise_for_status()
    return float(r.json()["price"])

def get_usdt_free_live(client: Client):
    # يحتاج API Key/Secret وصلاحية Read
    bal = client.get_asset_balance(asset="USDT")
    if not bal:
        return 0.0
    return float(bal.get("free", 0) or 0)

def maybe_place_buy_order(client: Client, usdt_amount: float):
    """
    ⚠️ تنفيذ فعلي فقط إذا ENABLE_TRADING=1
    """
    enable = get_env("ENABLE_TRADING", "0")
    if enable != "1":
        return "ENABLE_TRADING=0 (no real order placed)"

    # مثال شراء Market بكمية USDT -> تحتاج حساب quantity بالـ BTC
    price = get_price_btcusdt()
    qty = usdt_amount / price
    # تقريبي جداً — في الواقع لازم تطابق LOT_SIZE و MIN_NOTIONAL
    qty = round(qty, 6)

    order = client.order_market_buy(
        symbol="BTCUSDT",
        quantity=qty
    )
    return f"ORDER PLACED: {order.get('orderId')} qty={qty}"

def main():
    print("🚀 BOT WORKER STARTED", flush=True)

    init_db()

    mode = (get_env("MODE", "paper") or "paper").lower()
    buy_usdt = float(get_env("BUY_USDT", "15") or 15)

    api_key = get_env("BINANCE_API_KEY")
    api_secret = get_env("BINANCE_SECRET_KEY")

    client = None
    if mode == "live":
        if not api_key or not api_secret:
            # live بدون مفاتيح = يشتغل بس قراءة سعر + تنبيه
            print("⚠️ LIVE mode but missing BINANCE keys. Running in read-only (price only).", flush=True)
        else:
            client = Client(api_key, api_secret)

    tg_send(f"✅ Bot started. MODE={mode}")

    while True:
        try:
            price = get_price_btcusdt()

            usdt_free = 0.0
            notes = ""

            if mode == "paper":
                # paper: ما في اتصال حساب حقيقي
                usdt_free = float(get_env("PAPER_USDT", "1000") or 1000)
                notes = f"PAPER mode. Simulated USDT={usdt_free}. BUY_USDT={buy_usdt}"

            elif mode == "live":
                if client is None:
                    usdt_free = 0.0
                    notes = "LIVE mode (no keys) — price only"
                else:
                    usdt_free = get_usdt_free_live(client)
                    notes = f"LIVE mode. USDT_free={usdt_free}. BUY_USDT={buy_usdt}. ENABLE_TRADING={get_env('ENABLE_TRADING','0')}"

                    # مثال قرار بسيط جداً: لا يشتري تلقائيًا إلا إذا ENABLE_TRADING=1
                    # هنا فقط للتجربة: إذا عندك رصيد كافي > BUY_USDT
                    if usdt_free >= buy_usdt:
                        result = maybe_place_buy_order(client, buy_usdt)
                        if "ORDER PLACED" in result:
                            tg_send(f"🟢 {result}")
                        else:
                            # فقط ملاحظة (لأن ENABLE_TRADING غالبًا 0)
                            pass

            set_status(
                mode=mode,
                is_running=True,
                updated_at=now_iso(),
                usdt_free=usdt_free,
                last_price=price,
                last_error="",
                notes=notes
            )

            print(f"⏳ alive | mode={mode} | price={price} | usdt={usdt_free}", flush=True)
            time.sleep(20)

        except Exception as e:
            err = traceback.format_exc()
            set_status(
                mode=mode,
                is_running=True,   # البوت شغال لكن حدث خطأ
                updated_at=now_iso(),
                last_error=err,
                notes="Error happened. Will retry..."
            )
            print("❌ ERROR:", err, flush=True)
            tg_send(f"❌ Bot error:\n{str(e)[:400]}")
            time.sleep(10)

if __name__ == "__main__":
    main()
