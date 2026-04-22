# SQL Naming Conventions — Binding Rule

**Adopted:** 2026-04-22 (replaces the 2026-04-21 "both styles coexist" guidance).

This rule applies to EVERY PostgreSQL function, table, column, parameter, and
index in every Novara-owned schema. Extensions and TimescaleDB internals are
out of scope.

---

## The convention

**snake_case everywhere.** No exceptions for Novara-authored DB objects.

| Kind | Pattern | Example |
|---|---|---|
| Function name | `schema.verb_noun` | `issues.get_by_product`, `roadmap.upsert_feature` |
| Function parameter | `p_noun_subnoun` | `p_feature_id`, `p_user_id`, `p_page_size` |
| Table name | `snake_case` | `agent_session`, `issue_comment` |
| Column name | `snake_case` | `created_at_utc`, `parent_session_id` |
| Index name | `ix_<table>_<cols>` | `ix_feature_track_id` |

### Parameter prefix

All function parameters use the **`p_` prefix** (Novara convention, not a PG
requirement) to distinguish them from column references inside the function
body. The `p_` comes before the snake_case name: `p_user_id`, never `puserid`.

### Why snake_case (and not lowercase-no-underscore)

1. Matches the PostgreSQL ecosystem default (Django, Rails, SQLAlchemy, pgAdmin).
2. Matches what developers naturally write — removes cross-session drift.
3. Readable. `p_parent_session_id` is unambiguous; `p_parentsessionid` isn't.
4. `DapperModuleDbContext` bridges C# PascalCase to snake_case automatically,
   so there's zero friction on the consumer side.

### Why the old "no-underscore" convention was retired

The `p_lowercase` (no underscore) convention was born as a workaround for a
Dapper column-mapping bug that was fixed the same day
(`MatchNamesWithUnderscores = true`). The workaround outlived its reason.
Worse, it created a trap: when someone gave a function an underscore in the
*name* (e.g., `get_by_key`) but kept params without underscores, the Gateway's
naming heuristic lied and every call hit `42883 function does not exist`.

The introspection-based `BuildPgCall` (2026-04-22) eliminates the heuristic.
The convention retirement eliminates the trap entirely.

---

## Enforcement

### 1. Pre-commit hook (blocking)

`.claude/hooks/check-sql-param-naming.py` scans every `.sql` file being
committed. Blocks the commit if any `CREATE [OR REPLACE] FUNCTION` introduces
a parameter name that doesn't match `p_[a-z0-9]+(_[a-z0-9]+)*` (i.e., either
`p_xxx` or `p_xxx_yyy` — never `p_xxxyyy`).

### 2. Gateway runtime (informational)

`BuildPgCall` introspects `pg_proc` at call time. It adapts to whatever names
exist in the DB — legacy or snake_case. This is the safety net that makes the
per-module sweep safe: new callers always find old functions and vice versa.

### 3. Startup validator (future — Phase 4)

Gateway boot verifies every `SpNames.*` constant points at a function that
exists in the DB. WARN mode for a week, then HARD-FAIL. Belt-and-braces
against drift accumulating silently over time.

---

## Migration from legacy

Every Novara-owned function in pg_proc (~800 functions as of 2026-04-22) is on
the legacy no-underscore convention and must be migrated to snake_case
parameter names. The sweep runs **module-by-module**, with a DB backup taken
before the first batch:

- `NovaraPlatformDB_backup` and `NovaraWorkspaceProductDB_backup` live on the
  same PG server. Full-restore rollback if any batch goes catastrophically
  wrong.
- Each module's sweep is ONE migration file in that module's `migrations/`
  directory with a matching **reverse** migration staged for rollback.
- Verification after each batch: drift scan returns 0 for that schema, smoke
  test of module endpoints returns HTTP 200.

**Order** (smallest blast radius first):
1. Batch A: communicate, search, todo, template, desktopsync, workflows,
   personalsettings (≤7 fns each)
2. Batch B: reports, incidents, codereview, artifacts, productcore,
   infrastructure, repos, notifications, collaborate (8–17 fns)
3. Batch C: audit, intelligence, admin, viber, designstudio, promptstudio,
   health (20–40 fns)
4. Batch D (hotspots): knowledgebank (33, 32 drifters), agent_ops (104, 11 drifters)
5. Batch E (largest): issues, thinkboard, releases, quality, roadmap

Progress tracked in `.claude/tasks/sp-naming-standardization.md`.

---

## The split dictionary

When splitting a compound word into snake_case, the canonical splits live in
`NovaraSDK/distribution/pg-param-dictionary.json`. Operators adding novel
compounds (rare after initial population) append an entry with a short note
explaining the choice. The dictionary is the canonical vocabulary; inventing
splits on the fly creates drift.

Examples:
```json
{
  "featureid":         "feature_id",
  "userid":            "user_id",
  "productid":         "product_id",
  "parentsessionid":   "parent_session_id",
  "assigneeuserid":    "assignee_user_id",
  "ispluginname":      "is_plugin_name",
  "createdatutc":      "created_at_utc",
  "modifiedatutc":     "modified_at_utc",
  "isdeleted":         "is_deleted",
  "promptkey":         "prompt_key"
}
```

---

## Retired rules this supersedes

- `database-design-principles.md` §11 "snake_case **or** legacy no-underscore,
  both coexist" — retired. snake_case is mandatory for new work and all
  migrations.
- `database.md` "parameter names: legacy p_lowercase works, Dapper bridges" —
  retired. Legacy funcs still work via Gateway introspection but cannot be
  introduced in new migrations.
- `learned-errors.md DAPPER_UNDERSCORE_SILENT_DROP` — historical note only,
  already marked RESOLVED.

---

## FAQ

**Q: Will this break existing C# callers?**
A: No. The Gateway's `BuildPgCall` introspects `pg_proc` at call time, so it
sends whatever names the DB actually has — legacy or snake_case. C# continues
passing PascalCase property names unchanged.

**Q: What about the `p_` prefix — can I drop it?**
A: No. Every function parameter keeps `p_`. It distinguishes params from
columns inside the function body and avoids reserved-word collisions.

**Q: RETURNS TABLE output columns — do they need `p_`?**
A: No. `RETURNS TABLE(id INT, name VARCHAR, ...)` column names do NOT use
`p_`. Only INPUT params use `p_`.

**Q: What if I need a param whose name would require a keyword (e.g., "user")?**
A: Every Novara param already has the `p_` prefix which neutralises this. If
writing `p_user` feels weird, prefer the more specific form (`p_user_id`,
`p_user_name`).

**Q: Overloaded functions — allowed?**
A: Strongly discouraged. The Gateway's `BuildPgCall` picks the best overload
against the C# caller's property set, but overloads remain a source of
ambiguity and 42725 errors at the edges. Migrate toward single signatures;
use DEFAULTs for optional params instead.
