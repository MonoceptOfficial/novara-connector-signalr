# Module developer — daily workflow (post-CalVer / post-CPM)

Adopted 2026-04-21. Binding for every module developer working with Claude Code.

## The one-sentence version

**Start of day `/pull`. Work normally. End of day `/pushtoorigin`. Releasing? `./release.sh "msg"`.**

Everything else is unchanged from before CalVer/CPM.

---

## Morning (once per day)

```
cd NovaraModules/novara-module-{yours}
claude
```

Then at the Claude prompt:

```
/pull
```

What happens (all automatic):

1. `git pull origin master --ff-only`
2. Refresh `Directory.Packages.props` from the canonical NovaraSDK template
   (fetches over HTTPS with your `GITHUB_TOKEN`, or from the local
   `NovaraSDK/distribution/` clone if you have it as a sibling repo)
3. Diff shown if CPM pins moved — e.g. "Novara.Shell.UI 26.4.220 → 26.4.222"
4. `dotnet nuget locals http-cache --clear`
5. `dotnet restore host/Novara.DevHost.csproj --force`
6. `dotnet build host/Novara.DevHost.csproj --no-restore`
7. Prints the versions you're now running

**If CPM pins changed**, the output reminds you to commit the
`Directory.Packages.props` update — a one-file, one-line commit:

```
git add Directory.Packages.props && git commit -m "chore: sync CPM pins" && git push origin master
```

No `/pull` = no refreshed Shell.UI = "my module isn't showing latest Shell changes."
This is the #1 reported issue and it's always solved by `/pull`.

---

## Starting the platform

```
/start
```

Kills any existing Gateway on :5050, launches the DevHost with hot reload.
Browser to https://localhost:5050/dev → pick a user → you're in.

Hot reload keeps working: edit a C# file, `dotnet watch` rebuilds, browser
refreshes. The Gateway's cache policy (`max-age=31536000` for hashed chunks,
`no-cache` for entry files) means browser ALWAYS fetches fresh `main.js`
and `federation.manifest.json` — no Ctrl-F5 ritual needed.

---

## During the day

Normal development. Nothing about CPM/CalVer changes your inner loop.

- Edit C# / Angular / SQL
- Hot reload handles it
- Commit often

Two things to know:

1. **Never write `<PackageReference Include="..." Version="..." />` in a csproj.**
   CPM rejects the build. Versions live ONLY in `Directory.Packages.props`,
   which you don't hand-edit — it's refreshed by `/pull` or `/update-deps`.

2. **If you need to test against a newer (or older) package locally**, use
   `/update-deps Package=Version` for a temporary override:
   ```
   /update-deps Novara.Shell.Gateway=26.4.222
   ```
   Don't commit the `Directory.Packages.props` change — next `/pull` will
   re-align it with the canonical template.

---

## End of day (finishing work)

```
/pushtoorigin
```

This runs the pre-commit hooks (module-boundaries, recursion-safety,
prompts-discipline, no-inline-SQL, etc.) then commits + pushes. If a hook
blocks, read the error — it's catching a real rule violation, not being
punitive.

---

## Releasing your module (when you want a published version)

```
./release.sh "short description of what changed"
```

Or with typed sections:

```bash
./release.sh --added "New GuestReviewer role for Design Studio share tokens"
./release.sh --fixed "Dapper CT now propagates to cancellation"
./release.sh --breaking "Removed Guard.NotFoundException(string) ctor"
```

One command does all of:

1. Computes today's CalVer (`YYYY.M.D.N`)
2. Bumps your csproj `<Version>`
3. Prepends `CHANGELOG.md` entry under the right section
4. `dotnet build` (rolls back csproj + CHANGELOG if it fails)
5. `dotnet pack` to `D:/NovaraDev/LocalNuGet/`
6. `dotnet nuget push` to `nuget.pkg.github.com/MonoceptOfficial`
7. Updates `NovaraSDK/distribution/Directory.Packages.props.template`
   (if you have NovaraSDK cloned as a sibling)
8. Runs `propagate-packages.sh --apply` → every consumer repo's
   `Directory.Packages.props` is refreshed in-place (uncommitted)
9. Commits your own csproj + CHANGELOG changes
10. Pushes your module repo

Other module devs see the new version on their next `/pull`.

---

## Common mistakes (and the fix)

| Symptom | Cause | Fix |
|---|---|---|
| "Shell isn't showing my latest changes" | Stale `Novara.Shell.UI` pin in `Directory.Packages.props` | `/pull` refreshes the pin. 9/10 times this is it. |
| "Build fails: 'Novara.X has no Version attribute'" | You wrote `Version="..."` on a `<PackageReference>` | Remove the Version attribute. CPM rejects inline versions. |
| "Build fails: 'package X version Y not found'" | `Directory.Packages.props` pins a version that isn't on the feed yet | Wait for the release to finish propagating. Or `/update-deps` to pull latest. |
| "Pre-commit blocks my version bump" | Changed csproj `<Version>` without touching `CHANGELOG.md` | Use `./release.sh` — it handles both. Never hand-bump the version. |
| "Chrome won't load after deploy" | Should no longer happen — regex cache classifier + no-cache on entry files makes this structurally impossible. If it does, report — likely a regression. | — |
| `dotnet restore` says 401 | `GITHUB_TOKEN` expired | Regenerate at https://github.com/settings/tokens with `read:packages` |
| `/pull` says "CPM pins have changed since your last refresh" every day | Someone else is releasing modules regularly — this is NORMAL. Commit the change (`git add Directory.Packages.props && git commit -m "chore: sync CPM pins"`). | — |

---

## When something feels off: the diagnostic order

1. `/pull` — fixes 90% of "Shell stale" issues
2. `/status` — shows Gateway health, DB connectivity, git state, NuGet versions
3. `/clean` — nukes bin/obj + NuGet cache + restores from scratch (use when
   something is truly broken, not as a first-resort)
4. Check pending work in the repo: `cat documents/pendingwork/pending-*.md | tail -50`

---

## Versioning mental model (CalVer)

- **Old (semver):** "I'm bumping to v1.5.0 — minor because I added a method."
- **New (CalVer):** "I'm bumping to today's date. Did I break anything? If yes,
  I add a `BREAKING:` section to the CHANGELOG."

No more major/minor/patch decisions. Breaking changes signal via CHANGELOG
entries + (for SDK surface changes) an ADR in `.claude/architecture/`.
Year boundaries (`2027.1.1.1`) are the informal major-bump moment.

---

## Canonical references

- [`.claude/rules/versioning.md`](versioning.md) — CalVer standard in detail
- [`.claude/rules/release-workflow.md`](release-workflow.md) — release.sh discipline
- [`.claude/commands/pull.md`](../commands/release.md) in each module — the `/pull` implementation
- [`.claude/commands/update-deps.md`](../commands/release.md) in each module — override + refresh
- `NovaraSDK/distribution/Directory.Packages.props.template` — canonical CPM pins
- `NovaraSDK/distribution/propagate-packages.sh` — template → consumer-repo sync
- `NovaraSDK/distribution/release-module.sh` — the script behind every module's `release.sh`
