# Portal redesign — 2026-11-08

## Audit and implementation boundaries

The canonical portal is Next.js 14 Pages Router / React 18 / TypeScript, using global CSS and two older CSS modules. Operator authentication is an HTTP-only session cookie; `/api/ct` forwards authenticated requests with server-only credentials. Existing backend and updater behavior are preserved.

Inventory: overview, model studio, run/deployment list, nodes, task history, credits, settings and login already exist. Monitoring and help routes are missing. Existing components use large amounts of repeated inline styling and emoji. Polling is duplicated per page and shell; some failures become zero or empty lists. Dialogs do not trap focus. Readiness can fall back to Docker availability. Persistent deployment endpoints, streaming generation, pause/resume, remote resource editing, notification persistence and historical telemetry are not supported. These will not be fabricated.

## Information architecture and direction

Workspace: Overview / Model Studio / Deployments. Infrastructure: Compute Nodes / Monitoring. Activity: Task History / Credits. Management: Settings / Help. Desktop navigation is persistent; mobile uses an accessible modal drawer. The palette is neutral ink/navy with restrained violet actions, semantic statuses, compact type, clear rules and tabular figures. Distinct views use tables, a guided configuration canvas, a split inspector and operational summaries rather than repeating decorative cards.

All data comes from existing health, seeders, distributed status/catalog/jobs, history and credits endpoints. Each resource retains its own last-success timestamp and failure state. A disconnected or unavailable resource is never rendered as a successful empty response. Node identity/connection/eligibility/runtime are shown separately.

Models are per-request runs: each submitted configuration loads its assigned shards and generates output, then releases workers. The UI does not advertise an always-on endpoint. Playground actions submit another real run. Advanced JSON/XML import remains available. Research-specific receipt panels are omitted per the operator instruction; backend execution is unchanged.

## References (interaction research, not copied interfaces)

- https://vercel.com/docs/projects — separation of project configuration, deployments and operations.
- https://huggingface.co/docs/inference-endpoints/guides/create_endpoint — progressive configuration, initialization and testing.
- Linear views documentation was unavailable during the review; no findings are attributed to it.

## Acceptance record

Implementation and test evidence will be appended after actual checks. No participant research, accessibility conformance score, live inference success or production readiness is assumed.

## Local Docker activation — 2026-11-08

At the operator's explicit request, rebuilt the `portal` image and recreated only that service with `docker compose -f docker-compose.local.yml up -d --no-deps portal`. Port 3000 now serves the redesigned source rather than the earlier image. The other four services retained their running uptime; no backend/provider/updater changes were made.

Validation: Docker production build passed. HTTP 200 confirmed for login, overview, Model Studio, nodes, monitoring and help. The delivered Model Studio JavaScript bundle contains the new guided setup. Operator sign-in and authenticated health, seeders, catalog and jobs proxies passed; anonymous sessions remained unauthenticated. No jobs were submitted or cancelled. Browser rendering/responsive verification remains uncompleted following the prior Computer Use URL-identification block.
