---
description: Release the current Novara module — CalVer bump, CHANGELOG, pack, publish, push.
---

# /release — publish the current module

When the user invokes `/release`, run the module's `release.sh` with the
arguments they provided. This is the one-command release flow defined in
`.claude/rules/release-workflow.md`.

## Default behavior

Run from the module's repo root:

```bash
./release.sh "$ARGUMENTS"
```

If `$ARGUMENTS` is empty, ask the user for a one-line CHANGELOG entry
describing what changed. Don't proceed without it — the pre-commit hook
will reject the commit and the script will exit 4.

## Classifying the change

From the user's message, infer the CHANGELOG section:

| User's phrasing contains | Use flag |
|---|---|
| "new", "added", "now supports" | `--added` |
| "fix", "bugfix", "resolves", "closes" | `--fixed` |
| "remove", "drop", "delete" | `--removed` |
| "deprecate" | `--deprecated` |
| "security", "CVE", "vulnerability" | `--security` |
| "break", "breaking", "incompatible", "removes public API" | `--breaking` |
| Anything else | `--changed` (default) |

If you're uncertain — especially about breaking — ask before running.
Getting the breaking flag wrong silently loses the signal.

## Breaking change confirmation

If `--breaking` is inferred or requested, confirm with the user before
proceeding. Example:

> "This looks breaking (removes the `Foo` API). Proceeding with
> `--breaking` will mark it in the CHANGELOG. OK? Also: is there an
> ADR for this change? (Per .claude/rules/versioning.md, SDK breaking
> changes need one.)"

## Dry run for confidence

For first-time contributors or risky changes, suggest:

```bash
./release.sh --dry-run "your message"
```

Shows the full plan (new version, CHANGELOG entry, build/pack/push
steps) without mutating anything. Re-run without `--dry-run` once the
plan looks right.

## If release.sh fails

Report the exit code + suggested next step from
`.claude/rules/release-workflow.md`:

- **Exit 2 (build)**: repo is clean, investigate + retry
- **Exit 3 (publish)**: `.nupkg` is on disk, retry `dotnet nuget push`
- **Exit 4 (commit/push)**: NuGet already on feed, fix git + manual commit

Never dodge a failed release by bumping to a different version.

## What NOT to do

- Never manually edit `<Version>` + CHANGELOG + pack + push step-by-step —
  always use `release.sh`. Manual releases skip safeguards.
- Never pass a version number explicitly — the script computes today's
  CalVer. Overriding is a bug.
- Never use `--skip-central` unless NovaraSDK truly isn't reachable.

## See also

- `.claude/rules/release-workflow.md` — full policy
- `.claude/rules/versioning.md` — CalVer specification
- `./release.sh --help` — script-level flag reference
