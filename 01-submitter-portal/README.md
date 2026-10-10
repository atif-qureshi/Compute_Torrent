# 01 — Requestor Web Portal (WP-1 to WP-5)

## Purpose
The **Leecher/Requestor** web app: submit a task, watch it run live across seeders, and get the final merged result. Secondary priority behind the seeder-side flow: build it after the seeder demo works end to end (WP-5).

## Requirements
| ID | Requirement | How we meet it |
|---|---|---|
| WP-1 | Task form: upload dataset/model, pick task type (Preprocessing, Inference, Training, LoRA) | Form with file upload, task kind selector, privacy level, model version; **MVP runs Inference only**, other kinds are shown as "coming soon" or accepted but flagged |
| WP-2 | Live dashboard: swarm status, number of active seeders on the task, per-chunk progress, via Socket.io | Task detail page subscribed to the server feed |
| WP-3 | Result view/download once reassembly signals completion | Results tab with ordered outputs and download |
| WP-4 | Basic credit/history view | History list with outcomes and a credits balance page |
| WP-5 | Secondary priority | Built in phase after the seeder demo (docs/BUILD-ORDER.md) |

The progress timeline mirrors the flow: Submitted -> Analysing difficulty -> Sliced into N chunks -> Assigned to M seeders -> Downloading -> Running -> Verifying -> Reassembling -> Final result ready.

## Screens (MVP)
1. Login/Register (simple)
2. New task (upload, kind, privacy level, estimate of difficulty and chunks)
3. My tasks (list with status chips)
4. Task detail: live dashboard, chunk table, verification summary, results, timing metrics
5. Network overview: seeders online, tiers
6. Credits and history

## Inputs / Outputs
| In | Out |
|---|---|
| user files and options | `POST` task to the coordination server |
| Socket.io events | live UI updates |
| result endpoint | rendered and downloadable output |

## Dependencies
- Needs: 02 (REST + Socket.io), 09 (credits, optional).
- Tech: Next.js, React, TypeScript, Tailwind, Socket.io client.

## Rules
1. Size and count limits enforced client side and server side.
2. A requestor sees only their own tasks.
3. Show a clear "what verification happened" badge so the research value is visible in the demo.

## Build steps
1. Static layout with mock data.
2. Task form wired to the API.
3. Socket.io live updates.
4. Result download and verification tab.
5. History and credits.
6. Demo polish (empty states, errors, loading).

## Acceptance checks
- Submit 20 prompts, see chunks progress live without refreshing.
- Failed chunk shows reason and retry count.
- Downloaded results keep the original prompt order.
- Usable at phone width for demos.

## Out of scope
Payments, organizations and teams, admin panel (use database tools for the MVP).