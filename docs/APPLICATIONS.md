# Applications Map (what you actually build and run)

One developer builds all of this. Decision taken for the MVP: the server-side logic (slicing, allocation, verification, reassembly, credits) lives in **one Coordination Server**, not on a separate requestor node. A requestor-side desktop app is future work.

## 1. The applications

| # | Application | Who uses it | Where it runs | Stack | Docs |
|---|---|---|---|---|---|
| A | **Seeder Desktop App** | donors | donor's Windows PC | Python, CustomTkinter, bundled Node.js WebTorrent helper, Docker | `08-provider-node/` |
| B | **Requestor Web Portal** | requestors | browser | Next.js, React, TypeScript, Tailwind, Socket.io client | `01-submitter-portal/` |
| C | **Coordination Server** (Tracker/Relay + logic) | nobody directly | your PC or a server; ngrok for off-LAN demos | FastAPI, WebSocket, python-socketio, SQLAlchemy | `02-orchestrator-api/` plus 04, 05, 06, 09, 10 |
| D | **Swarm service** | used by C | next to the server | Node.js, WebTorrent | `07-network-layer/` |
| E | **PostgreSQL 18** | used by C | Docker | `docker/` stack | `03-database/` |
| F | **Mock server** (dev tool only) | you, during early development | local | tiny fake of C speaking the four base messages | `docs/BUILD-ORDER.md` phase 0 |
| G | **Benchmark harness** (research tool) | you | local | Python scripts | `11-evaluation-benchmark/` |

## 2. How they connect

```
 Requestor browser (B) --REST + Socket.io--> Coordination Server (C) --SQL--> PostgreSQL (E)
                                                   |   \
                                      WebSocket    |    \ create / tear down swarms
                                                   |     v
 Seeder Desktop App (A) <==========================+   Swarm service (D)
        |    ^                                              |
        |    +----------- per-task private WebTorrent swarm +
        v
   Docker sandbox on the donor PC
```

## 3. What each app owns

| App | Owns | Does not do |
|---|---|---|
| A Seeder app | hardware profiling, networking client, sandbox, swarm download, local UI and stats | slicing, verification, credits calculation |
| B Portal | task form, live view, results, history | any computation, any file processing |
| C Server | registry, task lifecycle, slicing, allocation, verification, reassembly, credits, relay | running model inference |
| D Swarm service | per-task swarms and seeding of task data | deciding who gets what |

## 4. Machines for the demo

| Machine | Runs |
|---|---|
| Your main PC | C, D, E (Docker), B (dev server), plus one seeder instance |
| 1 or 2 more PCs (or VMs) | A (Seeder app) with Docker |
| Optional | ngrok tunnel so a seeder outside the LAN can reach C |

## 5. Packaging

| App | Delivered as |
|---|---|
| A | single Windows `.exe` or installer (PyInstaller) with the Node helper bundled |
| B | web build, served by the Next.js server for the demo |
| C, D, E | Docker compose stack (`docker/`); C and D images once code exists |

## 6. Future work (not in MVP)

Requestor-side desktop app joining the swarm directly, serverless coordination (libp2p DHT and Circuit Relay from the proposal), macOS/Linux seeder apps, multiple coordination servers.
