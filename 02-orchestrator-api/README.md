# ComputeTorrent coordinator API

The canonical coordinator implementation is in `orchestrator/`. It is the central control plane for the local volunteer-computing MVP.

## Working API and provider flow

- Authenticated portal API for model listing, task submission/detail/history, provider listing/revocation, credits, and local network status.
- Provider enrollment code creates a unique revocable credential for each provider PC.
- Provider WebSocket accepts registration, heartbeat, status, and result messages; assignments and verdict notices flow back over the same connection.
- The coordinator validates registered model manifests, slices independent prompt batches, selects eligible idle providers, and stores task/chunk state in PostgreSQL when available.
- It asks the swarm service to create and tear down private WebTorrent swarms for model/prompt data. The libp2p overlay is separate and does not relay those files.
- Returned text is hash-checked and verified using replica agreement, optional internal known-answer canary tasks, and limited transcript receipts. Full VeriLLM/canary verification is future work.
- Local deployment uses the Compose stack from the repository root; see [implementation status](../docs/IMPLEMENTATION-STATUS.md) and [local setup](../IMPLEMENTATION-SETUP.md).

## Current limits

- One central coordinator; no serverless/libp2p coordination or multi-coordinator failover.
- One local operator login and a fixed requestor account; not a multi-customer hosted service.
- Provider access tokens are per-node, but authorization and privacy policies are designed for a trusted local/LAN MVP.
- Tasks are independent prompt inference; the coordinator does not run training, model-parallel inference, or arbitrary user code.
- No Socket.IO portal event feed: the portal polls REST task/network endpoints.
- Disconnect handling can release/reassign work, but there is no production-grade lease timeout/restart-recovery system.

## Future work

- Multi-user identity, ownership isolation, quotas, stronger authorization, and operator audit logs.
- Resilient leases, bounded retries, coordinator recovery, and multi-coordinator operation.
- Trackerless libp2p file transfer and full VeriLLM/canary protocol integration.
- Production network threat model and security review before operating with untrusted internet participants.
