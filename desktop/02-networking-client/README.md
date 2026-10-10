# 08.02 — Networking Client (NC-1 to NC-6)

## Purpose
The seeder's control-plane link to the Coordination Server (Tracker/Relay): register, stay online, receive assignments, report progress, return results.

## Requirements
| ID | Requirement | How we meet it |
|---|---|---|
| NC-1 | After profiling, open a WebSocket to the registration endpoint and register profile plus tier | `register` message (docs/CONTRACTS.md) |
| NC-2 | Keep an online/idle heartbeat | `heartbeat` every N seconds with state idle, busy or paused |
| NC-3 | Listen for task assignments (chunk ids, model script reference, dataset reference, expected chunk count) | `task_assign` handler passes work to the dispatcher |
| NC-4 | Try STUN for a direct WebRTC upgrade; on failure silently use the relay, no error shown | Connectivity attempt in the background; user never sees a failure |
| NC-5 | Send status updates queued -> downloading -> running -> completed/failed in real time | `status_update` on every state change |
| NC-6 | Handle disconnect and reconnect; resume if possible, else mark failed locally and re-register | Reconnect loop with backoff, task resume check |

## Messages used
Sends: `register`, `heartbeat`, `status_update`, `result_submit`. Receives: `task_assign`, `verdict_notice`, `cancel`. Field details: docs/CONTRACTS.md section 3.

## Behavior details
1. **Connection states:** DISCONNECTED -> CONNECTING -> REGISTERED -> (IDLE or BUSY or PAUSED). Shown in the app as online/offline.
2. **Reconnect:** exponential backoff with a cap; on reconnect re-send `register` so the server restores the seeder.
3. **Mid-task disconnect:** keep the task running if the sandbox is healthy; on reconnect resend pending `status_update` and `result_submit`. If the task cannot be resumed, set it failed locally and report on reconnect.
4. **Pause (APP-4):** keep heartbeat but report state paused so the server sends nothing new.
5. **Result return:** `result_submit` per finished chunk, then `status_update: completed`.
6. **Idempotence:** every message carries ids so the server can ignore duplicates.

## Dependencies
- Needs: 01 profiling (profile), the coordination server or its mock (module 02).
- Feeds: 05-desktop-app-shell (task dispatcher), 03/04 (tasks to run).
- Tech: Python WebSocket client, STUN/WebRTC library (optional for first demo).

## Build steps
1. Against the **mock server**: connect, register, heartbeat.
2. Receive a fake `task_assign`, print it.
3. Send each status state and a fake `result_submit`.
4. Reconnect tests (kill and restart the mock).
5. STUN/WebRTC upgrade attempt with silent fallback.

## Acceptance checks
- Node shows "Online" within seconds of launch and stays online for hours.
- Killing the server and bringing it back makes the node return to "Online" without user action.
- A WebRTC failure produces no visible error.
- Status changes arrive at the server in the right order.

## Out of scope
Designing the server internals (module 02); only the message contract is fixed here (NFR-5).
