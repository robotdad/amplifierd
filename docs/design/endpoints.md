# amplifierd Endpoint Design

> Design document for the Amplifier daemon — a service exposing amplifier-core
> and amplifier-foundation capabilities over HTTP, WebSocket, and SSE.

## Status

**Draft v0.1** — Initial endpoint inventory derived from the public API surfaces
of `amplifier-core` (v1.0.7) and `amplifier-foundation`.

## Design Decisions

| Decision | Resolution |
|----------|-----------|
| **Authentication** | None. The daemon runs on localhost for the local user. |
| **Multi-tenancy** | Single-user. No session isolation or resource limits between tenants. |
| **Persistence** | Filesystem — `transcript.jsonl` + `metadata.json`, same as CLI. |
| **Relationship to distro-server** | None. distro-server is an "experience server" (chat, slack, voice UIs). amplifierd is a lower-level daemon exposing raw capabilities. |
| **gRPC** | Not now. HTTP + SSE + WebSocket only. Can revisit later. |
| **Contribution system** | Not exposed. Internal-only kernel mechanism (see appendix). |
| **Hot-reload** | Yes, for dev workflows. Explicit endpoints for reloading bundles/modules into running sessions. |

## Design Principles

1. **Thin service layer** — amplifierd is a transport adapter, not a new
   abstraction. Every endpoint maps directly to one or more kernel/foundation
   calls.
2. **Session-oriented** — Sessions are the unit of state. Most endpoints operate
   within a session context.
3. **Streaming-first** — Execution endpoints support SSE for real-time event
   delivery. WebSocket is available for bidirectional flows (approvals,
   cancellation).
4. **Stateless where possible** — Bundle loading, validation, and module
   discovery don't require session state.
5. **Localhost, no auth** — The daemon binds to `127.0.0.1` by default. No
   authentication layer. Any local process can connect.
6. **Dev-friendly** — Hot-reload of bundles and modules without restarting
   sessions, for fast iteration during development.

## Transport Conventions

| Pattern | Transport | Use Case |
|---------|-----------|----------|
| Request/Response | HTTP REST | CRUD, queries, one-shot operations |
| Server-push stream | SSE (`text/event-stream`) | Execution events, streaming responses |
| Bidirectional | WebSocket | Interactive approval, live cancellation |
| Long-poll fallback | HTTP with timeout | Approval resolution for simple clients |

All endpoints return JSON. Errors use RFC 7807 Problem Details.

---

## Table of Contents

1. [Session Lifecycle](#1-session-lifecycle)
2. [Execution](#2-execution)
3. [Event Streaming](#3-event-streaming)
4. [Cancellation](#4-cancellation)
5. [Approval System](#5-approval-system)
6. [Agent Delegation & Spawning](#6-agent-delegation--spawning)
7. [Context Management](#7-context-management)
8. [Module Management](#8-module-management)
9. [Bundle Management](#9-bundle-management)
10. [Session Fork & History](#10-session-fork--history)
11. [Validation](#11-validation)
12. [Introspection & Health](#12-introspection--health)
13. [Configuration](#13-configuration)
14. [Hot-Reload (Dev)](#14-hot-reload-dev)

---

## 1. Session Lifecycle

Wraps `AmplifierSession` init/execute/cleanup and `PreparedBundle.create_session()`.

### `POST /sessions`

Create a new session.

**Maps to:** `PreparedBundle.create_session()` → `AmplifierSession.__init__()` → `session.initialize()`

**Request body:**
```json
{
  "bundle": "foundation",
  "bundle_uri": "git+https://github.com/microsoft/amplifier-foundation@main",
  "session_id": null,
  "parent_id": null,
  "session_cwd": "/home/user/project",
  "config_overrides": {}
}
```

One of `bundle` (registry name) or `bundle_uri` (direct URI) is required.
`config_overrides` is deep-merged into the bundle's mount plan.

**Response:** `201 Created`
```json
{
  "session_id": "abc123-def456",
  "status": "running",
  "bundle": "foundation",
  "created_at": "2026-03-02T11:30:00Z",
  "config": { "...mount plan summary..." }
}
```

**Lifecycle:** `load_bundle()` → `bundle.prepare()` → `prepared.create_session()` →
register spawn capability → register persistence hooks.

---

### `GET /sessions`

List active sessions.

**Maps to:** Internal session store query.

**Query params:** `?status=running&limit=50&offset=0`

**Response:** `200 OK`
```json
{
  "sessions": [
    {
      "session_id": "abc123-def456",
      "status": "running",
      "bundle": "foundation",
      "created_at": "2026-03-02T11:30:00Z",
      "last_activity": "2026-03-02T11:31:00Z",
      "total_messages": 12,
      "tool_invocations": 5
    }
  ],
  "total": 1
}
```

---

### `GET /sessions/{session_id}`

Get session details.

**Maps to:** `SessionStatus.to_dict()` + `coordinator.to_dict()`

**Response:** `200 OK`
```json
{
  "session_id": "abc123-def456",
  "status": "running",
  "parent_id": null,
  "bundle": "foundation",
  "created_at": "2026-03-02T11:30:00Z",
  "last_activity": "2026-03-02T11:31:00Z",
  "stats": {
    "total_messages": 12,
    "tool_invocations": 5,
    "tool_successes": 4,
    "tool_failures": 1,
    "total_input_tokens": 15000,
    "total_output_tokens": 8000,
    "estimated_cost": 0.045
  },
  "mounted_modules": {
    "orchestrator": "loop-basic",
    "context": "context-simple",
    "providers": ["provider-anthropic"],
    "tools": ["tool-filesystem", "tool-bash", "tool-delegate"],
    "hooks": ["hooks-approval"]
  },
  "capabilities": ["tools", "streaming", "thinking"]
}
```

---

### `POST /sessions/{session_id}/resume`

Resume a previously persisted session.

**Maps to:** Load transcript → `create_session(is_resumed=True)` →
`context.set_messages(transcript)` → re-inject system prompt.

**Request body:**
```json
{
  "session_dir": "/home/user/.amplifier/projects/myproject/sessions/abc123"
}
```

If `session_dir` is omitted, the daemon looks up the session in its own store.

**Response:** `200 OK` — same shape as `POST /sessions`.

---

### `DELETE /sessions/{session_id}`

Destroy a session (cleanup resources).

**Maps to:** `session.cleanup()` → `coordinator.cleanup()` → `loader.cleanup()`

Emits `session:end` event before cleanup.

**Response:** `204 No Content`

---

## 2. Execution

Wraps `session.execute(prompt)` — the core orchestration loop.

### `POST /sessions/{session_id}/execute`

Execute a prompt (synchronous, full response).

**Maps to:** `AmplifierSession.execute(prompt)`

**Request body:**
```json
{
  "prompt": "Explain the authentication module",
  "metadata": {}
}
```

**Response:** `200 OK`
```json
{
  "response": "The authentication module...",
  "usage": {
    "input_tokens": 1500,
    "output_tokens": 800,
    "total_tokens": 2300
  },
  "tool_calls": [
    {"id": "tc_1", "name": "read_file", "status": "success"}
  ],
  "finish_reason": "end_turn"
}
```

---

### `POST /sessions/{session_id}/execute/stream`

Execute a prompt with streaming events via SSE.

**Maps to:** `session.execute(prompt)` + `HookRegistry` event capture on
`ALL_EVENTS` → push to SSE stream.

**Request body:** Same as `/execute`.

**Response:** `200 OK` with `Content-Type: text/event-stream`

```
event: session:start
data: {"session_id": "abc123", "timestamp": "..."}

event: llm:request
data: {"provider": "anthropic", "model": "claude-sonnet-4-20250514", "timestamp": "..."}

event: content:block:delta
data: {"type": "text", "text": "The authentication"}

event: content:block:delta
data: {"type": "text", "text": " module handles..."}

event: tool:pre
data: {"tool": "read_file", "call_id": "tc_1", "input": {"file_path": "src/auth.py"}}

event: tool:post
data: {"tool": "read_file", "call_id": "tc_1", "success": true}

event: content:block:delta
data: {"type": "text", "text": "Based on the source..."}

event: orchestrator:complete
data: {"response": "The authentication module...", "usage": {...}}

event: done
data: {}
```

**Event taxonomy** (maps directly to `amplifier_core.events`):

| Event Category | Events Streamed |
|---------------|-----------------|
| Session | `session:start`, `session:end`, `session:resume` |
| Prompt | `prompt:submit`, `prompt:complete` |
| LLM | `llm:request`, `llm:response` |
| Content | `content:block:start`, `content:block:delta`, `content:block:end` |
| Thinking | `thinking:delta`, `thinking:final` |
| Tool | `tool:pre`, `tool:post`, `tool:error` |
| Provider | `provider:request`, `provider:response`, `provider:retry`, `provider:error` |
| Context | `context:pre_compact`, `context:post_compact` |
| Orchestrator | `orchestrator:complete` |
| Approval | `approval:required`, `approval:granted`, `approval:denied` |
| Cancel | `cancel:requested`, `cancel:completed` |
| Meta | `done` (stream-only, signals end of response) |

---

## 3. Event Streaming

Subscribe to session events independently of execution.

### `GET /sessions/{session_id}/events` (SSE)

Subscribe to a live event stream for a session.

**Maps to:** `HookRegistry.register()` on `ALL_EVENTS` → SSE push.

**Query params:** `?events=tool:pre,tool:post,content:block:delta` (filter, optional)

Useful for:
- Monitoring dashboards
- Connecting a separate UI to an already-running session
- Observability and logging

---

### `GET /sessions/{session_id}/events/history`

Retrieve past events for a session (from persisted `events.jsonl`).

**Maps to:** Session store event log query.

**Query params:** `?since=2026-03-02T11:30:00Z&event_types=tool:pre,tool:post&limit=100`

**Response:** `200 OK`
```json
{
  "events": [
    {"event": "tool:pre", "data": {...}, "timestamp": "..."},
    {"event": "tool:post", "data": {...}, "timestamp": "..."}
  ],
  "total": 2,
  "has_more": false
}
```

---

## 4. Cancellation

Wraps `CancellationToken` — cooperative cancellation of running executions.

### `POST /sessions/{session_id}/cancel`

Cancel a running execution.

**Maps to:** `coordinator.request_cancel(immediate)` →
`CancellationToken.request_graceful()` or `.request_immediate()`

**Request body:**
```json
{
  "immediate": false
}
```

| `immediate` | Behavior |
|-------------|----------|
| `false` | Graceful — waits for running tool calls to complete |
| `true` | Immediate — stops as soon as possible |

**Response:** `200 OK`
```json
{
  "state": "graceful",
  "running_tools": ["read_file"]
}
```

---

### `GET /sessions/{session_id}/cancel/status`

Check cancellation state.

**Maps to:** `CancellationToken.state`, `.running_tools`, `.running_tool_names`

**Response:** `200 OK`
```json
{
  "state": "graceful",
  "is_cancelled": true,
  "is_graceful": true,
  "is_immediate": false,
  "running_tools": [
    {"call_id": "tc_1", "name": "bash"}
  ]
}
```

---

## 5. Approval System

Wraps `ApprovalProvider` / `ApprovalSystem` — interactive approval gates for
tool calls and hook-requested approvals.

### `GET /sessions/{session_id}/approvals`

List pending approval requests.

**Maps to:** Internal approval queue (populated by hooks returning
`HookResult(action="ask_user")`).

**Response:** `200 OK`
```json
{
  "pending": [
    {
      "request_id": "apr_1",
      "tool_name": "bash",
      "action": "rm -rf build/",
      "risk_level": "high",
      "prompt": "Allow deleting the build directory?",
      "options": ["allow", "deny"],
      "timeout": 300.0,
      "default": "deny",
      "created_at": "2026-03-02T11:31:00Z"
    }
  ]
}
```

---

### `POST /sessions/{session_id}/approvals/{request_id}`

Respond to an approval request.

**Maps to:** `ApprovalSystem.request_approval()` resolution.

**Request body:**
```json
{
  "decision": "allow",
  "reason": "Build directory is regenerable",
  "remember": false
}
```

**Response:** `200 OK`
```json
{
  "request_id": "apr_1",
  "decision": "allow",
  "resolved_at": "2026-03-02T11:31:05Z"
}
```

---

### WebSocket: `WS /sessions/{session_id}/approvals/ws`

Bidirectional approval channel. The server pushes approval requests as they
arrive; the client sends decisions in real-time. This avoids polling.

**Server → Client:**
```json
{"type": "approval_request", "request_id": "apr_1", "tool_name": "bash", "action": "rm -rf build/", "risk_level": "high", "prompt": "Allow?", "options": ["allow", "deny"]}
```

**Client → Server:**
```json
{"type": "approval_response", "request_id": "apr_1", "decision": "allow"}
```

---

## 6. Agent Delegation & Spawning

Wraps `PreparedBundle.spawn()` and the `session.spawn` capability.

### `POST /sessions/{session_id}/spawn`

Spawn a child agent session.

**Maps to:** `coordinator.get_capability("session.spawn")` →
`PreparedBundle.spawn(child_bundle, instruction, ...)`

**Request body:**
```json
{
  "agent": "foundation:explorer",
  "instruction": "Survey the authentication module",
  "context_depth": "recent",
  "context_scope": "conversation",
  "context_turns": 5,
  "provider_preferences": [
    {"provider": "anthropic", "model": "claude-sonnet-4-20250514"}
  ],
  "model_role": "research"
}
```

**Response:** `200 OK`
```json
{
  "output": "The authentication module contains...",
  "session_id": "abc123-child-span_foundation-explorer",
  "status": "success",
  "turn_count": 5,
  "metadata": {}
}
```

---

### `POST /sessions/{session_id}/spawn/stream`

Spawn with streaming — child session events are streamed back via SSE.

Same request body as `/spawn`. Response is SSE with child session events
prefixed by `child:`:

```
event: child:session:start
data: {"session_id": "abc123-child-span_foundation-explorer"}

event: child:content:block:delta
data: {"type": "text", "text": "Surveying..."}

event: child:orchestrator:complete
data: {"output": "The authentication module...", "turn_count": 5}

event: done
data: {}
```

---

### `POST /sessions/{session_id}/spawn/{child_session_id}/resume`

Resume a child agent session (multi-turn delegation).

**Maps to:** Session resume with `session_id` lookup → `session.execute(instruction)`

**Request body:**
```json
{
  "instruction": "Now also check the test coverage"
}
```

---

### `GET /sessions/{session_id}/agents`

List available agents for this session (from bundle config).

**Maps to:** `coordinator.config["agents"]`

**Response:** `200 OK`
```json
{
  "agents": {
    "foundation:explorer": {
      "description": "Deep local-context reconnaissance agent",
      "model_role": "general"
    },
    "foundation:zen-architect": {
      "description": "Architecture design and review",
      "model_role": "reasoning"
    }
  }
}
```

---

## 7. Context Management

Wraps `ContextManager` protocol — the session's message history and memory.

### `GET /sessions/{session_id}/context/messages`

Retrieve conversation messages.

**Maps to:** `context.get_messages()`

**Query params:** `?format=raw` (raw) or `?format=request&token_budget=100000`
(as prepared for LLM request via `get_messages_for_request()`)

**Response:** `200 OK`
```json
{
  "messages": [
    {"role": "system", "content": "You are Amplifier..."},
    {"role": "user", "content": "Explain auth"},
    {"role": "assistant", "content": "The auth module..."}
  ],
  "total": 3
}
```

---

### `POST /sessions/{session_id}/context/messages`

Inject a message into context (for system prompts, context injection).

**Maps to:** `context.add_message(message)`

**Request body:**
```json
{
  "role": "system",
  "content": "Additional context: the user prefers TypeScript."
}
```

---

### `PUT /sessions/{session_id}/context/messages`

Replace all messages (for session restore or context manipulation).

**Maps to:** `context.set_messages(messages)`

---

### `DELETE /sessions/{session_id}/context/messages`

Clear context.

**Maps to:** `context.clear()`

---

## 8. Module Management

Wraps `ModuleLoader` — discovery, loading, and inspection of modules.

### `GET /modules`

Discover available modules.

**Maps to:** `ModuleLoader.discover()` → `list[ModuleInfo]`

**Query params:** `?type=tool` (filter by module type)

**Response:** `200 OK`
```json
{
  "modules": [
    {
      "id": "tool-filesystem",
      "name": "Filesystem Tool",
      "version": "1.2.0",
      "type": "tool",
      "mount_point": "tools",
      "description": "File read/write/edit operations",
      "config_schema": {}
    },
    {
      "id": "provider-anthropic",
      "name": "Anthropic Provider",
      "version": "2.0.1",
      "type": "provider",
      "mount_point": "providers",
      "description": "Claude models via Anthropic API"
    }
  ]
}
```

---

### `GET /modules/{module_id}`

Get detailed module info.

**Maps to:** `ModuleLoader.load()` → inspect module metadata + protocol compliance.

**Response includes** config schema, supported capabilities, protocol interface.

---

### `POST /sessions/{session_id}/modules/mount`

Hot-mount a module into a running session.

**Maps to:** `ModuleLoader.load(module_id)` → `mount_fn(coordinator)` →
`coordinator.mount(mount_point, module)`

**Request body:**
```json
{
  "module_id": "tool-web-fetch",
  "config": {},
  "source": "git+https://github.com/microsoft/amplifier-module-tool-web-fetch@main"
}
```

---

### `POST /sessions/{session_id}/modules/unmount`

Hot-unmount a module from a running session.

**Maps to:** `coordinator.unmount(mount_point, name)`

**Request body:**
```json
{
  "mount_point": "tools",
  "name": "tool-web-fetch"
}
```

---

### `GET /sessions/{session_id}/modules`

List currently mounted modules in a session.

**Maps to:** `coordinator.mount_points` + `coordinator.to_dict()`

---

## 9. Bundle Management

Wraps `BundleRegistry` and `Bundle` — loading, composition, and preparation.

### `GET /bundles`

List registered bundles.

**Maps to:** `BundleRegistry.list_registered()` + `get_state()`

**Response:** `200 OK`
```json
{
  "bundles": [
    {
      "name": "foundation",
      "uri": "git+https://github.com/microsoft/amplifier-foundation@main",
      "version": "2.0.0",
      "loaded_at": "2026-03-02T10:00:00Z",
      "has_updates": false
    }
  ]
}
```

---

### `POST /bundles/register`

Register a bundle name → URI mapping.

**Maps to:** `BundleRegistry.register({name: uri})`

**Request body:**
```json
{
  "name": "my-bundle",
  "uri": "git+https://github.com/myorg/my-bundle@main"
}
```

---

### `DELETE /bundles/{name}`

Unregister a bundle.

**Maps to:** `BundleRegistry.unregister(name)`

---

### `POST /bundles/load`

Load and inspect a bundle (without creating a session).

**Maps to:** `load_bundle(source)` → `Bundle`

**Request body:**
```json
{
  "source": "git+https://github.com/microsoft/amplifier-foundation@main"
}
```

**Response:** `200 OK`
```json
{
  "name": "foundation",
  "version": "2.0.0",
  "description": "...",
  "includes": ["foundation:behaviors/agents"],
  "providers": [{"module": "provider-anthropic"}],
  "tools": [{"module": "tool-filesystem"}, {"module": "tool-bash"}],
  "hooks": [{"module": "hooks-approval"}],
  "agents": {"foundation:explorer": {}, "foundation:zen-architect": {}},
  "context_files": ["bundle-awareness.md", "delegation-instructions.md"]
}
```

---

### `POST /bundles/prepare`

Prepare a bundle for session creation (download modules, install deps).

**Maps to:** `bundle.prepare(install_deps=True)` → `PreparedBundle`

Returns a `prepared_bundle_id` that can be referenced in `POST /sessions`.

---

### `POST /bundles/compose`

Compose multiple bundles together (preview the merge result).

**Maps to:** `Bundle.compose(*others)`

**Request body:**
```json
{
  "bundles": ["foundation", "git+https://github.com/myorg/custom-tools@main"],
  "overrides": {}
}
```

**Response:** Merged mount plan preview.

---

### `POST /bundles/{name}/check-updates`

Check if a bundle has updates available.

**Maps to:** `BundleRegistry.check_update(name)`

---

### `POST /bundles/{name}/update`

Update a bundle to latest.

**Maps to:** `BundleRegistry.update(name)`

---

## 10. Session Fork & History

Wraps `amplifier_foundation.session` — fork, slice, and lineage operations.

### `POST /sessions/{session_id}/fork`

Fork a session at a specific turn.

**Maps to:** `fork_session(session_dir, turn=N)`

**Request body:**
```json
{
  "turn": 5,
  "handle_orphaned_tools": "complete"
}
```

**Response:** `201 Created`
```json
{
  "session_id": "fork-xyz",
  "parent_id": "abc123",
  "forked_from_turn": 5,
  "message_count": 12
}
```

---

### `GET /sessions/{session_id}/fork/preview`

Preview what a fork at a given turn would look like.

**Maps to:** `get_fork_preview(session_dir, turn)`

**Query params:** `?turn=5`

---

### `GET /sessions/{session_id}/turns`

List turn boundaries and summaries.

**Maps to:** `get_turn_boundaries()` + `get_turn_summary()` for each turn.

**Response:** `200 OK`
```json
{
  "turns": [
    {"turn": 1, "user_message_preview": "Explain auth...", "assistant_preview": "The auth module..."},
    {"turn": 2, "user_message_preview": "Show the code...", "assistant_preview": "Here is src/auth.py..."}
  ],
  "total_turns": 2
}
```

---

### `GET /sessions/{session_id}/lineage`

Get the full fork lineage (ancestors + descendants).

**Maps to:** `get_session_lineage(session_dir)`

---

### `GET /sessions/{session_id}/forks`

List all child forks of this session.

**Maps to:** `list_session_forks(session_dir)`

---

## 11. Validation

Wraps validation framework — mount plan, module, and bundle validators.

### `POST /validate/mount-plan`

Validate a mount plan configuration.

**Maps to:** `MountPlanValidator().validate(mount_plan)`

**Request body:** Raw mount plan dict.

**Response:** `200 OK`
```json
{
  "passed": true,
  "errors": [],
  "warnings": ["No hooks configured"]
}
```

---

### `POST /validate/module`

Validate a module for protocol compliance.

**Maps to:** `ProviderValidator` / `ToolValidator` / `HookValidator` /
`OrchestratorValidator` / `ContextValidator` based on module type.

**Request body:**
```json
{
  "module_id": "tool-filesystem",
  "type": "tool",
  "source": "git+https://github.com/microsoft/amplifier-module-tool-filesystem@main",
  "config": {}
}
```

**Response:** `200 OK`
```json
{
  "valid": true,
  "checks": [
    {"check": "importable", "passed": true},
    {"check": "has_mount", "passed": true},
    {"check": "implements_protocol", "passed": true}
  ]
}
```

---

### `POST /validate/bundle`

Validate a bundle.

**Maps to:** `validate_bundle(bundle)`

**Request body:** Bundle source URI or inline bundle definition.

**Response:** `200 OK`
```json
{
  "valid": true,
  "errors": [],
  "warnings": []
}
```

---

## 12. Introspection & Health

### `GET /health`

Health check.

**Response:** `200 OK`
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "uptime_seconds": 3600,
  "active_sessions": 3,
  "rust_engine": true
}
```

---

### `GET /info`

Server info and capabilities.

**Response:** `200 OK`
```json
{
  "version": "0.1.0",
  "amplifier_core_version": "1.0.7",
  "amplifier_foundation_version": "2.0.0",
  "rust_available": true,
  "capabilities": [
    "streaming", "websocket", "approval", "cancellation",
    "hot_mount", "fork", "spawn"
  ],
  "module_types": ["orchestrator", "provider", "tool", "hook", "context", "resolver"],
  "well_known_capabilities": [
    "tools", "streaming", "thinking", "vision", "json_mode",
    "fast", "code_execution", "web_search", "deep_research",
    "local", "audio", "image_generation", "computer_use",
    "embeddings", "long_context", "batch"
  ]
}
```

---

### `GET /sessions/{session_id}/capabilities`

List registered capabilities for a session.

**Maps to:** `coordinator.get_capability()` for all known capability names.

---

### `GET /sessions/{session_id}/hooks`

List registered hooks for a session.

**Maps to:** `hooks.list_handlers()`

**Response:** `200 OK`
```json
{
  "handlers": {
    "tool:pre": ["approval-hook", "logging-hook"],
    "tool:post": ["logging-hook"],
    "session:start": ["session-naming-hook"]
  }
}
```

---

## 13. Configuration

### `GET /config/providers`

List available provider configurations.

**Maps to:** Module discovery filtered to `type=provider` + `ProviderInfo`.

**Response:** `200 OK`
```json
{
  "providers": [
    {
      "id": "provider-anthropic",
      "display_name": "Anthropic",
      "capabilities": ["tools", "streaming", "thinking", "vision"],
      "config_fields": [
        {
          "id": "api_key",
          "display_name": "API Key",
          "field_type": "secret",
          "env_var": "ANTHROPIC_API_KEY",
          "required": true
        }
      ],
      "models": [
        {
          "id": "claude-sonnet-4-20250514",
          "display_name": "Claude Sonnet 4",
          "context_window": 200000,
          "max_output_tokens": 64000,
          "capabilities": ["tools", "streaming", "thinking", "vision"]
        }
      ]
    }
  ]
}
```

---

### `GET /config/providers/{provider_id}/models`

List models for a specific provider.

**Maps to:** `Provider.list_models()` (requires instantiated provider).

---

## Endpoint Summary

| # | Method | Path | Category | Maps To |
|---|--------|------|----------|---------|
| 1 | POST | `/sessions` | Session | `PreparedBundle.create_session()` |
| 2 | GET | `/sessions` | Session | Session store query |
| 3 | GET | `/sessions/{id}` | Session | `SessionStatus` + `coordinator.to_dict()` |
| 4 | POST | `/sessions/{id}/resume` | Session | Transcript restore + `create_session(is_resumed=True)` |
| 5 | DELETE | `/sessions/{id}` | Session | `session.cleanup()` |
| 6 | POST | `/sessions/{id}/execute` | Execution | `session.execute(prompt)` |
| 7 | POST | `/sessions/{id}/execute/stream` | Execution | `session.execute()` + SSE events |
| 8 | GET | `/sessions/{id}/events` | Events | SSE subscription on `HookRegistry` |
| 9 | GET | `/sessions/{id}/events/history` | Events | `events.jsonl` query |
| 10 | POST | `/sessions/{id}/cancel` | Cancel | `CancellationToken.request_graceful/immediate()` |
| 11 | GET | `/sessions/{id}/cancel/status` | Cancel | `CancellationToken.state` |
| 12 | GET | `/sessions/{id}/approvals` | Approval | Approval queue |
| 13 | POST | `/sessions/{id}/approvals/{rid}` | Approval | `ApprovalSystem` resolution |
| 14 | WS | `/sessions/{id}/approvals/ws` | Approval | Bidirectional approval |
| 15 | POST | `/sessions/{id}/spawn` | Agents | `PreparedBundle.spawn()` |
| 16 | POST | `/sessions/{id}/spawn/stream` | Agents | `spawn()` + SSE |
| 17 | POST | `/sessions/{id}/spawn/{cid}/resume` | Agents | Child session resume |
| 18 | GET | `/sessions/{id}/agents` | Agents | `coordinator.config["agents"]` |
| 19 | GET | `/sessions/{id}/context/messages` | Context | `context.get_messages()` |
| 20 | POST | `/sessions/{id}/context/messages` | Context | `context.add_message()` |
| 21 | PUT | `/sessions/{id}/context/messages` | Context | `context.set_messages()` |
| 22 | DELETE | `/sessions/{id}/context/messages` | Context | `context.clear()` |
| 23 | GET | `/modules` | Modules | `ModuleLoader.discover()` |
| 24 | GET | `/modules/{id}` | Modules | Module metadata + protocol check |
| 25 | POST | `/sessions/{id}/modules/mount` | Modules | `coordinator.mount()` |
| 26 | POST | `/sessions/{id}/modules/unmount` | Modules | `coordinator.unmount()` |
| 27 | GET | `/sessions/{id}/modules` | Modules | `coordinator.mount_points` |
| 28 | GET | `/bundles` | Bundles | `BundleRegistry.list_registered()` |
| 29 | POST | `/bundles/register` | Bundles | `BundleRegistry.register()` |
| 30 | DELETE | `/bundles/{name}` | Bundles | `BundleRegistry.unregister()` |
| 31 | POST | `/bundles/load` | Bundles | `load_bundle()` |
| 32 | POST | `/bundles/prepare` | Bundles | `bundle.prepare()` |
| 33 | POST | `/bundles/compose` | Bundles | `Bundle.compose()` |
| 34 | POST | `/bundles/{name}/check-updates` | Bundles | `BundleRegistry.check_update()` |
| 35 | POST | `/bundles/{name}/update` | Bundles | `BundleRegistry.update()` |
| 36 | POST | `/sessions/{id}/fork` | Fork | `fork_session()` |
| 37 | GET | `/sessions/{id}/fork/preview` | Fork | `get_fork_preview()` |
| 38 | GET | `/sessions/{id}/turns` | Fork | `get_turn_boundaries()` + summaries |
| 39 | GET | `/sessions/{id}/lineage` | Fork | `get_session_lineage()` |
| 40 | GET | `/sessions/{id}/forks` | Fork | `list_session_forks()` |
| 41 | POST | `/validate/mount-plan` | Validation | `MountPlanValidator` |
| 42 | POST | `/validate/module` | Validation | Type-specific validators |
| 43 | POST | `/validate/bundle` | Validation | `validate_bundle()` |
| 44 | GET | `/health` | Introspection | Internal state |
| 45 | GET | `/info` | Introspection | Version + capability enumeration |
| 46 | GET | `/sessions/{id}/capabilities` | Introspection | `coordinator.get_capability()` |
| 47 | GET | `/sessions/{id}/hooks` | Introspection | `hooks.list_handlers()` |
| 48 | GET | `/config/providers` | Config | Provider discovery + `ProviderInfo` |
| 49 | GET | `/config/providers/{id}/models` | Config | `provider.list_models()` |
| 50 | POST | `/sessions/{id}/reload/bundle` | Hot-Reload | `BundleRegistry.update()` → remount |
| 51 | POST | `/sessions/{id}/reload/module` | Hot-Reload | `coordinator.unmount()` → re-load → remount |
| 52 | POST | `/reload/bundles` | Hot-Reload | `BundleRegistry.update()` (all) |
| 53 | GET | `/reload/status` | Hot-Reload | `BundleRegistry.check_update()` |

**Total: 53 endpoints** (50 HTTP + 2 SSE subscriptions + 1 WebSocket)

---

## 14. Hot-Reload (Dev)

Explicit reload endpoints for development workflows. Updates propagate to
running sessions on request — never automatically.

### `POST /sessions/{session_id}/reload/bundle`

Reload the session's bundle from source (re-fetch, re-compose, re-prepare).
Modules are unmounted and remounted with the updated bundle configuration.

**Maps to:** `BundleRegistry.update()` → `bundle.prepare()` → unmount all →
remount from new `PreparedBundle`.

**Request body:**
```json
{
  "force": false
}
```

`force: true` skips the update check and always re-fetches from source.

**Response:** `200 OK`
```json
{
  "reloaded": true,
  "bundle": "foundation",
  "previous_version": "2.0.0",
  "new_version": "2.0.1",
  "modules_remounted": ["tool-filesystem", "provider-anthropic"],
  "warnings": []
}
```

---

### `POST /sessions/{session_id}/reload/module`

Reload a single module in a running session (unmount + re-load + remount).

**Maps to:** `coordinator.unmount()` → `ModuleLoader.load()` → `mount_fn(coordinator)`

**Request body:**
```json
{
  "module_id": "tool-filesystem",
  "source": "file:///home/user/repos/amplifier-module-tool-filesystem",
  "config": {}
}
```

`source` is optional — omit to re-load from the existing source. Provide a
local `file://` path to test a dev checkout.

**Response:** `200 OK`
```json
{
  "reloaded": true,
  "module_id": "tool-filesystem",
  "mount_point": "tools",
  "source": "file:///home/user/repos/amplifier-module-tool-filesystem"
}
```

---

### `POST /reload/bundles`

Reload all registered bundles (daemon-wide, outside any session).

**Maps to:** `BundleRegistry.update()` for all registered bundles.

**Response:** `200 OK`
```json
{
  "reloaded": ["foundation", "my-bundle"],
  "unchanged": [],
  "errors": []
}
```

---

### `GET /reload/status`

Check what would change if bundles/modules were reloaded (dry-run).

**Maps to:** `BundleRegistry.check_update()` for all registered bundles.

**Response:** `200 OK`
```json
{
  "bundles": [
    {
      "name": "foundation",
      "current_version": "2.0.0",
      "available_version": "2.0.1",
      "has_update": true
    }
  ]
}

---

## Relationship to Core API Surface

The following amplifier-core capabilities are **not directly exposed** as
endpoints but are used internally by the daemon:

| Capability | Internal Use |
|------------|-------------|
| `RetryConfig` / `retry_with_backoff` | Used inside provider call paths |
| `classify_error_message` | Used for error categorization in responses |
| `truncate_values` / `redact_secrets` | Used for event sanitization before streaming |
| `ModuleLoader.initialize` | Used during session creation |
| Error hierarchy (`LLMError` tree) | Mapped to HTTP error responses |
| `HookResult` action routing | Drives approval, injection, and modification flows |
| `ChatRequest` / `ChatResponse` | Internal LLM communication, not exposed directly |
| Contribution system | Pull-based gather pattern (`register_contributor` / `collect_contributions`). See appendix. |
| Testing utilities | Not exposed (dev-only) |

---

## Appendix: Contribution System (Not Exposed)

The `ModuleCoordinator` has a **pull-based gather pattern** called the
contribution system: `register_contributor(channel, name, callback)` and
`collect_contributions(channel)`.

**How it works:** Modules register lazy callbacks on named "channels" at mount
time. Later, a consumer calls `collect_contributions("channel_name")` to invoke
all registered callbacks and collect their return values into a list. Errors are
silently skipped.

**Relationship to the event/hook system:**

| | Hook System | Contribution System |
|--|-------------|---------------------|
| Direction | Push (emit triggers handlers) | Pull (consumer calls collect) |
| Timing | Event-driven, real-time | On-demand, at consumer's discretion |
| Control flow | Can short-circuit (deny/modify) | Cannot; errors skipped |
| Purpose | Lifecycle interception & policy | Data aggregation & discovery |

**Three well-known channels are defined** in the spec (`CONTRIBUTION_CHANNELS.md`):
`observability.events`, `capabilities.catalog`, and `session.metadata`. However,
**no production code currently uses them** — the only callers are tests. The
existing `tool-delegate` module uses the older `register_capability()` approach
for the same purpose.

**Decision:** Not exposed as an endpoint. It is an internal kernel mechanism
with no production callers. If it gains real usage, it could surface as
`GET /sessions/{id}/contributions/{channel}` in a future version.

---

## Next Steps

- [ ] Define error response catalog (map `LLMError` hierarchy → HTTP status codes)
- [ ] Design WebSocket protocol for interactive sessions (beyond approvals)
- [ ] Prototype core session lifecycle endpoints (sessions CRUD + execute)
- [ ] Design filesystem persistence layout for daemon-managed sessions
- [ ] Define SSE event envelope format (event naming, data schema versioning)
