# 08.05 — Desktop App Shell and Installer (APP-1 to APP-6, NFR-2 to NFR-4)

## Purpose
The window, tray icon, onboarding and packaging that tie profiling, networking, sync and sandbox into one app a non-technical person can install and use.

## Requirements
| ID | Requirement | How we meet it |
|---|---|---|
| APP-1 | One installable package for at least Windows | PyInstaller single `.exe` or installer; Windows first |
| APP-2 | First run: detect hardware -> show tier -> "Start Seeding" | Onboarding screen |
| APP-3 | Dashboard: connection status, current task with progress, tasks completed, credits earned | Main screen fed by `status_update` and `verdict_notice` |
| APP-4 | "Pause Seeding" / "Stop" without closing the app | Sets paused state, heartbeat reports it, no new tasks accepted |
| APP-5 | Run in background, minimized to system tray | Tray icon with status and quick pause/resume |
| APP-6 | No task runs without the sandbox | Dispatcher refuses to start a task if the sandbox is not ready (hard invariant) |

## Screens
1. **Onboarding:** profile result in plain language, tier, Docker check, "Start Seeding".
2. **Dashboard:** Online/Offline, idle or current task with progress bar, tasks completed, credits earned, pause/resume.
3. **Task detail (local):** state steps (queued, downloading, running, completed), local container log (DS-6).
4. **Settings:** resource caps (CPU/RAM/GPU share), schedule or idle-only, bandwidth limit, startup behavior.
5. **Problems screen:** Docker missing, driver missing, server unreachable, with plain instructions (NFR-3).

## Task dispatcher (inside the shell)
Receives `task_assign` -> asks 04 to download -> hands chunk to 03 -> sends `result_submit` through 02 -> triggers cleanup -> updates local stats. One task at a time for MVP. Refuses new tasks while paused.

## Local data
Small local store for settings, task count, credit balance cache, and event log. Contains no task content.

## Installer and first-run checks (NFR-2, NFR-3)
Windows cannot silently install everything. Realistic plan:
1. Installer places the app, the Node helper and the pinned sandbox image reference.
2. First run checks: Docker Desktop installed and running, WSL2/virtualization available, NVIDIA driver and Container Toolkit for GPU.
3. If something is missing: clear message and a link or short steps; the app stays usable (profile, settings) but accepts no tasks.
4. Target for the demo: no manual steps beyond running the installer **when Docker is already installed**; otherwise guided steps.

## Resource behavior (NFR-4)
Idle: only a heartbeat and a small UI. No polling loops that burn CPU. GPU untouched until a task starts.

## Dependencies
- Needs: 01, 02, 03, 04 (all other seeder sub-modules).
- Tech: Python, CustomTkinter or PyQt, system tray library, PyInstaller; Docker Desktop on the host.

## Build steps
1. Window with the profile display (reuse 01).
2. Dashboard with fake status data.
3. Wire the dispatcher with mock server and dummy task.
4. Tray, pause/resume, settings.
5. Problems screens for Docker and drivers.
6. Package, then test install on a clean PC.

## Acceptance checks
- Fresh Windows PC with Docker: install, launch, onboarding, online.
- Pause stops new tasks; resume continues; closing the window keeps it in the tray.
- With Docker stopped, the app explains the problem and does not crash or accept tasks.
- Idle CPU usage stays near zero.

## Out of scope
Auto-update, multi-language UI, silent installation of Docker Desktop.
