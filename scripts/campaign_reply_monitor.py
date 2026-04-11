#!/usr/bin/env python3
"""
Campaign reply monitor (MVP automation loop).

Polls macOS Messages DB for inbound replies from contacts in a campaign/tag scope,
updates campaign_ops.db, and sends a concise iMessage alert with a suggested action.

Run example:
  uv run python scripts/campaign_reply_monitor.py \
    --campaign-id 1 \
    --tag group:wed_waitlist \
    --notify-to 13035551234 \
    --interval 20
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mac_messages_mcp.messages import (  # noqa: E402
    extract_body_from_attributed,
    find_handles_by_phone,
    query_messages_db,
    send_message,
)


DB_DEFAULT = os.path.join(
    os.path.dirname(__file__), "..", "data", "campaign_ops.db"
)


def now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def normalize_phone(phone: str) -> str:
    return "".join(ch for ch in (phone or "") if ch.isdigit())


def classify_response(text: str) -> str:
    if not text:
        return "unknown"
    t = text.lower().strip()
    yes_tokens = [
        "yes",
        "yep",
        "yeah",
        "coming",
        "can come",
        "i can come",
        "i'm in",
        "im in",
        "we're in",
        "we are in",
        "on my way",
        "on the way",
        "be there",
        "see you",
    ]
    no_tokens = [
        "no",
        "can't",
        "cant",
        "not coming",
        "can't make",
        "next time",
        "sorry",
        "won't",
        "wont",
    ]
    maybe_tokens = ["maybe", "not sure", "possibly", "if i can", "might"]

    has_yes = any(tok in t for tok in yes_tokens)
    has_no = any(tok in t for tok in no_tokens)
    has_maybe = any(tok in t for tok in maybe_tokens)

    if has_yes and has_no:
        return "maybe"
    if has_maybe:
        return "maybe"
    if has_yes:
        return "yes"
    if has_no:
        return "no"
    return "unknown"


def gtd_suggestion(reply_status: str) -> tuple[str, str]:
    """
    Returns: (gtd_bucket, concise suggested next action)
    """
    if reply_status == "yes":
        return (
            "Do",
            "Confirm ETA now; if they miss this one, ask waitlist opt-in + minimum notice.",
        )
    if reply_status == "no":
        return (
            "Clarify",
            "Acknowledge and ask if they want future waitlist/no-show alerts plus notice window (30/60/120 min).",
        )
    if reply_status == "maybe":
        return (
            "Clarify",
            "Ask a binary follow-up: can they make this session now? Also ask preferred notice window.",
        )
    return (
        "Review",
        "Unclear intent; send short clarification and capture waitlist alert preference.",
    )


@dataclass
class ContactScope:
    contact_id: int
    first_name: str
    last_name: str
    phone: str
    tags: list[str]

    @property
    def display_name(self) -> str:
        name = f"{self.first_name} {self.last_name}".strip()
        return name if name else self.phone


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS monitor_state (
            state_key TEXT PRIMARY KEY,
            last_message_rowid INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS inbound_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_rowid INTEGER NOT NULL UNIQUE,
            campaign_id INTEGER,
            contact_id INTEGER NOT NULL,
            handle_id INTEGER,
            body TEXT NOT NULL DEFAULT '',
            reply_status TEXT NOT NULL DEFAULT 'unknown',
            gtd_bucket TEXT NOT NULL DEFAULT 'Review',
            suggestion TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        """
    )


def get_conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    return conn


def parse_tag_filter(tag: str) -> tuple[str, str] | None:
    if not tag:
        return None
    if ":" not in tag:
        raise ValueError("Tag filter must be type:value (e.g. group:wed_waitlist)")
    tag_type, tag_value = tag.split(":", 1)
    tag_type = tag_type.strip().lower()
    tag_value = tag_value.strip().lower()
    if not tag_type or not tag_value:
        raise ValueError("Tag filter must be type:value")
    return tag_type, tag_value


def load_scope_contacts(
    conn: sqlite3.Connection, campaign_id: int | None, tag: str | None
) -> list[ContactScope]:
    args: list[Any] = []
    joins = []
    where = []

    if campaign_id is not None:
        joins.append("JOIN campaign_contacts cc ON cc.contact_id = c.id")
        where.append("cc.campaign_id = ?")
        args.append(campaign_id)
    if tag:
        tag_filter = parse_tag_filter(tag)
        assert tag_filter is not None
        joins.append("JOIN contact_tags ft ON ft.contact_id = c.id")
        where.append("ft.tag_type = ? AND ft.tag_value = ?")
        args.extend([tag_filter[0], tag_filter[1]])

    query = f"""
    SELECT
      c.id AS contact_id,
      c.first_name,
      c.last_name,
      c.phone,
      GROUP_CONCAT(DISTINCT (ct.tag_type || ':' || ct.tag_value)) AS tags
    FROM contacts c
    {' '.join(joins)}
    LEFT JOIN contact_tags ct ON ct.contact_id = c.id
    {'WHERE ' + ' AND '.join(where) if where else ''}
    GROUP BY c.id
    ORDER BY c.first_name, c.last_name, c.phone
    """
    rows = conn.execute(query, tuple(args)).fetchall()
    out: list[ContactScope] = []
    for row in rows:
        tags_raw = row["tags"] or ""
        tags = [t for t in tags_raw.split(",") if t]
        out.append(
            ContactScope(
                contact_id=int(row["contact_id"]),
                first_name=(row["first_name"] or "").strip(),
                last_name=(row["last_name"] or "").strip(),
                phone=normalize_phone(row["phone"] or ""),
                tags=tags,
            )
        )
    return out


def state_key_for(campaign_id: int | None, tag: str | None) -> str:
    return f"campaign={campaign_id if campaign_id is not None else 'all'}|tag={tag or 'all'}"


def get_last_rowid(conn: sqlite3.Connection, state_key: str) -> int | None:
    row = conn.execute(
        "SELECT last_message_rowid FROM monitor_state WHERE state_key = ?", (state_key,)
    ).fetchone()
    if not row:
        return None
    return int(row["last_message_rowid"])


def set_last_rowid(conn: sqlite3.Connection, state_key: str, rowid: int) -> None:
    conn.execute(
        """
        INSERT INTO monitor_state(state_key, last_message_rowid, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(state_key) DO UPDATE SET
          last_message_rowid = excluded.last_message_rowid,
          updated_at = excluded.updated_at
        """,
        (state_key, int(rowid), now_iso()),
    )


def get_max_message_rowid(handle_ids: list[int]) -> int:
    if not handle_ids:
        return 0
    placeholders = ", ".join("?" for _ in handle_ids)
    rows = query_messages_db(
        f"SELECT COALESCE(MAX(ROWID), 0) AS max_rowid FROM message WHERE handle_id IN ({placeholders})",
        tuple(handle_ids),
    )
    if not rows or "error" in rows[0]:
        return 0
    return int(rows[0].get("max_rowid", 0) or 0)


def fetch_incoming_messages(handle_ids: list[int], last_rowid: int) -> list[dict]:
    if not handle_ids:
        return []
    placeholders = ", ".join("?" for _ in handle_ids)
    query = f"""
    SELECT ROWID, date, text, attributedBody, handle_id
    FROM message
    WHERE is_from_me = 0
      AND ROWID > ?
      AND handle_id IN ({placeholders})
    ORDER BY ROWID ASC
    """
    params = tuple([last_rowid, *handle_ids])
    rows = query_messages_db(query, params)
    if not rows:
        return []
    if "error" in rows[0]:
        return []
    out = []
    for row in rows:
        body = row.get("text") or extract_body_from_attributed(row.get("attributedBody"))
        if not body:
            continue
        out.append(
            {
                "rowid": int(row["ROWID"]),
                "date": row.get("date"),
                "handle_id": int(row["handle_id"]) if row.get("handle_id") is not None else None,
                "body": str(body).strip(),
            }
        )
    return out


def update_campaign_status_for_contact(
    conn: sqlite3.Connection,
    campaign_id: int | None,
    contact_id: int,
    reply_status: str,
    body: str,
) -> int | None:
    if campaign_id is not None:
        row = conn.execute(
            """
            SELECT id FROM campaign_contacts
            WHERE campaign_id = ? AND contact_id = ?
            """,
            (campaign_id, contact_id),
        ).fetchone()
        if not row:
            return None
        conn.execute(
            """
            UPDATE campaign_contacts
            SET reply_status = ?, last_reply_text = ?, last_reply_at = ?, send_status = 'sent'
            WHERE campaign_id = ? AND contact_id = ?
            """,
            (reply_status, body[:2000], now_iso(), campaign_id, contact_id),
        )
        return int(campaign_id)

    # No campaign specified: update latest campaign for this contact.
    row = conn.execute(
        """
        SELECT cc.campaign_id
        FROM campaign_contacts cc
        JOIN campaigns c ON c.id = cc.campaign_id
        WHERE cc.contact_id = ?
        ORDER BY c.created_at DESC, c.id DESC
        LIMIT 1
        """,
        (contact_id,),
    ).fetchone()
    if not row:
        return None
    chosen_campaign_id = int(row["campaign_id"])
    conn.execute(
        """
        UPDATE campaign_contacts
        SET reply_status = ?, last_reply_text = ?, last_reply_at = ?, send_status = 'sent'
        WHERE campaign_id = ? AND contact_id = ?
        """,
        (reply_status, body[:2000], now_iso(), chosen_campaign_id, contact_id),
    )
    return chosen_campaign_id


def send_alert(
    notify_to: str,
    group_chat: bool,
    contact_name: str,
    tags: list[str],
    body: str,
    reply_status: str,
    gtd_bucket: str,
    suggestion: str,
    dry_run: bool,
) -> None:
    tag_str = ", ".join(tags[:4]) if tags else "no-tags"
    snippet = body.replace("\n", " ").strip()
    if len(snippet) > 140:
        snippet = snippet[:137] + "..."
    msg = (
        f"reply in from {contact_name} [{tag_str}]\n"
        f"\"{snippet}\"\n"
        f"classified: {reply_status} | GTD: {gtd_bucket}\n"
        f"next: {suggestion}"
    )
    if dry_run:
        print(f"[DRY RUN notify] -> {notify_to}\n{msg}\n")
        return
    result = send_message(recipient=notify_to, message=msg, group_chat=group_chat)
    print(f"[notify] {result}")


def maybe_run_hook(hook_cmd: str | None, payload: dict[str, Any]) -> None:
    if not hook_cmd:
        return
    try:
        subprocess.run(
            hook_cmd,
            shell=True,
            text=True,
            input=json.dumps(payload),
            check=False,
        )
    except Exception as exc:
        print(f"[hook error] {exc}")


def build_handle_maps(
    scope_contacts: list[ContactScope],
) -> tuple[dict[int, ContactScope], list[int]]:
    handle_to_contact: dict[int, ContactScope] = {}
    handle_ids: list[int] = []
    for c in scope_contacts:
        handles = find_handles_by_phone(c.phone) or []
        for hid in handles:
            handle_to_contact[int(hid)] = c
            handle_ids.append(int(hid))
    # Deduplicate while preserving order.
    seen = set()
    unique_handles: list[int] = []
    for hid in handle_ids:
        if hid in seen:
            continue
        seen.add(hid)
        unique_handles.append(hid)
    return handle_to_contact, unique_handles


def monitor_loop(
    db_path: str,
    campaign_id: int | None,
    tag: str | None,
    notify_to: str,
    notify_group_chat: bool,
    interval: int,
    hook_cmd: str | None,
    dry_run: bool,
) -> None:
    with get_conn(db_path) as conn:
        scope_contacts = load_scope_contacts(conn, campaign_id, tag)
        if not scope_contacts:
            raise RuntimeError("No contacts found for monitor scope (campaign/tag).")
        handle_to_contact, handle_ids = build_handle_maps(scope_contacts)
        if not handle_ids:
            raise RuntimeError(
                "No message handles found for scoped contacts. "
                "Ensure they have message history in chat.db."
            )

        key = state_key_for(campaign_id, tag)
        last_rowid = get_last_rowid(conn, key)
        if last_rowid is None:
            bootstrap = get_max_message_rowid(handle_ids)
            set_last_rowid(conn, key, bootstrap)
            conn.commit()
            last_rowid = bootstrap
            print(
                f"[bootstrap] state={key} last_rowid={last_rowid}. "
                "Monitoring only new inbound replies from now on."
            )

    print(
        f"[monitor] scope contacts={len(scope_contacts)} handles={len(handle_ids)} "
        f"interval={interval}s notify_to={notify_to}"
    )
    while True:
        try:
            with get_conn(db_path) as conn:
                key = state_key_for(campaign_id, tag)
                last_rowid = get_last_rowid(conn, key) or 0
                incoming = fetch_incoming_messages(handle_ids, last_rowid)
                if not incoming:
                    time.sleep(interval)
                    continue

                max_seen = last_rowid
                for msg in incoming:
                    rowid = int(msg["rowid"])
                    if rowid > max_seen:
                        max_seen = rowid
                    handle_id = int(msg["handle_id"]) if msg["handle_id"] is not None else -1
                    contact = handle_to_contact.get(handle_id)
                    if not contact:
                        continue
                    already = conn.execute(
                        "SELECT id FROM inbound_events WHERE message_rowid = ?", (rowid,)
                    ).fetchone()
                    if already:
                        continue

                    body = msg["body"]
                    reply_status = classify_response(body)
                    gtd_bucket, suggestion = gtd_suggestion(reply_status)
                    matched_campaign_id = update_campaign_status_for_contact(
                        conn, campaign_id, contact.contact_id, reply_status, body
                    )
                    conn.execute(
                        """
                        INSERT INTO inbound_events(
                          message_rowid, campaign_id, contact_id, handle_id, body,
                          reply_status, gtd_bucket, suggestion, created_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            rowid,
                            matched_campaign_id,
                            contact.contact_id,
                            handle_id,
                            body[:4000],
                            reply_status,
                            gtd_bucket,
                            suggestion,
                            now_iso(),
                        ),
                    )
                    conn.commit()

                    payload = {
                        "contact_id": contact.contact_id,
                        "contact_name": contact.display_name,
                        "phone": contact.phone,
                        "tags": contact.tags,
                        "campaign_id": matched_campaign_id,
                        "message_rowid": rowid,
                        "reply_text": body,
                        "reply_status": reply_status,
                        "gtd_bucket": gtd_bucket,
                        "suggestion": suggestion,
                        "created_at": now_iso(),
                    }
                    maybe_run_hook(hook_cmd, payload)
                    send_alert(
                        notify_to=notify_to,
                        group_chat=notify_group_chat,
                        contact_name=contact.display_name,
                        tags=contact.tags,
                        body=body,
                        reply_status=reply_status,
                        gtd_bucket=gtd_bucket,
                        suggestion=suggestion,
                        dry_run=dry_run,
                    )
                    print(
                        f"[event] rowid={rowid} contact={contact.display_name} status={reply_status}"
                    )

                set_last_rowid(conn, key, max_seen)
                conn.commit()
            time.sleep(interval)
        except KeyboardInterrupt:
            print("Stopped.")
            break
        except Exception as exc:
            print(f"[monitor error] {exc}")
            time.sleep(interval)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Monitor campaign replies and notify with suggested actions."
    )
    ap.add_argument("--db", default=DB_DEFAULT, help="Path to campaign_ops.db")
    ap.add_argument(
        "--campaign-id",
        type=int,
        default=None,
        help="Scope to a campaign ID (optional)",
    )
    ap.add_argument(
        "--tag",
        default="",
        help="Optional tag scope type:value (e.g. group:wed_waitlist)",
    )
    ap.add_argument(
        "--notify-to",
        required=True,
        help="Phone number or chat ID for notifications",
    )
    ap.add_argument(
        "--notify-group-chat",
        action="store_true",
        help="Treat --notify-to as chat ID for group chat send",
    )
    ap.add_argument(
        "--interval",
        type=int,
        default=20,
        help="Polling interval in seconds (default 20)",
    )
    ap.add_argument(
        "--hook-cmd",
        default="",
        help="Optional shell command. JSON payload for each event is sent to stdin.",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not send iMessage notifications, just print",
    )
    args = ap.parse_args()

    db_path = os.path.abspath(args.db)
    monitor_loop(
        db_path=db_path,
        campaign_id=args.campaign_id,
        tag=args.tag.strip() or None,
        notify_to=str(args.notify_to).strip(),
        notify_group_chat=bool(args.notify_group_chat),
        interval=max(5, int(args.interval)),
        hook_cmd=args.hook_cmd.strip() or None,
        dry_run=bool(args.dry_run),
    )


if __name__ == "__main__":
    main()
