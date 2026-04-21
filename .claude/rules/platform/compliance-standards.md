# Compliance Standards — Binding Development Rules

Novara targets enterprise customers. These rules ensure we don't break compliance later. They apply to ALL code, not just new features.

## Standards We Must Follow

| Standard | Why | When |
|----------|-----|------|
| OWASP Top 10 | Industry baseline, auditors check this first | NOW — every PR |
| GDPR/CCPA | Legal obligation for any EU/CA customer data | NOW — in code patterns |
| SOC 2 Type II | US enterprise sales gate | Building evidence from now |
| ISO 27001 | International enterprise gate | Pursue with SOC 2 for 30-40% savings |

## Binding Code Rules

### 1. Authentication & Access Control (SOC 2 CC6.1, ISO A.5.15)
- Every data endpoint MUST require `[Authorize]` — no anonymous access
- Every endpoint MUST check permissions via `Permissions.cs` — not just `[Authorize]`
- Admin actions MUST require elevated permission checks
- Permission changes MUST be audit-logged
- Failed logins MUST be logged with: UserId (attempted), IP, timestamp, user agent
- Account lockout after 5 consecutive failures (configurable per tenant)
- Session idle timeout max 30 min, absolute timeout max 24 hours

### 2. Encryption (SOC 2 CC6.3, ISO A.8.24)
- TLS 1.2+ enforced — reject HTTP in production
- AES-256 for secrets at rest in DB (API keys, connection strings, tokens)
- Encryption keys in environment variables or Key Vault — NEVER in DB or appsettings.json
- Hash passwords with bcrypt/Argon2 — NEVER MD5/SHA1/SHA256 alone
- Use `RandomNumberGenerator` for tokens — NEVER `Random`
- NEVER implement custom crypto — use established libraries

### 3. Audit Trail (SOC 2 CC7.1, ISO A.8.15)
- Every data mutation (create, update, delete) MUST write to audit log
- Audit entry MUST include: TenantId, UserId, Action, EntityType, EntityId, OldValue JSON, NewValue JSON, Timestamp, IPAddress, CorrelationId
- Audit logs are APPEND-ONLY — no UPDATE or DELETE on AuditLog
- Audit log retention: minimum 1 year, configurable per tenant
- Configuration changes MUST be audit-logged
- NEVER disable audit logging, even in development

### 4. Data Isolation (ISO A.8.3, GDPR Article 28)
- Every query MUST filter by TenantId (existing rule, reinforced)
- Blob storage paths: `{TenantId}/{EntityType}/{EntityId}/{filename}` — never flat
- API responses MUST be filtered by requesting user's permissions — no over-fetching
- Row-level security: users see only data they own or are explicitly granted

### 5. Input Validation & Security (OWASP Top 10)
- Parameterized queries ONLY — never string concatenation for SQL (Dapper enforces this)
- Server-side input validation on ALL endpoints: length, type, format, allowed chars
- Output encoding for all user-generated content in responses
- CORS: only known origins — NEVER `Access-Control-Allow-Origin: *` in production
- Content-Type headers set correctly on all responses
- No `dynamic` return types from public API endpoints — use typed DTOs
- Rate limiting on all public endpoints (default: 100 req/min per user, 1000 req/min per tenant)

### 6. Security Headers (OWASP, SOC 2)
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Strict-Transport-Security: max-age=31536000; includeSubDomains`
- `X-XSS-Protection: 0` (rely on CSP instead)
- `Content-Security-Policy: default-src 'self'`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: camera=(), microphone=(), geolocation=()`

### 7. Logging Rules (ISO A.8.15, SOC 2 CC7.2)
- Structured logging (JSON) with: Timestamp, Level, CorrelationId, TenantId, UserId, Action
- NEVER log: passwords, full API keys, tokens, connection strings, PII
- Mask secrets to first 6 + last 4 chars when logging
- Security events (login, logout, permission change, password reset) logged separately
- Log retention: minimum 90 days application logs, minimum 1 year audit logs

### 8. GDPR Data Subject Rights
- Must support data export per user (all tables with user's PII)
- Must support data erasure per user (anonymize or delete across all tables)
- Must log what customer data is sent to LLM APIs (Article 28/30 — processor obligation)
- LLM data processing: log EntityType, data categories sent, provider, timestamp — NOT the actual content
- Data retention periods must be configurable per tenant
- Consent management: record what user agreed to and when

### 9. Secrets Management (SOC 2 CC6.3, ISO A.8.9)
- API responses MUST mask credential fields (first 6 + last 4 visible, rest asterisks)
- NEVER store secrets in git (appsettings.json with real values is BANNED)
- NEVER log secrets in error messages, exceptions, or stack traces
- NEVER return different HTTP status for "user exists" vs "doesn't exist" (enumeration attack)
- NEVER store session tokens in URL query parameters
- Swagger MUST be disabled in production

### 10. Dependency & Supply Chain Security (OWASP A06, ISO A.8.25)
- `dotnet list package --vulnerable` must pass in CI/CD
- No packages with known critical/high CVEs
- NuGet package lock files committed
- Static analysis (Roslyn analyzers) on every build
- No secrets in git history — scan with git-secrets or equivalent

## Anti-Patterns That Break Compliance

```csharp
// BANNED — SQL injection risk
var sql = $"SELECT * FROM Users WHERE Name = '{input}'";

// BANNED — logging secrets
_logger.LogInformation("API Key: {Key}", apiKey);

// BANNED — returning secrets
return new { ApiKey = settings.ClaudeApiKey };

// BANNED — anonymous endpoint with data
[AllowAnonymous]
[HttpGet("users")] // NO — data endpoints must be authenticated

// BANNED — wildcard CORS in production
options.AddPolicy("allow", b => b.AllowAnyOrigin());

// BANNED — no permission check
[HttpDelete("issues/{id}")] // Must check Permissions.IssuesDelete
```

## When Adding New Features — Compliance Checklist

Before any feature ships, verify:
- [ ] All endpoints have `[Authorize]` + permission check
- [ ] All mutations write to audit log
- [ ] All queries filter by TenantId
- [ ] No secrets in responses (masked)
- [ ] No PII in logs
- [ ] Input validated server-side
- [ ] Rate limiting applied
- [ ] If feature sends data to LLM: data processing logged
