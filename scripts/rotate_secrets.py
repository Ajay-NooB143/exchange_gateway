"""Rotate encryption key and re-encrypt secrets."""
import os
import sys
from pathlib import Path

try:
    from cryptography.fernet import Fernet
except ImportError:
    os.system(f"{sys.executable} -m pip install cryptography")
    from cryptography.fernet import Fernet

BASE_DIR = Path(__file__).parent.parent
KEY_FILE = BASE_DIR / '.secrets.key'
ENCRYPTED_FILE = BASE_DIR / '.env.encrypted'


def rotate():
    if not ENCRYPTED_FILE.exists():
        print(f"❌ {ENCRYPTED_FILE} not found. Run encrypt_secrets.py first")
        sys.exit(1)

    if not KEY_FILE.exists():
        print(f"❌ {KEY_FILE} not found")
        sys.exit(1)

    old_key = KEY_FILE.read_bytes()
    old_cipher = Fernet(old_key)
    env_data = old_cipher.decrypt(ENCRYPTED_FILE.read_bytes())

    new_key = Fernet.generate_key()
    new_cipher = Fernet(new_key)
    encrypted = new_cipher.encrypt(env_data)

    KEY_FILE.write_bytes(new_key)
    KEY_FILE.chmod(0o600)
    ENCRYPTED_FILE.write_bytes(encrypted)

    bot_token = None
    chat_id = None
    for line in env_data.decode().splitlines():
        if line.startswith('TELEGRAM_BOT_TOKEN='):
            bot_token = line.split('=', 1)[1].strip()
        elif line.startswith('TELEGRAM_CHAT_ID='):
            chat_id = line.split('=', 1)[1].strip()

    if bot_token and chat_id:
        try:
            import urllib.request
            import json
            msg = f"🔑 Secrets rotated: new key generated at {__import__('datetime').datetime.now().isoformat()}"
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            data = json.dumps({'chat_id': chat_id, 'text': msg}).encode()
            urllib.request.urlopen(urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'}), timeout=10)
            print("✅ Telegram alert sent")
        except Exception as e:
            print(f"⚠️  Telegram alert failed: {e}")

    print(f"✅ Secrets rotated — new key saved to {KEY_FILE}")


if __name__ == '__main__':
    rotate()
