# Module Extraction — BINDING Rules (Learned from 2026-04-08 Failure)

## What Failed
Agents generated 17 module services from descriptions instead of copying monolith code.
Result: 40+ SP mismatches, wrong method signatures, missing methods, wrong entity fields.
Breadth-first approach (all 17 modules at once) left every module incomplete.
Every fix was "make it match the monolith" — the monolith is the ONLY valid source.

## The ONLY Correct Approach: One Module, Fully Complete, Then Next

### Step 1: Inventory (before writing any code)
For the target module, extract from monolith:
- Every controller endpoint (route, HTTP method, parameters)
- Every service method (exact signature, SP called, Dapper pattern used)
- Every SP with exact params from DB: `SELECT PARAMETER_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.PARAMETERS WHERE SPECIFIC_NAME='X'`
- Every entity class with all properties
- Every request/response DTO

### Step 2: COPY (not generate, not rewrite, not "improve")
For each monolith file, create module version by copying and changing ONLY:
- Namespace
- `IDbContext` → `IModuleDbContext`
- `SpNames.X` → `ModuleSpNames.X`
- `ControllerBase` → `ModuleBaseController`
- `[Route("api/v1/X")]` → `[ModuleRoute("X")]`

NOTHING ELSE CHANGES. Same method signatures. Same parameters. Same Dapper patterns.
Same return types. Same error handling. Copy. Paste. Find-replace namespace. Done.

### Step 3: Build — 0 errors

### Step 4: Test EVERY endpoint against monolith
- Start Shell + module
- GET every list endpoint → compare count + fields with monolith
- GET every detail endpoint → compare field-by-field
- POST create → verify in DB, compare with monolith create
- PUT update → verify changed, compare with monolith update
- DELETE → verify soft-deleted
- Any special operations (transition, vote, etc.)
- ALL must match monolith response

### Step 5: Commit ONLY after Step 4 passes completely

### Step 6: Move to next module

## Module Order
1. Issues (already correct)
2. Artifacts
3. Learn (KB + Reports)
4. Ship
5. Run
6. Collaborate
7. Observe
8. Admin
9. Think
10. Build
11. Test
12. Review
13. Plan (LAST — most coupled)

## NEVER
- Never delegate service/controller writing to agents
- Never generate code from descriptions
- Never do two modules in parallel
- Never say "done" without testing write operations
- Never decommission monolith until ALL modules verified
- Never assume SP names/params — always check INFORMATION_SCHEMA
- Never change method signatures from what the monolith has
