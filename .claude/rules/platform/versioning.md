# Versioning — CalVer is the Standard (2026-04-21)

Every Novara-authored NuGet package uses **Calendar Versioning** in the format
`YYYY.M.D.N`. Every non-Novara NuGet (Dapper, Npgsql, Scriban, etc.) stays on
its upstream version scheme — we don't rewrite the external ecosystem.

This rule is load-bearing. It governs the Central Package Management file
(`Directory.Packages.props`), every module's output version, customer-facing
release notes, and the hooks that enforce release discipline.

---

## The format

```
YYYY.M.D.N
│    │ │ │
│    │ │ └── Nth release on that day (1, 2, 3 — rarely > 1)
│    │ └──── Day of month (1-31, NOT zero-padded)
│    └────── Month (1-12, NOT zero-padded)
└─────────── Year (4 digits)
```

Examples:
- `2026.4.21.1` — first release on 21 April 2026
- `2026.4.21.2` — hotfix / second release same day
- `2026.12.31.1` — a New Year's Eve release
- `2027.1.1.1` — the first release of the new year (informal "major bump")

NuGet sort order is numeric per segment — `2026.4.21.1 < 2026.4.21.2 < 2026.4.22.1`. Do not zero-pad — `2026.04.21` is technically sortable by NuGet but visually confusing; Novara convention is "no leading zeros on month/day."

---

## Why CalVer

Novara ships continuously. 43+ modules moving weekly. For that cadence, semver's `major.minor.patch` discipline is expensive to maintain correctly (teams have to reason about what counts as a breaking change every release) and the **date information is more useful at operational-time**: when a customer or operator sees a version, they should immediately know:

- **When was this shipped?** — "2026.4.21" tells you April 21.
- **Is this current?** — glance at today's date.
- **How old is my Gateway relative to the module?** — subtract the dates.
- **Which version landed before/after which?** — sort order is chronological.

Semver's major-minor signal matters more for libraries with unknown downstream consumers. Novara's consumers are known (modules + known customer deployments) and pinned via Central Package Management. We don't need the signal-via-version-number; we have a CHANGELOG for that.

---

## Breaking changes — how we communicate them without a major bump

Semver's "1.x → 2.x" forces a conversation. CalVer doesn't. We compensate with discipline:

### 1. CHANGELOG.md entry on every release — **pre-commit enforced**

Every module that publishes a new NuGet version MUST have a corresponding `CHANGELOG.md` entry in the same commit. The pre-commit hook (`.claude/hooks/check-changelog-on-version-bump.py`) rejects commits that bump the csproj `<Version>` without touching `CHANGELOG.md`.

### 2. BREAKING marker in the entry

```markdown
## 2026.4.21.1 — SDK

### BREAKING
- `Guard.NotFoundException(string)` ctor removed — use `NotFoundException(entity, id)` instead.

### Added
- `Guard.Positive(int)` for non-ID positive-int validation.

### Fixed
- Dapper CT overloads now honor request cancellation.
```

Reviewers reject PRs without this structure. The NuGet `ReleaseNotes` metadata echoes the same.

### 3. ADR for any SDK breaking change

The SDK is load-bearing for 43+ modules. Any breaking change to `Novara.Module.SDK` needs an Architecture Decision Record before it ships — see `.claude/architecture/`. The ADR covers: what breaks, who needs to update, migration path, rollout plan.

### 4. Year transitions — informal "major bump" moment

January 1 is the natural time to land aggregated non-trivial surface changes. Not required, but convention: if you have a big refactor in mind, time it to the new year so the year segment acts like a major. Jan 1, 2027 versions (`2027.1.1.1`) naturally read as "new generation."

### 5. Customer comms

When a breaking change ships in a particular `YYYY.M.D.N`, the release announcement includes an explicit "Breaking changes in this release" section. Operators reading the release don't need to guess from the version number — the narrative carries the signal.

---

## Where the numbers live

### In each module's `.csproj`

```xml
<PropertyGroup>
  <PackageId>Novara.Module.Roadmap</PackageId>
  <Version>2026.4.21.1</Version>    <!-- THIS release's version -->
</PropertyGroup>
```

### In the Directory.Packages.props (central pin for DEPENDENCIES)

```xml
<ItemGroup>
  <PackageVersion Include="Novara.Module.SDK"       Version="2026.4.21.1" />
  <PackageVersion Include="Novara.Module.Roadmap"   Version="2026.4.21.1" />
  ...
</ItemGroup>
```

These two must stay in sync — when a module's csproj bumps to `2026.4.22.1`, the central file also updates to that number on next `propagate-packages.sh` run.

---

## Tooling

### `distribution/propagate-packages.sh`
Copies the canonical `Directory.Packages.props.template` from `NovaraSDK/distribution/` into every consumer repo (44 targets). Run after editing the template. `--commit` auto-commits per repo.

### `distribution/migrate-csprojs-to-cpm.py`
One-time sweep. Removes `Version="..."` attributes from `<PackageReference>` nodes for packages that are centrally managed. Idempotent.

### `.claude/hooks/check-changelog-on-version-bump.py`
Pre-commit hook. Rejects any commit that touches `<Version>` in a csproj (package output version) without touching `CHANGELOG.md` in the same commit.

---

## FAQ

**Q: What about a legacy module still on semver like `1.7.0`?**
A: Grandfathered — stays on semver until its next release, at which point it bumps to the current calendar date. Within ~3 months every package should have rolled over.

**Q: My dependency is external — does it have to be CalVer too?**
A: No. External NuGets (Dapper, Npgsql, etc.) use their upstream scheme. Only Novara-authored packages use CalVer. The `Directory.Packages.props` file will have a visible mix — that's expected.

**Q: Can I publish `2026.4.21` (3-segment) without `.N`?**
A: Technically yes — NuGet accepts both. But always include `.N` so multi-release days aren't awkward. Our convention: always 4 segments.

**Q: How do consumers say "I want the latest 2026 release"?**
A: With CPM, they don't need to — the central file pins exact. If you're outside CPM and want a range, use `[2026, 2027)` — explicit year bound.

**Q: What if I genuinely need a semver-style "stable LTS" branch?**
A: Rare. Use the suffix: `2026.4.21.1-lts.2028` means "LTS branch supported through 2028." NuGet handles pre-release suffixes correctly.

**Q: Does CalVer break NuGet Gallery tooling?**
A: No. NuGet has always supported 4-segment versions and arbitrary numeric segments. Tested on GitHub Packages + nuget.org.

---

## When this rule was adopted

2026-04-21. Preceded by the 2026-04-21 Prompt Studio SDK consolidation which exposed the pain of chasing version bumps across 22+ stale csprojs. Central Package Management + CalVer both landed same day as a coherent release-management overhaul.

Related files:
- `.claude/rules/engineering-discipline.md` Gate 6 (build-before-handoff)
- `.claude/tools/verify-session-builds.sh`
- `NovaraSDK/distribution/Directory.Packages.props.template`
- `NovaraSDK/distribution/propagate-packages.sh`
- `NovaraSDK/distribution/migrate-csprojs-to-cpm.py`
