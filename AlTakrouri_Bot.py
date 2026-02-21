import ccxt, time, os, requests, threading
from flask import Flask

app = Flask(__name__)

# مفاتيح robot التي فعلناها سابقاً
exchange = ccxt.binance({
    'apiKey': 'NpU0M5UXBSptfwhaDCiV0fLVkcrjcU4Tvnu3delwEojasUY40P86f4woNJefqe6r',
    'secret': 'ATaA2II1KD6Y9wAUXaAudCbRULT9WnOqTiZ04PTj0sYTmdiebv4Ue9Wfi3lfxfn',
    'enableRateLimit': True,
    'options': {'adjustForTimeDifference': True, 'recvWindow': 15000}
})

# تيلجرام التكروري
TG_TOKEN = '8588741495:AAEYDfLoXnJVFbtMEdyjdNrZznwdSdJs0WQ'
TG_ID = '5429169001'

def send_tg(msg):
    try: requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data={"chat_id": TG_ID, "text": msg, "parse_mode": "HTML"})
    except: pass

@app.route('/')
def health_check():
    # رد فوري للسيرفر لضمان بقاء الحالة Healthy
    return "✅ رادار التكروري نشط!"

def trading_loop():
    print("🚀 المحرك السحابي يبحث عن صفقات الآن...", flush=True)
    while True:
        try:
            # مراقبة رصيدك الـ 41.14 USDT
            bal = exchange.fetch_balance()
            usdt = float(bal.get('USDT', {}).get('free', 0))
            print(f"💰 الرصيد الحالي: {usdt:.2f} USDT", flush=True)
            
            if usdt >= 11.5:
                tickers = exchange.fetch_tickers()
                for sym, t in tickers.items():
                    # مقامرة ذكية: صعود أكثر من 5%
                    if '/USDT' in sym and t['percentage'] and t['percentage'] > 5.0:
                        exchange.create_market_buy_order(sym, 11) # تجاوز NOTIONAL
                        send_tg(f"🎯 <b>تم شراء {sym}!</b>\nبمبلغ 11 USDT من السحاب.")
                        break
        except Exception as e:
            print(f"⚠️ تنبيه: {str(e)[:50]}", flush=True)
        time.sleep(60)

# تشغيل التداول في الخلفية لعدم تعطيل الـ Health Check
threading.Thread(target=trading_loop, daemon=True).start()

if __name__ == '__main__':
    # المنفذ 8080 الذي يطلبه السيرفر
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
