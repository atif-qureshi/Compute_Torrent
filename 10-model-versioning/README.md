# 10 — Model, Adapter and Benchmark Versioning

## Purpose
Guarantee that every worker runs exactly the same model, adapter and settings, so results are reproducible and comparable.

## What is versioned
| Item | Identity |
|---|---|
| Base model | name + weights hash + swarm infohash |
| LoRA adapter | adapter ID + base model version + hash + infohash |
| Inference config | decoding mode (greedy), seed, max tokens, tokenizer hash |
| Benchmark set | dataset name, prompt list hash, version |
| Worker environment | container image digest |

## Responsibilities
1. Registry of model and adapter versions in DB with hashes and infohashes.
2. Manifest binding: every task manifest stores exact version IDs (no "latest").
3. Worker check: before running, worker compares its local hash to the manifest; mismatch triggers download of the right version.
4. Compatibility rules: an adapter only applies to its declared base model version.
5. Cache management on workers (keep last N versions).
6. Deprecation: mark a version retired without deleting history.
7. Benchmark versioning so experiments in module 11 can be repeated exactly.

## Inputs / Outputs
| In | Out |
|---|---|
| new model/adapter upload (admin) | version record + seeded torrent |
| task request | resolved version IDs in manifest |
| worker hash report | OK or "needs download" |

## Dependencies
- Needs: 03. Soft: 07 (distribution).
- Used by: 02, 04, 08, 11.

## Rules
1. Hash is the identity; names are labels.
2. Verification comparisons (06) are valid only within the same version tuple.
3. Never change a published version; create a new one.

## Build steps
1. Version tables and admin script to register a model.
2. Manifest binding and worker check.
3. Adapter compatibility check.
4. Cache cleanup policy.
5. Benchmark version records for 11.

## Acceptance checks
- Two workers with different local model files: one is forced to re-download, the other runs.
- Task referencing a retired version is rejected with a clear message.
- Re-running a benchmark version reproduces the same prompt set exactly.

## Out of scope
Model training pipelines, automatic model conversion.
