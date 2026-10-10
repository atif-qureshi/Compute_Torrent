import docker
import os
import shutil
import time
import logging
from pathlib import Path
from typing import Optional, Dict, List
from dataclasses import dataclass, field
from enum import Enum

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TaskStatus(Enum):
    SUCCESS = 'success'
    FAILED = 'failed'
    TIMEOUT = 'timeout'
    OOM = 'out_of_memory'
    CRASH = 'crash'

@dataclass
class SandboxConfig:
    cpu_limit: float = 2.0
    memory_limit: str = '2g'
    timeout_seconds: int = 300
    enable_gpu: bool = False
    gpu_device_ids: Optional[List[str]] = None

@dataclass
class SandboxResult:
    status: TaskStatus
    output_files: List[str]
    exit_code: int
    runtime_seconds: float
    error_message: Optional[str] = None
    logs: str = ''

class DockerSandbox:
    def __init__(self, workspace_root: str = './workspace'):
        self.workspace_root = Path(workspace_root)
        self.workspace_root.mkdir(exist_ok=True)
        try:
            self.client = docker.from_env()
            logger.info('Docker client initialized')
        except Exception as e:
            logger.error(f'Docker not available: {e}')
            raise

    def create_workspace(self, task_id: str):
        task_workspace = self.workspace_root / task_id
        input_dir = task_workspace / 'input'
        output_dir = task_workspace / 'output'
        
        for d in [task_workspace, input_dir, output_dir]:
            d.mkdir(parents=True, exist_ok=True)
        
        logger.info(f'Workspace created: {task_workspace}')
        return str(input_dir), str(output_dir), str(task_workspace)

    def cleanup_workspace(self, task_workspace: str):
        try:
            if os.path.exists(task_workspace):
                shutil.rmtree(task_workspace)
                logger.info(f'Workspace deleted: {task_workspace}')
        except Exception as e:
            logger.error(f'Workspace cleanup failed: {e}')

    def run_task(self, task_id: str, command: str, config: SandboxConfig = None):
        if config is None:
            config = SandboxConfig()
        
        input_dir, output_dir, task_workspace = self.create_workspace(task_id)
        container = None
        start_time = time.time()
        
        try:
            cfg = {
                'image': 'python:3.10-slim',
                'command': ['sh', '-c', command],
                'volumes': {
                    input_dir: {'bind': '/input', 'mode': 'ro'},
                    output_dir: {'bind': '/output', 'mode': 'rw'}
                },
                'working_dir': '/output',
                'network_mode': 'none',
                'mem_limit': config.memory_limit,
                'nano_cpus': int(config.cpu_limit * 1e9),
                'detach': True,
                'remove': False,
                'user': 'nobody'
            }
            
            logger.info(f'Creating container for task {task_id}')
            container = self.client.containers.create(**cfg)
            
            logger.info(f'Starting container {container.id[:12]}')
            container.start()
            
            result = container.wait(timeout=config.timeout_seconds)
            exit_code = result['StatusCode']
            runtime = time.time() - start_time
            logs = container.logs().decode('utf-8', errors='replace')
            output_files = os.listdir(output_dir) if os.path.exists(output_dir) else []
            
            if exit_code == 0:
                status = TaskStatus.SUCCESS
                error_msg = None
            else:
                status = TaskStatus.FAILED
                error_msg = f'Exit code {exit_code}'
            
            return SandboxResult(status, output_files, exit_code, runtime, error_msg, logs)
        
        except docker.errors.ContainerError as e:
            runtime = time.time() - start_time
            return SandboxResult(TaskStatus.CRASH, [], e.exit_status, runtime, str(e), str(e))
        
        except Exception as e:
            runtime = time.time() - start_time
            if 'timeout' in str(e).lower():
                status = TaskStatus.TIMEOUT
                error_msg = f'Timeout after {config.timeout_seconds}s'
            else:
                status = TaskStatus.FAILED
                error_msg = str(e)
            return SandboxResult(status, [], -1, runtime, error_msg, '')
        
        finally:
            if container:
                try:
                    container.remove(force=True)
                    logger.info(f'Container removed')
                except:
                    pass
            self.cleanup_workspace(task_workspace)

    def verify_cleanup(self):
        try:
            containers = self.client.containers.list(all=True)
            return len(containers) == 0 or all('computetorrent' not in str(c.name) for c in containers)
        except:
            return False

def main():
    sandbox = DockerSandbox()
    cmd = 'echo Hello > /output/result.txt && cat /output/result.txt'
    result = sandbox.run_task('test-001', cmd)
    print(f'Status: {result.status.value}')
    print(f'Files: {result.output_files}')
    print(f'Cleanup OK: {sandbox.verify_cleanup()}')

if __name__ == '__main__':
    main()
