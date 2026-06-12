"""
Multilingual Engine - OMNI BRAIN V2
=====================================
Translate trading content into 32 languages using Google Translate (free)
with LibreTranslate fallback and local caching.

Languages:
  Indian (12): hi, te, ta, kn, ml, mr, gu, pa, bn, or, as, ur
  International (20): en, ar, id, ms, tr, ru, pt, es, fr, de, zh, ja, ko, th, vi, sw, fa, nl, pl, it
"""

import os
import sys
import json
import hashlib
import logging
import urllib.request
import urllib.parse
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path

log = logging.getLogger('MultilingualEngine')

LOG_DIR = Path(__file__).parent.parent / 'production' / 'logs'
LOG_DIR.mkdir(parents=True, exist_ok=True)
CACHE_FILE = LOG_DIR / 'translation_cache.json'
LIBRE_URL = os.environ.get('LIBRE_TRANSLATE_URL', 'https://libretranslate.com/translate')

LANGUAGES: Dict[str, Dict[str, str]] = {
    'hi': {'name': 'Hindi', 'native': 'हिंदी', 'flag': '🇮🇳', 'dir': 'ltr'},
    'te': {'name': 'Telugu', 'native': 'తెలుగు', 'flag': '🇮🇳', 'dir': 'ltr'},
    'ta': {'name': 'Tamil', 'native': 'தமிழ்', 'flag': '🇮🇳', 'dir': 'ltr'},
    'kn': {'name': 'Kannada', 'native': 'ಕನ್ನಡ', 'flag': '🇮🇳', 'dir': 'ltr'},
    'ml': {'name': 'Malayalam', 'native': 'മലയാളം', 'flag': '🇮🇳', 'dir': 'ltr'},
    'mr': {'name': 'Marathi', 'native': 'मराठी', 'flag': '🇮🇳', 'dir': 'ltr'},
    'gu': {'name': 'Gujarati', 'native': 'ગુજરાતી', 'flag': '🇮🇳', 'dir': 'ltr'},
    'pa': {'name': 'Punjabi', 'native': 'ਪੰਜਾਬੀ', 'flag': '🇮🇳', 'dir': 'ltr'},
    'bn': {'name': 'Bengali', 'native': 'বাংলা', 'flag': '🇮🇳', 'dir': 'ltr'},
    'or': {'name': 'Odia', 'native': 'ଓଡ଼ିଆ', 'flag': '🇮🇳', 'dir': 'ltr'},
    'as': {'name': 'Assamese', 'native': 'অসমীয়া', 'flag': '🇮🇳', 'dir': 'ltr'},
    'ur': {'name': 'Urdu', 'native': 'اردو', 'flag': '🇮🇳', 'dir': 'rtl'},
    'en': {'name': 'English', 'native': 'English', 'flag': '🇬🇧', 'dir': 'ltr'},
    'ar': {'name': 'Arabic', 'native': 'العربية', 'flag': '🇸🇦', 'dir': 'rtl'},
    'id': {'name': 'Indonesian', 'native': 'Bahasa Indonesia', 'flag': '🇮🇩', 'dir': 'ltr'},
    'ms': {'name': 'Malay', 'native': 'Bahasa Melayu', 'flag': '🇲🇾', 'dir': 'ltr'},
    'tr': {'name': 'Turkish', 'native': 'Türkçe', 'flag': '🇹🇷', 'dir': 'ltr'},
    'ru': {'name': 'Russian', 'native': 'Русский', 'flag': '🇷🇺', 'dir': 'ltr'},
    'pt': {'name': 'Portuguese', 'native': 'Português', 'flag': '🇧🇷', 'dir': 'ltr'},
    'es': {'name': 'Spanish', 'native': 'Español', 'flag': '🇪🇸', 'dir': 'ltr'},
    'fr': {'name': 'French', 'native': 'Français', 'flag': '🇫🇷', 'dir': 'ltr'},
    'de': {'name': 'German', 'native': 'Deutsch', 'flag': '🇩🇪', 'dir': 'ltr'},
    'zh': {'name': 'Chinese', 'native': '中文', 'flag': '🇨🇳', 'dir': 'ltr'},
    'ja': {'name': 'Japanese', 'native': '日本語', 'flag': '🇯🇵', 'dir': 'ltr'},
    'ko': {'name': 'Korean', 'native': '한국어', 'flag': '🇰🇷', 'dir': 'ltr'},
    'th': {'name': 'Thai', 'native': 'ภาษาไทย', 'flag': '🇹🇭', 'dir': 'ltr'},
    'vi': {'name': 'Vietnamese', 'native': 'Tiếng Việt', 'flag': '🇻🇳', 'dir': 'ltr'},
    'sw': {'name': 'Swahili', 'native': 'Kiswahili', 'flag': '🇰🇪', 'dir': 'ltr'},
    'fa': {'name': 'Farsi', 'native': 'فارسی', 'flag': '🇮🇷', 'dir': 'rtl'},
    'nl': {'name': 'Dutch', 'native': 'Nederlands', 'flag': '🇳🇱', 'dir': 'ltr'},
    'pl': {'name': 'Polish', 'native': 'Polski', 'flag': '🇵🇱', 'dir': 'ltr'},
    'it': {'name': 'Italian', 'native': 'Italiano', 'flag': '🇮🇹', 'dir': 'ltr'},
}

INDIAN_LANGS = ['hi', 'te', 'ta', 'kn', 'ml', 'mr', 'gu', 'pa', 'bn', 'or', 'as', 'ur']
RTL_LANGS = ['ar', 'ur', 'fa']

DIRECTION_TRANSLATIONS: Dict[str, Dict[str, str]] = {}
for code in LANGUAGES:
    DIRECTION_TRANSLATIONS[code] = {}

DIRECTION_TRANSLATIONS['en'] = {'BULLISH': 'BULLISH', 'BEARISH': 'BEARISH'}
DIRECTION_TRANSLATIONS['hi'] = {'BULLISH': 'तेजी (BULLISH)', 'BEARISH': 'मंदी (BEARISH)'}
DIRECTION_TRANSLATIONS['te'] = {'BULLISH': 'బుల్లిష్', 'BEARISH': 'బేరిష్'}
DIRECTION_TRANSLATIONS['ta'] = {'BULLISH': 'ஏற்றம்', 'BEARISH': 'இறக்கம்'}
DIRECTION_TRANSLATIONS['kn'] = {'BULLISH': 'ಬುಲ್ಲಿಷ್', 'BEARISH': 'ಬೇರಿಷ್'}
DIRECTION_TRANSLATIONS['ml'] = {'BULLISH': 'ബുള്ളിഷ്', 'BEARISH': 'ബെയരിഷ്'}
DIRECTION_TRANSLATIONS['mr'] = {'BULLISH': 'तेजी', 'BEARISH': 'मंदी'}
DIRECTION_TRANSLATIONS['gu'] = {'BULLISH': 'તેજી', 'BEARISH': 'મંદી'}
DIRECTION_TRANSLATIONS['pa'] = {'BULLISH': 'ਤੇਜ਼ੀ', 'BEARISH': 'ਮੰਦੀ'}
DIRECTION_TRANSLATIONS['bn'] = {'BULLISH': 'বুলিশ', 'BEARISH': 'বেয়ারিশ'}
DIRECTION_TRANSLATIONS['or'] = {'BULLISH': 'ବୁଲିଶ', 'BEARISH': 'ବିୟରିଶ'}
DIRECTION_TRANSLATIONS['as'] = {'BULLISH': 'বুলিছ', 'BEARISH': 'বিয়েৰিছ'}
DIRECTION_TRANSLATIONS['ur'] = {'BULLISH': 'تیزی', 'BEARISH': 'مندی'}
DIRECTION_TRANSLATIONS['ar'] = {'BULLISH': 'صاعد', 'BEARISH': 'هابط'}
DIRECTION_TRANSLATIONS['id'] = {'BULLISH': 'NAIK', 'BEARISH': 'TURUN'}
DIRECTION_TRANSLATIONS['ms'] = {'BULLISH': 'NAIK', 'BEARISH': 'TURUN'}
DIRECTION_TRANSLATIONS['tr'] = {'BULLISH': 'YÜKSELİŞ', 'BEARISH': 'DÜŞÜŞ'}
DIRECTION_TRANSLATIONS['ru'] = {'BULLISH': 'БЫЧИЙ', 'BEARISH': 'МЕДВЕЖИЙ'}
DIRECTION_TRANSLATIONS['pt'] = {'BULLISH': 'ALCISTA', 'BEARISH': 'BAIXISTA'}
DIRECTION_TRANSLATIONS['es'] = {'BULLISH': 'ALCISTA', 'BEARISH': 'BAJISTA'}
DIRECTION_TRANSLATIONS['fr'] = {'BULLISH': 'HAUSSIER', 'BEARISH': 'BAISSIER'}
DIRECTION_TRANSLATIONS['de'] = {'BULLISH': 'BULLISH', 'BEARISH': 'BEARISH'}
DIRECTION_TRANSLATIONS['zh'] = {'BULLISH': '看涨', 'BEARISH': '看跌'}
DIRECTION_TRANSLATIONS['ja'] = {'BULLISH': '強気', 'BEARISH': '弱気'}
DIRECTION_TRANSLATIONS['ko'] = {'BULLISH': '상승', 'BEARISH': '하락'}
DIRECTION_TRANSLATIONS['th'] = {'BULLISH': 'ขาขึ้น', 'BEARISH': 'ขาลง'}
DIRECTION_TRANSLATIONS['vi'] = {'BULLISH': 'TĂNG', 'BEARISH': 'GIẢM'}
DIRECTION_TRANSLATIONS['sw'] = {'BULLISH': 'KUONGEKA', 'BEARISH': 'KUSHUKA'}
DIRECTION_TRANSLATIONS['fa'] = {'BULLISH': 'صعودی', 'BEARISH': 'نزولی'}
DIRECTION_TRANSLATIONS['nl'] = {'BULLISH': 'STIJGEND', 'BEARISH': 'DALEND'}
DIRECTION_TRANSLATIONS['pl'] = {'BULLISH': 'WZROSTOWY', 'BEARISH': 'SPADKOWY'}
DIRECTION_TRANSLATIONS['it'] = {'BULLISH': 'TORO', 'BEARISH': 'ORSO'}

CONFIRMATION_MESSAGES: Dict[str, str] = {}
CONFIRMATION_MESSAGES['hi'] = 'भाषा हिंदी में बदल दी गई ✅'
CONFIRMATION_MESSAGES['te'] = 'భాష తెలుగుకు మార్చబడింది ✅'
CONFIRMATION_MESSAGES['ta'] = 'மொழி தமிழுக்கு மாற்றப்பட்டது ✅'
CONFIRMATION_MESSAGES['kn'] = 'ಭಾಷೆಯನ್ನು ಕನ್ನಡಕ್ಕೆ ಬದಲಾಯಿಸಲಾಗಿದೆ ✅'
CONFIRMATION_MESSAGES['ml'] = 'ഭാഷ മലയാളത്തിലേക്ക് മാറ്റി ✅'
CONFIRMATION_MESSAGES['mr'] = 'भाषा मराठीमध्ये बदलली गेली ✅'
CONFIRMATION_MESSAGES['gu'] = 'ભાષા ગુજરાતીમાં બદલાઈ ગઈ ✅'
CONFIRMATION_MESSAGES['pa'] = 'ਭਾਸ਼ਾ ਪੰਜਾਬੀ ਵਿੱਚ ਬਦਲ ਦਿੱਤੀ ਗਈ ✅'
CONFIRMATION_MESSAGES['bn'] = 'ভাষা বাংলায় পরিবর্তন করা হয়েছে ✅'
CONFIRMATION_MESSAGES['or'] = 'ଭାଷା ଓଡ଼ିଆକୁ ବଦଳାଗଲା ✅'
CONFIRMATION_MESSAGES['as'] = 'ভাষা অসমীয়ালৈ সলনি কৰা হৈছে ✅'
CONFIRMATION_MESSAGES['ur'] = 'زبان اردو میں تبدیل کر دی گئی ✅'
CONFIRMATION_MESSAGES['en'] = 'Language changed to English ✅'
CONFIRMATION_MESSAGES['ar'] = 'تم تغيير اللغة إلى العربية ✅'
CONFIRMATION_MESSAGES['id'] = 'Bahasa diubah ke Indonesia ✅'
CONFIRMATION_MESSAGES['ms'] = 'Bahasa ditukar ke Melayu ✅'
CONFIRMATION_MESSAGES['tr'] = 'Dil Türkçe olarak değiştirildi ✅'
CONFIRMATION_MESSAGES['ru'] = 'Язык изменен на русский ✅'
CONFIRMATION_MESSAGES['pt'] = 'Idioma alterado para português ✅'
CONFIRMATION_MESSAGES['es'] = 'Idioma cambiado a español ✅'
CONFIRMATION_MESSAGES['fr'] = 'Langue changée en français ✅'
CONFIRMATION_MESSAGES['de'] = 'Sprache auf Deutsch geändert ✅'
CONFIRMATION_MESSAGES['zh'] = '语言已更改为中文 ✅'
CONFIRMATION_MESSAGES['ja'] = '言語を日本語に変更しました ✅'
CONFIRMATION_MESSAGES['ko'] = '언어가 한국어로 변경되었습니다 ✅'
CONFIRMATION_MESSAGES['th'] = 'เปลี่ยนภาษาเป็นภาษาไทยแล้ว ✅'
CONFIRMATION_MESSAGES['vi'] = 'Đã đổi ngôn ngữ sang tiếng Việt ✅'
CONFIRMATION_MESSAGES['sw'] = 'Lugha imebadilishwa hadi Kiswahili ✅'
CONFIRMATION_MESSAGES['fa'] = 'زبان به فارسی تغییر یافت ✅'
CONFIRMATION_MESSAGES['nl'] = 'Taal gewijzigd naar Nederlands ✅'
CONFIRMATION_MESSAGES['pl'] = 'Język zmieniony na polski ✅'
CONFIRMATION_MESSAGES['it'] = 'Lingua cambiata in italiano ✅'

SIGNAL_TEMPLATES: Dict[str, str] = {}
SIGNAL_TEMPLATES['en'] = (
    "\U0001f680 TRADE SIGNAL \u2014 {decision}\n"
    "Asset: {symbol}\n"
    "Direction: {direction}\n"
    "Score: {score}/100\n"
    "Entry: {entry}\n"
    "SL: {sl} | TP: {tp}\n"
    "Time: {time}"
)
SIGNAL_TEMPLATES['hi'] = (
    "\U0001f680 \u091f\u094d\u0930\u0947\u0921 \u0938\u093f\u0917\u094d\u0928\u0932 \u2014 {decision}\n"
    "\u090f\u0938\u0947\u091f: {symbol}\n"
    "\u0926\u093f\u0936\u093e: {direction}\n"
    "\u0938\u094d\u0915\u094b\u0930: {score}/100\n"
    "\u090f\u0902\u091f\u094d\u0930\u0940: {entry}\n"
    "SL: {sl} | TP: {tp}\n"
    "\u0938\u092e\u092f: {time}"
)
SIGNAL_TEMPLATES['te'] = (
    "\U0001f680 \u0c1f\u0c4d\u0c30\u0c47\u0c21\u0c4d \u0c38\u0c3f\u0c17\u0c4d\u0c28\u0c32\u0c4d \u2014 {decision}\n"
    "\u0c06\u0c38\u0c46\u0c1f\u0c4d: {symbol}\n"
    "\u0c26\u0c3f\u0c36: {direction}\n"
    "\u0c38\u0c4d\u0c15\u0c4b\u0c30\u0c4d: {score}/100\n"
    "\u0c0e\u0c02\u0c1f\u0c4d\u0c30\u0c40: {entry}\n"
    "SL: {sl} | TP: {tp}\n"
    "\u0c38\u0c2e\u0c2f\u0c02: {time}"
)
SIGNAL_TEMPLATES['ar'] = (
    "\U0001f680 \u0625\u0634\u0627\u0631\u0629 \u062a\u062f\u0627\u0648\u0644 \u2014 {decision}\n"
    "\u0627\u0644\u0623\u0635\u0644: {symbol}\n"
    "\u0627\u0644\u0627\u062a\u062c\u0627\u0647: {direction}\n"
    "\u0627\u0644\u0646\u0642\u0627\u0637: {score}/100\n"
    "\u0627\u0644\u062f\u062e\u0648\u0644: {entry}\n"
    "\u0648\u0642\u0641: {sl} | \u0647\u062f\u0641: {tp}\n"
    "\u0627\u0644\u0648\u0642\u062a: {time}"
)

REGIONAL_HASHTAGS: Dict[str, List[str]] = {
    'hi': ['#फॉरेक्सट्रेडिंग', '#ट्रेडिंगहिंदी', '#शेयरबाजार', '#सोनाट्रेडिंग', '#forexhindi', '#tradinghindi', '#indiantrader', '#nsetrading'],
    'te': ['#ట్రేడింగ్', '#ఫారెక్స్', '#బంగారం', '#telugutrader', '#andhratrader', '#forextelugu', '#tradingtelugu'],
    'ta': ['#டிரேடிங்', '#ஃபாரெக்ஸ்', '#தங்கம்', '#tamiltrader', '#forextamil'],
    'kn': ['#ಕನ್ನಡದಲ್ಲಿಟ್ರೇಡಿಂಗ್', '#ಫಾರೆಕ್ಸ್', '#ಚಿನ್ನ', '#kannadatrading'],
    'ml': ['#മലയാളംട്രേഡിങ്', '#ഫോറക്സ്', '#സ്വർണം', '#forexmalayalam'],
    'mr': ['#मराठीट्रेडिंग', '#फॉरेक्स', '#सोने', '#forexmarathi', '#marathitrader'],
    'gu': ['#ગુજરાતી ટ્રેડિંગ', '#ફોરેક્સ', '#સોનું', '#forexgujarati'],
    'pa': ['#ਪੰਜਾਬੀ ਟ੍ਰੇਡਿੰਗ', '#ਫੋਰੈਕਸ', '#ਸੋਨਾ', '#forexpunjabi'],
    'bn': ['#বাংলা ট্রেডিং', '#ফরেক্স', '#সোনা', '#forexbangla', '#banglatrader'],
    'or': ['#ଓଡ଼ିଆଟ୍ରେଡିଂ', '#ଫରେକ୍ସ', '#ସୁନା', '#forexodia'],
    'as': ['#অসমীয়াট্ৰেডিং', '#ফৰেক্স', '#সোণ', '#forexassamese'],
    'ur': ['#اردوٹریڈنگ', '#فاریکس', '#سونےکیٰتجارت', '#forexurdu'],
    'en': ['#forextrading', '#forexsignals', '#xauusd', '#smc', '#trading', '#algorithmictrading', '#forexanalysis'],
    'ar': ['#تداول', '#فوركس', '#ذهب', '#تحليل', '#arabictrader', '#forexarabic', '#تداولالعملات', '#استثمار'],
    'id': ['#tradingforex', '#belajarforex', '#forexindonesia', '#tradingemas', '#analisisforex', '#sinyalforex'],
    'ms': ['#tradingforex', '#belajarforex', '#forexmalaysia', '#emas', '#analisisforex'],
    'tr': ['#forexsinyalleri', '#altinanaliz', '#forexturkiye', '#borsa', '#tradingturkiye'],
    'ru': ['#трейдинг', '#форекс', '#золото', '#анализрынка', '#трейдингсигналы'],
    'pt': ['#tradingforex', '#sinaisforex', '#ouro', '#forexbrasil', '#analiseforex'],
    'es': ['#tradingforex', '#señalesforex', '#orotrading', '#forexespañol', '#analisisforex'],
    'fr': ['#tradingforex', '#signauxforex', '#or', '#forexfrance', '#analyseforex'],
    'de': ['#forexhandel', '#tradingsignale', '#goldhandel', '#forexdeutschland'],
    'zh': ['#外汇交易', '#黄金交易', '#交易信号', '#外汇分析', '#算法交易'],
    'ja': ['#FXトレード', '#ゴールドトレード', '#シグナル', '#外国為替', '#トレーディング'],
    'ko': ['#외환거래', '#금거래', '#트레이딩신호', '#외환분석'],
    'th': ['#เทรดฟอเร็กซ์', '#เทรดทอง', '#สัญญาณเทรด', '#วิเคราะห์ฟอเร็กซ์'],
    'vi': ['#giaodichforex', '#tinhieugiaodich', '#vang', '#phan tich forex'],
    'sw': ['#forex', '#biashara', '#dhahabu', '#isharaforex'],
    'fa': ['#فارکس', '#طلا', '#سیگنال_فارکس', '#تحلیل_بازار', '#معاملات'],
    'nl': ['#forexhandel', '#tradingsignalen', '#goudhandel', '#forexnederlands'],
    'pl': ['#forexhandel', '#sygnałytradingowe', '#złoto', '#forexpolska'],
    'it': ['#tradingforex', '#segnialiforex', '#oro', '#forexitalia', '#analisitecnica'],
}

REGIONAL_PRICES: Dict[str, Dict[str, Any]] = {
    'hi': {'code': 'INR', 'symbol': '₹', 'monthly': 999, 'yearly': 9990},
    'te': {'code': 'INR', 'symbol': '₹', 'monthly': 999, 'yearly': 9990},
    'ta': {'code': 'INR', 'symbol': '₹', 'monthly': 999, 'yearly': 9990},
    'kn': {'code': 'INR', 'symbol': '₹', 'monthly': 999, 'yearly': 9990},
    'ml': {'code': 'INR', 'symbol': '₹', 'monthly': 999, 'yearly': 9990},
    'mr': {'code': 'INR', 'symbol': '₹', 'monthly': 999, 'yearly': 9990},
    'gu': {'code': 'INR', 'symbol': '₹', 'monthly': 999, 'yearly': 9990},
    'pa': {'code': 'INR', 'symbol': '₹', 'monthly': 999, 'yearly': 9990},
    'bn': {'code': 'INR', 'symbol': '₹', 'monthly': 999, 'yearly': 9990},
    'or': {'code': 'INR', 'symbol': '₹', 'monthly': 999, 'yearly': 9990},
    'as': {'code': 'INR', 'symbol': '₹', 'monthly': 999, 'yearly': 9990},
    'ur': {'code': 'INR', 'symbol': '₹', 'monthly': 999, 'yearly': 9990},
    'en': {'code': 'USD', 'symbol': '$', 'monthly': 12, 'yearly': 120},
    'ar': {'code': 'AED', 'symbol': 'د.إ', 'monthly': 45, 'yearly': 450},
    'id': {'code': 'IDR', 'symbol': 'Rp', 'monthly': 150000, 'yearly': 1500000},
    'ms': {'code': 'MYR', 'symbol': 'RM', 'monthly': 50, 'yearly': 500},
    'tr': {'code': 'TRY', 'symbol': '₺', 'monthly': 350, 'yearly': 3500},
    'ru': {'code': 'RUB', 'symbol': '₽', 'monthly': 1100, 'yearly': 11000},
    'pt': {'code': 'USD', 'symbol': '$', 'monthly': 12, 'yearly': 120},
    'es': {'code': 'USD', 'symbol': '$', 'monthly': 12, 'yearly': 120},
    'fr': {'code': 'EUR', 'symbol': '€', 'monthly': 11, 'yearly': 110},
    'de': {'code': 'EUR', 'symbol': '€', 'monthly': 11, 'yearly': 110},
    'zh': {'code': 'USD', 'symbol': '$', 'monthly': 12, 'yearly': 120},
    'ja': {'code': 'JPY', 'symbol': '¥', 'monthly': 1800, 'yearly': 18000},
    'ko': {'code': 'KRW', 'symbol': '₩', 'monthly': 16000, 'yearly': 160000},
    'th': {'code': 'THB', 'symbol': '฿', 'monthly': 420, 'yearly': 4200},
    'vi': {'code': 'VND', 'symbol': '₫', 'monthly': 300000, 'yearly': 3000000},
    'sw': {'code': 'USD', 'symbol': '$', 'monthly': 12, 'yearly': 120},
    'fa': {'code': 'USD', 'symbol': '$', 'monthly': 12, 'yearly': 120},
    'nl': {'code': 'EUR', 'symbol': '€', 'monthly': 11, 'yearly': 110},
    'pl': {'code': 'PLN', 'symbol': 'zł', 'monthly': 50, 'yearly': 500},
    'it': {'code': 'EUR', 'symbol': '€', 'monthly': 11, 'yearly': 110},
}

BOT_COMMANDS_HELP: Dict[str, str] = {}
BOT_COMMANDS_HELP['en'] = "\U0001f4da Available commands:\n/status - Live scores for all 4 assets\n/score XAUUSD - Detailed analysis\n/cb - Circuit breaker status\n/language - Change language\n/report - Daily report\n/referral - Get referral code\n/help - Show this help"
BOT_COMMANDS_HELP['hi'] = "\U0001f4da \u0909\u092a\u0932\u092c\u094d\u0927 \u0915\u092e\u093e\u0902\u0921:\n/status - \u0938\u092d\u0940 4 \u090f\u0938\u0947\u091f\u094d\u0938 \u0915\u0947 \u0932\u093e\u0907\u0935 \u0938\u094d\u0915\u094b\u0930\n/score XAUUSD - \u0935\u093f\u0938\u094d\u0924\u0943\u0924 \u0935\u093f\u0936\u094d\u0932\u0947\u0937\u0923\n/cb - \u0938\u0930\u094d\u0915\u093f\u091f \u092c\u094d\u0930\u0947\u0915\u0930 \u0938\u094d\u0925\u093f\u0924\u093f\n/language - \u092d\u093e\u0937\u093e \u092c\u0926\u0932\u0947\u0902\n/report - \u0926\u0948\u0928\u093f\u0915 \u0930\u093f\u092a\u094b\u0930\u094d\u091f\n/help - \u092f\u0939 \u0938\u0939\u093e\u092f\u0924\u093e \u0926\u093f\u0916\u093e\u090f\u0902"
BOT_COMMANDS_HELP['te'] = "\U0001f4da \u0c05\u0c02\u0c21\u0c41\u0c2c\u0c3e\u0c1f\u0c41 \u0c15\u0c2e\u0c3e\u0c02\u0c21\u0c4d\u0c32\u0c41:\n/status - \u0c2e\u0c4a\u0c24\u0c4d\u0c24\u0c02 4 \u0c06\u0c38\u0c46\u0c1f\u0c4d\u0c32 \u0c32\u0c48\u0c35\u0c4d \u0c38\u0c4d\u0c15\u0c4b\u0c30\u0c4d\u0c32\u0c41\n/score XAUUSD - \u0c35\u0c3f\u0c38\u0c4d\u0c24\u0c30\u0c2e\u0c48\u0c28 \u0c35\u0c3f\u0c36\u0c4d\u0c32\u0c47\u0c37\u0c23\n/cb - \u0c38\u0c30\u0c4d\u0c15\u0c3f\u0c1f\u0c4d \u0c2c\u0c4d\u0c30\u0c46\u0c15\u0c30\u0c4d \u0c38\u0c4d\u0c25\u0c3f\u0c24\u0c3f\n/language - \u0c2d\u0c3e\u0c37 \u0c2e\u0c3e\u0c30\u0c4d\u0c1a\u0c02\u0c21\u0c3f\n/report - \u0c30\u0c4b\u0c1c\u0c41 \u0c28\u0c3f\u0c35\u0c47\u0c26\u0c3f\u0c15\n/help - \u0c08 \u0c38\u0c39\u0c3e\u0c2f\u0c02 \u0c1a\u0c42\u0c2a\u0c3f\u0c38\u0c4d\u0c24\u0c41\u0c02\u0c26\u0c3f"
BOT_COMMANDS_HELP['ar'] = "\U0001f4da \u0627\u0644\u0623\u0648\u0627\u0645\u0631 \u0627\u0644\u0645\u062a\u0627\u062d\u0629:\n/status - \u062f\u0631\u062c\u0627\u062a \u062c\u0645\u064a\u0639 \u0627\u0644\u0623\u0635\u0648\u0644 \u0627\u0644\u0623\u0631\u0628\u0639\u0629\n/score XAUUSD - \u062a\u062d\u0644\u064a\u0644 \u0645\u0641\u0635\u0644\n/cb - \u062d\u0627\u0644\u0629 \u0642\u0627\u0637\u0639 \u0627\u0644\u062f\u0627\u0626\u0631\u0629\n/language - \u062a\u063a\u064a\u064a\u0631 \u0627\u0644\u0644\u063a\u0629\n/report - \u0627\u0644\u062a\u0642\u0631\u064a\u0631 \u0627\u0644\u064a\u0648\u0645\u064a\n/help - \u0639\u0631\u0636 \u0647\u0630\u0647 \u0627\u0644\u0645\u0633\u0627\u0639\u062f\u0629"

for code in LANGUAGES:
    if code not in BOT_COMMANDS_HELP:
        BOT_COMMANDS_HELP[code] = BOT_COMMANDS_HELP['en']

ERROR_MESSAGES: Dict[str, str] = {}
ERROR_MESSAGES['en'] = "Invalid command. Use /help to see available commands."
ERROR_MESSAGES['hi'] = "अमान्य कमांड। उपलब्ध कमांड के लिए /help देखें।"
ERROR_MESSAGES['te'] = "చెల్లని కమాండ్. అందుబాటులో ఉన్న కమాండ్ల కోసం /help చూడండి."
ERROR_MESSAGES['ar'] = "أمر غير صالح. استخدم /help لعرض الأوامر المتاحة."

SUBSCRIPTION_EXPIRED: Dict[str, str] = {}
SUBSCRIPTION_EXPIRED['en'] = "Your VIP subscription has expired. Renew at: {link}"
SUBSCRIPTION_EXPIRED['hi'] = "आपकी VIP सदस्यता समाप्त हो गई। नवीनीकृत करें: {link}"
SUBSCRIPTION_EXPIRED['te'] = "మీ VIP సభ్యత్వం గడువు ముగిసింది. పునరుద్ధరించండి: {link}"
SUBSCRIPTION_EXPIRED['ar'] = "انتهت صلاحية اشتراك VIP الخاص بك. جدد على: {link}"


class MultilingualEngine:
    """Translate content between 32 languages with caching."""

    def __init__(self):
        self.cache: Dict[str, str] = {}
        self._load_cache()

    def _load_cache(self):
        if CACHE_FILE.exists():
            try:
                with open(CACHE_FILE) as f:
                    self.cache = json.load(f)
            except Exception:
                self.cache = {}

    def _save_cache(self):
        try:
            with open(CACHE_FILE, 'w') as f:
                json.dump(self.cache, f, indent=2, ensure_ascii=False)
        except Exception as e:
            log.warning(f"Cache save failed: {e}")

    def _cache_key(self, text: str, target_lang: str) -> str:
        raw = f"{text}_{target_lang}"
        return hashlib.md5(raw.encode()).hexdigest()

    def translate(self, text: str, target_lang: str,
                  source_lang: str = 'en') -> str:
        if target_lang == source_lang:
            return text
        if not text or not text.strip():
            return text

        key = self._cache_key(text, target_lang)
        if key in self.cache:
            return self.cache[key]

        try:
            result = self._google_translate(text, target_lang, source_lang)
            self.cache[key] = result
            self._save_cache()
            log.info(f"Translated {len(text)} chars → {target_lang}")
            return result
        except Exception as e:
            log.warning(f"Google Translate failed: {e}, trying LibreTranslate")
            try:
                result = self._libre_translate(text, target_lang, source_lang)
                self.cache[key] = result
                self._save_cache()
                return result
            except Exception as e2:
                log.warning(f"LibreTranslate also failed: {e2}")
                return text

    def _google_translate(self, text: str, target: str, source: str) -> str:
        import urllib.request, urllib.parse
        encoded = urllib.parse.quote(text)
        url = (f"https://translate.googleapis.com/translate_a/"
               f"single?client=gtx&sl={source}&tl={target}"
               f"&dt=t&q={encoded}")
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0'
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        parts = []
        for segment in data[0]:
            if segment[0]:
                parts.append(segment[0])
        return ''.join(parts)

    def _libre_translate(self, text: str, target: str, source: str) -> str:
        import urllib.request
        payload = json.dumps({
            'q': text, 'source': source,
            'target': target, 'format': 'text'
        }).encode()
        req = urllib.request.Request(LIBRE_URL, data=payload,
                                      headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        return data.get('translatedText', text)

    def translate_direction(self, direction: str, lang: str) -> str:
        dir_map = {'BUY': 'BULLISH', 'SELL': 'BEARISH', 'BULLISH': 'BULLISH', 'BEARISH': 'BEARISH'}
        mapped = dir_map.get(direction.upper(), direction.upper())
        dirs = DIRECTION_TRANSLATIONS.get(lang, {})
        return dirs.get(mapped, mapped)

    def translate_signal(self, template_data: Dict[str, Any],
                         lang: str) -> str:
        template = SIGNAL_TEMPLATES.get(lang, SIGNAL_TEMPLATES['en'])
        dir_translated = self.translate_direction(
            template_data.get('direction', 'BULLISH'), lang
        )
        data = dict(template_data)
        data['direction'] = dir_translated
        return template.format(**data)

    def get_confirmation(self, lang: str) -> str:
        return CONFIRMATION_MESSAGES.get(lang, CONFIRMATION_MESSAGES['en'])

    def get_hashtags(self, lang: str) -> str:
        tags = REGIONAL_HASHTAGS.get(lang, REGIONAL_HASHTAGS['en'])
        return ' '.join(tags[:8])

    def get_regional_price(self, lang: str) -> Dict[str, Any]:
        return REGIONAL_PRICES.get(lang, REGIONAL_PRICES['en'])

    def get_bot_help(self, lang: str) -> str:
        return BOT_COMMANDS_HELP.get(lang, BOT_COMMANDS_HELP['en'])

    def get_error_message(self, lang: str) -> str:
        return ERROR_MESSAGES.get(lang, ERROR_MESSAGES['en'])

    def get_expired_message(self, lang: str, link: str = '') -> str:
        msg = SUBSCRIPTION_EXPIRED.get(lang, SUBSCRIPTION_EXPIRED['en'])
        return msg.format(link=link)

    def get_supported_languages(self) -> List[Dict[str, Any]]:
        return [
            {'code': code, **meta}
            for code, meta in LANGUAGES.items()
        ]

    def get_language_code_from_flag(self, flag: str) -> Optional[str]:
        for code, meta in LANGUAGES.items():
            if meta['flag'] == flag:
                return code
        return None

    def detect_script_region(self, lang: str) -> str:
        if lang in INDIAN_LANGS:
            return 'IN'
        if lang in RTL_LANGS:
            return 'ME'
        if lang in ['id', 'ms', 'th', 'vi', 'zh', 'ja', 'ko']:
            return 'AS'
        if lang in ['tr', 'ru']:
            return 'EU'
        if lang in ['pt', 'es', 'fr', 'de', 'it', 'nl', 'pl']:
            return 'EU'
        return 'INT'


_engine: Optional[MultilingualEngine] = None


def get_engine() -> MultilingualEngine:
    global _engine
    if _engine is None:
        _engine = MultilingualEngine()
    return _engine


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

    if '--test' in sys.argv:
        engine = get_engine()
        print(f"\n{'='*60}")
        print(f"  MULTILINGUAL ENGINE — TEST")
        print(f"{'='*60}")
        print(f"\n  Languages: {len(LANGUAGES)}")
        print(f"  Indian: {len(INDIAN_LANGS)}")
        print(f"  RTL: {len(RTL_LANGS)}")

        test_text = "Hello, welcome to OMNI BRAIN trading signals!"
        print(f"\n  Test translation: '{test_text}'")

        test_langs = ['hi', 'te', 'ar', 'id', 'tr', 'ru', 'zh', 'es', 'fr', 'de']
        for lang in test_langs:
            translated = engine.translate(test_text, lang)
            meta = LANGUAGES.get(lang, {})
            print(f"  {meta.get('flag','')} {lang} ({meta.get('native','')}): {translated}")

        print(f"\n  Direction translations:")
        for lang in ['hi', 'te', 'ar', 'id', 'tr', 'ru', 'zh', 'es']:
            meta = LANGUAGES.get(lang, {})
            b = engine.translate_direction('BULLISH', lang)
            be = engine.translate_direction('BEARISH', lang)
            print(f"  {meta.get('flag','')} {lang}: {b} / {be}")

        print(f"\n  Signal template (en):")
        data = {'symbol': 'XAUUSD', 'direction': 'BULLISH', 'decision': 'EXECUTE',
                'score': 85, 'entry': '2345.50', 'sl': '2325.00', 'tp': '2380.00', 'time': '14:30 UTC'}
        print(f"  {engine.translate_signal(data, 'en')}")
        print(f"\n  Signal template (te):")
        print(f"  {engine.translate_signal(data, 'te')}")
        print(f"\n  Signal template (ar):")
        print(f"  {engine.translate_signal(data, 'ar')}")

        print(f"\n  Regional prices:")
        for lang in ['hi', 'ar', 'id', 'tr', 'ru', 'fr', 'ja']:
            p = engine.get_regional_price(lang)
            meta = LANGUAGES.get(lang, {})
            print(f"  {meta.get('flag','')} {lang}: {p['symbol']}{p['monthly']}/{p['code']}")

        print(f"\n  Bot commands (te):")
        print(f"  {engine.get_bot_help('te')}")

        print(f"\n  Confirmation (ar): {engine.get_confirmation('ar')}")
        print(f"  Confirmation (hi): {engine.get_confirmation('hi')}")

        print(f"\n  Hashtags (hi): {engine.get_hashtags('hi')[:80]}...")
        print(f"  Hashtags (ar): {engine.get_hashtags('ar')[:80]}...")

        print(f"\n{'='*60}")
        print(f"  Cache entries: {len(engine.cache)}")
        print(f"{'='*60}")

    elif '--translate' in sys.argv:
        idx = sys.argv.index('--translate')
        text = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else "Hello"
        lang = sys.argv[idx + 2] if idx + 2 < len(sys.argv) else 'hi'
        engine = get_engine()
        print(engine.translate(text, lang))

    else:
        print("Usage:")
        print("  python multilingual_engine.py --test           # Test all languages")
        print("  python multilingual_engine.py --translate 'text' hi  # Translate")
