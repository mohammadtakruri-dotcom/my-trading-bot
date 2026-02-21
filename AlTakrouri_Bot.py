import ccxt, time, os, requests, threading
from flask import Flask

app = Flask(__name__)

# --- مفاتيح Takrouri_Cloud_Bot الجديدة ---
exchange = ccxt.binance({
    'apiKey': '9rld4dEHZpfKTRcO55BDwvKK4gNuJOpLIXSRMEz1hvKRCGDUcMf2jfcDNBVPAjUZ',
    'secret': '8cTXmdPYN3jqk69NKvb9PXLHqoJfGWVgleVLRenXnfwhfraUNlkPA4MsFdlgkgT6',
    'enableRateLimit': True,
    'options': {'adjustForTimeDifference': True, 'recvWindow': 15000}
})

# بيانات تيلجرام التكروري
TG_TOKEN = '8588741495:AAEYDfLoXnJVFbtMEdyjdNrZznwdSdJs0WQ'
TG_ID = '5429169001'

def send_tg(msg):
    try: requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data={"chat_id": TG_ID, "text": msg, "parse_mode": "HTML"})
    except: pass

@app.route('/')
def health(): return "✅ رادار التكروري السحابي نشط ويعمل بالمفاتيح الجديدة!"

def trading_engine():
    print("🚀 انطلاق المحرك السحابي الجديد...", flush=True)
    while True:
        try:
            # الروبوت يراقب رصيدك الـ 41.14 USDT
            bal = exchange.fetch_balance()
            usdt = float(bal.get('USDT', {}).get('free', 0))
            print(f"💰 الرصيد الحالي: {usdt:.2f} USDT", flush=True)
            
            if usdt >= 11.5:
                tickers = exchange.fetch_tickers()
                for sym, t in tickers.items():
                    # استراتيجية المقامرة: صعود مفاجئ > 5%
                    if '/USDT' in sym and t['percentage'] and t['percentage'] > 5.0:
                        exchange.create_market_buy_order(sym, 11)
                        send_tg(f"🎯 <b>تمت عملية شراء!</b>\nالعملة: {sym}\nالمبلغ: 11 USDT")
                        break
        except Exception as e:
            print(f"⚠️ تنبيه: {str(e)[:50]}", flush=True)
        time.sleep(60)

# تشغيل التداول في الخلفية
threading.Thread(target=trading_engine, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
