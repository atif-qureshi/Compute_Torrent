"""Published algorithm fixtures, exhaustive route/oracle comparisons and live bridge contracts."""
import dataclasses
import itertools
import json
import math
import random
import sys
import tempfile
import time
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'orchestrator/app'))
from sun_optimizer import Server,Placement,Session,Infeasible,cg_block_placement,cg_bprr,shortest_route,cache_wait,OnlineAllocator,suggest_request_target,performance_bounds
from sun_milp import joint_milp
import distributed
from sun_runtime import sun_plan,calibration_key,record_calibration,CalibrationUnavailable


def server(name,memory=50,tau=.01,latency=.02,cap=None):
    return Server(name,memory,10,2,tau,{'c':latency},cap)


def exhaustive_routes(servers,placement,layers,client):
    by_id={s.node_id:s for s in servers}
    def walk(boundary,path,cost):
        if boundary==layers:
            yield path,cost
        for p in placement:
            if p.start<=boundary<p.end and client in by_id[p.node_id].latency:
                yield from walk(p.end,path+[p.node_id],cost+by_id[p.node_id].edge_seconds(client,p.end-boundary))
    return list(walk(0,[],0))


class SunAlgorithmTests(unittest.TestCase):
    def test_conservative_capacity_and_replica_placement(self):
        peers=[server('fast',60,.01),server('medium',36,.02),server('slow',48,.03)]
        placement=cg_block_placement(peers,6,1,['c'])
        self.assertEqual([(p.node_id,p.start,p.end) for p in placement],[('fast',0,5),('medium',3,6),('slow',0,4)])
        for p in placement:
            s=next(s for s in peers if s.node_id==p.node_id)
            self.assertLessEqual((p.end-p.start)*(s.block_bytes+s.cache_bytes),s.memory_bytes)
            self.assertGreaterEqual(p.session_capacity,1)
    def test_replica_lexicographic_tie_is_sorted_capacity_then_first_index(self):
        peers=[server('a',48),server('b',24),server('c',24)]
        placement=cg_block_placement(peers,4)
        self.assertEqual([(p.start,p.end) for p in placement],[(0,4),(0,2),(2,4)])
    def test_feasibility_changes_with_target_load(self):
        peers=[server('a',24),server('b',24)]
        cg_block_placement(peers,4,1)
        with self.assertRaises(Infeasible):cg_block_placement(peers,4,2)
    def test_latency_is_amortized_and_changes_server_order(self):
        peers=[server('near',48,.02,.001),server('remote',48,.001,.5)]
        self.assertEqual(cg_block_placement(peers,4)[0].node_id,'near')
    def test_absent_links_are_never_zero_cost(self):
        peers=[Server('a',100,10,2,.01,{})]
        with self.assertRaises(Infeasible):cg_block_placement(peers,4,clients=['c'])
        with self.assertRaises(Infeasible):shortest_route(peers,[Placement('a',0,4,1,1)],4,'c')
    def test_exact_shortest_route_matches_exhaustive_paths(self):
        rng=random.Random(912)
        for _ in range(60):
            peers=[server(str(i),rng.randint(2,6)*12,rng.uniform(.001,.2),rng.uniform(0,.3)) for i in range(4)]
            try:placement=cg_block_placement(peers,6)
            except Infeasible:continue
            route=shortest_route(peers,placement,6,'c')
            oracle=min(cost for _,cost in exhaustive_routes(peers,placement,6,'c'))
            self.assertAlmostEqual(route.per_token_seconds,oracle)
            self.assertEqual(route.stages[0].start,0);self.assertEqual(route.stages[-1].end,6)
            self.assertTrue(all(a.end==b.start for a,b in zip(route.stages,route.stages[1:])))
    def test_prefill_weighted_equation_8(self):
        s=Server('a',100,10,2,.1,{'c':.2},prefill_seconds=.4,prefill_latency={'c':1})
        self.assertAlmostEqual(s.edge_seconds('c',2,4,True),((1+.8)+3*(.2+.2))/4)
        with self.assertRaises(Infeasible):server('b').edge_seconds('c',1,4,True)
    def test_cache_wait_frees_only_enough_sessions_and_sorts_finish_times(self):
        s=server('a',60);p=Placement('a',0,4,2.5,.1)
        sessions=[Session('late',4,20),Session('early',4,12)]
        self.assertEqual(cache_wait(s,p,3,sessions,10),2)
        self.assertEqual(cache_wait(s,p,9,sessions,10),10)
        self.assertTrue(math.isinf(cache_wait(s,p,11,sessions,10)))
    def test_ws_rr_selects_faster_completion_over_low_compute_with_queue(self):
        peers=[server('slow',48,.1,.02),server('fast',48,.01,.02)]
        placement=[Placement(s.node_id,0,4,1,.1) for s in peers]
        route=shortest_route(peers,placement,4,'c',10,{'fast':[Session('busy',4,100)]},0,waiting=True)
        self.assertEqual(route.stages[0].node_id,'slow')
    def test_no_predicted_expiry_releases_real_cache(self):
        allocator=OnlineAllocator([server('a',48)],4)
        _,admitted=allocator.admit('first','c',10,0);self.assertTrue(admitted)
        _,admitted=allocator.admit('second','c',10,100);self.assertFalse(admitted)
        with self.assertRaises(RuntimeError):allocator.reconfigure([server('a',48)])
        allocator.complete('first');self.assertTrue(allocator.admit('second','c',10,100)[1])
    def test_partial_route_is_an_explicit_participant_extension(self):
        peers=[server('a',100,.01),server('b',100,.1)]
        p=cg_block_placement(peers,4)
        with self.assertRaises(Infeasible):shortest_route(peers,p,4,'c',min_nodes=2)
        route=shortest_route(peers,p,4,'c',min_nodes=2,allow_partial=True)
        self.assertEqual([s.end-s.start for s in route.stages],[3,1])
    def test_partial_extension_has_an_explicit_search_budget(self):
        from sun_optimizer import PlanningBudgetExceeded
        peers=[server('a',100),server('b',100)]
        p=cg_block_placement(peers,4)
        with self.assertRaises(PlanningBudgetExceeded):shortest_route(peers,p,4,'c',allow_partial=True,max_transitions=1)
    def test_bound19_target_does_not_claim_infeasible_guarantee(self):
        self.assertIsNone(suggest_request_target([server('a',12)],4,[1,2]))
        target=suggest_request_target([server('a',1000)],4,[2,2,2])
        self.assertEqual(target,2)
    def test_nan_negative_duplicate_and_zero_inputs_rejected(self):
        for value in [float('nan'),float('inf'),-1,0]:
            with self.assertRaises(ValueError):server('x',tau=value)
        with self.assertRaises(ValueError):cg_block_placement([server('x'),server('x')],4)
        with self.assertRaises(ValueError):cg_block_placement([server('x')],4,0)


class MILPTests(unittest.TestCase):
    def test_joint_integer_optimum_matches_exhaustive_placement_and_routes(self):
        peers=[server('a',38,.02,.05),server('b',38,.05,.01)]
        layers=3;clients=['c','c']
        choices=[[(start,start+size) for size in range(1,layers+1) for start in range(layers-size+1)] for _ in peers]
        best=math.inf
        for ranges in itertools.product(*choices):
            p=[Placement(s.node_id,a,b,0,0) for s,(a,b) in zip(peers,ranges)]
            paths=exhaustive_routes(peers,p,layers,'c')
            for selected in itertools.product(paths,repeat=2):
                used={s.node_id:(b-a)*s.block_bytes for s,(a,b) in zip(peers,ranges)}
                for route,_ in selected:
                    boundary=0
                    for node in route:
                        host=next(x for x in p if x.node_id==node);s=next(x for x in peers if x.node_id==node)
                        used[node]+=(host.end-boundary)*s.cache_bytes;boundary=host.end
                if all(used[s.node_id]<=s.memory_bytes for s in peers):best=min(best,sum(cost for _,cost in selected))
        result=joint_milp(peers,layers,clients)
        self.assertTrue(result['optimal']);self.assertAlmostEqual(result['objective_seconds'],best)
        relaxation=joint_milp(peers,layers,clients,relaxation=True)
        self.assertLessEqual(relaxation['objective_seconds'],best+1e-8)
        self.assertIsNone(relaxation['routes'])
    def test_conservative_algorithm_can_be_infeasible_when_joint_problem_is_feasible(self):
        peers=[server(str(i),12) for i in range(4)]
        with self.assertRaises(Infeasible):cg_bprr(peers,2,{'c':2})
        self.assertTrue(joint_milp(peers,2,['c','c'])['optimal'])
    def test_joint_reference_can_include_request_length_and_prefill(self):
        peers=[Server('a',100,10,2,.1,{'c':.2},prefill_seconds=.4,prefill_latency={'c':1})]
        result=joint_milp(peers,2,['c'],output_tokens=[4],include_prefill=True)
        self.assertAlmostEqual(result['objective_seconds'],1+.8+3*(.2+.2))
    def test_paper_figure5_suboptimality_and_theorem_bounds(self):
        # PDF p15: L^2 servers, sm=L*sc, M=(L+1)*sm, R=L^2.
        peers=[Server(str(i),6,2,1,1,{'c':10}) for i in range(4)]
        p,routes=cg_bprr(peers,2,{'c':4})
        self.assertEqual(routes['c'].per_token_seconds,22)
        exact=joint_milp(peers,2,['c']*4)
        self.assertAlmostEqual(exact['objective_seconds']/4,12)
        bound=performance_bounds(peers,2,{'c':4})
        self.assertLessEqual(bound['lower_bound_seconds'],12)
        self.assertGreaterEqual(bound['upper_bound_seconds'],22)
    def test_joint_reference_rejects_unreachable_and_oversized_instances(self):
        with self.assertRaises(Infeasible):joint_milp([Server('a',100,10,2,.1,{})],2,['c'])
        with self.assertRaises(ValueError):joint_milp([server('a')],33,['c'])


def native_peers(now):
    spec=dict(model_id='bigscience/bloom-560m',revision='a'*40,layers=4,hidden_size=1024,min_peers=2,max_peers=4,max_new_tokens=8)
    peers={}
    for i,rate in [('a',20),('b',8)]:
        profile=dict(petals_enabled=True,docker_ok=True,petals_protocol_version=1,petals_network_revision=2,
                     free_ram_gb=4,memory_limit_gb=4,disk_free_gb=10,gpu_free_mib=0,cpu_limit=2,
                     petals_runtime_digest='runtime-v1')
        profile['petals_capacity']=dict(model_id=spec['model_id'],revision=spec['revision'],source='petals-native-v1',
            dtype='float32',quant_type='none',device='cpu',block_bytes=100000000,cache_bytes_per_block=1000000,
            available_bytes=4*2**30,reserve_bytes=256*2**20,capacity_layers=4,inference_rps=rate,measured_at=now)
        peers[i]=dict(profile=profile,state='idle',client_ip='192.168.1.5',server_host='192.168.1.7:8001',network_mode='LAN')
    return spec,peers


class RuntimeBridgeTests(unittest.TestCase):
    def setUp(self):self.now=time.time();self.spec,self.peers=native_peers(self.now)
    def records(self):return {calibration_key(self.spec,n,i,'cpu'):dict(source='gateway-stage-rpc-residual-v1',estimated_round_trip_seconds=.01,measured_at=self.now,transport='direct') for n,i in self.peers.items()}
    def test_measured_bridge_executes_complete_capacity_safe_distinct_ranges(self):
        plan,note=sun_plan(self.spec,self.peers,distributed.provider_capacity,distributed.native_capacity,self.records(),self.now)
        self.assertEqual(len(plan),2);self.assertEqual(plan[0]['start'],0);self.assertEqual(plan[-1]['end'],4)
        self.assertEqual(len({p['node_id'] for p in plan}),len(plan));self.assertTrue(note['participant_constraint_extension'])
        self.assertTrue(all(p['end']-p['start']<=p['capacity_layers'] for p in plan))
    def test_auto_retains_baseline_when_data_missing_strict_mode_rejects(self):
        baseline=distributed.baseline_placement(self.spec,self.peers);note={}
        self.assertEqual(distributed.placement(self.spec,self.peers,calibration={},diagnostics=note),baseline)
        self.assertIn('fallback_reason',note)
        with self.assertRaises(ValueError):distributed.placement(self.spec,self.peers,calibration={},policy='sun')
    def test_auto_gate_retains_equal_baseline_and_uses_lower_cost_sun_candidate(self):
        note={}
        distributed.placement(self.spec,self.peers,calibration=self.records(),diagnostics=note)
        self.assertEqual(note['algorithm'],'baseline')
        self.assertIn('does not improve',note['fallback_reason'])
        self.spec['layers']=24
        for info in self.peers.values():info['profile']['petals_capacity']['capacity_layers']=24
        note={};plan=distributed.placement(self.spec,self.peers,calibration=self.records(),diagnostics=note)
        self.assertEqual(note['algorithm'],'sun_cg_bp_ws_rr_single_request')
        self.assertLess(note['estimated_per_token_seconds'],note['baseline_estimated_per_token_seconds'])
        self.assertEqual(plan[-1]['end'],24)
    def test_stale_network_or_changed_runtime_cannot_be_used(self):
        records=self.records()
        for r in records.values():r['measured_at']-=901
        with self.assertRaises(CalibrationUnavailable):sun_plan(self.spec,self.peers,distributed.provider_capacity,distributed.native_capacity,records,self.now)
        records=self.records();self.peers['a']['profile']['petals_runtime_digest']='other-runtime'
        with self.assertRaises(CalibrationUnavailable):sun_plan(self.spec,self.peers,distributed.provider_capacity,distributed.native_capacity,records,self.now)
    def test_calibration_requires_verified_completion_and_real_decode_samples(self):
        job=dict(id='fixture',spec=self.spec,status='completed',plan=[dict(node_id='a',start=0,end=4,device='cpu',transport='direct')],
                 metrics={'stage_rpc_timings':[dict(node_id='a',blocks=4,phase='decode',seconds=.23) for _ in range(4)]})
        records=record_calibration(job,self.peers,distributed.native_capacity,self.now)
        self.assertEqual(len(records),1)
        self.assertAlmostEqual(next(iter(records.values()))['estimated_round_trip_seconds'],.03)
        job['status']='failed';self.assertEqual(record_calibration(job,self.peers,distributed.native_capacity,self.now),{})
        job['status']='completed';job['metrics']['stage_rpc_timings'][0]['seconds']=.01
        for r in job['metrics']['stage_rpc_timings']:r['seconds']=.01
        pending=record_calibration(job,self.peers,distributed.native_capacity,self.now)
        self.assertEqual(next(iter(pending.values()))['source'],'pending-compute-calibration')
        self.assertIsNone(next(iter(pending.values()))['estimated_round_trip_seconds'])
    def test_two_stage_sizes_fit_processing_and_communication_without_zero_guess(self):
        key=calibration_key(self.spec,'a',self.peers['a'],'cpu')
        previous={key:{'observations':[dict(blocks=2,rpc_seconds=.05,measured_at=self.now-1,transport='direct')]}}
        job=dict(id='fit',spec=self.spec,status='completed',plan=[dict(node_id='a',start=0,end=4,device='cpu',transport='direct')],
                 metrics={'stage_rpc_timings':[dict(node_id='a',blocks=4,phase='decode',seconds=.09) for _ in range(4)]})
        fit=record_calibration(job,self.peers,distributed.native_capacity,self.now,previous)
        self.assertEqual(fit[key]['source'],'gateway-stage-linear-fit-v1')
        self.assertAlmostEqual(fit[key]['estimated_block_seconds'],.02)
        self.assertAlmostEqual(fit[key]['estimated_round_trip_seconds'],.01)
    def test_calibration_persists_without_changing_old_jobs(self):
        with tempfile.TemporaryDirectory() as folder:
            store=distributed.Store(str(Path(folder)/'jobs.sqlite'))
            store.save(dict(id='old',status='completed',spec={}))
            store.save_calibrations(self.records());reopened=distributed.Store(store.path)
            self.assertEqual(reopened.calibrations(),self.records());self.assertEqual(reopened.get('old')['status'],'completed')


class CoordinatorSunFlowTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, telemetry_failure=False):
        import asyncio
        import os
        from types import SimpleNamespace
        from unittest.mock import patch
        from fastapi import FastAPI
        now=time.time();spec,peers=native_peers(now);spec['layers']=24
        for info in peers.values():info['profile']['petals_capacity']['capacity_layers']=24
        manager=SimpleNamespace(active_seeders={n:object() for n in peers},seeder_info=peers)
        starts=[];submitted=[]
        async def send(message,node):
            if message['type']=='petals_start':
                starts.append(message['stage'])
                peers[node]['profile']['petals']=dict(job_id=message['job_id'],status='serving',peer_id=node,network_revision=2,transport='direct')
            return True
        manager.send_to_seeder=send
        async def background(fn,*args):
            if fn is distributed.resolve_revision:return {**args[0],**spec}
            path=args[0]
            if path=='/health':return dict(status='ready',bootstrap=['fixture'],relay_enabled=False)
            if path=='/jobs':submitted.append(args[1]);return dict(status='running')
            if path.startswith('/jobs/'):
                timings=[dict(node_id=p['node_id'],blocks=p['end']-p['start'],phase='decode',
                    seconds=(p['end']-p['start'])/peers[p['node_id']]['profile']['petals_capacity']['inference_rps']+.01)
                    for p in starts for _ in range(4)]
                return dict(status='completed',metrics={'stage_rpc_timings':timings})
            return {}
        with tempfile.TemporaryDirectory() as folder:
            store=distributed.Store(str(Path(folder)/'jobs.sqlite3'))
            store.save_calibrations({calibration_key(spec,n,p,'cpu'):dict(source='gateway-stage-rpc-residual-v1',
                estimated_round_trip_seconds=.01,measured_at=now,transport='direct') for n,p in peers.items()})
            with patch.dict(os.environ,COMPUTETORRENT_JOB_DATA=folder,COMPUTETORRENT_PLANNER='auto'), \
                 patch.object(distributed.asyncio,'to_thread',side_effect=background):
                app=FastAPI();distributed.install(app,manager)
                submit=next(r.endpoint for r in app.routes if r.path=='/api/distributed/jobs' and 'POST' in r.methods)
                listing=next(r.endpoint for r in app.routes if r.path=='/api/distributed/jobs' and 'GET' in r.methods)
                failure=patch.object(distributed.Store,'save_calibrations',side_effect=OSError('fixture telemetry disk full'))
                from contextlib import nullcontext
                with failure if telemetry_failure else nullcontext():
                    await submit(distributed.Upload(content={**spec,'prompt':'fixture'}))
                    for _ in range(100):
                        jobs=await listing()
                        if jobs[0]['status'] in {'failed','completed'}:break
                        await asyncio.sleep(.01)
                    for shutdown in app.router.on_shutdown:await shutdown()
                job=(await listing())[0]
            self.assertEqual(job['status'],'completed',job)
            self.assertEqual(job['optimizer']['algorithm'],'sun_cg_bp_ws_rr_single_request')
            self.assertEqual([(p['start'],p['end']) for p in starts],[(0,23),(23,24)])
            self.assertEqual(len(submitted),1)
            self.assertTrue(all(not p.get('busy') for p in peers.values()))
            if telemetry_failure:self.assertIn('calibration_error',job['optimizer'])
            else:self.assertEqual(len(store.calibrations()),2)
    async def test_actual_job_controller_dispatches_sun_processed_ranges(self):
        await self.exercise()
    async def test_optional_calibration_failure_does_not_fail_a_verified_job(self):
        await self.exercise(True)


if __name__=='__main__':unittest.main()
