# Phase 3 connectivity implementation checkpoint

The canonical control changes and isolated relay prototype are implemented. The Phase 3 completion condition remains open pending real device and pinned-runtime validation. This work did not start services, run ngrok, publish packages, change updater trust, or alter legacy route retirement.

## Implemented

| Area | Source and behavior |
| --- | --- |
| Enrollment | `orchestrator/app/main_production.py` requires the configured operator code and rejects the built-in fallback. The existing revocable credential and node ID remain the identity mechanism. The portal obtains the operator code through the authenticated API, with no default or tunnel-file fallback. Existing enrollment codes are shared operator secrets. Expiring single-use invites and proof-of-possession keys remain open. |
| Control transport | Canonical and legacy desktop shells require WSS for public endpoints. Plain WS accepts localhost and explicit private addresses for trusted LAN use. Enrollment and credential-bearing WebSocket connections do not follow redirects. Changing the coordinator origin requires enrollment for the new origin rather than sending the old bearer credential. |
| Session health | Desktop waits for a matching registration acknowledgment before marking itself connected. Canonical coordinator bounds initial registration and requires heartbeats within 45 seconds. Duplicate live sessions are rejected and only the owning connection can clear state. Reconnect uses bounded jitter and can reuse the same node identity. Workspace exposes heartbeat age as a control-plane measurement. |
| Local discovery | Desktop waits for the existing libp2p helper's joined marker and times out stalled helpers. The existing LAN mDNS and explicit bootstrap remain in place. Overlay status is kept separate from file and Petals readiness. Automatic coordinator discovery from an invite remains open. |
| ngrok | `start-ngrok.ps1` targets the loopback coordinator, matches the inspector's upstream, checks the legacy manifest retirement marker before launch, and stops copying or printing enrollment codes. Portal discovery requires a matching live inspector entry. The tunnel is a control path. Neither script nor tunnel was started. |
| Relay experiment | `11-evaluation-benchmark/petals_relay_prototype.py` pairs two outbound certificate-verified WSS sessions with one-use role credentials, a lease, frame/byte limits and fixed loopback destination. The loopback test sends TCP bytes to a fixture worker and receives the response. It is not wired into Compose, provider packaging, worker address advertisement, job admission or production. |

## Verification and remaining gates

- Three new isolated tests passed in `12-testing-validation/test_phase3_connectivity.py`. They cover endpoint policy, fallback enrollment rejection, wrong/duplicate credentials and session ownership, expiry and reconnect, legacy manifest 410, and TLS relay transfer with untrusted certificate, wrong role, quota and replay rejection.
- Existing provider (11), Petals network (4), and secure update (7) tests passed. Portal type checking, PowerShell launcher parsing and diff checks passed. Existing library deprecation warnings were observed.
- No real two-PC Wi-Fi, multi-PC LAN, separate ISP, CGNAT, proxy or restrictive firewall test was run. No pinned Hivemind bootstrap or layer RPC has traversed this relay. Live inference compatibility remains unverified. The separate standalone backend has a pre-existing indentation error in `backend/app/main.py` as confirmed in HEAD. It was left outside the canonical implementation.
- The prototype handles one stream pair per route and closes the pair on EOF. It needs TCP half-close semantics, validated listener/advertisement mapping for both directions, runtime peer-ID proof, and job/workspace-scoped authorization before integration. There is no automatic production NAT traversal or relay fallback yet. Existing WebTorrent transport remains separate. Repository onboarding has no tracked Tailscale requirement.

Next, use isolated Docker environments and two authorized test devices to validate bootstrap and native stage RPC over both direct and mapped routes. Only then connect the relay to scheduler eligibility and run the Wi-Fi, LAN, remote, CGNAT, firewall and disconnect matrix from the [network design](network-design.md). Hosted ingress, volunteer builds and distribution remain separate approval gates.
