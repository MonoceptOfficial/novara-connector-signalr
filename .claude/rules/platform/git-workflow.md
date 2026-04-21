---
globs: .claude/fix-issue.md, .github/**
---

# Git & Issue Workflow

## Branching Convention
- All repos (NovaraWorkspaceShell, novara-shell, NovaraModules, NovaraSDK, NovaraPlatformDB) use `master` branch
- Work directly on `master` for now (single developer)
- No slashes in branch names: `fix1`, `feature1` (NOT `fix/1`)
- If branch exists on remote, version it: `fix1v2`, `fix1v3`

## Push/Pull Rules
- ALWAYS explicit: `git push origin master`, `git pull origin master --ff-only`
- NEVER use `HEAD` as remote ref — caused data loss on 2026-04-05
- NEVER rebase against remote — use `--ff-only` for pulls
- Use `/pushall` to push all 3 repos consistently
- If push fails: `git pull origin master --ff-only`. If that fails: ask the user.

## Commits
- Commit messages format: `<action> <subject> (<summary>)`
- Action: `add`, `update`, `remove`, `fix`
- Keep changes focused — don't refactor unrelated code

## Pull Requests
- PR title includes ticket ID
- PR description summarizes what was changed and why
