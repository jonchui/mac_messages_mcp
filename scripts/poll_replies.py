#!/usr/bin/env python3
"""
Poll for replies from a list of contacts (e.g. junior league parents).
No webhook available on macOS — run this on a schedule (e.g. every 5–10 min)
or manually after sending a batch.

Usage:
  uv run python scripts/poll_replies.py [--since-today] [--hours N] [--csv out.csv] [--phones 7143767892,3032575751]
  Default: --since-today (from 6 AM today to now) so you get all replies from this morning's outreach in time for the ladder.
  Use --hours N to override (e.g. last N hours only).

Output: For each contact, prints last reply from them, classification (yes/no/mixed), and suggested reply.
Optionally appends to --csv for headcount (contact, response, suggested_reply, timestamp).

Agentic vs deterministic:
  Default: deterministic rules (fast, no API). Can miss nuances (e.g. don't thank when no reply).
  --use-ai: pass contact + their message + context to an LLM; use its suggested reply or "no action".
            Handles nuance (no reply = no action, ambiguous = appropriate short reply). Set OPENAI_API_KEY or ANTHROPIC_API_KEY.
            Install optional deps: uv sync --extra ai  (or pip install -e ".[ai]")
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta

# Add project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mac_messages_mcp.messages import get_recent_messages, send_message


def _suggested_reply_via_ai(contact: str, last_reply: str | None, context: str = "") -> str:
    """Ask an LLM for a suggested reply. Returns reply text or empty string for no action. Uses OPENAI_API_KEY or ANTHROPIC_API_KEY."""
    # Prefer OpenAI, then Anthropic
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return ""
    prompt = f"""You are helping a coach (JC) get headcount for a junior league session. Keep replies very short and friendly.

Context: {context or "Getting RSVPs for junior league."}
Contact: {contact}
Their last message: {last_reply or "(No reply yet — they have not responded)"}

Should we send a reply?
- If they have NOT replied yet: output exactly "NO_ACTION" and nothing else.
- If they replied (yes/no/mixed/ambiguous): output a single short reply JC could send (1 line, friendly, confirm we got it). No explanation.

Output only the reply text, or NO_ACTION."""
    if os.environ.get("OPENAI_API_KEY"):
        try:
            import openai
            client = openai.OpenAI()
            r = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=80,
            )
            out = (r.choices[0].message.content or "").strip()
            return "" if out.upper() == "NO_ACTION" else out
        except Exception:
            return ""
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            import anthropic
            client = anthropic.Anthropic()
            m = client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=80,
                messages=[{"role": "user", "content": prompt}],
            )
            out = (m.content[0].text if m.content else "").strip()
            return "" if out.upper() == "NO_ACTION" else out
        except Exception:
            return ""
    return ""


def _parse_last_reply_from_them(formatted_log: str, my_label: str = "You") -> str | None:
    """Parse get_recent_messages output; return last message body that is NOT from me."""
    if not formatted_log or "Error" in formatted_log or "No " in formatted_log:
        return None
    lines = [ln.strip() for ln in formatted_log.split("\n") if ln.strip()]
    last_from_them = None
    for line in lines:
        # Format like "[2025-02-21 10:00:00] Christina: yes we're coming"
        if line.startswith("["):
            rest = line.split("]", 1)[-1].strip()
            if rest.startswith(my_label + ":"):
                continue
            # From them: "Name: body" or "3032575751: body"
            if ": " in rest:
                _, body = rest.split(": ", 1)
                last_from_them = body
    return last_from_them


def classify_response(text: str) -> str:
    """Classify reply as yes, no, or mixed. Returns 'yes' | 'no' | 'mixed' | 'unknown'."""
    if not text:
        return "unknown"
    t = text.lower().strip()
    # Yes-like (including "they'll be there", "yup they are in", "will be there today")
    if any(w in t for w in [
        "yes", "coming", "we'll be there", "we will", "both", "all", "see you", "yep", "yeah", "sure",
        "will be there", "they'll be there", "they will be there", "we'll be there", "are in", "they are in",
        "make it today", "will make it", "he will be there", "she will be there"
    ]):
        if any(w in t for w in ["no", "not", "won't", "can't", "only one", "just one", "one kid", "one is"]) and "next week" not in t:
            return "mixed"
        if "not" in t and "next week" in t and ("will be there today" in t or "today" in t):
            return "mixed"  # e.g. "we will be there today! we will NOT be there NEXT week"
        return "yes"
    # No-like
    if any(w in t for w in ["no", "not coming", "can't make it", "won't be", "sorry", "next time", "nope"]):
        return "no"
    return "unknown"


def parse_for_week(last_reply: str) -> str:
    """Parse which week(s) the reply is for. Returns e.g. this_week, next_week, both, unknown."""
    if not last_reply:
        return "unknown"
    t = last_reply.lower()
    has_today = "today" in t
    has_this_week = "this week" in t
    has_next_week = "next week" in t
    has_not_next = "not" in t and "next" in t
    if has_today or has_this_week:
        if has_next_week or has_not_next:
            return "this_week_and_next"  # e.g. "today yes, not next week"
        return "this_week"
    if has_next_week:
        return "next_week"
    return "unknown"


def suggested_reply(response: str, name: str = "", last_reply: str | None = None) -> str:
    """Suggest a reply only when they actually replied. No reply = no action."""
    if not (last_reply or "").strip():
        return ""  # No reply yet — don't suggest thanking them for getting back to you
    if response == "yes":
        return "Thanks! See you soon!"
    if response == "no":
        return "No problem, next time!"
    if response == "mixed":
        return "Got it, thanks for letting me know!"
    return "Thanks for getting back to me!"


def main() -> None:
    ap = argparse.ArgumentParser(description="Poll for replies from contacts and suggest responses.")
    ap.add_argument("--since-today", action="store_true", default=True, help="Look back from 6 AM today (default)")
    ap.add_argument("--no-since-today", action="store_false", dest="since_today", help="Use --hours instead of since 6 AM today")
    ap.add_argument("--hours", type=int, default=None, help="Hours of messages to look back (overrides --since-today if set)")
    ap.add_argument("--csv", default="", help="Append results to this CSV (contact, response, suggested_reply, timestamp)")
    ap.add_argument("--phones", default="", help="Comma-separated phone numbers (e.g. 7143767892,3032575751)")
    ap.add_argument("--names", default="", help="Comma-separated names in same order as --phones (optional)")
    ap.add_argument("--sent", type=int, default=None, help="Total messages sent out (for headcount: 1) N sent, 2) replied, 3) yes/no/mixed)")
    ap.add_argument("--use-ai", action="store_true", help="Use LLM for suggested reply (set OPENAI_API_KEY or ANTHROPIC_API_KEY)")
    ap.add_argument("--context", default="", help="Context for AI (e.g. 'Junior league 11-1, getting headcount')")
    ap.add_argument("--notify", action="store_true", help="Send approval request to --notify-to (mobile-friendly yes/no)")
    ap.add_argument("--notify-to", default="", help="Phone number to receive pending-reply approval (e.g. your own number)")
    args = ap.parse_args()

    # Lookback: from 6 AM today to now (so we get all morning replies in time for 11 AM ladder), unless --hours set
    if args.hours is not None:
        hours = args.hours
    else:
        now = datetime.now()
        today_6am = now.replace(hour=6, minute=0, second=0, microsecond=0)
        if now < today_6am:
            hours = 24
        else:
            hours = max(1, int((now - today_6am).total_seconds() / 3600))
        print(f"Lookback: since 6 AM today ({hours} hours)", file=sys.stderr)

    phones = [p.strip() for p in args.phones.split(",") if p.strip()]
    names = [n.strip() for n in args.names.split(",")] if args.names else []
    if not phones:
        # Optional: read from env or default list
        env_phones = os.environ.get("POLL_REPLIES_PHONES", "")
        phones = [p.strip() for p in env_phones.split(",") if p.strip()]
    if not phones:
        print("Provide --phones 7143767892,3032575751 or set POLL_REPLIES_PHONES", file=sys.stderr)
        sys.exit(1)

    if args.use_ai and not (os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")):
        print("Warning: --use-ai set but no OPENAI_API_KEY or ANTHROPIC_API_KEY; using deterministic suggestions.", file=sys.stderr)

    rows: list[dict] = []
    for i, phone in enumerate(phones):
        name = names[i] if i < len(names) else phone
        raw = get_recent_messages(hours=hours, contact=phone)
        last = _parse_last_reply_from_them(raw)
        response = classify_response(last or "")
        if args.use_ai:
            reply = _suggested_reply_via_ai(name, last, args.context or "")
            if not reply:
                reply = suggested_reply(response, name, last)
        else:
            reply = suggested_reply(response, name, last)
        for_week = parse_for_week(last or "")
        row = {
            "contact": name, "phone": phone, "last_reply": last or "", "response": response,
            "for_week": for_week, "suggested_reply": reply,
            "reply_approved": "", "reply_sent": "",
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        }
        rows.append(row)
        print(f"{name} ({phone}): response={response} | for_week={for_week} | last={repr(last)[:50]}")
        if reply:
            print(f"  -> REPLY: {reply}")
        else:
            print(f"  -> No reply yet — no action")

    if args.csv and rows:
        os.makedirs(os.path.dirname(args.csv) or ".", exist_ok=True)
        file_exists = os.path.isfile(args.csv)
        fieldnames = ["contact", "phone", "last_reply", "response", "for_week", "suggested_reply", "reply_approved", "reply_sent", "timestamp"]
        with open(args.csv, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            if not file_exists:
                w.writeheader()
            w.writerows(rows)
        print(f"\nAppended {len(rows)} rows to {args.csv} (single source of truth)")

    # Approval table: show suggested reply for each so user can approve before sending
    _print_approval_table(rows)

    # Optional: send one iMessage to notify_to with pending replies so they can approve from phone (Y1 N2 Y3)
    if args.notify and args.notify_to and rows:
        _send_approval_notification(rows, args.notify_to)

    # Colored headcount summary
    _print_headcount(rows, args.sent)


def _ansi(c: str) -> str:
    """ANSI code for terminal colors (no-op if not a TTY)."""
    if not sys.stdout.isatty():
        return ""
    codes = {
        "green": "\033[92m",
        "red": "\033[91m",
        "yellow": "\033[93m",
        "cyan": "\033[96m",
        "bold": "\033[1m",
        "dim": "\033[2m",
        "reset": "\033[0m",
    }
    return codes.get(c, "")


def _send_approval_notification(rows: list[dict], notify_to: str) -> None:
    """Send one iMessage to notify_to listing pending replies; ask for Y1/N1, Y2/N2, ... Reply format: Y=send, N=skip."""
    pending = [r for r in rows if (r.get("suggested_reply") or "").strip()]
    if not pending:
        return
    lines = ["RSVP approval — reply with Y or N for each number (e.g. Y1 N2 Y3)"]
    for i, r in enumerate(pending, 1):
        contact = r.get("contact", "")
        reply = (r.get("suggested_reply") or "").strip()[:60]
        lines.append(f"{i}. {contact}: \"{reply}\"")
    lines.append("Reply e.g. Y1 N2 Y3 = send #1, skip #2, send #3")
    body = "\n".join(lines)
    try:
        result = send_message(notify_to, body)
        if "Error" not in result:
            # Persist batch so approve_replies.py can match Y1 -> row 0
            batch_path = os.path.join(os.path.dirname(__file__), "..", "data", "approval_batch.json")
            os.makedirs(os.path.dirname(batch_path), exist_ok=True)
            batch = {
                "sent_at": datetime.now(tz=timezone.utc).isoformat(),
                "items": [
                    {
                        "contact": r.get("contact", ""),
                        "phone": r.get("phone", ""),
                        "suggested_reply": (r.get("suggested_reply") or "").strip(),
                        "timestamp": r.get("timestamp", ""),
                    }
                    for r in pending
                ],
            }
            with open(batch_path, "w", encoding="utf-8") as f:
                json.dump(batch, f, indent=2)
            print(f"Approval request sent to {notify_to}. Reply with Y1/N1, Y2/N2, etc.", file=sys.stderr)
        else:
            print(f"Failed to send approval request: {result}", file=sys.stderr)
    except Exception as e:
        print(f"Error sending approval request: {e}", file=sys.stderr)


def _print_approval_table(rows: list[dict]) -> None:
    """Print a table of suggested replies so the user can approve before sending. Skip people who haven't replied."""
    b = _ansi("bold")
    c = _ansi("cyan")
    g = _ansi("green")
    d = _ansi("dim")
    r = _ansi("reset")
    print(f"\n{b}{c}─── REPLIES TO APPROVE (review before sending) ───{r}")
    for row in rows:
        contact = row.get("contact", "")
        last = (row.get("last_reply") or "").strip()
        resp = row.get("response", "")
        reply = row.get("suggested_reply", "")
        if not last:
            print(f"  {d}{contact}: No reply yet — no action{r}")
            continue
        if not reply:
            print(f"  {d}{contact}: Replied but no reply suggested (unknown){r}")
            continue
        print(f"  {b}{contact}{r} [{resp}]")
        print(f"    Their message: {last[:60]}")
        print(f"    {g}Your reply: {reply}{r}")
        print()
    print(f"{c}─────────────────────────────────────────────────────{r}")


def _print_headcount(rows: list[dict], sent: int | None) -> None:
    g = _ansi("green")
    y = _ansi("yellow")
    c = _ansi("cyan")
    b = _ansi("bold")
    r = _ansi("reset")
    replied = sum(1 for row in rows if (row.get("last_reply") or "").strip())
    yes = sum(1 for row in rows if row.get("response") == "yes")
    no = sum(1 for row in rows if row.get("response") == "no")
    mixed = sum(1 for row in rows if row.get("response") == "mixed")
    unknown = sum(1 for row in rows if row.get("response") == "unknown")
    total_polled = len(rows)
    sent_n = sent if sent is not None else total_polled
    print()
    print(f"{b}{c}─── HEADCOUNT ───{r}")
    print(f"  1) {b}{sent_n}{r} messages sent out")
    print(f"  2) {b}{replied}{r} replied back")
    print(f"  3) current  {g}{yes} yes{r}  {y}{no} no{r}  {y}{mixed} mixed{r}  {_ansi('dim')}{unknown} unknown{r}")
    print(f"{c}─────────────────{r}")


if __name__ == "__main__":
    main()
