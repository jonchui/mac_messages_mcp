# Personal EA / Chief-of-Staff Spec — Messages from You (650-450-7174)

**Goal:** You talk to an AI agent (via a separate contact), and the agent sends iMessages **as you** (from 650-450-7174). No unapproved or placeholder messages. Everything tied to tasks (Notion/GitHub). Optionally: agent reaches out by text or call, uses MCPs, learns from your approvals.

---

## Technical reality (iMessage)

- **One Apple ID = one identity.** Your number 650-450-7174 is tied to your Apple ID. Any device signed into that Apple ID (this Mac, your iPhone) can send/receive as that number. There is no “second sender” on the same number at the OS level.
- **What we have today:** This Mac runs the Messages MCP. When it sends via the Messages app (AppleScript), it uses whatever account is signed in on this Mac. **If this Mac is signed into iMessage with your Apple ID (650-450-7174), then messages already come from 650-450-7174.** No extra trick needed for “send from my number.”
- **The real design choice:** How **you** talk to the agent (inbound), and how we **approve** outbound so nothing goes out unapproved.

---

## Inbound: how you talk to the agent

You want a “different contact” so the agent has a dedicated inbox for **you** (instructions, approvals, context) while the agent sends to **others** from 650-450-7174.

| Option | Inbound (you → agent) | Outbound (agent → your contacts) | Pros / cons |
|--------|------------------------|----------------------------------|-------------|
| **A) Email** | You email e.g. `jonsAIBot@jonchui.com` (or `agent@jonchui.com`). Mac or cloud service receives, agent reads. | Agent sends via this Mac’s Messages → 650-450-7174. | ✅ One Apple ID, one number. ✅ No extra SIM. ❌ You use email, not iMessage, to command. |
| **B) Second number (dedicated “agent line”)** | You iMessage a second number (e.g. cheap VoIP/SIM). That Mac or service receives; agent reads. | Agent still sends to the world from **this** Mac (your Apple ID) → 650-450-7174. | ✅ You text the agent like a contact. ❌ Need to run something that receives that second number (second Mac, or gateway). |
| **C) Same number, same thread** | You and agent share 650-450-7174. You give orders in a special thread (e.g. a group with only you + an email, or a “note to self” pattern). | Same Mac, same number. | ✅ No new identity. ❌ Harder to separate “me” vs “agent” in one inbox; easy to get messy. |

**Recommendation for P1:** **Option A (email).** You email the agent; agent runs on this Mac (or a server that can drive this Mac’s Messages). All outbound to contacts goes from this Mac → 650-450-7174. No second phone/SIM, no second iMessage identity.

**P2:** Add Option B (second number) if you want to “text the agent” like a contact and have a clear “agent line” in iMessage.

---

## Outbound: always from you, never unapproved

- **From number:** All agent-sent messages to your contacts must go through **this Mac’s Messages app** signed in as your Apple ID (650-450-7174). Then they already show as from 650-450-7174.
- **Approval rule:** No message is sent unless:
  - It was explicitly approved by you (approve button, or “Y” in a structured reply), **and**
  - It contains no placeholders (e.g. no `[sdfsdf]`, `[NAME]`, `[TIME]`). Reject or edit those.
- **Learning (P2):** Store every approved message and context (task, thread, contact). Use for tone/style hints and future suggestions (RAG or fine-tuning).

---

## Task linkage (Notion / GitHub)

- **P1:** Every “campaign” or batch (e.g. “Playdate asks – Val, Rebecca, Meghan, Sherri”) has a **task id**: Notion page URL or GitHub issue (e.g. `notion:abc123`, `github:owner/repo#42`). Stored with the send log. Replies and follow-ups are associated with that task so you can see “this thread belongs to this goal.”
- **P2:** Bi-directional sync: task in Notion (or GitHub) shows “Messages: 4 sent, 2 replied, 1 approved reply pending.” Optional deep link from a message thread back to the task (for you only, when you want it).

**Task types (examples):** Scheduling (e.g. weekly Sydney playdates), event feedback (e.g. Picklr/work), co-parenting (e.g. asks to Vicki). Central system (Notion or GitHub) holds tasks; agent only references them by id and optionally updates status.

---

## P1 (bare minimum) — spec

1. **Inbound**
   - You interact with the agent via **email** (e.g. `jonsAIBot@jonchui.com` or `agent@jonchui.com`). No second iMessage identity required.
   - Agent runs in a context that can read that inbox (this Mac with a mail check, or a cloud worker that fetches mail and triggers the same logic).

2. **Outbound**
   - All messages to your contacts are sent **only** via this Mac’s Messages app (signed in as 650-450-7174). So they come from 650-450-7174.
   - **Approval gate:** Every proposed message is shown to you (in email, or in a simple dashboard/Notion block) with Approve / Edit / Reject. Only approved messages are sent. Any message containing placeholders like `[…]` is blocked (rejected or sent back for edit).

3. **Tasks**
   - Every send is tied to a **task id** (Notion or GitHub). You (or the agent) supply it when creating the batch. Stored in a send log (e.g. `data/` or DB) with thread/contact and task_id. No sync to Notion/GitHub required in P1; just storage and retrieval.

4. **No “bot identity” in threads**
   - P1 does not add `jonsAIBot@jonchui.com` (or any bot) to recipient threads. Everything to contacts is from 650-450-7174 only.

**Deliverables P1**

- Doc/spec: “Inbound = email to jonsAIBot@jonchui.com; outbound = this Mac Messages (650-450-7174); approval required; task_id on every batch.”
- Approval flow in code: propose message → show to user (email or link) → record Approve/Edit/Reject → send only if Approved and no placeholders.
- Placeholder check: block send if body contains `[` … `]` (or a small allowlist for known good tags).
- Data model: send log with (task_id, contact, message, status, approved_at, sent_at). Optional: link to Notion/GitHub in UI or in the email you get.

---

## P2 (nice to have / next step)

1. **Inbound**
   - **Second contact for the agent:** Add ability to “text the agent” (e.g. second number or jonsAIBot@jonchui.com in iMessage). So you can talk to the agent via iMessage as well as email.

2. **Learning**
   - Store approved messages and context; use for “how Jon writes” (tone, length, structure). Suggest replies that match your style; improve over time (e.g. RAG over approved history).

3. **Task sync**
   - Notion (or GitHub) as source of truth: task shows “Messages: N sent, M replied, K pending approval.” Option to open task from a message thread (for you).

4. **EA / chief-of-staff behavior**
   - Proactive suggestions (e.g. “Sydney playdate – no reply from Val in 48h, suggest follow-up?”).
   - Priority ordering by context (work vs family vs Picklr).
   - Agent can **reach out to you**: by text (iMessage to 650-450-7174 or to the “agent line” if present) or by **call** (Twilio or similar to 650-450-7174) when escalation is needed.

5. **MCPs**
   - Agent (same process or same “EA” runtime) has access to your important MCPs (e.g. GitHub, Notion, calendar, Hostinger, etc.). Can read/write tasks, create issues, check calendar when proposing times.

6. **Optional “bot in thread”**
   - If you ever want recipients to know it’s the bot: add `jonsAIBot@jonchui.com` (or similar) to specific threads as a participant. P2 only; not default.

---

## Architecture options (concise)

### Option 1: Mac-only, email inbound (P1)

- **Inbound:** Email to `jonsAIBot@jonchui.com` (or similar). This Mac runs a mail checker (e.g. IMAP poll or Mail.app rule + script) and turns new emails into “agent tasks.”
- **Agent:** Runs on this Mac (Cursor when you’re planning; or a background script/daemon that uses the same MCP or same `messages.py`).
- **Outbound:** This Mac’s Messages app (AppleScript / MCP) → 650-450-7174. Approval flow: proposed message → email to you with Approve/Edit/Reject link or reply-with-Y/N → only then send.
- **Tasks:** task_id (Notion/GitHub) stored with each batch; optional link in approval email.

### Option 2: Mac + second Mac for “agent line” (P2)

- **Inbound:** Second Mac (or a VM/always-on Mac) signed into iMessage with **only** `jonsAIBot@jonchui.com` (or a second number). You iMessage that; that Mac receives. A process on that Mac (or this Mac polling that Mac’s DB, if shared storage) reads new messages and runs the agent.
- **Outbound:** Still **this** Mac (your main Apple ID, 650-450-7174) sends to your contacts. So: “agent line” = receive only (or receive + reply to **you** on that line); “your number” = send to everyone else from this Mac.
- **Problem you noted:** If the second Mac only has the bot identity, it can’t send as 650-450-7174. So outbound must stay on the main Mac. That’s consistent with Option 2 above.

### Option 3: Cloud worker + this Mac as “send gateway”

- **Inbound:** Email or API hits a cloud worker (e.g. Vercel/Cloudflare + your MCP server, or a small backend). Worker decides what to do and, for sends, calls an API on this Mac (or a relay on this Mac) that runs the same `send_message` logic.
- **Outbound:** This Mac runs a tiny “gateway” (HTTP or MCP over stdio/SSE) that only accepts “send this message” requests from the cloud after approval. Gateway uses Messages on this Mac → 650-450-7174. Approval can happen in cloud (you click in Notion or email), then cloud asks Mac to send.

---

## Your two “solution ideas” — clarified

1. **“Mac receives from a given EMAIL; sends via PHONE”**  
   - Mac is signed in to iMessage with your Apple ID (650-450-7174). So “sends via PHONE” = sends via Messages on that Mac = from 650-450-7174. Receiving “from a given email” = you email the agent at jonsAIBot@jonchui.com; Mac (or a service) reads that inbox. No conflict: inbound = email, outbound = iMessage from same number. **This is Option 1 (P1).**

2. **“Different Mac that only gets/receives on one phone”**  
   - That second Mac would have a **different** number or email (the “agent line”). It can’t send as 650-450-7174. So we don’t use that Mac for sending to your contacts; we use it only for **you** to talk to the agent. Sending to contacts still happens on your main Mac. So: second Mac = inbound only (or inbound + replies to you on the agent line). Main Mac = outbound from 650-450-7174. **This is Option 2 (P2).**

---

## Summary table

| Requirement | P1 | P2 |
|-------------|----|----|
| Messages to contacts from 650-450-7174 | ✅ This Mac Messages | Same |
| Never send unapproved / no placeholders | ✅ Approval gate + block `[...]` | Same + learn from approvals |
| You talk to agent via “different contact” | ✅ Email (jonsAIBot@jonchui.com) | + iMessage to agent line (second number or bot email) |
| Each message tied to a task | ✅ task_id (Notion/GitHub) stored | + Sync status to Notion/GitHub; link from thread to task |
| Agent reaches out: text | — | ✅ iMessage to you (or agent line) |
| Agent reaches out: call | — | ✅ Twilio etc. to 650-450-7174 |
| Connect to MCPs (GitHub, Notion, etc.) | Same Cursor/MCP stack when you’re in planning | + Used by background EA for proactive tasks |
| EA / chief-of-staff (priority, context, proactive) | — | ✅ |

---

## Suggested next steps

1. **Confirm P1 scope:** Email inbound, this Mac outbound (650-450-7174), approval gate, placeholder block, task_id on every batch. No second number yet.
2. **Implement approval flow** in this repo: propose → show (email or link) → Approve/Edit/Reject → send only if approved and no `[...]`.
3. **Add task_id** to `playdate_batch_sent.json` (or DB) and to any new “campaign” send flow; document format (e.g. `notion:page_id`, `github:owner/repo#N`).
4. **Design email inbound:** Either Mail.app rule + script on this Mac, or IMAP poll script, or cloud webhook that receives and enqueues “agent tasks” that this Mac processes.
5. **P2 backlog:** Second number/agent line, learning from approvals, Notion/GitHub sync, proactive EA, reach out by text/call, MCP integration for EA.

If you want, next we can turn this into a **Notion page** or **GitHub project** with the same P1/P2 breakdown and checkboxes.
