# 06 — Verification Engine

This module contains working MVP checks and research-inspired audit records. It does **not** implement full VeriLLM or a production-grade canary verification protocol. The limits below are intentional and should stay visible in product and research documentation.

## Available in this MVP

| Check | Current behavior | Assurance limit |
|---|---|---|
| Payload integrity | Provider checks downloaded prompt/model/adapter SHA-256 values; result text is checked against its reported output hash. | Proves bytes match the expected digest, not that inference was honest or correct. |
| Replica agreement | Up to three unique providers can execute a chunk; a strict output-hash majority is accepted. Duplicate provider reports do not count twice. | With one available provider there is no independent replica agreement. Hardware/runtime differences can reject otherwise valid results. |
| Known-answer canary | An operator-provided prompt and expected output hash can be queued as a separate internal task through the normal provider queue/runtime. A mismatch fails the task, records a provider failure, and repeated failures quarantine the provider. | Exact-output checks require matching model, runtime, seed, and decoding behavior. Canary probes are not mixed into user prompts and do not prove the ordinary task was computed correctly. |
| Challenged transcript receipt | The coordinator commits to all unique replica reports and the task/model/prompt/verdict envelope, then samples up to two distinct report openings from a fresh nonce. `GET /api/verifications/{task_id}/{chunk_id}` independently validates envelope binding, challenge selection, and Merkle inclusion proofs. | This makes the stored output transcript tamper-evident and checkable. It does not prove hidden-state inference, bind to a public consensus ledger, or stop a compromised coordinator from fabricating the original receipt. |

The hidden canary task is filtered from requestor task/history APIs. The expected answer hash remains coordinator-side. No canary is represented as proof that the assigned provider independently computed an ordinary user prompt.

## Future architecture work

- Full VeriLLM protocol components: per-layer activation logging and commitments, verifier prefill/recomputation, indistinguishable inference/verification work, VRF/on-chain challenge and dispute contracts, peer-prediction incentives, and the protocol's trust assumptions.
- Production canary design: stronger probe secrecy and rotation policy, robust cross-runtime tolerances, collusion analysis, controlled recovery, and measured false-positive/false-negative rates.
- Independent auditability for the randomness, commitment timing, and verifier implementation.
- Evaluation against honest, faulty, and colluding providers before presenting checks as security guarantees.

These protocol components are roadmap work, not simulated features. The local MVP now has the challenged transcript checks and exact-answer canary workflow described above; the portal must continue to label them as MVP checks.

## Operational constraints

- The coordinator holds canary expected-output hashes and verification state.
- Credits are awarded only for verified outputs, but credits are demo accounting with no monetary value.
- A failed replica majority fails closed; the current implementation does not perform VeriLLM-style partial re-execution to arbitrate disagreements.
- See [implementation status](../docs/IMPLEMENTATION-STATUS.md) and [risk decisions](../docs/RISKS-AND-DECISIONS.md).
