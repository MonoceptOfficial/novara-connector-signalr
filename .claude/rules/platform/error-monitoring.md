---
globs: "**/*.cs"
---

# Error Log Monitoring — Smart Testing Workflow

## Before starting work, capture baseline:
sqlcmd query: SELECT 'Backend' AS Source, COUNT(*) AS Unresolved FROM platform.ErrorLog WHERE IsResolved = 0 UNION ALL SELECT 'Frontend', COUNT(*) FROM platform.FrontendErrorLog WHERE IsResolved = 0

## After testing, check NEW errors only (last 5 min):
sqlcmd query: SELECT 'BE' AS Src, Level, LEFT(Message,60) AS Msg, PluginName FROM platform.ErrorLog WHERE IsResolved = 0 AND CreatedAtUtc >= DATEADD(MINUTE, -5, GETUTCDATE()) UNION ALL SELECT 'FE', Level, LEFT(Message,60), Source FROM platform.FrontendErrorLog WHERE IsResolved = 0 AND CreatedAtUtc >= DATEADD(MINUTE, -5, GETUTCDATE())

## STOP if same error repeats 3+ times — fix root cause first.
## After fixing, mark resolved with note.
## Query unresolved: GET /admin/errors?isResolved=false

## Known Noise (do NOT log these as errors):
- `Unexpected end of request content` on `/sessions/heartbeat` — client disconnect, normal behavior
- Transient SQL connectivity errors — retry automatically, only alert if sustained > 5 min
- `GetPipelinesByProduct` — stub SP, returns empty until publish pipeline is built

## When creating new SPs:
- Always check ALL columns have matching INSERT values (e.g., ReceivedAt was missing from InsertHeartbeat)
- Always verify NOT NULL columns have DEFAULT or are explicitly populated
- Always use INT for @UserId parameters, never NVARCHAR

## Frontend logger protections:
- Dedup: same error once per 5 min
- Circuit breaker: 3 fails = stop 10 min
- Cap: 50 errors per page load
- Self-exclusion: skip /admin/errors
- Batch: 3 sec debounce
- Skip: 401s and status 0
