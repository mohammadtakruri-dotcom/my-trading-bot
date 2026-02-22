import ccxt
import time
import os
import requests
import threading
from flask import Flask

# إعداد واجهة الويب لضمان بقاء التطبيق نشطاً في DigitalOcean
app = Flask(__name__)

# --- جلب مفاتيح Takrouri_Cloud_Bot من متغيرات النظام ---
# تأكد من وضع هذه المفاتيح في App Settings -> Environment Variables
API_KEY = os.getenv('BINANCE_API_KEY')
SECRET_KEY = os.getenv('BINANCE_SECRET_KEY')

# إعداد الاتصال الاحترافي بباينانس
exchange = ccxt.binance({
    'apiKey': API_KEY,
    'secret': SECRET_KEY,
    'enableRateLimit': True,
    'options': {
        # حل مشكلة الخطأ -1022 عن طريق مزامنة الوقت مع خوادم باينانس
        'adjustForTimeDifference': True, 
        # زيادة نافذة الاستلام لضمان قبول الطلب عبر الـ Static IP
        'recvWindow': 60000              
    }
})

# بيانات التنبيهات المخصصة لك يا محمد
TG_TOKEN = '8588741495:AAEYDfLoXnJVFbtMEdyjdNrZznwdSdJs0WQ'
TG_ID = '5429169001'

def send_telegram(msg):
    """إرسال تنبيه فوري لهاتفك عند اكتشاف فرص أو تنفيذ صفقات"""
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TG_ID, "text": msg, "parse_mode": "HTML"})
    except Exception as e:
        print(f"⚠️ خطأ تيلجرام: {e}", flush=True)

@app.route('/')
def health_check():
    """هذا المسار يخبر DigitalOcean أن السيرفر يعمل بشكل ممتاز"""
    return "✅ رادار التكروري السحابي يعمل بالـ Static IP والمفاتيح المحدثة."

def trading_engine():
    """المحرك الذكي للتداول التلقائي"""
    print("🚀 انطلاق المحرك المطور.. جاري فحص الرصيد والفرص الآن..", flush=True)
    
    while True:
        try:
            # جلب الرصيد الحقيقي (يجب أن يظهر هنا رصيدك 41.14 USDT)
            balance = exchange.fetch_balance()
            usdt = float(balance.get('USDT', {}).get('free', 0))
            print(f"💰 الرصيد المتاح: {usdt:.2f} USDT", flush=True)

            # استراتيجية محمد: شراء بـ 11 USDT عند الصعود القوي
            if usdt >= 11.5:
                tickers = exchange.fetch_tickers()
                for symbol, t in tickers.items():
                    # فلتر الصعود بنسبة أكبر من 5%
                    if '/USDT' in symbol and t['percentage'] and t['percentage'] > 5.0:
                        print(f"🎯 وجدت فرصة: {symbol} (+{t['percentage']}%)", flush=True)
                        
                        # تنفيذ الشراء الفعلي
                        exchange.create_market_buy_order(symbol, 11)
                        
                        msg = f"🔔 <b>تم الشراء بنجاح!</b>\nالعملة: {symbol}\nالمبلغ: 11 USDT\nالنسبة: {t['percentage']}%"
                        send_telegram(msg)
                        break
            
        except Exception as e:
            # طباعة الأخطاء لتشخيصها فوراً من السجلات
            print(f"⚠️ تنبيه المحرك: {str(e)[:120]}", flush=True)
        
        # الفحص كل دقيقة لضمان عدم تجاوز حدود باينانس
        time.sleep(60)

# تشغيل محرك التداول في خيط مستقل (Thread) لضمان استمرار عمل الـ API
threading.Thread(target=trading_engine, daemon=True).start()

if __name__ == '__main__':
    # استخدام المنفذ 8080 المطلوب للمنصة
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
