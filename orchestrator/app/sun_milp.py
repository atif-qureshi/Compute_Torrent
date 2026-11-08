"""Small-instance exact joint-placement/routing reference for Sun's equation (6).

Equivalent interval-choice / block-boundary-flow MILP, rather than reproducing
all big-M auxiliaries in equation (13). Optional SciPy/HiGHS; not a live runtime
dependency. Fractional relaxation is a lower bound and is never rounded into a
worker plan. Idle servers may be omitted. Intended for regression/oracle work.
"""
import math
from sun_optimizer import Infeasible, Placement, Route, Stage, integer, unique_servers


def joint_milp(servers, layers, clients, *, relaxation=False, time_limit=10, max_variables=25000,
               output_tokens=None, include_prefill=False):
    integer(layers,'layers')
    if layers > 32 or len(servers) > 12 or not 1 <= len(clients) <= 16:
        raise ValueError('MILP reference is bounded to 32 blocks, 12 servers, 16 requests')
    unique_servers(servers)
    token_counts = [1]*len(clients) if output_tokens is None else list(output_tokens)
    if len(token_counts)!=len(clients):raise ValueError('One output bound per request required')
    for count in token_counts:integer(count,'output_tokens')
    if not math.isfinite(time_limit) or time_limit <= 0:
        raise ValueError('Positive finite solver time limit required')
    try:
        import numpy as np
        from scipy.optimize import milp, Bounds, LinearConstraint
        from scipy.sparse import coo_matrix
    except ImportError as exc:
        raise RuntimeError('Install research optimization requirements for the optional MILP reference') from exc
    costs, choices, arcs = [], [], []
    rows, lower, upper = [], [], []
    def var(cost=0):
        if len(costs) >= max_variables:
            raise ValueError('MILP variable budget exceeded; use CG-BPRR for larger instances')
        costs.append(cost)
        return len(costs)-1
    def constraint(terms,lo,hi):
        rows.append(terms);lower.append(lo);upper.append(hi)
    memory = [dict() for _ in servers]
    for index,s in enumerate(servers):
        host_choices=[]
        # Zero-use servers need not allocate an artificial unused block.
        for count in range(1,min(layers,s.max_blocks or layers,s.memory_bytes//s.block_bytes)+1):
            for start in range(layers-count+1):
                x=var();choice=(index,start,start+count,x);choices.append(choice);host_choices.append(x)
                memory[index][x]=count*s.block_bytes/s.memory_bytes
        constraint({x:1 for x in host_choices},0,1)
    for r,client in enumerate(clients):
        flow=[{} for _ in range(layers+1)]
        for index,start,end,x in choices:
            s=servers[index]
            if client not in s.latency:
                continue
            for boundary in range(start,end):
                blocks=end-boundary
                if (end-start)*s.block_bytes+blocks*s.cache_bytes > s.memory_bytes:
                    continue
                y=var(token_counts[r]*s.edge_seconds(client,blocks,token_counts[r],include_prefill))
                arcs.append((r,index,start,end,boundary,x,y))
                constraint({y:1,x:-1},-math.inf,0)
                flow[boundary][y]=1;flow[end][y]=-1
                memory[index][y]=blocks*s.cache_bytes/s.memory_bytes
        for boundary,terms in enumerate(flow):
            rhs=1 if boundary==0 else -1 if boundary==layers else 0
            constraint(terms,rhs,rhs)
    for terms in memory:
        constraint(terms,-math.inf,1)
    if not costs:
        raise Infeasible("No server can host a model block")
    ri,ci,data=[],[],[]
    for row,terms in enumerate(rows):
        for col,value in terms.items():ri.append(row);ci.append(col);data.append(value)
    matrix=coo_matrix((data,(ri,ci)),shape=(len(rows),len(costs))).tocsc()
    result=milp(np.array(costs),integrality=np.zeros(len(costs)) if relaxation else np.ones(len(costs)),
                bounds=Bounds(np.zeros(len(costs)),np.ones(len(costs))),
                constraints=LinearConstraint(matrix,np.array(lower),np.array(upper)),
                options={'time_limit':time_limit,'mip_rel_gap':0.0})
    if result.x is None:
        raise Infeasible(f'Joint reference has no feasible solution: {result.message}')
    answer=dict(objective_seconds=float(result.fun),optimal=result.status==0,status=int(result.status),
                message=result.message,relaxation=relaxation,variables=len(costs),constraints=len(rows),
                formulation='interval-choice equivalent of Sun equation 6',
                objective='sum of request generation-time estimates' if output_tokens is not None or include_prefill else 'sum of per-token costs')
    if relaxation:
        answer['placement']=None;answer['routes']=None
        return answer
    if any(abs(v-round(v))>1e-5 for v in result.x):
        raise RuntimeError('Solver returned a nonintegral incumbent')
    selected=[c for c in choices if result.x[c[3]]>.5]
    placement=[Placement(servers[i].node_id,start,end,0,0) for i,start,end,_ in selected]
    routes=[]
    memory_by_node={servers[i].node_id:(end-start)*servers[i].block_bytes for i,start,end,_ in selected}
    objective=0.0
    for r,client in enumerate(clients):
        selected_arcs=[a for a in arcs if a[0]==r and result.x[a[-1]]>.5]
        boundary=0;stages=[]
        while boundary<layers:
            eligible=[a for a in selected_arcs if a[4]==boundary]
            if len(eligible)!=1:raise RuntimeError('Invalid MILP route flow')
            _,i,start,end,_,_,_=eligible[0];s=servers[i];cost=s.edge_seconds(client,end-boundary,token_counts[r],include_prefill)
            stages.append(Stage(s.node_id,boundary,end,start,end,cost));objective+=token_counts[r]*cost
            memory_by_node[s.node_id]+=s.cache_bytes*(end-boundary)
            boundary=end
        if len(stages)!=len(selected_arcs):raise RuntimeError('MILP contains extraneous route arcs')
        routes.append(Route(tuple(stages),sum(s.inference_seconds for s in stages),0,
                            sum(s.inference_seconds for s in stages),token_counts[r]*sum(s.inference_seconds for s in stages)))
    for s in servers:
        if memory_by_node.get(s.node_id,0)>s.memory_bytes:raise RuntimeError('MILP memory budget violation')
    if not math.isclose(objective,float(result.fun),rel_tol=1e-6,abs_tol=1e-8):raise RuntimeError('MILP objective reconstruction failed')
    answer.update(placement=placement,routes=routes)
    return answer
