# URL Security — No Sequential IDs

URLs must never expose sequential numeric IDs (like `/products/1/features/5`).

Sequential IDs allow attackers to enumerate resources (IDOR attacks), discover total counts, and guess valid IDs. This is an OWASP Top 10 vulnerability.

## Rules
- All route URLs must use obfuscated IDs (encoded via IdEncoder service)
- Internal API calls still use numeric IDs — decode before calling
- Every new route, routerLink, or URL parameter must go through the encoder
- This applies to ALL entities: products, features, issues, steps, etc.
