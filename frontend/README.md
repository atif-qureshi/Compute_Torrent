# ComputeTorrent submitter portal

This is the standalone frontend copy of the local Next.js requestor portal. It is maintained separately from `01-submitter-portal/`.

## Available pages

- **Workspace:** select a registered GGUF model, enter one prompt or a batch of up to 500 independent prompts, set output-token and worker RAM/CUDA requirements, and select WS-RR or CC-BP scheduling.
- **Network:** see connected provider PCs and available CPU/GPU/RAM profile details, revoke a provider credential, copy the coordinator WebSocket address, and follow trusted-LAN join instructions.
- **Task history:** poll task/chunk progress, inspect verification summaries, view completed results, and download result JSON.
- **Credits:** inspect the requestor credit balance and ledger. Credits are demo accounting and have no cash value.

The portal validates the prompt limits used by the coordinator and explains that prompts are sent to assigned volunteer PCs. The coordinator remains authoritative for model, hardware, credit, and task validation. Task submission is one request per batch; a batch of prompts costs one demo credit.

## Local development

The standalone Compose stack builds this directory with `docker/docker-compose.yml`; the canonical Compose stack builds `01-submitter-portal/` with `docker-compose.local.yml`. Choose one stack at a time. For standalone development, install the package dependencies and set:

```dotenv
COMPUTETORRENT_ORCHESTRATOR_API_URL=http://127.0.0.1:8001/api
COMPUTETORRENT_API_TOKEN=<same private value as the local coordinator>
COMPUTETORRENT_PORTAL_PASSWORD=<private local password>
COMPUTETORRENT_SESSION_SECRET=<at least 64 random characters>
COMPUTETORRENT_COOKIE_SECURE=false
```

Run `npm run dev` and open `http://localhost:3000`. Keep the portal and coordinator local or on a trusted LAN; no domain/public deployment is needed. The portal uses one local operator login and the fixed `web-portal` requestor identity. It is not a multi-user hosted service.
