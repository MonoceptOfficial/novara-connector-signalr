# Build Consistency — One Config, Both Modes

## The Problem
Novara is built two ways depending on who's working:

- **CTO workspace** — every repo cloned side-by-side, `ProjectReference` wires the source
  tree into one solution. Fast source-level debugging. Used to evolve the platform.
- **Module developer** — only one module repo cloned, `PackageReference` pulls the SDK
  from NuGet. Isolated, scalable. Used by 100+ future module developers.

If these two modes have different build rules, the platform drifts. A stamp, a warning
level, a deterministic build flag that works in one mode and not the other creates bugs
that only reproduce for one population of developers.

## The Rule

**All cross-cutting build rules live in ONE file: `NovaraSDK/build/Novara.Build.props`.**

That file is the canonical source of truth for:
- Strong-name assembly signing (dev key; prod uses Azure Trusted Signing)
- Git commit SHA + branch stamping into every assembly
- Build UTC timestamp
- (Future) Deterministic builds, warning levels, nullable defaults, Source Link, etc.

It's imported two ways — same file, no drift:

```
CTO workspace mode                 Module developer mode
(ProjectReference → SDK source)    (PackageReference → SDK NuGet)

     MSBuild walks up                    NuGet installs package
           │                                     │
           ▼                                     ▼
    Workspace/                          module/bin/nuget-cache/
    Directory.Build.props               Novara.Module.SDK/
           │                            build/Novara.Module.SDK.props
           │   ┌──────────────────────────────┘
           ▼   ▼
     NovaraSDK/build/Novara.Build.props  ← ONE file
```

- **CTO workspace**: `D:\NovaraDev\Workspace\Directory.Build.props` is a thin
  `<Import Project="NovaraSDK\build\Novara.Build.props" />` stub. MSBuild auto-imports
  the workspace-root props into every .csproj it finds by walking up the directory
  tree. The props live in the SDK repo (versioned).
- **Module dev**: SDK's csproj packs `NovaraSDK/build/Novara.Build.props` into the
  NuGet as `build/Novara.Module.SDK.props`. NuGet's built-in convention auto-imports
  this into any project that references the SDK package.

## How to add a new cross-cutting build rule

1. **Edit one file:** `NovaraSDK/build/Novara.Build.props`
2. **Commit to NovaraSDK.**
3. **CTO workspace picks it up on next pull** — nothing else to do.
4. **Module developers get it on next SDK NuGet upgrade** — their build auto-imports
   the new version.

## What NOT to do

- DO NOT add `Directory.Build.props` inside `NovaraWorkspaceShell/api/`,
  `NovaraModules/novara-module-*/`, or any individual repo. That creates drift between
  CTO mode and module-dev mode.
- DO NOT inline build properties into individual .csproj files that belong in the
  shared config. If another repo would benefit from the same rule, it belongs in
  the SDK's `Novara.Build.props`.
- DO NOT put the git-stamp Target in both the workspace-root file AND the SDK NuGet —
  one of them would drift. Always one canonical file imported two ways.

## Runtime: reading the stamp

```csharp
using Novara.Module.SDK;

var prov = AssemblyProvenance.Extract(typeof(MyClass).Assembly);
// prov.CommitSha, prov.ShortCommitSha, prov.Branch, prov.BuiltAtUtc, prov.Version
```

In the Gateway, inject `IVersionInfo` to get Gateway + every module's provenance
without touching reflection yourself.

## Why this matters

A 10-year platform gets 100 module developers, 1 CTO workspace, multiple CI pipelines,
customer air-gapped builds, and rebuilds from zip archives for compliance. Every one
of those must stamp the same way. This file convention is the contract that makes
that invariant hold without daily vigilance.
