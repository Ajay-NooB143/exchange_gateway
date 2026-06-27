#!/bin/bash
set -e

VPS_IP="${VPS_IP:?VPS_IP is required}"
VPS_PATH="${VPS_PATH:-/opt/trading-bridge}"
LOCAL_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "⚡ QUICK SYNC - OMNI BRAIN V2"
echo "=============================="

rsync -avz --delete --progress \
    --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.venv' \
    --exclude='venv' \
    --exclude='node_modules' \
    --exclude='logs/' \
    --exclude='data/csv/' \
    "${LOCAL_PATH}/" "root@${VPS_IP}:${VPS_PATH}/"

ssh "root@${VPS_IP}" "cd ${VPS_PATH} && pm2 reload ecosystem.config.js && pm2 save"

echo "✓ Quick sync complete"
