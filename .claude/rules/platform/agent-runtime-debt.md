# Agent runtime — known architectural debt (Phase L incomplete)

This is a deliberate debt marker, not a rule. Recording it so the next engineer
sees the shape of the mess clearly before touching it.

## What's wrong

`Novara.Module.Agentic.Services.AgentRuntimeService.RunAsync` does TWO conceptually
different jobs in one method:

1. **Full session lifecycle**: creates a new `agent_ops.session` row, assembles
   initial context via `IContextRecipeEngine`, runs the agent loop, persists the
   terminal state, publishes events. This is what `AgentSessionService`'s first-
   run path calls.

2. **Just-the-reasoning-body**: runs the perceive-reason-act inner loop for an
   already-created session without touching session lifecycle. This is what
   `AgentLoopStepExecutor` calls from inside `IRecipeRunner`.

Today the same method does both, switched by whether the caller happened to
already create a session row. That coupling:

- Forces `AgentLoopStepExecutor` to duplicate context-assembly work or skip it.
- Made the BRD orchestrator flow (Phase AC) require a special-case "fast path"
  inside `AgentRuntimeService` that detects orchestrator step kinds and delegates
  to `IRecipeRunner` — which is what Phase L was *meant* to do universally.
- Creates a mild recursion smell: `AgentRuntimeService → IRecipeRunner →
  AgentLoopStepExecutor → IAgentRuntime (=AgentRuntimeService)`. Lazy resolution
  via `IServiceProvider` breaks the DI cycle but not the semantic one.

## What Phase L was supposed to finish

- `AgentSessionService.RunLinkedAsync` → `IRecipeRunner.RunAsync` (only path).
- `IRecipeRunner.RunAsync` owns session creation + step dispatch.
- `AgentLoopStepExecutor.ExecuteAsync` owns the inner reasoning loop body.
- `AgentRuntimeService.RunAsync` either shrinks to a thin launcher OR deletes
  entirely — its responsibilities are now split cleanly between session service
  and step executor.

## Why it wasn't finished in Phase AC bug sweep

- Every existing agent (bug_fixer, error_fix, ci_fixer, code_reviewer,
  doc_linter, incident_responder, local_spec, feature_implementer, etc.) runs
  through the inline loop today. Moving that body to `AgentLoopStepExecutor`
  requires carefully preserving: tool-registry wiring, conversation-history
  compaction, token-budget tracking, trace recording, mode-aware behavior, and
  the Phase Y async-first dispatch contract.
- No test coverage exists. A refactor without regression tests can silently
  break any of the 7 production agents and nobody would notice until a user
  hits the broken path.
- The BRD flow works end-to-end TODAY via the "fast path" special case. The
  special case is smelly, but it's verified.

## The right follow-up order

1. Build xunit test project for agentic, add tests that exercise each of the
   7+ agent flows end-to-end with mocked `IAgentReasoning`.
2. Extract inline loop from `AgentRuntimeService` into a private method
   (not yet into `AgentLoopStepExecutor`). Tests still pass.
3. Move that private method's body into `AgentLoopStepExecutor.ExecuteAsync`.
   Tests still pass.
4. Delete the Phase AC "orchestrator fast path" from `AgentRuntimeService`.
   Add `AgentSessionService.RunLinkedAsync` → `IRecipeRunner.RunAsync` direct.
5. Tests still pass = Phase L complete.

## Current workaround location

`AgentRuntimeService.RunAsync` section `// ── 4.5 Orchestrator-recipe fast path`.
Detects recipes with `brd_parse`/`features_upsert`/`wait_for_queue` step kinds
and delegates to `IRecipeRunner`. The inline loop still runs for every other
agent.

This file should be deleted once Phase L is actually complete.
