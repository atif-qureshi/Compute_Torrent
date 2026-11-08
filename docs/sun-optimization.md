# Sun optimization implementation checkpoint

2026-11-08. Targeted Phase 8 optimization work requested by the operator. Implemented and isolated-tested; the whole phase is not complete. No live services restarted, provider executables distributed, or updater settings changed.

## Research attribution and implementation

The supplied Sun et al. paper is the source of CG-BPRR, CG-BP, WS-RR, the joint memory/placement/routing formulation, and conditional performance bounds. The two Petals papers provide contiguous transformer hosting, native distributed execution and routing foundations. Sun does not provide a universally optimal replacement for every Petals heuristic: conservative sizing can reject feasible problems and its greedy solution can be suboptimal. The author's simulator is https://github.com/TingyangSunJeff/LLM_inference_simulator ; this implementation was independently derived from the supplied paper, not validated as byte-for-byte simulator parity.

| Paper method | Code | Scope |
| --- | --- | --- |
| Algorithm 1 conservative block capacities, amortized server ranking, underserved-block placement and lexicographic tie breaking | `orchestrator/app/sun_optimizer.py`: `cg_block_placement`, `cg_bprr` | Reference kernel; fractional session capacities preserved |
| Equations 3/4 boundary graph and client-centric shortest path | `shortest_route` | Exact reference suffix consumption by default; bounded participant extension explicitly opt-in |
| Equation 8 prefill and decode cost weighting | `Server.edge_seconds` | Reference kernel and optional MILP cost model |
| Algorithm 2 coarse placement and fine waiting-aware routing | `OnlineAllocator`, `cache_wait` | Reservation/admission library, not a deployed concurrent job service |
| Equation 20 cache release waiting | `cache_wait`, `OnlineAllocator.admit/complete` | Predicted finish never frees real reservations without explicit completion |
| Mean-plus-standard-deviation request target and sufficient bound 19 | `suggest_request_target` | Reference tuning helper; a bound below one is not proof of infeasibility |
| Joint optimization equation 6 | `orchestrator/app/sun_milp.py`: `joint_milp` | Equivalent interval-choice/boundary-flow formulation with optional SciPy/HiGHS; bounded offline oracle |
| LP lower bound and theoretical bounds 17/35 | `joint_milp(relaxation=True)`, `performance_bounds` | No fractional-plan rounding; assumptions checked |

The MILP is an equivalent interval formulation, not a verbatim implementation of the paper's big-M equation 13. Idle servers may be omitted. CPU adaptation, minimum participant constraints, partial hosted-range consumption, freshness checks and baseline dominance gating are ComputeTorrent engineering extensions, not published Sun contributions. Do not attribute performance guarantees to these extensions.

## Actual coordinator integration

`distributed.py` preserves the former planner as `baseline_placement`. `COMPUTETORRENT_PLANNER=auto|baseline|sun` controls selection. Auto requires fresh matching native memory/compute evidence and observed activation-path costs, then selects Sun only when its estimated decode cost is strictly below the baseline under the same model. Otherwise it retains the baseline and records the reason. Strict `sun` is for controlled experiments and fails explicitly when prerequisites are absent.

`sun_runtime.py` converts current eligible peers into measured servers. It reuses actual CPU/GPU limits, available memory, model block bytes and cache bytes. Unknown latency is never zero. Calibration keys bind model revision, device, runtime digest, configured limits and network context. Records expire after 900 seconds. Only completed runs with passing existing verification and canary results contribute at least three decode samples. First-token and verification work are excluded. P95 RPC minus native compute is labelled a communication estimate; negative residuals remain non-routable evidence. Multiple stage lengths can fit a positive compute/intercept model with a bounded residual. This is not an independent bandwidth/RTT benchmark.

`generate_job.py` records actual per-stage RPC timings. SQLite stores calibration without changing peer identities. Optional calibration write failures cannot invalidate completed inference. Recovery or a changed transport invalidates the modeled plan estimate. Job diagnostics distinguish reference hosted intervals from actual disjoint processed ranges.

The existing runtime admits one active job and starts ephemeral workers. It materializes selected processed ranges only, not an always-on replicated CG-BP pool. Therefore full online multi-request deployment of Algorithm 2 is still pending. The tested reservation engine alone does not establish that feature. Model context, KV growth, network contention and churn can invalidate constant-cost predictions; actual end-to-end evaluation remains essential.

The gateway image now uses `computetorrent-petals-gateway:local`, avoiding overwriting the provider-owned `computetorrent-petals:local` runtime/digest contract. Candidate gateway and coordinator images were built; existing running containers were not recreated. Source activation requires a separately approved local service restart. No installer rebuild is required for the timing collector, which runs in the gateway.

## Verification evidence

Final selected suite: 28 optimizer tests, 5 native-capacity tests, 13 recovery tests and 12 hybrid-network tests: **58 passed**. Python compilation, scoped `git diff --check`, Compose configuration validation and production-path optimizer imports in the candidate Python 3.10 image passed. A package-style import probe initially used a different path from the script entrypoint; the actual `/app/app` production import path passed. Existing FastAPI lifespan deprecation warnings remain.

Optimizer tests include 60 seeded shortest-path comparisons against exhaustive search, memory/coverage constraints, missing/stale telemetry, waiting/admission behavior, participant limits, dispatch integration, MILP versus independently enumerated tiny optima, LP bounds and calibration failures. The paper's small conservative-placement counterexample is reproduced: CG cost 22 versus exact cost 12. These are modeled costs, not measured seconds or speedups.

Two disposable network-disabled Docker fixtures ran real native Petals workers over the authenticated local WSS integration. Tiny random four-layer BLOOM and Llama/GQA both executed unequal **3+1** ranges, matched reference generation, completed the production pipeline and passed existing canary checks. Each captured ten stage RPC samples. Post-startup WSS payload was 45,939 bytes for BLOOM and 40,273 bytes for Llama. Fixture planner costs/capacity caps were controlled inputs. These tests prove isolated native integration, not pretrained accuracy, real GPU capacity allocation, two physical PCs, CGNAT connectivity or throughput improvement. Llama output is retained at `runtime/research-papers/sun-native-llama.log`.

`11-evaluation-benchmark/run_sun_comparison.py` compares actual baseline and Sun planners on explicitly synthetic scenarios, recording modeled costs, planner overhead and raw inputs. Actual inference duration stays null. Optional dependencies are in `requirements-optimization.txt`. No synthetic result is advertised as a measured speedup.

Reproduce selected tests with `python -m unittest discover -s 12-testing-validation -p test_sun_optimizer.py` and the three corresponding patterns `test_native_capacity_allocation.py`, `test_hybrid_recovery.py`, `test_hybrid_networking.py`. Run the offline comparison with `python 11-evaluation-benchmark/run_sun_comparison.py --milp`. Native smoke uses `CT_FIXTURE_SUN=1 CT_FIXTURE_LAYERS=4 CT_FIXTURE_MODEL=bloom` (or `llama`) with `11-evaluation-benchmark/smoke_integrated_petals_relay.py` inside the existing Petals image and repository/runtime Python paths.

## Remaining release and research gates

1. Approve local coordinator/gateway activation; verify fresh successful calibration in a real pretrained run.
2. Test heterogeneous physical CPU/GPU peers, model-specific cache/context limits and observed LAN/WAN costs. Retain the development fallback.
3. Run repeated baseline-versus-Sun pretrained A/B trials with identical prompts/seeds/context/load; report TTFT, token latency, throughput, memory, failures and planning overhead with distributions.
4. Implement persistent replica lifecycle and concurrent request admission/KV accounting before claiming full online Algorithm 2 service integration. Preserve recovery/session isolation.
5. Evaluate queue prediction and placement refresh under churn and load; validate ISP/CGNAT/firewall/reconnection behavior separately.
6. Review optional MILP dependency pinning and solver resource limits before adopting it beyond the bounded offline oracle.

Phase 8 remains partially implemented/isolated validated. No claim of global optimality, global P2P production readiness, completed multi-request scheduling, or production release approval is made.
