#!/usr/bin/env python3
"""
Get Chat ID Helper — OMNI BRAIN V2
====================================
Discover your Telegram chat ID by calling getUpdates.

Usage:
  python3 scripts/get_chat_id.py

Steps:
  1. Message your bot on Telegram first (/start)
  2. Run this script
  3. Copy the printed chat ID into your .env
"""
import os
import sys
import json
import urllib.request
import urllib.parse
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────────
ENV_PATH = Path(__file__).parent.parent / '.env'
BOT_USERNAME = 'omnibrainsignals_free'

# ── helpers ─────────────────────────────────────────────────────────────

def read_token() -> str:
    """Read TELEGRAM_BOT_TOKEN from .env or environment."""
    token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
    if token:
        return token
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            if line.startswith('TELEGRAM_BOT_TOKEN='):
                return line.split('=', 1)[1].strip()
    return ''


def fetch_updates(token: str) -> list:
    """Call getUpdates and return result list."""
    url = f"https://api.telegram.org/bot{token}/getUpdates?timeout=2"
    req = urllib.request.Request(url)
    try:
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read().decode())
        if data.get('ok'):
            return data.get('result', [])
        print(f"  API error: {data.get('description', 'unknown')}")
        return []
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:100]
        if '409' in str(e.code):
            print("  ⚠ Conflict: Another bot poller is active.")
            print("  Stop the telegram service first:")
            print("    pm2 stop omni-brain-telegram")
            print("  Then retry.")
        else:
            print(f"  HTTP {e.code}: {body}")
        return []
    except urllib.error.URLError as e:
        print(f"  ⚠ Cannot reach Telegram API (network issue): {e.reason}")
        print("  This is expected if this sandbox has no internet.")
        print("  Run this script directly on your VPS instead.")
        return []
    except Exception as e:
        print(f"  Error: {e}")
        return []


def extract_chat_ids(updates: list) -> list:
    """Extract unique chat IDs from updates."""
    found = []
    seen = set()
    for update in updates:
        msg = (update.get('message') or
               update.get('callback_query', {}).get('message') or
               update.get('edited_message') or
               {})
        chat = msg.get('chat', {})
        cid = chat.get('id')
        username = chat.get('username', '?')
        first_name = chat.get('first_name', '?')
        if cid and cid not in seen:
            seen.add(cid)
            found.append({
                'chat_id': str(cid),
                'username': username,
                'first_name': first_name,
                'type': chat.get('type', '?')
            })
    return found


def update_env(chat_id: str) -> bool:
    """Write chat_id into .env."""
    if not ENV_PATH.exists():
        print(f"  .env not found at {ENV_PATH}")
        return False
    
    content = ENV_PATH.read_text()
    if 'TELEGRAM_CHAT_ID=' in content:
        import re
        content = re.sub(r'TELEGRAM_CHAT_ID=.*', f'TELEGRAM_CHAT_ID={chat_id}', content)
    else:
        content += f'\nTELEGRAM_CHAT_ID={chat_id}\n'
    ENV_PATH.write_text(content)
    return True


# ── main ────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  TELEGRAM CHAT ID DISCOVERY")
    print("=" * 60)
    print()
    
    token = read_token()
    if not token:
        print("  ❌ No TELEGRAM_BOT_TOKEN found in .env or environment.")
        print()
        print("  Add it to .env:")
        print("    TELEGRAM_BOT_TOKEN=your_bot_token_here")
        sys.exit(1)
    
    print(f"  Bot token: {token[:10]}...{token[-4:]}")
    print()
    print(f"  Step 1: Open Telegram and send /start to @{BOT_USERNAME}")
    print(f"  Step 2: Run this script again")
    print()
    
    print("  Fetching updates from Telegram...")
    updates = fetch_updates(token)
    
    if not updates:
        print()
        print("  ⚠ No updates found.")
        print(f"  Make sure you sent /start to @{BOT_USERNAME} first.")
        print()
        print("  Then run:")
        print(f"    python3 scripts/get_chat_id.py")
        sys.exit(1)
    
    chats = extract_chat_ids(updates)
    
    if not chats:
        print()
        print("  ⚠ No chat IDs found in updates.")
        print("  Send a message to the bot first, then retry.")
        sys.exit(1)
    
    print()
    print(f"  Found {len(chats)} chat(s):")
    print()
    for i, chat in enumerate(chats, 1):
        print(f"  [{i}] Chat ID: {chat['chat_id']}")
        print(f"      Name: {chat['first_name']} (@{chat['username']})")
        print(f"      Type: {chat['type']}")
        print()
    
    # Auto-select first one
    selected = chats[0]['chat_id']
    print(f"  Recommended: TELEGRAM_CHAT_ID={selected}")
    
    ok = update_env(selected)
    if ok:
        print(f"  ✅ Updated .env with TELEGRAM_CHAT_ID={selected}")
    else:
        print(f"  ⚠ Could not update .env — add this to your .env manually:")
        print(f"    TELEGRAM_CHAT_ID={selected}")
    
    print()
    print("  Next step: Restart services:")
    print("    pm2 restart all --update-env")
    print()
    print("=" * 60)


if __name__ == '__main__':
    main()
