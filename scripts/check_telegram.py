#!/usr/bin/env python3
"""
Telegram Bot Diagnostic Script - OMNI BRAIN V2
===============================================
Test Telegram bot connectivity and send a test message.

Usage:
  python3 scripts/check_telegram.py
"""

import os
import sys
import json
import urllib.request
import urllib.error
from pathlib import Path

# Load .env
ENV_PATH = Path(__file__).parent.parent / '.env'
if ENV_PATH.exists():
    with open(ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())


def test_bot_info(token):
    """Test 1: Get bot info."""
    print("\n[Test 1] Bot Info")
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        resp = urllib.request.urlopen(url, timeout=10)
        data = json.loads(resp.read().decode())
        if data.get('ok'):
            bot = data['result']
            print(f"  Bot name: @{bot.get('username', 'unknown')}")
            print(f"  Bot ID: {bot.get('id')}")
            print(f"  Can join groups: {bot.get('can_join_groups', False)}")
            return True
        else:
            print(f"  Error: {data.get('description', 'unknown')}")
            return False
    except Exception as e:
        print(f"  Failed: {e}")
        return False


def test_send_message(token, chat_id):
    """Test 2: Send a test message."""
    print("\n[Test 2] Send Test Message")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        'chat_id': int(chat_id),
        'text': 'Test message from OMNI BRAIN V2',
        'parse_mode': 'HTML'
    }).encode()
    req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read().decode())
        if data.get('ok'):
            print(f"  Message sent successfully!")
            return True
        else:
            print(f"  Error: {data.get('description', 'unknown')}")
            return False
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"  HTTP {e.code}: {body[:200]}")
        if e.code == 400:
            print("  Send /start to bot first!")
        elif e.code == 403:
            print("  Bot blocked by user or chat_id invalid")
        return False
    except Exception as e:
        print(f"  Failed: {e}")
        return False


def get_updates(token):
    """Test 3: Get recent updates."""
    print("\n[Test 3] Get Updates")
    url = f"https://api.telegram.org/bot{token}/getUpdates?timeout=2"
    try:
        resp = urllib.request.urlopen(url, timeout=10)
        data = json.loads(resp.read().decode())
        if data.get('ok'):
            updates = data.get('result', [])
            print(f"  Found {len(updates)} update(s)")
            if updates:
                for u in updates[:3]:
                    msg = u.get('message', {})
                    text = msg.get('text', '')
                    chat = msg.get('chat', {})
                    print(f"    - Chat {chat.get('id')}: {text[:50]}")
            return True
        else:
            print(f"  Error: {data.get('description', 'unknown')}")
            return False
    except Exception as e:
        print(f"  Failed: {e}")
        return False


def main():
    print("=" * 60)
    print("  TELEGRAM BOT DIAGNOSTIC - OMNI BRAIN V2")
    print("=" * 60)

    token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID', '')

    if not token:
        print("\n  No TELEGRAM_BOT_TOKEN found in .env")
        sys.exit(1)

    print(f"\n  Bot token: {token[:10]}...{token[-4:]}")
    print(f"  Chat ID: {chat_id if chat_id else 'NOT SET'}")

    results = []
    results.append(('Bot Info', test_bot_info(token)))

    if chat_id:
        results.append(('Send Message', test_send_message(token, chat_id)))
        results.append(('Get Updates', get_updates(token)))
    else:
        print("\n  No chat_id set. Run: python3 scripts/get_chat_id.py")

    print("\n" + "=" * 60)
    print("  RESULTS")
    print("=" * 60)
    for name, ok in results:
        icon = 'OK' if ok else 'FAIL'
        print(f"  [{icon}] {name}")
    print("=" * 60)


if __name__ == '__main__':
    main()
