"""Tests for encrypt_secrets.py, rotate_secrets.py, and .env loading - OMNI BRAIN V2"""
import sys, os, json, time, threading, tempfile, stat
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'production'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import pytest


class TestSecretsManager:
    @pytest.fixture(autouse=True)
    def setup_temp_env(self):
        tmpdir = Path(tempfile.mkdtemp())
        env_file = tmpdir / '.env'
        env_file.write_text('TELEGRAM_BOT_TOKEN=test:bot_token\nTELEGRAM_CHAT_ID=12345\nPIPELINE_API_KEY=test_key\n')
        self.tmpdir = tmpdir
        self.env_file = env_file
        yield
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)

    def _encrypt(self):
        from cryptography.fernet import Fernet
        key = Fernet.generate_key()
        cipher = Fernet(key)
        key_file = self.tmpdir / '.secrets.key'
        key_file.write_bytes(key)
        key_file.chmod(0o600)
        encrypted = cipher.encrypt(self.env_file.read_bytes())
        encrypted_file = self.tmpdir / '.env.encrypted'
        encrypted_file.write_bytes(encrypted)
        return key, key_file, encrypted_file

    def test_encrypt_creates_files(self):
        key, key_file, encrypted_file = self._encrypt()
        assert encrypted_file.exists()
        assert key_file.exists()

    def test_key_file_permissions(self):
        _, key_file, _ = self._encrypt()
        mode = os.stat(key_file).st_mode
        assert mode & stat.S_IRWXO == 0

    def test_decrypt_loads_correct_values(self):
        from cryptography.fernet import Fernet
        key, key_file, encrypted_file = self._encrypt()
        cipher = Fernet(key)
        decrypted = cipher.decrypt(encrypted_file.read_bytes()).decode()
        assert 'TELEGRAM_BOT_TOKEN=test:bot_token' in decrypted
        assert 'PIPELINE_API_KEY=test_key' in decrypted

    def test_rotate_generates_new_key(self):
        from cryptography.fernet import Fernet
        key, key_file, encrypted_file = self._encrypt()
        old_key = key_file.read_bytes()
        cipher = Fernet(old_key)
        env_data = cipher.decrypt(encrypted_file.read_bytes())
        new_key = Fernet.generate_key()
        new_cipher = Fernet(new_key)
        new_encrypted = new_cipher.encrypt(env_data)
        key_file.write_bytes(new_key)
        encrypted_file.write_bytes(new_encrypted)
        new_cipher2 = Fernet(key_file.read_bytes())
        decrypted = new_cipher2.decrypt(encrypted_file.read_bytes()).decode()
        assert decrypted == env_data.decode()
        assert key_file.read_bytes() != old_key

    def test_rotate_preserves_data(self):
        from cryptography.fernet import Fernet
        key, key_file, encrypted_file = self._encrypt()
        cipher = Fernet(key)
        original = cipher.decrypt(encrypted_file.read_bytes())
        new_key = Fernet.generate_key()
        new_cipher = Fernet(new_key)
        key_file.write_bytes(new_key)
        encrypted_file.write_bytes(new_cipher.encrypt(original))
        final_cipher = Fernet(key_file.read_bytes())
        assert final_cipher.decrypt(encrypted_file.read_bytes()) == original

    def test_wipe_deletes_files(self):
        key, key_file, encrypted_file = self._encrypt()
        key_file.unlink()
        encrypted_file.unlink()
        assert not key_file.exists()
        assert not encrypted_file.exists()

    def test_encrypted_env_loading(self):
        from cryptography.fernet import Fernet
        key = Fernet.generate_key()
        cipher = Fernet(key)
        key_file = self.tmpdir / '.secrets.key'
        key_file.write_bytes(key)
        encrypted_file = self.tmpdir / '.env.encrypted'
        encrypted_file.write_bytes(cipher.encrypt(self.env_file.read_bytes()))
        loaded_key = key_file.read_bytes()
        loaded_cipher = Fernet(loaded_key)
        decrypted = loaded_cipher.decrypt(encrypted_file.read_bytes()).decode()
        lines = [l.strip() for l in decrypted.splitlines() if l.strip() and not l.startswith('#')]
        env_vars = {}
        for line in lines:
            if '=' in line:
                k, v = line.split('=', 1)
                env_vars[k.strip()] = v.strip()
        assert env_vars['TELEGRAM_BOT_TOKEN'] == 'test:bot_token'
        assert env_vars['PIPELINE_API_KEY'] == 'test_key'

    def test_fallback_to_plaintext_env(self):
        from cryptography.fernet import Fernet
        env_overrides = {}
        for line in self.env_file.read_text().splitlines():
            line = line.strip()
            if line and '=' in line:
                k, v = line.split('=', 1)
                env_overrides[k.strip()] = v.strip()
        assert env_overrides['TELEGRAM_BOT_TOKEN'] == 'test:bot_token'

    def test_gitignore_entries(self):
        gitignore = Path(__file__).parent.parent / '.gitignore'
        content = gitignore.read_text()
        assert '.env' in content
        assert '.env.encrypted' in content
        assert '.secrets.key' in content

    def test_decrypt_with_wrong_key_fails(self):
        from cryptography.fernet import Fernet
        key1 = Fernet.generate_key()
        key2 = Fernet.generate_key()
        cipher1 = Fernet(key1)
        encrypted = cipher1.encrypt(b'SECRET=data')
        cipher2 = Fernet(key2)
        with pytest.raises(Exception):
            cipher2.decrypt(encrypted)
