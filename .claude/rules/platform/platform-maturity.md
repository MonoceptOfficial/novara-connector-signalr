# Platform Maturity — Building for the Next 5 Years

These are architectural investments that compound over time. Not all are urgent — but each one should be considered when building new features. When a new feature naturally touches one of these areas, build it right the first time.

## 1. Self-Aware Platform (Novara Monitors Novara)

Novara should know its own health without humans checking. This means:

**Health Score per Module:**
Every module (Features, Issues, KB, Collaboration, etc.) should have an automated health score:
- API response time P95 < 500ms
- Error rate < 0.1%
- SP execution time P95 < 200ms
- Stale data detection (entities not updated in expected timeframes)

**Build this into every new feature:**
When creating a new endpoint, also create its health check assertion:
```csharp
// In the service, not the controller
public async Task<HealthCheckResult> CheckHealthAsync()
{
    // Can we reach the SP? Does it return within 200ms? Is the data reasonable?
}
```

**Why:** Enterprise customers expect an SLA. You can't guarantee an SLA without automated monitoring.

## 2. Schema Migration System (Non-Negotiable for Customers)

Tracked as #778 but deserves emphasis: without a migration system, every customer upgrade is manual SQL work. This blocks:
- Self-service upgrades
- Automated CI/CD
- Multiple environment promotion (dev → staging → prod)

**The investment:** DbUp or FluentMigrator with versioned migration scripts. Run on startup. Idempotent. Reversible where possible.

**Rule for new DB changes:** Every table/column/SP change MUST have a corresponding migration script. No more ad-hoc SQL.

## 3. API Versioning (Before the Second Customer)

Once two customers are running different versions, API compatibility matters.

**Minimum viable approach:**
- Route prefix already includes v1: `/api/v1/...`
- Adding fields to responses is non-breaking
- Removing/renaming fields is breaking → requires `/api/v2/...`
- Support N and N-1 simultaneously (v1 and v2 both active)
- Version header in responses: `X-Novara-Api-Version: 1.4.2`

**Rule for new endpoints:** Every new endpoint goes in v1 unless it breaks an existing contract.

## 4. Feature Flags (Hide What's Not Ready)

Tracked as a concept in architecture-decisions.md but not implemented. Without this:
- Incomplete features are visible to customers
- Can't do trunk-based development safely
- Can't A/B test or gradual rollout

**Minimum viable approach:**
```csharp
// In service layer (not controller)
if (!await _featureFlags.IsEnabledAsync("thinkboard", tenantId))
    throw new BusinessRuleException("ThinkBoard is not enabled for your organization.");
```
Feature flags stored in `platform.ProductSetting` with key pattern `feature:{name}:enabled`.

## 5. Automated Contract Validation

The API surface is the product. Breaking it silently is the fastest way to lose customer trust.

**What to build:**
- Generate OpenAPI spec from controllers on every build
- Diff current spec against last release spec
- Flag breaking changes (removed endpoints, renamed fields, changed types)
- Block deployment if breaking change detected without version bump

**When:** Before the second customer deploys. After that, it's too late.

## 6. Structured Error Taxonomy

Right now errors are: ValidationException, NotFoundException, BusinessRuleException, generic Exception. For enterprise customers, errors need to be machine-parseable:

```json
{
  "error": {
    "code": "FEATURE_LOCKED",
    "message": "This feature is currently being edited by another Viber session.",
    "details": { "lockOwner": "agent-1", "lockedSince": "2026-04-05T10:30:00Z" },
    "helpUrl": "https://docs.novara.io/errors/FEATURE_LOCKED"
  }
}
```

**Why:** Customer support automation, customer-built integrations, and API consumers need stable error codes, not message string matching.

## 7. Idempotency Keys on All Write Endpoints

Architecture-decisions.md mentions this but it's not implemented. Every POST/PUT should accept an optional `X-Idempotency-Key` header. Same key = same response, no duplicate creation.

**Why this matters NOW:** Desktop offline sync queues writes and replays them. Without idempotency, a network retry creates duplicate features/issues/comments.

## 8. Tenant Data Export and Portability

GDPR Article 20 requires data portability. Enterprise customers will ask "can I export all my data?"

**What to build:**
- `GET /api/v1/admin/export?format=json` → full tenant data dump
- `GET /api/v1/admin/export?format=csv&entity=features` → per-entity CSV
- Scheduled export job (nightly backup to customer's blob storage)

**When:** Before any EU customer. After that, it's a compliance violation.

## 9. Rate Limiting and Abuse Prevention

The compliance rules mention rate limiting but it's not implemented. For enterprise:
- Per-user: 100 req/min (prevents runaway scripts)
- Per-tenant: 1000 req/min (prevents one tenant starving others in SaaS shared)
- Per-endpoint: AI endpoints get lower limits (expensive API calls)

Use `AspNetCoreRateLimit` NuGet package — drop-in middleware, configurable per-route.

## 10. Observability Pipeline (Traces → Insights → Actions)

The monitoring plugin captures raw data (request traces, frontend perf, error logs). The next level is automated insights:

- **Anomaly detection**: "Error rate for /features endpoint jumped 400% in the last hour"
- **Correlation**: "Slow response times correlate with this SP executing > 2s"
- **Prediction**: "At current growth rate, this table will exceed 1M rows in 3 weeks — add an index"

This is the "predictive intelligence" in the North Star vision. Start with simple threshold alerts, evolve to pattern detection.

## Priority Order

For the next development phase, in order of impact:
1. **Schema migration system (#778)** — blocks customer upgrades
2. **Feature flags** — blocks safe deployment of incomplete features
3. **BU isolation (#772)** — blocks multi-BU customers (SECURITY)
4. **Idempotency keys** — blocks reliable desktop sync
5. **Rate limiting** — blocks multi-tenant SaaS safety
6. **API versioning** — blocks second customer deployment
7. **Error taxonomy** — blocks enterprise integration quality
8. **Health scoring** — blocks SLA guarantees
9. **Contract validation** — blocks CI/CD confidence
10. **Data export** — blocks EU customer compliance
