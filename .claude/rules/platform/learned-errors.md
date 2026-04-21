---
globs: "**/*.cs,**/*.ts,**/*.sql"
---

# Learned Errors — Living Knowledge from Debugging

## How This File Works

This file grows automatically during debugging sessions. Every error we encounter
and fix becomes a permanent learning. Claude reads this before writing code.
New modules are built knowing every mistake that was ever made.

**When to add an entry:**
- You fix a bug and the root cause wasn't obvious
- You see the same error class for the second time
- The error took > 10 minutes to diagnose
- The error was in production or could have reached production

**Format for each entry:**
```
### [ERROR_CLASS] — [Short description]
**Pattern:** [What the error looks like — message, HTTP status, behavior]
**Root cause:** [What was actually wrong]
**Fix:** [What to do]
**Guardrail:** [SDK class / rule / check that prevents this]
**Module(s):** [Which modules hit this]
```

---

## Error Classes

### DAPPER_NULL_MAPPING — DB column exists but C# entity property missing
**Pattern:** API returns 200 but field is null. No error thrown. Data silently lost.
**Root cause:** Dapper maps SQL columns to C# properties BY NAME. If the entity class
doesn't have a matching property, the column is silently dropped. No warning, no error.
**Fix:** Add the property to the entity class. Check ALL columns in the SELECT.
**Guardrail:** `Guard.Found()` catches null results. But for individual fields,
always verify entity class has ALL properties matching SP output columns.
**Module(s):** Issues (ContextJson), Roadmap (multiple fields)

### EMPTY_CATCH_SILENT — Exception swallowed, no logging, feature silently fails
**Pattern:** Feature "doesn't work" but no errors in logs. Returns empty data or null.
**Root cause:** `catch (Exception) { return Array.Empty<T>(); }` or `catch { return null; }`
**Fix:** Remove empty catch. Let exception propagate. GlobalExceptionMiddleware handles it.
**Guardrail:** `SafeExecute.RunAsync()` for non-critical ops. For data ops: NEVER catch silently.
**Module(s):** Any module with try/catch in services

### SP_PARAM_TYPE_MISMATCH — VARCHAR parameter for INT column
**Pattern:** Query runs but returns wrong results or full table scan. Performance degrades.
**Root cause:** SP parameter declared as VARCHAR but column is INT. PostgreSQL does implicit cast,
which prevents index usage and causes full table scans.
**Fix:** Change SP parameter to INT. Convert string → int in C# BEFORE calling SP.
**Guardrail:** Database design principles require INT for all ID params. /deep-scan detects these.
**Module(s):** Any module with INT columns queried by string parameters

### MISSING_ISDELETED_FILTER — Query returns soft-deleted rows
**Pattern:** List shows deleted items. Count is wrong. Deleted items reappear after refresh.
**Root cause:** SP WHERE clause doesn't include `WHERE isdeleted = false`.
**Fix:** Add `AND isdeleted = false` to every SELECT in the SP.
**Guardrail:** Database standards require isdeleted filter on every SELECT.
**Module(s):** Multiple — check every new SP

### API_RETURNS_200_WITH_NULL — Endpoint succeeds but data is null or empty
**Pattern:** Frontend shows empty state even though data exists in DB. No error shown.
**Root cause:** Multiple possible: (1) SP returns data but entity class drops it (Dapper null mapping),
(2) Response DTO missing the field, (3) Service returns null and controller wraps in Ok(),
(4) Wrong ProductId/TenantId context.
**Fix:** Trace the 5 layers: DB → SP → API service → DTO → frontend model.
**Guardrail:** `Guard.Found()` for single-entity lookups. Always verify API response body, not just HTTP 200.
**Module(s):** All modules — most common bug class

### FRONTEND_MODEL_DRIFT — API returns field but Angular model doesn't have it
**Pattern:** API returns data correctly, but UI doesn't display the new field.
**Root cause:** TypeScript interface doesn't have the property. Angular silently ignores extra JSON fields.
**Fix:** Add the property to the TypeScript model interface. Update the template.
**Guardrail:** When adding a DB column, trace all 4 layers: Entity → DTO → API → TS model.
**Module(s):** All modules — happens on every new column

### CONNECTION_TIMEOUT_SILENT — DB connection times out but error swallowed
**Pattern:** API hangs for 30 seconds then returns empty or generic error.
**Root cause:** DB connection timeout with no explicit error handling. Default timeout too long.
**Fix:** Set explicit commandTimeout on slow queries. Use connection pooling. Health check catches this.
**Guardrail:** IModuleDbContext timeout overloads. Health check /health/ready tests DB connectivity.
**Module(s):** Health (large telemetry tables), Roadmap (complex joins)

### EVENT_HANDLER_CRASH — One event handler failure prevents others from executing
**Pattern:** Module A publishes event, Module B's handler crashes, Module C's handler never runs.
**Root cause:** Event bus didn't isolate handler execution. One throw killed the chain.
**Fix:** InMemoryEventBus rebuilt with per-handler isolation (5s timeout + circuit breaker).
**Guardrail:** SDK EventBus has handler isolation built in. Each handler wrapped in try/catch + timeout.
**Module(s):** N/A — fixed in infrastructure before it hit production

### CORS_ORIGIN_MISSING — Frontend gets blocked by CORS policy
**Pattern:** Browser console shows "CORS policy" error. API works in Postman but not browser.
**Root cause:** New origin URL not added to Cors:Origins in appsettings.json.
**Fix:** Add the origin to appsettings.json Cors:Origins array.
**Guardrail:** Document all deployment origins. Never use wildcard (*) in production.
**Module(s):** Shell — happens when adding new deployment URLs

### JWT_CLAIM_MISSING — GetUserId() throws because claim not in token
**Pattern:** 500 error on any authenticated endpoint. "User ID not found in token."
**Root cause:** Dev login generates JWT without all required claims. Or old token format.
**Fix:** Verify /dev-login generates all claims: userId, tenantId, email, role, sessionId.
**Guardrail:** ModuleBaseController.GetUserId() throws explicitly — never returns 0 silently.
**Module(s):** All modules — JWT structure must be consistent

### MODULE_ACCESSES_PLATFORM_DB — Product module queries platform schema directly
**Pattern:** Module uses `IPlatformDbContext` to query platform tables. Works in dev but breaks in distributed deployments. Creates hidden coupling.
**Root cause:** Developer needed user names or settings and queried platform DB directly instead of using the product-scoped copy or SDK service.
**Fix:** Use `productcore.user` / `productcore.product` (synced copies in product DB) for user/product data. Use `IModuleSettingsStore` for settings. Use `ICacheService` for cached lookups.
**Guardrail:** Only modules with `DbScope = ModuleDbScope.Platform` may inject `IPlatformDbContext`. Product-scoped modules get compile-time error if they try (enforced by SDK when modules are NuGet distributed).
**Module(s):** Any product-scoped module. Check: grep for `IPlatformDbContext` in non-platform modules.

---

## How to Use This File

**Before writing a new module service:** Read the error classes above. Your service
should not be vulnerable to any of these patterns.

**When you hit an error:** Check this list first. If the error matches a known class,
apply the documented fix. If it's NEW, add an entry after fixing it.

**Progressive growth:** This file should grow by 2-3 entries per debugging session.
Over time, it becomes the complete knowledge of what can go wrong and how to prevent it.
New module developers read this once and know every trap that exists.

### CREATED_AT_ACTION_ZERO_ID — CreatedAtAction with id=0 causes "No route matches"
**Pattern:** POST create returns 500: `InvalidOperationException: No route matches the supplied values`. GET works fine.
**Root cause:** `CreatedAtAction(nameof(GetDetail), new { id = 0 }, ...)` — placeholder ID. ASP.NET can't build Location URL with id=0 when route has `{id:int}` constraint.
**Fix:** Replace with `Ok(ApiResponse<T>.Ok(result, "Created."))` — Angular doesn't use Location headers.
**Guardrail:** `CrudServiceBase` pattern uses Ok(). Module template uses Ok(). Never use CreatedAtAction with placeholder IDs.
**Why it existed:** POST endpoints not tested — only GET was verified. Template now uses Ok().
**Module(s):** Any module using CreatedAtAction — search for `CreatedAtAction.*= 0`.

### MISSING_DB_DEFAULTS — NOT NULL column without DEFAULT causes insert failures
**Pattern:** `null value in column "isdeleted" violates not-null constraint` on CREATE.
**Root cause:** Table has `NOT NULL` but no `DEFAULT`. SP doesn't set the column explicitly.
**Fix:** `ALTER TABLE ALTER COLUMN SET DEFAULT`. isdeleted=false, counts=0, status='Draft'.
**Guardrail:** DATABASE_STANDARDS.md requires `DEFAULT` on every NOT NULL column. /deep-scan should check.
**Why it existed:** Table created without DEFAULT on NOT NULL column. SP didn't set value explicitly.
**Module(s):** Any new table. DATABASE_STANDARDS.md now requires DEFAULT on every NOT NULL column.

### SP_COUPLING_COMMENT_WRONG — SP coupling comment references old SP, actual SP has different params
**Pattern:** `function xxx() does not exist` — function exists but with different required params. Service code passes wrong params because coupling comment shows old signature.
**Root cause:** SP coupling comments copied from monolith during extraction. When SPs were recreated with different signatures, comments weren't updated. Developer trusted the comment.
**Fix:** Verify comment against actual function: `SELECT pg_get_function_arguments(oid) FROM pg_proc WHERE proname = 'xxx'`. Update both comment and Dapper parameters.
**Guardrail:** SP coupling comments must be verified against live DB on first test. /deep-scan should compare comments against actual signatures.
**Why it existed:** Comments were written without verifying against actual DB function.
**Module(s):** Any module. Always verify SP coupling comments against live DB on first test.

### MISSING_CANCELLATION_TOKEN — Async method without CancellationToken
**Pattern:** User navigates away or request times out, but server continues processing. Under load, abandoned requests pile up — CPU/DB connections wasted. With pool max 50, just 50 slow queries exhaust the pool.
**Root cause:** Methods declared `public async Task<T> DoSomething(...)` without `CancellationToken ct = default` parameter. No way for the framework to signal cancellation.
**Fix:** Add `CancellationToken ct = default` as last parameter on every `public async Task` method in interfaces and services. Pass through to `ExecuteProcedureAsync`. Controllers get `CancellationToken ct` auto-bound by ASP.NET from `HttpContext.RequestAborted`.
**Guardrail:** Every new async method MUST include CancellationToken. Pre-commit hook should flag async methods without it.
**Module(s):** All modules — this was a codebase-wide gap (252 methods missing). Fixed progressively.

### ID_FILTER_VS_FK — String parameter for ID filter is not the same as wrong FK type
**Pattern:** `p_assigneeuserid TEXT` in SP looks like a type mismatch (column is INT). But it's a FILTER parameter, not an FK.
**Root cause:** Filter parameters support comma-separated values ("1,2,3") for multi-user filtering. The SP internally casts or splits. The entity property `AssigneeUserId` is correctly `int?`.
**Fix:** No fix needed if the parameter is intentionally TEXT for CSV filtering. Document in SP coupling comment: `// p_assigneeuserid VARCHAR — CSV filter, not FK`.
**Guardrail:** When auditing parameter types, distinguish between: (1) FK parameters that reference a column → MUST be INT, (2) Filter parameters that accept CSV lists → TEXT is acceptable. DB standards already document this exception.
**Module(s):** Issues (getbyproduct), Reports (report filters with UserIds/Statuses CSV).

### MISSING_SP_COUPLING_COMMENT — ExecuteProcedure call without parameter contract
**Pattern:** Dapper SP call has no inline comment showing function name, parameter types, and return type. When the SP signature changes (column renamed, parameter added), the C# code silently breaks at runtime — no compile error, no warning.
**Root cause:** Services generated or migrated without documenting the DB contract. Fast coding without DB verification. The comment takes 30 seconds to write but saves hours of debugging when a SP changes.
**Fix:** Every `ExecuteProcedureAsync` / `ExecuteProcedureSingleAsync` call gets a comment above the method:
```csharp
// SP: {schema}.{functionname}(p_param1 TYPE, p_param2 TYPE, ...)
// Returns: {EntityType} row(s) | void
```
**Guardrail:** Pre-commit hook counts `// SP:` vs `ExecuteProcedure` lines. Warn if coverage < 80%. Block if < 50%.
**Module(s):** All modules — 11 services had zero SP comments. Fixed 2026-04-13.

### UNBOUNDED_LIST_RETURN — IEnumerable without pagination risks OOM
**Pattern:** `GetAllAsync()` returns `IEnumerable<T>` loading ALL rows. A product with 50K features or test results causes memory exhaustion or 30+ second responses.
**Root cause:** Methods designed for demo data (10-100 rows) without considering production scale. No pagination parameters on the interface or SP.
**Fix:** Replace `IEnumerable<T>` with `PagedResponse<T>` for any list that could grow beyond ~100 items. Add `p_page`/`p_pagesize` with defaults to the SP. Always include `COUNT(*) OVER() AS totalcount`.
**Guardrail:** Any new list method MUST accept PaginationParams. Pre-commit hook should warn on `IEnumerable<` returns in service interfaces.
**Module(s):** 96 methods across all modules return unbounded lists. Priority: GetCollections, GetStrategies, GetInsights, GetJournal, GetRoles, GetLabels.

### FIRE_AND_FORGET_UNOBSERVED — Task.Run without error visibility
**Pattern:** `_ = Task.Run(async () => { ... })` — if the inner task throws, the exception is unobserved. No log, no alert, data silently lost. Also bypasses graceful shutdown — server stops but background task continues hitting a dead DB connection.
**Root cause:** Quick hack for "run this in the background" without proper job infrastructure. Feels fast, breaks silently.
**Fix:** Use `SafeExecute.FireAndForget()` for simple side effects (logs the error). Use `IJobService.EnqueueAsync()` for work that needs status tracking and retry. Never raw `Task.Run` for business logic.
**Guardrail:** Pre-commit hook should flag `Task.Run` in service code. Only acceptable with documented justification.
**Module(s):** CodeGenerationService (has full try/catch — acceptable until job queue wired). FeatureWorkItemService (fixed to SafeExecute).

### RAW_SQL_BYPASSES_SP — Inline SQL instead of function call
**Pattern:** `connection.ExecuteAsync("UPDATE ... SET isdeleted = true ...")` — bypasses the SP layer. No version tracking, no audit in migration scripts, harder to find in DB schema pulls.
**Root cause:** Developer needed a quick delete and wrote inline SQL instead of creating a function. Felt faster, but now there are two ways to delete — one tracked, one not.
**Fix:** Create proper `{schema}.{function}()` functions for every mutation. Inline SQL is only acceptable for system table inspection (pg_proc, information_schema).
**Guardrail:** Grep for `connection.Execute` and `conn.Query` in services. Only AuditExecutionService (DB inspection) should have them.
**Module(s):** DesignStudioService (DeleteFlowAsync, DeleteTemplateAsync — SPs created 2026-04-12).

### MULTI_SP_METHOD_INVISIBLE_CALLS — Method-level SP comment hides uncovered call sites
**Pattern:** A method calls 4-5 SPs. A single block comment at the top lists the SPs. Grep-based coverage checks count `// SP:` lines vs `ExecuteProcedure` lines — reports 56-75% coverage even though the developer thinks it's "covered." During review, uncovered calls are invisible — you can't tell what SP a line calls without reading SpNames.cs.
**Root cause:** Block comments written during initial implementation. Developer intended one comment to cover all calls in a method. But repeated calls (same SP in success/failure paths) or helper lookups (GetDetail before mutation) were never individually annotated.
**Fix:** Every `ExecuteProcedure` call site gets its own inline `// SP:` comment. For repeated SPs, add a short qualifier: `// SP: audit.completerun — mark failed with error summary`. Method-level block comments stay for context but don't replace inline comments.
**Guardrail:** SP coverage check: `grep -c "// SP:" vs grep -c "ExecuteProcedure"` per file. Target: 100% for all services. Run as part of verification before commit.
**Module(s):** BlueprintChatService (was 56%), FeatureWorkItemService (was 70%), DesignStudioService (was 72%), CodeGenerationService (was 75%). All fixed to 100% on 2026-04-13.

### HARDCODED_SYSTEM_USER_ID — Magic number for AI user instead of resolver
**Pattern:** `UserId = 1638` or `CreatedByUserId = 1638` hardcoded in service code for AI-generated content (chat messages, analysis results). Works in dev, fails in every customer deployment because user IDs are auto-incremented per database.
**Root cause:** Developer looked up the system user ID in the dev database and pasted it into code. Faster than writing a resolver, but deployment-specific. The value 1638 is the `claude@novara.system` user in dev only.
**Fix:** Created `ISystemUserResolver` in SDK + `SystemUserResolver` implementation in Gateway. Modules inject the resolver and call `GetAiUserIdAsync()`. Cached for 30 minutes. Falls back to 0 if user not found.
**Guardrail:** Grep for `UserId = [0-9]{3,}` in service code. Any literal userId > 100 is suspicious — should be a parameter or resolver call. Pre-commit check.
**Module(s):** DesignStudioService (2 places), FeatureTaskService (2 places), BlueprintChatService (1 place — had its own resolver, now uses shared SDK interface). All fixed 2026-04-13.

### HARDCODED_MODEL_VERSION — Stale model string instead of using LLM response
**Pattern:** `ModelVersion = "claude-sonnet-4-20250514"` hardcoded in DB write. The DB records which model "was used" but the value is what the developer assumed at coding time, not what was actually used. When models change or the tenant uses a different provider, the DB has wrong data.
**Root cause:** `LlmResult` already had a `Model` property, but developers stored the model name before calling the LLM (as a "request" field) instead of reading it from the response (as a "result" field). The result's `Model` property was ignored.
**Fix:** Use `llmResult.Model` from the response for DB writes. For async operations where the model is recorded before the call completes, use `GenerationStatus.Pending` and update after completion.
**Guardrail:** Grep for `claude-` or `gpt-` in service code (not in prompt text). Any model name string literal in service layer should come from config or LLM response.
**Module(s):** CodeGenerationService, DocGenerationService (2 places each). Fixed 2026-04-13.

### MAGIC_STRING_PROMPT_KEY — Prompt key as raw string instead of constant
**Pattern:** `GetPromptAsync("prompt.feature.chat.system")` — prompt key is a raw string. A typo like `"prompt.feature.chat.sytem"` fails silently (prompt not found, AI generates without system instructions, output is garbage). No compile-time check, no IDE autocomplete.
**Root cause:** `GetPromptAsync` takes a string key. The simplest call is a string literal. Without a convention requiring constants, every developer writes the key inline. Over time, 30 unique keys were scattered across 8 modules.
**Fix:** Created `PromptKeys.cs` in each module's `Constants/` folder (e.g., `RoadmapPromptKeys`, `ThinkBoardPromptKeys`). All 30 prompt keys replaced with constants. Pattern: `_llm.GetPromptAsync(RoadmapPromptKeys.ChatSystem)`.
**Guardrail:** `GetPromptAsync` calls must reference a `*PromptKeys.*` constant. Grep: `GetPromptAsync("[^"]*PromptKeys)` should match ALL calls. Any `GetPromptAsync("` with a raw string is a violation.
**Module(s):** Roadmap (17 keys), ThinkBoard (6 keys), EnterpriseThinkBoard (3 keys), Audit (1 key), Health (1 key). All 30 fixed 2026-04-13.

### MAGIC_STRING_LLM_ROLE — Hardcoded "user"/"assistant"/"system" instead of SDK constant
**Pattern:** `Role = "assistant"` or `Role = "user"` scattered across AI chat services. These are protocol values (OpenAI/Anthropic standard), not business data. A typo like `"assitant"` causes silent mapping failure.
**Root cause:** LLM roles are a small, stable set — developers never think to constantize them. But they're used in database writes (chat message tables), making a typo cause data corruption.
**Fix:** Created `LlmRoles` class in SDK with `User`, `Assistant`, `System` constants. Replaced all magic strings.
**Guardrail:** Grep: `Role = "user"\|Role = "assistant"\|Role = "system"` in service code should return 0 matches. All should use `LlmRoles.*`.
**Module(s):** DesignStudioService (4 places), BlueprintChatService (3 places), FeatureTaskService (3 places). All fixed 2026-04-13.

### FEDERATION_CHANGE_DETECTION — Module Federation standalone components need explicit cdr.detectChanges()
**Pattern:** Component shows "Loading..." forever. API returns data (verified with curl), but the template doesn't update. No errors in console. Data is set in the subscription handler but Angular doesn't re-render.
**Root cause:** Module Federation loads standalone components in a separate NgZone context. Angular's automatic zone-based change detection doesn't trigger for async operations (HTTP subscriptions, setTimeout, etc.) in federated components. The component's view stays stale after data arrives.
**Fix:** Inject `ChangeDetectorRef` in every federated standalone component. Call `this.cdr.detectChanges()` after EVERY async data update — in both `next` and `error` handlers of every `subscribe()` call.
**Guardrail:** Every new Angular component in a module MUST have `ChangeDetectorRef` injected and called after async operations. Add to the component template in CLAUDE.md. Pre-commit check: grep for `.subscribe({` without `detectChanges` nearby.
**Why it's dangerous:** No error, no warning, no console message. The component just silently doesn't render. Only visible by running the Shell UI, not by building the module independently.
**Module(s):** ALL modules with Angular components. Fixed in roadmap (TrackList, Overview, InitiativeList, MilestoneList) 2026-04-13. Check ALL other modules.

### ANGULAR_VERSION_MISMATCH — Different @angular versions across repos cause pipe/type resolution failures
**Pattern:** `NG3004: Unable to import pipe DecimalPipe. The symbol is not exported from .../novara-ui-kit/node_modules/@angular/common/index.d.ts` — pipe types resolve through a DIFFERENT Angular version than the Shell's.
**Root cause:** `novara-ui-kit` had Angular 20.3 in its `node_modules` while the Shell was on Angular 21.2. The federation build resolves types through the ui-kit's Angular, not the Shell's. Different Angular versions have different export structures for pipes.
**Fix:** Upgrade all shared packages (ui-kit, shell-sdk) to the same Angular version as the Shell. Run `npm install @angular/common@21.x @angular/core@21.x` in ui-kit and shell-sdk whenever the Shell Angular version changes.
**Guardrail:** Add a version check script that compares `@angular/core` version across Shell, ui-kit, and shell-sdk `node_modules`. Run before every `ng serve` or `ng build`. Alert if versions differ. Add to pre-commit hook for web changes.
**Module(s):** All modules — any Angular version mismatch between shared packages and Shell causes this. Fixed 2026-04-13 by upgrading ui-kit to Angular 21.2.8.

### MODULE_RENAME_STALE_PATHS — Module directory renamed but Shell paths not updated
**Pattern:** `Could not resolve "D:\NovaraDev\Workspace\NovaraModules\novara-module-plan\web\index.ts"` — old directory name, module was renamed to `novara-module-roadmap`.
**Root cause:** When module directories are renamed, the Shell's `tsconfig.json` paths and `app.routes.ts` imports must be updated. Without a Shell build as a gate, stale paths go undetected.
**Fix:** When renaming a module directory, update ALL of: (1) Shell `tsconfig.json` paths, (2) Shell `app.routes.ts` imports, (3) Shell `federation.config.js` if applicable, (4) verify Shell build passes.
**Guardrail:** Module rename checklist in CLAUDE.md. Shell build must pass after any module rename. Consider a script that validates all tsconfig paths resolve to existing directories.
**Module(s):** 8 modules renamed without Shell path update. Fixed 2026-04-13.

### NO_SHELL_BUILD_GATE — TypeScript errors accumulate silently without Shell federation build
**Pattern:** 184 TypeScript errors across 6 modules — all accumulated over weeks without detection. Each module compiles independently, but the Shell federation build (which combines all modules) was never run.
**Root cause:** No CI/CD pipeline or pre-commit hook runs the Shell federation build. Individual module builds pass because they only check their own code. The Shell is the ONLY place where cross-module type compatibility is verified.
**Fix:** (1) Add Shell federation build to CI/CD pipeline — every PR to any module repo triggers a Shell build. (2) Add a pre-push hook that runs `ng build --configuration development` in the Shell before pushing web changes. (3) Run the Shell build manually after any module web change.
**Guardrail:** Weekly automated Shell build even without code changes — catches dependency drift, Angular updates, and accumulated type issues. Consider a "Shell health" dashboard that shows last successful build date.
**Module(s):** All modules with web/ frontends. Systemic gap identified 2026-04-13.

### MODULE_DISCOVERY_BIN_SCAN — GetReferencedAssemblies misses project-referenced modules
**Pattern:** Health endpoint shows 0 modules loaded. All module services fail with "Unable to resolve service for type X" — including existing, unchanged services. `ConfigureServices` never called.
**Root cause:** `Assembly.GetEntryAssembly().GetReferencedAssemblies()` only returns assemblies in the entry assembly's IL metadata. With `dotnet run` and project references, modules compile into the bin folder but aren't listed in GetReferencedAssemblies() because they're resolved by the runtime, not IL-referenced.
**Fix:** Scan bin directory with `Directory.GetFiles(AppContext.BaseDirectory, "Novara.Module.*.dll")` instead of GetReferencedAssemblies(). Exclude Novara.Module.SDK.dll (it's the base, not a module).
**Guardrail:** Health endpoint module count should always be >0 in dev. If 0, check module discovery in Program.cs.
**Module(s):** All modules. Fixed 2026-04-13 in Program.cs.

### PG_DATE_VS_TIMESTAMP — Dapper sends DateTime (timestamp) but PG function expects DATE
**Pattern:** `function xxx(p_date => timestamp) does not exist` when calling a PG function that declares `p_date DATE`. Also: `DateOnly cannot be used as a parameter value` when trying to use C# DateOnly with Dapper.
**Root cause:** C# `DateTime?` maps to PostgreSQL `timestamp`, not `date`. Dapper doesn't support `DateOnly`. When Npgsql sends a timestamp to a function expecting date, PostgreSQL can't find a matching overload.
**Fix:** Declare PG function params as `TIMESTAMP` and cast to DATE inside the function body: `p_targetdate::DATE`. Keep C# as `DateTime?`. Never use `DateOnly` with Dapper.
**Guardrail:** When creating PG functions with date params, always use TIMESTAMP and cast internally. SP coupling comments should note this.
**Module(s):** Roadmap (initiative, milestone). Fixed 2026-04-13.

### UNTYPED_UI_MODEL — Angular component uses any[] instead of typed interface
**Pattern:** `issues: any[] = []` in Angular component class. Template accesses `issue.title`, `issue.status` — no compile-time check, no IDE autocomplete, no refactoring safety. If backend renames a field, the UI silently shows `undefined` instead of breaking at build time.
**Root cause:** Angular doesn't enforce types on HTTP responses — `HttpClient.get<any>()` returns `any`, and developers propagate the `any` through to the component state instead of mapping to an interface. Works fine until a field is renamed or removed.
**Fix:** Create `models/{module}.models.ts` per module with typed interfaces matching the API response shape. Import and use in component properties, method return types, and service calls. Template expressions get autocomplete and compile-time validation.
**Guardrail:** Grep: `": any\[\]"` and `": any ="` in component .ts files. Count should decrease over time. Each module model file should cover all entity types the UI renders.
**Module(s):** Issues (2 components), Plan (1 component), Observe (3 components), Test (6 components), Ship (3 components), Reports (2 components). All fixed 2026-04-13. Created model files: issue.model.ts, plan.models.ts, health.models.ts, test.models.ts, ship.models.ts, report.models.ts.

### NUGET_PRIVATEASSETS_PROJECTREF — PrivateAssets="all" doesn't exclude ProjectReferences from nuspec
**Pattern:** Gateway NuGet 1.0.2 had all 33 modules as transitive dependencies despite `PrivateAssets="all"` on every ProjectReference. Module developers pulled the entire module graph when they only needed the Gateway.
**Root cause:** `PrivateAssets="all"` prevents transitive flow for `PackageReference` but does NOT prevent `ProjectReference` from becoming a nuspec dependency during `dotnet pack`. This is a known NuGet behavior, not a bug — ProjectReferences always become package dependencies unless excluded by other means.
**Fix:** Use MSBuild condition to exclude module ProjectReferences during pack: `<ItemGroup Condition="'$(NuGetPack)' != 'true'">`. Pack with `dotnet pack -p:NuGetPack=true`. SDK reference switches to PackageReference in pack mode.
**Guardrail:** After every `dotnet pack` of the Gateway, inspect the nuspec: `unzip -p *.nupkg *.nuspec | grep "dependency"`. Should show only SDK + infra packages (Dapper, YARP, etc.), never module packages.
**Module(s):** Gateway (Novara.Shell.Gateway). Fixed 2026-04-13. Version 1.0.3 is clean.

### NUGET_GLOB_EMPTY_MATCH — NuGet pack fails when glob matches zero files
**Pattern:** `error: Target path 'contentFiles\any\any\web\**\*.html' contains invalid characters` — the `*` characters appear in the path because no .html files matched the glob.
**Root cause:** When a NuGet `<Content Include="**/*.html" PackagePath="contentFiles/any/any/web/" Pack="true" />` glob matches ZERO files, NuGet doesn't silently skip — it passes the literal glob string `**/*.html` as a target path, which contains `*` (invalid path character). This only fails for empty matches; if even one file matches, it works.
**Fix:** Only include glob patterns for file types that actually exist in the directory. Check with `glob.glob()` or `find` before adding the Content item. Alternatively, use `Condition="Exists('...')"` but this doesn't work well with globs.
**Guardrail:** The pack script (`python3` or `generate-devhost.sh`) must check file existence before adding `<Content Include>` glob items. Never add `**/*.html` if the web/ folder has no .html files.
**Module(s):** All 26 modules with web/ folders. Fixed 2026-04-13 — pack script checks actual file types.

### PYTHON_ESCAPE_IN_XML — Python string escapes corrupt XML content
**Pattern:** `hexadecimal value 0x0C, is an invalid character` in csproj files. MSBuild refuses to parse the file.
**Root cause:** Python string `"\f"` is form-feed (0x0C), `"\a"` is bell (0x07). When writing XML with paths like `contentFiles\any\any\web\federation.config.js`, Python interprets `\f` as form-feed and `\a` as bell characters. The resulting XML contains invisible control characters that MSBuild rejects.
**Fix:** Always use raw strings (`r"..."`) or forward slashes in Python when writing XML/csproj paths. Never use backslash paths in Python string literals without the `r` prefix.
**Guardrail:** After any Python script that writes csproj files, verify with: `python3 -c "open('file.csproj','rb').read().find(b'\x0c')"` — should return -1.
**Module(s):** All 33 modules. Fixed 2026-04-13.

### NUGET_PACK_FORWARD_SLASHES — Always use forward slashes in csproj NuGet packaging paths
**Pattern:** `dotnet pack` on Windows accepts forward slashes in both `Include` and `PackagePath`. Backslashes work in `Include` (glob resolution) but can cause issues in `PackagePath` (stored in nuspec metadata). Mixed slashes cause confusion across tools.
**Root cause:** NuGet Pack targets on Windows normalize paths differently depending on where they appear. `Include` globs work with either slash. `PackagePath` is stored as-is in the nuspec — backslashes may not resolve correctly on Linux/macOS build agents.
**Fix:** Always use forward slashes for all NuGet packaging paths in csproj: `PackagePath="contentFiles/any/any/web/"`, `Include="../../../web/**/*.ts"`. Consistent, cross-platform, no ambiguity.
**Guardrail:** Grep csproj files for `PackagePath="contentFiles\` — should return 0 matches. All should use forward slashes.
**Module(s):** All modules with web content packaging. Established 2026-04-13.

### SDK_ASSEMBLY_VERSION_CONFLICT — Two SDK DLLs with different assembly versions in bin
**Pattern:** `CS0433: The type 'IPermissionChecker' exists in both 'Novara.Module.SDK, Version=1.1.0.0' and 'Novara.Module.SDK, Version=1.0.0.0'` — Gateway was built against SDK dev version (assembly 1.0.0.0), module references SDK stable (assembly 1.1.0.0). Two different SDK DLLs resolve into the bin.
**Root cause:** NuGet pre-release versions (1.1.0-dev.20260413) and stable versions (1.1.0) can have different assembly versions if the csproj `<Version>` was different when each was packed. The Gateway NuGet depends on one SDK version, the module depends on another. NuGet resolves the higher version but the Gateway DLL was compiled against the lower.
**Fix:** Gateway and all modules MUST reference the SAME SDK version (stable). When re-packing the Gateway, always use the stable SDK version in the NuGetPack condition. Bump Gateway version after every SDK version change.
**Guardrail:** After packing Gateway, verify: `dotnet list host/Novara.DevHost.csproj package | grep SDK` — should show exactly ONE SDK version, not two. If the build shows CS0433, the SDK versions are mismatched.
**Module(s):** All modules. Gateway 1.0.4 fixed to use SDK 1.1.0 stable. Learned 2026-04-13.

### GATEWAY_WWWROOT_LEAK — Shell UI accidentally packed inside Gateway NuGet
**Pattern:** `GenerateStaticWebAssetsDevelopmentManifest` crashes with `Sequence contains more than one element` when consuming Gateway NuGet. Build fails unless `StaticWebAssetsEnabled=false`, which disables UI serving.
**Root cause:** The CTO workspace Gateway project had `wwwroot/` with 121 Shell UI build files. `dotnet pack` for Web SDK projects automatically includes `wwwroot/` as `staticwebassets/` in the NuGet package. The .NET 10 Preview SDK then crashes when the consuming project tries to generate the development manifest for these assets (242 endpoints, 2 per file, triggers `SingleOrDefault()` on duplicates).
**Fix:** (1) Remove `wwwroot/` from Gateway project — Shell UI doesn't belong there. (2) Create separate `Novara.Shell.UI` NuGet content package that ships the Angular build as `contentFiles/any/any/wwwroot/` with `copyToOutput=true`. (3) Gateway serves from both `project/wwwroot/` (CTO workspace) and `bin/wwwroot/` (NuGet content via DevHost).
**Guardrail:** After `dotnet pack` of Gateway, verify: `unzip -p *.nupkg | grep staticwebassets | wc -l` should be 0. Gateway NuGet should be <100KB, not 2MB+.
**Module(s):** Gateway. Fixed in 1.0.6. Shell UI 1.0.0 created as separate package. Learned 2026-04-14.

### BULK_MODULE_OPERATIONS_BANNED — Never do bulk operations across 33 modules
**Pattern:** Scripting changes across all 33 module repos from the CTO workspace — updating csprojs, copying files, running builds in a loop. Errors cascade silently, one bad pattern corrupts all 33.
**Root cause:** Treating 33 independent repos as a monolith. Each module is its own project with its own developer. Bulk operations bypass the module developer's review and testing.
**Fix:** Each module must be set up and tested independently. Use a bootstrap script that a module developer (or Claude in that folder) runs. Go one module at a time: bootstrap → build → test → fix → commit → next.
**Guardrail:** Never write a script that loops over all 33 modules and modifies files. Instead, create a template/bootstrap that each module runs independently. If 33 modules need the same change, propagate it through the module template, not a bulk script.
**Module(s):** All. Learned 2026-04-13 after bulk csproj edits introduced form-feed characters and empty-glob errors across 26 modules simultaneously.

### NATIVE_FEDERATION_STICKY_CACHE — dev-server serves 404 on federation chunks after restart
**Pattern:** After restarting `ng serve`, browser console shows cascading 404s like `_angular_platform_browser.D74ZhWa_oy-dev.js 404`, `_angular_core.ABnmtBB2oI-dev.js 404`, etc. The files DO exist under `node_modules/.cache/native-federation/novara_shell/` but ng serve returns 404 for them at their expected URLs. "Federation init failed: TypeError: 404 Not Found" in the console.
**Root cause:** Angular Native Federation (`@angular-architects/native-federation`) maintains a separate federation-chunk cache at `node_modules/.cache/native-federation/`. When ng serve restarts, if it sees a valid remoteEntry.json and matching chunks already in that cache, it SKIPS the internal middleware registration that serves those chunks. Files exist on disk, but the HTTP route to serve them isn't wired up. Wiping only `dist/` and `.angular/cache/` is NOT enough — you must also wipe `node_modules/.cache/native-federation/`.
**Fix:** Before `ng serve`, `rm -rf node_modules/.cache/native-federation`. Guarantees the federation plugin rebuilds from scratch AND re-registers its middleware. The `scripts/restart-dev.sh` script now wipes all three caches (dist, .angular/cache, native-federation) as of 2026-04-15.
**Guardrail:** `scripts/restart-dev.sh` cleans all three cache dirs. Any manual ng serve restart MUST do the same or hit this bug.
**Module(s):** Shell (novara-shell/web). Learned after multiple restart cycles on 2026-04-15.

### RUNAWAY_EMPTY_GOAL_SESSIONS — An internal caller with `goal=""` floods agent_ops.session at ~6/sec
**Pattern:** `agent_ops.session` row count explodes by thousands in minutes. Every row has the same signature: same `agentname`, `goal = ''`, `state = 'CREATED'`, `status = 'Running'`, no `session_event` rows, no `session_transition` rows. The Active Sessions UI shows everything as "Running". Killing the Gateway process stops the loop instantly; restarting without a trigger keeps it stopped. Discovered 2026-04-18 after wiring FeatureImplementerAgent to the `feature_build_with_qa` recipe.
**Root cause (identified 2026-04-18 via guard stack-trace):** `DbContextRecipeEngine.BuildContextAsync` iterates every step in the agent's recipe and dispatches each to its registered step executor — but did NOT filter out lifecycle kinds. When `feature_build_with_qa` (which mixes context steps + lifecycle steps) was run, the lifecycle `agent_loop` step was invoked during CONTEXT assembly. `AgentLoopStepExecutor.ExecuteAsync` then called `runtime.RunAsync(ctx.Goal, ...)` with `ctx.Goal = ""` (context-only StepContext has no real goal) → that call re-entered `AgentRuntimeService.RunAsync` → which called `BuildContextAsync` again → infinite recursion creating one session per loop iteration. Fix: `DbContextRecipeEngine.BuildContextAsync` now skips any step whose kind is in a `LifecycleStepKinds` allowlist (session_start, session_setup, agent_loop, approval_gate, session_teardown, session_end, qa_gate, testing_gate, replay_verify). The Plan's eventual migration is still needed — `IContextRecipeEngine` is meant to be deleted once all callers go through `IRecipeRunner` — but the lifecycle-skip patch closes the recursion today.
**Fix:** Two layers of defense — (1) `AgentSessionService.RunAsync` validates via `Guard.NotEmpty(goal, ...)` at the public API boundary; (2) `AgentRuntimeService.RunAsync` rejects empty goals on entry, logs a stack trace once so the bad caller can be identified, and returns `Blocked` without inserting a session. Applied 2026-04-18 + 12,905 orphan rows hard-deleted.
**Guardrail:** Every public entry point that creates a session MUST fail-fast on empty goal or empty agent name. A session with no goal is always a bug — never a valid state. The stack-trace log is intentional: it's the only way to catch internal-process loops where HTTP request logs aren't the culprit.
**Module(s):** novara.agentic — `AgentRuntimeService` + `AgentSessionService`. Any future module that calls `ICrossModuleMediator.SendAsync(new SubmitAgentWork { ... })` is also protected (flows through the guarded AgentSessionService).

### CLAUDE_CLI_MODEL_ALIAS — `claude-code` is a product name, not a Claude model ID
**Pattern:** Every agent session using Claude CLI exits with code=1 after ~3s, empty stderr. stdout contains: `"There's an issue with the selected model (claude-code). It may not exist or you may not have access to it. Run --model to pick a different model."`. Platform-seeded agents have `model = 'claude-code'` in `agenthub.definition` and in the per-product `agent_ops.catalog`.
**Root cause (2026-04-18):** Claude CLI's `--model` flag expects a Claude model identifier — `sonnet`, `opus`, `haiku`, or full form like `claude-opus-4-7[1m]`. The string `"claude-code"` is the PRODUCT name (Claude Code, the CLI tool). The CLI doesn't know the product name as a model, rejects it, and dies. LocalClaudeCliAgentReasoning was passing `--model "claude-code"` blindly.
**Fix:** In `LocalClaudeCliAgentReasoning.InvokeCliAsync`, treat `claude-code` and `claude-cli` as aliases for "use CLI default model" — drop the `--model` flag in that case. Real model IDs pass through unchanged.
**Guardrail:** Any future adapter that forwards a model name to an LLM CLI MUST normalize product-name aliases before passing through. The empty-stderr signature was the diagnostic trap — logging stdout on failure (not just stderr) is essential for these Node.js-based CLIs. Added to LocalClaudeCliAgentReasoning's error path.
**Module(s):** novara.agentic — LocalClaudeCliAgentReasoning. Future: same check belongs in any `ILlmProvider` that shells out to a vendor CLI.

### DAPPER_UNDERSCORE_SILENT_DROP — RESOLVED (2026-04-15 safety net) + convention retired (2026-04-21)
**Historical pattern:** API query returned rows, every mapped property came back as its C# default (false / null / 0). No exception, no log. Column `is_system` did not map to C# `IsSystem`; `content_type` did not map to `ContentType`.
**Original root cause:** Dapper's default column-to-property mapping is case-insensitive but does not bridge underscores.
**Resolution (2026-04-15):** `Dapper.DefaultTypeMap.MatchNamesWithUnderscores = true` set globally in `DapperModuleDbContext` static ctor. Snake_case columns now map automatically to PascalCase C# properties (`parent_session_id` → `ParentSessionId`). Zero friction either way.
**Convention update (2026-04-21):** the prior "lowercase-no-underscore" rule has been RETIRED. It was a workaround picked alongside the real SDK fix on 2026-04-15, and it drifted to half-ignored (`agent_ops.dispatch_queue`, `spec_batch_item`, `agent_maturity_stats` all shipped snake_case). Going forward: **`snake_case` is the standard** — matches the PG ecosystem, matches what devs naturally write, eliminates cross-session drift.
**Guardrail today:** none needed for this class. Both styles bridge cleanly. Existing no-underscore tables stay as-is (no renames).
**Module(s):** First surfaced in `novara.knowledgebank` DMS migration 2026-04-15. From 2026-04-21 this class is no longer a bug pattern.

### BROWSER_CACHE_STALE — "Clear cache to recover" ritual after every deploy
**Pattern:** After a deploy, users report "page won't load", blank main pane, console errors like `Failed to load module script: Expected a JavaScript module` or 404s on federation chunks whose names don't exist on the current build. Hard refresh doesn't fix it — users must clear cache or use incognito. Dev team chases it as if it were a CDN / DNS / federation bug.
**Root cause:** GatewayExtensions cached EVERY static file for a year unless the name ended in `.html`. So main.js, polyfills.js, styles.css, federation.manifest.json, build-info.json all got `Cache-Control: public, max-age=31536000, immutable`. Chrome held the old main.js long after the new one was deployed. Old main.js references new-build chunks that don't exist on the server → 404 → blank page. bfcache made it worse.
**Fix (3 layers, all required):**
  1. Gateway (GatewayExtensions.cs) classifies files by regex `[.-]<8+char hash>(-dev)?.(js|mjs|css)` → 1y immutable for content-hashed chunks, no-cache for stable-name entries (main.js, styles.css, *.json, *.html, favicon).
  2. Shell emits `public/build-info.json` on every prebuild/prestart with `{version, sha, builtAt}` (scripts/stamp-build-info.mjs).
  3. Shell-sdk `BuildVersionService` polls `/build-info.json` every 2 min; when the fingerprint shifts, shows a reload banner. Gateway `/api/v1/version` folds the same shell fingerprint into the gateway+modules payload for single-call consumers.
**Guardrail:** Regex classifier is the primary defense — even without the polling banner, the next fetch of main.js is fresh. Polling is belt-and-braces for long-running tabs. The triple (Gateway cache rule, build stamp, polling banner) cannot both ship stale entry files AND fail to notify a running tab within 2 min.
**Why it existed:** The original rule was written for a simpler SPA shape where only HTML needs revalidation. Angular + Native Federation + ng-packagr emit hashed chunks AND stable-name entries side-by-side. A blanket 1y cache on everything-that-isn't-.html is catastrophically wrong for that mix.
**Module(s):** Gateway (all customer deployments). Shell UI. Every federated module that re-publishes its `remoteEntry.json` / stable filenames. Fixed 2026-04-19.

### LOSSY_AUDIT_REFACTOR — Replacing a self-contained audit blob with a foreign-key pointer
**Pattern:** Code that stored full text for audit purposes (`sourcePromptJson = { systemPrompt: "<full text>", userMessage }`) gets refactored to `{ promptVersionId: N, userMessage }` under the guise of normalization. Looks cleaner. Breaks the audit trail the moment the referenced version row is hard-deleted, archived, or the reader lacks DB access.
**Root cause:** Normalization instinct ("I can reference this by id") without checking intent. Author didn't ask what failure modes the original self-contained form survived. "Immutable" feels equivalent to "always accessible" — it isn't. Admins can hard-delete. Retention policies can archive. Cross-region consumers may lag. A court subpoena may need the exact text without DB access.
**Fix:** Preserve BOTH — store the pointer AS WELL AS the rendered text. Space cost is negligible (audit tables are rarely hot). Correlation key (`promptVersionId`) lets analytics join into usage rollups; the blob (`systemPrompt`) stays self-contained. Example: `{ promptVersionId: 42, systemPrompt: "You are...", userMessage: "..." }`.
**Guardrail (process):**
 1. Default on refactor: ADD fields, don't REPLACE them. Removing requires explicit written justification.
 2. Any diff that REDUCES content being assigned to fields matching `*audit*|*sourceprompt*|*snapshot*|*history*|*provenance*` needs a "what am I losing" note.
 3. For every audit table, ask: "Given one row, can I reconstruct what happened without joining any other table?" If no, the row is under-specified or over-normalized.
**Guardrail (code, future):** pre-commit hook that grep-flags diffs removing characters from such assignments and demands an explicit `// narrowing-audit: <reason>` opt-in.
**Why it existed:** Committed 2026-04-21 during BlueprintService migration to IPromptStudioBridge. sourcePromptJson dropped full systemPrompt text. User caught in review within minutes. Fix: store both promptVersionId AND rendered systemPrompt.
**Module(s):** Any module with audit-class storage. High-risk areas: roadmap BlueprintService sourcePromptJson, agentic agent_ops.session prompt_snapshot_json (kept correct), promptstudio.prompt_usage (cost audit), audit.log (everywhere).
