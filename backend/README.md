# Standalone backend

This is a separate copy of the current ComputeTorrent coordinator API. It includes its own model registry and copies of the task slicer and verification module. Changes here do not alter the numbered modules or the root Compose stack.

## Local run

From the repository root, install `backend/requirements.txt`, then run:

```powershell
python backend/main.py
```

Set `DATABASE_URL`, `COMPUTETORRENT_API_TOKEN`, `COMPUTETORRENT_SEEDER_ENROLLMENT_TOKEN`, `COMPUTETORRENT_SWARM_URL`, and `COMPUTETORRENT_SWARM_DATA` in the process environment when connecting this copy to local PostgreSQL and the swarm service. It listens on port 8001 and expects the swarm administration endpoint to remain local/private.

Register a local GGUF model with `python backend/app/register_model.py <name> <model.gguf>`. The model is copied into the shared swarm store and its hash and magnet URI are written into `backend/app/models.json`.

The root `docker-compose.local.yml` continues to run the canonical `orchestrator/` implementation. `docker/docker-compose.yml` is the separate Compose stack that builds this backend and the copied `frontend/` tree.
