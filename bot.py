import ccxt
import time
import sys

# استخدام منصة KuCoin لتجاوز قيود الموقع الجغرافي للسيرفرات
exchange = ccxt.kucoin()

def start_trading_bot():
    print("--- تم إطلاق الروبوت بنجاح: وضع التداول التجريبي ---")
    sys.stdout.flush() # أمر إجباري لظهور النص فوراً في Render
    
    # محفظة افتراضية للبدء
    balance_usd = 1000.0
    btc_held = 0.0
    
    print(f"رأس المال الوهمي الأولي: {balance_usd} USDT")
    sys.stdout.flush()

    while True:
        try:
            # جلب السعر اللحظي للبيتكوين من KuCoin
            ticker = exchange.fetch_ticker('BTC/USDT')
            current_price = ticker['last']
            time_str = time.strftime('%H:%M:%S')
            
            # طباعة السعر في شاشة الـ Logs
            print(f"[{time_str}] سعر البيتكوين الحالي: {current_price} USDT")
            sys.stdout.flush()
            
            # استراتيجية تجريبية بسيطة:
            # شراء وهمي إذا كان السعر أقل من 90,000 (مثال)
            if btc_held == 0 and current_price < 90000:
                btc_held = balance_usd / current_price
                buy_price = current_price
                balance_usd = 0
                print(f"🚀 نفذنا عملية شراء وهمية بسعر: {current_price}")
                sys.stdout.flush()

            # بيع وهمي إذا ارتفع السعر بنسبة 1% عن سعر الشراء
            elif btc_held > 0 and current_price > (buy_price * 1.01):
                balance_usd = btc_held * current_price
                profit = balance_usd - 1000
                print(f"💰 تم البيع بربح! الرصيد الحالي: {balance_usd} | صافي الربح: {profit}")
                btc_held = 0
                sys.stdout.flush()

            # تحديث السعر كل 10 ثوانٍ
            time.sleep(10)
            
        except Exception as e:
            print(f"تنبيه - خطأ في الاتصال: {e}")
            sys.stdout.flush()
            time.sleep(15)

if __name__ == "__main__":
    start_trading_bot()
