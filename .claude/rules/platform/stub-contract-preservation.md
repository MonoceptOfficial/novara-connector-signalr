# Stub Contract Preservation

## The rule

**Any stub component that replaces a real federated component MUST preserve the exact public contract of the real component:**

- Every `@Output()` is a real `EventEmitter<T>`, never a plain object with just `.emit()`
- Every `@Input()` has the same name, type, and default semantics
- The component's `selector` string is identical
- The component is `standalone: true` if the real one is

The Angular template compiler cannot distinguish a stub from the real thing. When it compiles a consumer's template `(closed)="handler()"`, it emits `component.closed.subscribe(handler)`. If the stub's `closed` is a plain `{ emit() }` object without `subscribe`, the app **crashes at bootstrap**: `subscribe is not a function`, no routes load, the whole module federation graph fails silent-ish.

## The incident this codifies

**2026-04-23** — Shell shipped with a stub `NovBugCapturePanelComponent` where:

```typescript
// WRONG — the stub that broke Shell boot
@Component({
  selector: 'nov-bug-capture-panel',
  template: '',
  outputs: ['closed'],     // ← promises the template an output
})
export class NovBugCapturePanelComponent {
  closed = { emit: () => {} };   // ← but it's NOT an EventEmitter
}
```

The real component at `NovaraTools/sdks/novara-angular-bug-capture/src/components/bug-capture-panel.component.ts`:

```typescript
@Output() closed = new EventEmitter<void>();
```

Consumers use `(closed)="showPanel = false"` in their template. Angular's generated code calls `.subscribe(...)`. Stub's object has no `subscribe` → runtime `TypeError`. Entire app mount fails. No modules load. Nothing on screen. Debugging cost: several hours.

## The fix pattern

**Option A — keep the emitter contract (use when consumers really do bind `(closed)`):**

```typescript
import { Component, EventEmitter, Input, Output } from '@angular/core';

@Component({
  selector: 'nov-bug-capture-panel',
  template: '<!-- stubbed -->',
  standalone: true,
})
export class NovBugCapturePanelComponent {
  @Input() visible = false;
  @Output() closed = new EventEmitter<void>();  // has .emit AND .subscribe
}
```

**Option B — strip the output if the stub is a true no-op:**

```typescript
@Component({ selector: 'nov-bug-capture-panel', template: '', standalone: true })
export class NovBugCapturePanelComponent {
  @Input() visible = false;
  // No output. Consumers binding (closed)="..." now get a compile-time error
  // instead of a runtime crash — a clearer failure mode.
}
```

**Never** use `outputs: ['closed']` in the decorator metadata alongside a plain-object `closed` field. If you use the decorator metadata form, the class field must still be a real `EventEmitter`.

## When stubs exist in Novara

Stubs live in these places:

- `novara-shell/web/src/stubs/*.ts` — Shell-side placeholders for modules/components not in the current dev setup
- Module `web/` can stub cross-module components for standalone build
- `@novara/shell-sdk` internal shims for unavailable services

Every stub above must satisfy this rule. No exceptions.

## How to verify

Before committing a stub file:

1. Open the real component it replaces. Note every `@Output()`.
2. In the stub, each `@Output()` must be `new EventEmitter<T>()` — **never** a plain object literal.
3. If the stub has no meaningful outputs, omit them entirely (Option B).

Claude should refuse to write a stub that declares `outputs: [...]` in decorator metadata unless the matching class field is a real `EventEmitter`.

## Related

- `architecture-decisions.md` — federation singleton sharing
- `module-development.md` — standalone component conventions
- `learned-errors.md § FEDERATION_CHANGE_DETECTION` — cousin federation class of bug
