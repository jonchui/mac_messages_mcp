#!/usr/bin/env python3
"""
Send the playdate ask to Val (Keevy), Rebecca (Eliza), Meghan (Violet), Sherri (Taylor).
Spaces blocks 2–3 sec apart per thread. Logs batch to data/playdate_batch_sent.json for polling.

Usage: uv run python scripts/send_playdate_batch.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from mac_messages_mcp.messages import send_message

DELAY_BETWEEN_BLOCKS = 2.5  # seconds

PLAYDATE_THREADS = [
    {
        "name": "Val (Keevy)",
        "phone": "16463440188",
        "blocks": [
            "Hey Val! Sydney has been begging for a play date w/ Keevy 😊 — you guys available?",
            "Option 1: You host. I'm at Picklr Thornton Sat 10–1 or 6–8, Sun 9–11 — can drop her before & grab after.",
            "Option 2: She comes here Sun 12–4 (rooftop pool, clubhouse, new place in Superior Origin — you're welcome too).",
            "LMK! (would love to make it regular if it works — sibling overload is real 😅)",
        ],
    },
    {
        "name": "Rebecca (Eliza)",
        "phone": "18454176830",
        "blocks": [
            "Hey Rebecca! Sydney has been begging for a play date w/ Eliza 😊. She said you're in Thornton — I'm at Picklr Thornton those days teaching so I can drop her before & grab after if you host.",
            "Times: Sat 10–1 or 6–8, Sun 9–11. Or she can come here Sun 12–4 (rooftop, clubhouse, new place — you're welcome too).",
            "LMK! (would love to make it regular if it works — sibling overload is real 😅)",
        ],
    },
    {
        "name": "Meghan (Violet)",
        "phone": "6462627070",
        "blocks": [
            "Hey Meghan! Sydney has been begging for a play date w/ Violet 😊 — you guys available?",
            "Option 1: You host. I'm at Picklr Thornton Sat 10–1 or 6–8, Sun 9–11 — drop her before & grab after.",
            "Option 2: She comes here Sun 12–4 (rooftop pool, clubhouse, new place — you're welcome too).",
            "LMK! (would love to make it regular if it works — sibling overload is real 😅)",
        ],
    },
    {
        "name": "Sherri (Taylor)",
        "phone": "17208380896",
        "blocks": [
            "Hey Sherri! Sydney has been begging for a play date w/ Taylor 😊 — you guys available?",
            "Option 1: You host. I'm at Picklr Thornton Sat 10–1 or 6–8, Sun 9–11 — drop her before & grab after.",
            "Option 2: She comes here Sun 12–4 (rooftop pool, clubhouse, new place — you're welcome too).",
            "LMK! (would love to make it regular if it works — sibling overload is real 😅)",
        ],
    },
]


def main() -> None:
    data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    os.makedirs(data_dir, exist_ok=True)
    log_path = os.path.join(data_dir, "playdate_batch_sent.json")

    results = []
    for thread in PLAYDATE_THREADS:
        name, phone, blocks = thread["name"], thread["phone"], thread["blocks"]
        print(f"Sending to {name} ({phone}) — {len(blocks)} blocks...", flush=True)
        for i, body in enumerate(blocks, 1):
            out = send_message(phone, body)
            if "Error" in out or "error" in out.lower():
                print(f"  Block {i}: {out}", flush=True)
                results.append({"name": name, "phone": phone, "block": i, "ok": False, "out": out})
            else:
                print(f"  Block {i}: sent.", flush=True)
                results.append({"name": name, "phone": phone, "block": i, "ok": True})
            if i < len(blocks):
                time.sleep(DELAY_BETWEEN_BLOCKS)

    payload = {
        "sent_at": datetime.now(tz=timezone.utc).isoformat(),
        "threads": [{"name": t["name"], "phone": t["phone"], "blocks": len(t["blocks"])} for t in PLAYDATE_THREADS],
        "results": results,
    }
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"\nLogged to {log_path}", flush=True)


if __name__ == "__main__":
    main()
