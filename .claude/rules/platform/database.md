---
globs: **/*DbContext*, **/*Repository*, **/SpNames*
---

# Database & Stored Procedure Rules

## Architecture
- Dapper micro-ORM via DapperModuleDbContext + DapperPlatformDbContext + ProductDatabaseRouter (per-product DB routing)
- **Platform DB:** `NovaraPlatformDB` — `platform` schema (config, auth, cross-product). `viber` schema (Viber Hub).
- **Product DB:** `NovaraWorkspaceProductDB` — per-module schemas (issues, roadmap, designstudio, etc.)
- **Template DB:** `NovaraTemplateProductDB` — golden image for new products
- Per-product databases: `ProductDatabaseRouter` resolves connection per ProductId via `platform.productdatabase` (cached 10 min)
- All function names centralized in each module's SpNames.cs (e.g., IssueSpNames, PlanSpNames) and shared PlatformSpNames.cs in SDK
- Product schema files: `../NovaraWorkspaceProductDB/` — Platform schema files: `../../NovaraPlatformDB/`

## Per-Module Schemas (current state)
Each module owns its schema. Display name = module ID = DB schema = C# namespace.
- `issues.*`, `roadmap.*`, `thinkboard.*`, `designstudio.*`, `knowledgebank.*`, `artifacts.*`
- `test.*`, `codereview.*`, `audit.*`, `health.*`, `infrastructure.*`, `releases.*`
- `incidents.*`, `viber.*`, `collaborate.*`, `admin.*`, `reports.*`, `notifications.*`
- `desktopsync.*`, `activities.*`, `communicate.*`, `search.*`
- `productcore.*` — shared cross-module tables (user, product, audittype, vibemachine, machineworkqueue)
- `productmeta.*` — migration tracking (migration_log, module_version)
- `product.*` — 123 backward-compat views only (auto-updatable, zero tables/functions)

## Table Design Rules (MANDATORY)
- **PK: Always `Id INT IDENTITY(1,1) NOT NULL`** — never NVARCHAR, never GUID
- **FK columns: Always INT** — same type as referenced PK. Never NVARCHAR for ID/FK columns.
- **FK references `Id`** — e.g., `ProductId INT` references `platform.Product(Id)`
- **User references: INT** — `CreatedByUserId INT`, `OwnerUserId INT`. Never NVARCHAR.
- **NEVER delete columns** — deprecate with new column, old stays
- **NEVER rename columns** — functions, code, and reports depend on exact names
- **Soft deletes only** — `IsDeleted BOOLEAN DEFAULT false`
- **Audit columns**: `CreatedByUserId INT`, `CreatedAtUtc TIMESTAMP`, `ModifiedByUserId INT`, `ModifiedAtUtc TIMESTAMP`
- Entity is `Product` (not Project) — PK is `Id` (not `ProductId`)
- See `database-design-principles.md` for the full design specification

## Per-Product DB Architecture (BINDING)
- **Database = Product:** Each product gets its own database. No `ProductId` column in product tables.
- **Deployment = Tenant:** Each enterprise gets its own deployment. No `TenantId` column in product tables.
- **No OrgId in module tables:** `OrgId` only exists in `productcore.product` (synced from platform). Never add to module tables.
- **Platform DB keeps TenantId:** `NovaraPlatformDB` manages cross-product routing and auth. TenantId stays there.
- **Two modules use platform DB:** `novara.rules` and `novara.appgateway` keep TenantId — they query platform schema.
- **C# code:** No `GetTenantId()` or `TenantId = tenantId` in product DB module controllers/services. No `ProductId` anywhere.

## Function Conventions (PostgreSQL)
- Use `CREATE OR REPLACE FUNCTION {schema}.{name}(...)` — schema = module schema (issues, roadmap, etc.)
- Parameter names: **`snake_case`** (e.g., `p_user_id`, `p_feature_id`, `p_parent_session_id`) — adopted 2026-04-21, aligns with PG ecosystem. Legacy `p_lowercase` (no-underscore) also works — Dapper's `MatchNamesWithUnderscores=true` bridges both.
- **ID parameters MUST be INT** — `p_user_id INT`, never `p_user_id VARCHAR`
- **No p_product_id or p_tenant_id** in product DB functions — database IS the product, deployment IS the tenant
- No `SELECT *` — list specific columns
- Use `EXISTS` over `COUNT(*) > 0`
- Function names: `issues.upsert`, `issues.get_by_product` (or `issues.getbyproduct` when extending tables already using no-underscore — local consistency wins)

## SP/Function ↔ Code Coupling (MANDATORY)
Every Dapper function call in C# must have an inline comment showing the contract:
```csharp
// SP: roadmap.getfeaturesbytrack(p_trackid INT, p_page INT, p_pagesize INT)
// Returns: Id, Title, Status, AssigneeName, TrackId, CreatedAtUtc + TotalCount via COUNT(*) OVER()
var features = await _db.ExecuteProcedureAsync<Feature>(PlanSpNames.GetFeaturesByTrack, new { ... });
```
This catches INT/NVARCHAR mismatches at read-time, not runtime. Add when touching existing code.

## After DB changes
- Run `python tools/pull-schema.py` in `NovaraWorkspaceProductDB/` to refresh local files from live DB
- For platform changes, run equivalent in `NovaraPlatformDB/`
- Commit the updated SQL files to the respective repo
