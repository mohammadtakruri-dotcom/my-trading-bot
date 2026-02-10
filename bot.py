import ccxt
import time
import sys

# الاتصال بمنصة بينانس
exchange = ccxt.binance()

print("--- بدء التداول الوهمي بنجاح ---")
sys.stdout.flush() # أمر إجباري لتظهر النتائج فوراً في Render

while True:
    try:
        ticker = exchange.fetch_ticker('BTC/USDT')
        price = ticker['last']
        
        # طباعة السعر مع التوقيت
        print(f"[{time.strftime('%H:%M:%S')}] سعر البيتكوين الآن: {price} USDT")
        sys.stdout.flush() 
        
        time.sleep(10) # تحديث كل 10 ثوانٍ
    except Exception as e:
        print(f"خطأ: {e}")
        sys.stdout.flush()
        time.sleep(5)
