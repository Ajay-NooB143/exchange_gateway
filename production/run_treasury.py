#!/usr/bin/env python3
"""PM2 wrapper for Treasury Monitor."""
import time, sys, logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
sys.path.insert(0, '/home/userland/api_workspace/production')
from treasury_monitor import get_treasury_monitor
tm = get_treasury_monitor()
print('Treasury Monitor active')
while True:
    tm.fetch_yields()
    time.sleep(900)
