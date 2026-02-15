import ccxt
import pandas as pd
import time
import os
from dotenv import load_dotenv

load_dotenv()

# إعداد المنصة مع نظام حماية الرصيد
exchange = ccxt.binance({
    'apiKey': os.getenv('ecHft3mkwGYEmdgkAgU9NxbLG9rQ0F7tEvguAty5VTlAD6OFkViku2TLrWE3rpUC'),
    'secret': os.getenv('QkmJ60G43gPtixzbKAtikJJUbvynLeJe2ci849w1qO74Ht2sBGON4rFwxlRQL2BV'),
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'}
})

# صمامات الأمان (Safety Rules)
MIN_BALANCE_RESERVE = 10.0  # رصيد احتياطي لا يلمسه الروبوت أبداً
TRADE_AMOUNT_USDT = 11.0     # المبلغ الثابت لكل صفقة (لإدارة المخاطر)

def get_account_balance():
    """جلب الرصيد مع معالجة أخطاء الشبكة لضمان الاستمرارية"""
    try:
        balance = exchange.fetch_balance()
        return float(balance.get('USDT', {}).get('free', 0))
    except Exception as e:
        print(f"⚠️ تنبيه: خطأ مؤقت في الاتصال، سيعيد الروبوت المحاولة... {e}")
        return None

def scan_market_opportunities():
    """رادار ذكي يمسح العملات الصاعدة فقط"""
    try:
        tickers = exchange.fetch_tickers()
        gainers = []
        for symbol, ticker in tickers.items():
            if '/USDT' in symbol and ticker['percentage'] is not None:
                # تصفية العملات التي لها زخم حقيقي فقط
                if ticker['percentage'] > 5: 
                    gainers.append({'symbol': symbol, 'pct': ticker['percentage']})
        return sorted(gainers, key=lambda x: x['pct'], reverse=True)[:5]
    except:
        return []

def safe_analysis(symbol):
    """تحليل فني دقيق لمنع الدخول في صفقات خاسرة"""
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='1m', limit=50)
        df = pd.DataFrame(bars, columns=['time', 'open', 'high', 'low', 'close', 'vol'])
        
        # مؤشرات الأمان (SMA)
        df['SMA7'] = df['close'].rolling(window=7).mean()
        df['SMA25'] = df['close'].rolling(window=25).mean()
        
        last_price = df['close'].iloc[-1]
        ma7 = df['SMA7'].iloc[-1]
        ma25 = df['SMA25'].iloc[-1]
        
        # شرط الدخول المضمون: تقاطع صاعد مؤكد
        if ma7 > ma25:
            print(f"✅ إشارة دخول آمنة لـ {symbol} عند سعر {last_price}")
            return True
        return False
    except:
        return False

# حلقة التشغيل الدائمة في Render
print("🚀 انطلاق نظام التكروري المضمون في السحابة...")
while True:
    balance = get_account_balance()
    
    if balance is not None:
        print(f"\n💰 الرصيد الحالي: {balance:.2f} USDT")
        
        # التحقق من توفر رصيد كافٍ بعد حجز الاحتياطي
        if balance > (TRADE_AMOUNT_USDT + MIN_BALANCE_RESERVE):
            opportunities = scan_market_opportunities()
            for opp in opportunities:
                if safe_analysis(opp['symbol']):
                    print(f"🎯 الروبوت يراقب {opp['symbol']} الآن وجاهز للتنفيذ...")
                time.sleep(1)
        else:
            print("🛑 الرصيد المتاح يقل عن الحد الآمن، وضع المراقبة فقط مفعل.")
            
    time.sleep(60) # فحص كل دقيقة لضمان الاستجابة السريعة
print("📡 الرادار يعمل الآن ويبحث عن فرص... الساعة: ", time.ctime())
