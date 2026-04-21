# Product vs Module — the firehose test

**Adopted:** 2026-04-21 · binding

When a new capability shows up, the first architectural question is: **does it earn its own Novara product (like TelemetryHub), or does it fold into Workspace as a module?**

Spreading the surface across too many sibling products multiplies maintenance cost (separate gateway, port, CI, deploy target, login path, standards files). Spreading nothing keeps Workspace lean. The answer isn't "always module" or "always new product." It's a test.

## The test

A capability earns **its own product** when **any** of these is true:

1. **Firehose property** — unbounded external data volume that would overwhelm Workspace. 100k+ writes/sec, multi-source ingestion pipelines, schemas we don't control. Example: customer-app telemetry generating 100M spans/day from SDKs we deployed at the edge.

2. **Different primary persona** — users who are a different team than Workspace's primary users (product managers, developers). SREs, ops, security auditors want their own tool, their own alerts, their own retention knobs. Forcing them into the PM tool annoys both groups.

3. **Fundamentally different retention economics** — tiered hot/warm/cold storage, archive to Parquet, different backup cadence, different GDPR export surface. Example: telemetry needs 1yr cold tier; Workspace needs 90d hot.

If **none** of the three is true, the capability is a **module enrichment** inside Workspace (or inside whichever existing product already owns the data).

## Worked examples (2026-04-21)

| Capability | Firehose? | Different persona? | Different retention? | Verdict |
|---|---|---|---|---|
| TelemetryHub | Yes — 100M spans/day from customer edge | Yes — SRE/Ops | Yes — tiered hot/warm/cold/Parquet | **Separate product** (kept) |
| Prompt Studio | No — hundreds of prompts, edits at human pace | No — same PMs | No — same retention | **Module** inside `novara-module-prompts` |
| AgenticHub | No — thousands of sessions/day, bounded by LLM rate limits | No — same devs + PMs | No — same retention | **Module** enrichment of `novara-module-agentic` |

## Why this rule matters

Every additional product means:
- Another gateway, another port, another deployment target
- Another CI pipeline + signed NuGet feed
- Another `.claude/rules/` directory that drifts from canonical
- Another login the customer has to configure (even with SSO)
- Another menu, another mental model for users
- Another set of standards the module-developer team has to track

For TelemetryHub, that cost is justified — the three properties make it an actual different product. For Prompt Studio and AgenticHub, that cost is pure overhead.

## How this intersects with other rules

- **Architecture Decision #28 (Per-Product Isolation):** one product = one database. This rule tells you whether a capability joins an EXISTING product's DB or gets its own.
- **Architecture Decision #11 (Connectors):** a capability that needs to call external services (Python eval harnesses, Node MCP adapters) uses Connectors — the external language runs behind the boundary, the module stays .NET + Dapper.
- **`architecture-lookup.md`:** before writing any new product scaffold, apply this test in § 0 of the spec. If the test fails, the spec should propose module enrichment instead.

## Enforcement

- Any new spec proposing a sibling product must pass all three tests in § 0 of its ADR, with evidence for each.
- Spec review rejects new products that fail the test, with a pointer to the module that should absorb the capability instead.

## Precedent incident

On 2026-04-21 we scaffolded `NovaraAgenticHub/` and `NovaraPromptStudio/` as sibling products. Within the same session we recognized neither passes the test and consolidated both into their respective Workspace modules. The scaffold bytes were cheap; the future maintenance cost would not have been. Redirects live at `D:/NovaraDev/NovaraAgenticHub/README.md` and `D:/NovaraDev/NovaraPromptStudio/README.md`.
