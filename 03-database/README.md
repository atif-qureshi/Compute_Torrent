# 03 — Database (PostgreSQL 18)

## Purpose
Single source of truth for manifests, worker profiles, tasks, results, verdicts, credits, and versions.

## Tables (logical groups)
| Group | Tables | Notes |
|---|---|---|
| Identity | requesters, workers | worker has public key, hardware profile, trust score |
| Work | tasks, chunks, assignments, results | chunk kind REAL or CANARY |
| Verification | verdicts, worker_flags | verdict per layer per result |
| Incentives | credit_ledger, priority_state | append-only ledger |
| Versions | model_versions, adapter_versions, benchmark_versions | hashes and infohashes |
| Network | manifests, torrents | infohash per task payload |
| Metrics | chunk_metrics, task_metrics, node_samples | P_i, D_i, V_i, recovery_time |
| Ops | events_log, heartbeats (short retention) | audit and debugging |

## Key relationships
- task 1..N chunks; chunk 1..R assignments (R = replication); assignment 1..1 result; result 1..3 verdicts.
- worker 1..N assignments; worker 1..N credit entries.
- task -> model_version -> adapter_version (optional).

## Rules
1. Credit ledger is append-only; balance is a sum, never an edited number.
2. Hashes are stored as text with algorithm name.
3. Soft-delete nothing in verification tables (needed for thesis evidence).
4. Heartbeats are pruned after a short window; aggregated into node_samples.
5. All timestamps UTC.

## Migrations (Alembic)
1. Baseline: identity + work tables.
2. Add verification and incentives.
3. Add versioning and network tables.
4. Add metrics tables and indexes.
Each migration reversible; test upgrade and downgrade on empty and seeded DB.

## Indexes worth planning
Chunk status per task, assignments by worker and deadline, results by assignment, ledger by worker, heartbeats by worker and time.

## Dependencies
- Needs: nothing. Used by: 02, 05, 06, 09, 10, 11.
- Tech: PostgreSQL 18, SQLAlchemy (async), asyncpg, Alembic.

## Build steps
1. Entity diagram review against docs/CONTRACTS.md.
2. Baseline migration and seed script (fake workers/tasks for dev).
3. Add remaining groups as modules arrive.
4. Backup/restore script for demo day.

## Acceptance checks
- Fresh DB reaches latest schema with one command.
- Seed data lets the portal and benchmark queries run without other modules.
- Query for "all timing data of task X" returns in one simple query (supports module 11).

## Running the database (Docker)
For now the database runs from the PostgreSQL 18 Docker image defined in `docker/` (see `docker/README.md`).
- Start: `docker compose up -d db` from the `docker/` folder (after copying `.env.example` to `.env`).
- Data lives in a named volume, so it survives restarts; `docker compose down -v` wipes it.
- A second database `computetorrent_test` is created automatically for module 12 tests.
- Tables are created only by Alembic migrations, never by the init SQL.
- Optional browser UI: Adminer via `docker compose --profile tools up -d`.
- Port is bound to localhost only; providers never connect to the database directly.

## Out of scope
Sharding, replication, cloud-managed DB.
