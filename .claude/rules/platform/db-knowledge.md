# Knowledge Source — Database First

## Rule: ALL knowledge lives in the database. Markdown files are instructions only.

At session start, load knowledge from the Knowledge Bank API:

```bash
source .claude/db-config.sh
JWT=$(get_jwt)

# Load all system architecture knowledge
curl -sk -X POST "$API_BASE/kb/pages/bulk-by-slug" \
  -H "Authorization: Bearer $JWT" -H "Content-Type: application/json" \
  -d '{"productId":1,"slugs":[
    "platform-overview","data-layer","auth-sessions","desktop-architecture",
    "ai-integration","gotchas","progressive-hardening","platform-maturity",
    "knowledge-methodology","coding-standards","database-design",
    "architecture-decisions","compliance-standards","customer-deployment",
    "multi-tenancy","query-performance","resilience","systems-thinking",
    "api-patterns","error-monitoring","git-workflow","issue-fix-lifecycle"
  ]}'
```

## What markdown files are for (ONLY these purposes):
- Claude behavioral instructions ("at session start, do X")
- Session lifecycle rules ("how to orient, how to close")
- Tool-specific config (hooks, keybindings)

## What markdown files are NOT for:
- Architecture knowledge → read from KB slug "architecture-decisions"
- Coding standards → read from KB slug "coding-standards"
- Database design → read from KB slug "database-design"
- Compliance rules → read from KB slug "compliance-standards"
- Any evolving knowledge → ALWAYS database

## Configuration constants:
All infrastructure config is in `.claude/db-config.sh`:
- Database: DB_SERVER, DB_NAME, DB_USER, DB_PASS
- Azure: AZURE_RG, AZURE_API_APP, AZURE_WEB_URL
- Local: LOCAL_API_URL, LOCAL_WEB_URL
- API: API_BASE, PRODUCT_ID, USER_ID
- Functions: run_sql(), deploy_api(), deploy_web(), get_jwt()

NEVER hardcode these values in scripts or code. Always source from db-config.sh.
