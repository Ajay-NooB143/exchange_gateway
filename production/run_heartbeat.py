#!/usr/bin/env python3
"""PM2 wrapper for Health Heartbeat."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from health_heartbeat import HealthHeartbeat
h = HealthHeartbeat()
print('Heartbeat active')
while True:
    h.send_heartbeat()
    time.sleep(300)
