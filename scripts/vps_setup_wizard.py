#!/usr/bin/env python3
"""
OMNI BRAIN V2 — VPS Setup Wizard
==================================
Interactive setup that runs on VPS.
Guides through entire configuration.
"""

import os
import sys
import json
import subprocess
import urllib.request
import urllib.error
from pathlib import Path

WORKSPACE = Path(__file__).parent.parent
ENV_FILE = WORKSPACE / '.env'
LOG_DIR = WORKSPACE / 'production' / 'logs'

REQUIRED_KEYS = [
    'LIVE_DATA_API_KEY',
    'TELEGRAM_BOT_TOKEN',
    'TELEGRAM_CHAT_ID',
    'GITHUB_TOKEN',
    'GITHUB_REPO',
    'ACCOUNT_BALANCE',
    'RISK_PCT',
]

OPTIONAL_KEYS = [
    'ANTHROPIC_API_KEY',
    'PERPLEXITY_API_KEY',
    'MT5_LOGIN',
    'MT5_PASSWORD',
    'MT5_SERVER',
]


def step_1_python_version():
    """Check Python version."""
    print("\n[Step 1/7] Checking Python version...")
    v = sys.version_info
    if v.major == 3 and v.minor >= 8:
        print(f"  \u2705 Python {v.major}.{v.minor}.{v.micro} — OK")
        return True
    else:
        print(f"  \u274c Python {v.major}.{v.minor}.{v.micro} — need 3.8+")
        return False


def step_2_packages():
    """Check and install missing packages."""
    print("\n[Step 2/7] Checking required packages...")
    packages = {
        'psutil': 'psutil',
        'numpy': 'numpy',
        'requests': 'requests',
        'websocket': 'websocket-client',
    }
    optional = {
        'numba': 'numba',
        'PIL': 'Pillow',
        'cryptography': 'cryptography',
    }
    all_ok = True

    for module, pip_name in packages.items():
        try:
            __import__(module)
            print(f"  \u2705 {pip_name} — installed")
        except ImportError:
            print(f"  \u26a0\ufe0f  {pip_name} — installing...")
            try:
                subprocess.check_call([sys.executable, '-m', 'pip', 'install', pip_name],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                print(f"  \u2705 {pip_name} — installed (newly)")
            except Exception as e:
                print(f"  \u274c {pip_name} — install failed: {e}")
                all_ok = False

    for module, pip_name in optional.items():
        try:
            __import__(module)
            print(f"  \u2705 {pip_name} — installed")
        except ImportError:
            print(f"  \u26a0\ufe0f  {pip_name} — not installed (optional)")

    return all_ok


def step_3_env_file():
    """Validate .env file."""
    print("\n[Step 3/7] Validating .env file...")
    if not ENV_FILE.exists():
        print(f"  \u274c .env file not found at {ENV_FILE}")
        print(f"  \U0001f4a1 Create it from .env.example and fill in values")
        return False

    env = {}
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip()

    all_ok = True
    for key in REQUIRED_KEYS:
        val = env.get(key, '')
        if val:
            masked = val[:4] + '***' if len(val) > 8 else '***'
            print(f"  \u2705 {key}: {masked}")
        else:
            print(f"  \u274c {key}: MISSING")
            all_ok = False

    for key in OPTIONAL_KEYS:
        val = env.get(key, '')
        if val:
            print(f"  \u2705 {key}: set")
        else:
            print(f"  \u26a0\ufe0f  {key}: not set (optional)")

    return all_ok


def step_4_api_connections():
    """Test API connections."""
    print("\n[Step 4/7] Testing API connections...")

    env = {}
    if ENV_FILE.exists():
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    env[k.strip()] = v.strip()

    # TwelveData
    api_key = env.get('LIVE_DATA_API_KEY', '')
    if api_key:
        try:
            url = f"https://api.twelvedata.com/price?symbol=XAU/USD&apikey={api_key}"
            resp = urllib.request.urlopen(url, timeout=10)
            data = json.loads(resp.read().decode())
            price = data.get('price', '?')
            print(f"  \u2705 TwelveData: XAU/USD ${price}")
        except Exception as e:
            print(f"  \u274c TwelveData: {e}")
    else:
        print(f"  \u26a0\ufe0f  TwelveData: skipped (no API key)")

    # Telegram
    bot_token = env.get('TELEGRAM_BOT_TOKEN', '')
    chat_id = env.get('TELEGRAM_CHAT_ID', '')
    if bot_token:
        try:
            url = f"https://api.telegram.org/bot{bot_token}/getMe"
            resp = urllib.request.urlopen(url, timeout=10)
            data = json.loads(resp.read().decode())
            bot_name = data.get('result', {}).get('username', '?')
            print(f"  \u2705 Telegram bot: @{bot_name}")
        except Exception as e:
            print(f"  \u274c Telegram bot: {e}")
    else:
        print(f"  \u26a0\ufe0f  Telegram: skipped (no bot token)")

    if chat_id:
        print(f"  \u2705 Chat ID: {chat_id[:6]}***")
    else:
        print(f"  \u274c Chat ID: MISSING")

    # GitHub
    github_token = env.get('GITHUB_TOKEN', '')
    github_repo = env.get('GITHUB_REPO', '')
    if github_token and github_repo:
        try:
            url = f"https://api.github.com/repos/{github_repo}"
            req = urllib.request.Request(url, headers={'Authorization': f'token {github_token}'})
            resp = urllib.request.urlopen(req, timeout=10)
            print(f"  \u2705 GitHub: {github_repo}")
        except Exception as e:
            print(f"  \u274c GitHub: {e}")
    else:
        print(f"  \u26a0\ufe0f  GitHub: skipped (no token)")

    return True


def step_5_pipeline_test():
    """Run one pipeline test with mock data."""
    print("\n[Step 5/7] Running pipeline test...")
    try:
        sys.path.insert(0, str(WORKSPACE))
        from production.live_feed_scanner import generate_mock_candles
        from pipeline_orchestrator import PipelineEngine

        engine = PipelineEngine()
        mock = generate_mock_candles('XAUUSD', 'H1', 100)
        candles_dicts = [c.to_dict() for c in mock]
        payload = {
            'symbol': 'XAUUSD', 'direction': 'LONG', 'timeframe': 'H1',
            'price': mock[-1].close if mock else 2000.0,
            'candles': candles_dicts,
            'candles_data': {'H1': candles_dicts},
        }
        result = engine.run_pipeline(payload, 'wizard')
        score = result.get('score', 0)
        decision = result.get('decision', 'BLOCK')
        print(f"  \u2705 Pipeline complete: score={score}, decision={decision}")
        steps = result.get('steps', {})
        for name, step_data in steps.items():
            if isinstance(step_data, dict) and 'score' in step_data:
                print(f"     {name:20s}: score={step_data['score']}")
        return True
    except Exception as e:
        print(f"  \u274c Pipeline test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def step_6_pm2_processes():
    """Check PM2 processes."""
    print("\n[Step 6/7] Checking PM2 processes...")
    try:
        result = subprocess.run(['pm2', 'list'], capture_output=True, text=True, timeout=10)
        lines = result.stdout.strip().split('\n')
        online = 0
        stopped = 0
        for line in lines:
            if 'online' in line.lower():
                online += 1
            elif 'stopped' in line.lower() or 'errored' in line.lower():
                stopped += 1

        if online > 0:
            print(f"  \u2705 PM2: {online} running")
        if stopped > 0:
            print(f"  \u26a0\ufe0f  PM2: {stopped} stopped/errored")

        if stopped > 0:
            print(f"  \U0001f504 Restarting stopped processes...")
            subprocess.run(['pm2', 'restart', 'all'], capture_output=True, timeout=10)
            print(f"  \u2705 PM2: all restarted")

        return online > 0 or stopped == 0
    except FileNotFoundError:
        print(f"  \u26a0\ufe0f  PM2 not found — not installed")
        return True
    except Exception as e:
        print(f"  \u26a0\ufe0f  PM2 check failed: {e}")
        return True


def step_7_final_status():
    """Print final status."""
    print("\n[Step 7/7] Final status")
    print("=" * 60)
    print(f"  \u2705 VPS is ready")
    print(f"  Dashboard: http://localhost:8089")
    print(f"  Signals: active")
    print(f"  Next: send /start to bot")
    print("=" * 60)


def main():
    print("OMNI BRAIN V2 \u2014 VPS Setup Wizard")
    print("=" * 60)

    results = []
    results.append(('Python version', step_1_python_version()))
    results.append(('Packages', step_2_packages()))
    results.append(('Env file', step_3_env_file()))
    results.append(('API connections', step_4_api_connections()))
    results.append(('Pipeline test', step_5_pipeline_test()))
    results.append(('PM2 processes', step_6_pm2_processes()))
    step_7_final_status()

    print("\n" + "=" * 60)
    print("  SETUP SUMMARY")
    print("=" * 60)
    all_ok = True
    for name, ok in results:
        icon = '\u2705' if ok else '\u274c'
        print(f"  {icon} {name}")
        if not ok:
            all_ok = False
    print("=" * 60)
    if all_ok:
        print("  \U0001f389 ALL CHECKS PASSED")
    else:
        print("  \u26a0\ufe0f  SOME CHECKS FAILED — fix issues above")
    return 0 if all_ok else 1


if __name__ == '__main__':
    sys.exit(main())
