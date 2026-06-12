#!/usr/bin/env python3
"""PM2 wrapper for Daily Report scheduler."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from daily_report import DailyReport
dr = DailyReport()
print('Report scheduler active')
while True:
    now = time.localtime()
    if now.tm_hour == 23 and now.tm_min == 59:
        dr.generate_report()
        time.sleep(120)
    time.sleep(30)
