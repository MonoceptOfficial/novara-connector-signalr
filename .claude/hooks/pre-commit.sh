#!/usr/bin/env bash
# pre-commit.sh — git pre-commit hook for Workspace + every module repo.
#
# Runs the fast, zero-dependency checks that MUST pass before code lands:
#   (B4) @angular/core version drift across Shell + modules (singleton sharing)
#   (B5) BRD-driven commit message format (handled by commit-msg hook, not here)
#   (future) any other <500ms structural check
#
# Wire it up per repo:
#   cp .claude/hooks/pre-commit.sh .git/hooks/pre-commit
#   chmod +x .git/hooks/pre-commit
#
# Or all-at-once from the Workspace root:
#   bash .claude/hooks/install-git-hooks.sh
#
# The hook is committed to the repo (in .claude/hooks/) so every cloner gets
# it. `.git/hooks/` is not committed, so the install step runs once per clone.
# This follows the Novara discipline of "guardrails travel with the code."

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="$SCRIPT_DIR/../tools"
REPO_ROOT="$(git rev-parse --show-toplevel)"

fail_count=0

echo "[pre-commit] running fast structural checks..."

# ── B4 — Angular version drift ────────────────────────────────────────
# Only runs if the checker exists AND any web/ or Angular-package file is staged.
# Skipping when the commit has no web impact keeps hook cost near-zero for
# backend-only PRs.
ANGULAR_CHECKER="$TOOLS_DIR/check-angular-version-drift.py"
if [[ -f "$ANGULAR_CHECKER" ]]; then
    staged_web_files=$(git diff --cached --name-only | grep -E '(package\.json|federation\.config\.js|/web/)' || true)
    if [[ -n "$staged_web_files" ]]; then
        echo "[pre-commit] B4: angular version drift check (web files staged)..."
        if ! python3 "$ANGULAR_CHECKER" --json > /tmp/novara-angular-drift.json 2>&1; then
            echo "❌ [B4] @angular/core version drift detected between Shell + modules." >&2
            echo "       Review: $(cat /tmp/novara-angular-drift.json)" >&2
            echo "       Fix by running: python .claude/tools/normalize-angular-versions.py" >&2
            fail_count=$((fail_count + 1))
        else
            echo "✓ [B4] angular versions aligned"
        fi
    fi
fi

# ── SQL param naming (snake_case with p_ prefix) ──────────────────────
# Blocks commits that introduce CREATE [OR REPLACE] FUNCTION with params
# that violate .claude/rules/sql-conventions.md. Only runs when a .sql file
# under a migrations/ folder is staged. See check-sql-param-naming.py for the
# exact rules + fix path.
SQL_CHECKER="$SCRIPT_DIR/check-sql-param-naming.py"
if [[ -f "$SQL_CHECKER" ]]; then
    staged_sql=$(git diff --cached --name-only --diff-filter=AM | grep -E '/migrations/.*\.sql$' || true)
    if [[ -n "$staged_sql" ]]; then
        echo "[pre-commit] SQL param naming check (migrations staged)..."
        if ! python3 "$SQL_CHECKER"; then
            # Hook prints its own detailed diagnostics + fix path to stderr.
            fail_count=$((fail_count + 1))
        else
            echo "✓ SQL params follow snake_case-with-p_-prefix convention"
        fi
    fi
fi

# ── More checks go here as they're added ──────────────────────────────

if [[ $fail_count -gt 0 ]]; then
    echo "" >&2
    echo "[pre-commit] $fail_count check(s) failed — commit blocked." >&2
    echo "             To bypass in an emergency (NOT for normal work): git commit --no-verify" >&2
    exit 1
fi

echo "[pre-commit] all checks passed"
exit 0
