import ccxt
import time
import os
import requests
import threading
from flask import Flask

# إعداد واجهة الويب لضمان بقاء التطبيق نشطاً في DigitalOcean
app = Flask(Takrouri_Cloud_Bot)

# --- جلب مفاتيح Takrouri_Cloud_Bot من متغيرات النظام الآمنة ---
# تأكد من وضع المفاتيح الجديدة (API Key & Secret Key) في App Settings -> Environment Variables
API_KEY = os.getenv('BINANCE_API_KEY')
SECRET_KEY = os.getenv('BINANCE_SECRET_KEY')

# إعداد الاتصال الاحترافي بباينانس لحل مشكلة الخطأ -1022
exchange = ccxt.binance({
    'apiKey': API_KEY,
    'secret': SECRET_KEY,
    'enableRateLimit': True,
    'options': {
        # مزامنة وقت السيرفر مع باينانس لمنع فشل التوقيع
        'adjustForTimeDifference': True, 
        # زيادة نافذة الاستقبال لضمان قبول الطلب عبر الـ Dedicated IPs
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
    """هذه الصفحة تؤكد لك أن السيرفر يعمل تقنياً"""
    return "✅ رادار التكروري يعمل بنجاح بالـ Static IP والمفاتيح الجديدة."

def trading_engine():
    """المحرك الأساسي للتداول التلقائي"""
    print("🚀 انطلاق المحرك المطور.. جاري فحص الرصيد والفرص الآن..", flush=True)
    
    while True:
        try:
            # التحقق من الرصيد الحقيقي (المتوقع 41.14 USDT)
            balance = exchange.fetch_balance()
            usdt = float(balance.get('USDT', {}).get('free', 0))
            print(f"💰 الرصيد الحالي المكتشف: {usdt:.2f} USDT", flush=True)

            # استراتيجية محمد: الشراء بـ 11 USDT عند الصعود القوي
            if usdt >= 11.5:
                tickers = exchange.fetch_tickers()
                for symbol, t in tickers.items():
                    # فحص العملات الصاعدة بأكثر من 5%
                    if '/USDT' in symbol and t['percentage'] and t['percentage'] > 5.0:
                        print(f"🎯 فرصة مكتشفة: {symbol} صاعدة بنسبة {t['percentage']}%", flush=True)
                        
                        # تنفيذ الشراء المباشر
                        exchange.create_market_buy_order(symbol, 11)
                        
                        msg = f"🔔 <b>تم الشراء بنجاح!</b>\nالعملة: {symbol}\nالمبلغ: 11 USDT\nالنسبة: {t['percentage']}%"
                        send_telegram(msg)
                        break
            
        except Exception as e:
            # طباعة الأخطاء في السجلات (لمراقبة حالة التوقيع -1022)
            print(f"⚠️ تنبيه المحرك: {str(e)[:150]}", flush=True)
        
        # الفحص كل دقيقة
        time.sleep(60)

# تشغيل التداول في الخلفية لضمان استجابة واجهة الويب
threading.Thread(target=trading_engine, daemon=True).start()

if __name__ == '__main__':
    # المنفذ 8080 المطلوب من قبل DigitalOcean
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
