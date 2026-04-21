# Progressive Hardening — Strengthen Every Iteration

Novara is entering production-grade development. Every code change must leave the codebase stronger than it was found. These rules are BINDING on every session — not aspirational, not "nice to have."

## 1. File Intent Headers — Living Documentation

Every non-trivial file has a block comment header documenting PURPOSE, design decisions, and relationships. These are LIVING documents — not write-once snapshots.

**Rules:**
- **New files** get a header immediately upon creation
- **Modified files**: if the header is missing, add one BEFORE making your change
- **Architecture changes**: update the header in the same commit as the code change
- **Never leave a stale header** — a header that says "uses X" when you just switched to "uses Y" is worse than no header

**Header structure (C#):**
```csharp
/// <summary>
/// [Name] — [Brief Description]
///
/// PURPOSE: [2-3 sentences: what it does and why it exists]
///
/// [HOW IT WORKS / DESIGN DECISIONS / KEY CONSTRAINTS — as needed]
///
/// RELATIONSHIPS: [Key dependencies and consumers]
/// </summary>
```

**Header structure (TypeScript):**
```typescript
/**
 * [Name] — [Brief Description]
 *
 * PURPOSE: [2-3 sentences: what it does and why it exists]
 *
 * [HOW IT WORKS / DESIGN DECISIONS — as needed]
 *
 * RELATIONSHIPS: [Key dependencies and consumers]
 */
```

## 2. Deprecation Markers — Never Silent Replacements

When something is superseded by a better implementation, mark it explicitly. Don't leave old code as a trap for the next developer.

**Pattern:**
```csharp
/// [DEPRECATED] Use ILlmService via LlmGatewayService instead.
/// Kept for: FeatureChatService streaming (gateway doesn't support streaming yet).
/// Remove when: LlmGatewayService supports streaming (#feature-id).
```

**Rules:**
- Every deprecated class/method gets a `[DEPRECATED]` marker in its header
- State WHAT replaces it
- State WHY it's still here (what depends on it)
- State WHEN it can be removed (which feature/condition)
- When you see deprecated code with no marker, add one

## 3. Contract Changelog in DTOs

Request/Response DTOs in the Contracts project are the API surface — changes here break callers. Track field evolution inline.

**Pattern:**
```csharp
/// CHANGELOG:
/// - 2026-04-05: Added ContextJson (replaces per-source columns)
/// - 2026-04-04: Added TrackId (default=1 General)
/// - 2026-03-15: Added Source field (TestMode, Manual, API)
public class CreateIssueRequest { ... }
```

**Rules:**
- When ADDING a field: add a changelog entry
- When REMOVING/RENAMING a field: add a changelog entry + mark as breaking change
- When making a field nullable that was required (or vice versa): add entry
- Only track structural changes, not description tweaks

## 4. SP ↔ Code Coupling Comments

Novara uses Dapper + stored procedures. The parameter contract between C# and SQL is invisible without these comments. Make it visible.

**Pattern:**
```csharp
// SP: product.GetFeaturesByTrack(@TenantId INT, @ProductId INT, @TrackId INT, @Status NVARCHAR, @Page INT, @PageSize INT)
// Returns: Id, Title, Status, AssigneeName, TrackId, CreatedAtUtc + TotalCount via COUNT(*) OVER()
var features = await _db.ExecuteProcedureAsync<Feature>(SpNames.GetFeaturesByTrack, new { ... });
```

**Rules:**
- Every `ExecuteProcedureAsync` / `ExecuteProcedureSingleAsync` call should have a comment showing the SP's parameter signature
- Include parameter TYPES (INT, NVARCHAR, etc.) — this catches the INT vs NVARCHAR mismatch bugs we've hit before
- Include return columns if they map to an entity (helps when SP output changes)
- New SP calls MUST have this comment. Existing calls: add when you touch the file

## 5. Known Issues Inline

Tracked issues that affect code should be marked WHERE they affect it, not just in GitHub. This prevents investigation of known problems and guides fixers to the right spot.

**Pattern:**
```csharp
// KNOWN ISSUE #803: fire-and-forget loses errors silently.
// Fix: Replace with proper background queue when job infrastructure is built.
_ = Task.Run(() => DispatchWorkItem(item));
```

**Rules:**
- When you discover a known issue in code, add an inline comment with the feature/issue number
- Format: `// KNOWN ISSUE #NNN: [one-line description]` + `// Fix: [what needs to happen]`
- When the issue is fixed, REMOVE the comment (don't leave "FIXED" markers — that's git's job)
- When filing a new issue, add the inline marker in the same commit

## 6. "Why Not" Comments on Non-Obvious Decisions

The most valuable comments explain WHY something is done a particular way — especially when the obvious approach was rejected.

**Pattern:**
```csharp
// WHY direct SQL instead of SP: This query joins multiple platform tables in a single call.
// A dedicated SP could be created but inline SQL is acceptable for simple auth lookups.
```

```typescript
// WHY not a route resolver: Product data loads async in ShellComponent, not via resolver,
// because the sidebar needs products before any child route activates.
```

**Rules:**
- Add "WHY" comments when you choose a non-obvious approach
- Add them when you use a workaround for a known limitation
- Add them when the "obvious" approach doesn't work and you've investigated
- Don't explain obvious things — only document surprises and trade-offs

## 7. Progressive Fix: One Improvement Per File You Touch

**THE COMPOUND RULE:** Every time you open a file to make a change, fix ONE pre-existing issue in that file. Not a rewrite — one targeted improvement.

**Priority order for what to fix:**
1. Missing CancellationToken on async method → add it
2. `Task<object>` return type → replace with typed DTO
3. Empty catch block → proper error handling or explicit comment
4. Magic string → SpNames constant or Permissions constant
5. Missing `[Authorize]` or permission check → add it
6. Missing TenantId in query → add it
7. `SELECT *` in inline SQL → list specific columns

**Rules:**
- Don't skip this because "it's not in scope" — it's ALWAYS in scope
- Don't batch 10 fixes — ONE per file, in the same commit as your actual change
- If the file has no issues, don't force one — move on
- Track what you fixed in the commit message: "add feature X + fix missing CancellationToken in Y"
- This applies to both .cs and .ts files
- **If the fix is a tracked issue** (has `// KNOWN ISSUE #NNN` inline or matches a DB issue): follow `issue-fix-lifecycle.md` — check DB status first, fix code, mark resolved via API. Database is the single source of truth — no local issue files.

## Summary: The Hardening Mindset

Every iteration of Novara should be:
- **More documented** — headers added or updated
- **More explicit** — deprecations marked, known issues flagged
- **More traceable** — SP contracts visible, DTO changes logged
- **More correct** — one fix per touched file compounds over time

This is not extra work — it's the standard for production-grade enterprise software.
