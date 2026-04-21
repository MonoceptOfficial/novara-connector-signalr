---
globs: "**/*"
---

# Systems-First Thinking (All Novara Development)

## Core Principles

1. **Build for the ecosystem, not just the feature**
   - Every feature should work for ALL products, not just Novara
   - Ask: "How will MozartAdmin use this? How will a future product use this?"
   - If it's product-specific, it goes in a plugin. If it's cross-product, it goes in the SDK.

2. **Design APIs before implementations**
   - Define the ingestion/consumption contract first
   - The contract is the product — implementations can change
   - Support N and N-1 API versions simultaneously

3. **Agent-based architecture**
   - Products install lightweight agents (NuGet: `Novara.Agent`, npm: `@novara/agent`)
   - Agents push data to Novara via REST API
   - Novara never reaches INTO other products — products push OUT
   - Exception: Novara itself uses direct DB (it's the host)

4. **Version everything**
   - Agent SDK follows semver
   - Track which version each product has installed
   - Heartbeat reports version — Novara can alert on outdated agents
   - Breaking changes require MAJOR version bump + migration guide

5. **Configuration flows from Novara to products**
   - Products register with Novara on startup
   - Novara can push config overrides via heartbeat response
   - No redeployment needed to change monitoring thresholds
   - Product Settings in Novara UI controls all product behavior

6. **Data flows from products to Novara**
   - API traces, frontend perf, sessions, errors → Novara ingestion API
   - Batch + async + fire-and-forget — monitoring should never impact product performance
   - Each product identified by ProductKey + AppId

7. **Observability is not optional**
   - Every product MUST have: API health, frontend perf, error logging, session tracking
   - The Novara Agent makes this automatic — 2 lines of code to add
   - If you can't observe it, you can't manage it

## Anti-Patterns to Avoid

- NEVER give products direct write access to Novara's database
- NEVER hardcode Novara's URL in product code (use config)
- NEVER skip versioning on SDK packages
- NEVER make monitoring synchronous (always async, batched, fire-and-forget)
- NEVER assume products are on the same server or network
- NEVER break the ingestion API without a MAJOR version bump

## Database Naming Convention

- Table: `platform.{Entity}` or `product.{Entity}` — PK always `Id INT IDENTITY(1,1)`
- Every row has `AppId NVARCHAR(50)` to identify which product sent it
- This allows all products' data in one table, filterable by product
- Consolidation SPs group by AppId for per-product dashboards
