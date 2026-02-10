import ccxt
import time
import sys
import requests

exchange = ccxt.kucoin()

def run_trading_bot():
    print("--- الروبوت يرسل البيانات الآن إلى MySQL ---")
    sys.stdout.flush()
    
    API_ENDPOINT = "https://3rood.gt.tc/update_bot.php"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    while True:
        try:
            ticker = exchange.fetch_ticker('BTC/USDT')
            price = f"${ticker['last']:,.2f}"
            
            payload = {
                'price': price,
                'total': '$1,000.00', # تجريبي
                'action': 'مراقبة السوق'
            }

            try:
                # إرسال البيانات مع تمديد وقت الانتظار (Timeout)
                response = requests.post(API_ENDPOINT, data=payload, headers=headers, timeout=20)
                print(f"الحالة: {response.status_code} | الرد: {response.text}")
            except Exception as e:
                print(f"عطل مؤقت في الشبكة: {e}")

            sys.stdout.flush()
            time.sleep(30) # تحديث كل 30 ثانية لتخفيف الضغط

        except Exception as e:
            print(f"خطأ تقني: {e}")
            sys.stdout.flush()
            time.sleep(10)

if __name__ == "__main__":
    run_trading_bot()
