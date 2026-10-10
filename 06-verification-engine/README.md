# 06 — Verification Engine (3 layers, no blockchain)

## Purpose
Decide whether results from unknown machines can be trusted, without blockchain or TEE hardware. Runs inside the Coordination Server after each `result_submit` arrives; the seeder app knows nothing about canaries or audits.

## Layer overview
| Layer | Name | Question answered | Cost |
|---|---|---|---|
| L1 | Canary Trap (Melous-style) | Did the worker really compute, honestly? | very low |
| L2 | SERENE (replication-based collusion detection) | Do independent replicas agree, is anyone colluding? | medium (extra replicas) |
| L3 | VeriLLM (partial re-run + peer prediction) | Is this specific LLM output faithful to the model? | low (about 1% in the paper) |

Run order: L1 on everything -> L2 on sampled or risky chunks -> L3 on disputes and random audits.

## L1 Canary Trap
- Orchestrator creates canary prompts with a **known expected output** (computed in advance by trusted runs, greedy decoding).
- Mixed randomly among real chunks, indistinguishable by format and size.
- Result check: output matches expected (exact or within defined tolerance).
- Outcomes: pass raises worker trust; fail flags worker and invalidates all its recent results.
- Metric: VSR = results passing canary / returned results x 100.

## L2 SERENE-lite
- Same chunk assigned to r workers (r = 2 or 3, chosen by risk).
- Compare outputs (exact match under greedy decoding; tolerance rule if hardware differs).
- Disagreement -> third replica or L3 arbitration.
- Track pairwise agreement history to expose collusion (two workers always agreeing on outputs that disagree with others).
- Collusion handling: flag pairs, force replicas onto non-flagged workers.

## L3 VeriLLM-lite
- Verifier takes a random subset of positions in the result and re-computes only that part (partial re-run), compares.
- Peer prediction idea: verifier reports are cross-checked so verifiers are also incentivized to be honest.
- MVP version: the orchestrator or a trusted verifier worker does the partial re-run; no on-chain proof. State this limitation in the report.

## Verdict handling
| Situation | Action |
|---|---|
| all layers pass | chunk VERIFIED, credits awarded |
| L1 fail | reject, flag worker, penalty, re-run elsewhere |
| L2 mismatch | arbitrate (third replica or L3), penalize loser |
| L3 mismatch | reject, strong penalty, possible suspension |

## Inputs / Outputs
| In | Out |
|---|---|
| returned results, expected canary outputs, replica sets | verdicts (layer, outcome, detail) |
| worker history | updated trust score and flags |

## Dependencies
- Needs: 03, 04 (canary injection), 08 (workers to produce replicas).
- Feeds: 09 (credits), 05 (trust/eligibility), 11 (VSR metric).
- Tech: Python; statistical helpers (simple tests, AUROC-style evaluation of detection in experiments).

## Rules
1. Verification secrets (canary map, audit positions) live only in the orchestrator.
2. Deterministic decoding settings are mandatory for comparability (see docs/RISKS-AND-DECISIONS.md D6).
3. Verification cost is measured separately as V_i for the time model.
4. Sampling rates are configuration, so experiments can vary them.

## Build steps
1. Canary generator and checker (L1) with a deliberately cheating test worker.
2. Replica assignment and comparison (L2).
3. Pair-agreement tracking and collusion flag.
4. Partial re-run audit (L3).
5. Detection-rate experiments with simulated cheaters (feeds 11).

## Acceptance checks
- A worker that returns random text is caught by L1 in nearly all runs.
- Two colluding workers returning identical wrong results are flagged by L2/L3.
- Honest workers are rarely falsely flagged; measure false positive rate.
- Verification overhead is reported as a percentage of total time.

## Out of scope
Zero-knowledge proofs, on-chain verification, TEE attestation.
