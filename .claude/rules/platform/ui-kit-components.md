# @novara/ui-kit — Components & Pipes Reference

Standalone Angular components shared across all modules. Keeps every module visually and behaviorally consistent — same status badges, same empty states, same data tables, same modals.

**Import path:** `import { StatusBadgeComponent, EmptyStateComponent, ... } from '@novara/ui-kit';`

**Selector prefix:** all components use `nov-` (e.g., `<nov-status-badge>`, `<nov-data-table>`).

**Standalone:** add the component class to your `imports: []` array; do NOT register a NgModule.

---

## When to use ui-kit vs roll your own

**Use ui-kit when:**
- A standard pattern already exists (badges, tables, modals, empty states)
- You're tempted to write a fourth confirm dialog

**Roll your own when:**
- The component is module-specific (e.g., feature board kanban — only Roadmap needs that)
- You'd be passing 15 inputs to coerce a generic component into module-specific behavior

If you find yourself writing a component that 3+ modules would benefit from, raise a PR to add it to ui-kit instead of duplicating.

---

## Display Components

### `<nov-status-badge>` — colored pill for entity status

```html
<nov-status-badge label="In Progress"></nov-status-badge>
<nov-status-badge label="Done" variant="success"></nov-status-badge>
```

Inputs: `label` (required), `variant: 'default' | 'success' | 'warning' | 'danger' | 'info' | 'muted'`.

The component has built-in colors for common Novara status values (`Draft`, `Under Review`, `Approved`, `In Development`, `Done`, etc.) — pass the label and it picks the right color. Use `variant` to override.

### `<nov-empty-state>` — friendly empty list message

```html
<nov-empty-state
  icon="📭"
  title="No scenarios yet"
  message="Create your first test scenario to start tracking quality.">
  <button class="btn btn-primary" (click)="create()">+ New Scenario</button>
</nov-empty-state>
```

Slot any CTA (button, link) as projected content.

### `<nov-loading-skeleton>` — placeholder while loading

```html
@if (loading) {
  <nov-loading-skeleton rows="5" />
} @else {
  <!-- real content -->
}
```

Inputs: `rows` (default 3), `width` (CSS value).

### `<nov-user-avatar>` — circle avatar with initials/photo

```html
<nov-user-avatar [user]="row.assignee" size="sm"></nov-user-avatar>
```

Inputs: `user: { fullName: string; avatarUrl?: string }`, `size: 'xs' | 'sm' | 'md' | 'lg'`.

### `<nov-tooltip>` — hover hint

```html
<button novTooltip="Soft-deletes the row">Delete</button>
```

Implemented as a directive — no element wrapper needed.

---

## Form Components

### `<nov-form-field>` — label + input + validation message

```html
<nov-form-field label="Title" [error]="form.get('title').errors?.['required'] && 'Required'">
  <input type="text" formControlName="title" />
</nov-form-field>
```

Wraps any form control with consistent label/spacing/error display.

### `<nov-button>` — standardized button

```html
<nov-button variant="primary" [loading]="saving" (click)="save()">Save</nov-button>
<nov-button variant="ghost" size="sm">Cancel</nov-button>
```

Inputs: `variant: 'primary' | 'secondary' | 'ghost' | 'danger'`, `size: 'sm' | 'md' | 'lg'`, `loading`, `disabled`, `type`.

### `<nov-select>` — typed dropdown

```html
<nov-select
  [options]="[{ value: 'open', label: 'Open' }, { value: 'closed', label: 'Closed' }]"
  [(value)]="selectedStatus"
  placeholder="Filter by status">
</nov-select>
```

---

## Layout Components

### `<nov-module-layout>` — standard module shell

Every module page should be wrapped in this. It handles sidebar-on-the-left + main-content layout, responsive collapse, animations.

```html
<!-- With sidebar -->
<nov-module-layout>
  <nav moduleSidebar>
    <nov-sidebar-section title="Quality">
      <nov-nav-item icon="📋" label="Scenarios" route="scenarios"></nov-nav-item>
      <nov-nav-item icon="▶️" label="Runs" route="runs"></nov-nav-item>
      <nov-nav-item icon="🚦" label="Gates" route="gates"></nov-nav-item>
    </nov-sidebar-section>
  </nav>
  <router-outlet></router-outlet>
</nov-module-layout>

<!-- Without sidebar (full-width) -->
<nov-module-layout>
  <router-outlet></router-outlet>
</nov-module-layout>
```

This is preferred over rolling your own grid/flex layout per module — keeps all 33 modules visually consistent.

### `<nov-data-table>` — sortable list table

```html
<nov-data-table
  [columns]="[
    { key: 'title', label: 'Title', sortable: true },
    { key: 'status', label: 'Status', width: '120px' },
    { key: 'createdAtUtc', label: 'Created', sortable: true, width: '150px' }
  ]"
  [rows]="scenarios"
  [loading]="isLoading"
  emptyMessage="No scenarios found"
  (sort)="onSort($event)"
  (rowClick)="onSelect($event)">

  <!-- Optional: custom cell rendering -->
  <ng-template #cellTemplate let-row let-col="column">
    @if (col.key === 'status') {
      <nov-status-badge [label]="row.status" />
    } @else {
      {{ row[col.key] }}
    }
  </ng-template>
</nov-data-table>
```

Replaces every hand-built `<table>` in your module. Includes loading state, empty state, sortable headers, row-click handling.

### `<nov-modal>` — overlay modal

```html
<nov-modal [open]="showEditor" (closed)="showEditor = false" title="Edit Scenario">
  <form>
    <!-- form fields -->
  </form>
  <ng-container modalActions>
    <nov-button variant="ghost" (click)="showEditor = false">Cancel</nov-button>
    <nov-button variant="primary" (click)="save()">Save</nov-button>
  </ng-container>
</nov-modal>
```

### `<nov-pagination>` — page controls

```html
<nov-pagination
  [page]="currentPage"
  [pageSize]="pageSize"
  [totalCount]="totalCount"
  (pageChange)="loadPage($event)">
</nov-pagination>
```

### `<nov-tabs>` — tab bar

```html
<nov-tabs [tabs]="['Overview', 'Tasks', 'Activity']" [(active)]="activeTab">
  @switch (activeTab) {
    @case ('Overview') { ... }
    @case ('Tasks') { ... }
    @case ('Activity') { ... }
  }
</nov-tabs>
```

### `<nov-drawer>` — slide-out panel

```html
<nov-drawer [open]="showDetails" (closed)="showDetails = false" position="right" width="500px">
  <h2>Details</h2>
  <!-- content -->
</nov-drawer>
```

---

## Feedback Components

### `<nov-confirm-dialog>` — destructive action confirmation

```html
<nov-confirm-dialog
  [open]="confirmDelete"
  title="Delete this scenario?"
  message="This cannot be undone."
  confirmLabel="Delete"
  variant="danger"
  (confirmed)="actuallyDelete()"
  (cancelled)="confirmDelete = false">
</nov-confirm-dialog>
```

Use this for ANY destructive operation — no more browser `confirm()`.

### `<nov-error-state>` — error placeholder

```html
@if (error) {
  <nov-error-state
    title="Couldn't load scenarios"
    [message]="error.message"
    (retry)="loadScenarios()">
  </nov-error-state>
}
```

---

## Navigation Components

### `<nov-nav-item>` — sidebar item with icon + label + active state

```html
<nov-nav-item icon="📋" label="Scenarios" route="scenarios"></nov-nav-item>
```

Used inside `<nov-module-layout>`'s `[moduleSidebar]` slot. Handles routerLink + active styling automatically.

### `<nov-sidebar-section>` — collapsible group of nav items

```html
<nov-sidebar-section title="Test Management">
  <nov-nav-item icon="📋" label="Scenarios" route="scenarios"></nov-nav-item>
  <nov-nav-item icon="▶️" label="Runs" route="runs"></nov-nav-item>
</nov-sidebar-section>
```

---

## Pipes

### `TimeAgoPipe` — relative time formatting

```html
<span>{{ row.createdAtUtc | timeAgo }}</span>
<!-- "3 minutes ago", "yesterday", "Mar 15" -->
```

```typescript
imports: [TimeAgoPipe]
```

### `UtcDatePipe` — explicit UTC formatting (avoids local-timezone surprises)

```html
<span>{{ row.modifiedAtUtc | utcDate:'medium' }}</span>
```

Use this instead of Angular's built-in `date` pipe when the underlying value is UTC and you want to make that explicit.

---

## Standard CSS variables to use

Don't hardcode colors. Use the CSS variables defined in the Shell theme:

```scss
.my-component {
  background: var(--bg-surface, #1a1a2e);
  border: 1px solid var(--border-subtle, rgba(255,255,255,0.08));
  color: var(--text-primary, #e2e8f0);

  .secondary-text { color: var(--text-secondary, #94a3b8); }
  .muted-text     { color: var(--text-muted, #64748b); }
  .accent         { color: var(--color-primary, #6366f1); }
  .success        { color: var(--color-success, #10b981); }
  .warning        { color: var(--color-warning, #f59e0b); }
  .danger         { color: var(--color-danger, #ef4444); }
}
```

The Shell sets these — your module inherits them automatically. They flip when the user switches theme (light/dark).

---

## Anti-patterns

```typescript
// BANNED: rolling your own table when nov-data-table fits
<table><thead><tr><th>...</th></tr></thead><tbody>...</tbody></table>

// BANNED: native browser confirm()
if (confirm('Delete?')) { ... }       // → use <nov-confirm-dialog>

// BANNED: hardcoded colors
.btn { background: #6366f1; color: #fff; }  // → use var(--color-primary)

// BANNED: importing the entire ui-kit when you only need 2 components
import * as Kit from '@novara/ui-kit';
// → import { StatusBadgeComponent, DataTableComponent } from '@novara/ui-kit';

// BANNED: rebuilding the module sidebar layout
<div class="my-sidebar"><div class="my-content">...</div></div>
// → use <nov-module-layout> with [moduleSidebar]
```

---

## When ui-kit doesn't have what you need

Three options, in order of preference:

1. **Compose existing primitives** — most "missing" components are 80% one of the existing ones. e.g., a "filter chip bar" is `<nov-button>` × N with custom styling. Try this first.

2. **Build it in your module** — if it's domain-specific (a feature kanban for Roadmap, a code-diff viewer for CodeReview), build it inside your module. Don't pollute ui-kit with module-specific components.

3. **Promote to ui-kit** — if 3+ modules would use it, raise a PR adding it to `novara-ui-kit/src/components/`. Bumps the package version, all modules pull on next `npm install`.
