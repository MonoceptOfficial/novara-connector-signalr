# Recursion Safety — Polymorphic Dispatchers, Event Loops, Engine Cycles

## Why This Exists

Novara has several polymorphic dispatchers: step executor registry, tool registry, event bus, cross-module mediator, workflow engine, connector handler registry. Each is a plug-in surface by design — modules register, the engine iterates.

Every one of these surfaces is a potential recursion vector. On 2026-04-18 the agent-session runner exhibited this: `AgentRuntimeService.RunAsync` called `BuildContextAsync` which iterated every step executor including `AgentLoopStepExecutor`, which called `RunAsync` again, which called `BuildContextAsync` again. 6 empty-goal sessions per second for 22 minutes before anyone noticed. See `learned-errors.md` § RUNAWAY_EMPTY_GOAL_SESSIONS.

The fix was explicit: context engines skip lifecycle step kinds. But the underlying discipline generalizes.

## The 3 rules

### R1 — Every polymorphic surface has a CATEGORY per member

When you register a plug-in (step executor, tool, event handler, workflow executor), the registration MUST carry a category the engine understands. The engine filters by category before dispatch.

| Surface | Category examples |
|---|---|
| Step executors | context / lifecycle / terminal |
| Tool registry | read-only / mutating / delegating |
| Event handlers | in-module / cross-module |
| Workflow executors | gate / action / branch |

Bag-of-executors dispatch without category is banned.

### R2 — Engines declare which categories they dispatch

The engine's contract states which categories of plug-in it will call. Any plug-in outside that set is skipped at iteration time, not at plug-in implementation time.

```csharp
// GOOD — engine declares its allowed categories explicitly
private static readonly HashSet<string> LifecycleStepKinds = new(OrdinalIgnoreCase) {
    "session_start", "session_setup", "agent_loop", ...
};

foreach (var step in steps) {
    if (LifecycleStepKinds.Contains(step.StepKind)) continue;  // skip what's out-of-scope
    var executor = registry.Get(step.StepKind);
    await executor.ExecuteAsync(ctx, ct);
}

// BAD — engine dispatches anything registered, trusting plug-ins to be well-behaved
foreach (var step in steps) {
    var executor = registry.Get(step.StepKind);
    await executor.ExecuteAsync(ctx, ct);
}
```

### R3 — Runtime recursion-depth guard on every engine entry point

Even with R1 and R2 in place, a future plug-in could slip through. The last line of defense is an `AsyncLocal<int>` depth counter on any method that transitively dispatches plug-ins. If depth exceeds a small threshold (3–5), log the stack and fail the call.

```csharp
private static readonly AsyncLocal<int> _depth = new();

public async Task<Result> RunAsync(...) {
    if (_depth.Value > 3) {
        _logger.LogError("Recursion depth {D} exceeded in {Method}. Stack:\n{S}",
            _depth.Value, nameof(RunAsync), Environment.StackTrace);
        return Result.Failed("Recursion depth exceeded");
    }
    _depth.Value++;
    try { /* work */ }
    finally { _depth.Value--; }
}
```

This is cheap (1 AsyncLocal read + increment) and caught the runaway within the first iteration once added.

## Detection

### Static — standalone scanner (live now)

A runnable Python scanner lives at `.claude/tools/check-recursion-safety.py`:

```bash
python3 .claude/tools/check-recursion-safety.py              # scan defaults
python3 .claude/tools/check-recursion-safety.py --paths X Y  # scan specific dirs
```

Exit 0 = clean. Exit 1 = violations printed as `{file}:{line}: WARN unfiltered dispatch`. Current workspace scans clean (713 files, 0 violations). Suitable for pre-commit hook + CI.

Regex-based so expect occasional false positives — they're code-review prompts, not compile errors. Skip-list excludes already-audited files (`DbContextRecipeEngine.cs`, `RecipeRunner.cs`, `ModuleLifecycleManager.cs`).

### Static — /deep-scan pattern (Audit module follow-up)

For a proper AST-level check wired into the Audit module's rule engine:

```csharp
// Anti-pattern: foreach over a polymorphic registry, calling ExecuteAsync/HandleAsync
// with no Contains/category-check in the loop body.
foreach (var X in anyField.All)              // or registry.All, registry.GetAll(), etc.
    await X.ExecuteAsync(ctx, ct);          // or X.HandleAsync, X.RunAsync
```

Detection logic (Roslyn):
1. Find `foreach (var X in expr)` where `expr` is a member access to a field named like `*registry*` / `*executors*` / `*handlers*` / `*tools*`
2. Walk the loop body for the first `await X.(ExecuteAsync|HandleAsync|RunAsync|InvokeAsync)(...)` call
3. Walk upward looking for a conditional guard (`if`, `?:`, `switch`) that references a property on `X` (like `X.Kind`, `X.Category`, `X.ModuleId`) OR references `step.Kind` in a Contains/Dictionary lookup
4. If no such guard is found in the loop body before the dispatch call — **warn**
5. Message: `"{file}:{line}: Polymorphic dispatch over '{expr}' without category filter — risk of recursion. See .claude/rules/recursion-safety.md"`

Target: `~/Workspace/NovaraModules/**/Services/**/*.cs` + `~/Workspace/NovaraSDK/**/*.cs`. First PR should expect ~5–15 hits; triage each.

### Runtime — Gateway health probe

Every engine entry point that could recurse registers an `AsyncLocal<int>` depth counter. Gateway health dashboard exposes the max depth seen in the last 5 min per engine. Any value > 2 is surfaced as a yellow indicator; > 5 is red.

### Operational — DB insert-rate alert

Simple guardrail at the DB layer — alert when `agent_ops.session` insert rate exceeds a threshold per agent per minute (default: 20/min). Catches engine recursion, bad webhooks, runaway cron jobs, or a misconfigured CI all at once.

```sql
SELECT agentname, COUNT(*) AS rate_per_min
FROM agent_ops.session
WHERE createdatutc > NOW() - INTERVAL '1 minute'
GROUP BY agentname
HAVING COUNT(*) > 20;
```

Expose via `/api/v1/products/{pid}/agentic/health/session-rate` + a NovaraSignalRHub push.

## When to apply this rule

- Building any new plug-in registry → design categories up front; don't add them later
- Reviewing any `foreach ... ExecuteAsync` pattern → require R2
- Adding any engine entry point that dispatches plug-ins → add R3 (depth guard)
- Writing tests → one test per engine: call with a recipe that exercises every registered category; assert exactly one top-level invocation per user request
