# Enterprise Quality Framework — Zero Tolerance

## Why This Exists
Novara is going to enterprises. A bug in their environment is not an inconvenience — it's a liability. Data loss, incorrect calculations, security gaps, or broken workflows can trigger contractual penalties, legal action, and lost trust that no amount of fixing can recover. Quality is not a feature — it's a survival requirement.

## The Three Pillars

### Pillar 1: Prevent (Before Code Ships)
### Pillar 2: Detect (During and After Changes)
### Pillar 3: Learn (Every Bug Makes the Platform Smarter)

---

## Pillar 1: PREVENT — Pre-Ship Guardrails

Every code change, no matter how small, goes through these checks before it's considered done.

### 1.1 Entity-DB Sync Check
After ANY database column change, verify the full chain:
```
DB Column → Domain Entity property → DTO property → Frontend model property
```
Missing any link = data silently lost. Dapper does NOT warn about unmapped columns.

**Checklist:**
- [ ] New DB column? Add property to Domain entity
- [ ] New entity property? Add to response DTO if user-facing
- [ ] New DTO field? Add to frontend model interface
- [ ] New frontend property? Add to template rendering

### 1.2 Data Flow Verification
For any change that touches data flow, verify with actual requests:
```bash
# Don't just build — HIT THE ENDPOINT
source .claude/db-config.sh && JWT=$(get_jwt)
curl -sk "$API_BASE/the-endpoint" -H "Authorization: Bearer $JWT"
# READ the response. Verify the SPECIFIC field you changed.
```

### 1.3 Impact Radius Assessment
Before committing, answer:
- What OTHER endpoints return this entity? Do they need updates?
- What list views show this data? Will they break?
- What exports/reports include this entity?
- Does the frontend model need the new field?
- Does this change affect the API contract? (Breaking change?)

### 1.4 Regression Check
After fixing a bug, verify:
- The original feature still works end-to-end
- Adjacent features using the same entity/SP still work
- No new errors in the error log (check last 5 min)

---

## Pillar 2: DETECT — Catching Issues Early

### 2.1 Error Log Monitoring (Existing — `error-monitoring.md`)
Before and after every change:
```sql
-- Baseline before work
SELECT COUNT(*) FROM platform.ErrorLog WHERE IsResolved = 0
-- After testing — any NEW errors?
SELECT * FROM platform.ErrorLog WHERE CreatedAtUtc >= DATEADD(MINUTE, -5, GETUTCDATE()) AND IsResolved = 0
```

### 2.2 SP-Entity Drift Detection
Periodically check for columns that exist in the DB but not in the entity:
```sql
-- Columns in product.Issue table
SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'product' AND TABLE_NAME = 'Issue'
-- Compare against properties in Issue.cs
-- Any mismatch = silently lost data
```
This should be part of /deep-scan and /strengthen.

### 2.3 API Contract Validation
Every endpoint's response shape should be verified after entity changes. The response DTO is the contract — if it doesn't have the field, the frontend can't show it.

---

## Pillar 3: LEARN — The Compound Intelligence Loop

This is the most important pillar. Every bug, every fix, every surprise must make the platform permanently smarter.

### 3.1 Bug Classification
Every bug belongs to a CLASS. Fixing one instance is not enough — add a guardrail for the entire class.

**Known Bug Classes:**

| Class | Pattern | Guardrail |
|-------|---------|-----------|
| Entity-DB Mismatch | DB column exists, entity property missing, Dapper drops silently | Entity-DB sync check (1.1) |
| SP Parameter Type | NVARCHAR param for INT column, causes implicit conversion | INT-only for ID params (database-design-principles.md) |
| Missing TenantId | Query returns cross-tenant data | Mandatory TenantId filter (multi-tenancy.md) |
| Silent Catch | Empty catch block hides real error | No empty catches (resilience.md) |
| Frontend Model Drift | API returns field, frontend model doesn't have it | Model sync check with entity |
| SP Not Deployed | Code references SP that doesn't exist on server | Deploy + verify after creating SP |
| SELECT * Fragility | SP returns all columns but entity cherry-picks | Always verify entity has ALL needed properties |

### 3.2 The Learning Entry
After every bug fix, create a learning entry in the Gotchas KB page (slug: `gotchas`):

**Format:**
```
### [Bug Class]: [Specific Instance]
**Found:** [date] during [what work]
**Root cause:** [what was actually wrong]
**Layers broken:** [which layers in the DB→UI chain]
**Fix:** [what was changed]
**Guardrail added:** [what prevents this class of bug from recurring]
**Time wasted:** [how much time was spent before finding root cause]
```

### 3.3 Guardrail Evolution
When a bug class appears for the second time, it gets escalated:
- **First occurrence:** Add to Gotchas KB + inline comment
- **Second occurrence:** Add automated check to /deep-scan or /strengthen
- **Third occurrence:** Add to pre-commit hook or CI pipeline — block deployment

### 3.4 Session Learning Summary
At session end, capture:
- What bugs were found and fixed?
- What NEW bug classes were discovered?
- What guardrails were added?
- What should /deep-scan check for now?

This goes into the session log AND updates relevant KB pages.

---

## The Enterprise Standard

Before any change reaches a customer environment:
1. **Investigation complete** — all 5 layers checked (bug-investigation.md)
2. **Fix verified** — API endpoint hit, response validated (bug-fix-verification.md)
3. **Impact assessed** — adjacent features checked
4. **Error log clean** — no new errors introduced
5. **Learning captured** — bug class identified, guardrail added
6. **KB updated** — gotchas page and relevant system pages current

### Speed vs Quality Decision Matrix

| Scenario | Approach |
|----------|----------|
| Quick typo fix | Fix, verify builds, commit |
| Data flow bug | Full 5-layer investigation → fix ALL layers → verify API response → check impact |
| New feature | Design → implement → verify ALL endpoints → check error logs → impact assessment |
| Enterprise-facing change | All of the above + regression check on adjacent features |

**Default to the more thorough approach.** The cost of a 20-minute verification is nothing compared to the cost of a customer-facing bug.

---

## Accountability Chain

Every change must be traceable:
1. **What changed** — git commit with clear message
2. **Why it changed** — linked to feature or issue in DB
3. **What was verified** — documented in session log
4. **What was learned** — captured in KB
5. **Who approved** — PR review or user confirmation

This is not bureaucracy — it's the evidence trail SOC 2 and ISO 27001 auditors require.
