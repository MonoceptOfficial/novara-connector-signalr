# Versioning — Novara CalVer Standard (2026-04-22)

Every Novara-authored package — NuGet, NPM, or anything else we ship —
uses ONE format:

```
YY.M.DN
│  │ ││
│  │ │└── N: release of day (0-9) — MANDATORY, always present
│  │ └─── D: day of month (1-31, no leading zero)
│  └───── Month (1-12, no leading zero)
└──────── Year (2 digits, e.g. 26 = 2026)
```

**Parsing rule:** the last digit is always `N`. Everything before it in the
patch segment is the day. `26.4.110` = April 11 release 0. `26.4.11` =
April 1 release 1. Never bare without N — N=0 is the first release of any
day.

**Examples:**
- `26.4.220` — first release on 22 April 2026
- `26.4.221` — same-day hotfix #1
- `26.4.222` — same-day hotfix #2
- `26.4.10`  — April 1, first release
- `26.4.11`  — April 1, first hotfix
- `26.4.110` — April 11, first release
- `27.1.10`  — January 1 2027, first release (year boundary = major bump)
- `26.12.319` — December 31 2026, hotfix 9 (year-end, N-maxed)

**N is capped at 9.** Novara has never released ten times in one day; this
is a hard cap, not a convention. If you somehow hit 10 same-day releases,
bump the day forward (`26.4.240` skipping `26.4.23.anything`). The
CHANGELOG carries the real date.

**Rules for `^` ranges:**
`^26.4.220` means `>=26.4.220 <27.0.0` — covers all hotfixes same day,
all future days this year, all future months this year. Year boundary =
implicit major bump = consumers must retune their pins. This is the entire
point of CalVer: the version number itself expresses the policy "treat
year changes as major-compatible-breaks."

---

## Why one format, one place

**Simplicity over local-optimum.** NuGet natively supports 4-segment
`YYYY.M.D.N` and NPM strictly allows 3-segment only; for most of the last
year Novara's rules split accordingly — NuGet used 4-seg, NPM used
`YYYY.M.DN` packed. That split caused drift via copy-propagation: a new
module created by copying an existing one would inherit whichever format
the source happened to use.

Converging on `YY.M.DN` for everything means:
- Copy-propagate from any module → the new module is correct by default
- One bump tool handles all package types (`.claude/tools/bump-calver.py`)
- One regex in the sweep (`.claude/tools/version-sweep.py`)
- Releases in CHANGELOG, logs, and UI chrome all line up character-for-character
- Year rollovers at `26 → 27` behave the same for NuGet + NPM consumers

**Why YY not YYYY.** Shorter. Matches Ubuntu's 20-year track record (`24.04`,
`26.04`, etc.). `26` becomes the semver major for range purposes, which
cleanly expresses "year boundary = breaking-until-proven-safe." The 2100
collision concern is theoretical — Novara codebases will not exist in their
current form in 2126. If they do, by then we'll have a migration plan.

**Why N is mandatory.** Without it, `26.4.11` is ambiguous (April 11 vs
April 1 rel 1). With N always emitted, the format is self-describing:
reader knows the last character is the release counter, everything before
is the day. First release of the day = N=0, never bare `YY.M.D`.

---

## Release discipline

Every module that publishes a new version MUST have a corresponding
`CHANGELOG.md` entry in the same commit. The pre-commit hook
(`.claude/hooks/check-changelog-on-version-bump.py`) rejects commits that
bump the csproj `<Version>` or package.json `version` without touching
`CHANGELOG.md`.

### BREAKING marker in the entry

```markdown
## 26.4.220 — SDK

### BREAKING
- `Guard.NotFoundException(string)` ctor removed — use `NotFoundException(entity, id)` instead.

### Added
- `Guard.Positive(int)` for non-ID positive-int validation.

### Fixed
- Dapper CT overloads now honor request cancellation.
```

### ADR for any SDK breaking change

The SDK is load-bearing for 43+ modules. Any breaking change to
`Novara.Module.SDK` needs an Architecture Decision Record before it ships
— see `.claude/architecture/`. The ADR covers: what breaks, who needs to
update, migration path, rollout plan.

### Year transitions — informal "major bump" moment

January 1 is the natural time to land aggregated non-trivial surface
changes. Not required, but convention: if you have a big refactor in
mind, time it to the new year so the year segment acts like a major.
Jan 1, 2027 versions (`27.1.10`) naturally read as "new generation."

### Customer comms

When a breaking change ships in a particular `YY.M.DN`, the release
announcement includes an explicit "Breaking changes in this release"
section. Operators reading the release don't need to guess from the
version number — the narrative carries the signal.

---

## Where the numbers live

### In each module's `.csproj`

```xml
<PropertyGroup>
  <PackageId>Novara.Module.Roadmap</PackageId>
  <Version>26.4.220</Version>
</PropertyGroup>
```

### In the Directory.Packages.props (central pin for dependencies)

```xml
<ItemGroup>
  <PackageVersion Include="Novara.Module.SDK"       Version="26.4.220" />
  <PackageVersion Include="Novara.Module.Roadmap"   Version="26.4.220" />
  ...
</ItemGroup>
```

### In each NPM `package.json`

```json
{
  "name": "@novara/shell-sdk",
  "version": "26.4.220",
  "peerDependencies": {
    "@novara/bug-capture-core": "^26.4.220"
  }
}
```

All three must stay in sync — when a package's output version bumps,
all consumer references update too. Use
`.claude/tools/bump-calver.py` to walk the workspace and apply the bump
uniformly (both `.csproj` and `package.json`, internal deps included).

---

## Tooling

### `.claude/tools/bump-calver.py`
Unified bumper. Computes today's `YY.M.DN`, auto-increments N if today's
version already exists in any package, rewrites both `package.json` and
`.csproj` files, updates internal Novara deps to `^YY.M.DN`.

```bash
python3 .claude/tools/bump-calver.py               # dry-run
python3 .claude/tools/bump-calver.py --apply       # apply
python3 .claude/tools/bump-calver.py --release 1   # force N=1 for a hotfix
```

### `.claude/tools/version-sweep.py`
Drift detection. Inventories every Novara-authored package and exits
non-zero if any is on semver OR bare `YY.M.D` without N. Suitable for CI.

```bash
python3 .claude/tools/version-sweep.py
```

### `.claude/hooks/check-changelog-on-version-bump.py`
Pre-commit hook. Rejects commits that bump `<Version>` or package.json
`version` without touching `CHANGELOG.md`.

### `NovaraSDK/distribution/release-module.sh` / `release.sh`
Per-repo release scripts. Compute `YY.M.DN` internally, bump csproj +
changelog, build, pack, publish, propagate central template, commit,
push. One command per release.

---

## FAQ

**Q: What about legacy modules still on semver like `1.7.0`?**
A: Grandfathered — stays on semver until its next release, at which point
it bumps to today's CalVer.

**Q: My dependency is external (Dapper, Angular, rxjs) — does it have to
be CalVer too?**
A: No. External packages use their upstream scheme. Only Novara-authored
packages (anything with `Novara.` prefix in NuGet, `@novara/` scope in
NPM) use CalVer. `Directory.Packages.props` will have a visible mix —
that's expected.

**Q: Can I publish `26.4.22` (3-segment without N) on NuGet since NuGet
doesn't require N?**
A: No. Single Novara standard. Always emit N, even on NuGet. Keeps
copy-propagation clean.

**Q: What if I genuinely need a semver-style "stable LTS" branch?**
A: Rare. Use the pre-release suffix: `26.4.220-lts.2028` means "LTS
branch supported through 2028." NuGet and NPM both handle pre-release
suffixes correctly.

**Q: Does CalVer break NuGet Gallery or npm registry tooling?**
A: No. Both have always supported arbitrary numeric version segments.
Tested on GitHub Packages and npmjs.com.

---

## Related files
- `.claude/rules/engineering-discipline.md` Gate 6 (build-before-handoff)
- `.claude/tools/verify-session-builds.sh`
- `NovaraSDK/distribution/Directory.Packages.props.template`
- `NovaraSDK/distribution/propagate-packages.sh`
- `NovaraSDK/distribution/release-module.sh`
- `.claude/tools/bump-calver.py`
- `.claude/tools/version-sweep.py`
