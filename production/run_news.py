#!/usr/bin/env python3
"""PM2 wrapper for Forex Factory News Monitor."""
import time, sys, logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
sys.path.insert(0, '/home/userland/api_workspace/production')
from forex_factory_news import get_forex_factory_news
fn = get_forex_factory_news()
print('News Monitor active')
while True:
    fn.fetch_calendar(force=True)
    time.sleep(1800)
