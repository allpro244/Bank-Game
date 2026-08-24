#!/usr/bin/env python3
"""Start the Bank Game. No dependencies needed beyond Python 3.10+.

    python3 run.py            # starts server on port 8321 and opens browser
    python3 run.py --port 9000
    python3 run.py --no-browser
"""

import sys

if sys.version_info < (3, 10):
    sys.exit("This game needs Python 3.10 or newer. You have %d.%d."
             % sys.version_info[:2])

import argparse
from bankgame.server import main

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8321)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    main(port=args.port, open_browser=not args.no_browser)
