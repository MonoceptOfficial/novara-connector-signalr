---
description: Remind developer when editing hooks that exist in sibling Mozart projects
globs:
  - .claude/hooks/**
---

## Shared Hooks Reminder

The hooks in `.claude/hooks/` are infrastructure scripts shared across all Mozart projects.
If you are fixing a bug or improving a hook, remind the developer:

> This hook also exists in the sibling projects (../NovaraWorkspaceShell, ../NovaraModules). Consider updating them too if this change is relevant.

Do NOT auto-copy. Just inform once — the developer decides.
