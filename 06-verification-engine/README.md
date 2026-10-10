# 06 — Verification Engine

This module contains working MVP checks and research-inspired audit records. It does **not** implement full VeriLLM or a production-grade canary verification protocol. The limits below are intentional and should stay visible in product and research documentation.

## Available in this MVP

| Check | Current behavior | Assurance limit |
|---|---|---|
| Payload integrity | Provider checks downloaded prompt/model/adapter SHA-256 values; result text is checked against its reported output hash. | Proves bytes match the expected digest, not that inference was honest or correct. |
| Replica agreement | Up to three providers can execute a chunk; a strict output-hash majority is accepted. | With one available provider there is no independent replica agreement. Hardware/runtime differences can reject otherwise valid results. |
| Known-answer canary | An operator-provided prompt and expected output hash can be queued as a separate internal task; a mismatch fails the task and increments provider failure state. | Exact-output checks require matching model, runtime, seed, and decoding behavior. This is not robust canary injection into real work or a collusion-resistant trust protocol. |
| Transcript receipt | Replica reports are committed into a SHA-256 Merkle tree; the task detail page exposes sampled report proofs. | This is a tamper-evident output transcript inspired by VeriLLM. It is not a proof of hidden-state inference or faithful model execution. |

The hidden canary task is filtered from requestor task/history APIs. The expected answer hash remains coordinator-side. No canary is represented as proof that the assigned provider independently computed an ordinary user prompt.

## Future architecture work

- Full VeriLLM protocol components: hidden-state prefill checks, sound challenge generation, peer-prediction incentives, disputes, and the protocol's required trust assumptions.
- Stronger canary design: secrecy and rotation policy, robust cross-runtime tolerances, collusion analysis, controlled retries, and measured false-positive/false-negative rates.
- Independent auditability for the randomness, commitment timing, and verifier implementation.
- Evaluation against honest, faulty, and colluding providers before presenting checks as security guarantees.

These items are roadmap work, not simulated features. The portal labels the current checks as MVP/VeriLLM-inspired and explains their limits.

## Operational constraints

- The coordinator holds canary expected-output hashes and verification state.
- Credits are awarded only for verified outputs, but credits are demo accounting with no monetary value.
- A failed replica majority fails closed; the current implementation does not perform VeriLLM-style partial re-execution to arbitrate disagreements.
- See [implementation status](../docs/IMPLEMENTATION-STATUS.md) and [risk decisions](../docs/RISKS-AND-DECISIONS.md).
