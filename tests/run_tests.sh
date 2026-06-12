#!/bin/bash
# OMNI BRAIN V2 - Test Runner
# Usage: ./tests/run_tests.sh [args]
set -e
cd "$(dirname "$0")/.."
exec python3 -m pytest tests/ -v "$@"
