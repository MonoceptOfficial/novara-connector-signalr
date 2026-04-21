---
globs: **/*.cs, **/*.csproj
---

# .NET Backend Patterns (Clean Architecture)

## Architecture
.NET 8 Web API with Clean Architecture:
- **Api** — Controllers, middleware, DI, Program.cs
- **Application** — Services, interfaces, auth, validators, constants
- **Domain** — Entities, enums, exceptions (zero dependencies)
- **Infrastructure** — Dapper DB, Claude API, Azure Blob, SignalR
- **Contracts** — Request/response DTOs

## Conventions
- Use async/await for all I/O operations
- Follow existing controller patterns for new endpoints
- All SP names in SpNames.cs — no magic strings
- All permissions in Permissions.cs
- Use typed exceptions (NotFoundException, ValidationException, etc.)
- Services implement interfaces defined in Application layer
- Domain depends on NOTHING

## Adding a new endpoint checklist
1. Add DTO in Contracts project
2. Add interface in Application/Interfaces
3. Add service implementation in Application/Services
4. Add SP name in SpNames.cs
5. Add controller endpoint in Api/Controllers
6. Register service in ServiceRegistration.cs
