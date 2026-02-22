import ccxt
import time
import os
import requests
import threading
from flask import Flask

# إعداد تطبيق ويب بسيط لضمان بقاء السيرفر في حالة Healthy
app = Flask(__name__)

# --- جلب مفاتيح Takrouri_Cloud_Bot من متغيرات البيئة ---
API_KEY = os.getenv('BINANCE_API_KEY')
SECRET_KEY = os.getenv('BINANCE_SECRET_KEY')

# إعداد الاتصال بباينانس مع حلول مشاكل التوقيع والـ IP الثابت
exchange = ccxt.binance({
    'apiKey': API_KEY,
    'secret': SECRET_KEY,
    'enableRateLimit': True,
    'options': {
        'adjustForTimeDifference': True,  # حل مشكلة Signature -1022 الناتجة عن فارق التوقيت
        'recvWindow': 60000              # زيادة نافذة الاستقبال لضمان قبول الطلب من الـ Static IP الجديد
    }
})

# بيانات تنبيهات تيلجرام الخاصة بك
TG_TOKEN = '8588741495:AAEYDfLoXnJVFbtMEdyjdNrZznwdSdJs0WQ'
TG_ID = '5429169001'

def send_telegram(message):
    """إرسال إشعارات فورية لـ محمد عند كل عملية شراء أو بيع"""
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        payload = {"chat_id": TG_ID, "text": message, "parse_mode": "HTML"}
        requests.post(url, data=payload)
    except Exception as e:
        print(f"⚠️ خطأ تيلجرام: {e}", flush=True)

@app.route('/')
def home():
    """المسار الرئيسي لضمان بقاء التطبيق نشطاً في DigitalOcean"""
    return "✅ رادار التكروري يعمل بنجاح باستخدام الـ Static IP الجديد."

def trading_engine():
    """المحرك الأساسي للبحث عن الفرص والتداول التلقائي"""
    print("🚀 انطلاق المحرك المطور.. جاري فحص الرصيد باستخدام المفاتيح الجديدة..", flush=True)
    
    while True:
        try:
            # التحقق من الرصيد (يجب أن يظهر رصيدك الـ 41.14 USDT هنا)
            balance = exchange.fetch_balance()
            usdt_balance = float(balance.get('USDT', {}).get('free', 0))
            print(f"💰 الرصيد الحالي المكتشف: {usdt_balance:.2f} USDT", flush=True)

            # استراتيجية التداول: الشراء بمبلغ 11 USDT عند وجود صعود قوي
            if usdt_balance >= 11.5:
                tickers = exchange.fetch_tickers()
                for symbol, ticker in tickers.items():
                    # البحث عن عملات صاعدة بأكثر من 5% (استراتيجية محمد)
                    if '/USDT' in symbol and ticker['percentage'] and ticker['percentage'] > 5.0:
                        print(f"🎯 فرصة مكتشفة: {symbol} صاعدة بنسبة {ticker['percentage']}%", flush=True)
                        
                        # تنفيذ أمر شراء حقيقي
                        exchange.create_market_buy_order(symbol, 11)
                        
                        msg = f"🔔 <b>تم الشراء بنجاح!</b>\nالعملة: {symbol}\nالمبلغ: 11 USDT\nالنسبة: {ticker['percentage']}%"
                        send_telegram(msg)
                        break
            
        except Exception as e:
            # طباعة الأخطاء في السجلات لمتابعتها (مثل خطأ -1022 السابق)
            print(f"⚠️ تنبيه المحرك: {str(e)[:100]}", flush=True)
        
        # انتظار دقيقة واحدة قبل الفحص التالي
        time.sleep(60)

# تشغيل التداول في الخلفية لضمان عدم توقف السيرفر
threading.Thread(target=trading_engine, daemon=True).start()

if __name__ == '__main__':
    # المنفذ 8080 المطلوب من قبل منصة DigitalOcean
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
