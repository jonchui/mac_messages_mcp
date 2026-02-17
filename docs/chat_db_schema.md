# chat.db schema reference (from custom DB backup – Mon Feb 16, 2026)

Concise reference for writing SQL against `~/Library/Messages/chat.db`.

---

## Core tables

### **message**
| Column         | Notes                          |
|----------------|--------------------------------|
| ROWID          | PK                             |
| guid           | Unique message id              |
| text           | Plain text body                |
| handle_id      | FK → handle.ROWID              |
| attributedBody | Rich/blob body                 |
| date           | Apple epoch (nanoseconds)       |
| **date_read**  | Read timestamp (NULL = unread)  |
| date_delivered| Delivered timestamp            |
| is_from_me     | 1 = sent by you, 0 = incoming  |
| is_delivered   |                                |
| is_finished    |                                |
| service        | e.g. iMessage, SMS             |
| account        |                                |
| type           |                                |

### **handle**
| Column  | Notes              |
|---------|--------------------|
| ROWID   | PK                 |
| id      | Phone/email string |
| country |                    |
| service |                    |

### **chat**
| Column    | Notes        |
|-----------|-------------|
| ROWID     | PK          |
| guid      |             |
| chat_identifier |     |
| room_name | Group chat  |
| display_name | Chat name |
| service_name |        |

### **chat_message_join**
| Column      | Notes   |
|-------------|--------|
| chat_id     | → chat |
| message_id  | → message |
| message_date|         |

### **chat_handle_join**
| Column   | Notes   |
|----------|---------|
| chat_id  | → chat  |
| handle_id| → handle|
| is_from_me |       |
| **is_read** | Per-chat read state |
| cache_roomnames |   |

### **message_attachment_join**
| Column       | Notes |
|--------------|-------|
| message_id   | → message |
| attachment_id| → attachment |

### **attachment**
| Column   | Notes |
|----------|--------|
| ROWID    | PK    |
| guid     |       |
| filename |       |
| mime_type|       |
| is_outgoing |     |

---

## Useful patterns

- **Total message count:** `SELECT COUNT(*) FROM message;`
- **Recent messages (with handle):** join `message` ↔ `handle` on `handle_id = handle.ROWID`, filter on `message.date`.
- **Unread incoming:** `message.is_from_me = 0 AND message.date_read IS NULL`
- **By chat:** use `chat_message_join` to link `message` ↔ `chat`; use `chat.display_name` or `chat.room_name` for labels.
