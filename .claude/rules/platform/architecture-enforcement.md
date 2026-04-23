# Architecture Enforcement — How the Guardrails Work

Novara is an AI-assisted engineering org. Most code is written by Claude (or with Claude's help). The single highest-impact place to enforce architecture is at the moment Claude writes the file — not later in code review.

This document explains the **enforcement stack**: what's checked, where, and how to fix violations when you hit them.

---

## The 4 enforcement layers

| Layer | Where | When it runs | What it catches |
|---|---|---|---|
| **L1: Rules** | `.claude/rules/platform/` | Claude reads at session start | Persuasion only — Claude usually follows |
| **L2: PreToolUse hook** | `.claude/hooks/check-module-boundaries.py` | Every Edit/Write/MultiEdit | Physical block — file is never written |
| **L3: Pre-commit hook** | `.husky/pre-commit` (planned) | `git commit` | Build + test must pass |
| **L4: CI architecture tests** | GitHub Actions + NetArchTest (planned) | Every PR | Backstop if hooks bypassed |

Each layer catches what the previous missed. **L2 is the most important** — it prevents bad code from ever existing on disk.

---

## Layer 2 — what the hook physically blocks

The hook (`check-module-boundaries.py`) runs on every `Edit`, `Write`, and `MultiEdit` from Claude. It only enforces inside **module folders** (`NovaraModules/novara-module-*/`). Edits in the Gateway, Shell, SDK, or test projects are skipped.

Files checked: `.cs`, `.ts`, `.sql`. Skipped: tests (`.Tests/`, `.Test/`, `.spec.`, `.test.`), migrations, generated files (openapi.yaml, asyncapi.yaml), `bin/`, `obj/`, `node_modules/`, etc.

### Rules that BLOCK (exit 2 — file not written)

| Rule ID | What it catches | How to fix |
|---|---|---|
| **R1-CROSS-MODULE-IMPORT-CS** | `using Novara.Module.X` from a different module | Use `IEventBus.PublishAsync()` for events; `ICrossModuleQuery.QueryAsync(...)` for read-only data |
| **R2-CROSS-MODULE-IMPORT-TS** | Angular `import ... from '@novara/module-X'` from a different module | Make HTTP call via `ApiService` instead — never import another module's components/services |
| **R3-HTTPCLIENT-CS** | Direct `HttpClient` use in module C# code | External calls go through Connectors (declare in manifest, consume via `IConnectorHandler`) |
| **R4-HTTPCLIENT-NG** | Direct `HttpClient` import in module Angular code | `import { ApiService } from '@novara/shell-sdk'` and call `this.api.moduleGet<T>(...)` |
| **R5-PLATFORM-DB-IN-PRODUCT-MODULE** | `IPlatformDbContext` in a product-scoped module | Use `productcore.user`/`productcore.product` synced views via `IModuleDbContext`. Settings: `IModuleSettingsStore` |
| **R6-RAW-INLINE-SQL** | `connection.ExecuteAsync("SELECT ...")` etc. | Create a database function, add to `Constants/SpNames.cs`, call via `ExecuteProcedureAsync` |
| **R8-HARDCODED-URL** | `https?://localhost:5000` etc. in TypeScript | Use `ApiService` (knows the base URL); for other env values inject `SHELL_ENVIRONMENT` |
| **R9-HARDCODED-SECRET** | API keys, tokens, passwords as string literals | Move to `IConfiguration` / `platform.AppSetting` via `IModuleSettingsStore` |
| **R10-EMPTY-CATCH** | `catch (Exception) { }` with empty body | Let it propagate (remove try/catch) OR log + rethrow OR use `SafeExecute.FireAndForget` |

### Rules that WARN (still allowed, but logged to stderr)

| Rule ID | What it catches |
|---|---|
| **R7-SELECT-STAR** | `SELECT * FROM ...` — list specific columns instead |
| **R11-SP-MAGIC-STRING** | Stored procedure name as string literal — should reference `SpNames.X` |
| **R12-MISSING-CANCELLATION-TOKEN** | Public async method missing `CancellationToken` parameter |

---

## Why each rule exists (the cost of breaking it)

Each rule traces back to a real incident or architectural decision. If you're tempted to disable a rule because you think it's wrong, please raise a PR to remove it instead — there's likely a reason that's not obvious.

| Rule | Cost of breaking it |
|---|---|
| R1, R2 — Cross-module imports | Tight coupling. Module A's release breaks Module B. Independent deployment dies. |
| R3, R4 — HttpClient direct | Bypasses auth interceptor (401 storms), bypasses base URL config (wrong env), unobservable in error tracking. |
| R5 — IPlatformDbContext in product module | Hidden coupling. Product DB router can't isolate per-product. Multi-tenant boundary leaks. |
| R6 — Raw SQL | Skipped audit logging, skipped permission checks, untracked schema changes. SP-only is the contract. |
| R8 — Hardcoded URL | Breaks when deployed under a different host (Tailscale, customer install). Also CORS. |
| R9 — Hardcoded secret | Will end up on GitHub. Will end up in container images. Will be exfiltrated. |
| R10 — Empty catch | Bugs disappear silently. Production looks healthy while features quietly stop working. |

---

## "The hook blocked my edit and it was wrong"

If you genuinely have a case the hook misjudges, you have three options (in order of preference):

1. **Refactor to fit the rule.** Usually possible; usually makes the code better. If the rule says "use IEventBus" and you wanted to call another module directly, IEventBus is almost always the right answer.

2. **Add an explicit exception in the hook.** If your case is one the rule should know about (like `AuditExecutionService` legitimately inspecting `pg_proc`), edit `check-module-boundaries.py` to add the exception, with a comment explaining why. Raise a PR to Workspace/Common.

3. **Disable the hook locally for one edit** by removing it from `.claude/settings.json`. **DON'T DO THIS** — the change shows up in your PR diff and the CI will fail anyway. It also signals to reviewers that you're working around the architecture.

---

## "How do I know if my module is breaking the boundary?"

Three places to look:

1. **Right now, while editing**: Claude will tell you (the hook output is shown in the chat).
2. **After committing**: pre-commit hook runs build + tests; CI runs NetArchTest.
3. **Periodically**: weekly architecture digest emails the platform owner with cross-module call graph; deviations stand out.

---

## Adding new rules

When you discover a new pattern that should be banned (or warned):

1. Add the check to `check-module-boundaries.py` (test it first — false positives are worse than missed violations)
2. Document it in this file
3. Add an entry to `learned-errors.md` describing the bug class
4. Run `bash shared/scripts/propagate-rules.sh all --commit` to push it everywhere

The more rules accumulate, the safer the platform gets. By the time you have 50+ rules, an entire class of bugs is impossible to write.

---

## Hook script location

- **Canonical**: `Workspace/Common/.claude/hooks/check-module-boundaries.py`
- **Synced to**: every module's `.claude/hooks/` (via `shared/scripts/propagate-rules.sh`)
- **Configured by**: `.claude/settings.json` (PreToolUse with `matcher: "Edit|Write|MultiEdit"`)

The hook is committed to git. It's part of the contract every module owner agrees to. Disabling it = visible in PR diff = caught in review.
