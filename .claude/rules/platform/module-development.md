# Module Development Rules — Binding for All Novara Modules

**Scope:** Every module in the NovaraModules/ workspace. Every Claude Code instance working on a module.
**Authority:** CTO / Architecture Review. These rules are enforced, not suggested.

---

## 1. SDK Is Your Only Dependency

Your module's `.csproj` references ONLY:
- `Novara.Module.SDK` (NuGet or ProjectReference)
- `Dapper` (data access)
- `Microsoft.AspNetCore.App` (framework reference)

**NEVER reference:**
- Another module's assembly (e.g., Novara.Module.Issues from Novara.Module.Roadmap)
- Shell/Gateway internals (Novara.Shell.Api.*)
- Infrastructure packages directly (Npgsql, Serilog, etc. — Shell provides these)

Communication with other modules happens ONLY through:
- `IEventBus` — publish events for others to react to
- `ICrossModuleQuery` — read-only queries to other modules via the router

---

## 2. Controller Patterns

### Base Class
```csharp
[ModuleRoute("{your-route}")]              // Product-scoped: /api/v1/products/{productId}/{route}
public class YourController : ModuleBaseController  // Provides GetUserId(), GetTenantId(), GetProductId()
```

Use `[PlatformRoute("admin/{route}")]` ONLY for platform-level admin endpoints (Admin, Rules, AppGateway modules).

### Authorization
- `[Authorize]` is inherited from `ModuleBaseController` — every endpoint requires auth
- Every mutation endpoint MUST have `[RequirePermission("{module}.{action}")]`
- Read endpoints: `[RequirePermission]` optional but recommended for sensitive data

### Response Wrapping
```csharp
// SUCCESS — always ApiResponse<T>.Ok()
return Ok(ApiResponse<Entity>.Ok(result, "Entity created."));
return Ok(ApiResponse<PagedResponse<Entity>>.Ok(pagedResult));

// NOT FOUND
return NotFound(ApiResponse<object>.Fail("Entity not found."));

// VALIDATION ERROR — throw, don't return
throw new ValidationException("Title is required.");

// NEVER return raw objects
// BANNED: return Ok(someObject);
// BANNED: return Ok(new { success = true, data = x });
```

### Controller Responsibilities
Controllers are THIN. They:
1. Extract parameters from request (route, query, body)
2. Call ONE service method
3. Wrap result in `ApiResponse<T>`
4. Return

Controllers do NOT:
- Contain business logic
- Call multiple service methods in sequence
- Catch exceptions (GlobalExceptionMiddleware handles this)
- Access IModuleDbContext directly (exception: simple pass-through queries that don't warrant a service method)

---

## 3. Service Patterns

### Interface + Implementation
```csharp
// Services/IYourService.cs
public interface IYourService
{
    Task<Entity> UpsertAsync(Entity entity, int userId, CancellationToken ct = default);
    Task<PagedResponse<Entity>> GetAllAsync(string? status, PaginationParams paging, CancellationToken ct = default);
    Task<Entity?> GetDetailAsync(int entityId, CancellationToken ct = default);
    Task DeleteAsync(int entityId, int userId, CancellationToken ct = default);
}
```

### SP Coupling Comments (MANDATORY)
Every `ExecuteProcedureAsync` call MUST have an inline comment showing:
1. The function signature (parameter names + types)
2. The return columns

```csharp
// SP: issues.getbyproduct(p_status VARCHAR, p_severity VARCHAR, p_page INT, p_pagesize INT)
// Returns: id, title, status, severity, assigneeuserid, createdatutc + totalcount
var items = await _db.ExecuteProcedureAsync<Issue>(IssueSpNames.GetByProduct, new {
    Status = status, Severity = severity, Page = paging.Page, PageSize = paging.PageSize
});
```

This catches INT/VARCHAR mismatches at read-time, not runtime.

### Error Handling in Services — USE SDK GUARD CLASS
```csharp
// USE Guard.Found() — NEVER "if null return null"
var entity = Guard.Found(
    await _db.ExecuteProcedureSingleAsync<Entity>(SpNames.GetDetail, new { Id = id }),
    "Entity", id);
// Throws NotFoundException("Entity with ID '42' was not found.") — clear, never silent

// USE Guard for all validation
Guard.NotEmpty(request.Title, "title");
Guard.ValidId(request.TrackId, "trackId");
Guard.Require(request.Priority != "Critical" || isAdmin, "Only admins can set Critical priority.");
Guard.OneOf(request.Status, new[] { "Open", "InProgress", "Done" }, "status");

// USE SafeExecute for non-critical side effects (audit, events, notifications)
await SafeExecute.RunAsync(
    () => _eventBus.PublishAsync(new EntityCreatedEvent { ... }),
    _logger, "Publish EntityCreatedEvent", "novara.yourmodule");

// BANNED: return null from service and handle in controller
// BANNED: catch (Exception) { return Array.Empty<T>(); }
// BANNED: catch (Exception) { _logger.LogWarning(...); return default; }
// BANNED: if (result == null) return null;  ← USE Guard.Found() instead
// BANNED: try { ... } catch { }  ← USE SafeExecute.RunAsync() for non-critical ops
```

### Inherit CrudServiceBase for Auto Audit + Events + Cache
```csharp
// NEW modules should inherit CrudServiceBase to get cross-cutting concerns for free:
public class YourService : CrudServiceBase, IYourService
{
    public YourService(IModuleDbContext db, IEventBus events, IAuditService audit,
        ICacheService cache, IErrorLogService errorLog, ILogger<YourService> logger)
        : base(db, events, audit, cache, errorLog, logger, "novara.yourmodule", "YourEntity") { }

    public async Task<Entity> CreateAsync(CreateRequest req, int userId)
    {
        Guard.NotEmpty(req.Title, "title");
        var result = Guard.Found(
            await Db.ExecuteProcedureSingleAsync<Entity>(SpNames.Upsert, new { ... }),
            "Entity", 0);
        await OnCreatedAsync(result.Id, result.Title, userId);  // Auto: audit + event + cache
        return result;
    }
}
// CrudServiceBase gives you: OnCreatedAsync, OnUpdatedAsync, OnDeletedAsync, OnStatusChangedAsync,
// GetCachedAsync (standardized cache keys), and structured logging — all automatic.
```

### DI Registration
```csharp
public override void ConfigureServices(IServiceCollection services)
{
    services.AddScoped<IYourService, YourService>();
    services.AddScoped<ICrossModuleQueryHandler, YourModuleQueryHandler>();
    // Register ALL services — ConfigureServices must NEVER be empty
}
```

---

## 4. Database Access

### Use ONLY IModuleDbContext — NEVER IPlatformDbContext
```csharp
// CORRECT: Always go through the abstraction (product DB, own schema)
await _db.ExecuteProcedureAsync<T>(SpNames.Function, new { Param = value });
await _db.ExecuteProcedureSingleAsync<T>(SpNames.Function, new { Param = value });
await _db.ExecuteProcedureAsync(SpNames.Function, new { Param = value }); // returns affected rows

// BANNED: Raw SQL queries
using var conn = _db.CreateConnection();
var result = await SqlMapper.QueryAsync<T>(conn, "SELECT ...");  // NO!

// BANNED: Magic strings
await _db.ExecuteProcedureAsync<T>("issues.getbyproduct", ...);  // NO! Use SpNames constant

// BANNED: Accessing platform DB from product-scoped modules
_platformDb.ExecuteProcedureAsync<T>("platform.GetUsers", ...);  // NO!
// Need user data? Use productcore.user (synced copy in product DB)
// Need settings? Use IModuleSettingsStore (SDK service)
// Need permissions? Use [RequirePermission] attribute
// ONLY modules with DbScope = ModuleDbScope.Platform may use IPlatformDbContext
```

### SpNames Constants
```csharp
public static class YourModuleSpNames
{
    // Core CRUD
    public const string Upsert = "{schema}.upsert";
    public const string GetByProduct = "{schema}.getbyproduct";
    public const string GetDetail = "{schema}.getdetail";
    public const string Delete = "{schema}.delete";

    // Business operations
    public const string TransitionStatus = "{schema}.transitionstatus";
}
```

### No ProductId/TenantId
Product DB modules: the database IS the product. The deployment IS the tenant.
- No `GetTenantId()` calls in product-scoped modules
- No `ProductId` parameter in function calls
- No `TenantId` column in product DB tables
- Exception: Admin, Rules, AppGateway modules use `IPlatformDbContext` with TenantId

---

## 5. Event Publishing

After every successful CREATE, UPDATE, DELETE operation in a service, publish an event:

```csharp
// After a successful create
await _eventBus.PublishAsync(new IssueCreatedEvent
{
    IssueId = result.Id,
    Title = result.Title,
    Severity = result.Severity,
    UserId = userId,
    TimestampUtc = DateTime.UtcNow
}, ct);
```

**Rules:**
- Publish AFTER the DB write succeeds (not before)
- Use typed event classes from SDK (IssueCreatedEvent, FeatureStatusChangedEvent, etc.)
- Use WellKnownEvents constants for standard events
- Include the entity ID and key identifying fields in the event
- Publish in the SERVICE layer, never in the controller
- If no typed event class exists, create one in the SDK

---

## 6. Frontend Patterns

### Module Federation
Every module's `web/` folder is an independent Angular build with Native Federation:
- `federation.config.js` exposes `./routes` and `./index`
- Shared dependencies: `@angular/*`, `rxjs`, `@novara/shell-sdk`, `@novara/ui-kit`, `ngx-toastr`
- All shared as `singleton: true`

### API Client
```typescript
@Injectable({ providedIn: 'root' })
export class YourService {
  constructor(private api: ApiService) {}

  getAll(paging: PaginationParams): Observable<PagedResponse<Entity>> {
    return this.api.moduleGet<PagedResponse<Entity>>('your-route', paging).pipe(map(r => r.data));
  }

  getDetail(id: number): Observable<Entity> {
    return this.api.moduleGet<Entity>(`your-route/${id}`).pipe(map(r => r.data));
  }

  create(entity: Partial<Entity>): Observable<Entity> {
    return this.api.modulePost<Entity>('your-route', entity).pipe(map(r => r.data));
  }
}
```

- Use `api.moduleGet/modulePost/modulePut/moduleDelete` for product-scoped routes (auto-prepends `products/{productId}/`)
- Use `api.get/post/put/delete` for platform-scoped routes
- Always `.pipe(map(r => r.data))` to unwrap ApiResponse envelope

### Components
- All components: `standalone: true`
- Use `@novara/ui-kit` components: `<nov-status-badge>`, `<nov-empty-state>`, `<nov-loading-skeleton>`
- Never build your own buttons, tables, modals — use ui-kit (or request additions)
- Loading state: `isLoading` boolean, show `<nov-loading-skeleton>` while true
- Empty state: show `<nov-empty-state>` when list is empty and not loading
- Error state: `toastr.error('message')` for transient, dedicated error display for persistent

### TypeScript Models
- Must match C# entity properties (camelCase version)
- Keep in sync — when C# entity changes, update TS interface in the same commit
- Export from `models/{name}.model.ts`

---

## 7. Bug Fix Protocol — Trace Bottom-Up

When something "doesn't work" or "data is missing":

1. **DB Schema**: Does the table/column exist? `\d {schema}.{table}`
2. **Function**: Does the function handle this case? Read its body.
3. **Data**: Is the data actually in the DB? `SELECT * FROM {schema}.{table} WHERE id = ...`
4. **API**: Does the endpoint return the field? `curl` the endpoint, read the response body.
5. **Frontend**: Does the component render it? Check the TypeScript model + template.

**Check ALL 5 layers even if you find a break early.** Multiple layers can be broken simultaneously.

**MANDATORY:** After fixing, verify with `curl` that the API returns the correct data. The developer/user must NEVER be the one discovering that a fix doesn't work.

---

## 8. File Structure Convention

```
novara-module-{name}/
├── .claude/                    # Claude Code AI setup
│   ├── CLAUDE.md               # Module-specific context
│   ├── settings.json           # Hooks config
│   ├── db-config.sh            # DB connection helpers
│   ├── rules/                  # Development rules (Tier 1 + Tier 2)
│   └── hooks/                  # Session lifecycle hooks
├── api/src/Novara.Module.{Name}/
│   ├── {Name}Module.cs         # ModuleBase entry point
│   ├── Controllers/            # 1-2 controllers max
│   ├── Services/               # Interface + implementation pairs
│   ├── Models/                 # C# entity classes
│   ├── Contracts/              # Request/response DTOs
│   ├── Constants/              # SpNames.cs
│   └── *.csproj                # SDK reference + embedded migrations
├── migrations/                 # SQL scripts (001_, 002_, 003_, 004_)
├── web/                        # Angular micro-frontend
│   ├── components/             # Standalone components
│   ├── services/               # API client services
│   ├── models/                 # TypeScript interfaces
│   ├── routes.ts               # Lazy-loaded routes
│   ├── index.ts                # Barrel export
│   └── federation.config.js    # Module Federation config
├── module.json                 # Manifest metadata
├── build.sh                    # Build + pack script
└── .gitignore
```
