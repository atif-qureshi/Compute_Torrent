# 04 — Task Slicer and Scheduler (Mode Selector)

## Purpose
Implements the concept's **Smart Task Decomposition / Automated Task Slicing Engine**: evaluate the task's difficulty, decide how it is executed (mode), cut it into chunks fitted to hardware tiers, add canary chunks, and produce the manifest. Runs inside the Coordination Server (module 02).

## Difficulty evaluation (first step)
Before slicing, estimate: input size (prompt count, tokens), expected compute (output length, model size), memory need (model + cache), and how many provider tiers in the pool can serve it. Output: a difficulty class (small / medium / large) and a resource estimate, shown to the requester before running and used to pick chunk sizes. Small tasks may stay in one chunk.

## Modes
| Mode | Idea | When to use (MVP rule) |
|---|---|---|
| CG-BP (coarse-grained block placement, from the Sun et al. / scheduling line of work) | place model blocks across nodes in a pipeline; fewer, larger stages | model too big for one node, or few workers with large memory |
| WS-RR (waterfilling-style split + request routing) | many independent requests routed across replicas by capacity | batch of many prompts, model fits on each worker |

**MVP default:** WS-RR style (batch of prompts spread over workers) because it needs no inter-worker pipeline. Add CG-BP after the first end-to-end success. Document any simplification versus the papers.

## Mode selector rule (simple, explainable)
1. If the model fits in the smallest eligible worker's memory -> WS-RR.
2. Else if a set of workers can jointly hold the blocks -> CG-BP.
3. Else reject task with a clear reason.
4. Requester may force a mode for experiments (module 11).

## Slicing responsibilities
1. Split input into N chunks sized by worker capacity (not equal sizes by default).
2. Keep original ordering index on every chunk.
3. Inject canary chunks (see 06) mixed in at random positions.
4. Hash each chunk payload.
5. Optionally compress payloads (ZSTD, post-MVP tuning).
6. Build the manifest: chunk list, hashes, model/adapter version, deadline hints. Orchestrator keeps a private copy including canary markers.
7. Support re-slicing a failed chunk into smaller pieces if it keeps failing.

## Inputs / Outputs
| In | Out |
|---|---|
| task (prompts, model version, tier, mode hint) | manifest + chunk payload files |
| worker capacity snapshot from 05 | chunk size plan |

## Dependencies
- Needs: 02, 03, 10; soft: 05.
- Feeds: 05, 06, 07.
- Tech: Python, Pydantic, ZSTD.

## Rules
1. Reassembly must be possible from manifest alone (index + count).
2. Chunks for the same task are all tied to one model version.
3. Privacy level 2: slice so no single seeder gets the entire task.

## Build steps
1. Fixed-size chunker with ordering and hashes.
2. Capacity-weighted chunk sizes.
3. Mode selector with the rule above.
4. Canary injection hook (empty first, filled by 06).
5. Second mode (CG-BP) plus mode comparison hooks for 11.

## Acceptance checks
- Concatenating verified chunk outputs in index order equals single-node output (same model, greedy decode).
- Selector picks expected mode for 5 prepared scenarios.
- Manifest sent to workers contains no canary hints.

## Out of scope
Training/fine-tuning splits, speculative decoding (listed in literature, not in MVP).
