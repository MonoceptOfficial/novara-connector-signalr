# Multi-Tenancy — Deployment-Level Isolation

## Architecture: One Deployment = One Tenant

Novara isolates tenants at the **deployment boundary**, not the database column level.

- **Each enterprise** gets its own Novara deployment (API + UI + DB server)
- **Each product** gets its own database within that deployment
- **No TenantId column** in product databases — the database IS the tenant boundary
- **No ProductId column** in product databases — the database IS the product boundary

## Where TenantId Lives

### Platform DB (NovaraPlatformDB) — KEEPS TenantId
The platform database manages cross-product routing, auth, users, and settings.
TenantId stays here because platform DB may serve multiple tenants in shared SaaS mode.

Tables with TenantId: `platform.tenant`, `platform.product`, `platform.appsetting`, etc.

### Product DB (per-product) — NO TenantId, NO ProductId
Each product gets its own database via `ProductDatabaseRouter`.
Product tables have NO TenantId or ProductId columns — they're implicit from the DB connection.

### Two modules use Platform DB
- `novara.rules` — admin-level automation rules, queries platform schema
- `novara.appgateway` — external integration config, queries platform schema
These modules KEEP TenantId in their C# code because they use `IPlatformDbContext`.

## Rules for Product DB Development

### 1. No TenantId in product tables or functions
```sql
-- CORRECT: product DB function — no tenant/product params
CREATE OR REPLACE FUNCTION issues.getbyproduct(p_status VARCHAR, p_page INT, p_pagesize INT)
RETURNS SETOF issues.issue AS $$
    SELECT * FROM issues.issue WHERE status = COALESCE(p_status, status);
$$ LANGUAGE sql;

-- BANNED: TenantId in product DB
CREATE OR REPLACE FUNCTION issues.getbyproduct(p_tenantid INT, p_productid INT, ...)
```

### 2. No GetTenantId() in product DB module controllers
```csharp
// CORRECT: product DB module
var result = await _service.GetScenariosAsync(type, page, pageSize);

// BANNED: passing TenantId to product DB service
var result = await _service.GetScenariosAsync(GetTenantId(), type, page, pageSize);
```

### 3. No TenantId/ProductId properties in product DB models
```csharp
// CORRECT: product DB entity
public class Issue {
    public int Id { get; set; }
    public string Title { get; set; }
    // NO TenantId, NO ProductId, NO OrgId
}
```

## Deployment Modes

| Mode | DB Setup | Who Uses It |
|------|----------|-------------|
| **Enterprise** (primary) | One server, one platform DB, per-product DBs | Each enterprise customer |
| **SaaS Shared** (future) | Shared platform DB with TenantId, per-product DBs per tenant | Small customers |
| **On-Prem** | Customer's own hardware, same architecture | Regulated industries |

## Data Isolation Guarantee
- Isolation is at the **database level**, not the row level
- Each product's data is physically separated in its own DB
- `ProductDatabaseRouter` resolves which DB to connect to per request
- Platform DB uses TenantId for cross-tenant auth/routing isolation

## Creating a New Product
1. `CREATE DATABASE "NewProductDB" TEMPLATE "NovaraTemplateProductDB"` — sub-second, empty schema
2. Insert row in `platform.productdatabase` with connection string
3. Insert row in `platform.product` with product metadata
4. ProductDatabaseRouter picks it up on next cache refresh (10 min) or restart
