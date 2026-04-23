# Novara Product Standard — BINDING

**Adopted:** 2026-04-23 · binding for every Novara product (Workspace, TelemetryHub, ViberHub, and every product after)

This document is the **contract** that a codebase must satisfy to qualify as a Novara product. It doesn't duplicate the detailed rules — it's the **index + product-level gates**. Each numbered requirement points at the authoritative binding rule.

## 0. Why this exists

Novara is a multi-product platform (Workspace, TelemetryHub, ViberHub, ...). Each product deploys independently, evolves on its own cadence, serves its own users. But they all share the same substrate — same SDK, same Gateway, same Shell, same module conventions, same database patterns.

Without a single contract, products drift. One module thinks snake_case, another thinks camelCase. One uses CalVer, another uses semver. One skips tests, another writes xunit. Three years later the platform is five disparate codebases with a Novara logo slapped on.

This document is the anti-drift gate. **Every Novara product PR + every new product bootstrap must be checkable against these requirements.**

## 1. What constitutes a Novara product

A "Novara product" is a deployment that:

- Ships its own Gateway (consumes `Novara.Shell.Gateway` NuGet) running on its own port
- Ships its own Shell UI (consumes `Novara.Shell.UI` NuGet or equivalent) on its own port
- Owns one platform DB (`Novara{Product}PlatformDB`) + at least one product DB (`Novara{Product}ProductDB`, cloneable per customer product)
- Installs one or more modules from the `novara-module-*` / `novara-{product}-module-*` ecosystem
- Deploys inside a customer's trust boundary (per Decision #14 — "one deployment per enterprise")

Not every Monocept codebase is a Novara product. A connector adapter, a SDK package, a standalone script, a migration tool — these are supporting artifacts, not products. They follow whichever rules apply to their category (connectors: `.claude/rules/connector-standard.md` when written; packages: `versioning.md`; etc.).

## 2. Repo + folder structure

Every Novara product has this shape at the workspace level:

```
D:/NovaraDev/
└─ {Product}/                               ← meta-folder, one per product
   ├─ Novara{Product}Shell/                 ← Gateway + Shell UI (consumed from Novara.Shell.Gateway/UI)
   │  ├─ api/                               ← Gateway host project
   │  │  └─ host/Novara.DevHost.csproj
   │  ├─ web/                               ← Angular 21 Shell UI (Native Federation host)
   │  ├─ scripts/                           ← build-all.sh, restart-dev.sh, release scripts
   │  ├─ .claude/                           ← product-level rules/commands/hooks (inherits Workspace common)
   │  ├─ Directory.Packages.props           ← CPM stub forwarding to workspace-level template
   │  ├─ CHANGELOG.md
   │  ├─ CLAUDE.md
   │  ├─ README.md
   │  └─ release.sh
   ├─ Novara{Product}Modules/               ← product-specific modules
   │  └─ novara-{product}-module-{name}/   ← each module is its own git repo
   │     ├─ api/src/Novara.{Product}.Module.{Name}/
   │     │  ├─ {Name}Module.cs
   │     │  ├─ Controllers/
   │     │  ├─ Services/
   │     │  ├─ Contracts/
   │     │  ├─ Models/
   │     │  ├─ Constants/{Name}SpNames.cs
   │     │  └─ Novara.{Product}.Module.{Name}.csproj
   │     ├─ web/                            ← Angular federation remote
   │     ├─ migrations/                     ← schema-only; data seeds go in seed files
   │     ├─ documents/                      ← specs, wireframes (module-owned)
   │     ├─ .claude/                        ← module-level rules
   │     ├─ Directory.Packages.props        ← CPM stub
   │     ├─ CHANGELOG.md
   │     ├─ CLAUDE.md
   │     ├─ module.json                     ← manifest (capabilities, dependencies)
   │     ├─ build.sh
   │     └─ release.sh
   ├─ Common/                               ← propagation target for shared rules/hooks
   │  ├─ .claude/rules/                    ← synced from Workspace/Common via propagate-rules.sh
   │  └─ ...
   └─ Directory.Packages.props              ← CANONICAL CPM template for this product's repos
```

**Rules that govern this structure:**
- Every module is its own git repo (binding, no monorepos of modules)
- Every module has `api/`, `web/`, `migrations/`, `.claude/`, `module.json`, `release.sh`, `CHANGELOG.md`
- Every product has its own Shell + its own meta-folder
- `Common/` inherits rules from `Workspace/Common/` via propagation script

## 3. Git + DevOps

### 3.1 Git host
All Novara-owned repos live on Azure DevOps under the `Novara-Monocept` organization. One project per product (`TelemetryHub`, `Workspace`, `ViberHub`, `Connectors`). See `.claude/rules/devops-hosting.md` (TBD) for project + permissions details.

Clone URL pattern:
```
https://dev.azure.com/Novara-Monocept/{Project}/_git/{repo-name}
```

### 3.2 Branching
`master` is the default branch on every repo. Per `git-workflow.md`. No GitFlow, no long-lived develop branch. Feature branches are transient; merged via PR.

### 3.3 Commit messages
Prefix: `add | update | fix | remove | refactor | docs | test | chore`. Per `git-workflow.md` + memory.

### 3.4 Pull before push
Always `git fetch` + `git pull --ff-only` before `git push`. No force-pushes to master without explicit user direction. Per memory rule.

## 4. Versioning + distribution

### 4.1 CalVer
Every Novara-authored NuGet + NPM package uses `YY.M.DN`. Mandatory N. Detailed rules in `.claude/rules/versioning.md`.

### 4.2 Central Package Management
Every `.csproj` declares `<PackageReference Include="..." />` with NO Version attribute. Versions pinned in `Directory.Packages.props` at workspace root, propagated to per-repo stubs via `distribution/propagate-packages.sh`.

### 4.3 Release discipline
Every version bump gets a `CHANGELOG.md` entry. Pre-commit hook `check-changelog-on-version-bump.py` enforces. `release.sh` handles the full cycle: bump + build + pack + publish + propagate + commit + push.

### 4.4 Package feed
All NuGet + NPM packages publish to the org-level `novara-platform` Azure Artifacts feed:
- NuGet: `https://pkgs.dev.azure.com/Novara-Monocept/_packaging/novara-platform/nuget/v3/index.json`
- NPM: `https://pkgs.dev.azure.com/Novara-Monocept/_packaging/novara-platform/npm/registry/`

Every `release.sh` pushes here. Every consumer `nuget.config` + `.npmrc` points here. Auth via `AZURE_ARTIFACTS_PAT` environment variable (or `az artifacts universal login` interactively).

## 5. Database

Per `.claude/rules/database.md`, `database-design-principles.md`, `sql-conventions.md`:

### 5.1 One database per product
Each product owns two: `Novara{Product}PlatformDB` (routing, auth) + `Novara{Product}ProductDB` (one product's data). Additional product DBs created on-demand via `CREATE DATABASE ... WITH TEMPLATE Novara{Product}TemplateProductDB`. Per Decision #28.

### 5.2 Schema per module
Each module owns a named schema (e.g. `agent_ops`, `ingest`, `roadmap`). No `product.*`, `dbo.*`, or shared schemas. `productcore.*` + `productmeta.*` are the only cross-module shared schemas.

### 5.3 Snake_case everywhere
Columns, function names, function parameters (`p_` prefix) — all `snake_case`. Pre-commit hook `check-sql-param-naming.py` blocks new functions with legacy naming. Per `sql-conventions.md`.

### 5.4 No raw SQL in services
All DB access via PostgreSQL functions. Function names in `{Module}SpNames.cs` constants. Pre-commit hook blocks raw SQL in module services (architecture rule R6).

### 5.5 INT identity primary keys
Never UUID/GUID for PK. Never composite PKs unless necessary. Per `database-design-principles.md`.

### 5.6 Soft delete + audit
Every table: `is_deleted BOOL`, `created_by_user_id INT`, `created_at_utc TIMESTAMP`, `modified_by_user_id INT`, `modified_at_utc TIMESTAMP`. Queries filter `is_deleted = false`.

## 6. Backend module conventions

Per `.claude/rules/module-development.md` + `dotnet-patterns.md`:

### 6.1 Every module extends `ModuleBase`
`public class {Name}Module : ModuleBase` — declared in `{Name}Module.cs` at module root. Registers controllers + services via `ConfigureServices(IServiceCollection)`.

### 6.2 Routing
`[ModuleRoute("path")]` for product-scoped endpoints (auto-prefixes `/api/v1/products/{productId}`). `[PlatformRoute("admin/path")]` for platform-level admin only (Admin, Rules, AppGateway — rare).

### 6.3 Controllers are thin
Extract parameters, call ONE service method, wrap result in `ApiResponse<T>`, return. No business logic. No exception catching (GlobalExceptionMiddleware handles). No direct DB access.

### 6.4 Service patterns
- Inherit `CrudServiceBase` for CRUD (auto audit + events + cache)
- Use `Guard.*` for validation (`NotEmpty`, `Found`, `Positive`, `OneOf`, `ValidId`)
- Use `SafeExecute.*` for non-critical side effects (audit, events, notifications)
- Inject `IModuleDbContext` (product DB), never `IPlatformDbContext` unless `DbScope = Platform`
- `SpNames.*` constants, never magic strings
- Inline `// SP:` comments showing function signature on every `ExecuteProcedureAsync` call

### 6.5 DTOs + typed contracts
No `dynamic`, no anonymous objects. Every request/response is a record/class in `Contracts/`. `ApiResponse<T>` wraps every response.

### 6.6 Pagination
Every list endpoint uses `PagedResponse<T>`. Never `IEnumerable<T>` for unbounded lists.

### 6.7 CancellationToken everywhere
Every public async method takes `CancellationToken ct = default`. Propagated through controller → service → DB.

### 6.8 Events on state changes
Every CREATE/UPDATE/DELETE publishes an event via `IEventBus.PublishAsync` with a typed event class from SDK. Published AFTER DB write succeeds.

## 7. Frontend module conventions

Per `ui-kit-components.md`, `sdk-services.md`, `coding-standards.md`:

### 7.1 Angular 21 + Native Federation
Every module's `web/` is a federation remote. Shell UI is the host. `federation.config.js` exposes `./routes` + `./index`.

### 7.2 Standalone components
Every component `standalone: true`, `changeDetection: ChangeDetectionStrategy.OnPush`. `ChangeDetectorRef` injected + `markForCheck()` called after every async update (federation learned-error).

### 7.3 HTTP via `ApiService`
No `HttpClient` direct in module code. No hardcoded URLs. `ApiService` from `@novara/shell-sdk` handles: auth, base URL, query params, `ApiResponse<T>` envelope. Pre-commit hook R3/R4 blocks violations.

### 7.4 UI primitives from `@novara/ui-kit`
`nov-status-badge`, `nov-empty-state`, `nov-loading-skeleton`, `nov-data-table`, `nov-modal`, `nov-pagination`, `nov-tabs`, `nov-drawer`, `nov-confirm-dialog`. No hand-rolled buttons/tables/modals when a `nov-*` equivalent exists.

### 7.5 IDs obfuscated in URLs
`IdEncoderService.e(id)` for encoding, `.d(str)` for decoding. Never raw sequential ids in routerLinks.

### 7.6 TypeScript models
Every API response has a typed interface in `models/*.models.ts`. No `any[]`, no untyped response handling.

## 8. Cross-module communication

Per `.claude/rules/architecture-decisions.md` + `architecture-enforcement.md`:

### 8.1 `IEventBus` for cross-module state changes
Typed events in SDK under `Novara.Events.*`. Versioned via `[EventVersion(n)]`. Publisher knows nothing about consumers.

### 8.2 `ICrossModuleQuery` for read-only cross-module queries
Typed `ICrossModuleRequest<TResult>` records in SDK `Contracts/CrossModule/`. Target module implements a handler. Mediator dispatches.

### 8.3 No direct module → module imports
Pre-commit hooks R1 (C#) + R2 (TypeScript) block cross-module `using Novara.Module.Other` / `import { X } from '@novara/module-other'`.

### 8.4 External calls via Connectors
No `HttpClient` direct (R3) or `HttpClient` import in Angular (R4). All external calls through the Connector framework. Per Decision #11.

## 9. Rules + hooks infrastructure

### 9.1 `.claude/rules/` — binding rules
Every product's `Common/.claude/rules/` is synced from `Workspace/Common/.claude/rules/` via `distribution/propagate-rules.sh`. Per-module `.claude/rules/` also synced, plus module-specific additions.

### 9.2 `.claude/hooks/` — pre-commit checks
Module boundaries, recursion safety, prompts discipline, CHANGELOG on version bump, SQL param naming, capability drift, packaging policy. All hooks in `Workspace/Common/.claude/hooks/` propagate to every repo.

### 9.3 `.claude/commands/` — slash commands
`/pull`, `/status`, `/start`, `/update-deps`, `/clean`, `/pushtoorigin`, `/release`. Standard developer workflow commands, identical in every product's repos.

## 10. Testing + observability

### 10.1 Observability-first, not unit-test-first
No xunit test projects inside Novara modules. Real runs are the characterization. Per `.claude/rules/observability-first-testing.md` (binding 2026-04-23).

### 10.2 Canaries are the safety net
Curated BRDs dispatched after significant changes. YAML format at `.claude/canaries/brds/`. Interim runner at `.claude/canaries/run.sh`. Permanent home: TelemetryHub canary module.

### 10.3 Every module emits structured traces
`ITraceRecorder` for step events. `IAuditService` for mutations. Logs are JSON-structured with correlation IDs per `architecture-decisions.md` #23.

## 11. Agents

Per `.claude/rules/agent-runtime-debt.md` + module conventions:

### 11.1 Agentic runtime shared
`Novara.Module.Agentic` NuGet consumed by any product that wants agents. Every product gets the same runtime — same session model, same step executors, same tool registry abstraction, same `IAgentReasoning` interface.

### 11.2 Agent population product-specific
Agents are data: rows in `agent_ops.definition` + `agent_ops.context_recipe` + prompts in `promptstudio.*`. Each product seeds its own: Workspace = BRDImplementer + FeatureImplementer + ErrorFix + CodeReviewer + DocLinter + more. TelemetryHub = AnomalyDetector + LogClassifier + AutoTriager + AlertSilencer + RemediationAgent. Different populations, same runtime.

### 11.3 Tools product-specific
Each product registers its own `INovaraToolProvider`s. Workspace provides dev tools (`write_file`, `run_build`, `dispatch_queue`). TelemetryHub provides SRE tools (`query_spans`, `evaluate_threshold`, `silence_alert`, `apply_runbook`).

## 12. Capability registry

Per `.claude/rules/capability-registry.md`:

### 12.1 Capabilities declared in code
`ModuleManifest` declares: `MenuItems`, `Permissions`, `PublishedEvents`, `SubscribedEvents`, `Widgets[]`, `DbSchema`, `Dependencies`. Code is the source of truth.

### 12.2 Cross-module contracts in SDK
Typed `ICrossModuleRequest<TResult>` records in `NovaraSDK/src/Novara.Module.SDK/Contracts/CrossModule/`. Named convention: `{Module}Contracts.cs`.

### 12.3 `CAPABILITIES.md` generated, not written
Auto-generated from `ModuleManifest` on every build. Pre-commit hook detects drift between generated + committed versions.

## 13. Widgets (observational surfaces)

Per `.claude/rules/extensibility-model.md`:

### 13.1 Every page-owning module has widget tables
`{schema}.widget_layout` + `{schema}.widget_user_state`. Schemas created from per-module template.

### 13.2 Widget descriptors are CODE
`ModuleManifest.Widgets[]`. Not DB. Contributions to other modules' pages by descriptor reference only.

### 13.3 Three render states
Every widget handles populated / empty (configured, no data) / unavailable (module not installed, shows install CTA).

## 14. Customer deployment

Per `.claude/rules/customer-deployment.md` + `architecture-decisions.md`:

### 14.1 One deployment per enterprise
No multi-tenant row-scoping. Per Decision #14.

### 14.2 Credentials per-tenant
LLM keys, storage keys, SSO config — all per-tenant in `platform.*` tables with `TenantId`. Never shared.

### 14.3 Air-gap ready
Every product must run without internet. Bundle + verify + install via signed NuGet packages. No calls to Monocept infrastructure at runtime unless explicitly configured.

## 15. Bootstrap — what a new Novara product needs to set up

Given a fresh Windows (or eventually Ubuntu) machine, a new product's `bootstrap.sh` (or PowerShell equivalent) must install:

### 15.1 System dependencies
- PostgreSQL 16 + TimescaleDB (if product needs timeseries) + pgvector
- .NET 10 SDK
- Node 20+
- Git, Tailscale, Claude CLI
- Azure CLI + azure-devops extension

### 15.2 Azure DevOps auth
- `az login` with user's Entra account
- `az devops configure --defaults organization=https://dev.azure.com/Novara-Monocept`
- NuGet feed auth: `az artifacts universal login` or PAT in environment
- NPM feed auth: `.npmrc` with PAT

### 15.3 Database provisioning
- `CREATE DATABASE Novara{Product}PlatformDB`
- `CREATE DATABASE Novara{Product}TemplateProductDB`
- `CREATE DATABASE Novara{Product}ProductDB WITH TEMPLATE Novara{Product}TemplateProductDB`
- Mark template DB `datistemplate=true`

### 15.4 Repo clones
- Clone product's Shell repo + all module repos from Azure DevOps
- Restore NuGets from `novara-platform` feed
- Restore NPM deps

### 15.5 Migrations
- Run platform DB migrations
- Run each module's product DB migrations
- Seed minimum data: test user, test product, agent definitions, starter prompts

### 15.6 Start
- Gateway on product's port (Workspace :5050, TelemetryHub :5030, ViberHub :5020 — convention: Workspace is authoritative, others pick non-colliding)
- Shell UI on product's port (:4200, :4230, :4220 — same pattern)
- Confirm `GET /health` returns 200

## 16. What MAY differ between products

- **Module population** — which modules each product ships (Workspace ships issues+designstudio+codereview; TelemetryHub ships ingest+canaries+dashboards)
- **DB extensions** — TimescaleDB only where timeseries needed; pgvector only where embeddings needed
- **Agent population** — different seeded agents + tools per product
- **Shell branding** — logos, colors, product name (via config, not code fork)
- **Port conventions** — each product claims a port range; documented here (see 15.6)
- **Connector integrations** — different customer integrations per product

## 17. What MUST be identical across products

Everything not listed in §16. The substrate is shared, enforced by this standard + the binding rules referenced.

## 18. Checking a product against this standard

A product passes the standard when:

1. Every binding rule listed above is honored (referenced rule file, not duplicated here)
2. Repo structure matches §2 exactly
3. Version artifacts pass CalVer + CPM validation (`version-sweep.py` clean)
4. DB schema passes snake_case + per-module-schema checks
5. Pre-commit hooks installed + green
6. `CHANGELOG.md` current + BREAKING entries for every breaking change since last audit
7. Observability-first discipline (no xunit projects)
8. `CAPABILITIES.md` generated + matches code

A **product audit script** (`distribution/audit-product.sh`) enforces these in CI. Runs on every PR. Failure blocks merge.

## 19. New product onboarding — cheat sheet

To stand up a new Novara product:

1. Create Azure DevOps project under `Novara-Monocept`
2. Create Shell repo: `Novara{Product}Shell`
3. Create 1-N module repos: `novara-{product}-module-{name}`
4. Clone Workspace's Shell + one module as templates; adapt
5. Create product DBs (Platform + Template + Product)
6. Write `bootstrap.sh` / `bootstrap.ps1` following §15
7. Seed agents + prompts + recipes
8. Run `audit-product.sh` — fix failures until green
9. Dispatch first BRD, watch agent implement it

## 20. Related rules (authoritative)

| Concern | Rule file |
|---|---|
| Versioning | `.claude/rules/versioning.md` |
| Release workflow | `.claude/rules/release-workflow.md` |
| Build consistency | `.claude/rules/build-consistency.md` |
| Module development | `.claude/rules/module-development.md` |
| Coding standards | `.claude/rules/coding-standards.md` |
| Dotnet patterns | `.claude/rules/dotnet-patterns.md` |
| Database | `.claude/rules/database.md` |
| Database design | `.claude/rules/database-design-principles.md` |
| SQL conventions | `.claude/rules/sql-conventions.md` |
| Architecture decisions | `.claude/rules/architecture-decisions.md` |
| Architecture enforcement | `.claude/rules/architecture-enforcement.md` |
| Architecture lookup | `.claude/rules/architecture-lookup.md` |
| Capability registry | `.claude/rules/capability-registry.md` |
| Extensibility (widgets) | `.claude/rules/extensibility-model.md` |
| Observability-first testing | `.claude/rules/observability-first-testing.md` |
| Customer deployment | `.claude/rules/customer-deployment.md` |
| Multi-tenancy (historical) | `.claude/rules/multi-tenancy.md` |
| Resilience | `.claude/rules/resilience.md` |
| Settings discipline | `.claude/rules/settings-discipline.md` |
| Prompts discipline | `.claude/rules/prompts-discipline.md` |
| SDK services | `.claude/rules/sdk-services.md` |
| UI kit components | `.claude/rules/ui-kit-components.md` |
| URL security | `.claude/rules/url-security.md` |
| URL conventions | `.claude/rules/url-conventions.md` |
| Git workflow | `.claude/rules/git-workflow.md` |
| Migration scope | `.claude/rules/migration-scope.md` |
| Packaging discipline | `.claude/rules/packaging-discipline.md` |
| Agent runtime debt | `.claude/rules/agent-runtime-debt.md` |
| Recursion safety | `.claude/rules/recursion-safety.md` |
| Learned errors | `.claude/rules/learned-errors.md` |
| Engineering discipline | `.claude/rules/engineering-discipline.md` |
| Engineering guardrails | `.claude/rules/engineering-guardrails.md` |
| Quality framework | `.claude/rules/quality-framework.md` |

This document is the **index**. Each rule file is authoritative for its concern.

## 21. Revision history

- 2026-04-23 — Initial version. Captures the Workspace standard as of today, makes it binding for every new Novara product starting with TelemetryHub.
