# Poll for replies (no webhook)

macOS does **not** expose a Messages webhook. You have two options:

1. **Poll on a schedule** (cron / launchd) — run the script every N minutes.
2. **"Local webhook"** — watch `~/Library/Messages/chat.db` for file changes; when it changes, run the poll script. That's the closest thing to a webhook (react to new activity on the DB).

---

## How often is polling happening?

**Right now: never automatically.** The script only runs when you run it (e.g. `uv run python scripts/poll_replies.py ...`). There is no built-in interval.

---

## How to poll automatically

### Option A: Schedule (cron or launchd)

Run the script every 5–10 minutes.

**cron (every 5 min):**
```bash
# Edit crontab: crontab -e
# Add (use your real path and phones):
*/5 * * * * cd /Users/jonchui/Documents/GitHub/mac_messages_mcp && uv run python scripts/poll_replies.py --sent 12 --phones "..." --names "..." --csv headcount.csv >> /tmp/poll_replies.log 2>&1
```

**launchd (macOS, every 5 min):**  
Create `~/Library/LaunchAgents/com.mac-messages-mcp.poll-replies.plist` that runs the same command on a `StartInterval` of 300.

### Option B: Watch chat.db (local "webhook")

When the Messages database file **changes** (new message, read receipt, etc.), run the poll script. No fixed interval — you react to activity.

- **Script:** `scripts/watch_chat_db_and_poll.py`  
  - Watches `~/Library/Messages/chat.db` mtime every 15 seconds.  
  - If it changed since last check, runs the poll logic (or subprocess `poll_replies.py`) with a 60s debounce so it doesn't run on every keystroke.  
- **Requires:** the script to be running in the background (e.g. in a terminal or as a launchd KeepAlive job).

There is no Apple API for "notify me when a new message arrives." Watching the DB file is the local equivalent of a webhook.

---

## How to poll (manual)

1. **MCP tools** from Cursor: `tool_get_recent_messages(hours=1, contact=...)`, `tool_get_unread_messages(limit=50)`.
2. **Script** `scripts/poll_replies.py`:
   - Takes `--phones`, `--names`, `--sent`, `--csv`, etc.
   - Fetches recent messages (default: since 6 AM today), picks latest reply per contact, classifies yes/no/mixed, prints headcount and suggested replies.

## Reply logic (yes/no/mixed)

- **Yes** (coming) → e.g. "Thanks! See you soon!"
- **No** (not coming) → e.g. "No problem, next time!"
- **Mixed** (one kid yes, one no) → e.g. "Got it, thanks for letting me know!"

You can later plug in your own tone (templates or LLM) and write to a DB for the SWISH ladder (who's in, skill level, etc.).

---

## Mobile approval (notify + yes/no from your phone)

So you can approve every suggested reply from your phone without Cursor/Poke/MCP on mobile:

1. **Poll and notify**  
   Run poll with `--notify` and `--notify-to <your_phone>` (e.g. your own number). You get **one iMessage** listing pending replies and numbers, e.g.:
   ```
   RSVP approval — reply with Y or N for each number (e.g. Y1 N2 Y3)
   1. Brian: "Thanks for getting back!"
   2. Christina: "No problem, next time!"
   Reply e.g. Y1 N2 Y3 = send #1, skip #2, send #3
   ```

2. **Reply from your phone**  
   In that same thread, reply with e.g. `Y1 N2 Y3` (Y = send, N = skip for #1, #2, #3). You can also use `1 0 1` (1 = send, 0 = skip).

3. **Process approvals**  
   On your Mac, run:
   ```bash
   uv run python scripts/approve_replies.py --from <your_phone>
   ```
   It reads your reply from that thread, sends the approved messages, and updates the CSV. Run it manually after you reply, or on a schedule (e.g. every 2 min) so approvals are applied quickly.

**Why this works without Poke/MCP on mobile:** Everything stays in iMessage. You get the approval request and reply in the same app; the script on the Mac (where MCP runs) does the sending. No need for Claude Code or Poke on your phone.
