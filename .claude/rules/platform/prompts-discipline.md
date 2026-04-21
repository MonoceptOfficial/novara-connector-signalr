# Prompts Discipline — Prompt Studio Is the Single Source

Every AI prompt in every Novara product lives in **`novara-module-promptstudio`** (schema: `promptstudio.*`). Modules consume prompts through the SDK contract — they never inline prompt text, never keep parallel prompt tables, never hardcode fallbacks. Adopted 2026-04-21.

## The rule

### Forbidden

- Inline system-prompt strings (`const string systemPrompt = """..."""`)
- Inline fallback strings on prompt lookups (`?? "You are a helpful assistant..."`) — if PromptStudio doesn't have the key, FAIL LOUD, don't paper over with a hardcoded default
- Parallel prompt tables in other module schemas (`module.someprompt`, `module.prompt_template` etc.)
- New `platform.*` prompt tables (all prompt content is per-product now)
- Seed migrations that INSERT prompt text into anything other than `promptstudio.*`

### Required

- **Content** lives in `promptstudio.prompt_version.content_text`, versioned immutably per (prompt_id, model_provider)
- **Keys** stay as code constants in each module's `Constants/*PromptKeys.cs` file (compile-time safety preserved)
- **Reads** go through `IPromptService.ResolveAsync(key, vars, options)` (SDK) — returns rendered text + model hint + resolved provider
- **Measurement** via `IPromptService.RecordUsageAsync` after every LLM call, OR via the `IPromptStudioBridge` facade which does resolve + generate + record in one call
- **Authoring** via the Prompt Studio UI (routes under `/prompt-studio` in the Shell) or the `POST /api/v1/products/{pid}/prompt-studio/prompts/{id}/versions` endpoint

## The canonical call pattern

### Simple case — one-shot resolve + LLM + record

```csharp
public class MyService
{
    private readonly IPromptStudioBridge _bridge;

    public MyService(IPromptStudioBridge bridge) => _bridge = bridge;

    public async Task<string> GenerateSomethingAsync(string userInput, CancellationToken ct)
    {
        var result = await _bridge.InvokeAsync(
            MyModulePromptKeys.GenerateSomething,   // compile-time key
            variables:    new { user_name = "Alice" },
            userMessage:  userInput,
            options:      new BridgeOptions
            {
                ConsumerType = "module",
                ConsumerId   = "novara.mymodule"
            },
            ct);

        if (!result.Success)
            throw new InvalidOperationException(result.FailureReason ?? "LLM call failed");

        return result.Text;
    }
}
```

### Advanced case — explicit resolve + custom LLM flow + manual record

For chat services, tool-calling, or any flow where you need finer control:

```csharp
var resolved = await _prompts.ResolveAsync(key, vars,
    new ResolveOptions { Provider = "anthropic" }, ct);

if (resolved is null) throw new InvalidOperationException($"No active version for {key}");

var sw = Stopwatch.StartNew();
var result = await _llm.GenerateWithHistoryAsync(
    resolved.RenderedText, history,
    resolved.ModelHint, ct);
sw.Stop();

await _prompts.RecordUsageAsync(new PromptUsageRecord {
    VersionId     = resolved.VersionId,
    SessionId     = currentSessionId,
    ConsumerType  = "agent_definition",
    ConsumerId    = agentName,
    ModelProvider = result.Provider,
    ModelUsed     = result.Model,
    TextTokensIn  = result.InputTokens,
    TextTokensOut = result.OutputTokens,
    CostUsd       = result.CostUsd,
    LatencyMs     = (int)sw.ElapsedMilliseconds,
    Success       = !result.AiUnavailable,
    FailureReason = result.FailureReason
}, ct);
```

## Migration from legacy `ILlmService.GetPromptAsync`

`ILlmService.GetPromptAsync` still exists — it's a deprecated thin wrapper that internally calls `IPromptService.ResolveAsync(key).RenderedText`. Existing callers keep working. When you touch a service, migrate to the bridge pattern above.

Progressive hardening: one caller per PR you touch.

## Why Prompt Studio is the only source

Before 2026-04-21, prompts were scattered across eight places:
- `platform.systemprompt` (48 rows, shared)
- `platform.systempromptvariant` (0 rows, designed-but-unused)
- `platform.systemprompthistory` (21 rows, audit)
- `agent_ops.prompt_template` (per-product, ~10 rows)
- `audit.type.prompttext` (per-product inline overrides)
- Inline `const string` in C# (2 locations)
- 5 `*PromptKeys.cs` files (29 keys, code)
- 4+ seed SQL scripts

Consolidation gains:
- **One measurement surface** — `prompt_usage` records every invocation, enabling cost / latency / success / outcome analytics per version per consumer
- **Per-provider variants** — one key can have Claude-XML-styled content alongside GPT-JSON-styled content; resolver handles fallback
- **Versioning + rollback** — every edit creates an immutable version; activate pointer moves; rollback is one click
- **A/B experiments** — traffic-split experiments scoped per (prompt, provider) with auto-winner detection
- **Agent-run fingerprinting** — `session_id` on every usage row → `v_agent_session_fingerprint` view answers "what did this marathon cost on which prompts"
- **Multi-modal-ready** — `image_slots` column handles the 5% of prompts that need vision input (audio / video / docs normalize to text at Connector boundary before reaching prompts)
- **Per-product isolation** — each product's prompts evolve independently (Decision #28)
- **Cross-product admin view** — Platform Admin can see drift across products via `ICrossModuleMediator`

## What modules must do

| Module | Action |
|---|---|
| Author/own AI prompts (audit, roadmap, thinkboard, designstudio, health, agentic, viber) | Migrate existing `GetPromptAsync` + `GenerateAsync` pairs to `IPromptStudioBridge.InvokeAsync` as you touch each service |
| Agent runtime (agentic) | Phase 1 done (2026-04-21): reads via `IPromptService.ResolveAsync`; legacy fallback kept pending test coverage. Phase 2 after xunit project lands for agentic |
| Audit module | Drop `audit.type.prompttext` column after all call sites migrated. `audit.type.promptkey` (the lookup key) stays |
| Intelligence module | `platform.systemprompt` + variant retired (migration 008). `platform.llmprovider` → per-product relocation pending (task #105) |
| New modules shipping AI features | Start with `IPromptStudioBridge` directly. Declare `*PromptKeys.cs`. Never inline prompt text. |

## Enforcement

- **PR review:** any `GenerateAsync` call with a string literal in the first param → block, request refactor to IPromptStudioBridge
- **Pre-commit hook** (future): grep for `GenerateAsync\(\s*"[^"]{20,}"` → WARN if content looks prompt-like
- **Architecture hook R5:** product-scoped modules cannot inject `IPlatformDbContext` — prevents accidental prompt reads from the retired platform table
- **ADR reference:** `.claude/architecture/novara-prompt-studio-adr.md` has the full contract + retirement plan

## Related rules

- `.claude/rules/architecture-decisions.md` — #11 Connectors, #28 Per-product isolation
- `.claude/rules/product-vs-module.md` — why Prompt Studio is a module, not a sibling product (firehose test)
- `.claude/rules/settings-discipline.md` — complementary rule for tunables (prompts are content; settings are tunables; both consolidated)
- `.claude/rules/learned-errors.md` § MAGIC_STRING_PROMPT_KEY — why keys must be constants
