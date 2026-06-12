"""Emergency wipe: delete encrypted secrets and key file."""
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
KEY_FILE = BASE_DIR / '.secrets.key'
ENCRYPTED_FILE = BASE_DIR / '.env.encrypted'


def wipe():
    deleted = []
    for f in [ENCRYPTED_FILE, KEY_FILE]:
        if f.exists():
            f.unlink()
            deleted.append(str(f.name))
            print(f"❌ Deleted: {f}")

    if not deleted:
        print("⚠️  No secret files found to wipe")
        return

    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID', '')
    if bot_token and chat_id:
        try:
            import urllib.request
            import json
            msg = "🚨 SECRETS WIPED - system halted"
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            data = json.dumps({'chat_id': chat_id, 'text': msg}).encode()
            urllib.request.urlopen(urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'}), timeout=10)
            print("✅ Telegram alert sent")
        except Exception as e:
            print(f"⚠️  Telegram alert failed: {e}")

    print("🚨 SECRETS WIPED — system halted")


if __name__ == '__main__':
    wipe()
