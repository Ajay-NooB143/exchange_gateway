"""
GitHub Signal Logger - OMNI BRAIN V2
=====================================
Pushes EXECUTE signals to GitHub for free public archive.

Repository Structure:
  signals/{YYYY-MM-DD}/{symbol}_{tf}_{HHmmss}.json

Content:
  Full signal JSON with score + components + market data

Commit Message:
  "signal: {symbol} {score} {decision} {time}"
"""

import os
import sys
import json
import base64
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from pathlib import Path

log = logging.getLogger('GitHubSignalLogger')

# Load .env file
def _load_env():
    """Load .env file from project root."""
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key.strip(), value.strip())

_load_env()


class GitHubSignalLogger:
    """
    Pushes EXECUTE signals to GitHub repository.
    
    Uses GitHub API with GITHUB_TOKEN for authentication.
    Creates public signal archive at:
      signals/{date}/{symbol}_{tf}_{time}.json
    """
    
    BASE_URL = 'https://api.github.com'
    
    def __init__(self):
        self.token = os.environ.get('GITHUB_TOKEN', '')
        self.repo = os.environ.get('GITHUB_REPO', '')  # format: username/repo
        self.enabled = bool(self.token and self.repo)
        
        if not self.enabled:
            log.warning("[GITHUB] Logging disabled. Set GITHUB_TOKEN and GITHUB_REPO in .env")
    
    def log_signal(self, signal_data: Dict[str, Any]) -> bool:
        """
        Log an EXECUTE signal to GitHub.
        
        Args:
            signal_data: Full signal dict with symbol, score, decision, etc.
        
        Returns:
            True if successful
        """
        if not self.enabled:
            return False
        
        decision = signal_data.get('decision', '')
        if decision != 'EXECUTE':
            return False
        
        try:
            symbol = signal_data.get('symbol', 'UNKNOWN')
            score = signal_data.get('score', 0)
            timeframe = signal_data.get('timeframe', 'H1')
            timestamp = signal_data.get('timestamp', datetime.now(timezone.utc).isoformat())
            
            # Create file path
            now = datetime.now(timezone.utc)
            date_str = now.strftime('%Y-%m-%d')
            time_str = now.strftime('%H%M%S')
            filename = f"signals/{date_str}/{symbol}_{timeframe}_{time_str}.json"
            
            # Build signal JSON
            signal_json = {
                'symbol': symbol,
                'timeframe': timeframe,
                'timestamp': timestamp,
                'decision': decision,
                'score': score,
                'components': signal_data.get('components', {}),
                'mtf_confirmed': signal_data.get('mtf_confirmed', False),
                'threshold_used': signal_data.get('threshold_used', 75),
                'circuit_breaker': signal_data.get('circuit_breaker', 'ACTIVE'),
                'provider': 'twelve_data'
            }
            
            # Commit message
            commit_message = f"signal: {symbol} {timeframe} score:{score} {decision} {now.strftime('%H:%M:%S')}"
            
            # Push to GitHub
            return self._push_file(filename, json.dumps(signal_json, indent=2), commit_message)
            
        except Exception as e:
            log.error(f"[GITHUB] Log error: {e}")
            return False
    
    def _push_file(self, filename: str, content: str, commit_message: str) -> bool:
        """Push a file to GitHub repository."""
        try:
            import urllib.request
            import urllib.error
            
            # Encode content
            content_bytes = content.encode('utf-8')
            content_b64 = base64.b64encode(content_bytes).decode('utf-8')
            
            # GitHub API URL
            url = f"{self.BASE_URL}/repos/{self.repo}/contents/{filename}"
            
            # Prepare request
            data = json.dumps({
                'message': commit_message,
                'content': content_b64
            }).encode('utf-8')
            
            headers = {
                'Authorization': f'token {self.token}',
                'Accept': 'application/vnd.github.v3+json',
                'User-Agent': 'OMNI-BRAIN-V2'
            }
            
            req = urllib.request.Request(url, data=data, headers=headers, method='PUT')
            
            response = urllib.request.urlopen(req, timeout=30)
            
            if response.status in (200, 201):
                log.info(f"[GITHUB] Pushed: {filename}")
                return True
            else:
                log.error(f"[GITHUB] API error: {response.status}")
                return False
                
        except urllib.error.HTTPError as e:
            if e.code == 422:
                log.warning(f"[GITHUB] File already exists: {filename}")
                return False
            log.error(f"[GITHUB] API error: {e.code}")
            return False
        except Exception as e:
            log.error(f"[GITHUB] Push error: {e}")
            return False
    
    def test_connection(self) -> Dict[str, Any]:
        """Test GitHub API connection."""
        if not self.enabled:
            return {
                'status': 'DISABLED',
                'message': 'Set GITHUB_TOKEN and GITHUB_REPO in .env'
            }
        
        try:
            import urllib.request
            
            url = f"{self.BASE_URL}/repos/{self.repo}"
            
            headers = {
                'Authorization': f'token {self.token}',
                'Accept': 'application/vnd.github.v3+json',
                'User-Agent': 'OMNI-BRAIN-V2'
            }
            
            req = urllib.request.Request(url, headers=headers)
            response = urllib.request.urlopen(req, timeout=10)
            
            data = json.loads(response.read().decode('utf-8'))
            
            return {
                'status': 'OK',
                'repo': data.get('full_name'),
                'private': data.get('private'),
                'stars': data.get('stargazers_count'),
                'url': data.get('html_url')
            }
            
        except Exception as e:
            return {
                'status': 'ERROR',
                'message': str(e)
            }


# Global instance
_github_logger: Optional[GitHubSignalLogger] = None


def get_github_logger() -> GitHubSignalLogger:
    """Get or create global GitHub logger instance."""
    global _github_logger
    if _github_logger is None:
        _github_logger = GitHubSignalLogger()
    return _github_logger


def log_to_github(signal_data: Dict[str, Any]) -> bool:
    """Convenience function to log signal to GitHub."""
    return get_github_logger().log_signal(signal_data)


# ══════════════════════════════════════════════════════════════════════════════
# CLI TEST
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import argparse
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )
    
    parser = argparse.ArgumentParser(description='GitHub Signal Logger')
    parser.add_argument('--test', action='store_true', help='Test connection')
    parser.add_argument('--demo', action='store_true', help='Push demo signal')
    args = parser.parse_args()
    
    logger = GitHubSignalLogger()
    
    if args.test:
        print("=" * 60)
        print("  GITHUB SIGNAL LOGGER - TEST")
        print("=" * 60)
        
        result = logger.test_connection()
        
        print(f"\nStatus: {result['status']}")
        if result['status'] == 'OK':
            print(f"Repo: {result['repo']}")
            print(f"Private: {result['private']}")
            print(f"Stars: {result['stars']}")
            print(f"URL: {result['url']}")
        else:
            print(f"Message: {result.get('message', 'Unknown error')}")
        
        print("\n" + "=" * 60)
    
    elif args.demo:
        print("=" * 60)
        print("  GITHUB SIGNAL LOGGER - DEMO")
        print("=" * 60)
        
        demo_signal = {
            'symbol': 'XAUUSD',
            'direction': 'LONG',
            'decision': 'EXECUTE',
            'score': 85,
            'timeframe': 'H1',
            'price': 2350.50,
            'components': {
                'OB': 20,
                'FVG': 20,
                'SWEEP': 30,
                'VWAP': 10,
                'SESSION': 5
            },
            'mtf_confirmed': True,
            'threshold_used': 75,
            'circuit_breaker': 'ACTIVE',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        print(f"\nDemo Signal:")
        print(json.dumps(demo_signal, indent=2))
        
        success = logger.log_signal(demo_signal)
        
        print(f"\nResult: {'SUCCESS' if success else 'FAILED/DISABLED'}")
        
        print("\n" + "=" * 60)
    
    else:
        parser.print_help()
