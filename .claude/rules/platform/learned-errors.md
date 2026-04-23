---
globs: "**/*.cs,**/*.ts,**/*.sql"
---

# Learned Errors — Living Knowledge from Debugging

Every bug whose root cause wasn't obvious, repeated 2×, took >10 min to diagnose, or reached (or could reach) production → add an entry. Claude reads this before writing code.

**Entry format:**
```
### [ERROR_CLASS] — [Short description]
**Pattern:** what it looks like
**Root cause:** what was wrong
**Fix:** what to do
**Guardrail:** SDK class / rule / check preventing recurrence
**Module(s):** where it hit
```

---

## Error Classes

### DAPPER_NULL_MAPPING — DB column exists but C# entity property missing
**Pattern:** API returns 200 but field is null. No error.
**Root cause:** Dapper maps columns to properties BY NAME. Missing property = column silently dropped.
**Fix:** Add property to entity. Verify ALL columns in SELECT have matching properties.
**Guardrail:** `Guard.Found()` for null results. For individual fields, entity must match SP output columns.
**Module(s):** Issues (ContextJson), Roadmap.

### EMPTY_CATCH_SILENT — Exception swallowed, feature silently fails
**Pattern:** Feature "doesn't work", no errors in logs. Returns empty data or null.
**Root cause:** `catch (Exception) { return Array.Empty<T>(); }` or `catch { return null; }`.
**Fix:** Remove empty catch. Let exception propagate. GlobalExceptionMiddleware handles it.
**Guardrail:** `SafeExecute.RunAsync()` for non-critical ops. NEVER catch silently for data ops.
**Module(s):** Any service with try/catch.

### SP_PARAM_TYPE_MISMATCH — VARCHAR parameter for INT column
**Pattern:** Query runs but wrong results / full table scan.
**Root cause:** SP param VARCHAR for INT column → PostgreSQL implicit cast blocks index usage.
**Fix:** SP param INT. Convert string → int in C# BEFORE call.
**Guardrail:** DB design principles require INT for all ID params. /deep-scan detects.

### MISSING_ISDELETED_FILTER — Query returns soft-deleted rows
**Pattern:** Deleted items appear in lists. Count is wrong.
**Root cause:** SP WHERE clause missing `isdeleted = false`.
**Fix:** Every SELECT on soft-deletable table includes the filter.
**Guardrail:** DB standards require isdeleted filter on every SELECT.

### API_RETURNS_200_WITH_NULL — Endpoint succeeds but data is null/empty
**Pattern:** Frontend shows empty state but data exists in DB.
**Root cause:** (1) Dapper null mapping, (2) DTO missing field, (3) service returns null wrapped in Ok(), (4) wrong ProductId context.
**Fix:** Trace 5 layers: DB → SP → service → DTO → frontend model.
**Guardrail:** `Guard.Found()` for single-entity lookups. Verify response body, not just HTTP 200.
**Module(s):** All — most common bug class.

### FRONTEND_MODEL_DRIFT — API returns field but Angular model doesn't have it
**Pattern:** API returns data, UI doesn't display new field.
**Root cause:** TS interface missing the property. Angular silently ignores extra JSON fields.
**Fix:** Add property to TS model. Update template.
**Guardrail:** Adding a DB column means updating all 4 layers: Entity → DTO → API → TS model.

### CONNECTION_TIMEOUT_SILENT — DB timeout swallowed
**Pattern:** API hangs 30s then returns empty/generic error.
**Fix:** Explicit commandTimeout on slow queries. Use connection pooling.
**Guardrail:** IModuleDbContext timeout overloads. /health/ready tests DB connectivity.
**Module(s):** Health (telemetry tables), Roadmap (complex joins).

### EVENT_HANDLER_CRASH — One handler crash prevents others
**Pattern:** Module A publishes, B crashes, C's handler never runs.
**Root cause:** Event bus didn't isolate handler execution.
**Fix:** InMemoryEventBus rebuilt with per-handler isolation (5s timeout + circuit breaker).
**Guardrail:** SDK EventBus isolates each handler (try/catch + timeout). Fixed before hitting prod.

### CORS_ORIGIN_MISSING — Browser blocks, Postman works
**Fix:** Add origin to appsettings.json `Cors:Origins`.
**Guardrail:** Document all deployment origins. Never wildcard (*) in prod.

### JWT_CLAIM_MISSING — GetUserId() throws, claim not in token
**Fix:** Verify /dev-login generates all claims: userId, email, role, sessionId.
**Guardrail:** `ModuleBaseController.GetUserId()` throws explicitly — never silent 0.

### MODULE_ACCESSES_PLATFORM_DB — Product module queries platform schema
**Pattern:** Module uses `IPlatformDbContext` to query platform tables. Hidden coupling, breaks distributed deployments.
**Fix:** Use `productcore.user` / `productcore.product` (synced copies). `IModuleSettingsStore` for settings. `ICacheService` for cached lookups.
**Guardrail:** Only modules with `DbScope = ModuleDbScope.Platform` may inject `IPlatformDbContext`. Pre-commit + SDK compile-time enforcement.
**Module(s):** Grep `IPlatformDbContext` in non-platform modules.

### CREATED_AT_ACTION_ZERO_ID — CreatedAtAction with id=0 → "No route matches"
**Pattern:** POST returns 500 with `InvalidOperationException`.
**Root cause:** `CreatedAtAction(nameof(GetDetail), new { id = 0 }, ...)` — placeholder ID can't build Location URL with `{id:int}` route constraint.
**Fix:** Use `Ok(ApiResponse<T>.Ok(result, "Created."))` — Angular doesn't use Location headers.
**Guardrail:** `CrudServiceBase` + module template use Ok(). Never CreatedAtAction with placeholder IDs.

### MISSING_DB_DEFAULTS — NOT NULL column without DEFAULT
**Pattern:** `null value in column "isdeleted" violates not-null constraint` on CREATE.
**Fix:** `ALTER TABLE ALTER COLUMN SET DEFAULT`. isdeleted=false, counts=0, status='Draft'.
**Guardrail:** DATABASE_STANDARDS.md requires DEFAULT on every NOT NULL column. /deep-scan should check.

### SP_COUPLING_COMMENT_WRONG — Comment references old SP signature
**Pattern:** `function xxx() does not exist` — function exists but different required params. Service passes wrong params because comment shows old signature.
**Fix:** Verify comment against live function: `SELECT pg_get_function_arguments(oid) FROM pg_proc WHERE proname = 'xxx'`. Update both comment and Dapper params.
**Guardrail:** Verify SP coupling comments against live DB on first test. /deep-scan compares comments to actual signatures.

### MISSING_CANCELLATION_TOKEN — Async method without CT
**Pattern:** User disconnects, server keeps processing. Under load (pool max 50), 50 slow queries exhaust the pool.
**Fix:** `CancellationToken ct = default` as last param on every public async method. Pass through to `ExecuteProcedureAsync`. Controllers get CT auto-bound from `HttpContext.RequestAborted`.
**Guardrail:** Every new async method requires CT. Pre-commit hook flags async methods without it.
**Module(s):** Codebase-wide gap (252 methods). Fixed progressively.

### ID_FILTER_VS_FK — VARCHAR ID filter vs INT FK
**Pattern:** `p_assigneeuserid TEXT` looks like type mismatch (column INT) but it's a FILTER, not FK.
**Root cause:** Filter params support CSV ("1,2,3") for multi-user filtering. Entity property correctly `int?`.
**Fix:** No fix if intentional for CSV filtering. Document: `// p_assigneeuserid VARCHAR — CSV filter, not FK`.
**Guardrail:** Distinguish FK params (INT, mandatory) vs filter params (TEXT, CSV acceptable). Document in SP coupling comment.
**Module(s):** Issues (getbyproduct), Reports.

### MISSING_SP_COUPLING_COMMENT — ExecuteProcedure call without parameter contract
**Pattern:** Dapper call has no inline comment. When SP signature changes, C# silently breaks at runtime.
**Fix:** Every `ExecuteProcedure*` gets a comment:
```csharp
// SP: {schema}.{functionname}(p_param1 TYPE, ...)
// Returns: {EntityType} row(s) | void
```
**Guardrail:** Pre-commit hook counts `// SP:` vs `ExecuteProcedure` — warn <80%, block <50%.
**Module(s):** 11 services had zero SP comments. Fixed 2026-04-13.

### UNBOUNDED_LIST_RETURN — IEnumerable without pagination
**Pattern:** `GetAllAsync()` loads ALL rows. 50K features = OOM or 30+ sec response.
**Fix:** Replace `IEnumerable<T>` with `PagedResponse<T>` for lists >~100 items. Add `p_page`/`p_pagesize` to SP. Include `COUNT(*) OVER() AS totalcount`.
**Guardrail:** New list methods require PaginationParams. Pre-commit warn on `IEnumerable<` in service interfaces.
**Module(s):** 96 methods codebase-wide. Priority: GetCollections, GetStrategies, GetInsights, GetJournal, GetRoles, GetLabels.

### FIRE_AND_FORGET_UNOBSERVED — Task.Run without error visibility
**Pattern:** `_ = Task.Run(async () => { ... })` — inner throw unobserved, no log, data silently lost. Bypasses graceful shutdown.
**Fix:** `SafeExecute.FireAndForget()` for side effects. `IJobService.EnqueueAsync()` for tracked work with retry. Never raw `Task.Run` for business logic.
**Guardrail:** Pre-commit flags `Task.Run` in service code.
**Module(s):** CodeGenerationService (has full try/catch — acceptable until job queue wired). FeatureWorkItemService (fixed).

### RAW_SQL_BYPASSES_SP — Inline SQL instead of function call
**Pattern:** `connection.ExecuteAsync("UPDATE ... SET isdeleted = true")` — bypasses SP layer.
**Fix:** Create `{schema}.{function}()` for every mutation. Inline SQL acceptable only for system table inspection (pg_proc, information_schema).
**Guardrail:** Grep `connection.Execute` / `conn.Query` — only AuditExecutionService (DB inspection) should have them.
**Module(s):** DesignStudioService (SPs created 2026-04-12).

### MULTI_SP_METHOD_INVISIBLE_CALLS — Method-level block comment hides uncovered calls
**Pattern:** Method calls 4-5 SPs; single block comment at top. Grep coverage reports 56-75% but developer thinks "covered". Uncovered calls invisible in review.
**Fix:** Every call site gets its own inline `// SP:` comment. Repeated SPs get a qualifier: `// SP: audit.completerun — mark failed`.
**Guardrail:** SP coverage check per file: target 100%.
**Module(s):** BlueprintChatService, FeatureWorkItemService, DesignStudioService, CodeGenerationService. All 100% on 2026-04-13.

### HARDCODED_SYSTEM_USER_ID — Magic userId for AI user
**Pattern:** `UserId = 1638` hardcoded for AI-generated content. Works in dev, fails every customer deployment (user IDs are auto-incremented per DB).
**Fix:** `ISystemUserResolver` in SDK + `SystemUserResolver` in Gateway. Inject and call `GetAiUserIdAsync()`. Cached 30 min.
**Guardrail:** Grep `UserId = [0-9]{3,}` in service code — any literal >100 is suspicious.
**Module(s):** DesignStudioService, FeatureTaskService, BlueprintChatService. Fixed 2026-04-13.

### HARDCODED_MODEL_VERSION — Stale model string instead of LLM response
**Pattern:** `ModelVersion = "claude-sonnet-4-20250514"` hardcoded. DB records the coded-at-time assumption, not actual model used.
**Fix:** Use `llmResult.Model` from response. For async, record `GenerationStatus.Pending` and update after completion.
**Guardrail:** Grep `claude-` / `gpt-` in service code (not prompts). Model strings come from config or LLM response.
**Module(s):** CodeGenerationService, DocGenerationService.

### MAGIC_STRING_PROMPT_KEY — Prompt key as raw string
**Pattern:** `GetPromptAsync("prompt.feature.chat.sytem")` typo fails silently — prompt not found, AI runs without system instructions, garbage output.
**Fix:** `PromptKeys.cs` per module's `Constants/`. All keys are constants: `_llm.GetPromptAsync(RoadmapPromptKeys.ChatSystem)`.
**Guardrail:** `GetPromptAsync` calls must reference a `*PromptKeys.*` constant. Grep for raw-string calls.
**Module(s):** 30 keys across Roadmap/ThinkBoard/EnterpriseThinkBoard/Audit/Health. Fixed 2026-04-13.

### MAGIC_STRING_LLM_ROLE — Hardcoded "user"/"assistant"/"system"
**Pattern:** `Role = "assitant"` typo → silent DB corruption.
**Fix:** SDK `LlmRoles.User`, `.Assistant`, `.System` constants.
**Guardrail:** Grep `Role = "user"|"assistant"|"system"` → 0 matches.
**Module(s):** DesignStudioService, BlueprintChatService, FeatureTaskService.

### FEDERATION_CHANGE_DETECTION — Standalone components need explicit cdr.detectChanges()
**Pattern:** Component shows "Loading..." forever. API returns data (curl confirms), template doesn't update. No console errors.
**Root cause:** Module Federation loads standalones in separate NgZone context. Automatic zone-based change detection doesn't trigger for async ops in federated components.
**Fix:** Inject `ChangeDetectorRef`. Call `cdr.detectChanges()` after EVERY async update (both `next` and `error` in every `subscribe()`).
**Guardrail:** Every federated standalone component has `ChangeDetectorRef` injected. Pre-commit grep `.subscribe({` without nearby `detectChanges`.
**Why it's dangerous:** Zero error signal. Only visible when running Shell UI, not independent module build.
**Module(s):** ALL modules with Angular components.

### ANGULAR_VERSION_MISMATCH — Different @angular versions across shared packages
**Pattern:** `NG3004: Unable to import pipe DecimalPipe` — pipe types resolve through different Angular version than Shell's.
**Root cause:** Shared packages (ui-kit, shell-sdk) had Angular 20.3 while Shell was 21.2. Federation build resolves types through the ui-kit's Angular.
**Fix:** Upgrade all shared packages to match Shell Angular version. `npm install @angular/common@21.x @angular/core@21.x` in ui-kit and shell-sdk.
**Guardrail:** Version check script comparing `@angular/core` across Shell/ui-kit/shell-sdk node_modules. Pre-commit for web changes.

### MODULE_RENAME_STALE_PATHS — Module renamed but Shell tsconfig not updated
**Pattern:** `Could not resolve "D:\...\novara-module-plan\web\index.ts"` — old name, module renamed.
**Fix:** Module rename = update ALL: Shell `tsconfig.json` paths, `app.routes.ts` imports, `federation.config.js`. Verify Shell build passes.
**Guardrail:** Module rename checklist in CLAUDE.md. Script validating tsconfig paths resolve.

### NO_SHELL_BUILD_GATE — TS errors accumulate silently without federation build
**Pattern:** 184 TS errors across 6 modules accumulated over weeks. Each module compiles independently; only Shell federation build catches cross-module type incompat.
**Fix:** Shell federation build in CI every PR. Pre-push hook runs `ng build --configuration development`. Weekly automated Shell build catches dependency drift.
**Guardrail:** "Shell health" dashboard showing last successful build date.

### MODULE_DISCOVERY_BIN_SCAN — GetReferencedAssemblies misses project refs
**Pattern:** Health endpoint shows 0 modules. All module services fail "Unable to resolve service". `ConfigureServices` never called.
**Root cause:** `GetReferencedAssemblies()` only returns IL-metadata-referenced assemblies. With `dotnet run` + project refs, modules are runtime-resolved, not IL-referenced.
**Fix:** Scan bin: `Directory.GetFiles(AppContext.BaseDirectory, "Novara.Module.*.dll")`. Exclude `Novara.Module.SDK.dll`.
**Guardrail:** Module count >0 in dev; if 0, check Program.cs discovery.

### PG_DATE_VS_TIMESTAMP — Dapper sends timestamp, PG function expects DATE
**Pattern:** `function xxx(p_date => timestamp) does not exist`. Also: `DateOnly cannot be used as a parameter value`.
**Root cause:** C# `DateTime?` maps to PG `timestamp`, not `date`. Dapper doesn't support `DateOnly`.
**Fix:** Declare PG function params as `TIMESTAMP`, cast internally: `p_targetdate::DATE`. Keep C# as `DateTime?`. Never use `DateOnly` with Dapper.
**Guardrail:** PG functions with date params use TIMESTAMP + internal cast. Note in SP coupling comment.

### UNTYPED_UI_MODEL — Angular component uses any[]
**Pattern:** `issues: any[] = []`. Template accesses `issue.title` with no compile-time check. Backend rename → UI shows `undefined`.
**Fix:** `models/{module}.models.ts` per module with typed interfaces matching API shape. Use in component properties, method returns, service calls.
**Guardrail:** Grep `": any\[\]"` / `": any ="` in component .ts — should trend down.
**Module(s):** Issues, Plan, Observe, Test, Ship, Reports. Fixed 2026-04-13.

### NUGET_PRIVATEASSETS_PROJECTREF — PrivateAssets doesn't exclude ProjectRefs from nuspec
**Pattern:** Gateway NuGet shipped all 33 modules as transitive deps despite `PrivateAssets="all"`.
**Root cause:** `PrivateAssets="all"` prevents transitive flow for `PackageReference` but NOT for `ProjectReference` during pack.
**Fix:** MSBuild condition excludes ProjectRefs during pack: `<ItemGroup Condition="'$(NuGetPack)' != 'true'">`. Pack with `dotnet pack -p:NuGetPack=true`.
**Guardrail:** After pack, `unzip -p *.nupkg *.nuspec | grep "dependency"` — only SDK + infra, never modules.
**Module(s):** Gateway. Fixed 1.0.3.

### NUGET_GLOB_EMPTY_MATCH — NuGet pack fails when glob matches zero files
**Pattern:** `error: Target path 'contentFiles\...\web\**\*.html' contains invalid characters`.
**Root cause:** Empty glob = NuGet passes literal `**/*.html` as target path (contains `*`, invalid char).
**Fix:** Pack script checks file existence before adding `<Content Include>` glob.
**Guardrail:** Pack script verifies actual file types before adding content items.

### PYTHON_ESCAPE_IN_XML — Python string escapes corrupt XML
**Pattern:** `hexadecimal value 0x0C, is an invalid character` in csproj.
**Root cause:** Python `"\f"` = form-feed (0x0C), `"\a"` = bell (0x07). Paths like `contentFiles\any\any\web\federation.config.js` get interpreted.
**Fix:** Always raw strings (`r"..."`) or forward slashes in Python writing XML/csproj.
**Guardrail:** After Python csproj writes, verify: `open('file.csproj','rb').read().find(b'\x0c')` == -1.

### NUGET_PACK_FORWARD_SLASHES — Use forward slashes in NuGet packaging paths
**Pattern:** Windows accepts both but mixed slashes cause cross-platform issues. `PackagePath` backslashes may not resolve on Linux/macOS build agents.
**Fix:** Forward slashes for all NuGet packaging paths in csproj. `PackagePath="contentFiles/any/any/web/"`.
**Guardrail:** Grep `PackagePath="contentFiles\` → 0 matches.

### SDK_ASSEMBLY_VERSION_CONFLICT — Two SDK DLLs with different assembly versions
**Pattern:** `CS0433: The type 'IPermissionChecker' exists in both 'SDK, Version=1.1.0.0' and 'SDK, Version=1.0.0.0'`.
**Root cause:** NuGet pre-release (1.1.0-dev) and stable (1.1.0) can have different assembly versions if csproj `<Version>` differed at pack time.
**Fix:** Gateway + all modules reference SAME SDK version (stable). Re-pack Gateway uses stable SDK. Bump Gateway after every SDK change.
**Guardrail:** After pack: `dotnet list package | grep SDK` → exactly ONE SDK version.

### GATEWAY_WWWROOT_LEAK — Shell UI packed inside Gateway NuGet
**Pattern:** `GenerateStaticWebAssetsDevelopmentManifest` crashes with `Sequence contains more than one element`. Requires `StaticWebAssetsEnabled=false` to build, which disables UI serving.
**Root cause:** Gateway project had `wwwroot/` with Shell UI build files. `dotnet pack` for Web SDK auto-includes `wwwroot/` as `staticwebassets/` in NuGet. .NET 10 SDK crashes on 242 endpoints (2 per file).
**Fix:** (1) Remove `wwwroot/` from Gateway. (2) Separate `Novara.Shell.UI` NuGet ships Angular build as `contentFiles/any/any/wwwroot/`. (3) Gateway serves from project/wwwroot/ (dev) and bin/wwwroot/ (NuGet via DevHost).
**Guardrail:** After pack: `unzip -p *.nupkg | grep staticwebassets | wc -l` == 0. Gateway NuGet <100KB, not 2MB+.
**Module(s):** Gateway 1.0.6. Shell UI 1.0.0 as separate package.

### BULK_MODULE_OPERATIONS_BANNED — Never script changes across all 33 modules
**Pattern:** Scripting csproj updates / file copies / bulk builds in a loop — errors cascade silently, one bad pattern corrupts all 33.
**Fix:** Each module set up + tested independently. Bootstrap script the module developer runs. One at a time: bootstrap → build → test → fix → commit → next.
**Guardrail:** No scripts that loop over all modules and modify files. Propagate via module template.
**Module(s):** All. Learned after bulk csproj edits introduced form-feed + empty-glob errors across 26 modules at once.

### NATIVE_FEDERATION_STICKY_CACHE — dev-server 404s on federation chunks after restart
**Pattern:** Browser 404s on `_angular_platform_browser.D74ZhWa_oy-dev.js` etc. Files exist under `node_modules/.cache/native-federation/` but ng serve returns 404.
**Root cause:** `@angular-architects/native-federation` maintains separate federation-chunk cache. On restart, valid remoteEntry.json + matching chunks → plugin SKIPS middleware registration. Files exist on disk, HTTP route not wired.
**Fix:** Before `ng serve`: `rm -rf node_modules/.cache/native-federation`. `scripts/restart-dev.sh` wipes dist + .angular/cache + native-federation.
**Guardrail:** `restart-dev.sh` cleans all three. Manual restarts must do the same.

### NGDEVMODE_UNDEFINED_AFTER_LONG_HMR — `ngDevMode is not defined` during class-field init
**Pattern:** Fresh page load (Ctrl+Shift+R or cross-origin navigation) crashes at service construction with `ReferenceError: ngDevMode is not defined`, usually surfacing on whichever service has a class field like `_modules = signal([], ...ngDevMode ? [{debugName:'_modules'}] : [])`. DevTools shows the stack inside a compiled `_ServiceName` constructor at a field-initializer line. App doesn't bootstrap; `<app-root>` stays empty.
**Root cause:** Angular 21's `signal(..., { debugName })` emits `ngDevMode ? [...] : []` in compiled output. `ngDevMode` is a build-time global that `@angular/build` + esbuild inject via a `define:` plugin in dev builds. After many hours of HMR (12+ hrs observed), rebuilt chunks occasionally lose the define and the flag is simply undefined. Production builds replace it with `false` via terser and are unaffected. Class fields initialize BEFORE the constructor, so the error fires before any `try/catch`.
**Fix:** Top of `NovaraWorkspaceShell/novara-shell/web/src/main.ts` (BEFORE any `import`): `(globalThis as any).ngDevMode ??= true;`. Guards against the esbuild define drifting off rebuilt chunks — harmless in prod (terser strips the branch). Plus: after long sessions, `bash scripts/restart-dev.sh shell` forces a clean `.angular/cache` + federation-cache wipe.
**Guardrail:** Polyfill stays in main.ts as belt-and-braces. `trace-dev-entry.js` in `.claude/tools/playwright-e2e/` surfaces this class of error on every "Shell is stuck" investigation.
**Why it hides:** User's real browser survives with cached chunks locked in a working set. Full page reload (hard-refresh, cross-origin navigation, new tab) re-fetches fresh and exposes the rot. Appeared when Gateway cross-origin `/dev-entry` redirect (Shell on :4200, Gateway API-only on :5050) forced a full navigation from :5050 to :4200 on 2026-04-22.
**Module(s):** Novara Shell UI + any module using `signal({ debugName })`.

### RUNAWAY_EMPTY_GOAL_SESSIONS — Internal caller with goal="" floods agent_ops.session ~6/sec
**Pattern:** Row count explodes by thousands in minutes. Same agentname, `goal=''`, no session_event/transition rows. Killing Gateway stops it instantly.
**Root cause:** `DbContextRecipeEngine.BuildContextAsync` dispatched every step in recipe — including lifecycle kinds like `agent_loop`. `AgentLoopStepExecutor` called `runtime.RunAsync(ctx.Goal = "")` → re-entered `BuildContextAsync` → infinite recursion, one session per loop.
**Fix:** Two layers — (1) `AgentSessionService.RunAsync` validates goal via `Guard.NotEmpty`. (2) `AgentRuntimeService.RunAsync` rejects empty goals on entry, logs stack trace once to identify bad caller, returns `Blocked`. `BuildContextAsync` skips lifecycle kinds via `LifecycleStepKinds` allowlist. Applied 2026-04-18; 12,905 orphan rows deleted.
**Guardrail:** Every session-creation entry point fails fast on empty goal/agentname. See also `recursion-safety.md` and arch decision #16.
**Module(s):** novara.agentic.

### CLAUDE_CLI_MODEL_ALIAS — `claude-code` is a product name, not a model ID
**Pattern:** Agent sessions exit code=1 after ~3s, empty stderr. stdout: "issue with the selected model (claude-code). It may not exist...".
**Root cause:** Claude CLI `--model` expects model identifier (`sonnet`, `opus`, `haiku`, or full ID). `"claude-code"` is the CLI PRODUCT name. Platform-seeded agents had `model = 'claude-code'`.
**Fix:** `LocalClaudeCliAgentReasoning.InvokeCliAsync` treats `claude-code`/`claude-cli` as aliases for CLI default — drops `--model` flag. Real model IDs pass through.
**Guardrail:** Any adapter forwarding model names to LLM CLI normalizes product-name aliases. Log stdout on failure (not just stderr) for Node.js-based CLIs.
**Module(s):** novara.agentic.

### DAPPER_UNDERSCORE_SILENT_DROP + SP_VERSION_BUMP_MISSED_PARAM_MIGRATION — SUPERSEDED (2026-04-22)
**Historical pattern:** Two incidents, now fully resolved:
1. (2026-04-15) Dapper's default column mapping didn't bridge `snake_case` columns to C# PascalCase → silent nulls. Fixed same-day via `DefaultTypeMap.MatchNamesWithUnderscores = true`.
2. (2026-04-22) Gateway's `BuildPgCall` heuristic ("function name has underscore? → send snake_case params, else lowercase") produced 42883s for 54 "drifter bomb" functions where the name acquired an underscore but params stayed on legacy form.

**Resolution (both):** See `.claude/architecture/2026-04-22-sp-calling-convention-adr.md` — Phase 1 runtime introspection (BuildPgCall queries `pg_proc.proargnames` per call, caches per-process), Phase 2 snake_case sweep (800 ProductDB functions converged, 0 drifters remain), Phase 3 pre-commit hook (`check-sql-param-naming.py` blocks new legacy params), Phase 4 startup validator (`SpNamesValidator` checks every SpNames constant against pg_proc at boot).

**Why kept as a one-liner here:** future agent hitting a 42883 should recognize the CLASS, not redo the investigation. The 54 drifter bombs are defused; the bug class is closed.

### INTROSPECTION_CACHE_STALE_AFTER_DDL — OPEN (2026-04-22)
**Pattern:** Gateway's `_spParamNamesCache` (ConcurrentDictionary, per-process) caches `pg_proc.proargnames` on first call. When DDL renames a function's params mid-session, the Gateway keeps calling with the OLD names and hits 42883.
**Workaround:** restart Gateway after any function-signature-changing migration.
**Planned fix:** LISTEN/NOTIFY on `pg_proc` changes OR time-based TTL on the cache OR admin endpoint to flush. Tracked in ADR § Open items.
**Module(s):** Gateway infrastructure.

### BROWSER_CACHE_STALE — "Clear cache to recover" ritual after every deploy
**Pattern:** After deploy, blank main pane, `Failed to load module script` / 404s on federation chunks. Hard refresh doesn't help — users clear cache or use incognito.
**Root cause:** Gateway cached EVERY non-`.html` static file for 1 year. Chrome held old `main.js` long after deploy. Old `main.js` → new chunks don't exist on server → 404 → blank.
**Fix (3 layers, all required):**
  1. Gateway `GatewayExtensions.cs` regex-classifies files: `[.-]<8+char hash>(-dev)?.(js|mjs|css)` → 1y immutable. Stable-name entries (main.js, styles.css, *.json, *.html, favicon) → no-cache.
  2. Shell emits `public/build-info.json` on prebuild/prestart with `{version, sha, builtAt}` (scripts/stamp-build-info.mjs).
  3. Shell-sdk `BuildVersionService` polls `/build-info.json` every 2 min; fingerprint change → reload banner.
**Guardrail:** Regex classifier is primary defense. Polling = belt-and-braces for long tabs. Triple (cache rule + build stamp + polling) makes stale entries structurally impossible.
**Module(s):** Gateway, Shell UI, every federated module.

### NUGET_BLOAT_VIA_DEV_STAGING_LEAK — dev-convenience module staging leaked into Shell.UI NuGet, 90× bloat
**Pattern:** `scripts/build-all-modules.sh` stages every federated module's remote bundle in `novara-shell/web/public/modules/` so the Shell can serve them at `/modules/...` during local `ng serve`. Angular's production build copies `public/*` verbatim into `dist/`. `release-shell-ui.sh` then copies `dist/novara-shell/browser/*` into `Novara.Shell.UI/wwwroot/` and packs it. Net result: Shell.UI 2026.4.22.1 shipped at 90 MB compressed / 444 MB uncompressed containing duplicates of every module's federation bundle — the same bundles already shipping in each `Novara.Module.X` NuGet. Clean Shell.UI packs at ~1 MB.
**Root cause:** dev-convenience folder AND release-artifact folder share the same path. What's useful for ng-serve is catastrophic for dotnet pack.
**Fix:** In `release-shell-ui.sh`, between `ng build --configuration production` and the copy-to-wwwroot step, delete `dist/novara-shell/browser/modules/`. Each module's federation bundle lives in its own NuGet; Shell.UI must never re-pack it.
**Guardrail:** Central `Novara.Build.targets` policy Update's `Pack=false` on `**/wwwroot/modules/**` as belt-and-braces — even if the script regresses, the pack itself will exclude module subfolders.
**Module(s):** Only Novara.Shell.UI at packaging time. Root: `release-shell-ui.sh` + Angular's `public/` → `dist/` copy + csproj `<Content Include="wwwroot/**/*">` glob compounded (2026-04-22).

### NUGET_SHIPS_DEBUG_ARTIFACTS — Source maps, .ts sources, license manifests in every module NuGet
**Pattern:** Every Novara module csproj has `<Content Include="../../../web/dist/novara-module-X/browser/**/*" Pack="true" />` — a `**/*` glob that includes `.js`, `.js.map`, `.css.map`, `3rdpartylicenses.txt`, `prerendered-routes.json`, `stats.json`. A typical module NuGet shipped 10 MB of `.js.map` for 6 MB of actual `.js` runtime. Module NuGets were 2× their ideal size; aggregated across 40 packages, ~200 MB of debug artifacts shipped per release wave.
**Root cause:** `<Content Include>` globs don't filter by file type unless authors add Exclude. No author did, across 40+ csprojs. No central enforcement existed.
**Fix:** `NovaraSDK/build/Novara.Build.targets` (auto-imported via `Workspace/Directory.Build.targets`) declares a Target that runs `BeforeTargets="_GetPackageFiles"` and flips `Pack="false"` on any `@(Content)` item whose Identity matches source-map / .ts / Angular-exhaust regex. Works against items declared by csproj globs regardless of the csproj's own Include patterns. Result: Roadmap 3.5 MB → 1.4 MB (60% reduction), Shell.UI 90 MB → 1 MB (90× reduction).
**Guardrail:** Binding rule `.claude/rules/packaging-discipline.md`. Every NuGet audited for .map/.ts/licenses.txt file counts before release.
**Key MSBuild learnings:**
  1. `<Content Update>` in Directory.Build.**props** doesn't work — items don't exist yet (imported BEFORE csproj body). Must use Directory.Build.**targets** (imported AFTER csproj body) OR an explicit Target hooked `BeforeTargets="_GetPackageFiles"`.
  2. Global glob patterns like `**/*.js.map` don't match items whose Identity starts with `../` — use regex-on-`%(Identity)` inside a Target instead.
  3. `<Content Update="@(Content)" ...>` with a regex condition is the reliable way to modify metadata on already-declared items, regardless of how they got there.
**Module(s):** All 40+ packable csprojs across modules + connectors + Shell. Structural fix propagates automatically via auto-import; no per-csproj edits required (2026-04-22).

### LOSSY_AUDIT_REFACTOR — Replacing self-contained audit blob with FK pointer
**Pattern:** Refactor changes `sourcePromptJson = { systemPrompt: "<full text>", ... }` to `{ promptVersionId: N, ... }` as "normalization". Breaks audit trail the moment referenced row is deleted/archived, or reader lacks DB access.
**Root cause:** Normalization instinct without checking intent. "Immutable" ≠ "always accessible". Admins hard-delete, retention archives, cross-region consumers lag, court subpoenas may need exact text without DB access.
**Fix:** Preserve BOTH — pointer AND rendered text. Space cost negligible. Correlation key for analytics join; blob stays self-contained.
**Guardrail (process):**
1. Default on refactor: ADD fields, don't REPLACE. Removal requires explicit justification.
2. Diffs reducing content on fields matching `*audit*|*sourceprompt*|*snapshot*|*history*|*provenance*` need "what am I losing" note.
3. For every audit table: "Given one row, can I reconstruct what happened without joining?" If no, under-specified.
**Guardrail (code, future):** Pre-commit hook flags narrowing diffs; requires `// narrowing-audit: <reason>` opt-in.
**Module(s):** High-risk: roadmap BlueprintService sourcePromptJson, agentic agent_ops.session prompt_snapshot_json, promptstudio.prompt_usage, audit.log.

---

## How to Use

**Before writing a new module service:** read this list. Your service should not be vulnerable to any pattern above.

**When you hit an error:** check the list first. Known class = apply documented fix. New = add an entry after fixing it.

**Progressive growth:** 2-3 new entries per debugging session. Over time, new module developers read this once and know every trap.
