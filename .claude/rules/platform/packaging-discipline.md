# Packaging discipline — what Novara NuGets MUST and MUST NOT contain

Adopted 2026-04-22 after `Novara.Shell.UI 2026.4.22.1` shipped at 90 MB (expected ~5 MB)
and every module NuGet was 2× expected size. Binding rule for every Novara-authored
NuGet package, regardless of module class.

## Why this rule exists

Two compounding bugs produced 40× bloat:
1. Every module csproj used `<Content Include=".../browser/**/*" Pack="true" />` — a glob
   that sweeps in `.js`, `.js.map`, `.css.map`, `3rdpartylicenses.txt`,
   `prerendered-routes.json`, `stats.json` — everything Angular's production build emits.
2. `NovaraWorkspaceShell/novara-shell/web/public/modules/` is populated by `scripts/build-all-modules.sh` for
   local dev convenience (Gateway serves module remotes from there). Angular's `ng build`
   copies `public/` verbatim into `dist/`. `release-shell-ui.sh` then packs the dist into
   `Novara.Shell.UI` — duplicating every module's federation bundle inside the Shell NuGet.

A full release wave was shipping ~200 MB of artifacts that consumers and CI had to pull.

## The policy — five invariants

### 1. NEVER ship debug source maps

Files matching:
- `*.js.map`
- `*.css.map`
- `*.mjs.map`
- `*.ts.map`
- `*.d.ts.map`

These exist to help debuggers map minified output back to source. They are 3–6× the size
of the actual runtime code and customers never need them. If a customer needs to debug,
they open an issue and we attach maps to the ticket — not ship them in every NuGet.

### 2. NEVER ship raw TypeScript source

Files matching:
- `*/web/**/*.ts`
- `*.d.ts` (unless explicitly intended as a public type contract)

Consumers consume pre-built `.js` chunks. Shipping `.ts` doubles module size without
runtime benefit and leaks authoring-time structure into deployments.

### 3. NEVER ship Angular / build-tool generator exhaust

Files matching:
- `**/3rdpartylicenses.txt`
- `**/prerendered-routes.json`
- `**/stats.json`

Attribution files, prerender manifests, build stats — generated for the developer during
build, serve no purpose at runtime. The LICENSE already covers third-party attribution
at the SOURCE REPOSITORY level; we don't re-ship it with every binary.

### 4. NEVER ship dev-convenience federation staging

Files matching:
- `**/wwwroot/modules/**`

`NovaraWorkspaceShell/novara-shell/web/public/modules/` and `NovaraWorkspaceShell/novara-shell/web/dist/**/wwwroot/modules/` are
populated by `scripts/build-all-modules.sh` so the Gateway serves module remotes from
the Shell during local dev. Each federated module ships its **own** `Novara.Module.X`
NuGet whose Content includes `wwwroot/modules/novara-module-X/`. Packing that content
ALSO inside `Novara.Shell.UI` duplicates every module's bundle — customer deployments
then have two copies on disk for every module.

### 5. Size budgets (informational; hardening later)

| Package class | Budget | Rationale |
|---|---|---|
| `Novara.Module.SDK` | 300 KB | Pure .NET contracts, zero assets |
| `Novara.Module.*` (module NuGets) | 2 MB | DLL + migrations + frontend chunks + module.json |
| `Novara.Shell.Gateway` | 2 MB | Gateway DLL + minimal content |
| `Novara.Shell.UI` | 10 MB | Shell Angular bundle (no modules) |
| `Novara.Modules.Bundle` | 20 MB | Aggregates dependency graph only |
| `Novara.Connector.*` | 500 KB | Thin adapter DLL + manifest |

Packages that exceed their budget are not rejected yet, but will be flagged by the
audit command (planned follow-up). Today's enforcement is via the policy exclusions;
budget enforcement is belt-and-braces for the future.

## How this is enforced — structurally, not per-csproj

**Single source of truth**: `NovaraSDK/build/Novara.Build.targets` declares a Target
(`_NovaraApplyPackagingPolicy`) that runs `BeforeTargets="_GetPackageFiles"`. The Target
iterates `@(Content)` and flips `Pack="false"` on any item whose Identity matches the
invariants above, via MSBuild's regex `IsMatch` on `%(Identity)`.

**Two distribution paths** for the policy to reach every csproj:

1. **CTO workspace**: `Workspace/Directory.Build.targets` auto-imports
   `NovaraSDK/build/Novara.Build.targets` (via the merged monorepo path).
   Every csproj under `Workspace/` gets it automatically through MSBuild's
   directory walking.

2. **Module developer**: `Novara.Build.targets` is packed into the SDK NuGet as
   `build/Novara.Module.SDK.targets`. NuGet auto-imports that file into any project
   that references `Novara.Module.SDK` (convention). So module devs get the policy
   too, without cloning the workspace.

**Non-negotiables**:
- Never inline exclusion rules in individual csproj files — they'll drift. Put rules
  in `Novara.Build.targets` and let them propagate.
- Never use `<Content Include>` with `Pack="true"` and a broad `**/*` glob without
  relying on the central policy. If a new file type should NEVER ship, add it to
  the policy. Never to a specific csproj.

## Why the policy lives in `.targets`, not `.props`

MSBuild evaluates in three phases:

```
Phase 1: Directory.Build.props        (imports BEFORE csproj body)
Phase 2: csproj body                   (declares <Content Include=...> items)
Phase 3: Directory.Build.targets      (imports AFTER csproj body — items exist here)
```

Exclusion rules that look at `%(Identity)` have nothing to match in Phase 1 — items
aren't created yet. The policy only works in Phase 3, hence `.targets`, not `.props`.

## Releasing: how to verify

Before publishing, pack locally and inspect:

```bash
# Pack without pushing
dotnet pack path/to/csproj -c Release -o /tmp/packtest

# Sanity-check contents
unzip -l /tmp/packtest/Novara.Module.X.*.nupkg | awk '/\.map$/ {m+=$1; c++} END {print c, m/1024, "KB of source maps"}'
# Expected: 0 0 KB

# Size within budget?
ls -lh /tmp/packtest/*.nupkg
```

If source maps show up, the policy didn't apply — something broke the import chain.
Check `Workspace/Directory.Build.targets` is present and points at the right path.

## What to do if legitimately needing to ship an excluded file type

Override per-project via explicit `<Content Include=...>` with `Pack="true"` AND an
explicit Identity that doesn't match the exclusion globs. For example, if a module
genuinely needs to ship `stats.json` (unlikely but possible), rename it first:

```xml
<Content Include="public/module-stats.json"
         PackagePath="contentFiles/any/any/"
         Pack="true" />
```

The exclusion regex matches `/stats\.json$/` — `module-stats.json` doesn't match, packs
normally. Document this override with a comment pointing at this rule.

## Related files

- `NovaraSDK/build/Novara.Build.props` — early-phase build config (signing, git metadata)
- `NovaraSDK/build/Novara.Build.targets` — late-phase build config (packaging policy)
- `Workspace/Directory.Build.props` — workspace-wide early import
- `Workspace/Directory.Build.targets` — workspace-wide late import
- `.claude/rules/build-consistency.md` — the one-source-of-truth convention
- `.claude/rules/learned-errors.md` § NUGET_BLOAT_* — the incidents that drove this rule
