import ccxt
import time
import os
import requests
import threading
from flask import Flask

# إعداد تطبيق ويب بسيط للرد على اختبارات الجاهزية (Health Checks)
app = Flask(__name__)

# --- جلب مفاتيح Takrouri_Cloud_Bot من النظام ---
API_KEY = os.getenv('BINANCE_API_KEY')
SECRET_KEY = os.getenv('BINANCE_SECRET_KEY')

# إعداد الاتصال بباينانس باستخدام مكتبة ccxt
exchange = ccxt.binance({
    'apiKey': API_KEY,
    'secret': SECRET_KEY,
    'enableRateLimit': True,
    'options': {
        'adjustForTimeDifference': True,
        'recvWindow': 15000
    }
})

# بيانات تنبيهات تيلجرام الخاصة بك
TG_TOKEN = '8588741495:AAEYDfLoXnJVFbtMEdyjdNrZznwdSdJs0WQ'
TG_ID = '5429169001'

def send_telegram(message):
    """إرسال إشعارات فورية لهاتفك عند حدوث عملية تداول"""
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        payload = {"chat_id": TG_ID, "text": message, "parse_mode": "HTML"}
        requests.post(url, data=payload)
    except Exception as e:
        print(f"⚠️ خطأ في إرسال التيلجرام: {e}", flush=True)

@app.route('/')
def home():
    """هذا المسار يضمن بقاء حالة التطبيق Healthy في ديجيتال أوشن"""
    return "📡 رادار التكروري السحابي: نشط وجاري البحث عن فرص.."

def trading_loop():
    """المحرك الأساسي للروبوت: يبحث ويشتري تلقائياً"""
    print("🚀 انطلق المحرك السحابي.. جاري فحص الرصيد والفرص..", flush=True)
    
    while True:
        try:
            # الروبوت يراقب رصيدك الـ 41.14 USDT
            balance = exchange.fetch_balance()
            usdt_balance = float(balance.get('USDT', {}).get('free', 0))
            print(f"💰 الرصيد الحالي المكتشف: {usdt_balance:.2f} USDT", flush=True)

            # إذا توفر رصيد كافٍ لصفقة (تجاوز فلتر 11 USDT)
            if usdt_balance >= 11.5:
                # جلب أسعار العملات ومسح السوق
                tickers = exchange.fetch_tickers()
                for symbol, ticker in tickers.items():
                    # استراتيجية المقامرة: صيد العملات الصاعدة بأكثر من 5%
                    if '/USDT' in symbol and ticker['percentage'] and ticker['percentage'] > 5.0:
                        print(f"🎯 وجدت فرصة: {symbol} صاعدة بنسبة {ticker['percentage']}%", flush=True)
                        
                        # تنفيذ أمر شراء حقيقي بمبلغ 11 USDT
                        exchange.create_market_buy_order(symbol, 11)
                        
                        msg = f"✅ <b>تمت عملية شراء جديدة!</b>\nالعملة: {symbol}\nالمبلغ: 11 USDT\nالنسبة الحالية: {ticker['percentage']}%"
                        send_telegram(msg)
                        break  # شراء عملة واحدة في كل دورة
            
        except Exception as e:
            # طباعة الأخطاء في Runtime Logs للمتابعة
            print(f"⚠️ تنبيه من المحرك: {str(e)[:100]}", flush=True)
        
        # الانتظار لمدة دقيقة قبل الفحص التالي لتجنب الحظر
        time.sleep(60)

# تشغيل محرك التداول في خلفية التطبيق (Threading)
threading.Thread(target=trading_loop, daemon=True).start()

if __name__ == '__main__':
    # استخدام المنفذ 8080 المطلوب من DigitalOcean
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
