# Capability Registry — Single Source of Truth

## Why this rule exists

> "As soon as you have two sources of truth, whenever you forget to update one,
> you really don't know where and how it started diverging." — this rule is to
> prevent that.

Novara has a capability surface area that grows as modules grow. Without a
single source of truth, two engineers (or Claude twice) can independently build
the same capability in different modules, or the registry drifts from what the
code actually does. Either outcome = broken system with silent divergence.

This rule declares the ONE source and declares everything else derived.

---

## The ONE source of truth — CODE

A capability exists ONLY when it is declared in one of:

1. **`ModuleManifest`** in a module's `*Module.cs` file
   - `Id`, `MenuItems`, `Permissions`, `PublishedEvents`, `SubscribedEvents`,
     `DbSchema`, `Dependencies`
2. **`Contracts/CrossModule/*.cs`** in `NovaraSDK`
   - Typed `ICrossModuleRequest<TResult>` records (the API other modules call)
3. **`SettingField[]` declarations** on modules (via `settings-discipline.md`)
4. **Controllers with `[ModuleRoute]` / `[PlatformRoute]`** (the public HTTP surface)

**If a capability is not in one of these FOUR places, it does not exist.** If
someone claims it does ("I saw a function in some module that does X") — that
function IS the capability, but its existence must be represented in code at
one of the places above.

---

## Everything else is DERIVED

These are generated / materialized from the four primary sources:

| Derived artifact | Generated from | Where it lives |
|---|---|---|
| `CAPABILITIES.md` at product root | Scanning all loaded `ModuleManifest` + SDK contracts | `products/<name>/CAPABILITIES.md` (git-tracked) |
| `PLATFORM-EVENT-MAP.md` | `PublishedEvents` + `SubscribedEvents` across all modules | `distribution/PLATFORM-EVENT-MAP.md` |
| `productcore.capability` table | Gateway writes on module load, reading each `ModuleManifest` | Product DB, `productcore` schema |
| `module.json` per module | Generated from `ModuleManifest` at pack time | Module root (never hand-edited) |
| Swagger / OpenAPI | Generated from controllers by ASP.NET at runtime | `/swagger` endpoint |

**Primary → Derived is a one-way flow.** If you change a derived artifact
directly, it will be overwritten on the next regeneration. If you need to
change a capability, you change the code.

---

## Product DB, not Platform DB

Capabilities are **per-product**. Workspace has Issues / Roadmap / ThinkBoard;
TelemetryHub has Ingest / Logs / App / Infra. They do not share a capability
registry.

- **DEPRECATED (do not use):** `platform.platformcapability` in
  `NovaraPlatformDB`. It crossed product boundaries, which violates the
  per-product isolation principle (architecture decision #28). Still exists
  for backward compat but no new code should read or write it.

- **CANONICAL:** `productcore.capability` in each product's DB
  (`NovaraWorkspaceProductDB.productcore.capability`,
  `NovaraTelemetryProductDB.productcore.capability`). Populated at module load
  by the Gateway from each `ModuleManifest`.

Rationale: a capability lives and dies with a product. Cross-product queries
(rare — admin dashboards only) use the HTTPS connector pattern, not shared DB.

---

## Before writing new code — the mandatory check

**For agents (feature-implementer, bug-fixer, etc.) AND humans:**

Before creating a new controller, service, SP, cross-module query, event, or
setting, walk this checklist:

1. **Search `CAPABILITIES.md`** at the product root for the capability. Does
   any module already provide it?
2. **If yes:** use the existing cross-module contract. Do NOT reinvent.
   - Example: need to list features? `GetFeatureSummary` exists in roadmap.
     Call the mediator; don't write your own SP.
3. **If no, but the capability feels like one that should exist in another
   module:** check that module's `ModuleManifest` directly. CAPABILITIES.md
   may be stale (drift detection catches this — file a fix).
4. **If truly new:** declare the capability in YOUR module's manifest first,
   THEN write the code. The manifest is the contract.

### Banned patterns

- Writing a new SP that duplicates another module's existing cross-module query
- Hand-editing `module.json` or `CAPABILITIES.md` (they regenerate)
- Writing directly to `productcore.capability` (it's a derived cache)
- Writing to `platform.platformcapability` at all (deprecated)
- Creating a new event name whose semantics match an existing `PublishedEvents` entry
- Creating a new permission key when an existing one would serve

---

## How to add a capability — concrete flow

Given: you need feature X that doesn't exist anywhere.

1. **Pick the module that owns X conceptually.** (If none, consider if X is
   truly a new module, or an extension of an existing one.)
2. **Edit that module's `*Module.cs`:**
   - Add to `Permissions` if X has access control
   - Add to `MenuItems` if X has UI
   - Add to `PublishedEvents` if X emits signals
3. **If X is a cross-module query:** add a typed contract in
   `NovaraSDK/src/Novara.Module.SDK/Contracts/CrossModule/<Module>Contracts.cs`
4. **Implement the handler** in the module (service or handler class)
5. **Build + test.** Pre-commit regenerates `CAPABILITIES.md` + drift check
   compares with the committed copy.
6. **Commit both the code AND the regenerated CAPABILITIES.md in the same PR.**

---

## Drift detection (enforced at commit time + Gateway startup)

Two checks make divergence expensive:

1. **Pre-commit hook** (`.claude/hooks/check-capabilities-drift.py`) — runs the
   generator, diffs against the committed `CAPABILITIES.md`. Fails commit if
   they differ. Developer regenerates, re-commits.

2. **Gateway startup** — on module load, the Gateway inserts each module's
   capability rows into `productcore.capability` with `ON CONFLICT UPDATE`.
   If a row exists that doesn't match any currently-loaded manifest, it gets
   marked `orphaned = true` (not deleted — history preserved). Operator sees
   orphans in the Admin UI's "Capability Drift" panel.

---

## File conventions

| Artifact | Location |
|---|---|
| This rule | `.claude/rules/capability-registry.md` (canonical) |
| Rule propagation | Pushed to every module's `.claude/rules/platform/` by `distribution/propagate-rules.sh` |
| Generator | `distribution/generate-capabilities.py` |
| Pre-commit hook | `.claude/hooks/check-capabilities-drift.py` |
| Output file per product | `<product-root>/CAPABILITIES.md` — always in sync with code |

---

## Migration from `platform.platformcapability`

Status: **deprecated, not deleted**. Existing `platform.platformcapability`
rows continue to exist for historical purposes. New writes must go to
`productcore.capability`. A one-time migration copies existing platform rows
into the relevant product's `productcore.capability` (runs once per product
DB); after that, the platform table is read-only + not consulted by any code.

**Removal timeline:** `platform.platformcapability` will be dropped in a
future major release once all code paths are confirmed off of it. Do not add
new consumers in the meantime.

---

## Why this rule is load-bearing

Without it:
- Two modules grow a "list active users" endpoint; one fixes a bug the other
  keeps
- The BRD agent writes a new "audit log" feature because it doesn't see the
  existing one in `novara.audit`
- A settings field is defined twice with different names and defaults
- Adding a product means dragging the full catalog plus manual curation

With it:
- One grep of `CAPABILITIES.md` answers "does this exist?" in two seconds
- A new module declaring an overlapping capability fails pre-commit
- The BRD agent gets a generated capability catalog in its context every run
- Adding TelemetryHub is additive — its capabilities appear in its own
  `CAPABILITIES.md` without touching Workspace's

Protect the primary source. Regenerate the derived. Detect drift. Refuse to
let two sources of truth emerge.
