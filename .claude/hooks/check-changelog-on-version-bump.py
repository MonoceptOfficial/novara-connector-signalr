#!/usr/bin/env python3
"""
check-changelog-on-version-bump.py — pre-commit guard for CalVer discipline.

ENFORCES: any commit that bumps a `<Version>` element in a .csproj
(the package's OWN output version — what gets published to NuGet) MUST
include a corresponding CHANGELOG.md change in the same commit.

WHY this exists (see .claude/rules/versioning.md):
  CalVer lost semver's implicit "major bump = breaking change" signal.
  We replaced that signal with mandatory CHANGELOG.md entries per
  release. This hook is the enforcement — no CHANGELOG, no version
  bump, no commit.

INSTALL:
  Reference this script from .husky/pre-commit or the project's native
  pre-commit-hook file. It reads the staged diff via `git diff --cached`.

EXIT CODES:
  0  no version bumps, or every version bump has a matching CHANGELOG touch
  1  one or more csprojs bumped <Version> without touching CHANGELOG.md
  2  invoked outside a git repo or otherwise unexpected failure

BYPASS:
  Add `[no-changelog]` anywhere in the commit message. Use sparingly;
  bypasses are audited in the commit log.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

VERSION_TAG_RE = re.compile(r"^\s*<Version>([^<]+)</Version>\s*$")
NO_CHANGELOG_BYPASS = "[no-changelog]"


def run_git(args: list[str]) -> str:
    """Run a git command, return stdout. Returns empty string on failure."""
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True, text=True, check=False,
        )
        return result.stdout
    except FileNotFoundError:
        return ""


def commit_message() -> str:
    """Read the pending commit message from COMMIT_EDITMSG if available."""
    msg_file = Path(".git/COMMIT_EDITMSG")
    try:
        return msg_file.read_text(encoding="utf-8", errors="ignore")
    except FileNotFoundError:
        return ""


def staged_files() -> list[str]:
    """List of files staged for commit."""
    out = run_git(["diff", "--cached", "--name-only", "--diff-filter=ACMR"])
    return [line.strip() for line in out.splitlines() if line.strip()]


def version_bumped(csproj_path: str) -> tuple[str | None, str | None]:
    """
    Return (old_version, new_version) if <Version> changed in this csproj.
    Returns (None, None) if unchanged or if no <Version> line exists.
    """
    diff = run_git(["diff", "--cached", "-U0", "--", csproj_path])
    old_version = None
    new_version = None
    for line in diff.splitlines():
        # Only care about real -/+ changes to <Version>, not context / header lines.
        if line.startswith("---") or line.startswith("+++"):
            continue
        if line.startswith("-"):
            m = VERSION_TAG_RE.match(line[1:])
            if m:
                old_version = m.group(1)
        elif line.startswith("+"):
            m = VERSION_TAG_RE.match(line[1:])
            if m:
                new_version = m.group(1)
    if old_version and new_version and old_version != new_version:
        return old_version, new_version
    if new_version and not old_version:
        # Adding <Version> to a previously-unversioned project counts as a bump.
        return None, new_version
    return None, None


def changelog_nearby(csproj_path: str) -> Path | None:
    """
    Walk up from the csproj's directory looking for CHANGELOG.md. This handles
    both mono-module repos (CHANGELOG at repo root) and nested structures
    (CHANGELOG beside the api/ folder, etc.).
    Returns the first CHANGELOG.md found within 5 levels, or None.
    """
    current = Path(csproj_path).resolve().parent
    for _ in range(6):
        candidate = current / "CHANGELOG.md"
        if candidate.exists():
            return candidate
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def main() -> int:
    if not Path(".git").exists():
        # Not a git repo — skip silently.
        return 0

    msg = commit_message()
    if NO_CHANGELOG_BYPASS in msg:
        # Explicit opt-out. Still print a note so it's visible in CI output.
        print(f"[changelog-check] {NO_CHANGELOG_BYPASS} present — skipping. "
              "This bypass is audited; use sparingly.", file=sys.stderr)
        return 0

    files = staged_files()
    csprojs = [f for f in files if f.endswith(".csproj")]
    if not csprojs:
        return 0

    # Find csprojs with a <Version> bump in this commit.
    bumped: list[tuple[str, str | None, str]] = []
    for c in csprojs:
        old, new = version_bumped(c)
        if new:
            bumped.append((c, old, new))

    if not bumped:
        return 0

    # Any CHANGELOG.md staged?
    changelogs_staged = {
        f for f in files
        if f == "CHANGELOG.md" or f.endswith("/CHANGELOG.md")
    }

    # For each bumped csproj, require a CHANGELOG.md in the same repo tree.
    failures: list[str] = []
    for csproj_path, old, new in bumped:
        expected = changelog_nearby(csproj_path)
        if expected is None:
            failures.append(
                f"  {csproj_path}  (version {old or '(new)'} -> {new}): "
                f"no CHANGELOG.md found near this csproj — create one at the repo root."
            )
            continue

        # Convert absolute path back to repo-relative for membership check.
        try:
            rel = expected.resolve().relative_to(Path.cwd().resolve())
            rel_str = str(rel).replace(os.sep, "/")
        except ValueError:
            rel_str = str(expected)

        if rel_str not in changelogs_staged:
            failures.append(
                f"  {csproj_path}  (version {old or '(new)'} -> {new}): "
                f"expected CHANGELOG.md change at {rel_str}, "
                f"but it's not staged."
            )

    if failures:
        print("=" * 66, file=sys.stderr)
        print("  VERSION BUMP WITHOUT CHANGELOG -- commit BLOCKED", file=sys.stderr)
        print("=" * 66, file=sys.stderr)
        print("", file=sys.stderr)
        print("Novara uses CalVer (YYYY.M.D.N). Semver's implicit", file=sys.stderr)
        print("major-bump-means-breaking-change signal is replaced by a", file=sys.stderr)
        print("mandatory CHANGELOG.md entry per release. This hook is the", file=sys.stderr)
        print("enforcement -- no entry, no version bump, no commit.", file=sys.stderr)
        print("", file=sys.stderr)
        for f in failures:
            print(f, file=sys.stderr)
        print("", file=sys.stderr)
        print("Fix: add a CHANGELOG.md entry for this release and stage it:", file=sys.stderr)
        print("", file=sys.stderr)
        print("    ## 26.4.210", file=sys.stderr)
        print("    ### BREAKING / Added / Changed / Fixed", file=sys.stderr)
        print("    - short bullet describing the change", file=sys.stderr)
        print("", file=sys.stderr)
        print("Then:  git add <CHANGELOG.md>  &&  git commit", file=sys.stderr)
        print("", file=sys.stderr)
        print("Bypass (use sparingly; audited):", file=sys.stderr)
        print("    git commit -m 'your message  [no-changelog]'", file=sys.stderr)
        print("", file=sys.stderr)
        print("See .claude/rules/versioning.md for the full policy.", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # pragma: no cover — defensive only
        print(f"[changelog-check] unexpected error: {exc}", file=sys.stderr)
        sys.exit(2)
