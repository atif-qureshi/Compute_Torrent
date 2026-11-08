"""Measured single-job bridge to Sun kernels; no invented link costs.

Current workers are ephemeral and the coordinator admits one job. We therefore
materialize only the chosen processed ranges. Hosted replica placement remains
in diagnostics; this is NOT a persistent multi-request deployment of Algorithm 2.
"""
from dataclasses import asdict
import hashlib
import json
import math
import statistics
import time
from sun_optimizer import Server, cg_block_placement, shortest_route, Infeasible


class CalibrationUnavailable(ValueError):
    pass


def calibration_key(spec, node, info, device):
    profile = info.get('profile',{})
    runtime = profile.get('petals_cuda_runtime_digest' if device=='cuda' else 'petals_runtime_digest')
    if not runtime:
        raise CalibrationUnavailable(f'{node}: runtime digest is unreported')
    value = dict(node=node,model_id=spec['model_id'],revision=spec['revision'],device=device,
                 runtime=runtime,cpu_limit=profile.get('cpu_limit'),
                 memory_limit_gb=profile.get('memory_limit_gb'),client_ip=info.get('client_ip'),
                 coordinator=info.get('server_host'),network_mode=info.get('network_mode'))
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def sun_plan(spec, peers, capacity_fn, native_fn, calibration, now=None, baseline_plan=None):
    now = time.time() if now is None else now
    servers, devices, capacities, evidence = [], {}, {}, {}
    for node,info in peers.items():
        cap,device = capacity_fn(spec,info)
        if cap<=0:
            continue
        native = native_fn(spec,info)
        if not native:
            raise CalibrationUnavailable(f'{node}: matching fresh native block measurement is missing')
        key = calibration_key(spec,node,info,device)
        record = calibration.get(key)
        measured_at = record.get('measured_at') if isinstance(record, dict) else None
        if type(measured_at) not in (int,float) or not math.isfinite(measured_at) or not 0 <= now-measured_at <= 900:
            raise CalibrationUnavailable(f'{node}: fresh model-activation link calibration is missing')
        latency = record.get('estimated_round_trip_seconds')
        if (type(latency) not in (int,float) or not math.isfinite(latency) or latency<0
                or record.get('source') not in {'gateway-stage-rpc-residual-v1','gateway-stage-linear-fit-v1'}
                or record.get('transport') not in {'direct','wss'}):
            raise CalibrationUnavailable(f'{node}: invalid activation calibration')
        profile=info['profile']
        memory=(float(profile.get('gpu_free_mib',0))*2**20 if device=='cuda' else
                min(float(profile.get('free_ram_gb',0)),float(profile.get('memory_limit_gb',0)))*2**30)
        budget=int(min(float(native['available_bytes']),memory)-float(native['reserve_bytes']))
        if budget<=0:
            continue
        compute=record.get('estimated_block_seconds',1/float(native['inference_rps']))
        if type(compute) not in (int,float) or not math.isfinite(compute) or compute<=0:
            raise CalibrationUnavailable(f'{node}: invalid calibrated compute cost')
        servers.append(Server(node,budget,int(native['block_bytes']),int(native['cache_bytes_per_block']),
                              compute,{'coordinator':float(latency)},cap))
        devices[node],capacities[node],evidence[node]=device,cap,record
    if len({(s.block_bytes,s.cache_bytes) for s in servers})>1:
        raise CalibrationUnavailable('Worker block/cache byte measurements are incompatible')
    if len(servers)<spec.get('min_peers',2):
        raise Infeasible('Insufficient measured Sun candidates')
    placement=cg_block_placement(servers,spec['layers'],1,['coordinator'])
    parameters=dict(output_tokens=spec.get('max_new_tokens',32),waiting=True,
                    min_nodes=spec.get('min_peers',2),max_nodes=spec.get('max_peers',8))
    constrained=False
    try:
        route=shortest_route(servers,placement,spec['layers'],'coordinator',**parameters)
    except Infeasible:
        # Existing user contract can require multiple PCs even if one can hold
        # the full model. This explicit extension allows a host prefix to be used.
        route=shortest_route(servers,placement,spec['layers'],'coordinator',allow_partial=True,**parameters)
        constrained=True
    plan=[dict(node_id=s.node_id,start=s.start,end=s.end,device=devices[s.node_id],
               capacity_layers=capacities[s.node_id],allocation_weight=1/next(p.amortized_seconds for p in placement if p.node_id==s.node_id),
               allocation_basis='sun_cg_bp_ws_rr_single_request',
               proposed_host_start=s.host_start,proposed_host_end=s.host_end) for s in route.stages]
    diagnostics=dict(algorithm='sun_cg_bp_ws_rr_single_request',target_requests=1,
                     topology='client-centric',objective='estimated_decode_latency',
                     reference_placement=[asdict(p) for p in placement],
                     selected_route=[asdict(s) for s in route.stages],
                     estimated_per_token_seconds=route.per_token_seconds,
                     estimated_generation_seconds=route.completion_estimate_seconds,
                     participant_constraint_extension=constrained,
                     materialization='processed ranges only; no persistent replica pool',
                     latency_source='observed stage-RPC residual or positive linear fit',
                     paper_performance_guarantee_claimed=False,
                     calibration=evidence)
    if baseline_plan is not None:
        by_id={server.node_id:server for server in servers}
        diagnostics['baseline_estimated_per_token_seconds']=sum(
            by_id[stage['node_id']].edge_seconds('coordinator',stage['end']-stage['start'])
            for stage in baseline_plan)
    return plan,diagnostics


def record_calibration(job,peers,native_fn,now=None,previous_records=None):
    """Learn only from successfully verified, coordinator-timed model runs.

    A nonnegative residual is an estimate, not an independent network ping.
    Contradictory compute/RPC measurements are retained as non-routable evidence,
    never clipped to 0. Multiple observed stage sizes can fit a positive line.
    """
    now=time.time() if now is None else now
    if job.get('status')!='completed':
        return {}
    receipt=job.get('receipt',{})
    if receipt.get('verification',{}).get('passed') is not True or receipt.get('canary',{}).get('passed') is not True:
        return {}
    samples=job.get('metrics',{}).get('stage_rpc_timings',[])
    results={}
    previous_records=previous_records or {}
    for stage in job.get('plan',[]):
        node=stage['node_id'];info=peers.get(node)
        if not info:
            continue
        native=native_fn(job['spec'],info)
        if not native:
            continue
        rows=[r for r in samples if r.get('node_id')==node and r.get('phase')=='decode'
              and r.get('blocks')==stage['end']-stage['start']]
        seconds=[r.get('seconds') for r in rows]
        if len(seconds)<3 or any(type(t) not in (int,float) or not math.isfinite(t) or t<=0 for t in seconds):
            continue
        # P95 rather than a best-case latency; does not include verification.
        observed=sorted(seconds)[math.ceil(.95*len(seconds))-1]
        transport=stage.get('transport','direct')
        if transport not in {'direct','wss'}:
            continue
        try:key=calibration_key(job['spec'],node,info,stage['device'])
        except CalibrationUnavailable:continue
        old=previous_records.get(key,{})
        observations=[row for row in old.get('observations',[]) if isinstance(row,dict)
            and type(row.get('measured_at')) in (int,float) and 0<=now-row['measured_at']<=900
            and row.get('transport')==transport
            and type(row.get('blocks')) is int and row['blocks']>0
            and type(row.get('rpc_seconds')) in (int,float) and math.isfinite(row['rpc_seconds']) and row['rpc_seconds']>0]
        observations=(observations+[dict(blocks=stage['end']-stage['start'],rpc_seconds=observed,
                     measured_at=now,transport=transport)])[-8:]
        compute=1/native['inference_rps']
        residual=observed-(stage['end']-stage['start'])*compute
        source='gateway-stage-rpc-residual-v1' if residual>=0 else 'pending-compute-calibration'
        groups={}
        for row in observations:groups.setdefault(row['blocks'],[]).append(row['rpc_seconds'])
        if len(groups)>=2:
            xs=sorted(groups);ys=[statistics.median(groups[x]) for x in xs]
            slope,intercept=statistics.linear_regression(xs,ys)
            if slope>0 and intercept>=0 and all(abs((intercept+slope*x)-y)<=.2*y for x,y in zip(xs,ys)):
                compute,residual,source=slope,intercept,'gateway-stage-linear-fit-v1'
        results[key]=dict(source=source,estimated_round_trip_seconds=residual if residual>=0 else None,
                          estimated_block_seconds=compute if residual>=0 else None,
                          observed_p95_rpc_seconds=observed,native_inference_rps=native['inference_rps'],
                          blocks=stage['end']-stage['start'],sample_count=len(seconds),measured_at=now,
                          transport=transport,job_id=job['id'],observations=observations)
    return results
