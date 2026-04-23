# Observability-first testing — BINDING

**Adopted:** 2026-04-23 · binding from this point forward · replaces any plan for xunit/unit-test projects inside Novara modules.

## The principle

**Novara does not unit-test its own code.** It observes real runs, diffs against baselines, and feeds anomalies back through issues. Real runs of real agents and real API calls in the dev environment ARE the characterization. `session_event`, `trace_*`, `audit.log`, `feature_changeset` rows already capture every observable outcome — the same things tests would assert.

Writing tests that stand up a fake `IAgentReasoning` and mock a fake DB would manufacture thousands of throwaway rows (sessions, events, changesets, artifact links) that pollute the very observability signal we depend on. The cost exceeds the benefit for Novara's scale + evolution speed.

## What replaces tests

| Concern | Test-era answer | Observability-era answer |
|---|---|---|
| "Did this refactor break anything?" | Run xunit, expect green | Dispatch a canary BRD, read its trace, compare against baseline |
| "Does this new feature behave correctly?" | Write a `[Fact]` | Dispatch a real run, inspect traces + changeset row |
| "Is this regression intentional?" | Update the test | Update the baseline trace, explain in commit |
| "Where is this documented?" | The test file | The canary BRD + baseline trace + BRD monitor UI |
| "Can a new developer tell if they broke X?" | Run `dotnet test` | Run `.claude/canaries/run.sh` |

## What MUST exist for this to work (non-negotiable)

If any of these is missing, observability is just data — not a feedback loop.

1. **Canary BRDs.** A curated set of small, known-good BRDs — one per agent class minimum. Stored in `Workspace/Common/.claude/canaries/brds/`. Runnable via `./run.sh`. Baseline traces captured at `baselines/`. Maintained like migrations — reviewable, committed, versioned.
2. **Canary runner script.** Single command dispatches all canaries, waits for completion, collects traces, diffs against baselines, reports pass/fail. Lives at `.claude/canaries/run.sh`.
3. **Baseline regeneration discipline.** When behavior legitimately changes, baseline files update in the same commit as the code change. A baseline change in a PR without an explanation in the commit is a review red flag.
4. **BRD monitor UI.** Live agent runs surfaced visibly — session status, step events, child sessions, traces. Not buried in SQL queries. (See `novara-module-agentic/documents/wireframes/module-brd-monitor.html` for the target.)
5. **Anomaly detection.** Even simple first: "canary run's step event count changed ±2 from baseline" triggers a soft alert. Graduates to pattern detection over time.
6. **Small commits.** Every refactor/feature commit must be independently revertable. Blast radius = one commit. This is the safety belt in place of tests.

If a developer proposes a change that can't be validated via one of the above, they must either build the missing canary FIRST or escalate for an exception.

## Anti-patterns — BANNED

- **Unit test projects in Novara modules.** No `Novara.Module.*.Tests.csproj`. Past scaffolding has been removed. Future scaffolding is blocked.
- **Test-only packages in CPM.** No `xunit`, `NSubstitute`, `FluentAssertions`, `Testcontainers.*` pins in `Workspace/Directory.Packages.props`. If added by accident, pre-commit blocks.
- **Hand-written mocks for agent code.** `Substitute.For<IAgentReasoning>()` would still produce fake reasoning output that pollutes real signal. No mock-driven tests anywhere.
- **"We'll add tests later" promises.** Later never comes; the platform stays untested forever. Either build the canary now or skip it now.

## Scope — what this applies to

- All Novara modules: agentic, roadmap, issues, promptstudio, quality, every current and future.
- Backend C#, frontend Angular, SQL functions — all governed by the same rule.
- Every refactor, every feature, every bug fix.

## Scope — what this does NOT apply to

- The quality module's product feature itself. That module manages **customer** test cases for **customer** products. That's its business domain. Customers write their own scenarios, run their own tests, sign off their own releases — through the quality module UI. Not replaced by this rule.
- Static analysis tools (`.claude/hooks/*`, pre-commit rule checks, etc.). Those are style/architecture enforcement, not unit tests.
- Schema validation. Migrations still have their own integrity contract.

## When this rule is revisited

The triggers to re-evaluate the observability-first stance:

- Multiple concurrent developers touching the same module — regressions overlap, canary dispatches don't scale
- First enterprise customer whose SLA includes agent availability — regression cost exceeds debugging time
- Canary coverage coverage drops below "one per agent class + critical CRUD path"
- Observer agent (future module) fails to catch a regression three times running

At that point, reconsider. Until then: observability-first is the law.

## Related

- `Workspace/Common/.claude/canaries/README.md` — canary format, authoring, runner usage
- `Workspace/Common/.claude/canaries/brds/` — the canary BRDs themselves
- `novara-module-agentic/documents/wireframes/module-brd-monitor.html` — the target observation UI
- `.claude/rules/agent-runtime-debt.md` — the Phase L refactor that validated this approach's feasibility

## Why this is the right call for Novara specifically

Agents are already observable-first. Every dispatch produces rich trace data. Agents evolve weekly (prompts, models, recipes, tools). Tests that lock in last week's behavior become obstacles to this week's legitimate evolution. Observability adapts naturally — when a canary's step count shifts, the baseline updates and the commit explains why.

Long-term this also seeds Novara's own product roadmap: an **observer agent** that watches traces, diffs against learned baselines, raises anomaly issues for fix agents to handle. The test layer doesn't disappear — it transforms into an agent. That's coherent with every other architectural decision Novara has made.
