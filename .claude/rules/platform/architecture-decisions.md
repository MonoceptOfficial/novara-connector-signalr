# Architecture Decisions — Novara Platform

These are binding decisions that affect how EVERY feature is built. Follow them in all new code.

## 1. Async-First Design (prep for Event-Driven)

Novara will move to event-driven architecture with a message queue. Until the queue is in place, structure code so the transition is minimal.

**Rules:**
- **Never block on long operations in controllers.** If an operation takes >3 seconds (AI calls, report generation, bulk operations), return `202 Accepted` with a tracking ID, process async, notify via SignalR.
- **Separate command from query.** Read endpoints return data. Write endpoints accept work and return immediately. Don't mix reads and writes in one endpoint.
- **Service methods should be self-contained.** Each method should take all its inputs as parameters (not fetch from HTTP context). This makes them callable from a queue worker later without refactoring.
- **Use `CancellationToken` on all async methods.** Pass it through from controller to service to DB. This enables graceful shutdown and timeout handling.

**Pattern for long operations:**
```csharp
// Controller: accept and return tracking ID
[HttpPost("ideas/{ideaId}/ai-analyze")]
public async Task<IActionResult> AiAnalyze(int ideaId)
{
    var trackingId = await _service.QueueAnalysisAsync(ideaId, GetUserId());
    return Accepted(ApiResponse<object>.Ok(new { TrackingId = trackingId }));
}

// Service: do the work (today inline, tomorrow from queue)
public async Task<string> QueueAnalysisAsync(int ideaId, int userId)
{
    // Today: run inline with fire-and-forget notification
    // Tomorrow: publish to queue, worker picks up
    _ = Task.Run(() => RunAnalysisAsync(ideaId, userId));
    return Guid.NewGuid().ToString();
}
```

**When queue arrives:** Replace `Task.Run` with `queue.PublishAsync()`. Controller and service signatures don't change.

## 2. Cache-Ready Service Layer

Every service call that reads config, permissions, or lookup data should go through a cache-friendly pattern.

**Rules:**
- **Never call DB for data that changes less than once per hour** without considering cache. This includes: tenant config, permissions, feature flags, system prompts, labels, workflow definitions, roles.
- **Use the `IMemoryCache` pattern today** (in-process). When Redis arrives, swap the implementation — not every caller.
- **Cache keys must include TenantId.** Pattern: `tenant:{tenantId}:{entity}:{id}` or `tenant:{tenantId}:{entity}:list`.
- **Invalidate on write.** When an entity is updated, evict its cache entry. Don't rely on TTL alone for user-facing config.
- **TTL guidelines:** Permissions = 5 min, tenant config = 10 min, system prompts = 30 min, labels/roles = 15 min.

**Pattern:**
```csharp
public async Task<IEnumerable<Permission>> GetPermissionsAsync(int tenantId, int userId)
{
    var cacheKey = $"tenant:{tenantId}:permissions:{userId}";
    if (_cache.TryGetValue(cacheKey, out IEnumerable<Permission> cached))
        return cached;

    var result = await _db.ExecuteProcedureAsync<Permission>(SpNames.GetUserPermissions, new { TenantId = tenantId, UserId = userId });
    _cache.Set(cacheKey, result, TimeSpan.FromMinutes(5));
    return result;
}
```

## 3. Idempotent Write Operations

Every write operation must be safe to call twice with the same input and produce the same result.

**Rules:**
- **All create endpoints must accept an optional `ClientRequestId` (GUID).** If the same request ID arrives twice, return the original result instead of creating a duplicate.
- **Use UPSERT pattern in SPs** instead of blind INSERT. Check for existence before inserting.
- **Ingestion endpoints (agent data, telemetry) must deduplicate.** Use composite unique keys (TenantId + Timestamp + Source + Hash).
- **Never use auto-increment IDs as business identifiers in APIs.** Use DisplayId or encoded IDs for external references.

**SP pattern:**
```sql
-- Check for duplicate before insert
IF NOT EXISTS (SELECT 1 FROM product.SomeTable WHERE ClientRequestId = @ClientRequestId)
BEGIN
    INSERT INTO product.SomeTable (...) VALUES (...);
END
SELECT * FROM product.SomeTable WHERE ClientRequestId = @ClientRequestId;
```

## 4. Tenant-Scoped Everything

Already in `multi-tenancy.md` but reinforced here: NO database query without TenantId filter. NO service method without tenant context. This is the #1 security requirement.

## 5. Contract-First API Design

**Rules:**
- **Every endpoint must have typed request/response DTOs** in the Contracts project. No anonymous objects, no `dynamic`, no raw dictionaries.
- **Response envelope is always `ApiResponse<T>`.** Consistent shape for frontend.
- **Breaking changes require a new API version.** Adding fields is OK. Removing/renaming fields is breaking.
- **All list endpoints must support pagination.** Use `PaginationParams` (Page, PageSize). Return total count via `COUNT(*) OVER()`.

## 6. Resilience by Default

Already in `resilience.md` but the architectural implication:
- **Every external call (AI, Blob, external webhook) must have a timeout.** Default: 30 seconds for AI, 10 seconds for everything else.
- **Every external call must have a fallback.** AI down → tell user, don't crash. Blob down → queue for retry.
- **Circuit breaker on external services.** 3 consecutive failures → open circuit for 60 seconds → half-open probe → close on success.

## 7. Feature Flags Ready

Until the feature flag system is built, use this convention:
- **Add a `platform.ProductSetting` row** for any feature that might need to be toggled. Key pattern: `feature:{featureName}:enabled`.
- **Check in service layer, not controller.** Controllers stay thin.
- **Default to enabled.** If the setting doesn't exist, the feature is on. This prevents new tenants from having everything disabled.

## 8. Background Work Pattern

Until the job infrastructure is built:
- **Use `IHostedService` for scheduled work** (stale session cleanup, health checks, usage aggregation).
- **Log start/end/error of every background operation.** Background failures are invisible without logging.
- **Never block the main request pipeline** for background work. Fire-and-forget is acceptable today with proper error logging.

## 9. Demo-Ready vs Production-Ready Balance

Novara needs to demo well AND scale. The rule:
- **Every feature must work end-to-end** (controller → service → SP → real DB). No mock data, no stubs in demo paths.
- **Incomplete features should be behind feature flags**, not half-implemented in the main path.
- **AI features should degrade gracefully.** If Claude API key isn't configured, show "AI features require configuration" — don't crash, don't show mock data.
- **Prioritize breadth over depth for demos.** A working simple version of 10 features beats a perfect version of 3.

## 10. Never-Stop Architecture — Business Continuity at Every Layer

**The platform must never block the user.** If any dependency fails, the experience degrades gracefully — never crashes, never loses work, never shows a dead end.

**Rules for every feature:**
- **Before building, answer:** What happens when this dependency (AI, DB, storage, external service) is unavailable? If the answer is "feature stops working" — add a fallback before shipping.
- **LLM auto-failover:** Use `LlmGateway` which tries providers in priority order (from `platform.LlmProvider`). If current provider fails → try next. Circuit breaker: 3 consecutive failures → disable provider for 5 min → half-open probe → re-enable on success.
- **Manual fallback when ALL AI is down:** Every AI-powered action must have a manual alternative. AI Analyze fails → show a structured template the user fills in manually. AI chat fails → let user type their own notes. Never show a dead button.
- **Storage failover:** Blob upload fails → queue to local disk → sync when restored. Never lose the file.
- **DB read failures:** Serve from cache with "stale data" warning. Never show empty screen for data that was loaded before.
- **DB write failures:** Queue locally, retry with backoff. Tell user "Saved locally, will sync." Never lose user work.
- **Real-time degradation:** SignalR down → polling fallback. Never lose notifications.
- **Show degradation state:** Amber banner when running on fallback ("Using GPT-4 instead of Claude", "Working offline, will sync"). User must always know what's degraded.
- **Per-tenant provider priority:** Each tenant can set their preferred LLM order. Novara admin can override globally.
- **Reprioritization:** Users can drag-and-drop features to reorder. Admin can bulk-change status. Business priorities change — the tool must keep up.

## 11. Unified Connector Architecture — Everything Outside Gateway Is a Connector

**Every service Novara communicates with — internal or external — goes through the Connectors framework.** No special-cased HTTP clients, no hardcoded service URLs, no module-specific polling logic.

**Rules:**
- **ViberHub, SignalR Hub, SMTP, Ollama are connectors** — same config UI, same health dashboard, same capabilities manifest as GitHub/Jira/PagerDuty. They use `internal-grpc` transport for performance but the same framework for management.
- **Modules implement `IConnectorHandler`** — the universal SDK interface for receiving events (`HandleEventAsync`), handling action results (`HandleActionResultAsync`), declaring requirements (`GetRequirements`), and declaring outbound actions (`GetOutboundActions`).
- **No module makes direct HTTP calls to external systems.** All outbound goes through `OutboundActionRequest` → Connectors Engine → Connector Adapter. No exceptions.
- **No module stores credentials.** Credentials live in AppGateway vault, accessed only by connector adapters.
- **No module implements polling/scheduling.** The Integration Engine handles all sync scheduling, cursor tracking, backfill, retry, DLQ.
- **Every connector declares a Capabilities Manifest** — inbound events, outbound actions, config schema, module-specific config schemas. This manifest enables: action validation, config UI rendering, requirement checking, health monitoring.
- **Two transport tiers:** `internal-grpc` for co-deployed Novara services (fast, direct). `external-rest` for customer tools (resilient with DLQ/retry/circuit-breaker). Module developer uses `IConnectorHandler` either way — transport is transparent.
- **Module-specific connector config:** Modules contribute config sections to connector instances via `GetModuleConfigSchema()`. Stored in `connector_module_config` table. Rendered as tabs in admin UI.
- **Graceful degradation is mandatory.** When a connector isn't installed, the consuming module shows "Connect {tool} to enable {feature}" — never crashes, never shows empty data without explanation.
- **IConnectorHandler is MANDATORY for connector event consumers.** Any module that declares `SubscribedEvents` starting with `connector.*` MUST register an `IConnectorHandler` implementation in `ConfigureServices`. The Gateway validates this at startup — missing handlers produce a WARNING log. Pattern: see `CodeReviewConnectorHandler` (GitHub PR → Review). Handler declares `ModuleId` + `ConnectorTypes`, receives `ConnectorDataEvent`, returns `ConnectorHandlerResult` with created/updated entity IDs.
- **Connectors are thin adapters, not modules.** A connector implements `ConnectorBase` (manifest, webhook parsing, test connection). Business logic, controllers, DB schemas, and menu items belong in the CONSUMING MODULE, not the connector. A connector should be ~200 LOC. If it has controllers or its own DB schema, it's a module in disguise.

## 12. Federated Intelligence — Data Sovereignty

**Novara NEVER ingests customer business data.** Novara stores metadata, findings, and aggregates. Customer data stays with the customer.

**The 4 Data Categories:**
1. **Novara-Generated Content** — features, issues, designs, KB articles, decisions, workflows, rules. Users create these IN Novara. Novara owns them.
2. **Novara-Instrumented Telemetry** — data collected by Novara SDKs embedded in customer products (Web Vitals, APM traces, custom events). Customer controls what to instrument and what to scrub. Novara receives pre-processed, PII-scrubbed telemetry.
3. **Federated Inspector Findings** — findings produced by Novara tools that run AT the customer site (data catalog scans, security scans, log fingerprints, infrastructure metrics). Tools scan locally, push findings. Raw data never crosses.
4. **Customer Primary Data** — rows, logs, request bodies, source code, files, PII/PHI/PCI. NEVER touches Novara. Stays at customer. Always.

**Rules:**
- Every module feature that consumes external data must declare which category it uses
- No module stores customer database rows, full log streams, source code, or regulated data
- SDKs must support PII scrubbing configuration (customer controls what's sent)
- Inspectors must do edge processing (aggregate, fingerprint, classify, scrub) BEFORE sending
- Compliance (GDPR, HIPAA, PCI) shifts to customer because Novara never holds regulated data
- This is Novara's competitive moat: the only enterprise platform that doesn't become a data liability

## 13. Integration Priority — 4 Modes in Order

When a module needs data from outside Novara, use modes in this priority order:

**Mode 1: CONNECTOR — Read from existing enterprise tools (PRIMARY)**
- Customer already has Datadog, Sentry, PagerDuty, Jira, GitHub, Snyk, etc.
- Novara connector pulls aggregates from existing tool's API
- DO NOT duplicate data that already lives in customer's APM/log/issue tool
- Novara's value: cross-tool correlation, not tool replacement

**Mode 2: SDK — Instrument greenfield products (SECONDARY)**
- For customers without APM tools or for new products
- Novara's own SDKs: @novara/browser-sdk, Novara.Apm.NET, mobile SDKs, analytics SDK
- Lightweight, Novara-native telemetry
- Customer chooses per-product: Mode 1 if Datadog exists, Mode 2 if not

**Mode 3: INSPECTOR — Scan on-prem assets (SUPPLEMENTARY)**
- For assets without APIs: databases, log files, source code, cloud billing exports
- Novara ships tools that run at customer site: Data Catalog Scanner, Security Scanner, Infrastructure Agent, Database Agent, Log Analyzer, Cost Analyzer
- Tools scan locally, push findings, never upload raw data

**Mode 4: UI PLUGIN — Embed Novara views in customer products (UBIQUITY)**
- Novara provides Web Components: `<novara-issue-lookup>`, `<novara-service-status>`, `<novara-feature-flag>`, etc.
- Framework bindings for React, Angular, Vue
- Customer embeds in their support portal, admin panel, internal tools, mobile app
- Two-way: customer product can also call Novara APIs

**Rules:**
- Every module's "Data Source Requirements" section must declare Mode (1, 2, 3, or 4)
- Connector (Mode 1) is ALWAYS the first choice — don't reinvent what the market already solved
- SDKs and Inspectors are Novara's own engineering — specified in novara-sdk-suite and novara-inspector-suite docs
- UI Plugins are a cross-cutting capability — every module can expose one

**Workspace Folder Conventions:**
- **`NovaraConnectors/`** — Mode 1 adapters. Code runs INSIDE Novara Gateway. Outbound from Novara.
- **`NovaraTools/sdks/`** — Mode 2 SDKs. Embedded in customer code. Inbound to Novara.
- **`NovaraTools/inspectors/`** — Mode 3 scanners. Standalone tools at customer site. Inbound to Novara.
- **`NovaraTools/sdks/novara-ui-components/`** — Mode 4 Web Components. Embedded in customer UIs.
- **`NovaraTools/`** is the umbrella for EVERYTHING deployed at the customer edge — developers installing SDKs, operators deploying Inspectors, frontends embedding UI components.
- Each tool is its own mini-project with README, INTEGRATION.md, DATA-CONTRACT.md, SECURITY.md, examples/, and CHANGELOG.md.
- See `D:\NovaraDev\Workspace\NovaraTools\README.md` for the master index and `DATA-FLOW.md` for data movement.

## 14. Deployment Model — Novara Runs INSIDE Customer Ecosystem

Novara is NEVER a traditional SaaS where customer data traverses the internet to Monocept.

**Rules:**
- Novara deploys INSIDE the customer's trust boundary: on-prem, customer's VPC, customer's air-gapped network
- Intelligence runs on customer's hardware (Ollama on customer GPU, pgvector in customer DB)
- All data movement — connectors, SDKs, inspectors, UI plugins — happens within customer's network
- Customer data never leaves customer infrastructure
- Novara itself can optionally send telemetry to Monocept (opt-in, about Novara's health only, never customer data)
- Customer owns the deployment, credentials, data retention, access control
- Air-gapped deployments are first-class: all functions must work without internet access (CVE feeds, LLM models, connector catalogs are importable offline)
- Updates via signed NuGet packages customer can verify and install

This is the #1 competitive advantage over cloud-native SaaS (Datadog, LaunchDarkly, Atlassian Cloud).

## 16. Recursion Safety — Polymorphic Dispatchers Declare Categories

**Every polymorphic registry (step executors, tools, event handlers, workflow executors, connector handlers, cross-module handlers) MUST carry a per-member CATEGORY that the dispatching engine filters on before invocation.**

**Rules:**
- Engines declare which categories they dispatch (hard-coded allowlist in the engine, not a plug-in opt-in)
- A `foreach` over `registry.All` without a kind/category filter in the loop body is a banned pattern (pre-commit check)
- Every engine entry point that transitively dispatches plug-ins carries an `AsyncLocal<int>` recursion-depth guard that fails fast at depth > 3
- Agent session insert-rate is monitored per agent per minute; > 20/min triggers an alert

**Why it matters:**
On 2026-04-18 a recipe engine without category filtering caused a context-building pass to dispatch a lifecycle step (`agent_loop`), which recursively re-entered the engine with an empty goal — 6 orphan sessions per second for 22 minutes. No compile error, no runtime exception, just a silent flood. This rule makes that class of bug structurally impossible.

**See:** `.claude/rules/recursion-safety.md` for the full pattern, detection logic, and example guardrails. `.claude/rules/learned-errors.md` § RUNAWAY_EMPTY_GOAL_SESSIONS for the specific incident.

## 15. Workflows as Platform Service — Universal Orchestration Layer

**Every state transition and every approval in Novara goes through `novara.workflows`.** No module implements its own state machine, approval chain, escalation logic, or approval UI. This parallels Decision #11 (Connectors as universal integration) and Decision #12 (Federated Intelligence).

**Rules:**
- **No custom state machines.** Modules declare workflow definitions; the Workflows engine executes them.
- **No custom approval UIs.** Use `<novara-approval-card>`, `<novara-approval-queue>` Web Components. One approval UX across the platform.
- **`IWorkflowParticipant` is mandatory** for any module with state transitions. Parallel to `IConnectorHandler`.
- **Central Approval Catalog** — every approval type is registered in a master catalog. The Dashboard's "Decisions Queue" aggregates from ALL modules.
- **Role-based authorization** — Admin module owns the `approval_role_mapping` (per-tenant). A role can approve a set of approval types; customers can override per-tenant.
- **Delegation is first-class** — user going on vacation → delegates approvals to another user for a date range.
- **Escalation on timeout** — every approval has an SLA; breach triggers escalation chain.
- **Break-glass override** — emergency bypass requires double approval + full audit trail.
- **Workflow-of-workflows** — changing a workflow definition is itself a workflow (requires approval + simulator test + migration of in-flight instances).
- **Audit trail is append-only** — every approval decision, delegation, escalation is permanently recorded for compliance.
- **Simulator mode** — test workflow changes on mock data before publishing.

**Why this matters:**
- Consistent UX — approvers see the same card whether it's a PR merge, budget overrun, or CVE waiver
- Single "pending decisions" view for executives — no tool-switching
- Compliance ready — one audit trail for all approvals across the enterprise
- Low-code change — customers can modify workflows without waiting for Novara releases
- No code duplication — 46 modules don't each reinvent state machines

**See also:** Decision #11 (Connectors), #12 (Federated Intelligence), #13 (Integration Priority). Workflows + Connectors + Intelligence are the three universal platform services.

## 17. Composable Dashboard Surfaces — Every Overview Is a Widget Composition

**Every module's overview / landing / dashboard / status page in Novara is a composition of widgets contributed by modules — not hand-built HTML.** Detail / edit / workflow surfaces stay domain-specific. This parallels Decision #11 (Connectors as universal integration), #12 (Federated Intelligence), and #15 (Workflows) — it is the fourth universal platform service, applied to UI composition.

**The dividing rule (binding):**
- Page summarises **multiple data sources at a glance** → widget composition (mandatory).
- Page deeply interacts with **one entity** (issue editor, design canvas, bug-report wizard, code viewer, settings form) → domain-specific UX (don't force widgets).

**Rules:**
- **Every module declares its widget catalogue** in its manifest via `IWidgetProvider.Widgets` — same extension-point shape as menu items, event handlers, and connector types. Widgets are registered at module load; Gateway aggregates.
- **Widget is the atomic unit**, not "card". Each widget declares: id, kind, title, default size (12-col grid units), min size, config schema (JSON schema), data contract, required sources, required permissions.
- **Layout is JSON, not code.** Pages are `{ grid, widgets:[{type,x,y,w,h,config}] }` — diffable, exportable, Git-friendly, version-controllable. Same model Grafana uses, battle-tested for a decade. Ship default, org default, team layout, personal layout — resolution chain with reset-to-default.
- **Data flows through resolvers, not direct DB calls.** Widgets declare a `DataContract` (e.g., `signal:telemetry.app.crash.count_1h`); server-side resolvers fetch. Widget code is pure render — never talks to storage. Swap underlying store (hot Postgres → pre-aggregated rollup → cached) without touching widgets.
- **Three render states are mandatory.** Populated (data present) / empty (configured but no data in window) / unavailable (source not configured — shows install CTA). No widget returns 404 or blank. Unavailable-state renders the customer education — "Install `novara-infra-k8s` to see this" — never dead UI.
- **Edit mode is a toggle.** Drag handles, resize corners, add-widget palette, per-widget config gear — invisible in view mode. One "Customize dashboard" button flips. Save As… offers Personal / Team / Org default / Ship default (admin only).
- **Scope of saved layouts:** `ship > org > team > user`, resolution order opposite. Admin can promote a personal layout to team or org default with one click.
- **Six standard widget kinds ship in `@novara/ui-kit`** at launch: KPI, chart, table, heatmap, timeline, markdown. New widget kinds go through ui-kit PR, not per-module reinvention.
- **Never build bespoke grid engines.** Use `angular-gridster2` as the standard for Shell UI. One battle-tested drag/resize framework, not 46 variations.
- **Widget catalogue and layout changes are auditable.** Every contributed widget, every promoted layout, every shipped default goes through `novara.audit` — same append-only trail as workflow definitions (#15) and connector configs (#11).
- **Connector + Widget are siblings.** Both are module-contributed descriptors feeding a shared runtime. Module authors learn one pattern ("declare your extensions in your manifest, the framework composes the surface") applied to I/O (connectors) and UI (widgets). This is the **Novara Extension Point family**: Connectors (#11), Workflow Participants (#15), Widgets (#17), Cross-Module Handlers. One mental model.
- **Descriptors are code-declared, DB-mirrored; instance config + layouts are DB-only.** The `WidgetDescriptor` (the *type* — what widgets exist) lives in the module's code; on module install the Gateway syncs it into `widget_catalog`. The DB copy is for fast querying (add-widget palette, marketplace browse) and versioning, never the source of truth. Instance config (one user's tuning for one widget on one dashboard) and layout JSON are pure DB. Same separation as connector manifests (type is code; instances are data) in Decision #11.
- **Widget sources are tiered**, matching the connector marketplace pattern: Tier-1 **module-declared** (code, shipped signed, 99% of widgets, full render power); Tier-2 **admin-authored** (DB rows, use existing widget kinds like markdown / table-from-query / chart-from-query, no new render code); Tier-3 **third-party/marketplace** (signed bundles, sandboxed render, phase-2 alongside connector marketplace). Customers add tier-2 widgets *without* a module redeploy.
- **Descriptor schema evolution follows `settings-discipline.md` rules**: never remove a field, widen only, deprecate before remove. Module upgrades use the same blue-green mechanism as Decision #22 (Module Lifecycle) — v2 descriptors live alongside v1 until layouts migrate; orphaned instances render as placeholders with a migrate-or-remove CTA (never silently disappear).

**Why it matters:**
Today every module reinvents its own cards. 33 Workspace modules + TelemetryHub + future Hubs × ~3 overview surfaces each = 100+ hand-built fixed layouts. Personas differ — SRE wants one cut, CISO another, product lead a third — one-size-fits-none is the current state. Enterprises ask for customisation in every single deal; we ship a rebuild every time. Composable surfaces turn this from an N² problem into an N one — build the framework once, every new module (and every new customer view, every new persona) is free.

This also unlocks the **third-party widget marketplace** downstream: partners and customers contribute widgets to modules they don't own, same mechanism as connector marketplace (#11). One registry, multiple authors.

**Migration approach (progressive, never big-bang):**
1. Build the framework once (`WidgetDescriptor` SDK + `novara.dashboards` module + `<DashboardShell>` in ui-kit).
2. Classify every existing module's surfaces as *overview* vs *detail*. Two engineers, one afternoon.
3. Migrate **TelemetryHub pages first** — newest, wireframe demo already in flight, lowest-risk validation surface.
4. Workspace overview pages migrate one per sprint (Dashboard, Health, Reports, Incidents, Audit, Releases, ThinkBoard, Roadmap).
5. **Detail/edit surfaces never migrate.** Design Studio, Code Review, Bug Studio wizard, settings forms stay custom. That's by design.
6. Every **new module from this decision forward ships its overview as a widget composition by default** — no more hand-rolled HTML in `module-*.html` for dashboard surfaces.

**See:** `specs/Telemetryhub/56-composable-surfaces.html` for the full contract (`WidgetDescriptor`, `ILayoutResolver`, `IWidgetDataResolver`), the 6 standard widget kinds, the layout JSON schema, scope-resolution algorithm, edit-mode UX spec, and per-surface migration inventory. Sibling to `42-shell-and-modules-architecture.html` — both describe platform-primitive composition patterns.

## 18. Event-Driven Core — Every Cross-Module Signal Is a Versioned Event

**Every significant state change, cross-module notification, and lifecycle action in Novara is a published event on a durable bus.** No direct module-to-module calls for state-change notification — publish an event, let interested consumers subscribe. The event catalogue is versioned; events never break backward compatibility silently.

**Rules:**
- **One bus, one contract.** `IEventBus.PublishAsync` + `IEventSubscriber.HandleAsync`. Backed by PostgreSQL LISTEN/NOTIFY for small deployments, Kafka for medium+, transparent to the module author.
- **Every event is a typed class** in the SDK (namespace `Novara.Events.*`), versioned via `[EventVersion(1)]` attribute. Consumers handle N and N-1 simultaneously.
- **Every event carries: event-id (idempotency key), correlation-id (trace linkage), tenant-id, product-id, actor, timestamp.** These are part of the envelope, not the payload — common across every event.
- **Well-Known Event Catalogue** maintained in `SdkEventCatalog.md`. Adding an event is a PR that updates the catalogue. Naming: `novara.{module}.{entity}.{verb}` (e.g., `novara.issues.issue.created`, `novara.releases.release.promoted`).
- **At-least-once delivery.** Consumers are idempotent on `event-id`. The platform does not promise exactly-once; consumers handle duplicates.
- **Durability level per event**: `ephemeral` (fire-and-forget, small deployments OK to lose), `durable` (bus persists until delivered), `replayable` (bus retains for N days, late-joining consumer can catch up).
- **No synchronous cross-module notification calls.** If Module A needs Module B to act, it publishes an event; B subscribes. Direct HTTP calls are for queries (`ICrossModuleQuery`), not state changes.
- **Schema registry** — event classes + JSON Schema autogenerated into the SDK's published NuGet. Consumers that fall behind a producer get a clear compile-time warning.
- **Dead-letter queue** for unhandled or rejected events — inspected by `novara.health`, alerted on depth > threshold.
- **Event-sourced state is an optional consumer pattern** — modules that want to replay history (audit, incidents, retrospectives) can subscribe to `replayable` events and rebuild state. Not mandatory.

**Why it matters:**
Without a durable event bus, every new cross-module feature requires another direct HTTP dependency. In a 33-module platform, that's N² coupling — catastrophic beyond a few releases. Event-driven inverts the dependency: producers don't know their consumers; consumers subscribe freely. Adding a new consumer (e.g., a new audit sink, a new analytics module, a customer's own event consumer) is a zero-touch change to the producer.

**See:** `specs/platform/novara-events-spec.html`.

## 19. Identity & Permissions as Platform Service — RBAC + ABAC + Delegation + Break-Glass

**Every authenticated request in Novara resolves identity + permissions through one platform service.** No module implements its own role model, permission checks, delegation, or escalation. Modules declare what they need; the platform decides who can do it.

**Rules:**
- **Two complementary models**: RBAC (role → permissions) for coarse structure; ABAC (attribute-based policy) for fine-grained rules (e.g., "user can edit their own issues but not others'"). Together in one resolver.
- **Every module declares its permission catalogue** in its manifest (`IPermissionProvider.Permissions`). Module authors never hard-code permission strings; permissions are descriptors with IDs, descriptions, risk levels.
- **`[RequirePermission("X")]`** on every mutation endpoint — binding from day one. Read endpoints optional but recommended for sensitive data.
- **Delegation is first-class**: "User A delegates approval authority to User B from 2026-05-01 to 2026-05-14." Stored on the Identity module; every permission check walks the delegation chain.
- **Break-glass**: emergency override requires double approval + full audit. Non-revocable log. Reserved for incident response.
- **Time-bound permissions**: grants expire. `user → role` assignments optionally carry `valid_until`. Reduces standing privilege.
- **Permission changes are audit events** (#18): every grant, revoke, delegate, break-glass emits `novara.identity.permission.*` events to the durable bus.
- **Customer tenant overrides** — customer admin can redefine which role maps to which Novara permissions. Novara ships defaults; customers tune.
- **Service accounts are first-class identities** (CI bots, inspectors, connectors). Tenant-scoped API keys with revocation. Same permission model as users.
- **Session model**: JWT for API, Cookie for UI, mTLS for inter-module calls (zero-trust). Never a shared secret; never a long-lived key in config.

**Why it matters:**
Every enterprise rewrites its identity model at least twice during a platform's life — the first time when the shipping-default roles don't match theirs, the second time when they realise their first rewrite painted them into a corner. Building RBAC + ABAC + delegation + break-glass from day one + customer-tunability + auditability means zero rewrites. The 33 modules never need to know any of this exists beyond a single attribute.

**See:** `specs/platform/novara-identity-spec.html`.

## 20. Configuration Hierarchy as Platform Service — Resolution Chain, Not Per-Module Code

**Every setting in Novara resolves through one hierarchy: `default → tenant → product → team → user`.** Modules declare their settings; platform handles storage, resolution, caching, audit. No module re-implements this.

**Rules:**
- **One resolver.** `IModuleSettings.GetAsync<T>(key, scope)`. Walks the chain most-specific to least-specific, returns first hit.
- **Every setting has a descriptor** (`SettingField` — already in the SDK via `settings-discipline.md`). Type-safe, range-validated, audited.
- **Four scopes, resolution order user > team > product > tenant > default.** Team scope optional per module.
- **Changes are audit events** — every write lands in `novara.audit`, immutable. Auditor can prove which value was in effect at any past moment.
- **Caching per-scope** with invalidation on write. Read-heavy; 5-min default TTL.
- **Schema evolution rules** (from `settings-discipline.md` — promoted here): never remove a field, never tighten bounds, never change type silently. Deprecate first, remove in next major.
- **Customer admins tune at product and tenant scope** through the Admin UI, generated from the declared `SettingField` list. No bespoke settings pages per module.
- **Secrets go through AppGateway vault**, referenced by key, never stored inline. Same resolution chain; value masked on read.
- **Bulk import/export** per product as signed JSON — customers can version-control their tuning in their own Git.

**Why it matters:**
Settings proliferate faster than any other surface. Without a single hierarchy, every module invents its own defaults/overrides pattern and customers drown in N inconsistent admin UIs. With one resolver + one descriptor model, customers tune Novara through one coherent experience and modules get enterprise-grade settings governance for free.

**See:** `specs/platform/novara-config-spec.html` + existing `.claude/rules/settings-discipline.md`.

## 21. Outbound Events / Webhooks as Platform Service — One Way to Talk to the World

**When Novara needs to tell the outside world something — Slack, Jira, PagerDuty, ServiceNow, customer webhook, email — it goes through the Outbound Events platform service.** No module implements its own webhook dispatcher.

**Rules:**
- **One outbound service.** `IOutboundEventDispatcher.SendAsync(OutboundEvent e)`. Platform handles: target registration, payload signing, retries with exponential backoff, circuit breakers, dead-letter, audit.
- **Every outbound subscription is a first-class entity** in the Admin UI: target URL/integration, event filter (by event type, by tenant, by severity), transform template (mapping Novara event → target format), secret/HMAC key, retry policy.
- **Built-in target types**: generic HTTPS webhook, Slack, Teams, PagerDuty, Jira, ServiceNow, GitHub, GitLab, email via SMTP, signed payload POST. New target types are modules (same `IConnectorHandler` pattern as inbound connectors).
- **Payload signing**: Ed25519 signature header on every outbound request. Customers verify; proves the event originated from their Novara.
- **At-least-once delivery** with idempotency key per event. Retry schedule: 1s, 5s, 30s, 5m, 30m, 2h, 12h, 24h, DLQ.
- **Observability**: every dispatched outbound event is a row in `outbound_delivery_log` (sender, target, attempts, status, response). Admin UI shows throughput, failure rate, per-target health.
- **Customer-defined outbound subscriptions live under the customer's tenant**; platform-defined (e.g., built-in PagerDuty for SLO breach) are ship defaults tunable per customer.
- **Rate-limiting per target** — respect customer's Slack/PagerDuty quota; back-pressure if needed.
- **Same connector framework as inbound.** Outbound is just another direction. Module authors don't learn two abstractions.

**Why it matters:**
Enterprises don't just want to USE Novara — they want Novara plugged into their existing operational plane. The CIO's demand is always "events flowing to our Slack / PagerDuty / Jira within 30 seconds." Retrofitting each module with its own outbound logic breaks that in month 2; one platform service solves it in week 1 and stays solved.

**See:** `specs/platform/novara-webhooks-spec.html`.

## 22. Module Lifecycle & Versioning — Install, Upgrade, Hot-Swap, Rollback, Safe-Mode

**Every Novara module has a declared lifecycle managed by the platform, not bespoke per-module deploy scripts.** Customers install, upgrade, rollback, and hot-swap modules through one UI backed by one process.

**Rules:**
- **Every module carries a `ModuleManifest`** — id, semver version, dependencies (other modules, SDK version), migrations list, rollback metadata, signing.
- **Five lifecycle stages**: `install → enable → run → disable → uninstall`. Each has hooks (`OnInstallAsync`, `OnEnableAsync`, etc.) the module author can implement.
- **Blue-green module upgrades** — new version installed alongside old; customer gates over via Admin UI; old kept for rollback window. No downtime.
- **Module migrations are idempotent and reversible where possible.** Up/down scripts versioned, tracked in `productmeta.migration_log`. Never auto-applied without customer confirmation on major upgrades.
- **Safe-mode boot** — if a module crashes the Gateway, next boot loads it in quarantine; Admin UI surfaces the error and allows rollback without full redeploy.
- **Dependency resolution** — module declares `[DependsOn("novara.workflows", ">=2.0")]`. Gateway refuses to start if unsatisfied; Marketplace surfaces incompatible modules at install time.
- **Signed bundles** — every module package signed by Monocept release key + customer's installation is audit-logged. Air-gap customers import signed `.nupkg` bundles through the same flow as online installs.
- **Module version compatibility matrix** — every release declares compatible SDK versions + compatible sibling-module versions. Published in the manifest + marketplace.
- **Deprecation window**: a module declared deprecated continues to load for N=2 minor versions, warning on every boot. Hard-removed in the next major.
- **Customer-written modules** follow the same contract — no separate "first-party vs customer" lifecycle. One model.

**Why it matters:**
Ten-year platforms install and uninstall modules dozens of times. Without a lifecycle contract, each module's install story is bespoke, each upgrade is terrifying, and rollback is "restore last night's backup." With a formal lifecycle + blue-green + safe-mode, a customer upgrades 46 modules on a Tuesday morning with confidence.

**See:** `specs/platform/novara-module-lifecycle-spec.html` + existing `specs/platform/novara-migration-framework-spec.html`.

## 23. Observability Contract — Every Module Emits Standard Health, Metrics, Traces

**Every module in Novara emits its own health signal, metrics, and traces through one standard contract.** The platform aggregates; `novara.health` renders. No module goes dark; no bespoke monitoring per module.

**Rules:**
- **Every module implements `IHealthCheck`** — returns `healthy | degraded | down` + structured reason + last-successful-operation timestamp. Queried by `novara.health` every 30s.
- **Every module emits standard metrics**: requests-per-second, error-rate, P50/P95/P99 latency, queue depth (if applicable), db-query-count. Via OpenTelemetry meter provider, same names across all modules.
- **Every module produces traces** — spans on every incoming request + outgoing DB call + outgoing connector call. Sampled at configured rate. OTLP export to local collector.
- **Correlation IDs propagate** through every call. Inherited from incoming request; passed through outgoing events (via #18) and cross-module calls.
- **Structured logs only** — JSON log lines with `{ts, level, correlation_id, module, tenant, product, event, attrs}`. No free-form `_logger.LogInformation("{data}")` without schema.
- **Readiness vs liveness** distinct. Readiness = "ready to accept traffic"; liveness = "not deadlocked". Kubernetes-compatible.
- **SLOs per module** — module declares its own SLOs (P95 latency target, error-rate target). Automatically surfaced in Workspace Health dashboard.
- **Sampling controls** — platform admin can tune trace sampling per module, per tenant, per environment. Default 10%; 100% for errors always.
- **No PII in logs, metrics, traces.** Same scrubber as TelemetryHub (#12). Violations fail pre-commit.
- **Meta-telemetry loop** — the observability infrastructure itself emits health signals. Prometheus exporter for metrics; OTel collector for traces; dashboards in Grafana (or the same `<DashboardShell>` from #17).

**Why it matters:**
When a module silently breaks in production at 3am, the on-call's first question is "is this module even supposed to be healthy?" Without a contract, the answer is module-specific archaeology. With one contract, every module has the same health surface, the same metric names, the same trace structure — and the 3am triage is fast.

**See:** `specs/platform/novara-observability-spec.html`.

## 24. Data Lifecycle & Retention Contract — Every Module Declares How Its Data Ages

**Every table, every blob, every log in Novara has a declared retention, export format, and RTBF (right-to-be-forgotten) behaviour.** No module silently keeps data forever; none invents its own retention.

**Rules:**
- **Every table has a `DataDescriptor`** (declared in migration or via attribute): retention duration by tier (hot/warm/cold/archive), export-includable, RTBF-user-scoped, tenant-scoped.
- **Four storage tiers, platform-wide semantics**: hot (queryable, full fidelity) → warm (rollups, queryable) → cold (compressed archive, restore-only) → forever (audit, append-only, never aged).
- **Tier transitions are platform-driven** — module declares "hot = 7d, warm = 90d, cold = 365d"; platform runs the jobs.
- **Export per tenant** — `GET /api/tenants/{id}/export` returns signed bundle of everything scoped to that tenant, across all modules. GDPR Article 20.
- **RTBF per user** — `DELETE /api/tenants/{id}/users/{userId}/data` cascades across every module's tables that declared the user-scope. Platform orchestrates; modules respond.
- **Retention is tunable per tenant** — customer may extend (never shorten below Novara's compliance minimum). Ship defaults meet regulatory floor.
- **Cold tier format is standardised** — Parquet on object store with consistent partitioning (`tenant/module/date.parquet`). One reader can restore anything.
- **Cross-module joins over cold tier** use the same partition scheme — analytics queries work against archive without per-module special-casing.
- **Audit of retention actions**: every tier transition, every RTBF, every export emits events to #18 and rows to `novara.audit`.
- **Backup/restore orthogonal to retention** — retention is about aging live data; backup is about disaster recovery. Both declared per module.

**Why it matters:**
Three years in, every enterprise platform drowns in data. Without per-module retention declared up-front, cleanup becomes a cross-team six-month project. Compliance auditors want one place to prove "here's every piece of user data we hold, here's how long we hold it, here's how we forget." One contract, zero surprise.

**See:** `specs/platform/novara-data-lifecycle-spec.html`.

## 25. API Contract Evolution — Versioning, Deprecation, Sunset

**Every externally-consumed API in Novara follows one contract-evolution protocol**: version explicit, deprecation window declared, sunset enforced. No module silently breaks a field name.

**Rules:**
- **URL versioning** — `/api/v{major}/...`. N and N-1 supported simultaneously for minimum 12 months after N+1 ships.
- **Field additions are always safe.** Never remove or rename a field on an existing version; introduce in a new version.
- **Breaking changes require**: new version, deprecation notice on old version (HTTP header `X-Deprecated: true, sunset: 2027-01-01`), migration guide published in KB, customer notification via outbound event (#21).
- **Response headers surface the contract state** — every response carries `X-Novara-Api-Version: 1.4.2` and optional `X-Deprecated`, `X-Sunset`.
- **OpenAPI spec auto-generated** on every build. CI diffs against last release's spec; breaking changes fail the build unless accompanied by a version bump + migration guide.
- **Consumer-driven contract tests** in the SDK — the published SDK includes tests the customer runs against a new Novara deployment before upgrading. Breaking changes surface pre-deploy.
- **Sunset is a scheduled operation**, not "whenever we get around to it." Calendar entry, customer notification, grace period, then hard-removed.
- **Internal module-to-module APIs** follow a simpler contract (`ICrossModuleQuery`, `IEventBus` events). Same principles: never break silently, versioned, deprecation supported.
- **SDK evolution mirrors API evolution** — the `.NET` SDK version tracks the API major. Customer upgrading from SDK 2.x to 3.x is a major event with a migration guide.
- **Anti-corruption layer** — connectors normalise external (customer-side) API shapes into Novara's internal shape. When the external API changes, only the connector adapts; internal consumers unaffected.

**Why it matters:**
The fastest way to lose customer trust is to silently break their integration. The fastest way to get stuck is to never break anything. The middle path is explicit: version, deprecate, migrate, sunset. Platforms that succeed for 10 years all do this; platforms that fail never do.

**See:** `specs/platform/novara-api-evolution-spec.html`.

## 26. Internationalisation & Localisation Contract — Every String, Date, Number, Currency

**Every user-visible string, date, number, currency, timezone reference in Novara goes through the i18n platform service.** No module hard-codes language or locale assumptions.

**Rules:**
- **Every user-facing string is a resource key**, not a literal. Modules declare their strings in `i18n/en-US.json` (plus translations). No `<h1>Release Health</h1>` — always `<h1>{{ 'module.releases.title' | t }}</h1>`.
- **Supported locales declared platform-wide** — Novara ships en-US baseline; customer installs add locales. Translations live in module packages and override-able per tenant.
- **Dates default to ISO-8601** in storage, localised at render. User timezone preference resolves through the config hierarchy (#20).
- **Numbers localised with `Intl.NumberFormat`** — thousand separators, decimal points differ per locale.
- **Currencies carry currency code** always (never "1000" without knowing if it's USD or EUR). ISO 4217 everywhere.
- **Plural rules via CLDR** — not module-specific if-else. `{count, plural, one {# issue} other {# issues}}`.
- **Text direction (LTR/RTL)** honoured in every layout — Arabic, Hebrew deployments work out of the box.
- **Sortable where human-readable** — sort by normalised form (collation), not raw bytes. German umlauts, Chinese pinyin, accents — all correct.
- **Translation workflow** — each string has a translator note; missing translations fall back to en-US with a visible `[untranslated]` tag in dev mode, silent fallback in prod.
- **Module authors never hard-code a language**. Code review blocks literal strings in user-facing surfaces. Enforced by lint rule.

**Why it matters:**
Every enterprise platform that doesn't bake in i18n from day one rewrites it in year 3 at 10× the cost. Novara's first non-English customer is inevitable; the only question is whether we greet them with "it works" or "give us six months". The strings-are-keys discipline is free to maintain once the lint rule fires on PR, and saves the year-3 rewrite.

**See:** `specs/platform/novara-i18n-spec.html`.

## 27. Multi-Region / Data Residency Contract — Where Data Lives Is Declared, Not Accidental

**Every piece of data in Novara has a declared residency: which customer region it lives in, never leaves.** Data residency is enforced at the platform level, not negotiated per deployment.

**Rules:**
- **Tenant declares its primary region** at creation — `us-east-1`, `eu-west-1`, `ap-south-1`, or an on-prem zone. Immutable without explicit migration.
- **Every data write is region-tagged** in the envelope. Platform enforces: write to a tenant's data outside its region is rejected with 451 Legal Reasons.
- **Cross-region reads only via explicit federation** — the customer admin opts in to a cross-region view (e.g., a US parent viewing EU subsidiary rollups). Federation happens at the aggregate level; raw rows never cross.
- **Deployment topology** — Novara can run multi-region with one shared control plane + region-local data planes. Gateway routes by tenant → region.
- **Data-sovereignty laws baked into defaults**: GDPR (EU data in EU), China's PIPL, India's DPDP, UAE data localisation — each has a shipped policy pack the customer enables.
- **Backups are region-local** by default. Cross-region replication requires explicit admin opt-in + audit event.
- **Air-gap is the strongest residency** — no data leaves the customer's network, ever. Inspectors/SDKs push inside; Workspace consumes inside; outbound only via signed quarterly export if the customer chooses.
- **Regional health is separate** — a region going down doesn't degrade other regions. Bulkheads at the region boundary.
- **Customer can audit residency** — `GET /api/tenants/{id}/residency-report` lists every module, every table, the region each row lives in. GDPR auditor's dream.
- **Region move is a first-class operation** — not a manual migration. Tenant admin triggers, platform orchestrates copy + switchover + verification + old-region purge.

**Why it matters:**
Data residency is bet-the-deal in regulated geographies. An enterprise customer in Germany asking "where does my data live?" cannot be answered with "probably in us-east-1, we think." Declaring residency up-front and enforcing it at the platform layer means one lawyer reads one spec and signs off on all 46 modules at once.

**See:** `specs/platform/novara-data-residency-spec.html`.

## 28. Per-Product Isolation — Every Product Is Its Own Blast Radius

**Within a Novara deployment, every product gets its own isolated environment: its own database, its own connectors, its own resource quotas, its own retention policies, its own audit trail.** A noisy product cannot drown a quiet one; a compromised product cannot reach siblings; a product can be deleted or exported cleanly without touching the rest. This is distinct from tenant-scoped data (#4) and deployment-model (#14): those are about *where data lives*; this is about *how blast radius is contained within a deployment*.

**Rules:**
- **Database per product.** Each product gets its own PostgreSQL database (`NovaraWorkspaceProductDB_{productKey}`, `NovaraTelemetryProductDB_{productKey}`). The `ProductDatabaseRouter` resolves the connection per request. A product's schema, extensions, indexes, retention, even PG version are independent of siblings.
- **Bulkhead at the connection pool.** Each product gets its own `pgBouncer` pool with its own max-connections quota. One product cannot exhaust the server's connection budget.
- **Resource quotas per product** — events/sec ingest, storage GB, query CPU-seconds/min, worker concurrency. Breaches trigger 429s *on that product only*, never spill to others.
- **Connector instances are product-scoped.** Datadog / Sentry / Prometheus connector configs live at the product level. Product A's Datadog account is invisible to Product B. Credentials never shared.
- **Signal families enabled per product.** Product A may have Application family only; Product B has Application + Infrastructure; Product C adds Cost. Enabling a family on one product doesn't enable it elsewhere.
- **Retention policies per product.** Product A (regulated) keeps 7 years; Product B (internal tool) keeps 30 days. Decision #24 applies per product, not per deployment.
- **Audit trail is product-scoped.** `audit.log` table lives in each product's DB. Cross-product audit views exist for platform admins, explicit opt-in only.
- **Quotas and rate limits are enforced at the ingest gateway.** Every event carries a `product_id`; gateway routes to the product's bus partitions, checks the product's quotas. Work for Product A cannot be delayed by Product B's queue depth.
- **Deletion is atomic and clean.** `DELETE /api/products/{id}` drops the product DB, archives its object-store data per retention, revokes its connector credentials, unwinds its entries from shared catalogues (widget_catalog, connector_catalog). One transaction, one audit entry, no orphans.
- **Export is independent.** A customer offboarding Product A gets a complete export bundle (PostgreSQL dump + object-store tarball + signed manifest + audit trail) that a new deployment can re-hydrate. Products B and C are untouched.
- **Cross-product federation is explicit opt-in**, never implicit. An executive wanting "all products dashboard" goes through the Workspace cross-product view which queries each product DB read-only through the router; products never query each other directly.
- **Compute is optionally product-scoped at larger tiers.** At XL tier (per spec 57 §13.4), noisy products can get dedicated processing workers + dedicated Kafka consumer groups to fully isolate CPU and memory. Small/Medium tiers share compute but isolate data.

**Why it matters:**
Tenants are *customers*; products are *what a customer ships*. A customer might run 5 products — mobile app, web app, admin portal, partner portal, internal dashboard — and the one with a misbehaving SDK generating 100× noise cannot be allowed to degrade the others. Without per-product isolation, Product A's release-day spike throttles Product B's on-call dashboard. With per-product isolation, each product is effectively its own mini-Novara — the customer buys one platform and gets N independent products inside it.

This also makes the per-product economics clean: customer ops can attribute CPU, storage, ingest bandwidth, compute cost to each product (Decision #24 helps with this at the data layer; this decision makes it architecturally supportable). Showback/chargeback to internal product teams becomes trivial.

For disaster recovery, per-product isolation means backups are product-scoped, restore is product-scoped, corruption in one product's DB doesn't require restoring the whole deployment.

**Relationship to other decisions:**
- **#4 Tenant-Scoped Everything** — still holds within each product. Every row in every product DB has a TenantId (where relevant). Tenant isolation is row-level within a product DB; product isolation is database-level within a deployment.
- **#14 Deployment Model** — one deployment = one customer. Inside that deployment, products are the second level of isolation.
- **#27 Multi-Region / Data Residency** — a product's data lives in the product's declared region. Two products in the same customer can live in different regions if the customer operates globally.
- **#24 Data Lifecycle & Retention** — retention policy is per-product. A customer may elect different retention for different products.
- **Spec 57 (Scaling)** — at Medium+ tier, product-scoped resources become first-class. At XL, products can have dedicated fleets.

**See:** `specs/platform/novara-per-product-isolation-spec.html` (to write) + existing CLAUDE.md "Per-Product DB Architecture" section (this decision formalises what's already built).
