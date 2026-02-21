import ccxt, time, os, requests, threading
from flask import Flask

app = Flask(__name__)

# --- الإعدادات بمفاتيح robot المفعّلة ---
API_KEY = 'NpU0M5UXBSptfwhaDCiV0fLVkcrjcU4Tvnu3delwEojasUY40P86f4woNJefqe6r'
SECRET_KEY = 'ATaA2II1KD6Y9wAUXaAudCbRULT9WnOqTiZ04PTj0sYTmdiebv4Ue9Wfi3lfxfn'

exchange = ccxt.binance({
    'apiKey': API_KEY,
    'secret': SECRET_KEY,
    'enableRateLimit': True,
    'options': {
        'adjustForTimeDifference': True, # لحل مشكلة توقيت السيرفر
        'recvWindow': 15000
    }
})

# بيانات التنبيه (تيلجرام)
TG_TOKEN = '8588741495:AAEYDfLoXnJVFbtMEdyjdNrZznwdSdJs0WQ'
TG_ID = '5429169001'

def send_tg(msg):
    try:
        requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", 
                     data={"chat_id": TG_ID, "text": msg, "parse_mode": "HTML"})
    except:
        pass

@app.route('/')
def home():
    # هذه الواجهة للرد على DigitalOcean Health Check
    return "📡 رادار التكروري السحابي يعمل بنجاح وحالته Healthy!"

def trading_logic():
    print("🚀 انطلق المحرك السحابي.. جاري فحص الرصيد والفرص..", flush=True)
    while True:
        try:
            # الروبوت يراقب رصيدك الـ 41.14 USDT
            bal = exchange.fetch_balance()
            usdt = float(bal.get('USDT', {}).get('free', 0))
            print(f"💰 الرصيد الحالي المكتشف: {usdt:.2f} USDT", flush=True)
            
            if usdt >= 11.5:
                tickers = exchange.fetch_tickers()
                for sym, t in tickers.items():
                    if '/USDT' in sym and t['percentage'] and t['percentage'] > 5.0:
                        # تنفيذ الشراء بـ 11 USDT لتجاوز فلتر NOTIONAL
                        exchange.create_market_buy_order(sym, 11)
                        send_tg(f"✅ <b>تم الشراء بنجاح!</b>\nالعملة: {sym}\nالمبلغ: 11 USDT")
                        print(f"🎯 تم شراء {sym}", flush=True)
                        break 
        except Exception as e:
            print(f"⚠️ خطأ في المحرك: {str(e)[:50]}", flush=True)
        
        time.sleep(60) # فحص كل دقيقة

# تشغيل محرك التداول في الخلفية لضمان استجابة Flask
threading.Thread(target=trading_logic, daemon=True).start()

if __name__ == '__main__':
    # استخدام المنفذ 8080 المطلوب من DigitalOcean
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
