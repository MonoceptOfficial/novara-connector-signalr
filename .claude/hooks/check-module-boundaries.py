#!/usr/bin/env python3
"""
check-module-boundaries.py — Claude PreToolUse hook for Novara module repos.

Blocks Edit/Write that violate platform architecture rules. Runs in <100ms.

PROTOCOL:
  - Reads tool input (JSON) from stdin
  - Inspects the proposed file content
  - Exit 0  → allow (silent or with stderr warning)
  - Exit 2  → BLOCK the tool call; stderr text is shown to Claude

DESIGN NOTES:
  - Only enforces inside <repo>/api/src/ and <repo>/web/src/ paths.
  - Skips: tests, docs, migrations, generated files, the Shell/Gateway/SDK itself.
  - Conservative: a false positive is worse than a missed violation.
    When in doubt, allow with a stderr warning rather than block.
  - Each check is independent — failing one doesn't prevent others from running.

EXIT CODES:
  0 — allowed (may print warnings to stderr)
  2 — BLOCKED — stderr is shown back to Claude as the reason
  Other — unexpected error (treated as allow + log; never blocks on script bug)
"""

import sys
import json
import re
import os
from pathlib import Path

# ─── Tool input parsing (Claude sends JSON on stdin) ───────────────────
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)  # malformed input = don't block

tool_name = data.get("tool_name", "")
tool_input = data.get("tool_input", {}) or {}

# Only enforce on Edit / Write (Edit gives new_string, Write gives content)
if tool_name not in ("Edit", "Write", "MultiEdit"):
    sys.exit(0)

file_path = tool_input.get("file_path", "")
if not file_path:
    sys.exit(0)

# Combine content from various tool inputs
if tool_name == "Write":
    content = tool_input.get("content", "")
elif tool_name == "MultiEdit":
    edits = tool_input.get("edits", [])
    content = "\n".join(e.get("new_string", "") for e in edits if isinstance(e, dict))
else:  # Edit
    content = tool_input.get("new_string", "")

if not content:
    sys.exit(0)

file_path_norm = file_path.replace("\\", "/")

# ─── Early, file-type-specific checks that must run BEFORE the general skip ───
# Some rules apply to files the general module/path filter would otherwise
# skip (e.g., .sql under /migrations/ is otherwise exempt). Handle those here
# and exit early if they're the only applicable rule.

# ── M1: Migration scope header (Phase A2) ────────────────────────────
# Every .sql under a migrations/ folder MUST start with
#   -- @scope: product | platform | both
# in the first ~15 lines. Without this the migration runner uses content
# heuristics to guess which DB to target, and guessing has historically
# misrouted migrations against the wrong DB (see rules/migration-scope.md).
_ext_early = os.path.splitext(file_path_norm)[1].lower()

def _print_block_header(rule_id: str, summary: str):
    """Shared bail-out printer for early-check violations."""
    print("", file=sys.stderr)
    print("============================================================", file=sys.stderr)
    print("  ARCHITECTURE VIOLATION — Edit BLOCKED by guardrail hook", file=sys.stderr)
    print("============================================================", file=sys.stderr)
    print(f"  File:   {file_path}", file=sys.stderr)
    print("", file=sys.stderr)
    print(f"  [{rule_id}] {summary}", file=sys.stderr)

if _ext_early == ".sql" and ("/migrations/" in file_path_norm or "/Migrations/" in file_path_norm):
    header_re = re.compile(r"^\s*--\s*@scope:\s*(product|platform|both)\b", re.MULTILINE)
    head = "\n".join(content.splitlines()[:15])
    if not header_re.search(head):
        _print_block_header("M1-MIGRATION-SCOPE-HEADER", "Migration missing scope header.")
        print("", file=sys.stderr)
        print("  Every .sql under migrations/ must declare its target DB", file=sys.stderr)
        print("  via an explicit header in the first ~10 lines:", file=sys.stderr)
        print("", file=sys.stderr)
        print("    -- @scope: product", file=sys.stderr)
        print("    -- Module: MyModule | Migration: NNN | Purpose: ...", file=sys.stderr)
        print("", file=sys.stderr)
        print("  Allowed values: product | platform | both", file=sys.stderr)
        print("  See .claude/rules/migration-scope.md for full rule + rationale.", file=sys.stderr)
        print("", file=sys.stderr)
        print("  Hook source: .claude/hooks/check-module-boundaries.py", file=sys.stderr)
        sys.exit(2)
    # Header present — fall through to further .sql checks (A3 + A5),
    # which apply to migrations too.

# ── M2: (RETIRED 2026-04-21) Column naming ────────────────────────────
# This hook used to block CREATE TABLE with underscored columns ("DAPPER_
# UNDERSCORE_SILENT_DROP risk"). That rule was retired: the SDK has set
# `Dapper.DefaultTypeMap.MatchNamesWithUnderscores = true` since 2026-04-15,
# and snake_case is now Novara's standard naming convention. Kept as a
# placeholder so section numbering (M3, M4, …) stays stable for readers
# cross-referencing this file — no runtime cost.

# ── M3: isdeleted filter required on SELECTs in function bodies (Phase A3) ──
# Functions in module migrations frequently SELECT from soft-deletable tables.
# Forgetting the isdeleted filter leaks deleted rows into API responses — the
# MISSING_ISDELETED_FILTER class (silent data leak). Heuristic:
#
#   - If the file contains CREATE [OR REPLACE] FUNCTION,
#   - AND contains at least one SELECT statement,
#   - AND does NOT contain `isdeleted` anywhere in the file,
#   - AND does NOT carry a file-level `-- no-softdelete` opt-out,
#   → BLOCK. Adding `WHERE isdeleted = false` is cheap; missing it is expensive.
#
# This is coarse (catches the "forgot entirely" class; doesn't verify each
# SELECT is properly filtered). A full SELECT-by-SELECT check belongs in
# /deep-scan, not a pre-edit hook.
if _ext_early == ".sql" and re.search(r"CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\b", content, re.IGNORECASE):
    # Opt-out at file level (first 15 lines)
    head_15 = "\n".join(content.splitlines()[:15])
    has_optout = "-- no-softdelete" in content or "/* no-softdelete" in content
    has_select = bool(re.search(r"\bSELECT\b", content, re.IGNORECASE))
    # Accept both naming conventions — legacy 'isdeleted' and modern 'is_deleted'
    # (snake_case adopted 2026-04-21). Dapper handles both in C# via MatchNames-
    # WithUnderscores, and new migrations (e.g. agentic 025/026) use is_deleted.
    _lower = content.lower()
    mentions_isdeleted = ("isdeleted" in _lower) or ("is_deleted" in _lower)
    # Only flag if there's a SELECT but no isdeleted reference anywhere AND no opt-out.
    # System-table inspection (pg_proc, information_schema, pg_catalog) is exempt
    # because those tables have no isdeleted column by design.
    system_table_pat = re.compile(r"\bFROM\s+(pg_|information_schema\.)", re.IGNORECASE)
    if has_select and not mentions_isdeleted and not has_optout:
        # If every SELECT is against a system catalog, skip — no user tables touched.
        selects = re.findall(r"\bSELECT\b[\s\S]{0,400}?;", content, re.IGNORECASE)
        user_select_found = False
        for s in selects:
            if system_table_pat.search(s):
                continue
            # Check whether SELECT targets a user table (schema.name pattern)
            if re.search(r"\bFROM\s+\w+\.\w+", s, re.IGNORECASE):
                user_select_found = True
                break
        if user_select_found:
            _print_block_header("M3-MISSING-ISDELETED-FILTER",
                "Function SQL has SELECT from user tables but NO isdeleted reference anywhere.")
            print("", file=sys.stderr)
            print("  Every SELECT on a soft-deletable table must include", file=sys.stderr)
            print("  `WHERE isdeleted = false` (or `isdeleted IS FALSE`).", file=sys.stderr)
            print("  Missing this leaks deleted rows into API responses —", file=sys.stderr)
            print("  the MISSING_ISDELETED_FILTER class (silent data leak).", file=sys.stderr)
            print("", file=sys.stderr)
            print("  Fix options:", file=sys.stderr)
            print("    1. Add `WHERE isdeleted = false` to every SELECT", file=sys.stderr)
            print("    2. For system-table inspection (pg_proc, information_schema),", file=sys.stderr)
            print("       the check auto-exempts — but this file seems to query a", file=sys.stderr)
            print("       schema-qualified user table.", file=sys.stderr)
            print("    3. Opt-out if the tables genuinely don't have isdeleted:", file=sys.stderr)
            print("       add `-- no-softdelete` comment anywhere in the file.", file=sys.stderr)
            print("", file=sys.stderr)
            print("  See .claude/rules/learned-errors.md § MISSING_ISDELETED_FILTER.", file=sys.stderr)
            sys.exit(2)

# ─── Identify what kind of file/repo we're in ───────────────────────────
def detect_module(p: str):
    """Return (module_kind, module_name) or (None, None).
       module_kind ∈ {'product-module', 'platform-module', 'shell', 'gateway', 'sdk', 'connector', 'viberhub', None}
    """
    # Product modules
    m = re.search(r"NovaraModules/novara-module-([a-z-]+)/", p)
    if m:
        name = m.group(1)
        # platform-scoped modules can use IPlatformDbContext legitimately.
        # agentic: reads shared agent definitions from agenthub schema in platform DB
        # (writes product-specific data to agent_ops in product DB) — hybrid by design.
        if name in ("rules", "appgateway", "agentic"):
            return ("platform-module", name)
        return ("product-module", name)
    if "/NovaraConnectors/" in p:
        return ("connector", None)
    if "/NovaraViberHub/" in p:
        return ("viberhub", None)
    if "/novara-shell/" in p:
        return ("shell", None)
    if "/NovaraSDK/" in p or "/novara-shell-sdk/" in p or "/novara-ui-kit/" in p:
        return ("sdk", None)
    if "/NovaraWorkspaceShell/" in p:
        return ("gateway", None)
    return (None, None)

module_kind, module_name = detect_module(file_path_norm)

# Only enforce in modules and connectors. Skip SDK/Shell/Gateway/ViberHub/unknown.
# (Those files have legitimate exceptions to most of these rules.)
if module_kind not in ("product-module", "platform-module"):
    sys.exit(0)

# Skip non-source files
SKIP_PATH_FRAGMENTS = (
    "/bin/", "/obj/", "/node_modules/", "/dist/", "/.git/",
    "/migrations/", "/Migrations/", "/documents/", "/docs/",
    "/.claude/", "/test/", "/Tests/", "/__tests__/", ".test.",
    ".spec.", "openapi.yaml", "asyncapi.yaml", "swagger.json"
)
if any(frag in file_path_norm for frag in SKIP_PATH_FRAGMENTS):
    sys.exit(0)

# Also skip .NET test projects (folder name ends in .Tests/ or .Test/)
if re.search(r"\.Tests?/", file_path_norm):
    sys.exit(0)

# Only check .cs, .ts, .sql files
ext = os.path.splitext(file_path_norm)[1].lower()
if ext not in (".cs", ".ts", ".sql"):
    sys.exit(0)

# ─── Rule checks ──────────────────────────────────────────────────────
violations = []
warnings = []

def add_violation(rule_id: str, msg: str, fix: str):
    violations.append((rule_id, msg, fix))

def add_warning(rule_id: str, msg: str):
    warnings.append((rule_id, msg))

# ── R1: Cross-module imports (C#) ────────────────────────────────────
if ext == ".cs" and module_name:
    pascal_self = module_name.replace("-", "").lower()
    for other in re.findall(r"^\s*using\s+Novara\.Module\.([A-Za-z]+)\s*;", content, re.MULTILINE):
        # Allow self-references and the SDK
        if other.lower().replace("_", "") == pascal_self:
            continue
        if other == "SDK":
            continue
        add_violation(
            "R1-CROSS-MODULE-IMPORT-CS",
            f"Cross-module import: 'using Novara.Module.{other};' in module '{module_name}'.",
            "Modules MUST NOT reference other modules directly.\n"
            "  - For events: inject IEventBus, call PublishAsync()\n"
            "  - For read-only data: inject ICrossModuleQuery, call QueryAsync('plan', 'feature', id)\n"
            "  See platform/architecture-decisions.md decision #11."
        )

# ── R2: Cross-module imports (TypeScript / Angular) ──────────────────
if ext == ".ts" and module_name:
    # @novara/module-X imports — only legal value is the SDK/UI-kit packages
    LEGAL_NOVARA_PKGS = {"@novara/shell-sdk", "@novara/ui-kit",
                         "@novara/bug-capture-core", "@novara/angular-bug-capture"}
    for imp in re.findall(r"from\s+['\"](@novara/[a-z0-9\-]+)['\"]", content):
        if imp in LEGAL_NOVARA_PKGS:
            continue
        # Self-reference is fine (rare but legal)
        if module_name.replace("-", "") in imp.replace("-", ""):
            continue
        add_violation(
            "R2-CROSS-MODULE-IMPORT-TS",
            f"Cross-module Angular import: '{imp}' in module '{module_name}'.",
            "Module web code may only import from @novara/shell-sdk, @novara/ui-kit,\n"
            "or its own module's local files. To get data from another module,\n"
            "make an HTTP call via ApiService — never import its components/services.\n"
            "  See platform/ui-kit-components.md and platform/sdk-services.md."
        )

# ── R3: HttpClient direct (C#) ───────────────────────────────────────
if ext == ".cs":
    # The actual HttpClient class import or constructor call
    if (re.search(r"using\s+System\.Net\.Http\s*;", content)
        and re.search(r"\bHttpClient\b", content)):
        add_violation(
            "R3-HTTPCLIENT-CS",
            "Direct HttpClient usage in module code.",
            "Modules don't call external services directly. Either:\n"
            "  - The data lives in another module → use ICrossModuleQuery / IEventBus\n"
            "  - The data lives in an external system → declare a Connector dependency\n"
            "    in your module manifest and consume it via IConnectorHandler\n"
            "  See platform/architecture-decisions.md decision #11 (Unified Connectors)."
        )

# ── R4: HttpClient direct (Angular) ──────────────────────────────────
if ext == ".ts":
    if re.search(r"from\s+['\"]@angular/common/http['\"]", content) and "HttpClient" in content:
        # SDK source is allowed (they wrap it); module code is not
        if "shell-sdk" not in file_path_norm:
            add_violation(
                "R4-HTTPCLIENT-NG",
                "Direct HttpClient import in module Angular code.",
                "Use ApiService from @novara/shell-sdk:\n"
                "  import { ApiService } from '@novara/shell-sdk';\n"
                "  this.api.moduleGet<MyType>('endpoint-path');\n"
                "ApiService handles auth tokens, base URL, error interceptor automatically.\n"
                "  See platform/sdk-services.md."
            )

# ── R5: IPlatformDbContext in product modules ────────────────────────
if ext == ".cs" and module_kind == "product-module":
    if re.search(r"\bIPlatformDbContext\b", content):
        add_violation(
            "R5-PLATFORM-DB-IN-PRODUCT-MODULE",
            f"Module '{module_name}' uses IPlatformDbContext but is product-scoped.",
            "Only the platform-scoped modules (rules, appgateway) may inject IPlatformDbContext.\n"
            "Product modules access platform data via the synced productcore.* tables\n"
            "(productcore.user, productcore.product) using IModuleDbContext.\n"
            "For settings, use IModuleSettingsStore. For cached lookups, ICacheService.\n"
            "  See platform/multi-tenancy.md and learned-errors.md MODULE_ACCESSES_PLATFORM_DB."
        )

# ── R6: Raw inline SQL in service code ───────────────────────────────
if ext == ".cs":
    # connection.ExecuteAsync("SELECT ...") or .QueryAsync("INSERT ...") with literal SQL
    raw_sql_pattern = re.compile(
        r"(connection|conn|cnn|_db|db)\.(Execute|Query|QuerySingle|QueryMultiple)\w*Async?\s*\(\s*[\"@]",
        re.IGNORECASE
    )
    if raw_sql_pattern.search(content):
        # Specific allow: AuditExecutionService inspects pg_proc/information_schema
        if "AuditExecutionService" not in file_path_norm:
            add_violation(
                "R6-RAW-INLINE-SQL",
                "Raw inline SQL detected in module service code.",
                "Mutations and queries must go through stored functions.\n"
                "  1. Create function: novara/{schema}.{name}() in your module's migration SQL\n"
                "  2. Add the function name to Constants/SpNames.cs\n"
                "  3. Call: _db.ExecuteProcedureAsync<T>(SpNames.YourFunction, new { ... })\n"
                "Inline SQL is acceptable ONLY for system inspection (pg_proc, information_schema).\n"
                "  See platform/database.md and learned-errors.md RAW_SQL_BYPASSES_SP."
            )

# ── R7: SELECT * in any SQL ──────────────────────────────────────────
if ext in (".cs", ".sql"):
    # Match SELECT * but skip COUNT(*), SUM(*), etc.
    if re.search(r"\bSELECT\s+\*\s+FROM\b", content, re.IGNORECASE):
        add_warning(
            "R7-SELECT-STAR",
            "SELECT * detected. List specific columns to avoid breaking when schema changes."
        )

# ── R8: Hardcoded URLs ───────────────────────────────────────────────
HARDCODED_URL_PATTERNS = [
    r"https?://localhost:\d+",
    r"https?://20\.219\.116\.\d+",  # the dev DB IP
    r"https?://10\.\d+\.\d+\.\d+",
]
if ext == ".ts":
    for pat in HARDCODED_URL_PATTERNS:
        if re.search(pat, content):
            # Skip comments
            non_comment = re.sub(r"//.*$|/\*.*?\*/", "", content, flags=re.DOTALL | re.MULTILINE)
            if re.search(pat, non_comment):
                add_violation(
                    "R8-HARDCODED-URL",
                    f"Hardcoded URL matching '{pat}' in module Angular code.",
                    "Use ApiService for HTTP calls (it knows the base URL).\n"
                    "If you need other env values, inject SHELL_ENVIRONMENT.\n"
                    "  See platform/sdk-services.md."
                )
                break

# ── R9: Hardcoded secrets ────────────────────────────────────────────
SECRET_PATTERNS = [
    (r"(?i)\b(api[_-]?key|apikey|secret|token|password|passwd|pwd)\s*[:=]\s*[\"'][A-Za-z0-9_\-/+=]{16,}[\"']",
     "secret-looking string assignment"),
    (r"sk-[A-Za-z0-9]{20,}", "OpenAI/Anthropic-style API key"),
    (r"ghp_[A-Za-z0-9]{30,}", "GitHub PAT"),
    (r"AKIA[0-9A-Z]{16}", "AWS access key ID"),
]
for pat, what in SECRET_PATTERNS:
    if re.search(pat, content):
        add_violation(
            "R9-HARDCODED-SECRET",
            f"Possible hardcoded secret detected ({what}).",
            "Secrets must come from configuration, never source code:\n"
            "  - C#: IConfiguration / IOptions / platform.AppSetting via IModuleSettingsStore\n"
            "  - Angular: never embed secrets; the Shell handles auth tokens\n"
            "If this is a false positive (e.g., a placeholder, test value), remove the\n"
            "secret-looking pattern or move it to a clearly-marked test/example file."
        )

# ── R10: Empty catch blocks ──────────────────────────────────────────
if ext == ".cs":
    # catch (...) { } or catch { }
    empty_catch = re.compile(r"catch\s*(?:\([^)]*\))?\s*\{\s*\}", re.MULTILINE)
    if empty_catch.search(content):
        add_violation(
            "R10-EMPTY-CATCH",
            "Empty catch block detected — silent exception swallowing.",
            "Empty catches hide bugs. Choose:\n"
            "  - Let it propagate: remove the try/catch entirely\n"
            "  - Log + rethrow: catch (Exception ex) { _logger.LogError(ex, ...); throw; }\n"
            "  - Non-critical fire-and-forget: SafeExecute.FireAndForget(() => ..., _logger)\n"
            "  See platform/resilience.md and learned-errors.md EMPTY_CATCH_SILENT."
        )

# ── R11: Magic strings for SP names ──────────────────────────────────
if ext == ".cs":
    # ExecuteProcedureAsync("string-literal", ...) instead of constant
    sp_literal = re.compile(
        r'ExecuteProcedure\w*Async\s*<[^>]*>\s*\(\s*"[^"]+"',
    )
    if sp_literal.search(content):
        add_warning(
            "R11-SP-MAGIC-STRING",
            "Stored procedure name as string literal. Add to Constants/SpNames.cs."
        )

# ── R12: Async public methods missing CancellationToken ──────────────
# Phase A1 (2026-04-20): flipped warn → block. Public async methods without
# CancellationToken exhaust pools under load and don't cancel on client
# disconnect — real incident class. Opt-out with `// no-ct` on the line
# above the method signature for documented exceptions (rare).
if ext == ".cs" and "Service.cs" in file_path_norm:
    method_pattern = re.compile(
        r"public\s+(?:async\s+)?Task(?:<[^>]+>)?\s+(\w+)\s*\(([^)]*)\)",
        re.MULTILINE
    )
    # Per-method exempt marker: a `// no-ct` comment within 3 lines before
    # the method signature allows documented non-cancellable methods (e.g.,
    # startup/shutdown hooks that shouldn't respond to caller cancellation).
    lines = content.splitlines()
    for m in method_pattern.finditer(content):
        method_name = m.group(1)
        params = m.group(2)
        if "CancellationToken" in params:
            continue
        # Check 3 preceding lines for the opt-out marker.
        start_line = content[:m.start()].count("\n")
        exempt = any(
            "// no-ct" in lines[i]
            for i in range(max(0, start_line - 3), start_line)
            if i < len(lines)
        )
        if exempt:
            continue
        add_violation(
            "R12-MISSING-CANCELLATION-TOKEN",
            f"Public async method '{method_name}' missing CancellationToken parameter.",
            "Add `CancellationToken ct = default` as the last parameter and pass "
            "through to every ExecuteProcedureAsync / other async call. "
            "Opt-out: place `// no-ct` on the line above the method signature if "
            "the method genuinely cannot be cancelled (rare; document why)."
        )
        break  # one violation per file is enough

# ── R13: SP coupling comment required above ExecuteProcedureAsync (Phase A4) ──
# Every Dapper SP call MUST have a `// SP: {schema}.{name}({p_name TYPE, ...})`
# comment within 3 lines above it. Without this:
#   - When the SP signature changes, C# code silently breaks at runtime (no
#     compile error); see learned-errors.md § SP_COUPLING_COMMENT_WRONG.
#   - Reviewers can't see the contract — they'd have to open SpNames.cs +
#     the .sql file to understand what a Dapper call touches.
#
# The comment shape is loose — `// SP:` prefix is enough to prove the
# developer thought about it. Progressive-hardening ratchets quality over time.
if ext == ".cs" and "/Services/" in file_path_norm:
    # Find every ExecuteProcedureAsync / ExecuteProcedureSingleAsync call.
    # Also catches ExecuteProcedure (sync) which is rarer but worth covering.
    exec_pat = re.compile(
        r"^(\s*)(?:(?:await|var|return|_)\s+)?[^/\n]*?\b_?[a-zA-Z]+\.ExecuteProcedure\w*Async?\s*\(",
        re.MULTILINE
    )
    lines = content.splitlines()
    line_starts = []
    offset = 0
    for ln in lines:
        line_starts.append(offset)
        offset += len(ln) + 1  # +1 for \n

    def _line_index_for(pos: int) -> int:
        # Binary search could work; linear is fine for typical service file size
        for i, start in enumerate(line_starts):
            if start > pos:
                return i - 1
        return len(line_starts) - 1

    missing_comment_lines = []
    for m in exec_pat.finditer(content):
        call_line = _line_index_for(m.start())
        # Look at up to 5 preceding non-blank lines for a `// SP:` comment.
        found = False
        checked = 0
        i = call_line - 1
        while i >= 0 and checked < 5:
            line = lines[i].strip()
            if not line:
                i -= 1
                continue
            checked += 1
            if line.startswith("//") and "SP:" in line:
                found = True
                break
            # Allow multi-line comment styles: `// SP: …` → `// returns: …` then empty
            if line.startswith("//") and ("Returns:" in line or "returns:" in line):
                # keep looking upward — returns-comment is usually the 2nd line of the SP block
                i -= 1
                continue
            # If we hit non-comment non-whitespace line before finding the SP comment, stop.
            if not line.startswith("//") and not line.startswith("/*") and not line.startswith("*"):
                break
            i -= 1
        if not found:
            missing_comment_lines.append(call_line + 1)  # 1-based for humans

    if missing_comment_lines:
        # Keep the first few; more than 3 = same pattern repeated, one message is enough
        add_violation(
            "R13-MISSING-SP-COUPLING-COMMENT",
            f"Dapper SP call(s) at line(s) {', '.join(map(str, missing_comment_lines[:5]))} missing inline SP coupling comment.",
            "Add above each ExecuteProcedureAsync call:\n"
            "    // SP: {schema}.{functionname}(p_param1 TYPE, p_param2 TYPE, ...)\n"
            "    // Returns: {EntityType} row(s)  |  void  |  INTEGER id\n"
            "  When the SP signature changes, reviewers catch it at diff time\n"
            "  rather than at runtime. See learned-errors.md § MISSING_SP_COUPLING_COMMENT\n"
            "  and § SP_COUPLING_COMMENT_WRONG for the cost of skipping this."
        )

# ═══════════════════════════════════════════════════════════════════════
#   Settings-discipline rules R20–R23 (see .claude/rules/settings-discipline.md)
#
# Every tunable value must be declared in a SettingField manifest and read via
# IModuleSettings / IGatewaySettingsReader / IConnectorConfigStore. Hardcoding
# them traps customers behind redeploys and skips validation + audit.
#
# A line carrying `// no-tune` is exempted — reserved for genuinely non-tunable
# constants (protocol values, SDK version strings) where the setting abstraction
# would add no value. Every exemption is visible in PR review.
# ═══════════════════════════════════════════════════════════════════════

def _line_exempt(line: str) -> bool:
    """True if the line carries a // no-tune opt-out marker."""
    return "// no-tune" in line or "/* no-tune" in line

def _iter_relevant_lines(src: str):
    """Yield (line_text, is_comment_only) for every line in src. Skips files in
    SDK/Shell/Gateway handled earlier; callers only reach this for module code."""
    for line in src.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        # Skip whole-line comments — they're allowed to mention timeouts, URLs, etc.
        if stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
            continue
        yield line

# ── R20: Hardcoded timeouts in service code ──────────────────────────
if ext == ".cs" and "/Services/" in file_path_norm:
    # TimeSpan.FromXxx(<literal>) with a numeric literal
    ts_pat = re.compile(
        r"TimeSpan\.From(?:Milliseconds|Seconds|Minutes|Hours)\s*\(\s*[0-9]+(?:\.[0-9]+)?\s*\)"
    )
    # HttpClient { Timeout = ... } with literal
    httpclient_pat = re.compile(
        r"(?:HttpClient|http)\s*\.?\s*Timeout\s*=\s*TimeSpan\.From"
    )
    # Task.Delay(<literal ms>)
    delay_pat = re.compile(r"Task\.Delay\s*\(\s*[0-9]{4,}\b")

    for line in _iter_relevant_lines(content):
        if _line_exempt(line):
            continue
        if ts_pat.search(line) or httpclient_pat.search(line) or delay_pat.search(line):
            add_violation(
                "R20-HARDCODED-TIMEOUT",
                "Hardcoded timeout in service code.",
                "Declare as SettingField with Min/Max and read via "
                "IModuleSettings.GetSecondsAsync(..., fallback). "
                "Opt-out: `// no-tune` on the same line for non-tunable constants. "
                "See settings-discipline.md."
            )
            break

# ── R21: Hardcoded retry counts / batch sizes / limits ──────────────
if ext == ".cs" and ("/Services/" in file_path_norm or "Worker" in file_path_norm):
    # private const int MaxXxx = <literal>, private static readonly int Yyy = <literal>
    # where name looks like a tunable.
    TUNABLE_NAME_RX = re.compile(
        r"\b(?:max|min|default)?(?:retries|retry|attempts|batch|pagesize|limit|threshold|concurrency|maxconcurrent)\w*\b",
        re.IGNORECASE
    )
    const_pat = re.compile(
        r"(?:private|internal)\s+(?:static\s+)?(?:readonly\s+)?(?:const\s+)?(?:int|long|double)\s+(\w+)\s*=\s*[0-9]+\s*;"
    )
    for line in _iter_relevant_lines(content):
        if _line_exempt(line):
            continue
        m = const_pat.search(line)
        if m and TUNABLE_NAME_RX.search(m.group(1)):
            add_violation(
                "R21-HARDCODED-TUNABLE",
                f"Hardcoded tunable constant '{m.group(1)}' looks like it belongs in a SettingField.",
                "Declare with Min/Max/Required in the module manifest and read via "
                "IModuleSettings.GetIntAsync(..., fallback). "
                "Opt-out: `// no-tune` on the same line for non-tunable values. "
                "See settings-discipline.md."
            )
            break

# ── R22: Hardcoded external URLs in service code ────────────────────
if ext == ".cs" and "/Services/" in file_path_norm:
    # Absolute http(s) URLs embedded in string literals inside service code.
    # Connectors are exempt (their whole point is to hold endpoint URLs in their
    # manifest — the LITERAL might appear as a DefaultValue).
    url_pat = re.compile(r'"https?://[^\s"]+"')
    for line in _iter_relevant_lines(content):
        if _line_exempt(line):
            continue
        m = url_pat.search(line)
        if not m:
            continue
        url = m.group(0)
        # Allow obvious non-endpoints (schemas, namespaces, example URLs)
        if any(x in url.lower() for x in ("schemas.xmlsoap.org", "w3.org", "localhost:", "example.com")):
            continue
        add_violation(
            "R22-HARDCODED-EXTERNAL-URL",
            f"Hardcoded external URL in service code: {url}.",
            "External endpoints belong in a Connector's ConfigFields (Type=Url, Required). "
            "Modules reach them via IConnectorActionInvoker. "
            "Opt-out: `// no-tune` on the same line for example URLs or protocol schemas. "
            "See settings-discipline.md."
        )
        break

# ── R23: const/readonly string that smells like config ──────────────
# Values that look like URLs, email addresses, or settings-like strings embedded
# as constants. These trap customers behind redeploys.
if ext == ".cs" and "/Services/" in file_path_norm:
    config_const_pat = re.compile(
        r'(?:private|internal)\s+(?:static\s+)?(?:readonly\s+)?(?:const\s+)?string\s+(\w+)\s*=\s*"([^"]+)"\s*;'
    )
    # Names that suggest deployment-specific values
    CONFIG_NAME_RX = re.compile(
        r"\b(url|endpoint|baseaddress|host|server|email|sender|recipient)\b",
        re.IGNORECASE
    )
    for line in _iter_relevant_lines(content):
        if _line_exempt(line):
            continue
        m = config_const_pat.search(line)
        if not m:
            continue
        name, value = m.group(1), m.group(2)
        if CONFIG_NAME_RX.search(name):
            add_violation(
                "R23-HARDCODED-CONFIG-CONSTANT",
                f"Constant '{name}' looks like deployment-specific config "
                f"(value: {value[:60]}...).",
                "Move to a SettingField so admins can tune without a redeploy. "
                "Opt-out: `// no-tune` on the same line for non-tunable protocol constants. "
                "See settings-discipline.md."
            )
            break

# ── R14: Pagination required on list service methods (Phase B1) ──────
# Methods returning IEnumerable<T>/List<T>/T[] where T looks like an entity
# must accept PaginationParams. Without pagination, a product with 50k rows
# causes memory exhaustion or 30-second responses — UNBOUNDED_LIST_RETURN class.
#
# Opt-out: methods named GetAll/ListAll/GetBy* that genuinely need all rows
# (lookups under 500 items) can place `// no-page` above the signature.
if ext == ".cs" and "Service.cs" in file_path_norm:
    list_return_pat = re.compile(
        r"public\s+(?:async\s+)?Task<(?:IEnumerable|List|IReadOnlyList|ICollection)<([A-Z]\w*)>>\s+(\w+)\s*\(([^)]*)\)",
        re.MULTILINE
    )
    offending = []
    for m in list_return_pat.finditer(content):
        entity_type = m.group(1)
        method_name = m.group(2)
        params = m.group(3)
        # Exempt primitive types (List<int>, List<string>) — likely ID lists, OK.
        if entity_type in ("Int32", "Int64", "String", "Guid", "Decimal", "Double"):
            continue
        # Opt-out: `// no-page` marker in the 3 lines above the signature
        start_line = content[:m.start()].count("\n")
        exempt = any(
            "// no-page" in (lines[i] if i < len(lines) else "")
            for i in range(max(0, start_line - 3), start_line)
        )
        if exempt:
            continue
        # Has PaginationParams / PagedResponse / PageSize in signature?
        if any(tok in params for tok in ("PaginationParams", "PagedRequest", "PageSize", "pageSize", "Page ")):
            continue
        offending.append((method_name, entity_type))
    if offending:
        names = ", ".join(f"{n}(…):List<{t}>" for n, t in offending[:5])
        add_violation(
            "R14-UNBOUNDED-LIST-RETURN",
            f"Service method(s) return unbounded lists without pagination: {names}.",
            "Switch return type to PagedResponse<T> and accept PaginationParams:\n"
            "    Task<PagedResponse<T>> GetListAsync(PaginationParams paging, CancellationToken ct = default)\n"
            "  SP adds `p_page INT`, `p_pagesize INT`, returns `COUNT(*) OVER() AS totalcount`.\n"
            "  Opt-out (small fixed lookups < 500 rows): `// no-page` above the signature.\n"
            "  See learned-errors.md § UNBOUNDED_LIST_RETURN."
        )

# ── R15: Ban `: any[]` in Angular component class fields (Phase B2) ──────
# Component class using `any[]` for list fields loses type safety —
# UNTYPED_UI_MODEL class. Angular silently ignores template-access mismatches,
# rendering `undefined` instead of showing a compile error when fields rename.
if ext == ".ts" and ("/components/" in file_path_norm or ".component.ts" in file_path_norm):
    # Match:   items: any[] = []
    # Match:   items: any = []
    # Allow non-component service classes (skipped by path filter above)
    any_array_pat = re.compile(
        r"^\s+(?:public\s+|private\s+|protected\s+)?(\w+)\s*:\s*any\s*\[\]\s*(?:=|;)",
        re.MULTILINE
    )
    offenders = []
    for m in any_array_pat.finditer(content):
        # Opt-out: // any-ok on the same line
        line_start = content.rfind("\n", 0, m.start()) + 1
        line_end = content.find("\n", m.end())
        line = content[line_start:line_end if line_end > -1 else len(content)]
        if "// any-ok" in line:
            continue
        offenders.append(m.group(1))
    if offenders:
        add_violation(
            "R15-UNTYPED-UI-MODEL",
            f"Component class field(s) declared as any[]: {', '.join(offenders[:5])}.",
            "Create a typed interface in models/{module}.models.ts and use it:\n"
            "    import { Signal } from '../../models/ingest.models';\n"
            "    signals: Signal[] = [];\n"
            "  Angular templates then get autocomplete + compile-time checking when fields rename.\n"
            "  Opt-out: `// any-ok` on the same line (rare — use for third-party JSON passthroughs).\n"
            "  See learned-errors.md § UNTYPED_UI_MODEL."
        )

# ── R16: Task.Run in service code must use SafeExecute.FireAndForget (Phase B3) ──
# Raw `_ = Task.Run(...)` or `Task.Run(...)` in service code silently swallows
# exceptions — FIRE_AND_FORGET_UNOBSERVED class. Exception gets GC'd as
# an unobserved task; no log, no alert, data lost.
if ext == ".cs" and "/Services/" in file_path_norm:
    # Find Task.Run call sites
    task_run_pat = re.compile(r"\bTask\.Run\s*\(", re.MULTILINE)
    for m in task_run_pat.finditer(content):
        # Grab surrounding 2 lines for context — is SafeExecute.FireAndForget present?
        line_start = content.rfind("\n", 0, m.start()) + 1
        line_end = content.find("\n", m.end())
        context_start = max(0, line_start - 200)
        snippet = content[context_start:line_end if line_end > -1 else len(content)]
        # Opt-out: `// no-fnf` on the same line (documented exception)
        line = content[line_start:line_end if line_end > -1 else len(content)]
        if "// no-fnf" in line:
            continue
        # If the Task.Run sits inside a SafeExecute.FireAndForget(...), allow.
        if "SafeExecute.FireAndForget" in snippet:
            continue
        # If the Task.Run result is awaited or returned (real async work, not fire-and-forget), allow.
        if "await Task.Run" in snippet or "return Task.Run" in snippet:
            continue
        # Otherwise: violation.
        add_violation(
            "R16-FIRE-AND-FORGET-UNOBSERVED",
            "Raw Task.Run(...) in service code — exception will be silently unobserved.",
            "Wrap in SafeExecute.FireAndForget for non-critical side effects:\n"
            "    SafeExecute.FireAndForget(() => DispatchWorkItem(item), _logger, nameof(DispatchWorkItem), ModuleId);\n"
            "  Or, for tracked/retriable work, enqueue via IJobService.EnqueueAsync().\n"
            "  Raw Task.Run discards the returned Task and its exception — the class\n"
            "  LEARN ABOUT REAL INCIDENT: learned-errors.md § FIRE_AND_FORGET_UNOBSERVED.\n"
            "  Opt-out (rare): `// no-fnf` on the same line with a comment explaining why."
        )
        break  # one violation per file is enough

# ─── Output handling ──────────────────────────────────────────────────
# Force UTF-8 stderr so messages render the same on Windows / macOS / Linux.
# (Windows Python defaults to cp1252; ascii box-drawing chars work everywhere.)
import io as _io
try:
    sys.stderr = _io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)
except Exception:
    pass

# Warnings always print to stderr (visible to Claude as informational)
if warnings:
    print("[!] Architecture warnings (allowed but noted):", file=sys.stderr)
    for rule_id, msg in warnings:
        print(f"  [{rule_id}] {msg}", file=sys.stderr)

# Violations BLOCK the edit
if violations:
    print("", file=sys.stderr)
    print("============================================================", file=sys.stderr)
    print("  ARCHITECTURE VIOLATION -- Edit BLOCKED by guardrail hook", file=sys.stderr)
    print("============================================================", file=sys.stderr)
    print(f"  File:   {file_path}", file=sys.stderr)
    print(f"  Module: {module_name or 'n/a'}", file=sys.stderr)
    print("", file=sys.stderr)
    for i, (rule_id, msg, fix) in enumerate(violations, 1):
        print(f"  {i}. [{rule_id}] {msg}", file=sys.stderr)
        for line in fix.splitlines():
            print(f"     {line}", file=sys.stderr)
        print("", file=sys.stderr)
    print("  Fix the violation(s) and try the edit again.", file=sys.stderr)
    print("  Hook source: .claude/hooks/check-module-boundaries.py", file=sys.stderr)
    print("  Documentation: .claude/rules/platform/architecture-enforcement.md", file=sys.stderr)
    sys.exit(2)

sys.exit(0)
