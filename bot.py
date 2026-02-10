import ccxt
import time
import sys
import requests

exchange = ccxt.kucoin()

def run_trading_bot():
    print("--- محاولة تجاوز جدار حماية الاستضافة ---")
    sys.stdout.flush()
    
    API_ENDPOINT = "https://3rood.gt.tc/update_bot.php"
    
    # محاكاة متكاملة لمتصفح حقيقي
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'ar,en-US;q=0.7,en;q=0.3',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    })

    while True:
        try:
            ticker = exchange.fetch_ticker('BTC/USDT')
            price = f"${ticker['last']:,.2f}"
            
            payload = {
                'price': price,
                'total': '$1,000.00',
                'action': 'مراقبة'
            }

            try:
                # محاولة الإرسال عبر Session
                response = session.post(API_ENDPOINT, data=payload, timeout=20)
                # إذا وجدنا كود JS في الرد، فهذا يعني أن الحماية لا تزال فعالة
                if "slowAES" in response.text:
                    print("تنبيه: السيرفر لا يزال يطلب تحدي المتصفح (JS Challenge)")
                else:
                    print(f"الرد: {response.status_code} | {response.text}")
            except Exception as e:
                print(f"عطل في الاتصال: {e}")

            sys.stdout.flush()
            time.sleep(30)

        except Exception as e:
            print(f"خطأ تقني: {e}")
            sys.stdout.flush()
            time.sleep(10)

if __name__ == "__main__":
    run_trading_bot()
