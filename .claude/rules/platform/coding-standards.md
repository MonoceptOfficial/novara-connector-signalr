---
globs: **/*.cs, **/*.ts, **/*.html, **/*.scss
---

# Coding Standards (All Monocept Projects)

## General
- Read existing code before modifying — understand patterns before changing.
- Follow the existing project conventions (naming, structure, patterns).
- Keep changes focused on the issue — don't refactor unrelated code beyond the scope.
- If frontend and backend both need changes, make both together — never leave one side incomplete.
- **Progressive hardening**: every file you touch gets ONE pre-existing fix (see `progressive-hardening.md`).
- **File intent headers**: every non-trivial file gets a PURPOSE block comment. Add when missing, update when changing architecture.
- **Deprecation markers**: when replacing old code with new, mark the old code `[DEPRECATED]` with what replaces it and when to remove.
- **SP coupling comments**: every Dapper SP call gets a comment showing parameter types and return columns.
- **Known issues inline**: tracked bugs/issues that affect code get `// KNOWN ISSUE #NNN` markers at the affected location.

## Speed & Efficiency
- Use the `codebase-explorer` subagent for initial research before coding.
- Use the `frontend-sync` subagent for parallel cross-repo changes.
- Start with a plan before jumping into code to avoid wrong-direction exploration.
- Make parallel file edits when files are independent.
- Don't over-explore — read only what's needed.
