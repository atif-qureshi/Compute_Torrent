"""Reproducible CPU-only planner comparison; no live inference or claimed speedup.

Default inputs are explicitly synthetic. --input accepts a JSON list with the
same schema for externally measured, provenance-documented scenarios.
"""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'orchestrator/app'))
from sun_optimizer import Server,cg_block_placement,shortest_route,performance_bounds,Infeasible
from sun_milp import joint_milp
from distributed import baseline_placement


def fixtures():
    return [dict(name='heterogeneous-compute',measurement_kind='synthetic',layers=24,
                 peers=[dict(id='fast',blocks=24,rps=80,rtt=.005),dict(id='slow',blocks=24,rps=4,rtt=.005)]),
            dict(name='high-latency-third-peer',measurement_kind='synthetic',layers=24,
                 peers=[dict(id='near-a',blocks=16,rps=20,rtt=.005),dict(id='near-b',blocks=16,rps=18,rtt=.005),
                        dict(id='remote',blocks=24,rps=30,rtt=1.5)]),
            dict(name='memory-limited-fast-peer',measurement_kind='synthetic',layers=24,
                 peers=[dict(id='small-fast',blocks=6,rps=80,rtt=.02),dict(id='large-slow',blocks=24,rps=8,rtt=.005)])]


def compare(case):
    layers=case['layers'];servers=[];peers={};now=time.time();sm=64*2**20;sc=8*2**20
    spec=dict(model_id='fixture/model',revision='a'*40,layers=layers,hidden_size=1024,min_peers=2,max_peers=8,max_new_tokens=32)
    for p in case['peers']:
        budget=p['blocks']*(sm+sc);free=(budget+256*2**20)/2**30
        native=dict(model_id=spec['model_id'],revision=spec['revision'],device='cpu',dtype='float32',quant_type='none',
                    block_bytes=sm,cache_bytes_per_block=sc,available_bytes=budget+256*2**20,reserve_bytes=256*2**20,
                    capacity_layers=p['blocks'],inference_rps=p['rps'],measured_at=now,source='petals-native-v1')
        peers[p['id']]=dict(state='idle',profile=dict(petals_enabled=True,docker_ok=True,petals_protocol_version=1,
            petals_network_revision=2,free_ram_gb=free,memory_limit_gb=free,disk_free_gb=10,gpu_free_mib=0,petals_capacity=native))
        servers.append(Server(p['id'],budget,sm,sc,1/p['rps'],{'client':p['rtt']}))
    start=time.perf_counter();baseline=baseline_placement(spec,peers);baseline_overhead=time.perf_counter()-start
    by_id={s.node_id:s for s in servers}
    baseline_cost=sum(by_id[p['node_id']].edge_seconds('client',p['end']-p['start']) for p in baseline)
    start=time.perf_counter();placement=cg_block_placement(servers,layers)
    try:route=shortest_route(servers,placement,layers,'client',min_nodes=2,max_nodes=8)
    except Infeasible:route=shortest_route(servers,placement,layers,'client',min_nodes=2,max_nodes=8,allow_partial=True)
    sun_overhead=time.perf_counter()-start
    return dict(name=case['name'],measurement_kind=case['measurement_kind'],source_inputs=case,
        baseline=dict(plan=baseline,estimated_per_token_seconds=baseline_cost,planner_seconds=baseline_overhead),
        sun=dict(reference_placement=[asdict(p) for p in placement],route=[asdict(s) for s in route.stages],
                 estimated_per_token_seconds=route.per_token_seconds,planner_seconds=sun_overhead,
                 participant_constraint_extension=route.partial_stages),
        actual_inference_seconds=None,physical_peer_test=False)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--input',type=Path)
    parser.add_argument('--output',type=Path,default=ROOT/'runtime/research-papers/sun-comparison.json')
    parser.add_argument('--milp',action='store_true');args=parser.parse_args()
    cases=json.loads(args.input.read_text()) if args.input else fixtures()
    result=dict(description='Planner cost-model comparison, not measured distributed LLM performance',cases=[compare(c) for c in cases])
    if args.milp:
        peers=[Server(str(i),6,2,1,1,{'c':10}) for i in range(4)]
        reference=joint_milp(peers,2,['c']*4)
        result['paper_figure5_reference']=dict(milp_optimal=reference['optimal'],average_per_token_seconds=reference['objective_seconds']/4,
            cg_bprr_per_token_seconds=22,bounds=performance_bounds(peers,2,{'c':4}),measurement_kind='paper-model fixture')
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(args.output)
    for case in result['cases']:print(case['name'],case['baseline']['estimated_per_token_seconds'],case['sun']['estimated_per_token_seconds'])


if __name__=='__main__':main()
