import ccxt
import time
import os
import requests
import threading
from flask import Flask

# إعداد واجهة الويب لضمان بقاء التطبيق نشطاً في DigitalOcean
app = Flask(__name__)
# --- جلب مفاتيح Takrouri_Cloud_Bot من النظام ---
API_KEY = os.getenv('BINANCE_API_KEY')
SECRET_KEY = os.getenv('BINANCE_SECRET_KEY')

# إعداد الاتصال الاحترافي بباينانس
exchange = ccxt.binance({
    'apiKey': API_KEY,
    'secret': SECRET_KEY,
    'enableRateLimit': True,
    'options': {
        'adjustForTimeDifference': True, 
        'recvWindow': 60000              
    }
})

# بيانات التنبيهات الخاصة بك يا محمد
TG_TOKEN = '8588741495:AAEYDfLoXnJVFbtMEdyjdNrZznwdSdJs0WQ'
TG_ID = '5429169001'

def send_telegram(msg):
    """إرسال تنبيه فوري لهاتفك عند كل تحرك للروبوت"""
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TG_ID, "text": msg, "parse_mode": "HTML"})
    except Exception as e:
        print(f"⚠️ خطأ تيلجرام: {e}", flush=True)

@app.route('/')
def health_check():
    """تأكيد عمل السيرفر تقنياً"""
@app.route('/')
def health_check():
    # تصميم احترافي باستخدام Bootstrap لشركة التكروري للبرمجيات
    return """
    <html>
    <head>
        <title>رادار التكروري السحابي</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
            body { background-color: #1a1a2e; color: white; text-align: center; padding-top: 50px; font-family: 'Arial', sans-serif; }
            .card { background-color: #16213e; border: 1px solid #0f3460; border-radius: 15px; margin: 20px auto; max-width: 500px; padding: 20px; box-shadow: 0px 10px 30px rgba(0,0,0,0.5); }
            .status-ok { color: #00ff41; font-weight: bold; }
        </style>
    </head>
    <body>
        <div class="card">
            <h2 class="mb-4">🚀 رادار التكروري السحابي</h2>
            <hr>
            <p>الحالة الآن: <span class="status-ok">متصل ويعمل</span></p>
            <p>وضع المخاطرة: <strong>3%</strong> | تم تجاوز <strong>WAVES</strong></p>
            <div class="mt-4">
                <small class="text-muted">تم التطوير بواسطة التكروري للبرمجيات © 2026</small>
            </div>
        </div>
    </body>
    </html>
    """

def trading_engine():
    """المحرك المطور للمخاطرة وتجاوز العملات المغلقة"""
    # قائمة العملات التي نريد تجنبها (القائمة السوداء)
    blacklist = ['WAVES/USDT'] 
    
    print("🚀 انطلاق رادار التكروري (وضع قنص الفرص 3%).. جاري الفحص..", flush=True)
    send_telegram("🚀 محمد، تم تفعيل وضع المخاطرة! سأقوم بتجاوز WAVES والبحث عن أي صعود فوق 3%.")
    
    while True:
        try:
            # التحقق من الرصيد (41.14 USDT)
            balance = exchange.fetch_balance()
            usdt = float(balance.get('USDT', {}).get('free', 0))
            print(f"💰 الرصيد الحالي: {usdt:.2f} USDT", flush=True)

            if usdt >= 11.5:
                tickers = exchange.fetch_tickers()
                for symbol, t in tickers.items():
                    # 1. فلتر العملات المستقرة والـ USDT
                    if '/USDT' not in symbol:
                        continue
                        
                    # 2. تجاوز العملات الموجودة في القائمة السوداء (مثل WAVES)
                    if symbol in blacklist:
                        continue

                    # 3. استراتيجية المخاطرة: صعود أكثر من 3.0%
                    if t['percentage'] and t['percentage'] > 3.0:
                        print(f"🎯 فرصة مكتشفة: {symbol} (+{t['percentage']}%)", flush=True)
                        
                        # تنفيذ الشراء المباشر بـ 11 USDT
                        exchange.create_market_buy_order(symbol, 11)
                        
                        msg = f"🔔 <b>تم الشراء بنجاح!</b>\nالعملة: {symbol}\nالمبلغ: 11 USDT\nالنسبة: {t['percentage']}%"
                        send_telegram(msg)
                        # التوقف بعد أول عملية شراء لانتظار الربح (أو إزالة break للاستمرار)
                        break
            
        except Exception as e:
            print(f"⚠️ تنبيه: {str(e)[:150]}", flush=True)
        
        # فحص كل 60 ثانية لضمان عدم فوات الفرص
        time.sleep(60)

# تشغيل المحرك في الخلفية
threading.Thread(target=trading_engine, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
