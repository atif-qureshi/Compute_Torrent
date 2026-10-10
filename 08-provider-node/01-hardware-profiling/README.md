# 08.01 — Hardware Profiling Module (HP-1 to HP-5)

## Purpose
Know what the donor's PC can do and turn it into a profile and a capability tier before talking to the network.

## Requirements
| ID | Requirement | How we meet it |
|---|---|---|
| HP-1 | On launch detect GPU model, VRAM, CUDA availability, CPU cores, total RAM | pynvml for NVIDIA GPU, psutil for CPU/RAM |
| HP-2 | Build `Node Profile` in the exact shape `{GPU, VRAM, CUDA, RAM}` | Base object exactly this; CPU cores and Docker status added as separate extension fields |
| HP-3 | Tier-1 if VRAM at least 8 GB (LLM inference, LoRA); Tier-2 otherwise (preprocessing, light work) | Local rule, applied before registering |
| HP-4 | Re-check on restart and on manual "Refresh" | Profile is recomputed, never cached across launches |
| HP-5 | Show profile and tier in plain language | Example text: "Your PC: RTX 3060, 12 GB VRAM -> Tier 1, eligible for AI inference and LoRA tasks" |

## Inputs / Outputs
| In | Out |
|---|---|
| operating system and drivers | Node Profile, capability tier, plain-language summary, `docker_ok` flag |

## Edge cases to decide
| Case | Handling |
|---|---|
| No NVIDIA GPU or no driver | GPU = none, VRAM = 0, CUDA = false, Tier-2 |
| Several GPUs | Use the one with most VRAM for the profile; note count in extension field |
| VRAM units | Report whole gigabytes (for example 12); tier test uses the value reported by the driver |
| pynvml fails to load | Fall back to Tier-2 and show a helpful message instead of crashing |
| Docker not installed or not running | `docker_ok` false; hand over to app shell (NFR-3) |
| Laptop on battery | Show warning; optional setting to pause seeding on battery |

## Dynamic data (extension, helps the allocator)
Current CPU/RAM/VRAM load and recent online history are sent with heartbeats so module 05 can compute availability.

## Dependencies
- Needs: nothing (standalone). Feeds: 02-networking-client (register), 05-desktop-app-shell (display).
- Tech: Python, psutil, pynvml (nvidia-ml-py).

## Build steps
1. Detect each field alone and print it.
2. Assemble the profile object and tier rule.
3. Plain-language summary text.
4. Refresh action and restart behavior.
5. Edge cases above, tested on a machine without a GPU.

## Acceptance checks
- Real hardware detected correctly on at least one NVIDIA PC and one PC without NVIDIA.
- Tier changes correctly across the 8 GB boundary (test with simulated values).
- App never crashes if the GPU library is missing.
