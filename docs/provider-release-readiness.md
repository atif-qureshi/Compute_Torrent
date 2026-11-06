# Provider release readiness checklist

Phase 0.5 checkpoint, 2026-11-06. **Production release blocked.** The checks below refer to the inspected source and isolated fixtures.

| Gate | Status | Evidence or required next action |
| --- | --- | --- |
| Signed metadata and package integrity | Passed in isolation | Rejects unsigned, forged, altered or incompatible metadata and corrupted payloads. Verified launch was intercepted. |
| HTTPS trust and redirects | Passed on loopback | Untrusted chain and hostname mismatch rejected. Trusted test TLS accepted. HTTPS-to-HTTP redirect denied. |
| Missing configuration and replay | Passed within local state assumptions | Unprovisioned builds reject updates. Older/conflicting sequences fail while local SQLite state is intact. A clean or restored client has no prior high-water mark. |
| Stable/testing channels and version | Passed in isolation | Wrong channel rejected. Testing signer/client round trip and numeric version ordering passed. Packaged channel separation is pending. |
| Legacy route containment | Passed in patched source | Isolated GET returned 410 and POST returned 405. Real ingress denial, image digest pinning, and rollback probes are pending. |
| Legacy exposure and migration | Blocked for rollout | No verified remote hostname or complete client/download inventory. Require operator-owned logs, ingress retirement and independently authenticated manual bootstrap. |
| Clean Windows installation and legacy upgrade | Blocked | No isolated Windows VM or Sandbox was available. Validate per-user install path, Start Menu, installed version, settings and node identity. |
| Real signed update, restart, interruption and recovery | Blocked | Exercise clean install, valid and invalid update, cancel/interrupt, interrupted transfer, restart, and recovery in disposable Windows instances. Keep a trusted recovery installer. |
| Hosted HTTPS and publisher permissions | Blocked | No provisioned release host or identity was available. Verify hostname, certificate chain and renewal, authorized publisher writes, unauthorized write denial, read-only serving, and payload-before-manifest promotion. |
| Signing keys and revocation | Blocked | Generate protected, separate stable/testing keys outside the checkout and serving path. Validate access, backup and rotation. Test emergency manifest withdrawal and a new-key bootstrap. |
| Windows publisher identity and artifact provenance | Blocked | The inspected legacy setup is unsigned. Define and validate Authenticode publisher policy, sign and timestamp the approved setup, and verify package version, embedded public key, channel, build digest and signed metadata. |
| Audit logging and emergency disablement | Blocked | Record approved signer, publisher, channel, version, sequence, digest, timestamp and approval reference. Retain release-host logs with restricted access. Drill disabling both manifests and keeping legacy ingress denied during rollback. |
| Regression coverage | Partial | Unit suites, in-process enrollment/WebSocket/API checks, portal type checking and mocked notification checks passed. Live Compose, browser and provider GUI, real P2P and model execution remain unverified. |
| Approval | Pending | Approve the Phase 0.5 checkpoint before resuming Phase 1. Deployment, publication, volunteer distribution and live-service changes each require explicit authorization. |

See the [audit and migration procedure](security-update-audit.md) and [test evidence](testing-results.md).
