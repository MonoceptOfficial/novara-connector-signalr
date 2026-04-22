# Architecture Decisions — Novara Platform

Binding decisions that affect how EVERY feature is built. Follow them in all new code.

**Deployment model context:** Novara ships as a product suite to enterprises. Each enterprise gets its own deployment (one instance per enterprise). Within a deployment, each product has its own database. There is no multi-tenant row-scoping — the deployment IS the tenant boundary. Within an enterprise, BU/Org isolation applies for users and access. See #4, #14, #28.

## 1. Async-First Design (prep for Event-Driven)

Novara will move to event-driven with a message queue. Structure code so the transition is minimal.

**Rules:**
- **Never block on long operations in controllers.** If an operation takes >3 seconds, return `202 Accepted` with a tracking ID, process async, notify via SignalR.
- **Separate command from query.** Read endpoints return data. Write endpoints accept work and return immediately.
- **Service methods self-contained.** Each method takes all inputs as parameters (not from HTTP context). Callable from a queue worker later without refactoring.
- **Use `CancellationToken` on all async methods.** Pass through controller → service → DB.

**Pattern:**
```csharp
public async Task<IActionResult> AiAnalyze(int ideaId) {
    var trackingId = await _service.QueueAnalysisAsync(ideaId, GetUserId());
    return Accepted(ApiResponse<object>.Ok(new { TrackingId = trackingId }));
}
// Service: _ = Task.Run(() => RunAnalysisAsync(...)); — today inline, tomorrow queue.PublishAsync()
```

## 2. Cache-Ready Service Layer

Every call that reads config, permissions, or lookup data goes through a cache-friendly pattern.

**Rules:**
- **Never call DB for data that changes <1/hr** without cache. Includes: org config, permissions, feature flags, system prompts, labels, workflow definitions, roles.
- **Use `IMemoryCache` today** (in-process). When Redis arrives, swap implementation only.
- **Cache keys scope to product (and org/BU or user where relevant).** Pattern: `product:{pid}:{entity}:{id}` or `product:{pid}:user:{uid}:permissions`.
- **Invalidate on write.** Don't rely on TTL alone.
- **TTL:** Permissions 5m, org config 10m, system prompts 30m, labels/roles 15m.

## 3. Idempotent Write Operations

Every write must be safe to call twice with same input → same result.

**Rules:**
- **Create endpoints accept optional `ClientRequestId` (GUID).** Duplicate request ID returns original result, not a new row.
- **UPSERT pattern in SPs** — check existence before insert.
- **Ingestion endpoints deduplicate** via composite unique key (Timestamp + Source + Hash + ProductId).
- **Never expose auto-increment IDs as business identifiers** in APIs. Use DisplayId or encoded IDs externally.

## 4. BU/Org Isolation Within a Deployment

**Multi-tenant row-scoping is NOT the Novara model.** Each enterprise gets its own deployment (see #14); within that deployment, each product has its own database (see #28). Isolation between enterprises happens at the deployment boundary, not via TenantId filters in queries.

**What DOES apply inside a deployment:**
- **BU/Org isolation** — an enterprise may have multiple business units. `OrgId` exists on product tables and MUST be enforced in every read path where a user's access is BU-scoped. Today this is an enforcement gap (URL manipulation exposes cross-BU data — see BU isolation gap in MEMORY); fix on sight.
- **ProductId isolation** — each product has its own DB via `ProductDatabaseRouter`; no cross-product queries at the DB layer. Cross-product reads go through `ICrossModuleQuery` / mediator (read-only).
- **User-owned row visibility** — `CreatedByUserId` + role/permission checks decide whether User A sees User B's records.

**Banned:** adding a new `TenantId` column to any product-DB table. Adding `WHERE TenantId = @TenantId` to any product-DB query. Treating the deployment as if it might serve multiple enterprises — it doesn't.

**Legacy exception:** `novara.rules` and `novara.appgateway` modules use platform DB and retain `TenantId`. Do not copy their pattern to product-DB modules.

See `multi-tenancy.md` for the full model (historical file — retained for Rules/AppGateway context).

## 5. Contract-First API Design

**Rules:**
- **Typed request/response DTOs** in Contracts project. No anonymous objects, `dynamic`, or raw dictionaries.
- **Response envelope always `ApiResponse<T>`.**
- **Breaking changes require a new API version.** Adding fields is OK; removing/renaming is breaking.
- **All list endpoints paginated** via `PaginationParams`. Return total via `COUNT(*) OVER()`.

## 6. Resilience by Default

See `resilience.md`. Architectural implications:
- **Every external call has a timeout.** AI: 30s, everything else: 10s.
- **Every external call has a fallback.** AI down → tell user. Blob down → queue for retry.
- **Circuit breaker on external services.** 3 failures → open 60s → half-open probe → close on success.

## 7. Feature Flags Ready

Until feature flag system is built:
- **Add a `platform.ProductSetting` row** for toggleable features. Key: `feature:{name}:enabled`.
- **Check in service layer, not controller.**
- **Default to enabled.** Missing setting = feature is on. Prevents new deployments from having everything off.

## 8. Background Work Pattern

Until job infrastructure is built:
- **`IHostedService` for scheduled work** (cleanup, health checks, aggregation).
- **Log start/end/error of every background operation.**
- **Never block the request pipeline** for background work. Fire-and-forget acceptable with error logging.

## 9. Demo-Ready vs Production-Ready Balance

- **Every feature works end-to-end** (controller → service → SP → real DB). No mock data.
- **Incomplete features hide behind feature flags**, not half-implemented in the main path.
- **AI features degrade gracefully.** No API key → "AI features require configuration". Never crash, never show mock.
- **Breadth over depth for demos.** 10 simple working features > 3 perfect ones.

## 10. Never-Stop Architecture — Business Continuity

**The platform never blocks the user.** Every dependency failure degrades gracefully — never crashes, never loses work, never dead-ends.

**Rules:**
- **Before building:** what happens if this dependency is unavailable? If "feature stops working" — add a fallback before shipping.
- **LLM auto-failover** via `LlmGateway` (priority list from `platform.LlmProvider`). Circuit breaker: 3 fails → disable 5m → half-open probe.
- **Manual fallback when ALL AI is down.** AI Analyze fails → structured template user fills in manually. Never a dead button.
- **Storage failover.** Blob upload fails → queue to local disk → sync when restored.
- **DB read failures.** Serve from cache with "stale data" banner.
- **DB write failures.** Queue locally, retry with backoff. "Saved locally, will sync."
- **Real-time.** SignalR down → polling fallback.
- **Show degradation state** via amber banner. User always knows what's degraded.
- **Per-deployment LLM provider priority.** Enterprise admin configures; Monocept ships defaults.
- **Reprioritization.** Drag-and-drop to reorder. Bulk status changes.

## 11. Unified Connector Architecture — Everything Outside Gateway Is a Connector

**Every service Novara communicates with — internal or external — goes through the Connectors framework.** No special-cased HTTP clients, no hardcoded service URLs, no module-specific polling.

**Rules:**
- **ViberHub, SignalR Hub, SMTP, Ollama are connectors** — same config UI, same health dashboard as GitHub/Jira. `internal-grpc` transport for perf, same framework for management.
- **Modules implement `IConnectorHandler`** — receives events, handles action results, declares requirements + outbound actions.
- **No direct HTTP from modules.** All outbound via `OutboundActionRequest` → Connectors Engine → Adapter.
- **No credentials in modules.** Live in AppGateway vault, accessed only by connector adapters.
- **No polling/scheduling in modules.** Integration Engine handles sync, cursor tracking, backfill, retry, DLQ.
- **Every connector declares a Capabilities Manifest** (inbound events, outbound actions, config schema).
- **Two transport tiers:** `internal-grpc` (co-deployed) vs `external-rest` (customer tools, resilient DLQ/retry/CB). Transparent to module author.
- **Module-specific connector config** contributed via `GetModuleConfigSchema()`. Stored in `connector_module_config`. Rendered as tabs in admin UI.
- **Graceful degradation mandatory.** Connector not installed → "Connect {tool} to enable {feature}". Never empty data without explanation.
- **`IConnectorHandler` MANDATORY for `connector.*` event subscribers.** Gateway validates at startup. Pattern: `CodeReviewConnectorHandler` (GitHub PR → Review).
- **Connectors are thin adapters, not modules** (~200 LOC). Business logic, controllers, DB schemas belong in consuming module.

## 12. Federated Intelligence — Data Sovereignty

**Novara NEVER ingests customer business data.** Metadata, findings, aggregates only. Customer data stays with the customer.

**The 4 Data Categories:**
1. **Novara-Generated Content** — features, issues, designs, KB articles. Users create IN Novara.
2. **Novara-Instrumented Telemetry** — SDK-collected (Web Vitals, APM, events). Customer controls scrubbing. PII-scrubbed before ingest.
3. **Federated Inspector Findings** — produced at customer site (catalog/security/infra scans). Raw data never crosses.
4. **Customer Primary Data** — rows, logs, request bodies, source code, PII/PHI/PCI. NEVER touches Novara.

**Rules:**
- Every module feature consuming external data declares its category
- No module stores customer DB rows, full log streams, source code, or regulated data
- SDKs support PII scrubbing config (customer-controlled)
- Inspectors do edge processing (aggregate, fingerprint, scrub) before sending
- Compliance (GDPR/HIPAA/PCI) shifts to customer — Novara never holds regulated data
- Novara's competitive moat: the only enterprise platform that doesn't become a data liability

## 13. Integration Priority — 4 Modes in Order

When a module needs outside data, try modes in priority order:

**Mode 1: CONNECTOR** (PRIMARY) — Read from existing enterprise tools (Datadog, Sentry, Jira, GitHub). Don't duplicate data that already lives in customer's APM. Novara's value: cross-tool correlation.

**Mode 2: SDK** (SECONDARY) — Instrument greenfield products. Novara SDKs: `@novara/browser-sdk`, `Novara.Apm.NET`, mobile, analytics. For customers without APM tools.

**Mode 3: INSPECTOR** (SUPPLEMENTARY) — Scan on-prem assets without APIs (databases, logs, source, cloud billing). Scans locally, pushes findings, never uploads raw data.

**Mode 4: UI PLUGIN** (UBIQUITY) — Web Components (`<novara-issue-lookup>`, etc.) embedded in customer products. Two-way: customer product can call Novara APIs back.

**Rules:**
- Every module's "Data Source Requirements" section declares Mode (1/2/3/4)
- Connector is ALWAYS first choice — don't reinvent what the market solved
- UI Plugins are cross-cutting — every module can expose one

**Workspace folders:**
- `NovaraConnectors/` — Mode 1 (inside Gateway, outbound)
- `NovaraTools/sdks/` — Mode 2 (in customer code, inbound)
- `NovaraTools/inspectors/` — Mode 3 (at customer site, inbound)
- `NovaraTools/sdks/novara-ui-components/` — Mode 4

## 14. Deployment Model — One Deployment Per Enterprise

**Novara is NEVER a shared SaaS where multiple customers share a database.** Each enterprise gets its own deployment inside their trust boundary.

**Rules:**
- Deploys INSIDE customer trust boundary: on-prem, VPC, air-gapped
- One instance per enterprise — no row-level multi-tenancy, no shared DB
- Intelligence runs on customer hardware (Ollama on customer GPU, pgvector in customer DB)
- All data movement happens within customer network — never leaves
- Novara itself can opt-in telemetry to Monocept (Novara health only, never customer data)
- Air-gap is first-class: all functions work without internet (CVE feeds, LLM models, connector catalogs importable offline)
- Updates via signed NuGet packages customer verifies and installs

This is the #1 competitive advantage over cloud-native SaaS (Datadog, LaunchDarkly, Atlassian Cloud).

## 15. Workflows as Platform Service — Universal Orchestration Layer

**Every state transition and every approval goes through `novara.workflows`.** No module implements its own state machine, approval chain, escalation, or approval UI. Parallel to #11 (Connectors) and #12 (Federated Intelligence).

**Rules:**
- **No custom state machines.** Modules declare workflow definitions; engine executes.
- **No custom approval UIs.** Use `<novara-approval-card>`, `<novara-approval-queue>`.
- **`IWorkflowParticipant` mandatory** for any module with state transitions. Parallel to `IConnectorHandler`.
- **Central Approval Catalog** — every approval type registered. Dashboard "Decisions Queue" aggregates from ALL modules.
- **Role-based auth.** Admin owns `approval_role_mapping` (deployment-configurable, optionally org/BU-scoped).
- **Delegation first-class** — vacation → delegate to another user for a date range.
- **Escalation on timeout** — every approval has SLA; breach triggers escalation chain.
- **Break-glass override** — emergency bypass requires double approval + audit.
- **Workflow-of-workflows** — changing a workflow def is itself a workflow.
- **Audit trail append-only.**
- **Simulator mode** — test workflow changes on mock data before publish.

**Why:** Consistent UX across all approval types. One "pending decisions" view for executives. One audit trail for compliance. Low-code workflow changes without Novara release.

## 16. Recursion Safety — Polymorphic Dispatchers Declare Categories

**Every polymorphic registry (step executors, tools, event handlers, workflow executors, connector handlers) MUST carry a per-member CATEGORY that the dispatching engine filters on before invocation.**

**Rules:**
- Engines declare which categories they dispatch (hard-coded allowlist in engine, not plug-in opt-in)
- `foreach` over `registry.All` without a category filter in the loop body is banned (pre-commit check)
- Every engine entry point that transitively dispatches plug-ins carries `AsyncLocal<int>` recursion-depth guard, fails fast at depth > 3
- Agent session insert-rate monitored per agent per minute; > 20/min triggers alert

**Why:** On 2026-04-18 a recipe engine without category filtering dispatched a lifecycle step during context-building, which recursively re-entered the engine — 6 orphan sessions/sec for 22 min. See `learned-errors.md § RUNAWAY_EMPTY_GOAL_SESSIONS`. Full pattern in `.claude/rules/recursion-safety.md`.

## 17. Composable Dashboard Surfaces — Every Overview Is a Widget Composition

**Every module's overview/landing/dashboard/status page is a composition of widgets contributed by modules — not hand-built HTML.** Detail/edit/workflow surfaces stay domain-specific. Fourth universal platform service (alongside #11, #12, #15).

**Dividing rule (binding):**
- Page summarises **multiple data sources at a glance** → widget composition (mandatory)
- Page deeply interacts with **one entity** (issue editor, design canvas, settings form) → domain-specific UX

**Rules:**
- **Every module declares its widget catalogue** via `IWidgetProvider.Widgets` in its manifest. Registered at module load; Gateway aggregates.
- **Widget is the atomic unit.** Declares: id, kind, title, default size (12-col grid), min size, config schema, data contract, required sources, permissions.
- **Layout is JSON, not code.** `{ grid, widgets:[{type,x,y,w,h,config}] }` — diffable, exportable, Git-friendly. Grafana model.
- **Data flows through resolvers.** Widgets declare `DataContract` (e.g., `signal:telemetry.app.crash.count_1h`); server-side resolvers fetch. Widget code is pure render.
- **Three render states mandatory:** populated / empty (configured, no data) / unavailable (not configured — shows install CTA). No 404s, no blank.
- **Edit mode is a toggle.** Drag handles, resize, add-widget palette, per-widget config gear — invisible in view mode.
- **Layout scope:** `ship > deployment > org/BU > team > user`, resolution opposite. Admin promotes personal → team/org default one click.
- **Six standard widget kinds** in `@novara/ui-kit`: KPI, chart, table, heatmap, timeline, markdown. New kinds via ui-kit PR.
- **Use `angular-gridster2`** — one battle-tested drag/resize, not 46 variations.
- **Auditable** — widget catalogue + layout changes go through `novara.audit`.
- **Connector + Widget are siblings.** Module-contributed descriptors feeding a shared runtime. One mental model across the Extension Point family (Connectors #11, Workflows #15, Widgets #17, Cross-Module Handlers).
- **Descriptors: code-declared, DB-mirrored. Instance config + layouts: DB-only.** Type lives in code; Gateway syncs to `widget_catalog` on install.
- **Three tiers:** Tier-1 module-declared (code, signed, full render). Tier-2 admin-authored (DB rows, reuse existing kinds, no new render code). Tier-3 third-party marketplace (signed, sandboxed, phase-2).
- **Schema evolution follows `settings-discipline.md`** — never remove, widen only, deprecate before remove. Blue-green per #22.

**Why:** 33 Workspace modules × ~3 overview surfaces = 100+ hand-built layouts. Personas differ (SRE, CISO, PM) — enterprises ask for customisation every deal. Composable surfaces turn an N² problem into an N one.

## 18. Event-Driven Core — Every Cross-Module Signal Is a Versioned Event

**Every state change, cross-module notification, and lifecycle action is a published event on a durable bus.** No direct module-to-module calls for state-change notification. Event catalogue is versioned.

**Rules:**
- **One bus, one contract.** `IEventBus.PublishAsync` + `IEventSubscriber.HandleAsync`. Backed by PG LISTEN/NOTIFY for small, Kafka for medium+. Transparent to module author.
- **Every event is a typed class** in SDK (`Novara.Events.*`), versioned via `[EventVersion(1)]`. Consumers handle N and N-1.
- **Every event carries envelope:** event-id (idempotency), correlation-id, product-id, org-id (where applicable), actor, timestamp.
- **Well-Known Event Catalogue** in `SdkEventCatalog.md`. Adding an event = PR updates catalogue. Naming: `novara.{module}.{entity}.{verb}`.
- **At-least-once delivery.** Consumers idempotent on `event-id`.
- **Durability per event:** `ephemeral` / `durable` / `replayable` (retained N days for late-joining consumers).
- **No synchronous cross-module notification calls.** Direct calls are for queries (`ICrossModuleQuery`), not state changes.
- **Schema registry** auto-generated into SDK NuGet. Falling behind producer = compile-time warning.
- **Dead-letter queue** for unhandled/rejected — inspected by `novara.health`, depth alerts.
- **Event-sourced state is optional consumer pattern** — audit/incidents/retrospectives subscribe to `replayable` and rebuild state.

**Why:** Without a durable bus, every cross-module feature adds an HTTP dependency. N² coupling in a 33-module platform is catastrophic.

## 19. Identity & Permissions as Platform Service — RBAC + ABAC + Delegation + Break-Glass

**Every authenticated request resolves identity + permissions through one platform service.** No module implements its own role model, permission checks, delegation, or escalation.

**Rules:**
- **Two models:** RBAC (role → permissions) for coarse structure; ABAC (attribute-based policy) for fine-grained (e.g., "user can edit own issues; BU admin can edit any in their BU"). Together in one resolver.
- **Every module declares its permission catalogue** in manifest (`IPermissionProvider.Permissions`). No hard-coded permission strings — descriptors with IDs, descriptions, risk levels.
- **`[RequirePermission("X")]`** on every mutation endpoint. Read endpoints optional but recommended for sensitive data.
- **Delegation first-class:** "User A delegates to User B 2026-05-01 to 2026-05-14." Every check walks delegation chain.
- **Break-glass:** emergency override = double approval + full audit. Non-revocable log.
- **Time-bound permissions:** grants expire via `valid_until`. Reduces standing privilege.
- **Permission changes are audit events** (#18).
- **Deployment-level role overrides** — enterprise admin redefines role → permission mapping. Novara ships defaults; customer tunes per deployment.
- **Service accounts are first-class** (CI bots, inspectors, connectors). Deployment-scoped API keys with revocation.
- **Session model:** JWT for API, Cookie for UI, mTLS for inter-module (zero-trust).

## 20. Configuration Hierarchy as Platform Service — Resolution Chain, Not Per-Module Code

**Every setting resolves through one hierarchy: `default → deployment → org/BU → product → team → user`.** Modules declare; platform handles storage, resolution, caching, audit.

**Rules:**
- **One resolver:** `IModuleSettings.GetAsync<T>(key, scope)`. Walks most-specific to least, first hit wins.
- **Every setting has a descriptor** (`SettingField` — see `settings-discipline.md`). Type-safe, range-validated, audited.
- **Six scopes**, resolution user > team > product > org/BU > deployment > default. Team and org/BU optional per module.
- **Changes are audit events** — immutable. Auditor can prove which value was in effect at any past moment.
- **Caching per-scope** with invalidation on write. 5-min default TTL.
- **Schema evolution:** never remove, never tighten bounds, never change type silently. Deprecate first.
- **Enterprise admins tune at deployment, org/BU, and product scope** via generated Admin UI. No bespoke settings pages per module.
- **Secrets via AppGateway vault** — referenced by key, masked on read.
- **Bulk import/export** as signed JSON per product — enterprises can Git-version their tuning.

## 21. Outbound Events / Webhooks as Platform Service — One Way to Talk to the World

**When Novara talks to the outside — Slack, Jira, PagerDuty, ServiceNow, webhook, email — it goes through the Outbound Events service.** No module implements its own webhook dispatcher.

**Rules:**
- **One service:** `IOutboundEventDispatcher.SendAsync(OutboundEvent e)`. Platform handles: target registration, signing, retries with backoff, circuit breakers, DLQ, audit.
- **Every subscription is a first-class entity** in Admin UI: target, event filter, transform template, secret/HMAC key, retry policy.
- **Built-in targets:** generic HTTPS webhook, Slack, Teams, PagerDuty, Jira, ServiceNow, GitHub, GitLab, SMTP, signed POST. New targets = modules (same `IConnectorHandler` pattern).
- **Payload signing:** Ed25519 header. Customers verify.
- **At-least-once delivery** with idempotency key. Retry: 1s, 5s, 30s, 5m, 30m, 2h, 12h, 24h, DLQ.
- **Observability:** every dispatched event → `outbound_delivery_log` (sender, target, attempts, status, response).
- **Subscriptions scoped to deployment** (optionally narrowed to product or org/BU). Platform-defined targets (e.g., built-in PagerDuty for SLO breach) are ship defaults, enterprise-tunable.
- **Rate-limiting per target** — respect customer Slack/PagerDuty quotas.
- **Same framework as inbound connectors.** Outbound is just another direction.

## 22. Module Lifecycle & Versioning — Install, Upgrade, Hot-Swap, Rollback, Safe-Mode

**Every module has a declared lifecycle managed by the platform, not bespoke deploy scripts.** Customers install, upgrade, rollback, hot-swap through one UI.

**Rules:**
- **Every module carries a `ModuleManifest`** — id, CalVer (`YYYY.M.D.N`), dependencies, migrations, rollback metadata, signing.
- **Five lifecycle stages:** `install → enable → run → disable → uninstall`. Hooks: `OnInstallAsync`, `OnEnableAsync`, etc.
- **Blue-green upgrades** — new version alongside old; customer gates over via Admin UI; old kept for rollback window. Zero downtime.
- **Migrations idempotent and reversible.** Up/down scripts versioned, tracked in `productmeta.migration_log`. Cross-year upgrades require confirmation.
- **Safe-mode boot** — module crashes Gateway → next boot quarantines; Admin UI surfaces error + rollback without redeploy.
- **Dependency resolution:** `[DependsOn("novara.workflows", ">=26.4.10")]` (Novara CalVer `YY.M.DN` per `versioning.md`). Gateway refuses start if unsatisfied.
- **Signed bundles** by Monocept release key. Installation audit-logged. Air-gap imports same flow.
- **Compatibility matrix** — every release declares compatible SDK + sibling-module versions.
- **Deprecation window:** deprecated module loads for 2 calendar quarters with boot warning. Hard-removed at next year boundary.
- **Customer-written modules** follow same contract. No "first-party vs customer" split.

## 23. Observability Contract — Every Module Emits Standard Health, Metrics, Traces

**Every module emits health signal, metrics, traces through one contract.** Platform aggregates; `novara.health` renders.

**Rules:**
- **`IHealthCheck` on every module** — returns `healthy | degraded | down` + structured reason + last-success timestamp. Queried every 30s.
- **Standard metrics:** RPS, error-rate, P50/P95/P99 latency, queue depth, db-query-count. OpenTelemetry, same names across modules.
- **Traces:** spans on every incoming request + outgoing DB + outgoing connector. Sampled. OTLP export.
- **Correlation IDs propagate** through every call (incoming → events #18 → cross-module).
- **Structured logs only** — JSON `{ts, level, correlation_id, module, product, org, event, attrs}`. No free-form `LogInformation("{data}")`.
- **Readiness vs liveness distinct.** K8s-compatible.
- **SLOs per module** — declared by module, surfaced in Health dashboard.
- **Sampling controls** — admin tunes per module/product/env. Default 10%; 100% for errors.
- **No PII in logs/metrics/traces.** Same scrubber as #12. Violations fail pre-commit.
- **Meta-telemetry loop** — observability infra emits its own health signals.

## 24. Data Lifecycle & Retention Contract — Every Module Declares How Its Data Ages

**Every table, blob, log has declared retention, export format, and RTBF behaviour.** No module keeps data forever; none invents its own retention.

**Rules:**
- **Every table has `DataDescriptor`** (migration or attribute): retention by tier, export-includable, RTBF-user-scoped, product-scoped.
- **Four tiers:** hot (queryable, full fidelity) → warm (rollups, queryable) → cold (compressed archive, restore-only) → forever (audit, never aged).
- **Tier transitions platform-driven** — module declares "hot=7d, warm=90d, cold=365d"; platform runs jobs.
- **Export per deployment and per product.** `GET /api/products/{id}/export` → signed bundle across all modules for that product. GDPR Article 20 via per-product export.
- **RTBF per user:** `DELETE /api/users/{userId}/data` cascades across modules declaring user-scope.
- **Retention tunable per deployment** (and optionally per product) — extend yes, shorten below compliance floor no. Ship defaults meet regulatory floor.
- **Cold tier standardised:** Parquet on object store, partitioned `product/module/date.parquet`. One reader restores anything.
- **Cross-module joins over cold tier** use same partition scheme.
- **Audit everything** — tier transitions, RTBF, exports → events (#18) + `novara.audit`.
- **Backup ≠ retention** — retention ages live data; backup is DR. Both declared per module.

## 25. API Contract Evolution — Versioning, Deprecation, Sunset

**Every externally-consumed API follows one protocol: version explicit, deprecation declared, sunset enforced.**

**Rules:**
- **URL versioning** — `/api/v{major}/...`. N and N-1 supported ≥12 months after N+1 ships.
- **Field additions always safe.** Never remove/rename on an existing version.
- **Breaking changes require:** new version, `X-Deprecated: true, sunset: 2027-01-01` header on old, migration guide in KB, customer notification (#21).
- **Response headers surface contract state:** `X-Novara-Api-Version: 26.4.210` (Novara CalVer `YY.M.DN`). URL `/api/v1` stays semver-style for URL stability.
- **OpenAPI auto-generated** every build. CI diffs against last release; breaking change fails build unless URL-major bump + CHANGELOG + guide.
- **Consumer-driven contract tests** in SDK — customer runs against new Novara pre-deploy. Breaking changes surface early.
- **Sunset scheduled**, not ad hoc. Calendar entry, notification, grace period, hard-remove.
- **Internal module APIs** (`ICrossModuleQuery`, `IEventBus`) — same principles, simpler mechanics.
- **SDK uses CalVer** (`YYYY.M.D.N`). Year-boundary = informal "major" moment. Mid-year breaking still requires CHANGELOG BREAKING + ADR.
- **Anti-corruption layer** — connectors normalise external API shapes to Novara's internal shape. External change → only connector adapts.

## 26. Internationalisation & Localisation — Every String, Date, Number, Currency

**Every user-visible string, date, number, currency, timezone goes through the i18n service.**

**Rules:**
- **Every user-facing string is a resource key**, not a literal. Modules declare in `i18n/en-US.json` + translations.
- **Supported locales declared platform-wide.** Ships en-US; customer installs add locales. Deployment-overridable.
- **Dates stored ISO-8601**, localised at render. User timezone via config hierarchy (#20).
- **Numbers via `Intl.NumberFormat`.**
- **Currencies carry ISO 4217 code** always.
- **Plurals via CLDR** — `{count, plural, one {# issue} other {# issues}}`. Not if-else.
- **LTR/RTL honoured** in every layout.
- **Sort by normalised form** (collation) — German umlauts, Chinese pinyin, accents correct.
- **Missing translations fall back to en-US** with `[untranslated]` tag in dev, silent in prod.
- **Lint rule blocks literal strings** in user-facing surfaces.

**Why:** Platforms that don't bake in i18n rewrite it in year 3 at 10× cost. First non-English customer is inevitable.

## 27. Multi-Region / Data Residency — Where Data Lives Is Declared, Not Accidental

**Every deployment has a declared region; data never leaves it.** For customers operating in multiple regions, a deployment can have per-product region placement.

**Rules:**
- **Deployment declares primary region** at install — `us-east-1`, `eu-west-1`, `ap-south-1`, or an on-prem zone. Immutable without explicit migration.
- **Every data write is region-tagged** in the envelope. Platform enforces: write outside the deployment's region → 451 Legal Reasons.
- **Cross-region reads only via explicit federation** — enterprise admin opts in (e.g., US parent viewing EU subsidiary rollups). Federation at aggregate level; raw rows never cross.
- **Multi-region deployment topology** — one control plane + region-local data planes. Gateway routes by product → region.
- **Data-sovereignty policy packs:** GDPR (EU), PIPL (China), DPDP (India), UAE localisation. Customer enables per deployment.
- **Backups region-local by default.** Cross-region replication = opt-in + audit event.
- **Air-gap is strongest residency** — no data leaves ever. Outbound only via signed export if customer chooses.
- **Regional health isolated** — region down doesn't degrade others.
- **Customer audits residency:** `GET /api/deployments/{id}/residency-report` lists every module/table/region.
- **Region move is a first-class operation** — enterprise admin triggers, platform orchestrates copy + switchover + verification + old-region purge.

## 28. Per-Product Isolation — Every Product Is Its Own Blast Radius

**Within a deployment, every product gets its own isolated environment:** own database, own connectors, own resource quotas, own retention, own audit trail. Distinct from deployment-model (#14) — that's *where data lives across enterprises*; this is *how blast radius is contained within one enterprise's deployment*.

**Rules:**
- **Database per product.** `NovaraWorkspaceProductDB_{productKey}`. `ProductDatabaseRouter` resolves per request. Schema, extensions, indexes, retention, even PG version independent.
- **Bulkhead at connection pool.** Each product = own `pgBouncer` pool with own max-connections. No deployment-wide exhaustion.
- **Resource quotas per product:** events/sec, storage GB, query CPU-seconds/min, worker concurrency. Breach → 429s on that product only.
- **Connector instances product-scoped.** Datadog/Sentry/Prometheus configs at product level. Credentials never shared.
- **Signal families per product.** Product A = Application only; B = Application + Infra; C adds Cost.
- **Retention per product.** Regulated product = 7yr; internal tool = 30d.
- **Audit trail product-scoped** (`audit.log` in product DB). Cross-product views for platform admins, opt-in.
- **Ingest enforces quotas.** Every event carries `product_id`; gateway routes to product partitions, checks quotas.
- **Deletion atomic and clean.** `DELETE /api/products/{id}` drops product DB, archives per retention, revokes credentials, unwinds shared-catalogue entries.
- **Export independent.** Offboard Product A → complete bundle (PG dump + object store + manifest + audit) re-hydratable in a new deployment. B/C untouched.
- **Cross-product federation opt-in**, never implicit. Executive "all products" view via read-only router queries.
- **Compute optionally product-scoped at XL tier.** Noisy products get dedicated workers + Kafka consumer groups. S/M tiers share compute, isolate data.

**Why:** A misbehaving SDK on Product A cannot degrade Product B. Per-product economics (showback/chargeback to internal product teams) become trivial. DR: product-scoped backups and restores.

**Relationships:**
- **#4 BU/Org Isolation** — within a product, `OrgId` and user permissions gate row visibility. Product isolation is DB-level; BU isolation is row-level within a product.
- **#14 Deployment Model** — one deployment = one enterprise. Products = second level of isolation within that deployment.
- **#27 Data Residency** — a product's data lives in the deployment's declared region (or its own if multi-region placement is configured).
- **#24 Data Lifecycle** — retention declared per product.
