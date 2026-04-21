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

## 11. Naming Convention — snake_case (adopted 2026-04-21)

**Use standard PostgreSQL `snake_case`** for column names, SP parameter names, table names.

✅ `parent_session_id`, `is_enabled`, `created_at_utc`, `content_type`
✅ SP params: `p_user_id`, `p_parent_session_id`
✅ Functions: `agent_ops.claim_next_spec_item`

**Why:**
- Matches PostgreSQL ecosystem norms (Django, Rails, SQLAlchemy, Supabase, Postgres docs).
- Matches the `snake_case` already used in ~half the Novara schema
  (`agent_ops.dispatch_queue`, `spec_batch_item`, `agent_maturity_stats`,
  `session_event`, etc.).
- Matches what Claude and human devs naturally write — eliminates
  cross-session drift.
- The Dapper safety net (`Dapper.DefaultTypeMap.MatchNamesWithUnderscores = true`
  in `DapperModuleDbContext` static ctor) bridges snake_case DB columns to
  PascalCase C# properties automatically — `parent_session_id` → `ParentSessionId`
  with zero friction.

**Legacy `no-underscore` convention (pre-2026-04-21) — retired:**
- Existing tables like `agent_ops.catalog.isenabled`, `agent_ops.session.agentname`
  continue to work — Dapper handles both styles. No renames required.
- New code: prefer snake_case. Matching an existing table's style when extending
  it is also fine (local consistency wins over global uniformity).

**Root-cause note:** the previous `lowercase-no-underscore` rule was born from
a 2026-04-15 bug where Dapper's default column→property mapping silently
dropped underscore columns to default values. The rule was a workaround
picked alongside the real fix (enabling `MatchNamesWithUnderscores` globally).
Once the safety net shipped the same day, the rule was obsolete but stayed.
Retired here.

## Automated Enforcement
- `platform.CheckParameterTypeMismatches` SP runs as part of database health checks
- Detects NVARCHAR parameters and columns that should be INT
- Results surfaced in Database Health dashboard and `/strengthen` reports
- New violations must be fixed before merging
