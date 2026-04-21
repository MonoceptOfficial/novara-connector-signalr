# @novara/shell-sdk — Services Reference

The `@novara/shell-sdk` npm package provides the runtime services every module uses for HTTP, auth, navigation, theming, and ID obfuscation. Module Federation guarantees a single instance per app — you inject these services and they "just work" because the Shell already provides them.

**Import path:** `import { ApiService, AuthService, ... } from '@novara/shell-sdk';`

**Never** `import { HttpClient } from '@angular/common/http'` directly in a module — use `ApiService`. See [coding-standards.md](./coding-standards.md) for why.

---

## ApiService — The Only HTTP You Should Ever Write

Wraps `HttpClient` with auth, base URL, query-param serialization, and the `ApiResponse<T>` envelope.

### Module-scoped methods (auto-prepend `products/{productId}/`)

The Shell sets the current product ID on navigation. These methods automatically scope your call to the active product:

```typescript
constructor(private api: ApiService) {}

// GET /api/v1/products/{currentProductId}/quality/scenarios?status=Active
this.api.moduleGet<TestScenario[]>('quality/scenarios', { status: 'Active' });

// POST /api/v1/products/{currentProductId}/quality/scenarios
this.api.modulePost<TestScenario>('quality/scenarios', { title, type });

// PUT /api/v1/products/{currentProductId}/quality/scenarios/42
this.api.modulePut<TestScenario>('quality/scenarios/42', { title });

// DELETE /api/v1/products/{currentProductId}/quality/scenarios/42
this.api.moduleDelete('quality/scenarios/42');

// File upload
this.api.moduleUpload<UploadResult>('quality/imports', formData);

// Paginated list (server returns PagedResponse<T> with items + totalCount)
this.api.moduleGetPaged<TestScenario>('quality/scenarios',
  { page: 1, pageSize: 25 },
  { type: 'Functional' });
```

### Generic methods (no auto-scoping — use for /admin, /platform endpoints)

```typescript
// GET /api/v1/products  (top-level, no product context)
this.api.get<ProductList>('products');

// POST /api/v1/admin/users
this.api.post<User>('admin/users', { email, role });

// File download (returns Blob)
this.api.downloadBlob('quality/scenarios/42/export');
```

### Response shape

Every `ApiService` method returns `Observable<ApiResponse<T>>`:

```typescript
interface ApiResponse<T> {
  success: boolean;
  message: string;
  data: T;
  errorCode?: string;
}
```

Always unwrap via `r.data`:
```typescript
this.api.moduleGet<TestScenario[]>('quality/scenarios')
  .pipe(map(r => r.data || []))
  .subscribe(scenarios => this.scenarios = scenarios);
```

### Anti-patterns — banned

```typescript
// BANNED: HttpClient direct
constructor(private http: HttpClient) {}
this.http.get('http://localhost:5000/api/v1/...');

// BANNED: hardcoded URL
this.api.get('http://localhost:5000/...');

// BANNED: using 'admin/products' (the gateway exposes /products, not /admin/products)
this.api.get('admin/products');

// BANNED: double-wrapping the type
this.api.moduleGet<{ data: TestScenario[] }>(...)  // moduleGet ALREADY wraps in ApiResponse
// Correct:
this.api.moduleGet<TestScenario[]>(...)
```

---

## AuthService — Current User + Token

```typescript
constructor(private auth: AuthService) {}

this.auth.currentUser    // UserContext | null { userId, role, sessionId }
this.auth.isLoggedIn     // boolean
this.auth.token          // current JWT, or null
this.auth.user$          // Observable<UserContext | null>
this.auth.logout('Session expired')
```

You almost never call `auth.login()` from a module — that flows through `/dev` (dev) or external SSO (prod). Modules just read `currentUser`.

---

## IdEncoderService — URL ID Obfuscation

URLs must never expose raw sequential IDs (see [url-security.md](./url-security.md)). Use the encoder for every ID in a route or routerLink:

```typescript
constructor(private id: IdEncoderService) {}

const encoded = this.id.e(42);     // '14pa68' (or similar) — opaque
const decoded = this.id.d('14pa68'); // 42

// In templates with routerLink:
[routerLink]="['/products', id.e(product.id), 'roadmap']"

// In navigation:
this.router.navigate(['/products', this.id.e(productId), 'tracks']);

// Decoding from route params:
this.productId = this.id.d(this.route.snapshot.paramMap.get('productId'));
```

---

## PermissionService — Role/Permission Checks

```typescript
constructor(private perms: PermissionService) {}

if (this.perms.has('issues.create')) { /* show button */ }
if (this.perms.hasAny(['issues.edit', 'issues.delete'])) { ... }
if (this.perms.isAdmin) { /* admin-only */ }
```

For route guarding, use `permissionGuard` instead of in-component checks:
```typescript
{ path: 'admin', loadChildren: ..., canActivate: [permissionGuard], data: { permission: 'admin.access' } }
```

---

## ThemeService — User Theme Preference

```typescript
constructor(private theme: ThemeService) {}

this.theme.current         // 'light' | 'dark' | 'system'
this.theme.set('dark')
this.theme.theme$          // Observable for reactive UI
```

Modules don't usually call this — Shell handles theme application via CSS variables. Only useful if your module renders a theme picker (rare).

---

## SHELL_ENVIRONMENT — Injection Token (use sparingly)

`ApiService` already injects this and exposes `apiUrl` indirectly. Only inject `SHELL_ENVIRONMENT` directly if you need other env values:

```typescript
import { Inject } from '@angular/core';
import { SHELL_ENVIRONMENT, ShellEnvironment } from '@novara/shell-sdk';

constructor(@Inject(SHELL_ENVIRONMENT) private env: ShellEnvironment) {}

const signalRUrl = this.env.signalRUrl;  // e.g., for SignalR connection
```

**Do not** inject `SHELL_ENVIRONMENT` to build API URLs — use `ApiService` instead.

---

## Guards — Route Protection

```typescript
import { authGuard, permissionGuard, adminGuard } from '@novara/shell-sdk';

const routes = [
  // Require login
  { path: 'dashboard', component: Dashboard, canActivate: [authGuard] },

  // Require specific permission
  { path: 'admin/users', component: UserAdmin,
    canActivate: [permissionGuard], data: { permission: 'admin.users.manage' } },

  // Admin-only shortcut
  { path: 'platform-settings', component: Settings, canActivate: [adminGuard] },
];
```

---

## Interceptors — Already Wired by the Shell

You **don't** wire these — Shell registers them globally. Knowing they exist explains behavior:

| Interceptor | What it does |
|---|---|
| `authInterceptor` | Attaches `Authorization: Bearer <token>` to every HTTP request; refreshes token on 401 |
| `retryInterceptor` | Retries transient 503/504 once with backoff |
| `apiErrorInterceptor` | Captures 4xx/5xx and feeds them into `ApiErrorService` (Shell shows toast/banner) |

If you see a 401 in the network tab and the user wasn't redirected to login, check Shell's auth interceptor isn't broken — but don't reimplement it in your module.

---

## ApiErrorService — Visible HTTP Errors

The Shell observes API errors and shows banners. If you need to suppress that for an expected-failing call (e.g., probing for existence), use the standard `catchError` operator — `apiErrorInterceptor` only fires for unhandled errors that propagate to the subscription.

```typescript
this.api.moduleGet<Resource>(`quality/scenarios/${id}`)
  .pipe(catchError(err => err.status === 404 ? of({ data: null } as any) : throwError(() => err)))
  .subscribe(...);
```

---

## Standard module component skeleton

```typescript
import { Component, ChangeDetectionStrategy, ChangeDetectorRef, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute } from '@angular/router';
import { ApiService, IdEncoderService } from '@novara/shell-sdk';
import { TestScenario } from '../models/test.models';

@Component({
  selector: 'nov-quality-scenarios',
  standalone: true,
  imports: [CommonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `...`,
})
export class ScenariosComponent implements OnInit {
  scenarios: TestScenario[] = [];
  loading = false;

  constructor(
    private api: ApiService,
    private id: IdEncoderService,
    private route: ActivatedRoute,
    private cdr: ChangeDetectorRef,
  ) {}

  ngOnInit() {
    this.loading = true;
    this.api.moduleGet<TestScenario[]>('quality/scenarios').subscribe({
      next: (res) => {
        this.scenarios = res.data || [];
        this.loading = false;
        this.cdr.markForCheck();  // OnPush + async = mandatory
      },
      error: () => { this.loading = false; this.cdr.markForCheck(); },
    });
  }
}
```

This skeleton encodes every required pattern: standalone component, OnPush, ApiService for HTTP, IdEncoderService for IDs, ChangeDetectorRef for async-after-OnPush. Use it as the starting point for every new module component.
