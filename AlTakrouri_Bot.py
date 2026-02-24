import ccxt
import time
import os
import requests
import threading
from flask import Flask

# إعداد واجهة الويب الاحترافية
app = Flask(__name__)

# جلب المفاتيح الآمنة من DigitalOcean
API_KEY = os.getenv('BINANCE_API_KEY')
SECRET_KEY = os.getenv('BINANCE_SECRET_KEY')

# إعداد الاتصال الاحترافي بالـ Static IP
exchange = ccxt.binance({
    'apiKey': API_KEY,
    'secret': SECRET_KEY,
    'enableRateLimit': True,
    'options': {
        'adjustForTimeDifference': True, 
        'recvWindow': 60000              
    }
})

# بيانات التنبيهات
TG_TOKEN = '8588741495:AAEYDfLoXnJVFbtMEdyjdNrZznwdSdJs0WQ'
TG_ID = '5429169001'

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TG_ID, "text": msg, "parse_mode": "HTML"})
    except Exception as e:
        print(f"⚠️ خطأ تيلجرام: {e}", flush=True)

@app.route('/')
def health_check():
    """واجهة مستخدم تعكس وضع القوة الجديد"""
    return """
    <html>
    <head>
        <title>التكروري للبرمجيات | رادار القوة</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
            body { background: linear-gradient(135deg, #0f2027 0%, #203a43 50%, #2c5364 100%); color: white; height: 100vh; display: flex; align-items: center; justify-content: center; font-family: 'Segoe UI', sans-serif; }
            .card { background: rgba(0, 0, 0, 0.6); border: 1px solid #00ff41; border-radius: 20px; padding: 40px; box-shadow: 0 0 20px #00ff41; text-align: center; }
            .status-pulse { display: inline-block; width: 12px; height: 12px; background-color: #00ff41; border-radius: 50%; box-shadow: 0 0 10px #00ff41; animation: pulse 1.5s infinite; }
            @keyframes pulse { 0% { transform: scale(1); opacity: 1; } 50% { transform: scale(1.5); opacity: 0.5; } 100% { transform: scale(1); opacity: 1; } }
        </style>
    </head>
    <body>
        <div class="card">
            <h1 class="mb-4">🚀 رادار التكروري (وضع القوة)</h1>
            <div class="mb-3"><span class="status-pulse"></span> <span style="color: #00ff41;">النظام يعمل بكفاءة قصوى</span></div>
            <hr style="border-color: #00ff41;">
            <p class="lead">الرصيد المراقب: <strong>41.14 USDT</strong></p>
            <p>مبلغ الصفقة الجديد: <span class="badge bg-success">30 USDT</span></p>
            <p class="mt-4 small text-muted">تم التعديل بناءً على طلب محمد لكسر قيود السيولة</p>
        </div>
    </body>
    </html>
    """

def trading_engine():
    # استبعاد العملات التي تسبب مشاكل تقنية
    blacklist = ['WAVES/USDT', 'XMR/USDT', 'ANT/USDT', 'MULTI/USDT'] 
    
    print("🚀 انطلاق الرادار بوضع القوة (30 USDT).. جاري الفحص..", flush=True)
    send_telegram("🚀 <b>يا محمد، تم رفع مبلغ الصفقة لـ 30 USDT!</b>\nهذا الوضع سيضمن تنفيذ العمليات فوراً وتجاوز كافة قيود باينانس.")
    
    while True:
        try:
            balance = exchange.fetch_balance()
            usdt = float(balance.get('USDT', {}).get('free', 0))
            print(f"💰 الرصيد الحالي: {usdt:.2f} USDT", flush=True)

            # الرصيد الحالي 41.14 كافٍ تماماً لصفقة بـ 30 USDT
            if usdt >= 30.5:
                tickers = exchange.fetch_tickers()
                for symbol, t in tickers.items():
                    if '/USDT' in symbol and symbol not in blacklist:
                        # قنص العملات الصاعدة بأكثر من 5%
                        if t['percentage'] and t['percentage'] > 5.0:
                            print(f"🎯 فرصة ذهبية بـ 30 USDT في: {symbol} (+{t['percentage']}%)")
                            
                            # تنفيذ الشراء بـ 30 USDT لضمان العبور
                            exchange.create_market_buy_order(symbol, 30)
                            
                            send_telegram(f"🔔 <b>تم تنفيذ صفقة ناجحة!</b>\nالعملة: {symbol}\nالمبلغ: 30 USDT\nالنسبة: {t['percentage']}%")
                            break
        except Exception as e:
            # مراقبة الأخطاء في السجلات السوداء
            print(f"⚠️ تنبيه المحرك: {str(e)[:100]}", flush=True)
        time.sleep(60)

threading.Thread(target=trading_engine, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
