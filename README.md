# Channel Sync Runner

A small GitHub Actions job that copies new posts between Telegram channels you own,
using a Telethon user session. Text, photos, videos (streamable), documents and albums
are re-sent as new messages in their original order.

## How it works

1. Reads the last synced message ID per source channel from a private HTTP endpoint
   (`GET /internal/sync/state`). With no checkpoint, it starts from the latest 5 posts.
2. Downloads media (512 KB chunks, 4–8 parallel parts) while the previous post is
   uploading — a bounded queue of 2 keeps disk usage low. Temp files are deleted
   right after each send.
3. After every post/album it stores the new checkpoint (`POST /internal/sync/state`).

Runs every 6 hours, on `repository_dispatch` (`tg_sync`) and manually.

## Configuration

All settings are repository **secrets** (Settings → Secrets and variables → Actions):

| Secret | Description |
|---|---|
| `TG_API_ID`, `TG_API_HASH` | Telegram API credentials |
| `TG_SESSION` | Telethon `StringSession` string |
| `SYNC_MAP` | JSON list: `[{"source": <id>, "target": <id>}]` |
| `WORKER_URL` | Base URL of the state endpoint |
| `INTERNAL_API_SECRET` | Bearer token for the state endpoint |

## Privacy

Workflow logs in a public repo are public. The runner prints only anonymous summaries
such as `Channel #1: synced 4 items` — never IDs, text, captions, usernames or file names.
Third-party logging is disabled and errors are reported by exception class only.
