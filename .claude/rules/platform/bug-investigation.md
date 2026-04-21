# Bug Investigation Protocol — DB-Up, Never UI-Down

## The Problem
Novara is a full-stack platform: DB → SP → API → Frontend. When something "doesn't show up" or "data is missing," the root cause could be at ANY layer. Guessing wastes time and leads to wrong fixes.

## The Rule: Verify Each Layer Before Coding

When investigating a bug — especially "data not showing" or "feature not working" — follow this exact sequence. Do NOT skip layers. Do NOT start coding until you know WHERE the break is.

**CRITICAL: Check ALL 5 layers even if you find a break early.** Multiple layers can be broken simultaneously. Finding one break does not mean the others are fine.

### Dapper Gotcha
Dapper maps SQL columns to C# entity properties by name. If the entity class is missing a property, that column is **silently dropped** — no error, no warning. `SELECT *` returning `ContextJson` means nothing if `Issue.cs` has no `ContextJson` property. Always check the Domain entity class when the API returns null for a column that exists in the DB.

### Step 1: DB Schema — Does the column/table exist?
```bash
source .claude/db-config.sh && run_sql "
  SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = 'product' AND TABLE_NAME = 'TheTable'
  ORDER BY ORDINAL_POSITION"
```
**If column is missing → fix is: ALTER TABLE or new column. Stop here.**

### Step 2: SP Definition — Does the SP read/write the column?
```bash
source .claude/db-config.sh && run_sql "
  SELECT OBJECT_DEFINITION(OBJECT_ID('product.TheStoredProcedure'))"
```
Check: Does the INSERT include the column? Does the SELECT return it?
**If SP skips the column → fix is: ALTER the SP. Stop here.**

### Step 3: Actual Data — Is the data in the DB?
```bash
source .claude/db-config.sh && run_sql "
  SELECT TOP 5 Id, TheColumn FROM product.TheTable ORDER BY Id DESC"
```
**If data is NULL/missing → fix is: the write path (SP or API code). Stop here.**

### Step 4: API Response — Does the endpoint return the field?
```bash
source .claude/db-config.sh
JWT=$(get_jwt)
curl -sk "$API_BASE/the-endpoint/123" -H "Authorization: Bearer $JWT" | jq '.data.theField'
```
**If field missing from response → fix is: DTO or service mapping. Stop here.**

### Step 5: Frontend — Does the UI render the field?
Only NOW look at the Angular component. Check:
- Does the model/interface have the property?
- Does the template render it?
- Is there a parsing issue (e.g., JSON string that needs `JSON.parse`)?

## Why This Order Matters
- The database is the source of truth. Start there.
- Each layer is a 30-second check. The full trace takes < 3 minutes.
- Fixing the wrong layer wastes more time than investigating all layers.
- Guessing leads to "fixes" that mask the real problem.

## Anti-Patterns — BANNED
```
# BANNED: Firing off a broad Explore agent to guess at the problem
# BANNED: Reading frontend code first and assuming the backend is broken
# BANNED: Creating new columns/SPs without checking if they already exist
# BANNED: "The SP probably doesn't exist" — CHECK, don't guess
```

## When to Apply
- User reports "X doesn't show up" → full trace
- User reports "I did Y but Z didn't happen" → full trace
- Error in logs → check SP definition + actual data first
- Any data flow bug → full trace

## After Investigation: Verify the Fix
Follow `bug-fix-verification.md`. No fix is complete until verified end-to-end. Curl the API, read the response, verify the specific field. The user must NEVER be the one discovering that a fix doesn't work.
