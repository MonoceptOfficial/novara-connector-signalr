# Architecture Lookup — Reuse Before Inventing (BINDING)

## Why this rule exists

On 2026-04-20, a workspace-multiview ADR proposed a new `platform.userlayout`
table — which violated the binding per-product-DB rule + the "use existing
modules, don't reinvent" principle. A per-user-per-product preference table
belongs in the existing `novara.personal-settings` module's product-scoped
schema, not in a new platform-level table.

The mistake was: write the spec without first walking the existing structure.
The fix: a mandatory lookup protocol before ANY spec proposes something new.

## The rule

**Before proposing any new:**
- Database schema
- Database table
- Module
- SDK service / interface
- Configuration key pattern
- Platform-level abstraction

**You MUST first run the Existing-Structure Lookup and record the result in
a mandatory header block at the top of the spec / ADR.**

No spec is accepted without this header. No implementation starts without it.

## The lookup protocol (follow in this exact order)

### Step 1 — Schema ownership
For any persistence concern, check which schema already owns it:

```
# Per-product DB schemas (productcore, productmeta, + one per module)
cat .claude/rules/database.md   # authoritative list
# Or inspect live:
psql -d NovaraWorkspaceProductDB -c "\dn"
```

If a schema already exists that's semantically close, **reuse it**. Don't create
a new schema just because the concern is "slightly different."

### Step 2 — Module ownership
For any feature, check which module owns that feature area:

```
cat CLAUDE.md   # the "33 Active Modules" table
```

The categories are: MySpace / Envision / Build / Learn / Govern / Profile /
Admin / CrossCutting. Match your concern to a category, then to a specific
module. Per-user preferences → Profile → `novara.personal-settings`. Comments +
reactions → CrossCutting → `novara.collaborate`. Workflows → `novara.workflows`.

If the match is a stretch, write one paragraph in the spec justifying why a
new module is warranted. "I want a cleaner name" is not justification.

### Step 3 — SDK service lookup
Check if the abstraction already exists in `@novara/shell-sdk` or
`Novara.Module.SDK`:

```
# TypeScript SDK surface
cat /d/NovaraDev/Workspace/novara-shell-sdk/src/index.ts

# .NET SDK surface
grep -r "public interface I" /d/NovaraDev/Workspace/NovaraSDK/src --include="*.cs"
```

Common traps:
- Proposing a new settings primitive when `IModuleSettings` / `IGatewaySettingsReader` exists.
- Proposing a new storage primitive when `IStorageClient` exists.
- Proposing a new notification primitive when `INotificationService` + SignalR exist.
- Proposing a new share/invite primitive when `IShareTokenService` exists.
- Proposing a new audit primitive when `IAuditService` exists.

### Step 4 — ADR / decision constraints
Check `.claude/rules/architecture-decisions.md` for binding decisions that
constrain your choice. Today's list (summary — full file is authoritative):

| # | Decision | Most likely to constrain |
|---|---|---|
| 1 | Async-first design | Long operations → `IJobService`, not sync controllers |
| 2 | Cache-ready service layer | Reads of stable data → `ICacheService` |
| 4 | Tenant-scoped everything | No query without tenant context in platform code |
| 11 | Unified Connector Architecture | External service calls → Connectors, never direct HTTP |
| 12 | Federated Intelligence | Customer data never leaves customer |
| 14 | Deployment model | In-customer-trust-boundary only |
| 15 | Workflows as Platform Service | State transitions + approvals → `IWorkflowParticipant` |
| 17 | Composable Dashboard Surfaces | Overviews = widget composition, not hand-HTML |
| 18 | Event-Driven Core | Cross-module signals → versioned events on `IEventBus` |
| 19 | Identity & Permissions | `[RequirePermission]` on every mutation |
| 20 | Configuration Hierarchy | Settings → `IModuleSettings` with scope chain |
| 21 | Outbound Webhooks | External posts → `IOutboundEventDispatcher` |
| 23 | Observability Contract | Logs/metrics/traces via SDK standard shape |
| 24 | Data Lifecycle | Every table declares retention + RTBF |
| 28 | **Per-Product Isolation** | **Database = product. No `platform.*` for product data. No `productid` in product DB.** |

### Step 5 — Module structure check
Every module follows a canonical shape enforced by `.claude/tools/module-drift.py`:

```
novara-module-{name}/
├── api/src/Novara.Module.{Name}/
│   ├── {Name}Module.cs
│   ├── Controllers/
│   ├── Services/
│   ├── Constants/*SpNames.cs
│   ├── Contracts/
│   └── Models/
├── migrations/
├── web/
└── module.json
```

If proposing additions to an existing module, they must fit this shape. If
proposing a new module, it must be born with this shape.

### Step 6 — Record the lookup

Every spec / ADR MUST open with a table like this:

```markdown
## 0. Existing-Structure Lookup

| Concern | Checked | Existing home | Decision |
|---|---|---|---|
| ... | ✅ | ... | REUSE / EXTEND / NEW (justify) |

**Binding rules this ADR touches and honors:** (list rule files)

**Revision history:** (list any prior drafts that were rejected for
violating existing structure)
```

See `D:\NovaraDev\specs\platform\novara-workspace-multiview-spec.md` § 0 for
the canonical example.

## Red flags — if you see these in a draft, STOP and redo the lookup

- A new `platform.*` table for data that's per-product or per-user
- A new module that overlaps an existing module's category
- A new SDK interface when an existing one covers 80% of the case
- A new configuration mechanism that bypasses `IModuleSettings`
- A new cross-module call that bypasses `IEventBus` / `ICrossModuleMediator`
- A new external-service call that bypasses the Connector framework
- A new UI dashboard hand-built instead of widget-composed (post-Decision #17)

If your spec contains any of these without an explicit "Decision: NEW because ..."
justification referencing why the existing option doesn't fit, it's rejected.

## Enforcement

- **Spec review:** every ADR PR must have section § 0 populated. Reviewer checks
  each row is accurate.
- **Post-commit scanner** (future work — `.claude/tools/check-spec.py`): parses
  `.md` files in `.claude/architecture/` and `D:\NovaraDev\specs\**`, flags any
  missing § 0 block, flags any `platform.*` table proposed in a product-scoped
  spec.
- **Memory rule:** agents and Claude instances save a note reminding themselves
  to run this lookup before drafting any new spec. Rule reinforced on each
  session start via `.claude/rules/` loading.

## What this protects against

- Reinvented settings tables → settings drift across modules
- New platform-DB tables that break customer per-product isolation
- Duplicate modules with overlapping scope
- Specs that silently contradict earlier ADRs
- Rewrites of capabilities already in the SDK

One hour of lookup saves a week of rework.
