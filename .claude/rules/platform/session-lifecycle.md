# Session Lifecycle — Simplified

## Session Commands (consolidated)

| Command | When | What it does |
|---------|------|-------------|
| `/savesession` | Anytime, or on exit | Creates/updates DevSession in DB with summary, pending, decisions, gotchas |

## Retired Commands (DO NOT USE)
- `/park` — replaced by `/savesession`
- `/closesession` — replaced by `/savesession`
- `/handover` — replaced by `/savesession` (data in DB, not markdown files)
- `/startsession` — use `/initiative` or just start working

## How It Works

### Starting a session
- The `session-start-reminder.sh` hook fires on first message
- `/initiative` loads context: latest DevSession from DB, assigned features, KB pages
- If no `/initiative`, just start working — `/savesession` creates the record when called

### During a session
- Work normally
- Call `/savesession` manually if you want to checkpoint
- SessionKey (GUID) is stored in conversation memory after first save

### Ending a session
- User says "exit", "bye", "done" → remind them to run `/savesession`
- If user just closes → `auto-save-session.sh` Stop hook fires automatically
- The hook closes any active DevSession in the DB

### Session data goes to
- **product.DevSession** — human-readable summaries, shown in "My Sessions" UI
- **NOT** markdown files, NOT handover files, NOT KB pages

## Constants
- ProductId is always 1, UserId is always 1
- API: https://localhost:5050/api/v1
- Fallback: direct SQL via db-config.sh
