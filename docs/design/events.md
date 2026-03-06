# amplifierd Event Streaming Design

> How amplifierd streams real-time events to clients over SSE, including the
> event taxonomy, envelope format, data schemas, filtering, and the
> debug/raw tier system.

## Status

**Draft v0.1** — Derived from `amplifier_core.events` (51 constants), emission
site analysis across kernel, orchestrator, and foundation modules.

---

## SSE Envelope Format

Every SSE message follows this structure:

```
event: <event_name>
data: <json_payload>

```

The `event:` line uses the amplifier event name directly (e.g., `tool:pre`,
`content_block:delta`). The `data:` line is a single JSON object.

### Standard Envelope Fields

Every event payload includes these infrastructure-stamped fields:

| Field | Type | Source | Description |
|-------|------|--------|-------------|
| `timestamp` | `string` (ISO 8601 UTC) | Auto-stamped by `HookRegistry.emit()` | When the event was emitted |
| `session_id` | `string` | Default field set at session init | Session UUID |
| `parent_id` | `string \| null` | Default field set at session init | Parent session UUID (null for root) |

These fields are present on **every** event. Event-specific fields are merged
alongside them.

### Example

```
event: tool:pre
data: {"tool_name":"bash","tool_call_id":"tc_42","tool_input":{"command":"ls -la"},"timestamp":"2026-03-02T11:31:00.123Z","session_id":"abc123","parent_id":null}

```

---

## Event Taxonomy

### Emission Architecture

Events are emitted at three layers. The kernel defines the vocabulary; modules
produce the data.

```
┌─────────────────────────────────────────────────────┐
│  Layer 3: Foundation Modules                        │
│  tool-delegate, hooks-session-naming, etc.          │
│  Emits: delegate:*, deprecation:*, session-naming:* │
├─────────────────────────────────────────────────────┤
│  Layer 2: Orchestrator Modules                      │
│  loop-basic, loop-streaming, etc.                   │
│  Emits: content_block:*, thinking:*, tool:*,        │
│         llm:*, provider:*, orchestrator:*,          │
│         execution:*, context:*                      │
├─────────────────────────────────────────────────────┤
│  Layer 1: Kernel (session.py / Rust session.rs)     │
│  Emits: session:*, cancel:*                         │
└─────────────────────────────────────────────────────┘
```

### Complete Event Catalog

#### Session Lifecycle (Kernel-Emitted)

| Event | Emitter | Description |
|-------|---------|-------------|
| `session:start` | Kernel | Session initialized and ready |
| `session:start:debug` | Kernel | + truncated mount plan (gated by `debug=true`) |
| `session:start:raw` | Kernel | + full mount plan (gated by `debug=true` AND `raw_debug=true`) |
| `session:end` | Kernel (Rust) | Session completed, failed, or cancelled |
| `session:resume` | Kernel | Resumed session initialized |
| `session:resume:debug` | Kernel | + truncated mount plan |
| `session:resume:raw` | Kernel | + full mount plan |
| `session:fork` | Kernel | Child session forked from parent |
| `session:fork:debug` | Kernel | + truncated mount plan |
| `session:fork:raw` | Kernel | + full mount plan |

#### Prompt Lifecycle (Orchestrator/App-Emitted)

| Event | Emitter | Description |
|-------|---------|-------------|
| `prompt:submit` | Orchestrator | User prompt submitted for processing |
| `prompt:complete` | App layer | Full turn complete (prompt + response) |

#### Content Streaming (Orchestrator-Emitted)

| Event | Emitter | Description |
|-------|---------|-------------|
| `content_block:start` | Orchestrator | New content block beginning |
| `content_block:delta` | Orchestrator | Incremental content chunk |
| `content_block:end` | Orchestrator | Content block finished |

#### Thinking (Orchestrator-Emitted)

| Event | Emitter | Description |
|-------|---------|-------------|
| `thinking:delta` | Orchestrator | Incremental thinking chunk |
| `thinking:final` | Orchestrator | Complete thinking content |

#### Tool Invocation (Orchestrator-Emitted)

| Event | Emitter | Description |
|-------|---------|-------------|
| `tool:pre` | Orchestrator | Tool call about to execute |
| `tool:post` | Orchestrator | Tool call completed |
| `tool:error` | Orchestrator | Tool call failed |

#### Provider / LLM (Orchestrator-Emitted)

| Event | Emitter | Description |
|-------|---------|-------------|
| `provider:request` | Orchestrator | LLM request sent to provider |
| `provider:response` | Orchestrator | LLM response received |
| `provider:retry` | Orchestrator | Retrying after transient failure |
| `provider:error` | Orchestrator | Provider call failed |
| `provider:throttle` | Orchestrator | Rate limit back-pressure applied |
| `provider:resolve` | Orchestrator | Provider selected for request |
| `provider:tool_sequence_repaired` | Orchestrator | Malformed tool sequence auto-repaired |
| `llm:request` | Orchestrator | Low-level LLM request (may differ from provider:request) |
| `llm:request:debug` | Orchestrator | + truncated request body |
| `llm:request:raw` | Orchestrator | + full request body |
| `llm:response` | Orchestrator | Low-level LLM response |
| `llm:response:debug` | Orchestrator | + truncated response body |
| `llm:response:raw` | Orchestrator | + full response body |

#### Execution (Orchestrator-Emitted)

| Event | Emitter | Description |
|-------|---------|-------------|
| `execution:start` | Orchestrator | Orchestrator loop starting |
| `execution:end` | Orchestrator | Orchestrator loop ending |
| `orchestrator:complete` | Orchestrator | Turn fully complete |

#### Context (Context Module-Emitted)

| Event | Emitter | Description |
|-------|---------|-------------|
| `context:pre_compact` | Context module | About to compact context |
| `context:post_compact` | Context module | Compaction finished |
| `context:compaction` | Context module | Compaction details |
| `context:include` | Context module | Context file included |

#### Planning (Orchestrator-Emitted)

| Event | Emitter | Description |
|-------|---------|-------------|
| `plan:start` | Orchestrator | Planning phase beginning |
| `plan:end` | Orchestrator | Planning phase finished |

#### Approval (Hook/App-Emitted)

| Event | Emitter | Description |
|-------|---------|-------------|
| `approval:required` | Hook | Approval gate triggered |
| `approval:granted` | App layer | Approval given |
| `approval:denied` | App layer | Approval denied |

#### Policy (Hook-Emitted)

| Event | Emitter | Description |
|-------|---------|-------------|
| `policy:violation` | Hook | Policy rule violated |

#### User Notification (Any Module)

| Event | Emitter | Description |
|-------|---------|-------------|
| `user:notification` | Any module | Display message to user |

#### Artifact (Tool-Emitted)

| Event | Emitter | Description |
|-------|---------|-------------|
| `artifact:write` | Tool module | File or artifact written |
| `artifact:read` | Tool module | File or artifact read |

#### Cancellation (Kernel-Emitted)

| Event | Emitter | Description |
|-------|---------|-------------|
| `cancel:requested` | App layer | Cancellation requested |
| `cancel:completed` | Kernel | Cancellation finished |

#### Delegate (Foundation `tool-delegate` Module)

These are non-canonical (not in `ALL_EVENTS`) but actively emitted.

| Event | Emitter | Description |
|-------|---------|-------------|
| `delegate:agent_spawned` | tool-delegate | Child agent session created |
| `delegate:agent_completed` | tool-delegate | Child agent finished |
| `delegate:agent_resumed` | tool-delegate | Child agent session resumed |
| `delegate:error` | tool-delegate | Delegation failed |

---

## Event Data Schemas

### Session Events

#### `session:start` / `session:resume`

```json
{
  "session_id": "abc123-def456",
  "parent_id": null,
  "timestamp": "2026-03-02T11:30:00.000Z"
}
```

#### `session:start:debug` / `session:resume:debug`

```json
{
  "lvl": "DEBUG",
  "session_id": "abc123-def456",
  "mount_plan": {
    "session": {"orchestrator": "loop-basic", "context": "context-simple"},
    "providers": [{"module": "provider-anthropic", "config": {"api_key": "[REDACTED]"}}],
    "tools": [{"module": "tool-filesystem"}]
  },
  "timestamp": "2026-03-02T11:30:00.000Z"
}
```

The `mount_plan` is processed through `redact_secrets(truncate_values(config))`:
- Strings longer than 180 characters are truncated
- Keys matching sensitive patterns (`api_key`, `password`, `token`, `secret`,
  `credential`, `auth`, `authorization`, `private_key`) → `"[REDACTED]"`

#### `session:start:raw` / `session:resume:raw`

Same as `:debug` but `mount_plan` is `redact_secrets(config)` — **no
truncation**, only sensitive keys redacted.

#### `session:end`

```json
{
  "session_id": "abc123-def456",
  "status": "completed",
  "timestamp": "2026-03-02T11:35:00.000Z"
}
```

`status`: `"completed"` | `"failed"` | `"cancelled"`

#### `session:fork`

```json
{
  "parent": "parent-session-uuid",
  "session_id": "child-session-uuid",
  "timestamp": "2026-03-02T11:31:00.000Z"
}
```

Debug/raw tiers add `mount_plan` with same truncation/redaction as session:start.

### Content Streaming Events

#### `content_block:start`

```json
{
  "block_type": "text",
  "block_index": 0,
  "timestamp": "2026-03-02T11:31:01.000Z",
  "session_id": "abc123"
}
```

`block_type`: `"text"` | `"thinking"`

#### `content_block:delta`

```json
{
  "delta": "The authentication module",
  "block_index": 0,
  "timestamp": "2026-03-02T11:31:01.050Z",
  "session_id": "abc123"
}
```

`delta` may also be a dict for provider-native formats:
`{"type": "text_delta", "text": "..."}` (Anthropic).

#### `content_block:end`

```json
{
  "block_index": 0,
  "block": {"text": "The authentication module handles user login..."},
  "timestamp": "2026-03-02T11:31:02.000Z",
  "session_id": "abc123"
}
```

### Thinking Events

#### `thinking:delta`

```json
{
  "delta": "Let me consider the architecture...",
  "timestamp": "2026-03-02T11:31:01.000Z",
  "session_id": "abc123"
}
```

#### `thinking:final`

```json
{
  "content": "Let me consider the architecture of this module...",
  "timestamp": "2026-03-02T11:31:02.000Z",
  "session_id": "abc123"
}
```

### Tool Events

#### `tool:pre`

```json
{
  "tool_name": "bash",
  "tool_call_id": "tc_42",
  "tool_input": {
    "command": "ls -la src/"
  },
  "timestamp": "2026-03-02T11:31:03.000Z",
  "session_id": "abc123"
}
```

#### `tool:post`

```json
{
  "tool_name": "bash",
  "tool_call_id": "tc_42",
  "result": {
    "success": true,
    "output": "total 48\ndrwxr-xr-x 6 user user 4096 ...",
    "error": null
  },
  "timestamp": "2026-03-02T11:31:04.000Z",
  "session_id": "abc123"
}
```

#### `tool:error`

```json
{
  "tool_call_id": "tc_42",
  "error": "Command timed out after 30 seconds",
  "timestamp": "2026-03-02T11:31:34.000Z",
  "session_id": "abc123"
}
```

### Provider / LLM Events

#### `llm:response` / `provider:response`

```json
{
  "usage": {
    "input_tokens": 1500,
    "output_tokens": 800,
    "total_tokens": 2300,
    "cache_read_tokens": 500,
    "cache_write_tokens": null
  },
  "model": "claude-sonnet-4-20250514",
  "provider": "anthropic",
  "duration_ms": 2340,
  "timestamp": "2026-03-02T11:31:05.000Z",
  "session_id": "abc123"
}
```

#### `llm:request:debug`

```json
{
  "lvl": "DEBUG",
  "messages": [
    {"role": "system", "content": "You are Amplifier... (truncated 15000 chars)"},
    {"role": "user", "content": "Explain the auth module"}
  ],
  "tools": [{"name": "bash", "parameters": {"...": "..."}}],
  "model": "claude-sonnet-4-20250514",
  "timestamp": "2026-03-02T11:31:03.000Z",
  "session_id": "abc123"
}
```

Processed through `redact_secrets(truncate_values(...))`.

### Orchestrator Events

#### `orchestrator:complete`

```json
{
  "turn_count": 1,
  "model": "claude-sonnet-4-20250514",
  "timestamp": "2026-03-02T11:31:10.000Z",
  "session_id": "abc123"
}
```

### Cancellation Events

#### `cancel:completed`

Clean completion:
```json
{
  "was_immediate": false,
  "timestamp": "2026-03-02T11:31:10.000Z",
  "session_id": "abc123"
}
```

Error path:
```json
{
  "was_immediate": true,
  "error": "AbortError: Execution cancelled by user",
  "timestamp": "2026-03-02T11:31:10.000Z",
  "session_id": "abc123"
}
```

### Delegate Events

#### `delegate:agent_spawned`

```json
{
  "agent": "foundation:explorer",
  "sub_session_id": "abc123-childspan_foundation-explorer",
  "parent_session_id": "abc123",
  "context_depth": "recent",
  "context_scope": "conversation",
  "timestamp": "2026-03-02T11:31:05.000Z",
  "session_id": "abc123"
}
```

#### `delegate:agent_completed`

```json
{
  "agent": "foundation:explorer",
  "sub_session_id": "abc123-childspan_foundation-explorer",
  "parent_session_id": "abc123",
  "success": true,
  "timestamp": "2026-03-02T11:31:15.000Z",
  "session_id": "abc123"
}
```

#### `delegate:error`

```json
{
  "agent": "foundation:explorer",
  "sub_session_id": "abc123-childspan_foundation-explorer",
  "parent_session_id": "abc123",
  "error": "Agent timed out after 300 seconds",
  "timestamp": "2026-03-02T11:31:15.000Z",
  "session_id": "abc123"
}
```

### Approval Events

#### `approval:required`

```json
{
  "request_id": "apr_1",
  "tool_name": "bash",
  "action": "rm -rf build/",
  "risk_level": "high",
  "prompt": "Allow deleting the build directory?",
  "options": ["allow", "deny"],
  "timeout": 300.0,
  "default": "deny",
  "timestamp": "2026-03-02T11:31:05.000Z",
  "session_id": "abc123"
}
```

---

## The Three-Tier Debug System

Events with rich payloads follow a three-tier pattern to control verbosity
and protect sensitive data.

| Tier | Suffix | Gating Config | Processing Applied |
|------|--------|---------------|-------------------|
| **Base** | (none) | Always emitted | Core identifiers only |
| **Debug** | `:debug` | `session.debug = true` | `redact_secrets(truncate_values(data))` |
| **Raw** | `:raw` | `session.debug = true` AND `session.raw_debug = true` | `redact_secrets(data)` — no truncation |

**Events with debug tiers:**

| Base | Debug | Raw |
|------|-------|-----|
| `session:start` | `session:start:debug` | `session:start:raw` |
| `session:resume` | `session:resume:debug` | `session:resume:raw` |
| `session:fork` | `session:fork:debug` | `session:fork:raw` |
| `llm:request` | `llm:request:debug` | `llm:request:raw` |
| `llm:response` | `llm:response:debug` | `llm:response:raw` |

### Truncation Rules (`truncate_values`)

- Recursively walks dicts and lists
- Strings longer than **180 characters** → `"{first_180}... (truncated N chars)"`
- Non-string values (ints, bools, nulls, nested dicts/lists) are preserved

### Redaction Rules (`redact_secrets`)

- Recursively walks dicts
- Keys matching (case-insensitive): `api_key`, `apikey`, `api-key`, `secret`,
  `password`, `token`, `credential`, `credentials`, `private_key`,
  `privatekey`, `auth`, `authorization` → value replaced with `"[REDACTED]"`
- Applied on ALL tiers (even `:raw` redacts secrets)

---

## Client-Side Filtering

### SSE `events` Query Parameter

Clients can filter which events they receive:

```
GET /sessions/{id}/events?events=content_block:delta,tool:pre,tool:post,orchestrator:complete
```

If omitted, **all events** are streamed.

### Filter Patterns

| Pattern | Matches |
|---------|---------|
| `content_block:delta` | Exact match |
| `content_block:*` | All content_block events |
| `tool:*` | `tool:pre`, `tool:post`, `tool:error` |
| `session:*` | All session lifecycle events (including debug/raw tiers) |
| `*:debug` | All debug-tier events |
| `*:raw` | All raw-tier events |

### Preset Filters

For convenience, named presets:

| Preset | Equivalent Filter | Use Case |
|--------|-------------------|----------|
| `?preset=streaming` | `content_block:*,thinking:*,done` | Text streaming UI |
| `?preset=tools` | `tool:pre,tool:post,tool:error` | Tool execution monitor |
| `?preset=full` | (no filter) | Full observability |
| `?preset=minimal` | `orchestrator:complete,error,done` | Simple request/response |
| `?preset=debug` | `*:debug` | Debug-level diagnostics |

---

## amplifierd-Owned Synthetic Events

These events are generated by the daemon itself, not by amplifier-core modules.

### `done`

Signals the end of a streaming response. Always the last event in an
`/execute/stream` SSE connection.

```json
{
  "status": "complete",
  "timestamp": "2026-03-02T11:31:10.000Z"
}
```

`status`: `"complete"` | `"error"` | `"cancelled"`

### `error`

Streamed error (see `errors.md` for full Problem Details shape).

```json
{
  "type": "https://amplifier.dev/errors/rate-limit",
  "title": "Rate Limit Exceeded",
  "status": 429,
  "detail": "...",
  "retryable": true,
  "retry_after_seconds": 30,
  "error_class": "RateLimitError"
}
```

### `keepalive`

Sent periodically on idle SSE connections to prevent proxy/load-balancer
timeouts.

```
event: keepalive
data: {}

```

Interval: every **15 seconds** of inactivity.

---

## `emit_and_collect` Events

The `HookRegistry` has a second emission method: `emit_and_collect(event, data)`
which gathers responses from all handlers (no short-circuit, no auto-stamping).

This pattern is used for **decision-gathering** — e.g., "multiple hooks propose
candidates and the caller aggregates." It is currently unused in production and
is not streamed to clients. If it gains usage, it would be exposed as internal
diagnostic events only.

---

## Implementation Notes

### Event Hook Registration

The daemon registers a hook on `ALL_EVENTS` to capture events for streaming:

```python
import asyncio
from amplifier_core.events import ALL_EVENTS

queue: asyncio.Queue[tuple[str, dict]] = asyncio.Queue()

async def event_capture_hook(event: str, data: dict) -> HookResult:
    await queue.put((event, data))
    return HookResult(action="continue")

# Register at lowest priority so other hooks run first
for event_name in ALL_EVENTS:
    hooks.register(event_name, event_capture_hook, priority=-1000, name="amplifierd-sse")
```

For delegate events (not in `ALL_EVENTS`), register explicitly:

```python
for event_name in ["delegate:agent_spawned", "delegate:agent_completed",
                    "delegate:agent_resumed", "delegate:error"]:
    hooks.register(event_name, event_capture_hook, priority=-1000)
```

### Backpressure

If the SSE client falls behind, the queue will grow. Strategies:

- **Bounded queue** with configurable max size (default: 10,000 events)
- **Drop policy**: Drop oldest events when full (content deltas are ephemeral)
- **Disconnect**: Close SSE connection if client is unresponsive for > 60s

### Connection Lifecycle

```
Client connects → GET /sessions/{id}/events
                    ↓
Server registers hook on ALL_EVENTS
                    ↓
Events flow: HookRegistry.emit() → queue → SSE writer → client
                    ↓
Client disconnects or session ends
                    ↓
Server unregisters hook, drains queue
```
