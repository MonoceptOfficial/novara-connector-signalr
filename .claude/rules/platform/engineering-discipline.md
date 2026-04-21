# Engineering Discipline — Procedural, Not Aspirational

## Why This Exists
Aspirational rules ("do the right thing") get overridden by urgency ("let's ship fast").
Procedural rules can't be overridden — they're gates that block progress until satisfied.
Novara serves enterprises. One bug in their environment is a contractual liability.

## The 5 Gates

Every piece of work must pass through these gates IN ORDER.
You cannot enter Gate N+1 until Gate N is satisfied.

### Gate 1: UNDERSTAND before you code
**Checkpoint:** Can you explain what the existing code does WITHOUT reading it?
- If YES → you're guessing. Read it.
- If NO → good. Read it now, then explain it back.

**Procedure:**
1. Read the existing implementation (if migrating/changing)
2. Read the SP definition from the database (if DB involved)
3. Read the caller (who calls this? what do they expect?)
4. Write a 3-line summary: WHAT it does, HOW it does it, WHAT depends on it
5. Only then write code

**Violation example:** "I'll generate the service from the SP name and description"
**Correct example:** "I read IssueService.cs lines 32-44. It calls UpsertIssue with these exact 16 parameters. I'll copy this call."

### Gate 2: ONE thing at a time
**Checkpoint:** Are you working on exactly ONE deliverable?
- If working on 2+ things → STOP. Finish the first one.

**Procedure:**
1. State what you're building: "I am building the Artifacts module"
2. Do NOT start anything else until Artifacts is committed and verified
3. If you discover something else needs fixing → write it down, don't fix it now
4. Context switching = quality loss. Every time.

**Violation example:** "While building Artifacts, I'll also start Learn and Ship in parallel"
**Correct example:** "Artifacts needs fixing in the Admin module. I'll note it and fix after Artifacts is complete."

### Gate 3: COPY, then modify
**Checkpoint:** Is your new code a modified copy of existing tested code?
- If writing from scratch → STOP. Find what exists and copy it.

**Procedure:**
1. Find the existing implementation
2. Copy it verbatim into the new location
3. Make the MINIMUM changes needed (namespace, imports, types)
4. Diff the original and the copy — the diff should be ONLY namespace/import changes
5. If the diff shows logic changes → justify each one explicitly

**Violation example:** "The monolith service has 443 lines but I'll write a cleaner 200-line version"
**Correct example:** "The monolith service has 443 lines. My module copy has 445 lines (added 2 SP coupling comments). Diff shows only namespace changes."

### Gate 4: VERIFY every path, not just the happy path
**Checkpoint:** Have you tested CREATE, READ, UPDATE, and DELETE?
- If only tested READ → you're 25% done, not 100%

**Procedure:**
1. Test GET list → compare response count with monolith
2. Test GET detail → compare every field with monolith
3. Test POST create → verify row exists in database
4. Test PUT update → verify change persisted
5. Test DELETE → verify soft-deleted
6. Test edge cases → what happens with invalid ID? missing required field?
7. Record the test results (curl commands + responses)

**Violation example:** "54/54 GET endpoints return 200. Module is done."
**Correct example:** "Issues module: GET list=17 items match, GET detail=all fields match, POST create=row in DB with correct Status, PUT update=description changed, DELETE=IsDeleted=1. Module is done."

### Gate 5: SIGN OFF before moving on
**Checkpoint:** Is there written evidence that this work is complete?
- If no evidence → it's not done

**Procedure:**
1. Update MODULE_EXTRACTION_CHECKLIST.md with all boxes checked
2. Write the sign-off line with date and what was verified
3. Commit with message that includes verification evidence
4. Only THEN move to the next task

## Applying This Beyond Code

These gates apply to EVERYTHING, not just module extraction:

### Adding a new feature
1. UNDERSTAND: Read the existing module. What patterns does it use?
2. ONE THING: Build the feature end-to-end before starting another
3. COPY: Base it on an existing similar feature's pattern
4. VERIFY: Test every endpoint, every edge case
5. SIGN OFF: Update the checklist, commit with evidence

### Fixing a bug
1. UNDERSTAND: Trace the bug through all 5 layers (DB→SP→API→Frontend)
2. ONE THING: Fix this bug completely before touching anything else
3. COPY: If the fix exists in a similar place, copy the pattern
4. VERIFY: Prove the fix works AND didn't break adjacent features
5. SIGN OFF: Mark the issue resolved in DB with verification notes

### Refactoring
1. UNDERSTAND: Map every caller, every dependency, every consumer
2. ONE THING: Refactor one component at a time
3. COPY: The new version must pass all existing tests before the old version is removed
4. VERIFY: Every caller still works. Every response is identical.
5. SIGN OFF: The old code is removed ONLY after the new code is verified

## What This Means for the Team

Every pull request must answer:
1. What did you UNDERSTAND before writing this?
2. What ONE thing does this PR do?
3. What did you COPY from, and what did you change?
4. How did you VERIFY it works (show the evidence)?
5. What is the SIGN-OFF (checklist item, test results)?

If a PR can't answer these 5 questions, it's not ready for review.

## Gate 6: HANDOFF tells the truth (added 2026-04-21)

**Why this gate exists:** On 2026-04-21 a session wrote a new Prompt Studio
service (`PromptStudioService.cs`) against an SDK surface that didn't
exist — `Guard.Positive`, `ExecuteProcedureScalarAsync<T>`, a
`NotFoundException(string)` ctor, `ct:` parameters on SDK methods that
never accepted `ct`. The session never ran `dotnet build`. Its handoff
document said **"Phase 1 BACKEND COMPLETE."** The next operator walked
in cold, hit 175 compile errors across six modules, and spent the first
hour of a new session reverse-engineering what happened instead of
moving forward.

The root cause was not the missing SDK surface. It was the lie in the
handoff. That lie poisoned every downstream assumption.

**Checkpoint:** A handoff document that claims "COMPLETE" / "DONE" /
"SHIP-READY" for any project or phase MUST be backed by a clean build
of every `.csproj` the session touched. No exceptions.

**Procedure:**
1. Before writing a handoff section that says "complete", list every
   `.csproj` your session created or edited code in.
2. Run `bash .claude/tools/verify-session-builds.sh <csproj> ...`
   on all of them.
3. Paste the resulting "N/N clean" line into the handoff document as
   evidence. If the script exits non-zero, fix the breakage or rewrite
   the handoff to say "INCOMPLETE — N projects fail to compile, see X".
4. For Angular packages, equivalent: `ng build` must exit 0 before
   calling a federation module complete.
5. For SQL migrations, equivalent: the migration runner must apply the
   script against a throwaway DB with zero errors before calling a
   schema change complete.

**Violation examples (what the 2026-04-21 session did):**
- "Phase 1 BACKEND COMPLETE" in handoff with zero build evidence
- "33 call sites migrated" — none of them verified against the SDK
- Brand-new service file (`PromptStudioService.cs`) never committed and
  never built — handoff silently listed it as shipped

**Correct pattern:**
- "Phase 1 BACKEND COMPLETE — build evidence below"
- "  ✓ Novara.Module.SDK.csproj (0 errors, 772 warnings CS1587)"
- "  ✓ Novara.Shell.Api.csproj (0 errors)"
- "  ✓ Novara.Module.PromptStudio.csproj (0 errors)"
- "  N/N clean via verify-session-builds.sh"

**Why the pre-commit hook R13 didn't catch this:**
R13 only fires on `git commit`. The session in question never committed
the broken file — it was generated, left in the working tree, and the
handoff claimed it shipped. No commit = no hook. This gate closes that
escape hatch by moving the verification to handoff time, not commit time.

## The CTO's Role
- Don't accept "it compiles" as evidence of correctness
- Don't accept "GET works" as evidence of completeness
- Don't accept "agent generated it" as evidence of quality
- DO ask: "Show me the monolith source you copied from"
- DO ask: "Show me the curl output for POST and DELETE"
- DO ask: "Show me the DB row after create"
