# Structured `final_answer` — the compounding contract

When a feature-implementer (or any agent that emits `<final>...</final>`) completes a session, the `final_answer` is the durable record of what happened. This rule defines the SCHEMA that every implementer agent must produce.

**Why:** every downstream piece of the compounding stack depends on this shape:
- `FeatureChangesetEventSubscriber` writes to `roadmap.featurechangeset` from these fields
- `ISharedContextCompactor` pulls gotchas + decisions into the parent BRD's `shared_learnings`
- Aggregation views (`v_gotchafrequency`, `v_decisionfrequency`, `v_patterncandidates`) derive cross-run patterns from these fields
- `LearningsStepExecutor` queries aggregations to inject pre-flight context for the NEXT feature

Free-text summaries break the whole loop. Structured JSON makes it real.

---

## The schema

The agent's `<final>...</final>` payload MUST be a JSON object with these fields. ALL fields are optional EXCEPT `implementationSummary` and `testsRun`.

```json
{
  "implementationSummary": "3-5 sentences describing what was actually built. First-person past tense: 'Added ingest.source table, upsertsource SP, POST /sources endpoint with idempotency via (productid, name).'",

  "filesChanged": [
    {
      "path":         "modules/ingest/api/src/Novara.Module.Ingest/Controllers/SourcesController.cs",
      "action":       "created",
      "linesAdded":   68,
      "linesRemoved": 0,
      "language":    "csharp"
    }
  ],

  "migrationsAdded": [
    "modules/ingest/migrations/002_source_table.sql"
  ],

  "endpointsAdded": [
    "POST /api/v1/products/{productId}/ingest/sources",
    "GET /api/v1/products/{productId}/ingest/sources"
  ],

  "dbObjectsAdded": [
    { "kind": "table",    "name": "ingest.source" },
    { "kind": "function", "name": "ingest.upsertsource", "returns": "INTEGER" },
    { "kind": "index",    "name": "ix_source_product" }
  ],

  "testsAdded": [
    {
      "name":      "SourcesControllerTests.Upsert_validSource_returns201",
      "path":      "tests/Novara.Module.Ingest.Tests.Integration/SourcesControllerTests.cs",
      "type":      "integration",
      "framework": "xunit"
    }
  ],

  "testsRun": [
    { "name": "dotnet build",       "type": "build",       "framework": "dotnet", "status": "pass", "durationMs": 4200 },
    { "name": "Unit tests",          "type": "unit",        "framework": "xunit",  "status": "pass", "count": 12, "durationMs": 1800 },
    { "name": "Integration tests",   "type": "integration", "framework": "xunit",  "status": "pass", "count": 3,  "durationMs": 5600 },
    { "name": "POST /sources smoke", "type": "smoke",       "framework": "curl",   "status": "pass", "evidence": "HTTP 201, {id:42, api_key_preview:abc...}" }
  ],

  "decisions": [
    {
      "title":                "Use SCRAM-SHA-256 for api_key hashing",
      "type":                 "design_decision",
      "rationale":            "pgcrypto supports it natively; matches auth-module pattern; avoids separate crypto lib.",
      "alternativesRejected": ["bcrypt (needs extension)", "plaintext (security)"]
    }
  ],

  "gotchas": [
    {
      "title":            "p_productid must be INT not VARCHAR",
      "details":          "Initially wrote as VARCHAR; integration test caught implicit cast preventing index seek.",
      "bugClassIfKnown":  "SP_PARAM_TYPE_MISMATCH"
    }
  ],

  "nextFeatureHints": [
    "The api_key hash-on-write, plaintext-once return pattern can be reused for webhook-signing keys in feature #8",
    "Source registration is idempotent on (productid, name) — document in SP coupling comment for future callers"
  ],

  "kbPagesToCreate": [
    { "title": "Ingest — Source registration flow", "slug": "ingest-source-registration", "spaceId": 4 }
  ]
}
```

---

## Required field semantics

### `implementationSummary` (string, REQUIRED)
3-5 sentences. First-person past tense. Written for the OPERATOR doing a post-run review, not for the agent itself.

### `testsRun` (array, REQUIRED)
What tests were EXECUTED during the session. Every entry: `{name, type, framework, status, durationMs?, count?, evidence?}`.
- `type`: `build | unit | integration | sp | smoke | e2e | replay | security | performance`
- `status`: `pass | fail | skip`
- `count`: when the single entry represents a test suite with N tests
- `evidence`: for smoke tests, a short string proving the result (e.g., first 100 chars of curl output)

**If no tests ran, agent MUST emit an empty array `[]` with an explanatory gotcha entry:**
```json
"testsRun": [],
"gotchas": [{"title": "No tests executed", "details": "...why...", "bugClassIfKnown": null}]
```

### Optional fields

All other fields default to empty array / null if not applicable. Agent SHOULD populate every applicable field — the more filled in, the richer the changeset row, the better the next feature's context.

---

## Validation

The `AgentLoopStepExecutor` parses `final_answer` at session end. Three outcomes:

| Parse result | Current behavior (template v1.0) | Future (template v1.1) |
|---|---|---|
| Valid JSON matching schema | Proceed | Proceed |
| Valid JSON, missing `implementationSummary` | Warning logged; `implementationSummary` = truncated raw text | Step fails, agent retries |
| Valid JSON, missing `testsRun` | Warning logged; `testsRun` = empty array + synthetic "no tests reported" gotcha | Step fails, agent retries |
| Not valid JSON | Warning logged; entire `final_answer` stored as plaintext in `implementationsummary` column | Step fails, agent retries with schema reminder |

**v1.0 = soft enforcement (warn)**. We tighten to hard-block once agents reliably produce the schema.

---

## Agent prompt additions

The feature-implementer agent's system prompt should include:

```
When producing your <final> answer, respond with ONLY a JSON object
matching this schema:

    { "implementationSummary": "...", "filesChanged": [...], ..., "gotchas": [...] }

Required fields: implementationSummary, testsRun.
See .claude/rules/structured-final-answer.md for the full spec.

Free-text summaries are NOT acceptable — they break the compounding
learning pipeline that every future feature depends on.
```

This addition goes into every agent's platform-level prompt template. Agents that don't emit the schema get logged warnings; operator sees poor audit-trail quality and can nudge the prompt.

---

## What this enables

Because every session produces this structured output:

1. **`roadmap.featurechangeset` row** = the audit trail for one feature attempt. Searchable, comparable, long-lived.
2. **`v_gotchafrequency` + `v_decisionfrequency`** = patterns surfaced across all features. Claude running in another product sees "this gotcha hit 5 other features."
3. **`v_modulehotspots`** = which modules are gnarly. Future features in high-hotspot modules get extra context.
4. **`v_patterncandidates`** = gotchas/decisions seen 3+ times. Ready for promotion to formal rules.
5. **`nextFeatureHints`** = direct pipe into the next sibling feature's context via `ISharedContextCompactor`.
6. **`kbPagesToCreate`** = auto-promotion of learnings to Knowledge Bank after review.

All of this depends on the schema being followed. Agents that freelance break the stack.

---

## Relationship to other Novara docs

- `.claude/rules/capability-registry.md` — capabilities the agent can use
- `.claude/rules/learned-errors.md` — bug classes referenced in `gotchas[].bugClassIfKnown`
- Roadmap migration `008_feature_changeset.sql` — the schema's persistent home
- Roadmap migration `009_feature_changeset_sps.sql` — SPs that write/read changesets
- Roadmap migration `010_feature_changeset_views.sql` — aggregation views that derive from this
- Product Factory Spec P10 (BRD-driven with structured feedback) + P11 (compounded learning) — principles this rule realizes
