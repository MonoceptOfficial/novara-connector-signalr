# Feature-Driven Development — Standard Workflow

## Core Principle
Any significant work should be tracked as a Feature in Novara. This applies to ALL products, not just Novara itself.

## When to Create a Feature
- New feature that will take more than 1 session
- Refactoring that touches multiple files/modules
- Bug fix that requires design changes
- Infrastructure change affecting multiple services
- Any work someone else might need to continue

## When NOT to Create a Feature
- Quick bug fix (< 30 minutes)
- Config change
- Documentation-only update

## The Lifecycle
```
Submitted → Elaborating → InDesign → Analyzing → ReadyForExecution → InDevelopment → InReview → Done
```

Gates enforce quality — you can't skip to coding without elaboration, design, and impact analysis.

## Claude Code Behavior

### During /work
- If user describes significant work that isn't a feature yet, suggest: "This sounds like it should be a feature. Want me to create one?"
- Always prefer working on assigned features over ad-hoc work
- Respect the phase — if feature is in Elaborating, don't write code

### During coding
- If you discover the scope is bigger than expected, suggest creating sub-features
- If you find something that should be done differently, add a journal entry
- Track accomplishments for the /park summary

### On completion
- Knowledge loop auto-generates a KB article
- Future features automatically reference past knowledge
- The system gets smarter with every completed feature

## Creating Features via API
```bash
curl -X POST "$API_BASE/roadmap/ideas" \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"productId":PRODUCT_ID,"title":"...","description":"...","category":"..."}'
```

Categories: Feature, Enhancement, Infrastructure, AI, Security, Performance, Research

## Cross-Product Transfer
This pattern works for any product that uses Novara. Each product has its own features, sessions, and knowledge base. The workflow is the same everywhere — only the ProductId changes.
