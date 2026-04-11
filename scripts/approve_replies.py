#!/usr/bin/env python3
"""
Process approval replies from your phone (mobile-friendly).

After poll_replies.py --notify --notify-to <your_phone>, you get an iMessage
with pending replies. You reply with e.g. Y1 N2 Y3 (Y=send, N=skip).
This script reads that reply, sends the approved messages, and updates the CSV.

Usage:
  uv run python scripts/approve_replies.py --from 7143767892 [--csv data/rsvp_headcount.csv] [--batch data/approval_batch.json]

Run manually after you've replied, or on a schedule (e.g. every 2 min) so approvals are processed quickly.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mac_messages_mcp.messages import get_recent_messages, send_message


def _parse_last_reply_from_them(formatted_log: str, my_label: str = "You") -> str | None:
    """Return last message body that is NOT from me."""
    if not formatted_log or "Error" in formatted_log or "No " in formatted_log:
        return None
    lines = [ln.strip() for ln in formatted_log.split("\n") if ln.strip()]
    last_from_them = None
    for line in lines:
        if line.startswith("["):
            rest = line.split("]", 1)[-1].strip()
            if rest.startswith(my_label + ":"):
                continue
            if ": " in rest:
                _, body = rest.split(": ", 1)
                last_from_them = body
    return last_from_them


def parse_approval_reply(text: str) -> dict[int, bool]:
    """Parse e.g. 'Y1 N2 Y3' or '1 0 1' into {1: True, 2: False, 3: True}. Keys are 1-based indices."""
    if not text:
        return {}
    out: dict[int, bool] = {}
    # Y1 N2 Y3 or y1 n2
    for m in re.finditer(r"(?i)([YN]|yes|no)\s*(\d+)", text):
        idx = int(m.group(2))
        out[idx] = m.group(1).upper().startswith("Y") or m.group(1).lower() == "yes"
    # Plain "1 0 1" as positional (1=send, 0=skip)
    if not out:
        digits = re.findall(r"\b([01])\b", text)
        for i, d in enumerate(digits):
            out[i + 1] = d == "1"
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Process Y1/N1 approval reply and send approved messages.")
    ap.add_argument("--from", dest="from_phone", required=True, help="Phone number that received the approval request (we read your reply from this thread)")
    ap.add_argument("--csv", default="", help="Path to RSVP CSV (default: data/rsvp_headcount.csv)")
    ap.add_argument("--batch", default="", help="Path to approval_batch.json (default: data/approval_batch.json)")
    args = ap.parse_args()

    base = os.path.join(os.path.dirname(__file__), "..")
    csv_path = args.csv or os.path.join(base, "data", "rsvp_headcount.csv")
    batch_path = args.batch or os.path.join(base, "data", "approval_batch.json")

    if not os.path.isfile(batch_path):
        print("No approval batch found. Run poll_replies.py --notify --notify-to <your_phone> first.", file=sys.stderr)
        sys.exit(0)

    with open(batch_path, encoding="utf-8") as f:
        batch = json.load(f)
    items = batch.get("items") or []
    if not items:
        print("Batch has no items.", file=sys.stderr)
        sys.exit(0)

    raw = get_recent_messages(hours=24, contact=args.from_phone)
    last = _parse_last_reply_from_them(raw)
    if not last:
        print("No reply from you in that thread yet. Reply with e.g. Y1 N2 Y3.", file=sys.stderr)
        sys.exit(0)

    decisions = parse_approval_reply(last)
    if not decisions:
        print("Could not parse approval reply. Use e.g. Y1 N2 Y3 or 1 0 1.", file=sys.stderr)
        sys.exit(1)

    sent_count = 0
    for idx, do_send in decisions.items():
        if idx < 1 or idx > len(items):
            continue
        item = items[idx - 1]
        phone = item.get("phone", "")
        contact = item.get("contact", "")
        msg = (item.get("suggested_reply") or "").strip()
        if not phone or not msg:
            continue
        if do_send:
            result = send_message(phone, msg)
            if "Error" not in result:
                sent_count += 1
                print(f"Sent to {contact} ({phone}): {msg[:50]}...")
            else:
                print(f"Failed to send to {contact}: {result}", file=sys.stderr)

    if not os.path.isfile(csv_path):
        print(f"CSV not found: {csv_path}. Not updating reply_sent.", file=sys.stderr)
    else:
        # Update CSV: set reply_approved and reply_sent for rows that match batch items we sent
        rows: list[dict] = []
        with open(csv_path, newline="", encoding="utf-8") as f:
            r = csv.DictReader(f)
            fieldnames = r.fieldnames or []
            for row in r:
                rows.append(row)
        for idx, do_send in decisions.items():
            if idx < 1 or idx > len(items):
                continue
            item = items[idx - 1]
            ts = item.get("timestamp", "")
            for row in rows:
                if (row.get("contact") == item.get("contact") and row.get("phone") == item.get("phone")
                    and row.get("timestamp") == ts and not (row.get("reply_sent") or "").strip()):
                    row["reply_approved"] = "Y" if do_send else "N"
                    row["reply_sent"] = "Y" if do_send else ""
                    break
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)

    # Clear batch so we don't reprocess
    with open(batch_path, "w", encoding="utf-8") as f:
        json.dump({"sent_at": batch.get("sent_at"), "items": []}, f, indent=2)

    print(f"Done. Sent {sent_count} message(s).")


if __name__ == "__main__":
    main()
