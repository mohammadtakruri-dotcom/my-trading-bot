import ccxt
import time
import sys
import requests # مكتبة لإرسال البيانات لواجهتك

# استخدام KuCoin لتجنب الحظر الجغرافي
exchange = ccxt.kucoin()

def run_bot():
    print("--- البوت يعمل الآن ويقوم بتغذية لوحة التحكم ---")
    sys.stdout.flush()
    
    # إعدادات المحفظة الوهمية
    balance = 1000.0
    btc_held = 0.0
    
    # الرابط الخاص بملف الاستقبال على موقعك (استبدله بالرابط الحقيقي)
    WEB_API_URL = "https://your-domain.com/update_dashboard.php"

    while True:
        try:
            ticker = exchange.fetch_ticker('BTC/USDT')
            price = ticker['last']
            
            # حساب القيمة الإجمالية
            total_value = balance + (btc_held * price)
            
            # إرسال البيانات للواجهة
            payload = {
                'price': f"${price:,.2f}",
                'total': f"${total_value:,.2f}",
                'action': "شراء" if btc_held > 0 else "مراقبة"
            }
            
            try:
                requests.post(WEB_API_URL, data=payload, timeout=5)
            except:
                pass # تجاهل إذا كان الموقع متوقفاً مؤقتاً

            print(f"تم إرسال السعر: {price}")
            sys.stdout.flush()
            time.sleep(15)

        except Exception as e:
            print(f"خطأ: {e}")
            sys.stdout.flush()
            time.sleep(10)

if __name__ == "__main__":
    run_bot()
