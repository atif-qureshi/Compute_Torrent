"""Capacity-aware contiguous transformer-layer placement for distributed inference.

This module plans layer ownership only. The provider activation transport and
Petals-compatible execution runtime are a separate protocol and must be online
before a plan can be dispatched.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


class LayerPlanError(ValueError):
    """Raised when currently eligible peers cannot host every model layer."""


@dataclass(frozen=True)
class LayerSlice:
    peer_id: str
    start_layer: int  # inclusive
    end_layer: int  # exclusive
    device: str
    usable_memory_mib: int

    @property
    def layer_count(self) -> int:
        return self.end_layer - self.start_layer

    def as_dict(self) -> dict[str, Any]:
        return {
            "peer_id": self.peer_id,
            "start_layer": self.start_layer,
            "end_layer": self.end_layer,
            "layer_count": self.layer_count,
            "device": self.device,
            "usable_memory_mib": self.usable_memory_mib,
        }


def _available_memory(profile: dict[str, Any], reserve_ratio: float) -> tuple[int, str]:
    """Estimate memory available to model weights, in MiB.

    CUDA VRAM is used only when the provider reports a working CUDA runtime.
    CPU nodes reserve half of reported free RAM (or 30% of total RAM when a
    heartbeat has no free-RAM field), leaving room for the OS and other work.
    """
    if profile.get("CUDA"):
        # Existing provider profiles report VRAM in MiB; newer profiles may
        # report vram_mib explicitly. Never infer CUDA from a display-adapter name.
        vram_mib = int(profile.get("vram_mib") or profile.get("VRAM") or 0)
        if vram_mib > 0:
            return int(vram_mib * (1.0 - reserve_ratio)), "cuda"

    free_ram = profile.get("free_ram_gb")
    total_ram = profile.get("RAM", 0)
    available_gib = max(0.0, float(free_ram)) if free_ram is not None else max(0.0, float(total_ram) * 0.30)
    return int(available_gib * 1024 * 0.50), "cpu"


def plan_layer_slices(
    total_layers: int,
    peers: Iterable[dict[str, Any]],
    *,
    layer_memory_mib: int,
    reserve_ratio: float = 0.20,
    require_multiple_peers: bool = True,
) -> list[LayerSlice]:
    """Assign complete contiguous layer ranges according to peer capacity.

    Each peer mapping must contain ``peer_id`` and ``profile``. Capacity is
    computed from CUDA VRAM when available, otherwise conservative CPU RAM.
    Peers with ``docker_ok=False``, ``paused=True`` or ``layer_runtime_ready``
    explicitly false are excluded. A caller can set ``layer_runtime_ready``
    only after installing the compatible block-serving runtime.
    """
    if not isinstance(total_layers, int) or total_layers < 1:
        raise LayerPlanError("total_layers must be a positive integer")
    if not isinstance(layer_memory_mib, int) or layer_memory_mib < 1:
        raise LayerPlanError("layer_memory_mib must be a positive integer")
    if not 0.0 <= reserve_ratio < 0.8:
        raise LayerPlanError("reserve_ratio must be between 0 and 0.8")

    capacities: list[tuple[str, int, str, int]] = []
    for peer in peers:
        peer_id = peer.get("peer_id")
        profile = peer.get("profile") or {}
        if not isinstance(peer_id, str) or not peer_id.strip() or not isinstance(profile, dict):
            continue
        if profile.get("docker_ok") is False or profile.get("paused"):
            continue
        if not profile.get("layer_runtime_ready", False):
            continue
        memory_mib, device = _available_memory(profile, reserve_ratio)
        layer_capacity = min(total_layers, memory_mib // layer_memory_mib)
        if layer_capacity > 0:
            capacities.append((peer_id, int(layer_capacity), device, memory_mib))

    capacities.sort(key=lambda item: (-item[1], item[0]))
    remaining = total_layers
    slices: list[LayerSlice] = []
    next_layer = 0

    # Water-fill layer counts in proportion to capacity so a strong machine can
    # host more layers without one peer taking the entire model by default.
    allocations = {peer_id: 0 for peer_id, _, _, _ in capacities}
    while remaining and capacities:
        eligible = [item for item in capacities if allocations[item[0]] < item[1]]
        candidate = min(eligible, key=lambda item: (allocations[item[0]] / item[1], -item[1], item[0])) if eligible else None
        if candidate is None:
            break
        allocations[candidate[0]] += 1
        remaining -= 1

    if remaining:
        have = total_layers - remaining
        raise LayerPlanError(
            f"Insufficient eligible peer memory for {total_layers} layers: "
            f"estimated capacity is {have} layers"
        )

    active = [item for item in capacities if allocations[item[0]]]
    if require_multiple_peers and total_layers > 1 and len(active) < 2:
        raise LayerPlanError("At least two layer-ready peers are required for distributed inference")

    for peer_id, _, device, memory_mib in active:
        count = allocations[peer_id]
        slices.append(LayerSlice(peer_id, next_layer, next_layer + count, device, memory_mib))
        next_layer += count

    if next_layer != total_layers:
        raise LayerPlanError("Layer allocation did not cover the complete model")
    return slices


def choose_underprovisioned_interval(
    total_layers: int,
    block_throughput: list[float],
    max_layers: int,
) -> tuple[int, int]:
    """Choose a contiguous interval containing the weakest-served blocks.

    This follows the Petals paper's server load-balancing objective: a joining
    server should improve the slowest part of the model, and its block range
    must remain contiguous to avoid extra pipeline hops.
    """
    if total_layers < 1 or max_layers < 1:
        raise LayerPlanError("total_layers and max_layers must be positive")
    if len(block_throughput) != total_layers:
        raise LayerPlanError("block_throughput must contain one score per model layer")
    width = min(total_layers, max_layers)
    # A low/zero throughput score means a block is absent or underprovisioned.
    return min(
        ((start, start + width) for start in range(total_layers - width + 1)),
        key=lambda interval: (
            sum(max(0.0, float(value)) for value in block_throughput[interval[0]:interval[1]]) / width,
            interval[0],
        ),
    )


def choose_low_latency_chain(
    total_layers: int,
    servers: Iterable[dict[str, Any]],
    round_trip_ms: dict[tuple[str, str], float],
    *,
    client_rtt_ms: dict[str, float] | None = None,
    beam_width: int = 8,
) -> list[str]:
    """Find a low-latency sequence of peers covering all layers.

    Server entries contain ``peer_id``, ``start_layer``, ``end_layer`` and an
    optional ``compute_ms_per_layer``. Overlapping ranges allow failover and
    alternative paths; peer-to-peer and client-to-peer RTT measurements supply
    the network costs, as in the paper's latency-aware client routing.
    """
    if total_layers < 1 or beam_width < 1:
        raise LayerPlanError("total_layers and beam_width must be positive")
    client_rtt_ms = client_rtt_ms or {}
    valid = []
    for server in servers:
        try:
            peer_id = str(server["peer_id"])
            start = int(server["start_layer"])
            end = int(server["end_layer"])
            compute = max(0.0, float(server.get("compute_ms_per_layer", 0.0)))
        except (KeyError, TypeError, ValueError):
            continue
        if peer_id and 0 <= start < end <= total_layers:
            valid.append((peer_id, start, end, compute))
    if not valid:
        raise LayerPlanError("No layer-serving peers are available")

    # A beam item is (accumulated latency, covered-through layer, peer chain).
    beam: list[tuple[float, int, tuple[str, ...]]] = [(0.0, 0, ())]
    for _ in range(total_layers + 1):
        next_beam: list[tuple[float, int, tuple[str, ...]]] = []
        for cost, covered, chain in beam:
            if covered >= total_layers:
                return list(chain)
            previous = chain[-1] if chain else None
            candidates = [server for server in valid
                          if server[1] <= covered < server[2]
                          and server[0] != previous
                          and server[0] not in chain]
            for peer_id, start, end, compute in candidates:
                new_covered = max(covered, end)
                work_layers = new_covered - covered
                network = (max(0.0, float(client_rtt_ms.get(peer_id, 0.0))) if previous is None
                           else max(0.0, float(round_trip_ms.get((previous, peer_id), 0.0))))
                next_beam.append((cost + network + work_layers * compute,
                                  new_covered, chain + (peer_id,)))
        if not next_beam:
            break
        beam = sorted(next_beam, key=lambda item: (item[0], -item[1], item[2]))[:beam_width]

    completed = [item for item in beam if item[1] >= total_layers]
    if completed:
        return list(min(completed, key=lambda item: item[0])[2])
    raise LayerPlanError("Available layer ranges do not form a complete inference route")
