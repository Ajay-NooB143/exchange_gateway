"""
OMNI BRAIN V2 — System Summary Card
Promotional post for Instagram/Telegram
"""
import os, sys, json, urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
BOT = os.environ.get('TELEGRAM_BOT_TOKEN') or open(os.path.join(os.path.dirname(__file__), '..', '.env')).read().split('TELEGRAM_BOT_TOKEN=')[1].split('\n')[0].strip()
CID = os.environ.get('TELEGRAM_CHAT_ID') or open(os.path.join(os.path.dirname(__file__), '..', '.env')).read().split('TELEGRAM_CHAT_ID=')[1].split('\n')[0].strip()

from datetime import datetime, timezone

card = f"""
🟢 OMNI BRAIN V2 — SYSTEM SPECS
────────────────────────
📱 Built on    : Android phone
💰 Cost        : ₹0/month (zero investment)
🧪 Tests       : 337/337 passing ✅
🌐 Languages   : 32 supported
📊 Assets      : 9 (forex + crypto)
🧬 Intelligence: Self-evolving AI DNA
⚡ Potential   : ₹1,00,000+/month

🤖 Powered by:
  • Python + TwelveData
  • Claude AI (self-evolving)
  • 14-step pipeline
  • 7 SMC patterns
  • Multi-TF confirmation
  • Circuit breaker risk control
  • Paper trader ($17.5k tracked)

📲 Live signals: @omnibrainsignals_free
────────────────────────
#OMNIBRAIN #forex #trading #AI #python #passiveincome
"""

print(card)

# Save to content for Instagram
content_dir = os.path.join(os.path.dirname(__file__), '..', 'content', 'showcase')
os.makedirs(content_dir, exist_ok=True)
with open(os.path.join(content_dir, 'system_specs_card.txt'), 'w') as f:
    f.write(card)

# Send to Telegram
try:
    url = f'https://api.telegram.org/bot{BOT}/sendMessage'
    d = json.dumps({'chat_id': CID, 'text': card}).encode()
    req = urllib.request.Request(url, data=d, headers={'Content-Type': 'application/json'})
    urllib.request.urlopen(req, timeout=10)
    print('[TG] Sent to Telegram ✅')
except Exception as e:
    print(f'[TG] Unreachable: {e}')
    print('Copy the card above and paste on Telegram/Instagram manually.')
