#!/usr/bin/env python3
"""
Poll the 4 playdate threads (Val, Rebecca, Meghan, Sherri) for replies and notify.
Uses the same contact list as send_playdate_batch.py. Run on a schedule (cron) or via watch_chat_db_and_poll.

Usage:
  uv run python scripts/poll_playdate_replies.py [--hours 24] [--notify-to PHONE]
  Set PLAYDATE_NOTIFY_TO (your phone) to get an iMessage when there are replies to approve.

Cron example (every 10 min):
  */10 * * * * PLAYDATE_NOTIFY_TO=1234567890 cd /path/to/mac_messages_mcp && uv run python scripts/poll_playdate_replies.py --hours 48 >> /tmp/playdate_poll.log 2>&1
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

# Project root
ROOT = os.path.join(os.path.dirname(__file__), "..")
CONFIG_PATH = os.path.join(ROOT, "data", "playdate_batch_sent.json")
POLL_SCRIPT = os.path.join(os.path.dirname(__file__), "poll_replies.py")


def get_playdate_phones_and_names() -> tuple[list[str], list[str]]:
    """Read phones and names from last sent batch, or fallback to default list."""
    if os.path.isfile(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                data = json.load(f)
            threads = data.get("threads", [])
            if threads:
                phones = [t["phone"] for t in threads]
                names = [t["name"] for t in threads]
                return phones, names
        except Exception:
            pass
    # Fallback
    return (
        ["16463440188", "18454176830", "6462627070", "17208380896"],
        ["Val (Keevy)", "Rebecca (Eliza)", "Meghan (Violet)", "Sherri (Taylor)"],
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Poll playdate threads and optionally notify.")
    ap.add_argument("--hours", type=int, default=48, help="Hours of messages to look back")
    ap.add_argument("--notify-to", default="", help="Phone to receive reply summary (or set PLAYDATE_NOTIFY_TO)")
    ap.add_argument("--no-since-today", action="store_true", help="Use --hours instead of since 6 AM today")
    ap.add_argument("--csv", default="", help="Append results to CSV")
    args = ap.parse_args()

    notify_to = args.notify_to or os.environ.get("PLAYDATE_NOTIFY_TO", "").strip()
    phones, names = get_playdate_phones_and_names()

    cmd = [
        sys.executable,
        POLL_SCRIPT,
        "--no-since-today",
        "--hours", str(args.hours),
        "--phones", ",".join(phones),
        "--names", ",".join(names),
        "--sent", "4",  # headcount: 4 playdate threads
    ]
    if args.csv:
        cmd += ["--csv", args.csv]
    if notify_to:
        cmd += ["--notify", "--notify-to", notify_to]

    subprocess.run(cmd, cwd=ROOT)


if __name__ == "__main__":
    main()
