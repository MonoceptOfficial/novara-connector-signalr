# Customer Deployment Principles — Binding Rules

Two customers are ready to deploy. Every line of code must be written with this reality in mind.

## 1. No New Portals — One Novara UI

Do NOT create separate customer portals, admin dashboards, or alternative UIs. Novara has ONE frontend (Shell UI at `NovaraWorkspaceShell/novara-shell/web`). Scope visibility using roles and permissions, not separate apps. This keeps the codebase maintainable and deployable.

## 2. Credentials Are Per-Tenant, Never Shared

Every customer brings their own:
- **Claude/LLM API keys** — stored in `platform.LlmProvider` with TenantId
- **Azure Blob / Storage credentials** — per-tenant in `platform.AppSetting` with TenantId
- **SSO configuration** — per-tenant Azure AD / SAML settings
- **GitHub/SCM tokens** — per-tenant in `platform.ProductSetting`

**Rules:**
- NEVER use a shared API key across tenants. One customer's Claude usage must not affect another's billing or rate limits.
- NEVER store credentials in `appsettings.json` for production. Config file is for local dev only.
- ALL credential tables MUST have TenantId. No global secrets except the platform's own JWT key and DB connection.
- Credentials in DB MUST be encrypted at rest (AES-256). Store encryption key in environment variable, not in DB.
- API responses MUST mask credentials. Only first 6 + last 4 chars visible. Full value never returned via API.

## 3. Configuration Hierarchy

For any setting, the resolution order is:
```
Tenant Override (platform.AppSetting WHERE TenantId = @TenantId)
  → Product Override (platform.ProductSetting WHERE ProductId AND TenantId)
    → Platform Default (platform.AppSetting WHERE TenantId IS NULL)
      → appsettings.json (local dev fallback ONLY)
```

Never skip levels. A tenant can override any platform default. A product can override any tenant default.

## 4. Deployable as a Unit

Novara must be deployable with:
```
1. API binary (dotnet publish output)
2. Database migration scripts (versioned, idempotent)
3. appsettings.template.json (no secrets, just structure)
4. Agent installer package
5. One-page setup guide
```

No manual SQL scripts. No "ask the developer" steps. A competent IT team should deploy in under 1 hour.

## 5. Secrets Must Never Appear In

- Git history (appsettings.json with real values is BANNED in commits)
- API responses (mask all credential fields)
- Log files (scrub connection strings, API keys, tokens from all logging)
- Error messages (never include credential values in exceptions)
- Frontend localStorage/sessionStorage
- Browser network tab (mask in request/response bodies)

## 6. Existing Features Must Work End-to-End

Before adding new features, ensure every existing endpoint works with real data for a customer:
- No mock data returns
- No NotImplementedException
- No empty catch blocks hiding failures
- No TODO comments in the request path

If a feature isn't ready, disable it via feature flag — don't ship broken code.

## 7. Multi-Tenant Data Isolation (Reinforced)

This is not optional. It's a legal requirement once customers are on the platform.
- Every SELECT has WHERE TenantId = @TenantId
- Every SP accepts @TenantId as first parameter
- Every service method receives tenantId from middleware
- NO cross-tenant data leakage — ever

Test: If Tenant A's admin runs every API endpoint, they must NEVER see Tenant B's data, settings, users, or activity.

## 8. Agent Credentials Isolation

CodeFarm and Application agents installed at customer sites:
- Each agent authenticates with a tenant-scoped API key (not the user's JWT)
- Agent API key is generated per tenant, rotatable, revocable
- Agent can ONLY access data for its own tenant
- Agent credentials are separate from user credentials
- If an agent key is compromised, revoking it doesn't affect users

## 9. Build Order for Customer Readiness

Priority of what to build/fix BEFORE customers deploy:
```
1. Remove hardcoded secrets from appsettings.json (move to env vars)
2. Add TenantId to AppSetting, ProductSetting, LlmProvider tables
3. Add credential encryption in DB
4. Fix existing broken features (#68, #77 — magic strings, NotImplementedException)
5. Database migration runner (customers need to upgrade)
6. Feature flags (hide incomplete features from customers)
7. Per-tenant LLM provider configuration
8. Agent authentication (tenant-scoped API keys)
```

Everything else (new AI features, CodeFarm, marketplace) comes AFTER customers can safely run the platform.

## 10. What Customers See vs What We See

Until customer portal (#41) is built, use permission-based visibility:
- **Customer Admin** — sees their products, features, settings, dashboards
- **Customer User** — sees assigned work, features, issues
- **Novara Admin (us)** — sees all tenants, platform settings, system health
- **Novara Consultant** — sees assigned customer tenants only

Permissions already exist in `Permissions.cs`. Extend them, don't create separate apps.

## 11. UI Design Philosophy

Use the existing Shell UI (Angular 21 + @novara/ui-kit) design system for ALL new features. Do NOT:
- Create new design systems or component libraries
- Introduce new CSS frameworks or styling approaches
- Build separate portals or micro-frontends
- Change the existing navigation structure without discussion

DO:
- Follow existing component patterns (cards, tables, modals, toastr)
- Use the existing sidebar + content layout
- Add new menu items under existing categories
- Extend existing pages with new tabs/sections rather than creating new pages

## 12. Autonomous Agent Execution Protocol

When running features sequentially without human supervision:

**For each feature:**
1. Load feature context (description, tasks, prior sessions)
2. Develop and test the feature
3. Take screenshots of key UI states → save to `.claude/screenshots/{feature-id}/`
4. Update Knowledge Bank with what was built
5. Add journal entry summarizing work done
6. Commit and push
7. Park session
8. If a decision or permission is needed that blocks progress:
   - Add the question/blocker as a journal entry on the feature
   - Mark it in PendingItems
   - Move to the next feature — do NOT wait
9. Start new session for next feature

**Screenshot convention:**
- Folder: `.claude/screenshots/{feature-id}/`
- Naming: `{step-number}-{description}.png`
- Example: `84-01-appsettings-template.png`, `84-02-env-vars-configured.png`
