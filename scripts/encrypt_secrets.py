"""Encrypt .env file using Fernet symmetric encryption."""
import os
import sys
from pathlib import Path

try:
    from cryptography.fernet import Fernet
except ImportError:
    os.system(f"{sys.executable} -m pip install cryptography")
    from cryptography.fernet import Fernet

BASE_DIR = Path(__file__).parent.parent
ENV_FILE = BASE_DIR / '.env'
KEY_FILE = BASE_DIR / '.secrets.key'
ENCRYPTED_FILE = BASE_DIR / '.env.encrypted'


def encrypt():
    if not ENV_FILE.exists():
        print(f"❌ {ENV_FILE} not found")
        sys.exit(1)

    key = Fernet.generate_key()
    cipher = Fernet(key)

    env_data = ENV_FILE.read_bytes()
    encrypted = cipher.encrypt(env_data)

    KEY_FILE.write_bytes(key)
    KEY_FILE.chmod(0o600)
    ENCRYPTED_FILE.write_bytes(encrypted)

    print(f"✅ Encrypted: {ENV_FILE} → {ENCRYPTED_FILE}")
    print(f"✅ Key saved: {KEY_FILE} (chmod 600)")
    print("⚠️  Delete .env only after verifying decryption works at startup")


if __name__ == '__main__':
    encrypt()
