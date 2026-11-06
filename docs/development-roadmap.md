# ComputeTorrent development roadmap

The root [flow.md](../flow.md) controls phase scope, task order and approval gates. The original MVP build phases in [progress.md](../progress.md) use different numbering. This document records the audit-based execution priorities while preserving the approved sequence.

| Phase | Work                                       | Evidence or dependency to carry forward                                                                                                                                             |
| ----- | ------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 0     | Repository audit                           | Current architecture, risks and baseline checks are recorded.                                                                                                                       |
| 1     | Research analysis and architecture mapping | Read the three supplied papers, verify exact citations, and map supported techniques to the actual inference path. Establish a reproducible baseline before choosing optimizations. |
| 2     | Networking design                          | Use separate reachability requirements for control, file transport and Petals activations. Include enrollment and update trust boundaries in the design.                            |
| 3     | Connectivity implementation                | Validate real LAN and cross-network paths, including direct/relay fallback, NAT/CGNAT, authentication, and reconnect.                                                               |
| 4     | Provider app improvement                   | Build onboarding, status and recovery on the verified connectivity path.                                                                                                            |
| 5     | Installation and updates                   | Treat authenticity and safe replacement as gates. Reconcile setup, raw payload and feed metadata, then verify installation, update, interruption and recovery.                      |
| 6     | Dashboard UI/UX                            | Preserve the operator workflow and validate navigation, responsiveness, and accessibility.                                                                                          |
| 7     | Provider UI/UX                             | Validate resource controls and update states against the working desktop flows.                                                                                                     |
| 8     | Inference optimization                     | Compare approved research techniques against the current memory-based placement and capture controlled performance measurements.                                                    |
| 9     | Stability, security and recovery           | Address remaining audit findings and exercise disconnect, cancellation, invalid input and identity failure cases.                                                                   |
| 10    | Integration and performance                | Run cross-device scenarios and both model execution paths, then publish results in repository documentation.                                                                        |
| 11    | Release preparation                        | Make builds reproducible and check controlled deployment and release readiness. Publication and production deployment require explicit authorization.                               |

The highest severity findings are the updater trust gap and the fallback enrollment path. Keep the current deployment baseline scoped to the trusted local environment while these findings are unresolved. See the [architecture findings](architecture-analysis.md#findings-and-implementation-status) for the remaining priorities.

**Current checkpoint:** Phase 0 audit complete. Phase 1 is pending approval.
