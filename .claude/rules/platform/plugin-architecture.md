---
globs: src/Novara.Plugin.*/**/*.cs, src/Novara.Api/Infrastructure/Plugin/**/*.cs
---

# Novara Plugin Architecture Rules

## Naming conventions:
- SDK: `Novara.Plugin.SDK` (never Mozart.Plugin.SDK — that's MozartAdmin)
- Plugin packages: `Novara.Plugin.{Name}` (e.g., Novara.Plugin.Features)
- Manifest IDs: `novara.{name}` lowercase (e.g., novara.features)
- DB tables: per-module schema (e.g., `issues.*`, `roadmap.*`) for product data, `platform.*` for config (never `Plugin_*` — that's MozartAdmin)

## Plugin manifest MUST include:
- Id, Name, Version, Author, Description
- Icon (for UI display)
- Category (Plan/Build/Ship/Run/Learn/Govern)
- MenuItems (sidebar entries with routes)
- Permissions (granular access control)
- Settings (configurable from Admin UI)

## Plugin lifecycle:
Install → OnInstallAsync → OnEnableAsync → (running) → OnDisableAsync → OnUninstallAsync

## Services stay in Application layer:
- Interfaces in `Novara.Application/Interfaces/`
- Implementations in `Novara.Application/Services/`
- Plugin's ConfigureServices() registers them
- This allows host to use services without loading plugin assembly

## NuGet packaging:
- Feed: `nuget.pkg.github.com/MonoceptOfficial`
- Release: `./release.sh "short changelog message"` — one command (preferred)
- Manual: `dotnet pack -c Release -o ./nupkgs` + `dotnet nuget push --source ... --api-key ...`
- Version: **CalVer `YYYY.M.D.N`** (2026-04-21 adopted). Breaking change signal
  via mandatory `CHANGELOG.md` + `BREAKING:` tag, not major-bump. See
  `.claude/rules/versioning.md` for the full policy.
