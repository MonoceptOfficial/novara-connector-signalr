#!/usr/bin/env python3
"""
check-sql-param-naming.py — pre-commit guard for PostgreSQL function parameter naming.

Blocks commits that introduce a CREATE [OR REPLACE] FUNCTION whose parameters
violate the snake_case-with-p_-prefix convention defined in
`.claude/rules/sql-conventions.md`.

Specifically flags:
  - Params not starting with `p_`             (e.g. `userid`,   `feature_id`)
  - Params with legacy no-underscore names    (e.g. `p_userid`, `p_featureid`)
  - Params with mixed case                    (e.g. `p_UserId`)

The rule applies to migrations in `migrations/` directories across Novara repos.
Extension / TimescaleDB internals are out of scope — they live in generated
schema dumps, never in hand-edited migrations.

Run mode:
  Invoked from pre-commit.sh. Reads `git diff --cached --name-only` for .sql
  files. For each one, extracts the staged content and checks CREATE FUNCTION
  signatures. Exits 0 if clean, 1 if any violation found.

Fix path:
  Rename the offending param to snake_case with `p_` prefix. E.g.,
    p_userid     → p_user_id
    userid       → p_user_id
    p_UserId     → p_user_id
  Update the function body to reference the new name and any consumer SP names
  via the SpNames.cs constants (if the function name also changed).

Escape hatch:
  `git commit --no-verify` bypasses ALL pre-commit checks. Use only in true
  emergencies. Every such bypass is visible in the PR diff and subject to
  review. Don't normalise it.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

# Structural pattern: must start with `p_`, have at least one tail segment,
# lowercase alphanumeric with optional _snake_case segments. Blocks
# PascalCase / mixed-case / double-underscore / missing-prefix outright.
# The dictionary check catches legacy single-segment compounds (p_userid,
# p_featureid) that pass this structural check but should be split.
PARAM_PATTERN = re.compile(r"^p(?:_[a-z0-9]+)+$")

# Matches CREATE [OR REPLACE] FUNCTION with a parenthesized signature across
# newlines. Captures the parameter list for downstream analysis. Case-insensitive.
CREATE_FN_RE = re.compile(
    r"create\s+(?:or\s+replace\s+)?function\s+[a-z0-9_.]+\s*\((.*?)\)",
    re.IGNORECASE | re.DOTALL,
)

# Within a parameter list, grab each parameter name. A parameter looks like:
#   [IN|OUT|INOUT|VARIADIC]? <name> <type> [DEFAULT ...]?
# Comma-separated. We scan parenthetical TYPE declarations (like NUMERIC(18,2))
# by bracketing: simple approach splits on top-level commas.
# The param name is the first word-ish token after any IN/OUT/INOUT/VARIADIC mode.
PARAM_NAME_RE = re.compile(
    r"^\s*(?:(?:in|out|inout|variadic)\s+)?([a-zA-Z_][a-zA-Z0-9_]*)\s+",
    re.IGNORECASE,
)


def split_top_level_commas(s: str) -> list[str]:
    """Split string on commas that are NOT inside parentheses. Used to split
    a function's parameter list into individual param declarations."""
    parts = []
    depth = 0
    last = 0
    for i, ch in enumerate(s):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(s[last:i])
            last = i + 1
    parts.append(s[last:])
    return [p.strip() for p in parts if p.strip()]


def extract_param_names(signature: str) -> list[str]:
    """From the contents of a CREATE FUNCTION's (...) block, return the list
    of parameter names as declared."""
    names: list[str] = []
    for param in split_top_level_commas(signature):
        m = PARAM_NAME_RE.match(param)
        if m:
            names.append(m.group(1))
    return names


def load_compound_dictionary() -> dict[str, str]:
    """Load the canonical compound → snake_case map. The hook uses it to catch
    legacy single-segment compounds that pass the structural regex (e.g. p_userid
    matches p(_[a-z0-9]+)+ but should be p_user_id).

    Resolution order:
      1. Shell-relative canonical path (when running inside NovaraWorkspaceShell)
      2. Module-relative propagated path (when running inside a module repo,
         where distribution/propagate-rules.sh placed the dictionary)
    """
    script_dir = Path(__file__).resolve().parent
    candidates = [
        script_dir.parent.parent / "NovaraSDK" / "distribution" / "pg-param-dictionary.json",
        # Module repos receive a copy at .claude/distribution/pg-param-dictionary.json
        script_dir.parent / "distribution" / "pg-param-dictionary.json",
    ]
    for path in candidates:
        if path.is_file():
            try:
                with path.open(encoding="utf-8") as f:
                    doc = json.load(f)
                return doc.get("_compounds", {})
            except (OSError, json.JSONDecodeError):
                continue
    # Dictionary missing is not a hard failure — the structural check still
    # catches obvious violations. Log silently and proceed.
    return {}


_COMPOUNDS = load_compound_dictionary()


def check_param_name(name: str) -> str | None:
    """Return a violation message if `name` breaks the convention, else None."""
    if not PARAM_PATTERN.match(name):
        return f"parameter '{name}' violates snake_case-with-p_-prefix convention"
    # Strip the p_ prefix; check tail against known compounds
    if name.startswith("p_"):
        tail = name[2:]
        if "_" not in tail and tail in _COMPOUNDS:
            return (
                f"parameter '{name}' is a legacy compound — should be 'p_{_COMPOUNDS[tail]}' "
                f"(see pg-param-dictionary.json)"
            )
    return None


def check_file(path: Path, content: str) -> list[str]:
    """Return a list of human-readable violation messages for this .sql file."""
    issues: list[str] = []
    for fn_match in CREATE_FN_RE.finditer(content):
        sig = fn_match.group(1)
        line_no = content[: fn_match.start()].count("\n") + 1
        for name in extract_param_names(sig):
            violation = check_param_name(name)
            if violation:
                issues.append(f"{path}:{line_no}: {violation}")
    return issues


def get_staged_sql_files() -> list[Path]:
    """Return the list of .sql files staged in this commit (relative to repo root)."""
    try:
        out = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=AM"],
            text=True,
            encoding="utf-8",
        )
    except subprocess.CalledProcessError:
        return []
    paths: list[Path] = []
    for line in out.splitlines():
        line = line.strip()
        if not line.endswith(".sql"):
            continue
        # Only scan files in migrations/ — production migrations.
        # Schema dumps / generated snapshots sit elsewhere (NovaraWorkspaceProductDB/schema/)
        # and their conventions are governed by pg_dump output.
        normalized = line.replace("\\", "/")
        if "/migrations/" in normalized or normalized.startswith("migrations/"):
            paths.append(Path(line))
    return paths


def read_staged_content(path: Path) -> str:
    """Read the staged (indexed) content of a file — not the working tree version.
    Git refs require forward slashes on every OS, so we normalise before calling."""
    git_ref = ":" + str(path).replace("\\", "/")
    try:
        return subprocess.check_output(
            ["git", "show", git_ref],
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.CalledProcessError:
        # Fallback to working-tree content if git show fails (shouldn't normally happen)
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""


def main() -> int:
    staged = get_staged_sql_files()
    if not staged:
        return 0

    all_issues: list[str] = []
    for path in staged:
        content = read_staged_content(path)
        if not content:
            continue
        all_issues.extend(check_file(path, content))

    if not all_issues:
        return 0

    print("=" * 72, file=sys.stderr)
    print("SQL parameter naming violations detected:", file=sys.stderr)
    print("=" * 72, file=sys.stderr)
    for issue in all_issues:
        print(f"  {issue}", file=sys.stderr)
    print("", file=sys.stderr)
    print(
        "Every Novara function parameter must be snake_case with a `p_` prefix "
        "(e.g. p_feature_id, p_user_id).",
        file=sys.stderr,
    )
    print(
        "Full convention: .claude/rules/sql-conventions.md",
        file=sys.stderr,
    )
    print(
        "Vocabulary: NovaraSDK/distribution/pg-param-dictionary.json",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
