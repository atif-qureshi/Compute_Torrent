# ComputeTorrent — Partner 2 Requirements Document
### Scope: Provider (Seeder) Desktop Application — MVP
Version: v1.0 | Based on: ComputeTorrent Working & Architecture v3

---

## 1. Ownership & Scope Statement

This document covers **only Partner 2's ownership area** of the ComputeTorrent MVP:

| # | Component |
|---|-----------|
| 1 | Provider (Seeder) Desktop Application — installable app |
| 2 | Hardware Profiling Module |
| 3 | Docker Sandbox Runtime (execution isolation) |
| 4 | WebTorrent File Sync Client (data distribution layer) |
| 5 | Web Portal Frontend (Requestor-facing dashboard UI) |
| 6 | (Secondary support) Reassembly Module integration on the frontend side |

Anything belonging to the Coordination/Tracker Server, Task Slicing Engine, or Verification logic (Partner 1's ownership) is treated here strictly as an **external interface / black box** — i.e., we only define what messages go in and out, not how the other side works internally.

The end deliverable for the desktop portion is a **standalone installable desktop application** that a user downloads, installs, and runs on their own machine to join the network as a Seeder (compute provider).

---

## 2. MVP Goal

Give the project enough working clarity to demonstrate, end-to-end, that:
> "A user can install the Seeder app on their PC, the app detects their hardware, connects to the network, receives a task, runs it safely inside an isolated container, and returns a result — without ever putting the user's real files or system at risk."

Everything below is scoped to make **that single flow real**, not the whole platform.

---

## 3. High-Level Component Architecture (Partner 2 side only)

```
┌─────────────────────────────────────────────────────────┐
│                PROVIDER DESKTOP APPLICATION               │
│                                                             │
│  ┌───────────────┐   ┌──────────────────┐                 │
│  │ Hardware       │   │ Networking Client │──► (to Tracker/│
│  │ Profiling      │   │ (WebSocket +      │    Relay –     │
│  │ Module         │   │  optional WebRTC) │    external)   │
│  └───────┬────────┘   └────────┬──────────┘                │
│          │                     │                            │
│          ▼                     ▼                            │
│  ┌───────────────────────────────────────────┐             │
│  │        Task Receiver / Dispatcher UI        │             │
│  └───────┬─────────────────────┬──────────────┘             │
│          │                     │                            │
│          ▼                     ▼                            │
│  ┌───────────────┐   ┌──────────────────────┐              │
│  │ WebTorrent     │   │ Docker Sandbox        │              │
│  │ File Sync      │──►│ Runtime (execution)   │              │
│  │ Client         │   │                       │              │
│  └───────────────┘   └──────────┬────────────┘              │
│                                  │                            │
│                                  ▼                            │
│                       Result → returned via Networking Client │
└─────────────────────────────────────────────────────────┘

              (separately, on the requestor side)
┌─────────────────────────────────────────────────────────┐
│           WEB PORTAL FRONTEND (Requestor dashboard)        │
│  Task submission form → Live status view (Socket.io) →     │
│  Result display / download                                  │
└─────────────────────────────────────────────────────────┘
```

---

## 4. Functional Requirements

### 4.1 Hardware Profiling Module

| ID | Requirement |
|----|-------------|
| HP-1 | On app launch, automatically detect GPU model, VRAM size, CUDA availability, CPU core count, and total RAM. |
| HP-2 | Build a `Node Profile` JSON object in this exact shape: `{ GPU, VRAM, CUDA, RAM }`. |
| HP-3 | Assign the node a capability tier locally, before sending to the network: **Tier-1** if VRAM ≥ 8GB (eligible for LLM Inference / LoRA), **Tier-2** otherwise (eligible for Preprocessing / light training). |
| HP-4 | Re-check hardware profile if the app is restarted, or on a manual "Refresh" action from the user. |
| HP-5 | Display the detected profile and tier to the user in plain language inside the app UI (e.g., "Your PC: RTX 3060, 12GB VRAM → Tier 1 — eligible for AI Inference & LoRA tasks"). |

**Tech:** `pynvml` (NVIDIA GPU stats), `psutil` (CPU/RAM stats), Python.

### 4.2 Networking Client

| ID | Requirement |
|----|-------------|
| NC-1 | On launch (after hardware profiling), open a WebSocket connection to the network's registration endpoint and register the node with its profile + tier. |
| NC-2 | Maintain a persistent "online/idle" heartbeat so the network knows the node is available. |
| NC-3 | Listen for incoming task-assignment messages (chunk ID, model script reference, dataset reference, expected chunk count). |
| NC-4 | Attempt a STUN handshake for a direct WebRTC upgrade when possible; if it fails, silently continue routing through the relay (no error shown to the user — this must be invisible/automatic). |
| NC-5 | Send task status updates (queued → downloading → running → completed/failed) back over the same connection so they can be reflected on the requestor's dashboard in real time. |
| NC-6 | Handle disconnect/reconnect gracefully — if connection drops mid-task, attempt to resume; if resume fails, mark the task as failed locally and re-register. |

**Interface note (black box, not our scope to design internally):** we only need to agree on the JSON message schema exchanged with the Tracker/Relay — e.g. `register`, `task_assign`, `status_update`, `result_submit`.

### 4.3 Docker Sandbox Runtime

| ID | Requirement |
|----|-------------|
| DS-1 | For every incoming task, spin up a **fresh, disposable Docker container** — never reuse a container across tasks. |
| DS-2 | Container must have hard resource limits: capped CPU, capped memory, GPU access scoped via NVIDIA Container Toolkit only for the assigned task. |
| DS-3 | Container must have **no network access** except: (a) pulling its assigned data chunk, (b) returning its result. No access to the host filesystem outside its own mounted working directory. |
| DS-4 | On task completion (success or failure), the container must be **destroyed immediately** — no leftover state, no leftover files. |
| DS-5 | If a container crashes, times out, or exceeds resource limits, report `status: failed` back through the Networking Client rather than retrying silently. |
| DS-6 | Log container lifecycle events (created, started, completed, destroyed) locally for user-facing debugging/transparency, but do not expose raw logs to the network. |

**Tech:** Docker Engine (local), NVIDIA Container Toolkit for GPU passthrough.

### 4.4 WebTorrent File Sync Client

| ID | Requirement |
|----|-------------|
| WT-1 | On receiving a task assignment, join the **per-task private WebTorrent swarm** specified in the assignment message (swarm scoped only to that task's requestor + assigned seeders). |
| WT-2 | Download the dataset/model chunk(s) needed for the assigned task, verifying integrity via SHA-1 piece hashing (built into WebTorrent). |
| WT-3 | Support resume-on-failure if the download is interrupted mid-transfer. |
| WT-4 | Once the task is complete and result is submitted, leave the swarm — do not continue seeding that task's data indefinitely (per-task swarms are torn down after completion, per architecture doc). |
| WT-5 | Pass the downloaded chunk file path into the Docker Sandbox Runtime as a mounted volume, never as a direct host-filesystem path outside the container's isolated workspace. |

**Tech:** WebTorrent (Node.js implementation), integrated with the desktop app's backend process.

### 4.5 Provider Desktop Application (shell/installer requirements)

| ID | Requirement |
|----|-------------|
| APP-1 | Must be a **single installable package** for at least one OS (Windows first, since target users are consumer PC owners) — e.g. an `.exe`/installer produced via PyInstaller or an Electron-based packager. |
| APP-2 | On first run, show a simple onboarding screen: detect hardware → show tier → "Start Seeding" button. |
| APP-3 | Main dashboard screen (while running) must show: connection status (online/offline), current task (if any) with a progress indicator, total tasks completed, and credits earned so far. |
| APP-4 | Provide a "Pause Seeding" / "Stop" control so the user can opt out of accepting new tasks at any time without closing the app. |
| APP-5 | App must run in the background/minimized to system tray without needing to stay in focus. |
| APP-6 | No task should ever run without the sandboxing in 4.3 being active — this is a hard MVP invariant, not optional. |

**Tech:** Python + PyQt / CustomTkinter for UI (per architecture doc's chosen stack).

### 4.6 Web Portal Frontend (Requestor-facing, Partner 2 ownership)

| ID | Requirement |
|----|-------------|
| WP-1 | Task submission form: let a requestor upload a dataset/model and pick a task type (Preprocessing / Inference / Training / LoRA). |
| WP-2 | Live dashboard view: show swarm status, number of active seeders on the task, and per-chunk progress, updated in real time via Socket.io. |
| WP-3 | Result view: once the Reassembly Module (Partner 1 side) signals completion, display/download the final merged output. |
| WP-4 | Basic credit/history view: list of past tasks submitted and their outcomes. |
| WP-5 | This is a **secondary priority** relative to the Desktop App (4.1–4.5) for MVP — build after the seeder-side flow is functional end-to-end. |

**Tech:** Next.js / React + Tailwind (per architecture doc).

---

## 5. Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| NFR-1 | **Safety first:** under no circumstance should a task be able to read/write/delete anything on the host machine outside its Docker container's mounted workspace. |
| NFR-2 | The app should be usable by a non-technical user — no manual Docker or dependency installation should be required; the installer must bundle or auto-provision what's needed. |
| NFR-3 | The app should degrade gracefully — if Docker isn't available on first run, show a clear message and installation guidance rather than crashing. |
| NFR-4 | Resource usage when idle (no task running) must be minimal — this app is meant to run passively on someone's personal PC. |
| NFR-5 | All network communication should assume the Tracker/Relay (Partner 1's system) as a fixed external contract — do not hardcode assumptions about its internal implementation. |

---

## 6. End-to-End Flow (Seeder / Partner-2 Perspective)

Concrete scenario used for clarity (matches the reference walkthrough): **Sara** is a Seeder with an RTX 3060; **Ali** is a Requestor who submits 500 prompts for LLM inference.

1. **App launch** → Hardware Profiling Module scans Sara's PC → builds Node Profile `{ GPU: "RTX 3060", VRAM: 12GB, CUDA: true, RAM: 16GB }` → tiered as **Tier-1**.
2. **Networking Client** opens WebSocket connection to the Tracker, registers Sara's node as online with her profile.
3. Tracker (external/Partner 1) matches Sara's node against an incoming job and assigns her **2 chunks** (e.g. chunk #7 and #14 — 20 prompts each).
4. **WebTorrent File Sync Client** joins the per-task private swarm and downloads the model + prompt chunks assigned to Sara.
5. **Docker Sandbox Runtime** spins up a fresh disposable container, loads the model, runs inference on the 40 assigned prompts — fully isolated from Sara's personal files.
6. **Status Updates** are sent continuously through the Networking Client so Ali's Web Portal dashboard shows live progress.
7. On completion, results (text responses) are returned via the Networking Client to the Tracker/Relay.
8. The Docker container is immediately destroyed — no trace left on Sara's machine.
9. Sara's desktop app updates her local stats: task completed, credit balance incremented; app returns to idle/available state for the next task.

---

## 7. Data Contracts (for building against Partner 1's interface)

```json
// Node registration (sent on connect)
{
  "type": "register",
  "profile": { "GPU": "RTX 3060", "VRAM": 12, "CUDA": true, "RAM": 16 },
  "tier": 1
}

// Incoming task assignment (received)
{
  "type": "task_assign",
  "task_id": "abc123",
  "chunk_ids": [7, 14],
  "swarm_id": "swarm_abc123",
  "model_ref": "phi-3-gguf",
  "task_kind": "inference"
}

// Status update (sent)
{
  "type": "status_update",
  "task_id": "abc123",
  "state": "running" // queued | downloading | running | completed | failed
}

// Result submission (sent)
{
  "type": "result_submit",
  "task_id": "abc123",
  "chunk_id": 7,
  "output_ref": "result_chunk7.json"
}
```

*(Exact field names to be finalized jointly with Partner 1 — this is the working draft Partner 2 will build against.)*

---

## 8. MVP Build Order (Suggested)

1. Hardware Profiling Module (standalone, testable without network) — **HP-1 to HP-5**
2. Docker Sandbox Runtime (standalone — run a dummy script in an isolated container) — **DS-1 to DS-6**
3. Networking Client (connect + send/receive fake messages against a mock server) — **NC-1 to NC-6**
4. WebTorrent File Sync Client (join a test swarm, download a test file) — **WT-1 to WT-5**
5. Wire steps 1–4 together into the Desktop App shell + UI — **APP-1 to APP-6**
6. Package as installable executable
7. Web Portal Frontend (after desktop-side flow works end-to-end) — **WP-1 to WP-5**

---

## 9. Acceptance Criteria for MVP Demo

- [ ] User can download and install the app with zero manual setup steps beyond running the installer.
- [ ] App correctly detects real hardware and shows the right tier.
- [ ] App connects to the network and shows "Online" status.
- [ ] A test task (even a dummy/simulated one) can be received, run inside an isolated Docker container, and a result returned.
- [ ] After the task, no files from the task remain on the host machine.
- [ ] App UI shows live status while idle and while processing.
- [ ] (Stretch) Web Portal shows the task's live progress from the requestor side.

---

*This document intentionally excludes any internal design of the Coordination Server, Task Slicing Engine, or Verification Module — those belong to Partner 1's scope and are referenced here only as external message contracts.*
