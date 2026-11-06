"""
Integration Test: Networking Client + Hardware Profiler + Mock Server
"""
import asyncio
import sys
sys.path.insert(0, 'src')
sys.path.insert(0, '../01-hardware-profiling/src')

from networking_client import NetworkingClient, ClientConfig
from hardware_profiler import HardwareProfiler

async def test_integration():
    print('=' * 60)
    print('Integration Test: Networking Client + Hardware Profiler')
    print('=' * 60)
    
    # Step 1: Profile hardware
    print('\n[1/4] Profiling hardware...')
    profiler = HardwareProfiler()
    profile_result = profiler.profile()
    
    profile_dict = {
        'GPU': profile_result.profile.GPU,
        'VRAM': profile_result.profile.VRAM,
        'CUDA': profile_result.profile.CUDA,
        'RAM': profile_result.profile.RAM
    }
    
    print(f'Profile: {profile_dict}')
    print(f'Tier: {profile_result.tier}')
    
    # Step 2: Create networking client
    print('\n[2/4] Creating networking client...')
    config = ClientConfig(server_url='ws://localhost:8000')
    client = NetworkingClient(config)
    
    # Step 3: Set up callbacks
    task_received = asyncio.Event()
    
    def on_task_assign(data):
        print(f'\n[TASK RECEIVED]')
        print(f'  Task ID: {data.get(\"task_id\")}')
        print(f'  Chunks: {data.get(\"chunk_ids\")}')
        print(f'  Model: {data.get(\"model_ref\")}')
        task_received.set()
    
    def on_verdict(data):
        print(f'\n[VERDICT]')
        print(f'  Outcome: {data.get(\"outcome\")}')
        print(f'  Credits: {data.get(\"credits_earned\")}')
    
    def on_state_change(state):
        print(f'  State: {state.value}')
    
    client.on_task_assign = on_task_assign
    client.on_verdict_notice = on_verdict
    client.on_state_change = on_state_change
    
    # Step 4: Connect and register
    print('\n[3/4] Connecting to mock server...')
    success = await client.start(profile_dict, profile_result.tier)
    
    if not success:
        print('ERROR: Failed to connect')
        return
    
    print('Connected and registered!')
    
    # Step 5: Simulate task execution
    print('\n[4/4] Waiting for task assignment...')
    
    try:
        await asyncio.wait_for(task_received.wait(), timeout=10)
        
        print('\n[SIMULATING TASK EXECUTION]')
        task_id = 'mock-task-001'
        
        await client.send_status_update(task_id, 'queued')
        await asyncio.sleep(1)
        
        await client.send_status_update(task_id, 'downloading', progress=50)
        await asyncio.sleep(1)
        
        await client.send_status_update(task_id, 'running', progress=75)
        await asyncio.sleep(1)
        
        await client.send_result(
            task_id, 'chunk-1',
            'result.json', 'abc123hash',
            {'download': 2.5, 'run': 5.2}
        )
        
        await client.send_status_update(task_id, 'completed', progress=100)
        
        print('\n[SUCCESS] Task execution simulated')
        
    except asyncio.TimeoutError:
        print('\nNo task received (mock server may not send automatically)')
    
    # Keep running for a bit
    print('\n[HEARTBEAT] Keeping connection alive...')
    await asyncio.sleep(5)
    
    # Cleanup
    print('\n[CLEANUP] Stopping client...')
    await client.stop()
    
    print('\n' + '=' * 60)
    print('Test completed!')
    print('=' * 60)

if __name__ == '__main__':
    print('\nMake sure mock server is running:')
    print('  cd mock-server && python mock_server.py')
    print('\nStarting test in 3 seconds...\n')
    
    import time
    time.sleep(3)
    
    asyncio.run(test_integration())
