# P5 hardening matrix

| Flow / endpoint | Failure | Expected UI / response | Retry | Technical signal | Regression coverage |
|---|---|---|---|---|---|
| `POST /api/auth/login` | Invalid credentials | Login message, HTTP 401 | User resubmits | No password or token in logs | `test_auth_foundation.py` |
| `GET /api/auth/session` | Missing or expired session | Redirect to login, API HTTP 401 | New login | Request path and status only | Backend auth + real browser expiry |
| Planning confirm/publish | Wrong role | HTTP 403 before validation or mutation | Use authorized role | Audited mutation when authorized | `test_auth_foundation.py` + Planning tests |
| Workforce policy/override | Wrong role or invalid input | HTTP 403/422, existing state preserved | Correct permission/input | Typed API error | Workforce policy/override tests |
| Home summary | One source unavailable | Available cards remain; partial-data notice | Background refresh / next visit | Failed source count only | Mission Control performance tests |
| Planning workspace | Network/API failure | Finite alert and `Riprova`; no raw payload | Contextual button | Sanitized error classification | `product-hardening.test.js` |
| Fleet registry/detail | Empty, 404 or service failure | Empty/failure state; no infinite skeleton | Contextual retry | Sanitized context/status | Fleet first-paint and workspace tests |
| Fleet Vision | Aggregate source failure | Contextual failure card | `Riprova` | Sanitized context/status | Fleet Vision workspace tests |
| Journal Control Room | Empty or API failure | Empty/failure state, Archive path preserved | Contextual retry | Sanitized context/status | Journal Control Room tests |
| Attachment upload | Empty, oversize, unsupported or spoofed MIME | HTTP 413/422 and component error | Replace/retry file | Filename only in audit event | `test_attachments.py` |
| Attachment read/download/delete | Foreign organization or missing file | HTTP 404 without existence disclosure | None / reload owner data | Organization-scoped event | `test_attachments.py` |
| PWA navigation | Network unavailable | Neutral offline page; never cached operational data | `Riprova` | Service Worker fetch failure | `product-hardening.test.js` + static endpoint tests |

The Service Worker is deliberately network-first and caches only the neutral
offline document. API responses and release assets are never served from its
cache. Unhashed application assets require HTTP revalidation.
