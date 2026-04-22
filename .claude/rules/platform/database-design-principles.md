---
globs: **/*.sql, **/SpNames*, **/*DbContext*, **/*Service*, **/*Controller*
---

# Database Design Principles — High-Performance System

Novara is designed to scale to massive data volumes and potentially microservices. Every database decision must optimize for performance at scale.

## 0. Column Alterations — ALWAYS PROMPT THE USER
- **NEVER alter a column datatype without explicit user confirmation** — even if it looks safe
- ALTER TABLE changes can break running SPs, API code, reports, and downstream consumers
- Always show: table name, column name, current type, proposed type, and estimated row impact
- Wait for user approval before executing ANY ALTER TABLE ... ALTER COLUMN or DROP/ADD COLUMN
- This applies to adding columns too — confirm the type, nullability, and default value first

## 1. Primary Keys
- **Always `Id INT IDENTITY(1,1) NOT NULL`** — no exceptions
- Never GUID (16 bytes vs 4 bytes, terrible for clustered index fragmentation)
- Never NVARCHAR (string comparison is 5-10x slower than INT)
- Never composite PKs unless absolutely necessary (and then prefer surrogate + unique constraint)

## 2. Foreign Keys & Joins
- **All FK columns MUST be INT** — same type as the referenced PK
- Never join on NVARCHAR columns — use INT lookup first, then join on INT
- Never CAST() inside a JOIN or WHERE clause — resolve types before the query
- `platform.[User].Id` is INT — all references to users MUST be INT
- Exception: Plugin IDs (`PluginId NVARCHAR`) are string identifiers by design, not FK references

## 3. SP Parameters
- **ID parameters MUST be INT** — `@UserId INT`, `@ProductId INT`, `@FeatureId INT`
- Never `@UserId NVARCHAR(200)` — this forces implicit CAST on every query, kills index usage
- If the caller passes a string (e.g., JWT claim), convert to INT in the C# layer BEFORE calling the SP
- The `ResolveUserId()` function is RETIRED — convert in C# with `int.Parse()`
- Exception: CSV lists like `@UserIds NVARCHAR(MAX)` for report filters are acceptable

## 4. Column Types
- ID/FK columns: `INT NOT NULL` (or `INT NULL` if optional)
- User references: `INT` — never NVARCHAR for user IDs
- Timestamps: `DATETIME2` — never DATETIME (more precision, same storage)
- Booleans: `BIT NOT NULL DEFAULT 0`
- Short strings: `NVARCHAR(n)` with appropriate length
- Long text: `NVARCHAR(MAX)` — but never for ID columns
- Money: `DECIMAL(18,2)` — never FLOAT

## 5. Indexing
- Every FK column should have a non-clustered index
- Composite indexes: most selective column first
- Include columns for covering indexes (avoid key lookups)
- Never index NVARCHAR(MAX) columns directly — use computed columns or full-text

## 6. Implicit Conversions — BANNED
- Never compare INT to NVARCHAR (e.g., `WHERE UserId = @StringParam`)
- Never CAST inside WHERE/JOIN — it prevents index seeks
- The `/strengthen` database health check (`platform.CheckParameterTypeMismatches`) detects these automatically
- If detected: fix immediately — implicit conversions cause full table scans

## 7. Soft Deletes
- All tables: `IsDeleted BIT NOT NULL DEFAULT 0`
- Never hard delete — mark as deleted
- Every SELECT must include `WHERE IsDeleted = 0` (or use filtered indexes)
- Audit columns: `CreatedByUserId INT`, `CreatedAtUtc DATETIME2`, `ModifiedByUserId INT`, `ModifiedAtUtc DATETIME2`

## 8. SP Design
- `CREATE OR ALTER PROCEDURE novara.<Name>` — always idempotent
- `SET NOCOUNT ON` — reduces network traffic
- `BEGIN TRY / BEGIN CATCH` for transactional operations
- No `SELECT *` — list specific columns (schema changes break `SELECT *`)
- Use `EXISTS` over `COUNT(*) > 0` (short-circuits on first match)
- Pagination: `OFFSET @Skip ROWS FETCH NEXT @PageSize ROWS ONLY`
- Return `COUNT(*) OVER()` for total count in same query (avoids second round-trip)

## 9. Telemetry Tables — Exception to INT Rule
- `RequestTrace.UserId`, `FrontendPerfTrace.UserId`, `UserSessionTrace.UserId` — NVARCHAR is acceptable
- These store raw HTTP context values, not FK references
- They are write-heavy, rarely joined — string storage is fine
- Same for `AppId NVARCHAR(50)` — product identifier string, not a FK

## 10. Schema
- Platform/config objects: `platform` schema (auth, settings, products, tenants, metrics)
- Product-specific objects: `product` schema (features, issues, ideas, collaboration, artifacts)
- `novara` schema is retired — do NOT use for new objects
- `collab` schema is RETIRED — does not exist
- Never create objects in `dbo` schema for Novara features

## 11. Naming Convention — snake_case MANDATORY (2026-04-22)

**Use `snake_case` everywhere.** Not "prefer", not "both styles coexist" —
it is the only convention.

✅ Columns:   `parent_session_id`, `is_enabled`, `created_at_utc`, `content_type`
✅ SP params: `p_user_id`, `p_feature_id`, `p_parent_session_id`
✅ Functions: `agent_ops.claim_next_spec_item`
✅ Tables:    `feature_work_item`, `agent_session`

### Enforcement (three gates)

1. **Pre-commit hook** — `.claude/hooks/check-sql-param-naming.py` blocks any
   new `CREATE FUNCTION` with legacy params. Runs on every commit that
   touches `migrations/*.sql`.
2. **Gateway introspection** — `BuildPgCall` in `DapperModuleDbContext` +
   `DapperPlatformDbContext` queries `pg_proc` at call time, adapts C#
   PascalCase to the SP's actual param names. Guarantees the Gateway can
   call snake_case AND any legacy functions still lingering in the DB.
3. **Startup validator** (WARN → HARD-FAIL) — Gateway boot verifies every
   `SpNames.*` constant resolves to a live function. Planned Phase 4.

### Canonical vocabulary

`NovaraSDK/distribution/pg-param-dictionary.json` holds ~300 compound splits
(`userid → user_id`, `featureid → feature_id`, …) and ~145 atomic words that
pass through unchanged. Adding a new compound = append an entry, run
`./distribution/propagate-rules.sh all` to sync module repos.

### History

The old `lowercase-no-underscore` convention (pre-2026-04-21) was a workaround
for a 2026-04-15 Dapper mapping bug that was fixed the same day via
`MatchNamesWithUnderscores = true`. The workaround outlived its reason, then
mutated into a 54-function "drifter bomb" class (name has `_`, params don't)
that triggered runtime 42883 errors. The 2026-04-22 sweep converted ~700
functions to snake_case (88%) and replaced the brittle Gateway heuristic with
runtime introspection. Remaining legacy-param functions still work via
introspection but no new ones may be introduced.

See `.claude/rules/sql-conventions.md` for the full convention, the sweep
tool at `.claude/tools/sweep-module-params.py`, and the ADR at
`.claude/architecture/2026-04-22-sp-calling-convention-adr.md`.

## Automated Enforcement
- `platform.CheckParameterTypeMismatches` SP runs as part of database health checks
- Detects NVARCHAR parameters and columns that should be INT
- Results surfaced in Database Health dashboard and `/strengthen` reports
- New violations must be fixed before merging
