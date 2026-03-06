# amplifierd Feature Consideration — Deferred Items

Features identified in the distro `session_backend.py` gap analysis that are
not being implemented in the current sprint. Each item includes rationale
for deferral and notes for future implementation.

## 2. Tombstoning Ended Sessions

**Distro behavior:** `_ended_sessions: set[str]` tracks sessions that were
intentionally ended. `_reconnect()` checks this set and raises `ValueError`
to prevent resurrection of ended sessions.

**Why deferred:** amplifierd's `SessionManager.destroy()` already removes
the handle from `_sessions`. Without the per-session worker queue pattern
(item 3), there is no auto-reconnect path that could accidentally resurrect
an ended session. Once worker queues or auto-reconnect is added, tombstoning
should be revisited.

**Future implementation:** Add `_ended_sessions: set[str]` to SessionManager.
Check in `resume()`. Populate in `destroy()`.

---

## 3. Per-Session Worker Queue

**Distro behavior:** Each session has an `asyncio.Queue` and a worker task
(`_session_worker`) that drains it, running `handle.run()` calls sequentially.
This allows concurrent `send_message()` calls to queue rather than reject.

**Why deferred:** amplifierd's `SessionHandle.execute()` uses a simple status
check (`if self._status == SessionStatus.EXECUTING: raise RuntimeError`).
This is sufficient for the HTTP API where the client controls sequencing.
Worker queues add complexity that is only needed for multi-client scenarios
(e.g., two WebSocket clients sending messages to the same session).

**Future implementation:** Add `asyncio.Queue` per session in SessionManager.
Create `_session_worker()` coroutine. Route `execute()` through the queue.
Add sentinel-based shutdown in `destroy()`.

---

## 4. send_message() API — Request/Response Pattern

**Distro behavior:** `send_message()` takes a message string, routes through
the worker queue, and returns the response text (blocking until complete).
Separate from `execute()` which is fire-and-forget streaming.

**Why deferred:** amplifierd already has `POST /sessions/{id}/execute` (sync)
and `POST /sessions/{id}/execute/stream` (fire-and-forget). The distro's
`send_message()` is essentially `execute()` routed through the worker queue.
Once worker queues are added (item 3), a `send_message` variant becomes
trivial.

**Future implementation:** Add `POST /sessions/{id}/message` route that queues
the prompt through the worker and returns the response.

---

## 5. Multi-Client Event Fanout + User Message Broadcast

**Distro behavior:** `_QueueHolder` supports multiple event queues per session.
`broadcast_user_message()` pushes user messages to all connected clients.
`dequeue_client()` removes disconnected clients.

**Why deferred:** amplifierd's `EventBus` already supports multiple SSE
subscribers per session via independent `asyncio.Queue` instances. The
`subscribe(session_id=...)` method handles the fanout. User message broadcast
(`broadcast_user_message`) is a convenience that could be added as an EventBus
helper. Not needed until multi-client chat UI is implemented.

**Future implementation:** Add `publish_user_message(session_id, content, images)`
convenience method to EventBus. Consider whether the chat plugin SPA needs it.

---

## 7. Approval System Integration into Event Stream

**Distro behavior:** `ApprovalSystem` is wired to the event queue so approval
requests appear as `("approval_request", {...})` events in the SSE stream.

**Why deferred:** amplifierd already has `POST /sessions/{id}/approvals/{rid}`
routes and the approval state is managed through `SessionHandle._approval_cache`.
Unifying approval requests into the event stream is an enhancement that improves
real-time UX but doesn't block core functionality.

**Future implementation:** Port `ApprovalSystem` from `protocol_adapters.py`.
Wire it in `SessionHandle._wire_events()` or the new `_wire_display()` path.
Emit `approval_request` events to EventBus.

---

## 11. Bundle Overlay Loading

**Distro behavior:** `_load_bundle()` checks for a local overlay bundle
(created by the install wizard) and loads it by path. The overlay includes
the maintained distro bundle and any user-selected features.

**Why deferred:** This is a distro-specific install wizard feature.
amplifierd uses `BundleRegistry` with named bundles and URI-based loading.
The overlay concept doesn't map to amplifierd's architecture.

**Future implementation:** If amplifierd needs bundle composition,
implement via `BundleRegistry` features (e.g., bundle stacking or merge)
rather than filesystem overlay patterns.
