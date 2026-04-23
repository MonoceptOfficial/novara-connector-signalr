# Extensibility Model — widgets, panels, and per-module schema containment

**Adopted:** 2026-04-23 · binding for every module from this point forward
**Scope:** every Novara module's UI extensibility + data ownership

This rule is binding. Every module built from now on follows it. No retrofit debt accepted — if you skip this in a new module, that module's PRs get rejected at review.

---

## Why this rule exists now

Module development is starting at scale. If we ship five modules with hardcoded pages and then try to introduce widget composition later, we pay 5× the cost and discover incompatibilities at integration time. Introducing from day-one costs ~1 extra hour per module and buys forever extensibility.

The widget model was ratified by **Architecture Decision #17 (Composable Dashboard Surfaces)**. This rule extends it to EVERY observational surface (not just dashboards) and locks in per-module schema ownership so no module writes to a shared catalog table.

---

## The four layers (reminder)

```
Layer 4 · PRESENTATION  — widgets are here. Extensibility ★★★★★
Layer 3 · API           — endpoints + events + SDK. Extensibility ★★★☆☆
Layer 2 · BUSINESS      — C# services. Extensibility ★★☆☆☆
Layer 1 · DATA          — tables + SPs. Extensibility ★☆☆☆☆
```

**CODE declares what CAN be. DB declares what IS.** Agents reason against CODE (Layers 1-3). Humans configure DB (parts of each layer). Widgets are the Layer 4 extension primitive.

---

## Binding rule #0 — default-vs-override split (clarifies containment)

Every widget has TWO pieces of information:

1. **DEFAULT placement** — where this widget goes out of the box (panel, order, size)
2. **OVERRIDE placement** — if an admin has customized it for a specific product / team / user

The self-containment rule precisely:

| Data | Where it lives | Why |
|---|---|---|
| Widget descriptor | **contributing module's** `Module.cs` (CODE) | The module defines what the widget IS |
| Widget DEFAULT placement | **contributing module's** `Module.cs` — inside `WidgetDescriptor.Contributions[]` (CODE) | The module declares where its widgets go by default |
| Widget OVERRIDE (admin customized) | **page-owning module's** `{schema}.widget_layout` (DB) | Because admin was editing "the page," not "the widget" |
| Per-user widget state (collapsed / filter choices) | **page-owning module's** `{schema}.widget_user_state` (DB) | Scoped to the page view |

**Out-of-the-box, no DB writes are required** — every widget has a default placement from its contributor. A module renders correctly the moment it's installed. Only when an admin customizes does a row land in the page-host's `widget_layout`.

If a contributing module is uninstalled:
- Its widgets vanish from the in-memory `IWidgetCatalog` (clean — code removed)
- Its default placements vanish (clean)
- Any orphan override rows in other modules' `widget_layout` referencing its widget_ids are silently skipped by the renderer (graceful degradation)
- A periodic GC task purges orphans (cosmetic cleanup)

**Every module is therefore 100% self-contained** — PromptStudio contains all the widget info it needs in its own `Module.cs` and its own schema. Override rows in another module's schema only exist when an admin has explicitly customized a specific page's layout.

---

## Binding rule #1 — every page-owning module has its own widget schema

Every module that OWNS PAGES must include two tables in its own schema:

```sql
-- {module_schema}.widget_layout
-- Which widgets are placed where, with what overrides, on pages this module owns.
-- Only ROWS FOR OVERRIDES — defaults come from contributing modules' code.
CREATE TABLE {module_schema}.widget_layout (
    id                 BIGSERIAL PRIMARY KEY,
    page_id            VARCHAR(100) NOT NULL,   -- e.g. 'feature-detail', 'dashboard', 'catalog'
    widget_id          VARCHAR(200) NOT NULL,   -- the descriptor id, e.g. 'widget.acme.hipaa'
    panel              VARCHAR(40)  NOT NULL,   -- slot target: 'hero' | 'context_pane' | ...
    sort_order         INTEGER      NOT NULL DEFAULT 100,
    size_rows          INTEGER      NULL,       -- grid sizing (dashboards only)
    size_cols          INTEGER      NULL,
    scope              VARCHAR(20)  NOT NULL,   -- 'product' | 'team' | 'user'
    scope_id           VARCHAR(100) NULL,       -- team id or user id; null for product scope
    visibility_rules   JSONB        NULL,       -- {featureTags:['hipaa'], tier:'enterprise', …}
    is_hidden          BOOLEAN      NOT NULL DEFAULT false,
    -- Drift / reconciliation fields (per rules #7 and #8) --
    source             VARCHAR(20)  NOT NULL DEFAULT 'explicit',  -- explicit | snapshot | migration | imported
    base_default_hash  VARCHAR(64)  NULL,        -- SHA256 of the default at override-create time; enables 3-way merge
    last_reviewed_utc  TIMESTAMPTZ  NULL,        -- admin last confirmed this override is still wanted
    -- Audit --
    created_at_utc     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    modified_at_utc    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    modified_by_user_id INTEGER     NULL,
    UNIQUE(page_id, widget_id, scope, scope_id)
);

CREATE INDEX ix_{module_schema}_widget_layout_page
    ON {module_schema}.widget_layout(page_id, scope, scope_id)
    WHERE is_hidden = false;

-- {module_schema}.widget_user_state
-- Per-user UI state for a widget on a page (collapsed, filter choices, etc.)
CREATE TABLE {module_schema}.widget_user_state (
    id                 BIGSERIAL PRIMARY KEY,
    page_id            VARCHAR(100) NOT NULL,
    widget_id          VARCHAR(200) NOT NULL,
    user_id            INTEGER      NOT NULL,
    state_json         JSONB        NOT NULL DEFAULT '{}'::jsonb,
    modified_at_utc    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE(page_id, widget_id, user_id)
);
```

**Rules:**
- A module ONLY gets these tables if it OWNS at least one page
- The tables live in the module's own schema (e.g. `roadmap.widget_layout`, `promptstudio.widget_layout`)
- **No shared `productcore.widget_catalog` — no cross-schema writes**
- The module's migrations own these tables; module uninstall drops them

---

## Binding rule #2 — widget descriptors are CODE, not DB

Every module that CONTRIBUTES widgets declares them in `ModuleManifest.Widgets[]`. No DB mirror; the code IS the truth.

```csharp
// In the module's Module.cs
public override ModuleManifest Manifest { get; } = new()
{
    Id = "novara.compliance",
    // …other fields…
    Widgets = new()
    {
        new WidgetDescriptor
        {
            Id = "widget.compliance.hipaa",           // unique across platform
            Title = "HIPAA coverage",
            Icon = "🏥",
            Kind = WidgetKind.Table,                   // Decision #17 kinds
            TargetPanels = new[] { "context_pane" },   // which slots this widget fits in
            DataContract = "signal:compliance.feature.hipaa",
            RenderComponent = "HipaaWidgetComponent",   // Angular component name
            DefaultSize = new() { Rows = 3, Cols = 4 },
            Visibility = new WidgetVisibility
            {
                FeatureTags = new[] { "hipaa" },
                EnterpriseTier = EnterpriseTier.Enterprise,
                EmptyState = EmptyStateBehavior.Hide
            },
            Audiences = new[] { WidgetAudience.Security, WidgetAudience.Compliance }
        }
    }
};
```

**Rules:**
- Gateway builds the widget catalog in memory at module-load time
- Agents + services read from the in-memory catalog, never from DB
- Never write widget descriptors to DB — the code file is the authority
- Uninstalling a module removes its widgets from the catalog automatically

---

## Binding rule #3 — widget contribution is decoupled from page ownership

A module that HOSTS a page stores the LAYOUT for that page in its own `widget_layout` table — regardless of which modules CONTRIBUTED the widgets.

| Scenario | Widget descriptor location | Layout row location |
|---|---|---|
| Roadmap owns feature-detail, contributes `widget.roadmap.properties` | `roadmap/Module.cs` | `roadmap.widget_layout` |
| Compliance contributes `widget.compliance.hipaa` to feature-detail | `compliance/Module.cs` | `roadmap.widget_layout` (roadmap owns the page) |
| Agentic contributes `widget.agentic.last-session` to feature-detail | `agentic/Module.cs` | `roadmap.widget_layout` |
| PromptStudio owns catalog page with its own widgets | `promptstudio/Module.cs` | `promptstudio.widget_layout` |

**Rules:**
- Descriptor owned by the module that produces the widget
- Layout owned by the module that hosts the page
- No module ever writes rows to another module's schema
- An uninstalled module's widgets become "orphan widget_id refs" → rendering gracefully skips them (no FK, string reference)

---

## Binding rule #4 — when NOT to use widgets

Widgets are for **observational surfaces** only. Do NOT widgetise:

| Surface type | Use widgets? |
|---|---|
| Dashboard | ✅ Yes (Decision #17 mandates) |
| Detail page (observational) | ✅ Yes — feature detail, issue detail, user detail |
| Overview / landing | ✅ Yes |
| Reports (output) | ✅ Yes |
| Form (create/edit an entity) | ❌ No — domain-specific UX |
| Multi-step wizard | ❌ No — workflow engine |
| Editor / canvas (code, design, diagrams) | ❌ No — specialised tool |
| Navigation / sidebar | ❌ No — fixed information architecture |
| Settings page | ❌ No — structured forms |
| Real-time streaming UI (agent session live view, terminal) | ❌ No |

**Rough rule of thumb:** ~30% of screens are widget-composed (observational). ~70% are purpose-built. Widget architecture ONLY applies to the 30%.

---

## Binding rule #5 — introduce from day one

Every new module, on first creation:

1. Defines at least its ONE or TWO pages it owns in ModuleManifest (`Pages[]`)
2. Declares every widget it ships in `Widgets[]` — even the simplest "Properties" card is a widget
3. Includes migrations for `{module_schema}.widget_layout` + `{module_schema}.widget_user_state`
4. Its page components use the `WidgetHostComponent` (SDK primitive) to render widgets into panel slots — never hand-composed layouts

**No module ships with a hardcoded page layout.** This is the binding commitment.

---

## SDK primitives required (to make this trivial)

These live in `Novara.Module.SDK` and `@novara/shell-sdk`:

### C# (in `Novara.Module.SDK`)

```csharp
// Descriptor types
public class WidgetDescriptor { … }
public enum WidgetKind { KPI, Chart, Table, Heatmap, Timeline, Markdown, Custom }
public class WidgetVisibility { … }

// Already in ModuleManifest:
public class ModuleManifest {
    public List<WidgetDescriptor> Widgets { get; init; } = new();
    // …
}

// New SDK service the Gateway registers at startup:
public interface IWidgetCatalog {
    IEnumerable<WidgetDescriptor> GetAll();
    WidgetDescriptor? GetById(string id);
    IEnumerable<WidgetDescriptor> GetForPanel(string pageId, string panel);
}
```

### Angular (in `@novara/shell-sdk`)

```typescript
// A page uses this to render a panel's worth of widgets:
<nov-widget-host
  pageId="feature-detail"
  panel="context_pane"
  [context]="{ featureId }"
  [productId]="productId">
</nov-widget-host>
```

The host component:
1. Queries the Gateway: "what widgets are in this product's `widget_layout` for this page/panel/scope?"
2. Gets back descriptors + layout overrides
3. Dynamically imports each widget's Angular component from the contributing module's federation bundle
4. Renders in `sort_order`
5. Lazy-loads below-fold widgets via IntersectionObserver
6. Handles the three mandatory render states (populated / empty / unavailable)

Module devs never build a layout component. They just declare widgets + use `<nov-widget-host>` in their pages.

---

## Migration pattern for existing modules

Modules already built pre-rule (roadmap, agentic, promptstudio, issues, codereview, …) have one sprint to migrate:

1. Create `{schema}.widget_layout` + `{schema}.widget_user_state` migrations (reference the template)
2. Convert their existing hardcoded page components to widget descriptors
3. Rebuild pages using `<nov-widget-host>`
4. Commit with message: `refactor(module): adopt widget extensibility model`

Modules not owning pages (e.g. pure service modules) skip 1–3; they only declare `Widgets[]` if they contribute to other pages' panels.

---

## Impact on agents — why this is agent-friendly

Agents reason against the in-memory `IWidgetCatalog`:
- "Which widgets surface on a feature-detail page?" → deterministic
- "What data does widget X fetch?" → deterministic, by DataContract
- "What widget should I emit to surface this finding?" → agent proposes a widget id + descriptor; merge-request adds to a module's manifest

Agents do NOT touch `widget_layout` or `widget_user_state`. Those are human config. Agents always operate against the stable code contract, exactly per the extensibility-model principle.

---

## Binding rule #6 — widget ids never change after first ship

Same discipline as public API versioning. A widget id is a forever-contract. If the widget's shape changes fundamentally:

- Create a NEW widget id (e.g. `widget.foo` → `widget.foo.v2`)
- Old widget id keeps working for ONE release cycle (deprecated, removed next)
- Module author updates `Contributions[]` to point the old id at a deprecation adapter, new id at the real component
- Customer admins get a "widget deprecated" notification with a one-click "switch to new version"

**Never rename, never repurpose.** Customer overrides reference widget ids; breaking this breaks their customizations silently.

## Binding rule #7 — override rows carry provenance

Every row in `{schema}.widget_layout` includes a `source` column:

| source | Meaning | Behavior on default update |
|---|---|---|
| `explicit` | Admin drag-dropped, clicked hide, resized | Keep always. Admin notified if upstream default changed. |
| `snapshot` | System-created to pin a past default (rare, only for specific migrations) | Auto-follow new default silently |
| `migration` | Created by a one-time upgrade migration | Keep (treated like explicit) |
| `imported` | Came from a saved template / shared layout | Notify admin; offer re-import |

Plus a `base_default_hash` column capturing the default at the time the row was created. Enables three-way merge on upgrade.

## Binding rule #8 — three-way merge on default change

When platform / module upgrades change a widget's default, reconciliation engine (Gateway) runs:

| BASE (hash at override create) vs CURRENT DEFAULT | vs OUR OVERRIDE | Action |
|---|---|---|
| BASE == default (unchanged) | whatever | keep OUR (no-op) |
| BASE != default (default changed) | OURS == BASE (admin never touched) | silent follow new default |
| BASE != default | OURS != BASE (admin did customize) | **keep OURS + flag for admin review** |
| widget removed from code | any | orphan; render skip; GC after 90d |
| widget id renamed | any | not allowed per rule #6 |

Reconciliation engine runs on Gateway startup after detecting a module version bump. Admin sees a "Layout changes after upgrade" card on first login with before/after preview + per-row actions (accept / keep / custom-merge).

## Enforcement

- **Pre-commit hook** (`check-module-manifest.py`) — new pages without a corresponding `Widgets[]` declaration fail the hook
- **Module manifest validator** at Gateway startup — rejects a manifest that ships pages without widgets
- **Architecture review** — any PR that adds a hardcoded observational page gets rejected with a pointer to this rule

---

## Related

- `.claude/rules/architecture-decisions.md` **§17 Composable Dashboard Surfaces** — the widget contract this rule extends
- `.claude/rules/settings-discipline.md` — each widget's visibility toggle goes through `IModuleSettings`
- `.claude/rules/capability-registry.md` — widgets are capabilities; the ModuleManifest is the source of truth
- `novara-module-roadmap/documents/FUTURE-VISION.md` — the 85-widget catalogue applying this model to the feature detail page
- `novara-module-roadmap/documents/NOVARA-IS-AN-IDE.md` — why observational surfaces need extensibility
