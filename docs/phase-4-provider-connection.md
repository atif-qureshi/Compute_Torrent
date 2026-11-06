# Phase 4 provider connection checkpoint

Phase 4 applies to the canonical Windows provider at `08-provider-node/05-desktop-app-shell/production_seeder.py`, the entry point used by the canonical packaging recipe. The separate desktop source tree retains its earlier behavior. Coordinator, Petals, WebTorrent and update protocols were outside this change.

| Volunteer step | Implemented behavior |
| --- | --- |
| Find the coordinator | Paste the operator's HTTPS/WSS address, enter a same-LAN private IP, or reuse the saved address. A bare private IP uses port 8001. The adapter supplies the provider WebSocket path. Public endpoints still require WSS. |
| Join | Enter the operator code for first enrollment or credential recovery. Same-origin saved credentials can be reused. Changing origin requires a code for the new coordinator. The code remains memory-only. |
| See connection progress | Connecting, Enrolling, Registering, Registered, Reconnecting and Disconnecting are separate from task activity. Registered requires an acknowledgment with the expected node ID. A socket-close watcher clears that state even while a local task handler is busy. |
| Recover | Network loss retries with bounded jitter. Rejected credentials, invalid response/address and certificate errors return the user to onboarding with guidance. The client avoids showing raw server response details. |
| Disconnect or pause | Disconnect returns to onboarding, including cancellation during registration or backoff. Pause declines new assignments while allowing active work to finish. Disconnect and Quit ask the user to finish or cancel active work first. This avoids leaving a worker starting after the app exits. |
| See available resources | Existing CPU, RAM and GPU cards show configured limits, reported free RAM and dedicated VRAM. Docker availability is displayed separately from coordinator registration. Heartbeats refresh the dashboard resource summary. |

The optional discovery overlay starts after registration and releases its helper on session teardown. The app prevents overlapping manual connection attempts, cleans up the background loop on disconnect and serializes settings writes. An enrollment or hardware call already running on a worker thread may take until its timeout to finish. During a dropped connection, the badge clears immediately. Reconnection can wait for an already-running local task handler to settle. This does not add model-session failover.

## Validation

- Eight new tests in `12-testing-validation/test_phase4_provider_connection.py`. Loopback WebSockets verified delayed matching acknowledgement, wrong identity, cancellation while waiting, reconnect, and immediate status loss during a busy handler. Other cases covered shorthand and TLS policy, safe error messages, and active-task pause/disconnect/quit behavior.
- A hidden Windows CustomTkinter fixture with temporary settings verified onboarding construction, badge transitions, node ID, hardware values, Docker status and return to onboarding. External hardware scans and network startup were stubbed for this widget check.
- The 26 previously passing Phase 3, provider, Petals network and secure updater tests also passed. No packaged EXE or live coordinator was used.

The supported flow still starts with an operator-provided address and join code. Automatic cross-network discovery, real volunteer acceptance and the Phase 3 multi-device matrix remain open. The Tailscale development fallback remains available wherever operators already use it. Release, updater and deployment gates remain in force. Phase 5 awaits approval.
