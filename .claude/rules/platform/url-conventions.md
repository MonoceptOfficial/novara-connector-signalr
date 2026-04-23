# URL conventions — frontend routes vs REST API paths

TL;DR: They DON'T mirror each other. Know both shapes before tracing a bug.

## Three URL shapes you'll hit

### 1. Angular routes in the browser

Product-scoped UI paths always carry the `IdEncoder`-encoded product id:

| Browser URL | Module |
|---|---|
| `/products/{encodedPid}/tracks` | Roadmap — track list |
| `/products/{encodedPid}/roadmap` | Roadmap — full shell |
| `/products/{encodedPid}/features` | Roadmap — feature list |
| `/products/{encodedPid}/features/{encodedFid}` | Roadmap — feature detail |
| `/products/{encodedPid}/issues` | Issues |
| `/products/{encodedPid}/quality` | Quality / Test |
| `/products/{encodedPid}/agent-tasks` | Agentic shell + sub-pages |
| `/products/{encodedPid}/agent-tasks/sessions/{sessionId}` | Agent session detail |

`encodedPid` is a short opaque string (e.g. `14pa68`) produced by `IdEncoderService`. Never a raw number. Decoded only in components via `this.id.d(pid)`.

### 2. REST API paths in the Gateway

Two flavors, routed by the controller attribute:

| Attribute | Mounts at | Example |
|---|---|---|
| `[ModuleRoute("features")]` | `/api/v1/products/{productId}/features/...` | Controller on `FeatureController` in roadmap |
| `[PlatformRoute("tracks")]` | `/api/v1/tracks/...` (product id as path/query segment, NOT in URL scope) | `TrackController` in roadmap |

`ModuleRoute` is the default. `PlatformRoute` is used for:
- Platform-wide admin endpoints (auth, users, products, settings)
- Legacy carry-over where a module hasn't been migrated to module-scope yet

### 3. Remaining mixed cases (audit, admin, viber)

Roadmap was cleaned up in Phase BC.1 (2026-04-19) — every controller now uses `ModuleRoute`. The modules below still have MIXED routing (legacy debt, not a design choice):

**Audit:**
| Controller | Attribute | API path |
|---|---|---|
| `AuditEngineController` | `PlatformRoute` | `/api/v1/audit/...` |
| `HealthController` | `ModuleRoute` | `/api/v1/products/{pid}/health/...` |

**Admin + Viber** — see CLAUDE.md module table for the remaining split; the rules of thumb below still apply.

If you see a 404 and you assumed `products/{pid}/X`, double-check the controller attribute — `X` may be platform-scoped.

## How to trace a UI "page is blank / 404" bug

Use the **bug-investigation protocol** (`.claude/rules/bug-investigation.md`): work DB-up, don't guess.

1. **DB**: does the schema have data? Run the SP directly in psql.
2. **SP**: does the SP signature match what the service expects? Compare `pg_get_function_arguments()` to the Dapper call.
3. **API**: does the endpoint return 200 with real data? Curl it with a dev token.
4. **Angular service**: is it calling the right API path? Grep the service file for the URL it's hitting.
5. **Component**: does it actually render? Look for silent `forkJoin` errors, stale federation build, tsconfig path stub (see below).
6. **Route**: does the Shell's `app.routes.ts` load the actual module or a stub?

## Stubbed-module gotcha (Shell tsconfig)

`NovaraWorkspaceShell/novara-shell/web/tsconfig.json` has `paths` entries like:

```
"@novara/module-plan": ["src/stubs/module-plan.ts"]   ← STUB (empty routes)
"@novara/module-plan": ["../../NovaraModules/novara-module-roadmap/web/index.ts"]   ← LIVE
```

The stub path exports EMPTY route arrays. If a module's tsconfig path points at the stub but the browser navigates to one of its routes, the result is a **totally blank main pane** — route matches, `loadChildren` resolves to `[]`, nothing renders. No error, no loading spinner, no empty state.

Shell's default is "stubs for everything" so `ng serve` works without cloning every module repo. When you clone a module, flip its ONE tsconfig line from stub to source path. When the federation build for that module is published as a NuGet/npm artifact, that becomes the real target instead.

**Hit this symptom?** Open `NovaraWorkspaceShell/novara-shell/web/tsconfig.json`, find the module's line, confirm it points at `../../NovaraModules/novara-module-{name}/web/index.ts` and not at a stub.

## Common URL mistakes

- **Writing `/api/v1/products/{pid}/tracks`** — wrong, it's `/api/v1/tracks/product/{pid}`
- **Encoding product id in API URLs** — API uses raw integers, only Angular routes use the encoder
- **Calling `api.moduleGet('tracks/...')`** — `moduleGet` prepends `products/{pid}/`, so this hits `/api/v1/products/{pid}/tracks/...` which 404s. Use `api.get('tracks/...')` for platform-scoped endpoints.

## What to do if you're still stuck

Run the deployment verifier:

```bash
bash .claude/tools/verify-deployment.sh
```

18 checks, runs in ~5 seconds. Calls out missing SPs, missing recipes, orphan sessions, and structural drift.
