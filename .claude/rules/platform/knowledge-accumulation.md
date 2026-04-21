# Knowledge Accumulation — Automatic, Database-Only

## Principle
Every feature developed by Claude automatically generates its own KB page. No manual step.
No markdown files for knowledge. The database is the only brain. It grows smarter every session.

## The Three Knowledge Channels

### 1. Feature KB Page — Auto-Created, Evolves With Development

Every feature gets a companion KB page that IS the documentation. Not written after — written DURING.

**Automatic behavior during feature development:**

```
When starting work on a feature:
  1. Check if KB page exists for this feature (search by title or featureId link)
  2. If not → create it via POST /kb/pages with:
     - SpaceId: the product's default space (or SYS-ARCH for platform features)
     - Title: feature title
     - Content: initial scaffold (what, why, how)
     - Link to feature via slug: feature-{featureId}

During development (after each significant change):
  3. UPDATE the KB page with new version via PUT /kb/pages/{id}:
     - Architecture decisions made
     - How the implementation works
     - Files created/modified and why
     - Integration points with other modules
     - Gotchas discovered

When feature is complete:
  4. Final UPDATE — the page now covers everything:
     - What it does (purpose)
     - How it works (architecture)
     - Key files (entry points)
     - Decisions made and why
     - Known limitations
```

**The KB page content at any point is the COMPLETE picture.** Snapshot model — latest version
contains everything. No need to read history.

**What goes in the KB page vs the journal:**
- KB page: "How multi-tab workspace works" (reference — read to understand)
- Journal: "Apr 5: chose Angular tabs over BrowserView" (timeline — read to see evolution)

### 2. Feature Journals — Timeline of Decisions

Already exists: `product.FeatureJournal` table.

**Write automatically during development:**
- Start of session: "Starting work on [feature]. Current state: [status]."
- Design decision: "Chose X over Y because Z."
- Blocker found: "Discovered [issue]. Created issue #NNN."
- Session end: "Completed [summary]. Remaining: [what's left]."

Journals are append-only timeline entries. They explain HOW we got here.
KB pages explain WHERE we are now.

### 3. System Architecture KB — Cross-Cutting Knowledge

The SYS-ARCH KB space (SpaceId=4) contains platform-wide knowledge pages.

**Update automatically when a feature changes cross-cutting concerns:**
- Feature changes auth flow → update "Authentication & Sessions" page
- Feature adds new desktop service → update "Desktop Architecture" page  
- Feature changes DB pattern → update "Data Layer Architecture" page
- Feature discovers a gotcha → update "Gotchas & Surprises" page

**Rule:** If your feature changes how a system-level thing works, update the relevant
SYS-ARCH page in the same session. Don't leave it for later.

### 4. Issue Context — Link Bugs to Code Areas

When filing issues (via /raise-issues, /strengthen, or inline during development), include
module and affected files in ContextJson:
```json
{"module": "Features", "affectedFiles": ["src/Novara.Application/Services/FeatureService.cs"]}
```

At session start, query open issues for the module you're working on.
Database is the single source of truth for issue state.

## The Automatic Session Loop

```
Session Start:
  → Read handover (git — quick orientation only)
  → GET /kb/pages?spaceId=4 → read relevant SYS-ARCH pages
  → GET /features/{id}/journal → read feature history
  → GET /issues?status=Open&productId=1 → what's broken nearby

During Development (AUTOMATIC — no manual triggers):
  → First code change: create/update feature KB page with initial scaffold
  → Design decision: journal entry + update KB page
  → Gotcha discovered: update Gotchas KB page + journal entry
  → Bug spotted: file issue with ContextJson
  → Bug fixed: mark resolved via API
  → Architecture changed: update relevant SYS-ARCH page
  → Significant milestone: update feature KB page with how it works now

Session End:
  → Final journal entry summarizing session
  → Final KB page update (complete reference for what was built)
  → Handover for git-based quick context
```

## KB Page Template for Features

When creating a feature's KB page, use this structure:

```markdown
## [Feature Title]

### What It Does
[1-2 sentences — the user-facing purpose]

### How It Works
[Architecture: which files, which services, which SPs, which tables]
[Data flow: request → controller → service → SP → response]

### Key Files
- [file path] — [what it does in this feature]
- [file path] — [what it does in this feature]

### Design Decisions
- [Decision]: [What was chosen] because [why]. Alternative was [X] but [reason rejected].

### Integration Points
- [Module/Service]: [How this feature connects to it]

### Known Limitations
- [What doesn't work yet or has constraints]

*Last updated: [date] — [what changed]*
```

## What Stays in Markdown vs Database

| Markdown (.claude/rules/) | Database (KB + Journals + Issues) |
|---------------------------|----------------------------------|
| HOW Claude should behave | WHAT we learned |
| Coding standards | Architecture decisions |
| Git workflow rules | Module knowledge |
| Compliance requirements | Feature documentation |
| Build commands | Bug context and locations |
| (Instructions — versioned in git) | (Intelligence — accumulated in DB) |
