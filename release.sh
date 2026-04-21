#!/usr/bin/env bash
# release-module.sh — one-command release for any Novara module.
#
# Bumps the module's csproj <Version> to today's CalVer, updates CHANGELOG.md,
# builds + packs, pushes the NuGet, commits + pushes the repo, and (if
# NovaraSDK is a sibling clone) updates the central Directory.Packages.props
# template + re-propagates so every other module picks up the new pin.
#
# USAGE
#   ./release.sh "CHANGELOG entry line"
#   ./release.sh --breaking "what broke" --added "what's new"
#   ./release.sh --dry-run "test entry"       # show plan, don't do it
#
# FLAGS
#   --section TYPE      CHANGELOG section for the message: Added | Changed
#                       | Fixed | Removed | Deprecated | Security | BREAKING
#                       Default: Changed
#   --breaking "msg"    Shorthand for --section BREAKING
#   --added "msg"       Shorthand for --section Added
#   --fixed "msg"       Shorthand for --section Fixed
#   --changed "msg"     Shorthand for --section Changed
#   --dry-run           Show everything that would happen, don't mutate
#   --skip-publish      Commit/push the repo but don't push the NuGet
#   --skip-central      Don't update the central Directory.Packages.props
#                       template even if NovaraSDK is available
#   --skip-commit       Pack + publish but leave the git repo dirty
#   --sdk-path PATH     Override auto-detect of NovaraSDK location
#
# ENVIRONMENT
#   GITHUB_TOKEN        Required for NuGet push (PAT with write:packages).
#                       If absent and --skip-publish wasn't passed, fails early.
#
# REQUIREMENTS
#   - Run from inside a module repo (anywhere under the repo root).
#   - git, dotnet, python3, curl.
#   - A CHANGELOG.md at repo root (created if missing with a stub).
#
# EXIT CODES
#   0   success
#   1   precondition / argument failure
#   2   build failure — nothing was published or committed
#   3   publish failure — repo still clean, you can retry
#   4   commit / push failure — NuGet may already be on the feed

set -uo pipefail

# ─── Flag parsing ──────────────────────────────────────────────────
section="Changed"
message=""
dry_run=false
skip_publish=false
skip_central=false
skip_commit=false
sdk_path=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --section)       section="$2"; shift 2 ;;
        --breaking)      section="BREAKING"; message="$2"; shift 2 ;;
        --added)         section="Added";    message="$2"; shift 2 ;;
        --fixed)         section="Fixed";    message="$2"; shift 2 ;;
        --changed)       section="Changed";  message="$2"; shift 2 ;;
        --removed)       section="Removed";  message="$2"; shift 2 ;;
        --deprecated)    section="Deprecated"; message="$2"; shift 2 ;;
        --security)      section="Security"; message="$2"; shift 2 ;;
        --dry-run)       dry_run=true; shift ;;
        --skip-publish)  skip_publish=true; shift ;;
        --skip-central)  skip_central=true; shift ;;
        --skip-commit)   skip_commit=true; shift ;;
        --sdk-path)      sdk_path="$2"; shift 2 ;;
        --help|-h)       sed -n '2,40p' "$0" | sed 's|^# \?||'; exit 0 ;;
        --*)             echo "Unknown flag: $1" >&2; exit 1 ;;
        *)               if [[ -z "$message" ]]; then message="$1"; else echo "Unexpected: $1" >&2; exit 1; fi; shift ;;
    esac
done

if [[ -z "$message" ]]; then
    echo "error: CHANGELOG entry message required. Run with --help for usage." >&2
    exit 1
fi

# ─── Precondition: inside a git repo ───────────────────────────────
if ! git rev-parse --show-toplevel >/dev/null 2>&1; then
    echo "error: not inside a git repository" >&2
    exit 1
fi
REPO="$(git rev-parse --show-toplevel)"
cd "$REPO"

# ─── Precondition: single primary csproj (the one being released) ──
# Find .csprojs at api/src/*/ — the convention for module main assemblies.
primary_csproj="$(find "$REPO/api/src" -maxdepth 3 -name "Novara.Module.*.csproj" -not -path "*Tests*" 2>/dev/null | head -1)"
if [[ -z "$primary_csproj" ]]; then
    # Fall back to any Novara.* csproj at api/src
    primary_csproj="$(find "$REPO/api/src" -maxdepth 3 -name "Novara.*.csproj" -not -path "*Tests*" 2>/dev/null | head -1)"
fi
if [[ -z "$primary_csproj" ]]; then
    echo "error: could not locate the module's primary csproj under api/src/**" >&2
    echo "  Looked for: Novara.Module.*.csproj and Novara.*.csproj" >&2
    exit 1
fi

# ─── Extract current state ─────────────────────────────────────────
PACKAGE_ID="$(grep -oE '<PackageId>[^<]+</PackageId>' "$primary_csproj" | head -1 | sed 's|<[^>]*>||g')"
CURRENT_VERSION="$(grep -oE '<Version>[^<]+</Version>' "$primary_csproj" | head -1 | sed 's|<[^>]*>||g')"
MODULE_NAME="$(basename "$REPO")"

if [[ -z "$PACKAGE_ID" || -z "$CURRENT_VERSION" ]]; then
    echo "error: csproj at $primary_csproj must declare both <PackageId> and <Version>" >&2
    exit 1
fi

# ─── Compute next version ──────────────────────────────────────────
# Format: YYYY.M.D.N  (no zero-padding on month/day, per rules/versioning.md)
TODAY_Y="$(date +%Y)"
TODAY_M="$(date +%-m 2>/dev/null || date +%m | sed 's/^0//')"   # no leading zero
TODAY_D="$(date +%-d 2>/dev/null || date +%d | sed 's/^0//')"
TODAY_PREFIX="${TODAY_Y}.${TODAY_M}.${TODAY_D}"

if [[ "$CURRENT_VERSION" =~ ^${TODAY_PREFIX}\.([0-9]+)$ ]]; then
    # Already released today — bump the Nth segment.
    n=$((${BASH_REMATCH[1]} + 1))
    NEW_VERSION="${TODAY_PREFIX}.${n}"
else
    # First release today — start at .1
    NEW_VERSION="${TODAY_PREFIX}.1"
fi

# ─── Precondition: GITHUB_TOKEN unless --skip-publish ──────────────
if [[ "$skip_publish" == false ]] && [[ -z "${GITHUB_TOKEN:-}" ]]; then
    echo "error: GITHUB_TOKEN not set. Either export it or run with --skip-publish." >&2
    exit 1
fi

# ─── Announce the plan ─────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════════════════════"
echo "  Novara release — ${MODULE_NAME}"
echo "══════════════════════════════════════════════════════════════════"
echo "  Package:         $PACKAGE_ID"
echo "  Current version: $CURRENT_VERSION"
echo "  New version:     $NEW_VERSION"
echo "  CHANGELOG:       ## $NEW_VERSION  —  [${section}] $message"
[[ "$dry_run" == true ]]     && echo "  Mode:            DRY-RUN (no changes)"
[[ "$skip_publish" == true ]] && echo "  NuGet push:      SKIPPED"
[[ "$skip_central" == true ]] && echo "  Central template: SKIPPED"
[[ "$skip_commit"  == true ]] && echo "  Git commit/push: SKIPPED"
echo "──────────────────────────────────────────────────────────────────"

$dry_run && { echo "Dry run complete. Re-run without --dry-run to execute."; exit 0; }

# ─── 1. Update csproj <Version> ────────────────────────────────────
# Portable sed: write to temp then mv (avoid -i differences across platforms).
tmpfile="$(mktemp)"
sed "s|<Version>${CURRENT_VERSION}</Version>|<Version>${NEW_VERSION}</Version>|" "$primary_csproj" > "$tmpfile"
mv "$tmpfile" "$primary_csproj"
echo "✓ Bumped csproj version"

# ─── 2. Update CHANGELOG.md ────────────────────────────────────────
CHANGELOG="$REPO/CHANGELOG.md"
if [[ ! -f "$CHANGELOG" ]]; then
    cat > "$CHANGELOG" <<EOF
# ${PACKAGE_ID} — CHANGELOG

All notable changes. Format: CalVer \`YYYY.M.D.N\`. Newest first.

---

EOF
    echo "✓ Created new CHANGELOG.md"
fi

# Prepend the new entry after the top header.
entry_header="## ${NEW_VERSION}"
entry_block="${entry_header}

### ${section}
- ${message}

---

"

# Find the first "---" separator and inject above it; fallback: append after first blank line after title.
python3 - "$CHANGELOG" "$entry_block" <<'PY'
import sys, pathlib
path = pathlib.Path(sys.argv[1])
entry = sys.argv[2]
text = path.read_text(encoding="utf-8")
# Prefer to insert above the first "---" line (our section separator).
marker = "\n---\n"
idx = text.find(marker)
if idx == -1:
    # No separator yet — append after the header block (first blank line)
    parts = text.split("\n\n", 2)
    if len(parts) >= 2:
        path.write_text(parts[0] + "\n\n" + entry + parts[1] + ("\n\n" + parts[2] if len(parts) == 3 else ""), encoding="utf-8")
    else:
        path.write_text(text + "\n\n" + entry, encoding="utf-8")
else:
    path.write_text(text[:idx + 1] + entry + text[idx + 1:], encoding="utf-8")
PY
echo "✓ Updated CHANGELOG.md"

# ─── 3. Build ──────────────────────────────────────────────────────
echo "→ Building Release..."
if ! dotnet build -c Release "$primary_csproj" >/tmp/release-build.log 2>&1; then
    echo "✗ Build failed. See /tmp/release-build.log tail:"
    tail -20 /tmp/release-build.log
    # Roll back csproj + CHANGELOG on build failure so repo stays clean.
    git -C "$REPO" checkout -- "$primary_csproj" "$CHANGELOG" 2>/dev/null
    exit 2
fi
echo "✓ Build clean"

# ─── 4. Pack ───────────────────────────────────────────────────────
mkdir -p /d/NovaraDev/LocalNuGet
echo "→ Packing..."
if ! dotnet pack -c Release -p:NuGetPack=true "$primary_csproj" -o /d/NovaraDev/LocalNuGet >/tmp/release-pack.log 2>&1; then
    echo "✗ Pack failed. See /tmp/release-pack.log tail:"
    tail -20 /tmp/release-pack.log
    git -C "$REPO" checkout -- "$primary_csproj" "$CHANGELOG" 2>/dev/null
    exit 2
fi
NUPKG="/d/NovaraDev/LocalNuGet/${PACKAGE_ID}.${NEW_VERSION}.nupkg"
if [[ ! -f "$NUPKG" ]]; then
    echo "✗ Pack completed but $NUPKG does not exist"; exit 2
fi
echo "✓ Packed $NUPKG"

# ─── 5. Push to NuGet feed ─────────────────────────────────────────
if [[ "$skip_publish" == false ]]; then
    echo "→ Pushing to GitHub Packages feed..."
    if ! dotnet nuget push "$NUPKG" \
        --source "https://nuget.pkg.github.com/MonoceptOfficial/index.json" \
        --api-key "$GITHUB_TOKEN" >/tmp/release-push.log 2>&1; then
        echo "✗ NuGet push failed. See /tmp/release-push.log tail:"
        tail -10 /tmp/release-push.log
        # Don't roll back — build worked and .nupkg is on disk. Dev can retry push.
        exit 3
    fi
    echo "✓ Published to feed"
else
    echo "· Skipped NuGet push"
fi

# ─── 6. Update central template (if NovaraSDK reachable) ───────────
if [[ "$skip_central" == false ]]; then
    # Auto-detect NovaraSDK location: sibling of the module's workspace root.
    if [[ -z "$sdk_path" ]]; then
        candidate="$(cd "$REPO/../.." && pwd)/NovaraSDK"
        [[ -d "$candidate" ]] && sdk_path="$candidate"
    fi
    TEMPLATE="${sdk_path}/distribution/Directory.Packages.props.template"
    if [[ -n "$sdk_path" ]] && [[ -f "$TEMPLATE" ]]; then
        # Update the template's pin for this package.
        tmpfile="$(mktemp)"
        python3 - "$TEMPLATE" "$PACKAGE_ID" "$NEW_VERSION" "$tmpfile" <<'PY'
import sys, re, pathlib
path, pkg, ver, out = sys.argv[1:5]
text = pathlib.Path(path).read_text(encoding="utf-8")
pattern = re.compile(rf'(<PackageVersion\s+Include="{re.escape(pkg)}"\s+Version=")([^"]*)(")', re.MULTILINE)
if pattern.search(text):
    text = pattern.sub(rf'\g<1>{ver}\g<3>', text, count=1)
else:
    sys.exit(42)  # pkg not in template — caller handles
pathlib.Path(out).write_text(text, encoding="utf-8")
PY
        rc=$?
        if [[ $rc -eq 0 ]]; then
            mv "$tmpfile" "$TEMPLATE"
            echo "✓ Bumped central template: $PACKAGE_ID $NEW_VERSION"

            # Re-propagate + commit NovaraSDK if it's a clean git repo.
            if git -C "$sdk_path" rev-parse --show-toplevel >/dev/null 2>&1; then
                ( cd "$sdk_path/distribution" && ./propagate-packages.sh --apply >/dev/null 2>&1 ) && echo "✓ Propagated Directory.Packages.props to all repos"

                # Commit + push NovaraSDK itself (only the template change — propagate
                # into other repos is each repo's own commit, too much to cover here).
                if ! git -C "$sdk_path" diff --quiet distribution/Directory.Packages.props.template 2>/dev/null; then
                    git -C "$sdk_path" add distribution/Directory.Packages.props.template
                    git -C "$sdk_path" commit -m "chore: pin ${PACKAGE_ID} → ${NEW_VERSION}" >/dev/null 2>&1 && \
                    git -C "$sdk_path" push origin master >/dev/null 2>&1 && \
                    echo "✓ Pushed central-template bump to NovaraSDK origin"
                fi
            fi
        elif [[ $rc -eq 42 ]]; then
            echo "· $PACKAGE_ID not yet in central template — add manually if consumers need to pin it"
        else
            echo "✗ Central template update failed (exit $rc)"
        fi
    else
        echo "· NovaraSDK not found at expected path — central template not updated"
        echo "  Set --sdk-path to update manually, or let CI handle it"
    fi
else
    echo "· Skipped central template update"
fi

# ─── 7. Commit + push the module repo ──────────────────────────────
if [[ "$skip_commit" == false ]]; then
    cd "$REPO"
    git add "$primary_csproj" CHANGELOG.md
    # Stage Directory.Packages.props if it was touched by propagate earlier.
    git add Directory.Packages.props 2>/dev/null || true

    commit_msg="release: ${PACKAGE_ID} ${NEW_VERSION}

${section}: ${message}

Auto-generated by release-module.sh. See CHANGELOG.md for the full entry."

    if ! git commit -m "$commit_msg" >/tmp/release-commit.log 2>&1; then
        echo "✗ git commit failed. See /tmp/release-commit.log:"
        cat /tmp/release-commit.log
        exit 4
    fi
    echo "✓ Committed"

    if ! git push origin "$(git rev-parse --abbrev-ref HEAD)" >/tmp/release-push-git.log 2>&1; then
        echo "✗ git push failed. NuGet IS already on the feed. Resolve manually:"
        cat /tmp/release-push-git.log
        exit 4
    fi
    echo "✓ Pushed to origin"
fi

# ─── Done ──────────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════════════════════"
echo "  Released ${PACKAGE_ID} ${NEW_VERSION}"
echo "══════════════════════════════════════════════════════════════════"
echo "  Feed:        https://github.com/MonoceptOfficial?tab=packages"
echo "  Next steps:  consumer modules get this pin on their next"
echo "               \`git pull\` + \`dotnet restore\`."
