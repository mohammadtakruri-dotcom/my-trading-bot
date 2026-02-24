import ccxt
import time
import os
import requests
import threading
from flask import Flask

# التصحيح البرمجي لضمان استقرار السيرفر في DigitalOcean
app = Flask(__name__)

# --- جلب مفاتيح التداول من بيئة النظام الآمنة ---
API_KEY = os.getenv('BINANCE_API_KEY')
SECRET_KEY = os.getenv('BINANCE_SECRET_KEY')

# إعداد الاتصال بباينانس مع حلول مشاكل التوقيع والـ Static IP
exchange = ccxt.binance({
    'apiKey': API_KEY,
    'secret': SECRET_KEY,
    'enableRateLimit': True,
    'options': {
        'adjustForTimeDifference': True, 
        'recvWindow': 60000              
    }
})

# بيانات التنبيهات (تأكد من الضغط على Start في بوت التيلجرام)
TG_TOKEN = '8588741495:AAEYDfLoXnJVFbtMEdyjdNrZznwdSdJs0WQ'
TG_ID = '5429169001'

def send_telegram(msg):
    """إرسال إشعارات فورية لـ محمد عند كل تحرك للروبوت"""
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TG_ID, "text": msg, "parse_mode": "HTML"})
    except Exception as e:
        print(f"⚠️ خطأ تيلجرام: {e}", flush=True)

@app.route('/')
def health_check():
    """واجهة مستخدم احترافية لشركة التكروري للبرمجيات بدلاً من الصفحة البيضاء"""
    return """
    <html>
    <head>
        <title>التكروري للبرمجيات | رادار التداول</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
            body { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); color: white; height: 100vh; display: flex; align-items: center; justify-content: center; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
            .card { background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 20px; backdrop-filter: blur(10px); padding: 40px; box-shadow: 0 15px 35px rgba(0,0,0,0.5); text-align: center; max-width: 600px; }
            .status-pulse { display: inline-block; width: 12px; height: 12px; background-color: #00ff41; border-radius: 50%; margin-right: 10px; box-shadow: 0 0 10px #00ff41; animation: pulse 1.5s infinite; }
            @keyframes pulse { 0% { transform: scale(1); opacity: 1; } 50% { transform: scale(1.5); opacity: 0.5; } 100% { transform: scale(1); opacity: 1; } }
            .btn-custom { background: #0f3460; color: white; border: none; border-radius: 10px; padding: 10px 20px; transition: 0.3s; text-decoration: none; }
            .btn-custom:hover { background: #e94560; color: white; }
        </style>
    </head>
    <body>
        <div class="card">
            <h1 class="mb-4">🚀 رادار التكروري السحابي</h1>
            <div class="mb-3">
                <span class="status-pulse"></span> 
                <span style="color: #00ff41;">النظام يعمل بكفاءة عالية</span>
            </div>
            <hr style="border-color: rgba(255,255,255,0.1);">
            <p class="lead">الرصيد المراقب: <strong>41.14 USDT</strong></p>
            <p>وضع الاستراتيجية: <span class="badge bg-danger">مخاطرة 3%</span></p>
            <p>فلتر العملات: <span class="badge bg-warning text-dark">تم تجاوز WAVES</span></p>
            <div class="mt-4">
                <a href="https://t.me/BotFather" class="btn-custom">متابعة عبر تيلجرام</a>
            </div>
            <p class="mt-5 small text-muted">جميع الحقوق محفوظة © التكروري للبرمجيات 2026</p>
        </div>
    </body>
    </html>
    """

def trading_engine():
    """المحرك الأساسي للتداول وتجاوز العملات المغلقة"""
    blacklist = ['WAVES/USDT'] 
    print("🚀 انطلاق المحرك المطور.. جاري الفحص..", flush=True)
    
    # إشعار البداية (تأكد من الضغط على Start في البوت)
    send_telegram("🚀 <b>يا محمد، المحرك متصل الآن!</b>\nتم تفعيل واجهة المستخدم الجديدة ووضع المخاطرة 3%.")
    
    while True:
        try:
            # التحقق من الرصيد
            balance = exchange.fetch_balance()
            usdt = float(balance.get('USDT', {}).get('free', 0))
            print(f"💰 الرصيد الحالي المكتشف: {usdt:.2f} USDT", flush=True)

            if usdt >= 11.5:
                tickers = exchange.fetch_tickers()
                for symbol, t in tickers.items():
                    # فلتر العملات وتجاوز WAVES
                    if '/USDT' in symbol and symbol not in blacklist:
                        # شرط المخاطرة الجديد 3%
                        if t['percentage'] and t['percentage'] > 3.0:
                            print(f"🎯 فرصة مكتشفة: {symbol} (+{t['percentage']}%)", flush=True)
                            
                            # تنفيذ الشراء بـ 11 USDT
                            exchange.create_market_buy_order(symbol, 11)
                            
                            send_telegram(f"🔔 <b>تم الشراء بنجاح!</b>\nالعملة: {symbol}\nالنسبة: {t['percentage']}%\nالمبلغ: 11 USDT")
                            break
            
        except Exception as e:
            print(f"⚠️ تنبيه المحرك: {str(e)[:100]}", flush=True)
        
        # فحص كل دقيقة
        time.sleep(60)

# تشغيل محرك التداول في الخلفية
threading.Thread(target=trading_engine, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
