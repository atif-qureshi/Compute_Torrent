# Risks, Open Decisions, MVP Simplifications

## 1. Decisions to make early

| # | Decision | Recommended default |
|---|---|---|
| D1 | Which LLM for MVP | a small CPU-friendly model; same model everywhere |
| D2 | What is a "chunk" | one batch of prompts (batch inference) for MVP; pipeline block split only if time permits |
| D3 | Which scheduling mode first | the simpler one (round-robin style) then add the second |
| D4 | Worker to orchestrator channel | REST + WebSocket; chunks over swarm |
| D5 | Python to Node bridge | local HTTP/IPC API exposed by the p2p service |
| D6 | Determinism for comparing outputs | greedy decoding, fixed seed, same model hash, so replicas are comparable |
| D7 | Privacy levels meaning | Level 1 public prompts, Level 2 split so no seeder sees a full task, Level 3 reserved for trusted seeders only (not to be confused with hardware capability tiers) |

## 2. Honest simplifications (state these in the defense)

- **Verification is a limited MVP:** exact-output replica comparison, optional separate known-answer canary tasks, and a Merkle output-transcript receipt are implemented. Partial re-run, full VeriLLM hidden-state verification, robust canary security, peer prediction, and dispute handling are future work.
- **Orchestrator is central** for control. WebTorrent currently transfers files and uses configured tracker signalling. libp2p provides a separate LAN discovery/relay overlay; it is not a trackerless file-transfer path.
- **CPU-first**, GPU optional; proposal scope says consumer NVIDIA GPUs, so include at least one GPU run if hardware exists.
- **Small scale:** a handful of nodes, simulated churn and latency.

## 3. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Nondeterministic outputs break replica comparison | High | High | greedy decode, fixed seeds, same hardware class per replica pair, tolerance rules in 06 |
| Canary leaks to workers | Medium | High | canaries indistinguishable, orchestrator-private map |
| Swarm slower than plain HTTP for small payloads | High | Medium | measure and report; use swarm for model weights and large chunks |
| Docker overhead dominates timings | Medium | Medium | measure sandbox start separately, reuse warm containers |
| Scope creep | High | High | MVP cut list in README; build order gates |
| Scheduling math from papers hard to reproduce | Medium | Medium | implement simplified version, cite and document differences |

## 4. Proposal document issues to fix before defense

These are inconsistencies noticed in the proposal PDF; verify against the real papers.
- Literature table (section 2.3) and the references list disagree in places: for example [6] is "Sun et al. (2025)" in the table but "Parallax, Yuan et al." in the references; [7] BloomBee shows an arXiv ID in the table but an IEEE Access 2023 entry in references; [8], [9], [12] similar mismatches in titles, authors or IDs.
- Some entries say "details to be confirmed from the paper" ([10], [14], part of the summary table).
- Section 2.5 Research Gap table has an empty cell for incentives work; fill the "ComputeTorrent contribution" cell.
- The architecture image labels (Figure 2) are fine in the PDF; ensure the same figure is used in slides.

## 5. Decisions resolved by the requirements document and the single-builder change

| Topic | Earlier blueprint | Now |
|---|---|---|
| Who builds what | two partners, black boxes | one builder, every module is real |
| Control channel | REST + WebSocket | WebSocket to the Coordination Server (Tracker/Relay), four base messages plus heartbeat |
| Result path | back through the swarm | `result_submit` via the networking client to the server |
| Swarm lifetime | seeders keep serving model weights | per-task private swarm, torn down after the task; seeders leave (WT-4) |
| Container reuse | optional warm reuse | never; fresh container per task (DS-1) |
| Container network | none by default | none; app downloads and mounts the chunk, app returns the result (resolves DS-3 vs WT-5) |
| Tier naming | privacy tiers 1 to 3 | **capability tier** (hardware, 1 or 2) and **privacy level** (1 to 3) |
| Model cache on seeder | not decided | not cached by default so no task files remain; optional setting later |
| LAN peer connectivity | libp2p DHT and Circuit Relay v2 overlay | Implemented separately from WebTorrent; does not provide trackerless file transfer |
| Requestor node | open question (options A and B) | Option A: logic lives in the Coordination Server; option B is future work |
| Profile shape | `{GPU, VRAM, CUDA, RAM}` vs HP-1 asking for CPU cores | base four fields kept exactly; CPU cores and Docker status as extension fields |

## 6. New risks from the requirements document

| Risk | Impact | Mitigation |
|---|---|---|
| NFR-2 "installer provisions everything" is unrealistic on Windows (Docker Desktop, WSL2, virtualization, NVIDIA driver and Container Toolkit) | demo fails on a clean PC | check prerequisites on first run, give guided steps (NFR-3); demo on PCs prepared in advance |
| GPU in Docker on Windows is fiddly | Tier-1 path blocked | keep a CPU run path with a small model; show GPU as a bonus |
| Python app plus Node WebTorrent helper | packaging and process management bugs | bundle the helper, local-only control interface, start and stop with the app |
| One person owns server, seeder app, portal and research | schedule slip | follow docs/BUILD-ORDER.md cut order; stop at M4 at minimum |
| Requirements mention Training and LoRA task types | scope creep against the proposal exclusions | only Inference is implemented; other kinds are a field only |
| "Trackerless" wording vs active implementation | questions at the defense | WebTorrent file transfer uses configured trackers today; libp2p does not move files. Trackerless libp2p data transfer is future work. See docs/FLOW.md |
| Requirements doc example ids (`abc123`, `swarm_abc123`) are placeholders | confusion in code | use UUIDs everywhere (CONTRACTS rule 4) |

## 7. Questions left open for you

1. Do results go **only** through the coordination server, or should large outputs use the swarm too? (Default now: small results over WebSocket/upload, large via swarm.)
2. Is a GPU PC available for demos? If not, treat Tier-1 behavior as simulated and say so in the report.
3. Which LLM and prompt dataset for the benchmark (docs D1)?
