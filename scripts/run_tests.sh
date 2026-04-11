#!/usr/bin/env bash
# Run function tests (used by pre-commit and manually).
# Exit non-zero if any test fails so commits are blocked when used as a hook.
set -e
cd "$(dirname "$0")/.."
python3 -m unittest discover -s tests -p "test_*.py" -v
