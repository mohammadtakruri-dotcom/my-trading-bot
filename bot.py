import ccxt
import time
import sys

# استخدام منصة KuCoin لتجنب قيود الموقع الجغرافي في السيرفرات السحابية
exchange = ccxt.kucoin()

def run_bot():
    print("--- تم تشغيل الروبوت بنجاح: تداول وهمي (Paper Trading) ---")
    sys.stdout.flush() # لضمان ظهور النص فوراً في Render
    
    # إعداد محفظة وهمية للبدء
    balance_usd = 1000.0
    btc_held = 0.0
    
    print(f"رأس المال الوهمي للبداية: {balance_usd} دولار")
    sys.stdout.flush()

    while True:
        try:
            # جلب السعر الحالي للبيتكوين
            ticker = exchange.fetch_ticker('BTC/USDT')
            current_price = ticker['last']
            timestamp = time.strftime('%H:%M:%S')
            
            # طباعة السعر لمراقبته من شاشة الـ Logs
            print(f"[{timestamp}] السعر الحالي للبيتكوين: {current_price} USDT")
            sys.stdout.flush()
            
            # استراتيجية بسيطة جداً للتجربة:
            # 1. شراء وهمي إذا نزل السعر (كمثال عند 90,000)
            if btc_held == 0 and current_price < 90000:
                btc_held = balance_usd / current_price
                balance_usd = 0
                print(f"🚀 تم الشراء وهمياً بسعر: {current_price}")
                sys.stdout.flush()

            # 2. بيع وهمي إذا ربحنا 1% من سعر الشراء
            elif btc_held > 0 and current_price > (buy_price * 1.01):
                balance_usd = btc_held * current_price
                btc_held = 0
                print(f"💰 تم البيع بربح! الرصيد الجديد: {balance_usd} USDT")
                sys.stdout.flush()

            # الانتظار لمدة 15 ثانية قبل الفحص التالي
            time.sleep(15)
            
        except Exception as e:
            print(f"حدث خطأ في الاتصال: {e}")
            sys.stdout.flush()
            time.sleep(10)

if __name__ == "__main__":
    run_bot()
