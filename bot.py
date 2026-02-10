import ccxt
import time
import sys
import requests

# استخدام منصة KuCoin لتجاوز القيود الجغرافية للسيرفرات السحابية
exchange = ccxt.kucoin()

def run_trading_bot():
    print("--- الروبوت يرسل البيانات الآن إلى MySQL في 3rood.gt.tc ---")
    sys.stdout.flush()
    
    # رابط ملف PHP الذي قمنا ببرمجته للاستقبال
    API_ENDPOINT = "https://3rood.gt.tc/update_bot.php"
    
    # إضافة Headers لتجاوز قيود الحماية في السيرفر
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    # محفظة وهمية للبداية
    balance_usd = 1000.0
    btc_held = 0.0

    while True:
        try:
            ticker = exchange.fetch_ticker('BTC/USDT')
            current_price = ticker['last']
            price_formatted = f"${current_price:,.2f}"
            
            # منطق إرسال الإجراء الحالي
            action = "شراء وهمي" if btc_held == 0 else "مراقبة السوق"
            
            payload = {
                'price': price_formatted,
                'total': f"${(balance_usd + (btc_held * current_price)):,.2f}",
                'action': action
            }

            try:
                # إرسال البيانات مع تمديد وقت الانتظار (Timeout) لتجنب انقطاع الاتصال
                response = requests.post(API_ENDPOINT, data=payload, headers=headers, timeout=20)
                print(f"[{time.strftime('%H:%M:%S')}] الحالة: {response.status_code} | السعر: {current_price}")
            except Exception as e:
                print(f"تنبيه: عطل مؤقت في الاتصال مع السيرفر: {e}")

            sys.stdout.flush()
            # فحص السعر كل 30 ثانية لتجنب الضغط الذي يسبب قطع الاتصال
            time.sleep(30)

        except Exception as e:
            print(f"خطأ تقني في البوت: {e}")
            sys.stdout.flush()
            time.sleep(10)

if __name__ == "__main__":
    run_trading_bot()
