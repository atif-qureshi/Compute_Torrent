"""
Test Docker Sandbox - Simple verification
"""
import sys
sys.path.insert(0, 'src')

from docker_sandbox import DockerSandbox, SandboxConfig

def test_simple():
    print('=== Docker Sandbox Test ===')
    sandbox = DockerSandbox()
    
    # Test 1: Simple echo
    print('\nTest 1: Simple echo command')
    result = sandbox.run_task(
        'test-echo',
        'echo Hello from Docker > /output/result.txt'
    )
    print(f'Status: {result.status.value}')
    print(f'Exit code: {result.exit_code}')
    print(f'Output files: {result.output_files}')
    
    # Test 2: Resource limits
    print('\nTest 2: With resource limits')
    config = SandboxConfig(cpu_limit=1.0, memory_limit='512m', timeout_seconds=10)
    result = sandbox.run_task(
        'test-limits',
        'python -c \"print(Hello); open(\'/output/test.txt\', \'w\').write(\'ok\')\"',
        config
    )
    print(f'Status: {result.status.value}')
    
    # Test 3: Cleanup verification
    print('\nTest 3: Cleanup verification')
    clean = sandbox.verify_cleanup()
    print(f'Cleanup OK: {clean}')
    
    print('\n=== All tests completed ===')

if __name__ == '__main__':
    test_simple()
