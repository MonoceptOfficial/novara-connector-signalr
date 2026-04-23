# Bug Fix Verification — Quality Over Speed

## The Problem
Fixing code without verifying the fix is worse than not fixing at all. It wastes the user's time, erodes trust, and creates a false sense of progress. The user should NEVER be the one discovering that a "fix" doesn't work.

## The Rule: No Fix Is Complete Until Verified End-to-End

Every bug fix MUST go through this verification cycle. No exceptions. Do not declare a fix complete, do not say "refresh and check", do not move on — until YOU have verified it works.

## The Verification Cycle

### Phase 1: Investigate (Before Writing Any Code)
Follow the Bug Investigation Protocol (KB slug: bug-investigation):
1. DB Schema — does the column/table exist?
2. SP Definition — does the SP read/write correctly?
3. Actual Data — is the data in the DB?
4. API Response — does the endpoint return the field?
5. Frontend — does the UI render it?

**Identify ALL broken layers before fixing ANY of them.** A bug that spans 3 layers needs 3 fixes — not 1 fix and a prayer.

### Phase 2: Fix (All Broken Layers)
- Fix every broken layer identified in Phase 1
- If you find the break at layer 3, still verify layers 4 and 5 — they may also need fixes
- Don't assume downstream layers will "just work" because the upstream is fixed

### Phase 3: Verify (MANDATORY — This Is Not Optional)

After fixing, verify each layer you touched, bottom-up:

**Step 1: Build succeeds**
```bash
dotnet build --no-restore 2>&1 | tail -5
```
Not enough on its own, but catches compile errors.

**Step 2: API returns the correct data**
```bash
source .claude/db-config.sh && JWT=$(get_jwt)
curl -sk "$API_BASE/the-endpoint" -H "Authorization: Bearer $JWT"
```
Verify the specific field you fixed is present and has the right value. Don't just check "200 OK" — read the response body.

**Step 3: Frontend compiles**
```bash
cd ../NovaraWorkspaceShell/novara-shell/web && npx ng build --configuration development 2>&1 | tail -5
```

**Step 4: If API is running — test the actual endpoint**
If the API is live (dev server running), hit the real endpoint and verify the response. If the API needs a restart, tell the user and explain what to verify after restart.

**Step 5: Report verification results to the user**
Don't say "should work now." Say:
- "Verified: API now returns contextJson with value {first 50 chars...}"
- "Verified: Angular build passes, Bug Context section renders when contextJson is present"
- "NOT YET VERIFIED: API needs restart to pick up entity change. After restart, hit GET /issues/16 and confirm contextJson is in the response."

### Phase 4: Impact Assessment
Before declaring done, ask:
- What other endpoints use this entity/DTO? Do they also need the new field?
- Are there list views that should show this data (not just the detail view)?
- Are there export/report features that should include this field?
- Could this change break any existing serialization or API contracts?

## Anti-Patterns — BANNED

```
# BANNED: "Fixed. Refresh and check."
# → You must verify before telling the user to check.

# BANNED: Fixing one layer and assuming the rest work
# → Verify every layer in the data flow.

# BANNED: "Build succeeds" as the only verification
# → Build success ≠ feature works. Test the actual data flow.

# BANNED: Declaring done without hitting the API endpoint
# → If you changed backend code, curl the endpoint and read the response.

# BANNED: Fixing frontend without checking what the API returns
# → The frontend can only display what the API sends. Verify the API first.

# BANNED: "The SP uses SELECT * so it returns everything"
# → SELECT * returns to Dapper, which maps to the entity. No property = no data.
```

## The Quality Standard

The user should NEVER:
- Have to come back saying "it still doesn't work"
- Have to verify your fix themselves
- Have to be your QA

If the user reports a bug and you fix it, the next thing they should see is it working. Period.

## When to Apply
- Every bug fix, no matter how small
- Every feature that changes data flow
- Every change to entities, DTOs, SPs, or API endpoints
- Any time you modify how data moves between layers

## Speed vs Quality
Time is not the concern. Quality is the concern. A fix that takes 30 minutes and works is infinitely better than a fix that takes 5 minutes and needs 3 follow-ups. People will judge the platform by whether fixes actually work, not by how fast the code was written.
