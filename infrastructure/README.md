# Local infrastructure helpers

These scripts start, stop, and inspect the local Docker Compose stack. They do not deploy to a domain or expose services publicly. By default they run the canonical `docker-compose.local.yml`; pass `-Stack standalone` to use the separate `backend/` and `frontend/` copies under `docker/docker-compose.yml`.
