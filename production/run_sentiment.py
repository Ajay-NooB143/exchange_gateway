#!/usr/bin/env python3
"""PM2 wrapper for Sentiment Engine."""
import time, sys, logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
sys.path.insert(0, '/home/userland/api_workspace/production')
from sentiment_engine import get_sentiment_engine
se = get_sentiment_engine()
print('Sentiment Engine active')
while True:
    se.fetch_fear_greed()
    time.sleep(3600)
