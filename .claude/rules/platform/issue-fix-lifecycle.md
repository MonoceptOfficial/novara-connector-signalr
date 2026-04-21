# Issue Fix Lifecycle — Database Is the Single Source of Truth

## The Problem
Multiple actors fix bugs: Claude during feature work (progressive hardening), agent sessions
picking from the queue, and human developers. Without coordination, two actors independently
fix the same issue — wasting work and creating merge conflicts.

## The Single Source of Truth: Novara Database

The issue status in `product.Issue` is the ONLY authority on whether a bug is open or fixed.
No local files, no caches, no secondary indexes. Read from the DB, write to the DB.

## Before Fixing: Check the DB

When you spot a known issue in code (via inline `// KNOWN ISSUE #NNN` comment or by recognizing
a pattern from the issues list), check its status before spending time on it:

```bash
# Quick status check
curl -s "$API_BASE/issues/$ISSUE_ID" -H "Authorization: Bearer $JWT" | jq '.data.status'
```

- **Open / Triaged** → safe to fix
- **InProgress** → someone else claimed it, skip
- **Resolved / Closed** → already fixed, just clean up stale inline comment if present

## The Fix Flow: Fix → Mark → Commit

### Step 1: Fix the code
```csharp
// BEFORE: fire-and-forget (KNOWN ISSUE #803)
_ = Task.Run(() => DispatchWorkItem(item));

// AFTER: proper background queue with error logging
await _backgroundQueue.QueueAsync(() => DispatchWorkItem(item));
```

### Step 2: Mark resolved in DB via API
```bash
curl -s -X PUT "$API_BASE/issues/$ISSUE_ID/transition" \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"nextStatus": "Resolved", "comment": "Fixed in commit abc123 during Feature X work"}'
```

### Step 3: Remove inline KNOWN ISSUE comment
The fix IS the code now — git blame tells the story.

### Step 4: Commit with issue reference
```
add Feature X multi-tab workspace + fix #803 fire-and-forget in OrchestratorWorker
```

## How This Prevents Duplicate Work

```
Agent: "Give me next issue"
  → API: SELECT FROM product.Issue WHERE Status IN ('Open', 'Triaged', 'ReadyForAgent')
  → #803 is 'Resolved' → NOT returned
  → Agent gets #786 instead ✓
```

## Race Condition Prevention

If an agent picks an issue, it transitions to "InProgress" atomically:
```sql
UPDATE product.Issue SET Status = 'InProgress', AssigneeUserId = @AgentUserId
WHERE Id = @IssueId AND Status IN ('Open', 'Triaged', 'ReadyForAgent')
```
Claude sees InProgress → skips → no conflict.

## When API Is Not Running

If the API isn't available during local dev:
1. Fix the code anyway (progressive hardening shouldn't be blocked)
2. Reference in commit message: `fix #803`
3. Note in handover: "Mark #803 resolved in DB when API is available"
4. Next /startsession picks this up and marks resolved

## At Session Start: Pull Issues for Context

When starting a session that involves coding, pull open issues for the product to know what's
broken nearby:

```bash
curl -s "$API_BASE/issues?productId=1&status=Open,Triaged&pageSize=50" \
  -H "Authorization: Bearer $JWT" | jq '.data[] | {id, title, status}'
```

This gives you the working context without maintaining a separate file.
