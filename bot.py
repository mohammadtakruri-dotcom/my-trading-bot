import ccxt
import pandas as pd
import time
import os
import sys
from dotenv import load_dotenv

# تحميل المفاتيح من الخزنة المشفرة في Render
load_dotenv()

# تهيئة الاتصال بباينانس مع نظام الأمان
exchange = ccxt.binance({
    'apiKey': os.getenv('ecHft3mkwGYEmdgkAgU9NxbLG9rQ0F7tEvguAty5VTlAD6OFkViku2TLrWE3rpUC'),
    'secret': os.getenv('QkmJ60G43gPtixzbKAtikJJUbvynLeJe2ci849w1qO74Ht2sBGON4rFwxlRQL2BV'),
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'}
})

# صمامات الأمان (Safety Rules) لمنع المخاطرة برصيدك الحقيقي
MIN_BALANCE_RESERVE = 10.0  # رصيد احتياطي لا يلمسه الروبوت أبداً
TRADE_AMOUNT_USDT = 11.0     # المبلغ الثابت لكل صفقة تداول

def get_account_balance():
    """جلب الرصيد مع إجبار السجلات على الظهور فوراً"""
    try:
        balance = exchange.fetch_balance()
        usdt_free = float(balance.get('USDT', {}).get('free', 0))
        # استخدام flush=True لضمان ظهور القراءة في Render Logs فوراً
        print(f"💰 الرصيد الحالي المكتشف في محفظتك: {usdt_free:.2f} USDT", flush=True)
        return usdt_free
    except Exception as e:
        print(f"⚠️ تنبيه: فشل الاتصال بباينانس، سأحاول مجدداً... {e}", flush=True)
        return None

def scan_market_opportunities():
    """رادار مسح العملات الصاعدة التي تظهر في شاشتك"""
    try:
        tickers = exchange.fetch_tickers()
        gainers = []
        for symbol, ticker in tickers.items():
            if '/USDT' in symbol and ticker['percentage'] is not None:
                if ticker['percentage'] > 5: 
                    gainers.append({'symbol': symbol, 'pct': ticker['percentage']})
        return sorted(gainers, key=lambda x: x['pct'], reverse=True)[:5]
    except Exception as e:
        print(f"❌ خطأ في مسح السوق: {e}", flush=True)
        return []

# رسالة انطلاق النظام (لتأكيد أن الكود بدأ فعلياً)
print("🚀 انطلق نظام رادار التكروري المضمون في السحابة...", flush=True)
print("📡 جاري فحص الاتصال ومسح المحفظة الرقمية الآن...", flush=True)

while True:
    try:
        balance = get_account_balance()
        
        if balance is not None:
            # التحقق من توفر رصيد كافٍ للتداول الآمن
            if balance > (TRADE_AMOUNT_USDT + MIN_BALANCE_RESERVE):
                opportunities = scan_market_opportunities()
                if not opportunities:
                    print("⚖️ السوق حالياً مستقر، الرادار يبحث عن عملات صاعدة...", flush=True)
                
                for opp in opportunities:
                    print(f"🔥 فرصة مكتشفة: {opp['symbol']} بصعود {opp['pct']:.2f}%", flush=True)
            else:
                print(f"🛑 الرصيد المتاح ({balance:.2f}) يقل عن حد الأمان (21$)، وضع المراقبة مفعل.", flush=True)
                
    except Exception as main_error:
        print(f"⚠️ خطأ في الدورة الحالية: {main_error}", flush=True)
            
    # انتظار دقيقة واحدة قبل الفحص القادم لضمان استمرارية العمل
    time.sleep(60)
            
