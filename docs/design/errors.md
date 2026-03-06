# amplifierd Error Response Design

> How amplifierd maps internal errors to HTTP responses using
> RFC 7807 Problem Details.

## Status

**Draft v0.1** — Derived from `amplifier-core` LLMError hierarchy (16 classes)
and `amplifier-foundation` BundleError hierarchy (5 classes).

---

## Error Response Envelope

All error responses use [RFC 7807 Problem Details](https://www.rfc-editor.org/rfc/rfc7807):

```json
{
  "type": "https://amplifier.dev/errors/rate-limit",
  "title": "Rate Limit Exceeded",
  "status": 429,
  "detail": "Anthropic rate limit hit for claude-sonnet-4-20250514. Retry after 30s.",
  "instance": "/sessions/abc123/execute",

  "retryable": true,
  "retry_after_seconds": 30,
  "provider": "anthropic",
  "model": "claude-sonnet-4-20250514",
  "error_class": "RateLimitError"
}
```

| Field | Source | Required |
|-------|--------|----------|
| `type` | Static URI per error class | Yes |
| `title` | Human-readable, static per class | Yes |
| `status` | HTTP status code | Yes |
| `detail` | Specific message from the exception | Yes |
| `instance` | Request path that triggered the error | Yes |
| `retryable` | From `LLMError.retryable` | Yes (for LLM errors) |
| `retry_after_seconds` | From `RateLimitError.retry_after` | When available |
| `provider` | From `LLMError.provider` | When available |
| `model` | From `LLMError.model` | When available |
| `error_class` | Python class name for debugging | Yes |

---

## Error Categories

### 1. LLM Errors (Provider-Originated)

These errors originate from LLM provider calls during `session.execute()`.
The amplifier-core `LLMError` hierarchy normalizes errors across providers
(Anthropic, OpenAI, Azure, etc.) into a common taxonomy.

#### Inheritance Tree

```
LLMError                              → 502 Bad Gateway
├── RateLimitError                    → 429 Too Many Requests
│   └── QuotaExceededError            → 429 Too Many Requests
├── AuthenticationError               → 502 Bad Gateway
│   └── AccessDeniedError             → 502 Bad Gateway
├── ContextLengthError                → 413 Content Too Large
├── ContentFilterError                → 422 Unprocessable Content
├── InvalidRequestError               → 400 Bad Request
├── ProviderUnavailableError          → 503 Service Unavailable
│   └── NetworkError                  → 503 Service Unavailable
├── LLMTimeoutError                   → 504 Gateway Timeout
├── NotFoundError                     → 502 Bad Gateway
├── StreamError                       → 502 Bad Gateway
├── AbortError                        → 499 Client Closed Request
├── InvalidToolCallError              → 502 Bad Gateway
└── ConfigurationError                → 500 Internal Server Error
```

#### Full Mapping Table

| LLMError Class | HTTP Status | `Retry-After` Header | `retryable` | Type URI Suffix | Rationale |
|----------------|-------------|---------------------|-------------|-----------------|-----------|
| `RateLimitError` | **429** | Yes (from `e.retry_after`) | `true` | `/rate-limit` | Direct mapping — provider returned 429 |
| `QuotaExceededError` | **429** | No | `false` | `/quota-exceeded` | Same status family but NOT retryable (hard billing limit) |
| `AuthenticationError` | **502** | No | `false` | `/provider-auth` | amplifierd's client isn't at fault — the daemon's provider credentials failed |
| `AccessDeniedError` | **502** | No | `false` | `/provider-access-denied` | Valid creds but provider denied access — daemon-side issue |
| `ContextLengthError` | **413** | No | `false` | `/context-too-large` | Request too large for provider's context window |
| `ContentFilterError` | **422** | No | `false` | `/content-filtered` | Provider safety system blocked the content |
| `InvalidRequestError` | **400** | No | `false` | `/invalid-request` | Malformed request passed through to provider |
| `ProviderUnavailableError` | **503** | No | `true` | `/provider-unavailable` | Provider returned 5xx |
| `NetworkError` | **503** | No | `true` | `/network-error` | DNS/TCP/TLS failure — no HTTP response at all |
| `LLMTimeoutError` | **504** | No | `true` | `/provider-timeout` | Provider request timed out |
| `NotFoundError` | **502** | No | `false` | `/provider-not-found` | Provider returned 404 (model doesn't exist, etc.) |
| `StreamError` | **502** | No | `true` | `/stream-error` | Mid-stream connection drop |
| `AbortError` | **499** | No | `false` | `/aborted` | Caller cancelled (via `/cancel` endpoint) |
| `InvalidToolCallError` | **502** | No | `false` | `/invalid-tool-call` | LLM generated a malformed tool call |
| `ConfigurationError` | **500** | No | `false` | `/configuration-error` | Missing API key, invalid provider config |
| `LLMError` (base) | **502** | No | `false` | `/llm-error` | Unclassified provider error |

#### Why 502 for Auth/Access/NotFound?

The amplifierd client is not the one with bad credentials — the **daemon's
configured provider** has the problem. From the client's perspective, the daemon
(acting as a gateway) received an invalid response from the upstream provider.
This is textbook 502.

If the client had sent invalid credentials to amplifierd itself, that would be
401/403 — but amplifierd has no authentication (design decision).

#### `Retry-After` Header

Set on 429 responses when `RateLimitError.retry_after` is available:

```
HTTP/1.1 429 Too Many Requests
Retry-After: 30
Content-Type: application/problem+json

{"type": "https://amplifier.dev/errors/rate-limit", ...}
```

---

### 2. Bundle Errors (Foundation-Originated)

These errors come from bundle loading, composition, and preparation.

| Exception Class | HTTP Status | Type URI Suffix | When |
|----------------|-------------|-----------------|------|
| `BundleNotFoundError` | **404** | `/bundle-not-found` | Bundle URI doesn't resolve |
| `BundleLoadError` | **422** | `/bundle-load-error` | Bundle exists but can't be parsed |
| `BundleValidationError` | **422** | `/bundle-validation-error` | Bundle parsed but fails validation |
| `BundleDependencyError` | **422** | `/bundle-dependency-error` | Circular or missing dependencies |
| `BundleError` (base) | **500** | `/bundle-error` | Unclassified bundle error |

---

### 3. Module Errors (Loader-Originated)

| Exception Class | HTTP Status | Type URI Suffix | When |
|----------------|-------------|-----------------|------|
| `ModuleNotFoundError` | **404** | `/module-not-found` | Module not in any resolution layer |
| `ModuleLoadError` | **422** | `/module-load-error` | Module found but import/mount failed |
| `ModuleValidationError` | **422** | `/module-validation-error` | Module fails protocol compliance |
| `ModuleActivationError` | **422** | `/module-activation-error` | Dependency install or activation failed |

---

### 4. Session Errors (Daemon-Originated)

These are amplifierd's own errors, not inherited from core/foundation.

| Condition | HTTP Status | Type URI Suffix | When |
|-----------|-------------|-----------------|------|
| Session not found | **404** | `/session-not-found` | Unknown `session_id` in path |
| Session not running | **409** | `/session-not-running` | Execute/cancel on a completed/failed session |
| Session already exists | **409** | `/session-already-exists` | Create with duplicate `session_id` |
| Execution in progress | **409** | `/execution-in-progress` | Second execute while one is active |
| Approval not found | **404** | `/approval-not-found` | Unknown `request_id` |
| Approval already resolved | **409** | `/approval-already-resolved` | Responding to a resolved approval |
| Approval timeout | **408** | `/approval-timeout` | `ApprovalTimeoutError` from core |

---

### 5. Request Validation Errors

Standard HTTP 400/422 for malformed client requests — these are not
domain-specific.

| Condition | HTTP Status | Type URI Suffix |
|-----------|-------------|-----------------|
| Missing required field | **422** | `/validation-error` |
| Invalid field value | **422** | `/validation-error` |
| Malformed JSON body | **400** | `/malformed-request` |
| Unknown endpoint | **404** | (standard) |
| Method not allowed | **405** | (standard) |

---

## SSE Error Events

During streaming execution (`/execute/stream`), errors are delivered as SSE
events rather than HTTP status codes (the 200 response is already sent).

```
event: error
data: {"type": "https://amplifier.dev/errors/rate-limit", "title": "Rate Limit Exceeded", "status": 429, "detail": "...", "retryable": true, "retry_after_seconds": 30, "provider": "anthropic", "model": "claude-sonnet-4-20250514", "error_class": "RateLimitError"}

event: done
data: {"status": "error"}
```

The `error` event uses the same Problem Details shape as HTTP error responses.
The stream always terminates with a `done` event, with `status` set to
`"error"` or `"complete"`.

---

## WebSocket Error Frames

On WebSocket connections (approvals), errors are sent as structured messages:

```json
{
  "type": "error",
  "error": {
    "type": "https://amplifier.dev/errors/approval-timeout",
    "title": "Approval Timeout",
    "status": 408,
    "detail": "Approval request apr_1 timed out after 300s"
  }
}
```

---

## Error Classification Internals

amplifier-core provides `classify_error_message()` for mapping raw provider
error strings to `LLMError` subtypes. This is used internally when providers
raise generic exceptions.

**Classification priority:**

1. **HTTP status code** (unambiguous codes only):

   | Status | Maps to |
   |--------|---------|
   | 401 | `AuthenticationError` |
   | 403 | `AccessDeniedError` |
   | 404 | `NotFoundError` |
   | 413 | `ContextLengthError` |
   | 429 | `RateLimitError` |
   | >= 500 | `ProviderUnavailableError` |
   | 400, 422 | Falls through to message heuristics |

2. **Message heuristics** (case-insensitive, checked in order):

   | Pattern | Maps to |
   |---------|---------|
   | "context length", "too many tokens", "maximum context" | `ContextLengthError` |
   | "rate limit", "too many requests" | `RateLimitError` |
   | "authentication", "api key", "unauthorized" | `AuthenticationError` |
   | "not found" | `NotFoundError` |
   | "content filter", "safety", "blocked" | `ContentFilterError` |
   | (no match) + status 400/422 | `InvalidRequestError` |
   | (no match) | `LLMError` (base) |

3. **Fallback**: Unclassified errors become base `LLMError` → HTTP 502.

---

## Additional Error Properties

Some `LLMError` subtypes carry extra context:

| Class | Extra Fields | Exposed In Response |
|-------|-------------|---------------------|
| `RateLimitError` | `retry_after: float` | `retry_after_seconds` + `Retry-After` header |
| `InvalidToolCallError` | `tool_name: str`, `raw_arguments: str` | `tool_name`, `raw_arguments` |
| All `LLMError` | `provider: str`, `model: str`, `status_code: int` | `provider`, `model`, `upstream_status` |
| All `LLMError` | `delay_multiplier: float` | Not exposed (internal retry tuning) |

---

## Implementation Notes

### Error Handler Skeleton

```python
from amplifier_core import (
    LLMError, RateLimitError, QuotaExceededError,
    AuthenticationError, AccessDeniedError,
    ContextLengthError, ContentFilterError, InvalidRequestError,
    ProviderUnavailableError, NetworkError, LLMTimeoutError,
    NotFoundError, StreamError, AbortError,
    InvalidToolCallError, ConfigurationError,
)
from amplifier_foundation import (
    BundleNotFoundError, BundleLoadError,
    BundleValidationError, BundleDependencyError,
)

# Order matters — catch specific subclasses before parents.
LLM_ERROR_MAP: list[tuple[type, int, str]] = [
    (QuotaExceededError,        429, "quota-exceeded"),
    (RateLimitError,            429, "rate-limit"),
    (AccessDeniedError,         502, "provider-access-denied"),
    (AuthenticationError,       502, "provider-auth"),
    (ContextLengthError,        413, "context-too-large"),
    (ContentFilterError,        422, "content-filtered"),
    (InvalidRequestError,       400, "invalid-request"),
    (NetworkError,              503, "network-error"),
    (ProviderUnavailableError,  503, "provider-unavailable"),
    (LLMTimeoutError,           504, "provider-timeout"),
    (NotFoundError,             502, "provider-not-found"),
    (StreamError,               502, "stream-error"),
    (AbortError,                499, "aborted"),
    (InvalidToolCallError,      502, "invalid-tool-call"),
    (ConfigurationError,        500, "configuration-error"),
    (LLMError,                  502, "llm-error"),
]
```

### Catch Order

Because the hierarchy has 3 levels of inheritance, **subclasses must be caught
first**:

- `QuotaExceededError` before `RateLimitError` (overrides `retryable`)
- `AccessDeniedError` before `AuthenticationError` (different semantics)
- `NetworkError` before `ProviderUnavailableError` (more specific)

The `LLM_ERROR_MAP` list above is ordered correctly for `isinstance()` matching.

### Gap from Existing distro-server

The current `distro-server` catches all errors as bare `except Exception` and
returns generic "Check server logs" messages, discarding the `LLMError` type,
`retryable` flag, `retry_after`, `provider`, and `model`. amplifierd should
not repeat this — all error metadata must be preserved in responses.
