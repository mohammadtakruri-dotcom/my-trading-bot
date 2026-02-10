import ccxt
import time
import sys

# استخدام منصة KuCoin بدلاً من Binance لتجنب القيود الجغرافية للسيرفرات السحابية
exchange = ccxt.kucoin()

def start_trading():
    print("--- تم إطلاق الروبوت بنجاح: وضع التداول الوهمي ---")
    sys.stdout.flush() # أمر ضروري لإظهار النتائج فوراً في Render
    
    # محفظة افتراضية للبدء
    balance_usd = 1000.0
    btc_held = 0.0
    
    print(f"رأس المال الوهمي للبداية: {balance_usd} USDT")
    sys.stdout.flush()

    while True:
        try:
            # جلب السعر اللحظي للبيتكوين
            ticker = exchange.fetch_ticker('BTC/USDT')
            current_price = ticker['last']
            timestamp = time.strftime('%H:%M:%S')
            
            # طباعة السعر في شاشة الـ Logs
            print(f"[{timestamp}] سعر البيتكوين الآن: {current_price} USDT")
            sys.stdout.flush()
            
            # استراتيجية شراء بسيطة للتجربة
            if btc_held == 0 and current_price < 95000:
                btc_held = balance_usd / current_price
                buy_price = current_price
                balance_usd = 0
                print(f"🚀 تم الشراء وهمياً بسعر: {current_price}")
                sys.stdout.flush()

            # استراتيجية بيع وهمي عند ربح 1%
            elif btc_held > 0 and current_price > (buy_price * 1.01):
                balance_usd = btc_held * current_price
                profit = balance_usd - 1000
                print(f"💰 تم البيع بربح! الرصيد: {balance_usd} | الربح: {profit}")
                btc_held = 0
                sys.stdout.flush()

            # فحص السعر كل 15 ثانية
            time.sleep(15)
            
        except Exception as e:
            print(f"تنبيه - خطأ في الاتصال: {e}")
            sys.stdout.flush()
            time.sleep(10)

if __name__ == "__main__":
    start_trading()
