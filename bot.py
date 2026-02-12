import sys
import time
import requests
import ccxt # تأكد من تثبيت المكتبة عبر: pip install ccxt

# إعداد منصة KuCoin
# ملاحظة: بعض الميزات قد تتطلب API Key إذا كنت ستنفذ عمليات بيع وشراء حقيقية
exchange = ccxt.kucoin()

def run_trading_bot():
    print("--- الروبوت يبدأ العمل الآن ---")
    
    # رابط ملف PHP الذي يستقبل البيانات
    API_ENDPOINT = "https://3rood.gt.tc/update_bot.php"

    # إعدادات الجلسة لمحاكاة متصفح حقيقي وتجاوز الحماية
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'ar,en-US;q=0.7,en;q=0.3',
    })

    # بيانات المحفظة الافتراضية
    balance_usd = 1000.0
    btc_held = 0.0

    while True:
        try:
            # 1. جلب بيانات السعر من KuCoin
            ticker = exchange.fetch_ticker('BTC/USDT')
            current_price = ticker['last']
            
            # 2. تجهيز البيانات للإرسال
            action = "شراء وهمي" if btc_held == 0 else "مراقبة السوق"
            total_value = balance_usd + (btc_held * current_price)
            
            payload = {
                'price': f"${current_price:,.2f}",
                'total': f"${total_value:,.2f}",
                'action': action
            }

            # 3. محاولة إرسال البيانات للسيرفر
            try:
                # استخدام Session لإرسال الطلب (POST)
                response = session.post(API_ENDPOINT, data=payload, timeout=20)
                
                # فحص إذا كان السيرفر يحظر البوت (تحدي JS)
                if "slowAES" in response.text or response.status_code == 503:
                    print(f"[{time.strftime('%H:%M:%S')}] تنبيه: السيرفر يطلب تحدي JS أو الحماية فعالة.")
                else:
                    print(f"[{time.strftime('%H:%M:%S')}] تم الإرسال بنجاح | السعر: {current_price} | الحالة: {response.status_code}")
                
            except requests.exceptions.RequestException as e:
                print(f"عطل في الاتصال مع السيرفر: {e}")

            # تفريغ الذاكرة المؤقتة للطباعة
            sys.stdout.flush()
            
            # الانتظار لمدة 30 ثانية قبل التحديث القادم
            time.sleep(30)

        except Exception as e:
            print(f"خطأ تقني في البوت: {e}")
            time.sleep(10)

# تشغيل البوت
if __name__ == "__main__":
    run_trading_bot()
