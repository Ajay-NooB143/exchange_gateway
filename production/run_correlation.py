#!/usr/bin/env python3
"""PM2 wrapper for Correlation Engine."""
import time, sys, logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
sys.path.insert(0, '/home/userland/api_workspace/production')
from correlation_engine import get_correlation_engine
ce = get_correlation_engine()
print('Correlation Engine active')
while True:
    time.sleep(60)
