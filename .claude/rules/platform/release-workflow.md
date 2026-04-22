# Release Workflow — How to Publish a Novara Module

This rule is binding for **every release of every Novara package**, whether
initiated by a human developer, a CI workflow, or Claude Code. Releases are
the one operation that's irreversible — once `Novara.Module.X 26.4.210`
is on the NuGet feed, it stays there forever. Getting this right matters.

---

## The one-command release

Every module repo ships `release.sh` at its root (propagated from
`NovaraSDK/distribution/release-module.sh`). From inside the module's
working tree:

```bash
# Minimal form — required CHANGELOG message
./release.sh "short description of the change"

# Typed sections — Added, Fixed, Changed, Removed, Deprecated,
# Security, BREAKING
./release.sh --added "Guard.Positive() overload for long"
./release.sh --fixed "Dapper CT now cancels in-flight queries"
./release.sh --breaking "removed NotFoundException(string) ctor — use (entity, id)"

# Dry run — see the plan without changing anything
./release.sh --dry-run "test release"
```

### What the script does, in order

1. **Discovers** the module's primary csproj (`api/src/Novara.Module.*/*.csproj`)
2. **Reads** current `<PackageId>` + `<Version>`
3. **Computes** next CalVer: today's `YYYY.M.D.N` (increments `N` if a
   release already shipped today)
4. **Bumps** the csproj `<Version>` to the new CalVer
5. **Prepends** a `CHANGELOG.md` entry with the typed section
6. **Builds** Release — aborts on any error (rolls back csproj + CHANGELOG)
7. **Packs** the NuGet to `D:/NovaraDev/LocalNuGet/`
8. **Pushes** the NuGet to `nuget.pkg.github.com/MonoceptOfficial` using
   `$GITHUB_TOKEN`
9. **Updates** the central `Directory.Packages.props.template` in NovaraSDK
   (if SDK is a sibling clone) — pins the new version for all consumers
10. **Propagates** the updated template to all 44 consumer repos via
    `propagate-packages.sh`
11. **Commits** the module repo's own changes (csproj + CHANGELOG)
12. **Pushes** the module repo to origin

Every step that can fail does so with a clear exit code and leaves the
workspace in a clean state (csproj + CHANGELOG rollback on build failure;
NuGet-already-on-feed warning on push failure).

---

## When Claude is asked to release a module

The trigger is any phrasing like:
- "release this module"
- "publish this to NuGet"
- "ship a new version"
- "cut a release"
- `/release` slash command

**Default response**: run `./release.sh` with the user's message as the
CHANGELOG entry. Ask clarifying questions only if:
- The user didn't say what changed (ask for a one-line summary)
- The changes look breaking (confirm `--breaking` flag)
- The workspace is dirty with unrelated uncommitted work (confirm before
  including in the release commit)

**Never**: manually edit the `<Version>` + CHANGELOG + pack + push
sequence by hand. The script exists so nothing gets skipped.

**Never**: set the new version to anything other than today's CalVer.
The script computes it from `$(date)`. Overriding breaks the convention.

**Never**: use `--skip-central` unless NovaraSDK genuinely isn't
reachable. Stale central pins are how 22 modules drifted onto SDK 1.1.0
before this rule existed.

---

## If the script fails

### Build failure (exit 2)
csproj + CHANGELOG are rolled back. Investigate, fix, re-run. No NuGet
was published, no commits were made.

### Publish failure (exit 3)
Build worked, pack worked, the NuGet push to GitHub Packages failed.
The `.nupkg` is on disk at `/d/NovaraDev/LocalNuGet/$PACKAGE.$VERSION.nupkg`.
Git repo is still clean (no commit yet). Common causes:
- `GITHUB_TOKEN` invalid / expired / missing `write:packages` scope
- Network / feed downtime
- Version conflict (someone published the same number from another machine)

Fix the cause, re-run the push command manually:
```bash
dotnet nuget push /d/NovaraDev/LocalNuGet/PackageName.Version.nupkg \
  --source "https://nuget.pkg.github.com/MonoceptOfficial/index.json" \
  --api-key "$GITHUB_TOKEN"
```

### Commit/push failure (exit 4)
**NuGet is already on the feed** — this is important. Don't try to
re-release the same version. Fix the git issue, then manually commit
+ push the csproj/CHANGELOG changes. Never bump to a different version
just to dodge a failed commit.

---

## Releases trigger central-template updates

When `release.sh` runs successfully with NovaraSDK reachable:

1. This module's version pin in
   `NovaraSDK/distribution/Directory.Packages.props.template` updates.
2. `propagate-packages.sh --apply` copies the new template to every
   consumer repo's `Directory.Packages.props`.
3. NovaraSDK is committed + pushed.

Other repos are NOT auto-committed (too much blast radius). Module devs
will see the Directory.Packages.props change on their next `git pull` —
they commit when they're ready. A future CI workflow can automate this
further if the manual step becomes painful.

---

## What Claude must NEVER do during a release

- Run `git push --force` (obviously)
- Skip `--central` without an explicit reason
- Bypass the CHANGELOG hook with `[no-changelog]` for a release
- Publish a version whose date isn't today
- Commit unrelated files alongside the release commit
- Retry a failed push by bumping the version number (always debug the
  original failure first)

---

## Hooks that back this up

- `.claude/hooks/check-changelog-on-version-bump.py` — pre-commit,
  blocks version bumps without CHANGELOG change (release.sh satisfies
  this automatically because it stages both)
- `.claude/hooks/check-module-boundaries.py` — pre-commit, blocks
  architectural violations
- **CI enforcement (future)** — GitHub Action in each repo validates the
  same rules on PR

---

## Rollback

CalVer's one-way-door property means you can't republish a version you
published 30 seconds ago with a fix. To roll back:

1. Ship a NEW release (`26.4.211`) that reverts / fixes.
2. Update CHANGELOG entry noting what the rollback addressed.
3. Consumers update via `git pull`.

You can **unlist** a bad version on GitHub Packages (admin UI) so
consumers can't inadvertently pull it on a fresh restore, but the
version string is permanent.

---

## Related rules

- `.claude/rules/versioning.md` — the CalVer standard
- `.claude/rules/engineering-discipline.md` Gate 6 — handoff truth-telling
- `.claude/tools/verify-session-builds.sh` — build verification
- `NovaraSDK/distribution/Directory.Packages.props.template` — central pins
- `NovaraSDK/distribution/propagate-packages.sh` — pin propagation
- `NovaraSDK/distribution/release-module.sh` — the script this rule governs
