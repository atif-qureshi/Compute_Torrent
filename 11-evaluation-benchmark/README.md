# 11 — Evaluation and Benchmark

## Purpose
Produce the evidence for the research questions: single node vs P2P with 1, 2, 4, or N nodes, plus verification and incentive effects.

## Research questions mapped to experiments
| RQ | Experiments |
|---|---|
| RQ1 verification and incentives | E4 detection of cheaters, E5 credit behavior |
| RQ2 versioning and performance | E1 speedup, E2 overhead, E3 churn, E6 version consistency |

## Experiments
| ID | Name | What changes | Measured |
|---|---|---|---|
| E1 | Scaling | node count 1, 2, 4, N | completion time, speedup, efficiency |
| E2 | Overhead | payload size, network delay/bandwidth limits | communication overhead, transfer time |
| E3 | Churn | workers killed at random times | recovery time, success rate, extra work |
| E4 | Cheating | fraction of cheating workers, collusion | detection rate, false positives, VSR |
| E5 | Incentives | honest vs cheating workers | credit and trust trajectories |
| E6 | Versioning | mixed worker versions | forced re-downloads, consistency |
| E7 | Verification cost | sampling rates of L2/L3 | V_i share of total time |

## Formulas (from the proposal)
- T_P2P = max over i of (P_i + D_i + V_i)
- Speedup S = T_single / T_P2P
- Parallel efficiency E = S / N
- VSR = results passing canary / returned results x 100
- RSR = successfully reassembled tasks / completed tasks x 100
- Communication overhead = extra time or bytes due to P2P transfer

## Method
1. Fix controlled variables: model, dataset, hardware settings, decoding.
2. Single-node baseline measured first, same workload, same machine type.
3. Each configuration repeated several times (at least 5; more if variance is high).
4. Report mean, standard deviation, confidence interval; use a suitable statistical test for baseline vs P2P comparison.
5. Simulated network conditions (latency, bandwidth limits) with a controlled tool or the simulator.
6. Save raw data (CSV) plus environment description (hardware, versions).

## Harness (components)
| Component | Job |
|---|---|
| Workload generator | prepares prompt sets by size and sequence length |
| Runner | executes a configuration N times, collects timing from DB metrics |
| Fault injector | kills/slows workers, adds delay, simulates cheaters (shared with 12) |
| Analyzer | tables, charts, statistics |
| Reporter | exports result tables for the thesis |

## Inputs / Outputs
| In | Out |
|---|---|
| orchestrator metrics (chunk_metrics, task_metrics) | raw CSV, summary tables, charts |
| experiment configuration files | reproducible runs |

## Dependencies
- Needs: 02, 04, 08, 03 metrics; uses 06, 09, 10 for E4-E7.
- Tech: Python, pandas-style analysis, plotting library, statistics package.

## Deliverable: Controlled Single-Node vs Multi-Node P2P benchmark dataset (as promised in the proposal).

## Build steps
1. Metrics capture checked on tiny runs.
2. Runner + baseline run.
3. E1 and E2, then E3.
4. E4 to E7.
5. Charts and tables for report.

## Acceptance checks
- Any experiment can be re-run from a config file and gives similar results.
- Raw data includes P_i, D_i, V_i per chunk.
- Honest limitations (small scale, CPU-first) written beside the results.

## Out of scope
Large-scale live-network tests, long-running soak tests.
