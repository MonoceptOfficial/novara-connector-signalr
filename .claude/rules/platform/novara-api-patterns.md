---
globs: **/*.cs
---

# Novara API Patterns — PRODUCTION QUALITY ONLY

## Every feature MUST be end-to-end: Controller → Service → Stored Procedure → SQL Server

No shortcuts. No mock data. No empty fallbacks hiding missing implementations.

## Service implementation — REAL database operations:
```csharp
public async Task<IEnumerable<Project>> GetByProjectAsync(int projectId, PaginationParams paging)
{
    return await _db.ExecuteProcedureAsync<Project>(SpNames.GetProjects,
        new { ProjectId = projectId, Page = paging.Page, PageSize = paging.PageSize });
}
```

## BANNED patterns:
```csharp
// BANNED — silently hiding missing SPs
catch (Exception) { return Array.Empty<object>(); }

// BANNED — hardcoded mock data
return new List<Feature> { new Feature { Title = "Demo Feature" } };

// BANNED — fake AI responses
return "AI Analysis: Category suggestion: Infrastructure...";
```

## When an SP is missing:
- Let the exception propagate — GlobalExceptionMiddleware returns proper HTTP error
- The UI shows toastr error — user knows something is wrong
- FIX: Create and deploy the SP to SQL Server

## Plugin development:
1. `.csproj` with NuGet metadata
2. Plugin class with manifest
3. Controller with real endpoints
4. Service with real IDbContext + SpNames calls
5. Stored procedures DEPLOYED to SQL Server (not just .sql files in Git)
6. Registered in ServiceRegistration.cs

## Database:
- ALL in `novara` schema
- SP names in SpNames.cs — no magic strings
- SQL files in Git AND deployed to server — both required

## Configuration:
- Secrets → `platform.AppSetting` table (DB-first, appsettings.json fallback)
- Mask secrets when returning to frontend

## Claude API:
- Real calls via ClaudeApiClient → Anthropic REST API
- If key not configured → throw BusinessRuleException (not mock response)
- Use GenerateStructuredAsync<T> for typed JSON responses
