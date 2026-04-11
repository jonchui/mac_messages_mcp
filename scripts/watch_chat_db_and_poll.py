#!/usr/bin/env python3
"""
Watch ~/Library/Messages/chat.db for changes (local "webhook").
When the file mtime changes, run the poll script so you react to new replies
instead of polling on a fixed interval.

Usage:
  uv run python scripts/watch_chat_db_and_poll.py --phones 7143767892,... [--names ...] [--sent 12]
  Optional: --interval 15  (seconds between checks, default 15)
             --debounce 60 (min seconds between runs when DB changes, default 60)
             --csv headcount.csv

Run in background (e.g. in a terminal or via launchd). Requires Full Disk Access.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

# Add project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def get_chat_db_path() -> str:
    return os.path.join(os.path.expanduser("~"), "Library", "Messages", "chat.db")


def main() -> None:
    ap = argparse.ArgumentParser(description="Watch chat.db and run poll when it changes.")
    ap.add_argument("--phones", required=True, help="Comma-separated phone numbers")
    ap.add_argument("--names", default="", help="Comma-separated names (same order as phones)")
    ap.add_argument("--sent", type=int, default=None, help="Total messages sent (for headcount)")
    ap.add_argument("--csv", default="", help="Pass through to poll_replies.py --csv")
    ap.add_argument("--interval", type=int, default=15, help="Seconds between file checks")
    ap.add_argument("--debounce", type=int, default=60, help="Min seconds between poll runs when DB changes")
    args = ap.parse_args()

    db_path = get_chat_db_path()
    if not os.path.isfile(db_path):
        print(f"chat.db not found at {db_path}. Full Disk Access required.", file=sys.stderr)
        sys.exit(1)

    poll_script = os.path.join(os.path.dirname(__file__), "poll_replies.py")
    cmd = [
        sys.executable,
        poll_script,
        "--phones", args.phones,
    ]
    if args.names:
        cmd += ["--names", args.names]
    if args.sent is not None:
        cmd += ["--sent", str(args.sent)]
    if args.csv:
        cmd += ["--csv", args.csv]

    last_mtime: float | None = None
    last_run_time: float = 0

    print(f"Watching {db_path} every {args.interval}s (debounce {args.debounce}s). Ctrl+C to stop.", file=sys.stderr)
    while True:
        try:
            mtime = os.path.getmtime(db_path)
            now = time.time()
            if last_mtime is not None and mtime != last_mtime:
                if now - last_run_time >= args.debounce:
                    print(f"\n[chat.db changed] Running poll...", file=sys.stderr)
                    subprocess.run(cmd, cwd=os.path.dirname(os.path.dirname(poll_script)))
                    last_run_time = now
            last_mtime = mtime
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Watch error: {e}", file=sys.stderr)
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
