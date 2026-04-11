# ChatGPT app vs API — and how to use the app from scripts

## Why the ChatGPT app doesn’t need an API key

In the **ChatGPT app** (or chat.openai.com in a browser) you’re logged in with your **account**. The app uses that session to talk to OpenAI; no API key is involved.  
The **OpenAI API** (api.openai.com) is a separate product for developers. It always uses an **API key** and is billed separately from a ChatGPT Plus subscription. There is no supported way to “call the ChatGPT app” from code without using the API.

So:

- **App**: session auth, no key, not designed for scripts.
- **API**: key-based, script-friendly, what `poll_replies.py --use-ai` uses.

---

## Option A: Use the API (recommended)

- Get a key from [platform.openai.com](https://platform.openai.com/api-keys).
- Set `OPENAI_API_KEY` and run e.g. `poll_replies.py --use-ai`.
- Works without the app open; consistent and reliable.

---

## Option B: Drive the ChatGPT app with AppleScript (optional)

If you really want to use the **app** (no API key) from a script, you can automate the **UI**: focus the app, paste the prompt, trigger Send, then read the response from the window. That only works when:

- The **ChatGPT app is open and frontmost** (or we bring it to front).
- The **UI layout** doesn’t change (AppleScript is tied to accessibility elements).

So it’s a “consistent way” only in the sense that you always use the same script; it remains brittle and unsupported.

### Minimal AppleScript approach

1. **Focus ChatGPT** and ensure the input area is visible.
2. **Paste** your prompt (e.g. the same text we’d send to the API).
3. **Trigger Send** (e.g. Cmd+Return or click the Send button).
4. **Wait** for the reply to appear (e.g. poll until new content shows).
5. **Read** the reply text from the response area.

We don’t ship a full implementation because it breaks when OpenAI changes the app’s UI. If you want to try it, use **Script Editor** or **System Events** to inspect the ChatGPT window (menu: Accessibility Inspector) and wire steps 2–5 to the actual elements. A single “ask ChatGPT” AppleScript can then be called from Python with `subprocess.run(["osascript", "-e", script])` or by calling an `.scpt` file.

### BetterTouchTool (BTT)

Some setups use **BetterTouchTool**’s built-in **ChatGPT action**, which exposes an AppleScript verb like `chat_gpt user "prompt"`. That goes through BTT’s integration (which may use an API key or the app under the hood). It’s another “consistent” option if you already use BTT, but it’s not “the app with no key” in a generic sense.

---

## Summary

| Goal                         | Approach                    |
|-----------------------------|-----------------------------|
| Reliable, no app open        | **API key** + `--use-ai`    |
| Use the app, no key         | **AppleScript UI automation** (app must be open; fragile) |
| Already use BTT             | **BTT ChatGPT action** (if available) |

For your RSVP/suggested-reply flow, the **API + `--use-ai`** path is the one we support and recommend.
