# Settings Discipline — No Hardcoded Tunables, Manifest-Driven Config

Every tunable value in Novara — every timeout, retry count, URL, API key, cache TTL, threshold, batch size — MUST be declared in a manifest and read through the settings subsystem. Hardcoding these values is banned. The PreToolUse hook (`check-module-boundaries.py`) enforces this at edit time with rules R20–R23 (warnings during ramp-up, blocking after convergence).

## The WHY

Customer deployments survive for years. What was sensible on day one becomes wrong on day 500 — error rates change, user base scales, third-party service quotas shift, security requirements tighten. Settings-driven values let the admin retune WITHOUT a redeploy. Hardcoded values turn every adjustment into a release.

Beyond the operational win, manifest-driven settings also give us:
- **Validation at the boundary** — the validator rejects `maxRetries = -1` before it reaches runtime
- **Audit trail** — every change is recorded with who/when/before/after
- **Upgrade safety** — schema evolution is compared across versions so a tightened constraint doesn't silently break a running customer
- **Self-documenting** — every setting has a label, description, and range; Ops doesn't need to read code to know what a knob does

## Rules

### R20 — No hardcoded timeouts in service code

```csharp
// BANNED
private static readonly TimeSpan Timeout = TimeSpan.FromSeconds(30);
new HttpClient { Timeout = TimeSpan.FromSeconds(30) };
await Task.Delay(5000);

// CORRECT
var timeout = await _settings.GetSecondsAsync(ModuleId, "request.timeoutSeconds", 30);
http.Timeout = timeout;
await Task.Delay(await _settings.GetSecondsAsync(ModuleId, "retry.delaySeconds", 5), ct);
```

Declare a `SettingField` with `Type = Integer`, sensible `Min`/`Max`, `Required = true`, and a clear Description. The code-level fallback (`30` above) matches the manifest `DefaultValue` — these are the same number, kept in sync.

Exception: constants that are NOT tunable (protocol-level values like the JWT bearer scheme string "Bearer", mime types, SDK version strings). If it's a contract with another system, it's a constant, not a setting. Use your judgment; if the value could plausibly vary per deployment, it's a setting.

### R21 — No hardcoded retry counts, concurrency caps, batch sizes

```csharp
// BANNED
private const int MaxRetries = 3;
private const int BatchSize = 100;
for (int i = 0; i < 3; i++) { ... }

// CORRECT
var maxRetries = await _settings.GetIntAsync(ModuleId, "retry.max", 3);
var batchSize = await _settings.GetIntAsync(ModuleId, "ingest.batchSize", 100);
```

Same as R20 — declare with range, read through the settings API.

### R22 — No hardcoded URLs, hostnames, or ports in module code

```csharp
// BANNED
var baseUrl = "http://172.16.17.252:5098";
var smtpServer = "smtp.company.com";

// CORRECT — URL lives on the connector manifest
var ctx = await _resolver.ResolveAsync(ct);
var baseUrl = ctx.BaseUrl;
```

External service URLs belong in a connector's `ConnectorManifest.ConfigFields` (SettingField with `Type = Url`, `Required = true`). Modules call external services through `IConnectorActionInvoker`, never by constructing URLs themselves. That pattern is R3/R4 in the existing architecture-enforcement rules; R22 closes the loophole where the URL sneaks in via a different abstraction.

### R23 — No hardcoded secrets, API keys, tokens

Already R9 in the existing rules. Reinforced: every secret is a `SettingField` with `Sensitive = true`, stored in platform DB, encrypted at rest (pending), masked on read.

## Declaring a setting — the canonical pattern

```csharp
// In your ModuleBase.Manifest:
Settings = new()
{
    new()
    {
        Key = "ingest.batchSize",           // Stable. Never rename — code references it.
        Label = "Ingest batch size",         // UI-friendly.
        Description = "How many rows per ingest batch. Higher = faster import, more memory. " +
                      "Tune up for bulk loads, down if the worker OOMs.",
        Type = SettingFieldTypes.Integer,    // Integer (not Number) — whole numbers only.
        DefaultValue = "100",                 // UI prefill + fallback baseline.
        Min = 1,                              // Inclusive lower bound.
        Max = 10000,                          // Inclusive upper bound.
        Required = true,                      // Empty save fails validation.
        Group = "Performance",                // UI groups settings under this header.
        Order = 10,                           // Sort within the group.
    },
    // …
}
```

## Reading a setting — the canonical pattern

```csharp
public class MyService
{
    private const string ModuleId = "novara.mymodule";   // Single source of truth for this module's id.
    private readonly IModuleSettings _settings;

    public MyService(IModuleSettings settings) { _settings = settings; }

    public async Task IngestAsync(...)
    {
        var batchSize = await _settings.GetIntAsync(ModuleId, "ingest.batchSize", fallback: 100);
        // ↑ fallback matches DefaultValue on the manifest. Intentional redundancy.
        // The settings API is cached per-request — calling this in a tight loop is OK.
        ...
    }
}
```

For singletons (hosted services, circuit breakers) that can't inject Scoped `IModuleSettings`, use `IGatewaySettingsReader` instead. Same rule, different service name, scoped to Gateway-wide tunables (under `novara.gateway` module).

## Upgrade safety rules

When you ship a new version of a module or connector, its manifest may differ from the running version. The Shell runs `SettingSchemaEvolution.Compare(oldManifest, newManifest)` on enable and surfaces findings. You're responsible for making the delta safe:

### NEVER on upgrade

- **Remove a field from the manifest** — orphans admin overrides. Mark `Deprecated = true` with a `DeprecationMessage` for one release, then remove.
- **Change a field's Type** (e.g., `Text` → `Integer`) — stored value becomes unparseable. Add a new key and deprecate the old one.
- **Tighten `Min` / `Max` / `MinLength` / `MaxLength`** — previously-valid overrides now fail validation. Widen only.
- **Flip a field to `Required = true`** when it was optional — deployments without an override suddenly can't save.

### ALWAYS safe on upgrade

- Add new optional fields (Required = false)
- Widen bounds (lower Min, raise Max, shorter MinLength, longer MaxLength)
- Improve `Description` / `Label` / `Group` / `Order`
- Change `DefaultValue` (only affects unset overrides — already-set values are preserved)
- Add new `SettingFieldOption` entries to a select
- Mark a field `Deprecated = true` with a migration path in `DeprecationMessage`

### Deprecation flow

```csharp
new()
{
    Key = "legacy.key",
    Label = "Legacy setting",
    Type = SettingFieldTypes.Integer,
    DefaultValue = "100",
    Deprecated = true,                          // ← added in v1.5
    DeprecationMessage = "Use 'new.key' instead — removed in v2.0.",
}
```

The Admin UI shows deprecated fields with a visible warning. Stored overrides keep working but admins see them tagged. Next release, remove the entry entirely.

## Audit trail — where changes land

Audit follows the scope of the data. `SettingField` changes write through `IAuditService`:

- Product-scoped module settings (Agentic, Issues, etc.) → `audit.log` in product DB
- Platform-scoped module settings (Rules, AppGateway) → `platform.auditlog` in platform DB
- Gateway-wide settings → `platform.auditlog` in platform DB
- Connector instance config → `platform.auditlog` in platform DB

Every entry carries `OldValueJson` + `NewValueJson` (with secrets redacted to "****"), the user who changed it, and a UTC timestamp. The store is append-only — an auditor can answer "what was this value last Tuesday?" from the DB alone.

## When the hook blocks you

The hook is advisory for R20/R21/R22 during the ramp-up period. A WARN gets logged but the edit proceeds. As the codebase converges, we'll flip the severity to BLOCK. Read warnings as "this is drift — fix it now or fix it in your next PR."

If the hook produces a false positive (you have a genuinely non-tunable constant in service code), add a `// no-tune` comment on the line. The hook respects that marker. Don't abuse it — every marker is visible in the PR diff and reviewable.

## Related rules

- **architecture-enforcement.md** — R1–R11 for cross-module boundaries and inline SQL bans
- **architecture-decisions.md** — #11 (Connector Architecture), #12 (Federated Intelligence)
- **coding-standards.md** — General code hygiene, progressive hardening
- **compliance-standards.md** — GDPR, SOC 2, ISO — why audit and no-secrets-in-code matter at the enterprise level
