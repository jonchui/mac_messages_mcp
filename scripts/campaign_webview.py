#!/usr/bin/env python3
"""
Local Campaign Ops Webview (MVP)

A zero-dependency local web service to track:
- Campaign objective + CTA + response prompt
- Recipients and tags (group/cohort/etc.)
- Reply outcomes and basic conversion metrics
- Rerun by cloning prior campaigns

Run:
  uv run python scripts/campaign_webview.py
  # then open http://127.0.0.1:8765
"""
from __future__ import annotations

import argparse
import html
import os
import sqlite3
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


DB_DEFAULT = os.path.join(
    os.path.dirname(__file__), "..", "data", "campaign_ops.db"
)


def now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def get_conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str) -> None:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    with get_conn(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                objective TEXT NOT NULL DEFAULT '',
                cta TEXT NOT NULL DEFAULT '',
                response_prompt TEXT NOT NULL DEFAULT '',
                channel TEXT NOT NULL DEFAULT 'imessage_sms',
                created_at TEXT NOT NULL,
                source_campaign_id INTEGER
            );

            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                first_name TEXT NOT NULL DEFAULT '',
                last_name TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS campaign_contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER NOT NULL,
                contact_id INTEGER NOT NULL,
                intended_action TEXT NOT NULL DEFAULT '',
                send_status TEXT NOT NULL DEFAULT 'pending',
                sent_at TEXT,
                reply_status TEXT NOT NULL DEFAULT 'none',
                last_reply_text TEXT NOT NULL DEFAULT '',
                last_reply_at TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(campaign_id, contact_id)
            );

            CREATE TABLE IF NOT EXISTS campaign_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER NOT NULL,
                tag_type TEXT NOT NULL,
                tag_value TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS contact_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contact_id INTEGER NOT NULL,
                tag_type TEXT NOT NULL,
                tag_value TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(contact_id, tag_type, tag_value)
            );

            CREATE TABLE IF NOT EXISTS contact_preferences (
                contact_id INTEGER PRIMARY KEY,
                waitlist_opt_in INTEGER NOT NULL DEFAULT 0,
                min_notice_minutes INTEGER,
                auto_booking_opt_in INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            );
            """
        )


def parse_tags(raw: str) -> list[tuple[str, str]]:
    """
    Parse tags from:
    - group:wed_waitlist,cohort:3_5_plus
    - wed_waitlist,3_5_plus  (defaults type=group)
    """
    out: list[tuple[str, str]] = []
    for token in [t.strip() for t in raw.split(",") if t.strip()]:
        if ":" in token:
            tag_type, tag_value = token.split(":", 1)
            tag_type = tag_type.strip().lower()
            tag_value = tag_value.strip().lower()
        else:
            tag_type, tag_value = "group", token.strip().lower()
        if tag_type and tag_value:
            out.append((tag_type, tag_value))
    return out


def upsert_contact(
    conn: sqlite3.Connection, first_name: str, last_name: str, phone: str
) -> int:
    clean_phone = "".join(ch for ch in phone if ch.isdigit())
    if len(clean_phone) < 10:
        raise ValueError(f"Phone '{phone}' is too short")
    row = conn.execute(
        "SELECT id FROM contacts WHERE phone = ?", (clean_phone,)
    ).fetchone()
    if row:
        return int(row["id"])
    cur = conn.execute(
        """
        INSERT INTO contacts(first_name, last_name, phone, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (first_name.strip(), last_name.strip(), clean_phone, now_iso()),
    )
    return int(cur.lastrowid)


def campaign_summary_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT
          c.id,
          c.name,
          c.objective,
          c.cta,
          c.channel,
          c.created_at,
          COUNT(cc.id) AS recipients,
          SUM(CASE WHEN cc.sent_at IS NOT NULL THEN 1 ELSE 0 END) AS sent_count,
          SUM(CASE WHEN cc.reply_status != 'none' THEN 1 ELSE 0 END) AS replied_count,
          SUM(CASE WHEN cc.reply_status = 'yes' THEN 1 ELSE 0 END) AS yes_count,
          SUM(CASE WHEN cc.reply_status = 'no' THEN 1 ELSE 0 END) AS no_count,
          SUM(CASE WHEN cc.reply_status = 'maybe' THEN 1 ELSE 0 END) AS maybe_count
        FROM campaigns c
        LEFT JOIN campaign_contacts cc ON cc.campaign_id = c.id
        GROUP BY c.id
        ORDER BY c.id DESC
        """
    ).fetchall()


def cohort_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT
          ct.tag_type,
          ct.tag_value,
          COUNT(DISTINCT cc.id) AS touched,
          SUM(CASE WHEN cc.reply_status != 'none' THEN 1 ELSE 0 END) AS replied,
          SUM(CASE WHEN cc.reply_status = 'yes' THEN 1 ELSE 0 END) AS yes_count
        FROM campaign_contacts cc
        JOIN contact_tags ct ON ct.contact_id = cc.contact_id
        GROUP BY ct.tag_type, ct.tag_value
        ORDER BY touched DESC, ct.tag_type ASC, ct.tag_value ASC
        """
    ).fetchall()


def campaign_detail(
    conn: sqlite3.Connection, campaign_id: int
) -> tuple[sqlite3.Row | None, list[sqlite3.Row], list[sqlite3.Row]]:
    campaign = conn.execute(
        "SELECT * FROM campaigns WHERE id = ?", (campaign_id,)
    ).fetchone()
    recipients = conn.execute(
        """
        SELECT
          cc.id AS campaign_contact_id,
          cc.send_status,
          cc.sent_at,
          cc.reply_status,
          cc.last_reply_text,
          cc.last_reply_at,
          cc.intended_action,
          x.first_name,
          x.last_name,
          x.phone
        FROM campaign_contacts cc
        JOIN contacts x ON x.id = cc.contact_id
        WHERE cc.campaign_id = ?
        ORDER BY x.first_name, x.last_name, x.phone
        """,
        (campaign_id,),
    ).fetchall()
    tags = conn.execute(
        "SELECT tag_type, tag_value FROM campaign_tags WHERE campaign_id = ? ORDER BY tag_type, tag_value",
        (campaign_id,),
    ).fetchall()
    return campaign, recipients, tags


def parse_recipients_input(raw: str) -> list[dict]:
    """
    One recipient per line:
      FirstName LastName|3035551111|group:wed_waitlist,cohort:3_5_plus
      Erika|7322663659|group:wed_waitlist
    """
    rows: list[dict] = []
    for line in [ln.strip() for ln in raw.splitlines() if ln.strip()]:
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2:
            raise ValueError(
                f"Bad recipient line '{line}'. Use 'Name|Phone|optional_tags'."
            )
        name = parts[0]
        phone = parts[1]
        tag_part = parts[2] if len(parts) >= 3 else ""
        name_tokens = [n for n in name.split() if n]
        first_name = name_tokens[0] if name_tokens else ""
        last_name = " ".join(name_tokens[1:]) if len(name_tokens) > 1 else ""
        rows.append(
            {
                "first_name": first_name,
                "last_name": last_name,
                "phone": phone,
                "tags": parse_tags(tag_part),
            }
        )
    return rows


def h(text: str) -> str:
    return html.escape(text or "")


class CampaignOpsHandler(BaseHTTPRequestHandler):
    db_path: str = DB_DEFAULT

    def _send_html(self, html_text: str, status: int = 200) -> None:
        payload = html_text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _redirect(self, location: str) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", location)
        self.end_headers()

    def _post_form(self) -> dict[str, str]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        parsed = parse_qs(raw, keep_blank_values=True)
        return {k: v[0] for k, v in parsed.items()}

    def do_GET(self) -> None:  # noqa: N802
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                return self._render_home()
            if parsed.path == "/campaign":
                q = parse_qs(parsed.query)
                campaign_id = int((q.get("id") or ["0"])[0])
                return self._render_campaign(campaign_id)
            self._send_html("<h1>Not Found</h1>", status=404)
        except Exception as exc:
            self._send_html(
                f"<h1>Server Error</h1><pre>{h(str(exc))}</pre>",
                status=500,
            )

    def do_POST(self) -> None:  # noqa: N802
        try:
            if self.path == "/campaigns/create":
                return self._create_campaign()
            if self.path == "/campaigns/log_send":
                return self._log_send()
            if self.path == "/campaigns/record_reply":
                return self._record_reply()
            if self.path == "/campaigns/clone":
                return self._clone_campaign()
            self._send_html("<h1>Not Found</h1>", status=404)
        except Exception as exc:
            self._send_html(
                f"<h1>Action Failed</h1><pre>{h(str(exc))}</pre><p><a href='/'>Back</a></p>",
                status=400,
            )

    def _render_home(self) -> None:
        with get_conn(self.db_path) as conn:
            campaigns = campaign_summary_rows(conn)
            cohorts = cohort_rows(conn)

        campaign_rows = []
        for row in campaigns:
            recipients = int(row["recipients"] or 0)
            replied = int(row["replied_count"] or 0)
            reply_rate = (replied / recipients * 100.0) if recipients else 0.0
            campaign_rows.append(
                f"""
                <tr>
                  <td>{row["id"]}</td>
                  <td><a href="/campaign?id={row["id"]}">{h(row["name"])}</a></td>
                  <td>{h(row["objective"])}</td>
                  <td>{recipients}</td>
                  <td>{int(row["sent_count"] or 0)}</td>
                  <td>{replied}</td>
                  <td>{reply_rate:.1f}%</td>
                  <td>{int(row["yes_count"] or 0)} / {int(row["no_count"] or 0)} / {int(row["maybe_count"] or 0)}</td>
                </tr>
                """
            )

        cohort_rows_html = []
        for row in cohorts:
            touched = int(row["touched"] or 0)
            replied = int(row["replied"] or 0)
            yes_count = int(row["yes_count"] or 0)
            reply_rate = (replied / touched * 100.0) if touched else 0.0
            yes_rate = (yes_count / touched * 100.0) if touched else 0.0
            cohort_rows_html.append(
                f"""
                <tr>
                  <td>{h(row["tag_type"])}</td>
                  <td>{h(row["tag_value"])}</td>
                  <td>{touched}</td>
                  <td>{replied}</td>
                  <td>{reply_rate:.1f}%</td>
                  <td>{yes_rate:.1f}%</td>
                </tr>
                """
            )

        page = f"""
        <html>
          <head>
            <title>Campaign Ops MVP</title>
            <style>
              body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 24px; }}
              h1, h2 {{ margin: 8px 0 12px 0; }}
              .card {{ border: 1px solid #ddd; border-radius: 10px; padding: 14px; margin-bottom: 18px; }}
              table {{ width: 100%; border-collapse: collapse; }}
              th, td {{ border: 1px solid #e1e1e1; padding: 8px; text-align: left; vertical-align: top; }}
              textarea, input {{ width: 100%; box-sizing: border-box; }}
              .small {{ color: #555; font-size: 12px; }}
              button {{ padding: 8px 12px; }}
            </style>
          </head>
          <body>
            <h1>Campaign Ops MVP</h1>
            <p class="small">Track campaigns, cohorts, tags, and reply conversion for iMessage/SMS workflows.</p>

            <div class="card">
              <h2>Create Campaign</h2>
              <form method="post" action="/campaigns/create">
                <label>Name</label><input name="name" required />
                <label>Objective</label><input name="objective" placeholder="Fill no-show open play spots quickly" />
                <label>CTA</label><input name="cta" placeholder="If you're nearby, want to come play?" />
                <label>Response Prompt (playbook)</label><textarea name="response_prompt" rows="2" placeholder="If yes: confirm ETA. If no: ask waitlist opt-in."></textarea>
                <label>Campaign Tags (comma-separated, supports type:value)</label>
                <input name="campaign_tags" placeholder="campaign:open_play_fill,goal:fill_no_show,weekday:wed" />
                <label>Recipients (one per line: Name|Phone|optional_tags)</label>
                <textarea name="recipients" rows="8" placeholder="Rob Swanson|3035209551|group:wed_waitlist,cohort:3_5_plus&#10;Erika Yaroni|7322663659|group:wed_waitlist"></textarea>
                <label>Intended action label (optional)</label><input name="intended_action" placeholder="drive same-day arrivals" />
                <p><button type="submit">Create Campaign</button></p>
              </form>
            </div>

            <div class="card">
              <h2>Campaigns</h2>
              <table>
                <thead>
                  <tr><th>ID</th><th>Name</th><th>Objective</th><th>Recipients</th><th>Sent</th><th>Replied</th><th>Reply %</th><th>Yes/No/Maybe</th></tr>
                </thead>
                <tbody>
                  {''.join(campaign_rows) if campaign_rows else '<tr><td colspan="8">No campaigns yet</td></tr>'}
                </tbody>
              </table>
            </div>

            <div class="card">
              <h2>Cohort Breakdown (by contact tags)</h2>
              <table>
                <thead>
                  <tr><th>Tag Type</th><th>Tag Value</th><th>Touched</th><th>Replied</th><th>Reply %</th><th>Yes %</th></tr>
                </thead>
                <tbody>
                  {''.join(cohort_rows_html) if cohort_rows_html else '<tr><td colspan="6">No cohort data yet</td></tr>'}
                </tbody>
              </table>
            </div>
          </body>
        </html>
        """
        self._send_html(page)

    def _render_campaign(self, campaign_id: int) -> None:
        with get_conn(self.db_path) as conn:
            campaign, recipients, tags = campaign_detail(conn, campaign_id)
        if campaign is None:
            return self._send_html("<h1>Campaign not found</h1><p><a href='/'>Back</a></p>", status=404)

        recipients_html = []
        for r in recipients:
            full_name = f"{r['first_name']} {r['last_name']}".strip() or r["phone"]
            recipients_html.append(
                f"""
                <tr>
                  <td>{h(full_name)}</td>
                  <td>{h(r["phone"])}</td>
                  <td>{h(r["send_status"])}</td>
                  <td>{h(r["sent_at"] or '')}</td>
                  <td>{h(r["reply_status"])}</td>
                  <td>{h((r["last_reply_text"] or '')[:120])}</td>
                  <td>{h(r["last_reply_at"] or '')}</td>
                </tr>
                """
            )

        tag_text = ", ".join(f"{t['tag_type']}:{t['tag_value']}" for t in tags)
        page = f"""
        <html>
          <head>
            <title>Campaign #{campaign["id"]}</title>
            <style>
              body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 24px; }}
              .card {{ border: 1px solid #ddd; border-radius: 10px; padding: 14px; margin-bottom: 18px; }}
              table {{ width: 100%; border-collapse: collapse; }}
              th, td {{ border: 1px solid #e1e1e1; padding: 8px; text-align: left; vertical-align: top; }}
              input, textarea, select {{ width: 100%; box-sizing: border-box; }}
              button {{ padding: 8px 12px; }}
            </style>
          </head>
          <body>
            <p><a href="/">← Back</a></p>
            <h1>Campaign #{campaign["id"]}: {h(campaign["name"])}</h1>
            <div class="card">
              <p><strong>Objective:</strong> {h(campaign["objective"])}</p>
              <p><strong>CTA:</strong> {h(campaign["cta"])}</p>
              <p><strong>Response Prompt:</strong> {h(campaign["response_prompt"])}</p>
              <p><strong>Campaign tags:</strong> {h(tag_text)}</p>
              <form method="post" action="/campaigns/log_send" style="margin-bottom:8px;">
                <input type="hidden" name="campaign_id" value="{campaign["id"]}" />
                <button type="submit">Log send now for all pending recipients</button>
              </form>
              <form method="post" action="/campaigns/clone">
                <input type="hidden" name="campaign_id" value="{campaign["id"]}" />
                <button type="submit">Clone campaign (rerun scaffold)</button>
              </form>
            </div>

            <div class="card">
              <h2>Record Reply</h2>
              <form method="post" action="/campaigns/record_reply">
                <input type="hidden" name="campaign_id" value="{campaign["id"]}" />
                <label>Phone</label><input name="phone" placeholder="3035209551" required />
                <label>Reply status</label>
                <select name="reply_status">
                  <option value="yes">yes</option>
                  <option value="no">no</option>
                  <option value="maybe">maybe</option>
                  <option value="unknown">unknown</option>
                  <option value="none">none</option>
                </select>
                <label>Reply text</label><textarea name="reply_text" rows="2"></textarea>
                <label>Waitlist opt-in</label>
                <select name="waitlist_opt_in">
                  <option value="">(leave unchanged)</option>
                  <option value="1">yes</option>
                  <option value="0">no</option>
                </select>
                <label>Min notice minutes</label><input name="min_notice_minutes" placeholder="30" />
                <label>Auto-booking opt-in</label>
                <select name="auto_booking_opt_in">
                  <option value="">(leave unchanged)</option>
                  <option value="1">yes</option>
                  <option value="0">no</option>
                </select>
                <p><button type="submit">Save reply</button></p>
              </form>
            </div>

            <div class="card">
              <h2>Recipients</h2>
              <table>
                <thead>
                  <tr><th>Name</th><th>Phone</th><th>Send Status</th><th>Sent At</th><th>Reply</th><th>Last Reply Text</th><th>Last Reply At</th></tr>
                </thead>
                <tbody>
                  {''.join(recipients_html) if recipients_html else '<tr><td colspan="7">No recipients</td></tr>'}
                </tbody>
              </table>
            </div>
          </body>
        </html>
        """
        self._send_html(page)

    def _create_campaign(self) -> None:
        form = self._post_form()
        name = (form.get("name") or "").strip()
        objective = (form.get("objective") or "").strip()
        cta = (form.get("cta") or "").strip()
        response_prompt = (form.get("response_prompt") or "").strip()
        campaign_tags_raw = (form.get("campaign_tags") or "").strip()
        recipients_raw = (form.get("recipients") or "").strip()
        intended_action = (form.get("intended_action") or "").strip()
        if not name:
            raise ValueError("Campaign name is required")

        recipients = parse_recipients_input(recipients_raw) if recipients_raw else []
        with get_conn(self.db_path) as conn:
            cur = conn.execute(
                """
                INSERT INTO campaigns(name, objective, cta, response_prompt, channel, created_at)
                VALUES (?, ?, ?, ?, 'imessage_sms', ?)
                """,
                (name, objective, cta, response_prompt, now_iso()),
            )
            campaign_id = int(cur.lastrowid)

            for tag_type, tag_value in parse_tags(campaign_tags_raw):
                conn.execute(
                    """
                    INSERT INTO campaign_tags(campaign_id, tag_type, tag_value, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (campaign_id, tag_type, tag_value, now_iso()),
                )

            for recipient in recipients:
                contact_id = upsert_contact(
                    conn,
                    recipient["first_name"],
                    recipient["last_name"],
                    recipient["phone"],
                )
                conn.execute(
                    """
                    INSERT OR IGNORE INTO campaign_contacts(
                      campaign_id, contact_id, intended_action, send_status, created_at
                    )
                    VALUES (?, ?, ?, 'pending', ?)
                    """,
                    (campaign_id, contact_id, intended_action, now_iso()),
                )
                for tag_type, tag_value in recipient["tags"]:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO contact_tags(contact_id, tag_type, tag_value, created_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (contact_id, tag_type, tag_value, now_iso()),
                    )
        self._redirect(f"/campaign?id={campaign_id}")

    def _log_send(self) -> None:
        form = self._post_form()
        campaign_id = int(form.get("campaign_id", "0"))
        with get_conn(self.db_path) as conn:
            conn.execute(
                """
                UPDATE campaign_contacts
                SET send_status = 'sent', sent_at = COALESCE(sent_at, ?)
                WHERE campaign_id = ? AND send_status = 'pending'
                """,
                (now_iso(), campaign_id),
            )
        self._redirect(f"/campaign?id={campaign_id}")

    def _record_reply(self) -> None:
        form = self._post_form()
        campaign_id = int(form.get("campaign_id", "0"))
        phone = "".join(ch for ch in (form.get("phone") or "") if ch.isdigit())
        reply_status = (form.get("reply_status") or "unknown").strip().lower()
        reply_text = (form.get("reply_text") or "").strip()
        waitlist_opt_in = (form.get("waitlist_opt_in") or "").strip()
        min_notice_minutes = (form.get("min_notice_minutes") or "").strip()
        auto_booking_opt_in = (form.get("auto_booking_opt_in") or "").strip()

        if len(phone) < 10:
            raise ValueError("Phone must be full 10+ digits")
        if reply_status not in {"yes", "no", "maybe", "unknown", "none"}:
            raise ValueError("Invalid reply_status")

        with get_conn(self.db_path) as conn:
            contact = conn.execute(
                "SELECT id FROM contacts WHERE phone = ?", (phone,)
            ).fetchone()
            if not contact:
                raise ValueError(f"Phone {phone} is not in contacts")
            contact_id = int(contact["id"])
            row = conn.execute(
                """
                SELECT id FROM campaign_contacts
                WHERE campaign_id = ? AND contact_id = ?
                """,
                (campaign_id, contact_id),
            ).fetchone()
            if not row:
                raise ValueError("That phone is not attached to this campaign")

            conn.execute(
                """
                UPDATE campaign_contacts
                SET reply_status = ?, last_reply_text = ?, last_reply_at = ?, send_status = 'sent'
                WHERE campaign_id = ? AND contact_id = ?
                """,
                (reply_status, reply_text, now_iso(), campaign_id, contact_id),
            )

            pref = conn.execute(
                "SELECT contact_id FROM contact_preferences WHERE contact_id = ?",
                (contact_id,),
            ).fetchone()
            if waitlist_opt_in or min_notice_minutes or auto_booking_opt_in:
                current = conn.execute(
                    """
                    SELECT waitlist_opt_in, min_notice_minutes, auto_booking_opt_in
                    FROM contact_preferences WHERE contact_id = ?
                    """,
                    (contact_id,),
                ).fetchone()
                cur_waitlist = int(current["waitlist_opt_in"]) if current else 0
                cur_notice = current["min_notice_minutes"] if current else None
                cur_auto = int(current["auto_booking_opt_in"]) if current else 0
                new_waitlist = (
                    int(waitlist_opt_in)
                    if waitlist_opt_in in {"0", "1"}
                    else cur_waitlist
                )
                new_notice = (
                    int(min_notice_minutes)
                    if min_notice_minutes.isdigit()
                    else cur_notice
                )
                new_auto = (
                    int(auto_booking_opt_in)
                    if auto_booking_opt_in in {"0", "1"}
                    else cur_auto
                )
                if pref:
                    conn.execute(
                        """
                        UPDATE contact_preferences
                        SET waitlist_opt_in = ?, min_notice_minutes = ?, auto_booking_opt_in = ?, updated_at = ?
                        WHERE contact_id = ?
                        """,
                        (new_waitlist, new_notice, new_auto, now_iso(), contact_id),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO contact_preferences(contact_id, waitlist_opt_in, min_notice_minutes, auto_booking_opt_in, updated_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (contact_id, new_waitlist, new_notice, new_auto, now_iso()),
                    )
        self._redirect(f"/campaign?id={campaign_id}")

    def _clone_campaign(self) -> None:
        form = self._post_form()
        source_campaign_id = int(form.get("campaign_id", "0"))
        with get_conn(self.db_path) as conn:
            source = conn.execute(
                "SELECT * FROM campaigns WHERE id = ?", (source_campaign_id,)
            ).fetchone()
            if not source:
                raise ValueError("Source campaign not found")
            new_name = f"{source['name']} (rerun)"
            cur = conn.execute(
                """
                INSERT INTO campaigns(name, objective, cta, response_prompt, channel, created_at, source_campaign_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_name,
                    source["objective"],
                    source["cta"],
                    source["response_prompt"],
                    source["channel"],
                    now_iso(),
                    source_campaign_id,
                ),
            )
            new_campaign_id = int(cur.lastrowid)

            tags = conn.execute(
                "SELECT tag_type, tag_value FROM campaign_tags WHERE campaign_id = ?",
                (source_campaign_id,),
            ).fetchall()
            for t in tags:
                conn.execute(
                    """
                    INSERT INTO campaign_tags(campaign_id, tag_type, tag_value, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (new_campaign_id, t["tag_type"], t["tag_value"], now_iso()),
                )

            recips = conn.execute(
                """
                SELECT contact_id, intended_action
                FROM campaign_contacts
                WHERE campaign_id = ?
                """,
                (source_campaign_id,),
            ).fetchall()
            for r in recips:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO campaign_contacts(
                      campaign_id, contact_id, intended_action, send_status, created_at
                    )
                    VALUES (?, ?, ?, 'pending', ?)
                    """,
                    (new_campaign_id, r["contact_id"], r["intended_action"], now_iso()),
                )
        self._redirect(f"/campaign?id={new_campaign_id}")

    def log_message(self, format: str, *args) -> None:
        # Keep terminal output concise.
        _ = format, args


def serve(host: str, port: int, db_path: str) -> None:
    init_db(db_path)
    handler_cls = CampaignOpsHandler
    handler_cls.db_path = db_path
    server = ThreadingHTTPServer((host, port), handler_cls)
    print(f"Campaign Ops MVP running on http://{host}:{port}")
    print(f"SQLite DB: {db_path}")
    print("Ctrl+C to stop.")
    server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local Campaign Ops MVP webview.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Bind port (default 8765)")
    parser.add_argument("--db", default=DB_DEFAULT, help="SQLite DB path")
    args = parser.parse_args()
    serve(args.host, args.port, os.path.abspath(args.db))


if __name__ == "__main__":
    main()
