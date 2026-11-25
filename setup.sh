#!/bin/bash
# Set up your own journal library. See README.md.
cd "$(dirname "$0")" && exec /usr/bin/python3 scripts/setup.py "$@"
