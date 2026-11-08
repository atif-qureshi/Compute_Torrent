"""Sun et al. CG-BPRR/CG-BP and WS-RR, using zero-based half-open blocks.

Source: Optimizing Resource Allocation for Geographically-Distributed Inference
by Large Language Models, Algorithms 1/2, equations 3/4/8/14/15/18/20/21.
Independent implementation. Seconds and bytes throughout. No missing link is free.
The paper's guarantees require its assumptions; CPU/heterogeneous-byte inputs and
minimum-participant/partial-stage constraints are ComputeTorrent extensions.
"""
from dataclasses import dataclass
from fractions import Fraction
import math
import statistics
import threading


class Infeasible(ValueError):
    pass


class PlanningBudgetExceeded(Infeasible):
    pass


def positive(value, name, allow_zero=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 or (value == 0 and not allow_zero):
        raise ValueError(f"{name} must be a finite {'nonnegative' if allow_zero else 'positive'} number")
    return value


def integer(value, name, minimum=1):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


@dataclass(frozen=True)
class Server:
    node_id: str
    memory_bytes: int
    block_bytes: int
    cache_bytes: int
    decode_seconds: float
    latency: dict
    max_blocks: int | None = None
    prefill_seconds: float | None = None
    prefill_latency: dict | None = None

    def __post_init__(self):
        if not isinstance(self.node_id, str) or not self.node_id:
            raise ValueError("server identity is required")
        for name in ('memory_bytes', 'block_bytes', 'cache_bytes'):
            integer(getattr(self, name), name)
        positive(self.decode_seconds, 'decode_seconds')
        if not isinstance(self.latency, dict):
            raise ValueError('latency must map client identities to measured seconds')
        if any(not isinstance(key,str) or not key for key in self.latency):
            raise ValueError('Client identities must be nonempty strings')
        for value in self.latency.values():
            positive(value, 'latency', allow_zero=True)
        if self.max_blocks is not None:
            integer(self.max_blocks, 'max_blocks')
        if self.prefill_seconds is not None:
            positive(self.prefill_seconds, 'prefill_seconds')
        if self.prefill_latency is not None:
            for value in self.prefill_latency.values():
                positive(value, 'prefill_latency', allow_zero=True)

    def capacity(self, layers, requests):
        integer(layers, 'layers'); integer(requests, 'requests')
        return min(layers, self.max_blocks or layers,
                   self.memory_bytes // (self.block_bytes + requests * self.cache_bytes))

    def edge_seconds(self, client, blocks, output_tokens=1, include_prefill=False):
        # Equation 4 or the request-length-weighted Equation 8.
        if client not in self.latency:
            raise Infeasible(f'No measured client link for {client} -> {self.node_id}')
        integer(blocks, 'processed blocks'); integer(output_tokens, 'output_tokens')
        decode = self.latency[client] + self.decode_seconds * blocks
        if not include_prefill:
            return decode
        if self.prefill_seconds is None or self.prefill_latency is None or client not in self.prefill_latency:
            raise Infeasible(f'No matching prefill calibration for {self.node_id}')
        prefill = self.prefill_latency[client] + self.prefill_seconds * blocks
        return (prefill + (output_tokens - 1) * decode) / output_tokens


@dataclass(frozen=True)
class Placement:
    node_id: str
    start: int
    end: int
    session_capacity: float
    amortized_seconds: float


@dataclass(frozen=True)
class Stage:
    node_id: str
    start: int
    end: int
    host_start: int
    host_end: int
    inference_seconds: float
    wait_seconds: float = 0.0


@dataclass(frozen=True)
class Route:
    stages: tuple
    per_token_seconds: float
    wait_seconds: float
    penalized_seconds: float
    completion_estimate_seconds: float
    partial_stages: bool = False


@dataclass(frozen=True)
class Session:
    request_id: str
    blocks: int
    finish_at: float


def unique_servers(servers):
    result = {s.node_id: s for s in servers}
    if len(result) != len(servers):
        raise ValueError('Duplicate server identity')
    return result


def cg_block_placement(servers, layers, requests=1, clients=None):
    """Algorithm 1 lines 1-8, including overlap and lexicographic replica ties."""
    integer(layers, 'layers'); integer(requests, 'requests')
    unique_servers(servers)
    clients = tuple(clients) if clients is not None else tuple(sorted({c for s in servers for c in s.latency}))
    if not clients:
        raise Infeasible('No measured clients')
    candidates = []
    for server in servers:
        count = server.capacity(layers, requests)
        if count == 0 or any(c not in server.latency for c in clients):
            continue
        amortized = server.decode_seconds + max(server.latency[c] for c in clients) / count
        sessions = Fraction(server.memory_bytes - server.block_bytes * count, server.cache_bytes * count)
        candidates.append((amortized, server.node_id, count, sessions))
    if sum(c[2] for c in candidates) < layers:
        raise Infeasible('CG-BP conservative capacities do not cover the model at this request target')
    candidates.sort()
    dummy = max(c[0] for c in candidates) * 2 + 1
    capacity = [Fraction(0)] * layers
    cost = [dummy * requests] * layers
    placement = []
    for amortized, node, count, sessions in candidates:
        windows = range(layers - count + 1)
        if any(c < requests for c in capacity):
            feasible = [a for a in windows if any(c < requests for c in capacity[a:a+count])]
            start = min(feasible, key=lambda a: (-sum(cost[a:a+count]), a))
        else:
            # The text after Algorithm 1 specifies sorted(C_a,...,C_a+m-1).
            start = min(windows, key=lambda a: (tuple(sorted(capacity[a:a+count])), a))
        for block in range(start, start + count):
            served = min(max(Fraction(requests) - capacity[block], 0), sessions)
            cost[block] -= (dummy - amortized) * float(served)
            capacity[block] += sessions
        placement.append(Placement(node, start, start+count, float(sessions), amortized))
    if any(c < requests for c in capacity):
        raise Infeasible('CG-BP left an uncovered block')
    return placement


def cache_wait(server, placement, blocks, sessions, now):
    """Equation 20. Predictions do not release actual memory reservations."""
    integer(blocks, 'processed blocks')
    if placement.node_id != server.node_id:
        raise ValueError('Cache state must match the host identity')
    positive(now, 'now', allow_zero=True)
    available = server.memory_bytes - server.block_bytes * (placement.end - placement.start)
    needed = blocks * server.cache_bytes
    if available < needed:
        return math.inf
    pending = []
    for session in sessions:
        integer(session.blocks, 'session blocks')
        positive(session.finish_at, 'session finish time', allow_zero=True)
        pending.append((max(0.0, session.finish_at - now), session.blocks * server.cache_bytes))
    free = available - sum(memory for _, memory in pending)
    if free >= needed:
        return 0.0
    for remaining, memory in sorted(pending):
        free += memory
        if free >= needed:
            return remaining
    return math.inf


def shortest_route(servers, placement, layers, client, output_tokens=1, sessions=None,
                   now=0.0, waiting=False, min_nodes=1, max_nodes=None,
                   allow_partial=False, include_prefill=False, max_transitions=250000):
    """Lemma 3.1 DAG shortest path; WS-RR uses wait + tokens*edge cost.

    Exact published mode consumes the rest of the selected host interval.
    allow_partial and participant bounds are explicit single-job engineering
    extensions; only that bounded mode tracks a visited-server bitmask.
    """
    integer(layers, 'layers'); integer(output_tokens, 'output_tokens'); integer(min_nodes, 'min_nodes')
    by_id = unique_servers(servers)
    if len({p.node_id for p in placement}) != len(placement):
        raise ValueError('A server may host only one contiguous interval')
    for p in placement:
        if (p.node_id not in by_id or type(p.start) is not int or type(p.end) is not int
                or not 0 <= p.start < p.end <= layers):
            raise ValueError('Invalid hosted interval')
    max_nodes = len(placement) if max_nodes is None else integer(max_nodes, 'max_nodes')
    if max_nodes < min_nodes:
        raise Infeasible('Maximum participants is below the minimum')
    if allow_partial and len(placement) > 12:
        raise PlanningBudgetExceeded('Partial-stage routing is bounded to 12 servers')
    integer(max_transitions,'max_transitions')
    transitions = 0
    sessions = sessions or {}
    # (next block, visited mask or hop count) -> (penalized cost, route)
    states = {(0, 0): (0.0, ())}
    for boundary in range(layers):
        for (position, key), (score, route) in list(states.items()):
            if position != boundary or len(route) >= max_nodes:
                continue
            for index, p in enumerate(placement):
                if not p.start <= boundary < p.end or (allow_partial and key & (1 << index)):
                    continue
                server = by_id[p.node_id]
                ends = range(boundary+1, p.end+1) if allow_partial else (p.end,)
                for end in ends:
                    transitions += 1
                    if transitions > max_transitions:
                        raise PlanningBudgetExceeded('Route planning transition budget exceeded')
                    blocks = end - boundary
                    try:
                        inference = server.edge_seconds(client, blocks, output_tokens, include_prefill)
                    except Infeasible:
                        continue
                    wait = cache_wait(server, p, blocks, sessions.get(p.node_id, ()), now) if waiting else 0.0
                    if not math.isfinite(wait):
                        continue
                    edge = (wait + output_tokens * inference) if waiting else inference
                    stage = Stage(p.node_id, boundary, end, p.start, p.end, inference, wait)
                    next_key = key | (1 << index) if allow_partial else len(route)+1
                    state = (end, next_key)
                    candidate = (score + edge, route + (stage,))
                    old = states.get(state)
                    tie = lambda item: (item[0], tuple((s.node_id,s.start,s.end) for s in item[1]))
                    if old is None or tie(candidate) < tie(old):
                        states[state] = candidate
    completed = [v for (boundary,_),v in states.items() if boundary == layers and min_nodes <= len(v[1]) <= max_nodes]
    if not completed:
        raise Infeasible('No complete feasible route with known links and participant constraints')
    score, stages = min(completed, key=lambda v: (v[0], tuple((s.node_id,s.start,s.end) for s in v[1])))
    inference = sum(s.inference_seconds for s in stages)
    wait = max((s.wait_seconds for s in stages), default=0.0)
    return Route(stages, inference, wait, score, wait + output_tokens * inference, allow_partial)


def cg_bprr(servers, layers, requests_by_client):
    """Algorithm 1, with shared conservative placement and one route per client."""
    if not requests_by_client:
        raise ValueError('At least one request is required')
    for count in requests_by_client.values():
        integer(count, 'request count')
    placement = cg_block_placement(servers, layers, sum(requests_by_client.values()), requests_by_client)
    routes = {client: shortest_route(servers, placement, layers, client) for client in requests_by_client}
    return placement, routes


def suggest_request_target(servers, layers, arrivals):
    """Paper section 3.3.1 mean+std policy, capped by sufficient bound (19).

    A bound below one is reported, not rounded up into a false guarantee.
    The bound is sufficient, not necessary; explicit targets use exact Eq.18.
    """
    integer(layers, 'layers')
    if not servers or not arrivals:
        raise ValueError('Servers and observed arrival counts are required')
    for count in arrivals:
        integer(count, 'arrival count', 0)
    if len({(s.block_bytes,s.cache_bytes) for s in servers}) != 1:
        raise ValueError('Equation 19 assumes common per-block/cache memory sizes')
    sm, sc = servers[0].block_bytes, servers[0].cache_bytes
    bound = math.floor((sum(s.memory_bytes for s in servers) - sm*(layers+len(servers))) / (sc*(layers+len(servers))))
    if bound < 1:
        return None
    return min(max(1,math.ceil(statistics.mean(arrivals)+statistics.pstdev(arrivals))),bound)


def performance_bounds(servers, layers, requests_by_client):
    """Theorem 3.5 (17) and Appendix B.4 (35), under common-size assumptions."""
    if not requests_by_client or any(s.max_blocks is not None for s in servers):
        raise ValueError('Paper bounds require requests and unmodified block-count domains')
    if len({(s.block_bytes,s.cache_bytes) for s in servers})!=1:
        raise ValueError('Paper bounds require common block/cache sizes')
    placement=cg_block_placement(servers,layers,sum(requests_by_client.values()),requests_by_client)
    by_id=unique_servers(servers)
    count,total,upper=0,0,0.0
    for p in placement:
        count=p.end-p.start;total+=count;upper+=p.amortized_seconds*count
        if total>=layers:
            upper-=by_id[p.node_id].decode_seconds*(total-layers)
            break
    lower=0.0
    for client,requests in requests_by_client.items():
        integer(requests,'request count')
        candidates=[]
        for server in servers:
            count=server.capacity(layers,1)
            if count and client in server.latency:
                candidates.append((server.decode_seconds+server.latency[client]/count,server.node_id,count))
        remaining=layers;cost=0.0
        for amortized,_,count in sorted(candidates):
            used=min(remaining,count);cost+=used*amortized;remaining-=used
            if not remaining:break
        if remaining:raise Infeasible('No feasible lower-bound relaxation')
        lower+=requests*cost
    return dict(lower_bound_seconds=lower/sum(requests_by_client.values()),upper_bound_seconds=upper,
                assumptions='common block/cache sizes; complete client costs; paper capacity model')


class OnlineAllocator:
    """Algorithm 2 decision/admission engine, not a remote worker orchestrator.

    Placement changes are explicit and forbidden with live KV reservations.
    Completion-time predictions inform WS-RR but never silently free caches.
    A waiting proposal must be retried after real completion/progress updates.
    """
    def __init__(self, servers, layers, target_requests=1, clients=None):
        self._lock = threading.RLock()
        self.servers = list(servers)
        self.layers = layers
        self.placement = cg_block_placement(servers, layers, target_requests, clients)
        self.active = {}

    def propose(self, client, output_tokens, now):
        with self._lock:
            sessions = {}
            for record in self.active.values():
                for stage in record['route'].stages:
                    sessions.setdefault(stage.node_id, []).append(Session(record['id'],stage.end-stage.start,record['finish_at']))
            return shortest_route(self.servers,self.placement,self.layers,client,output_tokens,
                                  sessions,now,waiting=True)

    def admit(self, request_id, client, output_tokens, now):
        with self._lock:
            if not isinstance(request_id,str) or not request_id:
                raise ValueError('Nonempty request identity required')
            if request_id in self.active:
                raise ValueError('Duplicate active request')
            route = self.propose(client,output_tokens,now)
            by_id = unique_servers(self.servers)
            hosts = {p.node_id:p for p in self.placement}
            if route.wait_seconds > 0:
                return route, False
            # Real reservation check: estimated expiry never means cache release.
            for stage in route.stages:
                server = by_id[stage.node_id]
                used = sum((s.end-s.start)*server.cache_bytes for r in self.active.values()
                           for s in r['route'].stages if s.node_id==stage.node_id)
                required = (hosts[stage.node_id].end-hosts[stage.node_id].start)*server.block_bytes + used + (stage.end-stage.start)*server.cache_bytes
                if required > server.memory_bytes:
                    return route, False
            self.active[request_id] = dict(id=request_id,route=route,finish_at=now+route.completion_estimate_seconds)
            return route, True

    def complete(self, request_id):
        with self._lock:
            self.active.pop(request_id,None)

    def reconfigure(self, servers, target_requests=1, clients=None):
        with self._lock:
            if self.active:
                raise RuntimeError('Cannot re-place blocks while live KV sessions exist')
            placement = cg_block_placement(servers,self.layers,target_requests,clients)
            self.servers,self.placement = list(servers),placement
