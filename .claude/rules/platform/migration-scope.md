# Migration Scope — explicit `-- @scope:` header

Every `.sql` migration under `migrations/` MUST declare which DB it targets via an explicit header on the first ~10 lines:

```sql
-- @scope: product
-- Module: Roadmap | Migration: 006 | Purpose: BRD import columns + SP
```

or

```sql
-- @scope: platform
-- Platform: agenthub | Migration: 012 | Purpose: Seed BRDImplementerAgent
```

## Why this exists

Phase AB surfaced a latent bug where modules ship BOTH product-DB migrations (at `migrations/*.sql`) and platform-DB ones (at `migrations/platform/*.sql`), but the runner was executing ALL of them against whichever DB the module's `DbScope` declared. This crashed at least 11 modules on every Gateway boot.

We fixed the runner to route by **content heuristic** (regex looking for `agenthub.` / `platform.` schema refs), but that's brittle — a migration that happens to reference `platform.` in a comment or that uses a cleverly-aliased schema would be misrouted.

The header is the **deterministic source of truth**. The heuristic stays as a fallback for legacy migrations that don't yet have a header.

## Allowed values

| Header | Meaning |
|---|---|
| `-- @scope: product` | Runs ONLY on product DB (per-product database the module belongs to) |
| `-- @scope: platform` | Runs ONLY on platform DB (NovaraPlatformDB — shared catalog / auth / viber) |
| `-- @scope: both` | Runs on EVERY DB pass (rare — only for migrations that legitimately create shared objects in both) |

## Rules

1. **Every NEW migration must carry a header.** First line after the file-purpose comment.
2. **Legacy migrations without a header fall back to the content heuristic.** Don't assume the heuristic will work forever — add headers when you touch the file for any other reason.
3. **Folder convention still works** — `migrations/platform/*.sql` is implicitly platform-scoped even without a header, for back-compat. Prefer the explicit header for new files.
4. **Don't mix scopes in one file.** If a migration needs to touch both DBs, split it into two files.

## How the runner uses it

```
ModuleMigrationRunner.GetEmbeddedMigrations(assembly, isPlatformModule)
  for each embedded resource:
    if whitespace-only → skip
    if header says @scope:both → include in BOTH passes
    else: classify by header | folder | content-heuristic
    return scripts where isPlatformScript == isPlatformModule
```

A module's `DbScope = ModuleDbScope.Platform` causes the runner to open a connection to `NovaraPlatformDB` and include only platform-scoped scripts. `Product` modules open per-product DB and include only product-scoped scripts.

## Anti-patterns

- **DO NOT rely on folder location alone for NEW files.** Use the header.
- **DO NOT add `-- @scope: both` to avoid thinking.** Almost always wrong — pick one.
- **DO NOT write migrations that reference schemas they don't own.** A product-DB migration has no business creating functions in `platform.`.
