# Resilience — Highest Priority in Novara

## Core Principle
Novara is an enterprise platform. Data loss, silent failures, and unreachable services are unacceptable. Every feature must be built with resilience from day one — not added later.

## Rules

### 1. Never Lose User Work
- Every save operation must have a fallback chain: API → DB Direct → Local File
- If all save methods fail, ABORT the operation — don't proceed and lose data
- Tell the user explicitly what happened and what to do
- Recovery files must be auto-synced on next session

### 2. Never Fail Silently
- No empty catch blocks: `catch (Exception) { return Array.Empty<object>(); }` is BANNED
- If a service call fails, propagate the error — let the UI show a meaningful message
- Log every failure with context (what was attempted, what failed, what data was involved)
- If a background job fails (auto-park, knowledge loop, journal), log and retry — don't swallow

### 3. Graceful Degradation
- If AI/LLM is unavailable, show the user what's missing and let them proceed manually
- If the database is slow, return cached data with a "stale data" warning
- If a dependent service is down, queue the operation for retry — don't block the user
- Feature flags should allow disabling non-critical features without redeployment

### 4. Explicit Messaging
- When a fallback is used, ALWAYS tell the user: "Saved via {fallback}. Will sync when primary is available."
- When an operation is degraded, ALWAYS explain what's limited and why
- Never pretend everything is fine when it's not

### 5. Retry Strategy
- Transient failures (network timeout, 503): retry 3 times with exponential backoff (1s, 3s, 9s)
- Persistent failures (401, 404, 500): don't retry — surface the error
- Background operations: retry on next trigger (session start, heartbeat, scheduled job)
- Recovery files: check and sync on every session start

### 6. Data Integrity
- Every write operation should be idempotent where possible (upsert pattern)
- Use transactions for multi-step operations (BEGIN TRY/CATCH in SPs)
- Never leave data in a half-written state — if step 3 of 5 fails, roll back steps 1-2
- Validate data at system boundaries (API input), trust internal code

### 7. When Building New Features — Ask Yourself
- What happens if the API is down when this runs?
- What happens if the DB is unreachable?
- What happens if this is called twice with the same data?
- What happens if the user closes the browser mid-operation?
- What happens if this takes 30 seconds instead of 1 second?

If any answer is "data gets lost" or "fails silently" — fix it before shipping.

## When to Flag Resilience Gaps
If you notice ANY of these while working, flag it to the developer immediately:
- A catch block that swallows errors
- A save operation without fallback
- An API call without timeout handling
- A background job without retry logic
- A write operation that isn't idempotent
- User-facing feature that fails without explanation

Say: "Resilience gap found: {description}. This could cause data loss in production. Want me to fix it now or create a feature?"
