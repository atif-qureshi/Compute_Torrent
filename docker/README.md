# Separate local Docker stack

This Compose stack builds the standalone copies in `backend/` and `frontend/`; it does not replace or merge them into the canonical numbered modules. The P2P swarm service still uses `07-network-layer/`. Only local/LAN bindings are configured; there are no domain, reverse-proxy, or public-deployment services.

From the repository root, copy `.env.example` to `.env`, replace the secret placeholders, start Docker Desktop, and run:

```powershell
docker compose --project-directory . -f docker/docker-compose.yml up --build -d
```

Open `http://localhost:3000`. Stop this stack with:

```powershell
docker compose --project-directory . -f docker/docker-compose.yml down
```

The alternative canonical stack is `docker-compose.local.yml`; do not run both at once because they use the same local ports and container names.

The model registry is `backend/app/models.json` for this stack. Register an operator-approved GGUF model from the repository root with `python backend/app/register_model.py <name> <model.gguf>` after the swarm service is running. The model and task payloads are verified by SHA-256 and transferred through WebTorrent.
