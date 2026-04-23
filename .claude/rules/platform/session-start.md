---
globs: "**/*"
---

# Session Start — Auto-Orient + Auto-Takeover

At the start of every new conversation, you MUST do the following before writing any code:

## Step 1: Load Last Session Context from Database

```bash
source .claude/db-config.sh
JWT=$(get_jwt 2>/dev/null)
# Get latest DevSession
curl -sk "$API_BASE/products/1/dev-sessions" -H "Authorization: Bearer $JWT" 2>/dev/null | head -100
```

If API is unavailable, query directly:
```bash
source .claude/db-config.sh
run_sql "SELECT TOP 1 Id, Title, Status, DoneItems, PendingItems, DecisionsMade, Gotchas, BranchName
FROM product.DevSession WHERE ProductId = 1 AND UserId = 1 AND IsDeleted = 0
ORDER BY Id DESC"
```

**What to look for:**
- **PendingItems** — this is what to work on first
- **DecisionsMade** — respect these, don't reverse them
- **Gotchas** — avoid these traps

If no DevSession exists, this is a fresh start — proceed to Step 2.

## Step 2: Read Core Documentation (parallel reads)
1. `CLAUDE.md` — Architecture, database, auth, build commands, modules
2. `.claude/RULES.md` — Git workflow, branching, commits, PRs, issue workflow
3. `.claude/rules/dotnet-patterns.md` — .NET 8 Clean Architecture, endpoint checklist
4. `.claude/rules/novara-api-patterns.md` — PRODUCTION QUALITY rules, banned patterns
5. `.claude/rules/database.md` — SQL Server, Dapper, SpNames.cs, novara schema
6. `.claude/rules/systems-thinking.md` — Multi-product ecosystem, agent architecture
7. `.claude/rules/plugin-architecture.md` — Plugin SDK, manifest, lifecycle
8. `.claude/rules/bug-investigation.md` — DB-up investigation protocol (5 layers)
9. `.claude/rules/bug-fix-verification.md` — Mandatory end-to-end testing
10. `.claude/rules/quality-framework.md` — Enterprise quality: Prevent, Detect, Learn
11. KB slug `entity-terminology` — CRITICAL: maps entity names across DB/SP/API/frontend (prevents naming confusion)

## Step 3: Quick Codebase Scan (parallel)
```bash
git branch --show-current && git log --oneline -5
git status --short
ls src/Novara.Api/Controllers/
ls src/Novara.Application/Services/
```

## Step 4: Print Status Card

If handover exists, include it:
```
╔════════════════════════════════════════════════════╗
║  Novara API Session Ready                          ║
╠════════════════════════════════════════════════════╣
║  Branch:      <current branch>                     ║
║  Last commit: <short hash> <message>               ║
║  Uncommitted: <count> files                        ║
║  Controllers: <count>  Services: <count>           ║
║  DB:          NovaraPlatformDB + NovaraWorkspaceProductDB @ 20.219.116.10    ║
╠════════════════════════════════════════════════════╣
║  HANDOVER from <name> (<date>):                    ║
║  Done: <summary>                                   ║
║  Pending: <first item> ← START HERE                ║
║  Gotchas: <key warning>                            ║
╚════════════════════════════════════════════════════╝
```

Then say: **"Ready. What are we working on?"**
If handover had pending items: **"Picking up from <name>'s handover. First pending: <item>."**

## Quick Reference (always active)

**Architecture:** .NET 10 Gateway + 32 modules, per-module schemas
**Database:** NovaraPlatformDB (auth/routing) + NovaraWorkspaceProductDB (per-module schemas) @ 20.219.116.10 via Dapper
**Function Naming:** Per-module SpNames.cs — `"issues.Upsert"`, `"roadmap.GetFeaturesByTrack"`, `"platform.GetProducts"`
**Permissions:** All in `Permissions.cs`
**Build:** `dotnet build` | **Run:** `dotnet run --project src/Novara.Shell.Api` → https://localhost:5050
**Frontend:** `../NovaraWorkspaceShell/novara-shell/web/` (Angular 21, http://localhost:4200)
**Product DB Files:** `../NovaraWorkspaceProductDB/` (per-module schemas + productcore + productmeta)
**Platform DB Files:** `../../NovaraPlatformDB/` (platform + viber schemas)

**Adding an endpoint:**
1. Add DTO in Contracts
2. Add interface in Application/Interfaces
3. Add service in Application/Services
4. Add SP name in SpNames.cs
5. Add controller endpoint in Api/Controllers
6. Register in ServiceRegistration.cs

**Non-negotiable:**
- Every feature end-to-end: Controller → Service → Function → PostgreSQL
- No mock data, no empty catch fallbacks, no fake AI responses
- All SP names via SpNames.cs (no magic strings)
- All permissions via Permissions.cs
- Domain depends on NOTHING
- Per-module schemas only (issues, roadmap, etc.) — never `product` for new objects, never `novara`, never `collab`, never `dbo`
- Branch names: fix1, feature1 (no slashes)
