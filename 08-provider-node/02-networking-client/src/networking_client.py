import asyncio
import json
import logging
import time
from enum import Enum
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass
import websockets

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ConnectionState(Enum):
    DISCONNECTED = 'disconnected'
    CONNECTING = 'connecting'
    REGISTERED = 'registered'
    IDLE = 'idle'
    BUSY = 'busy'
    PAUSED = 'paused'

@dataclass
class ClientConfig:
    server_url: str = 'ws://localhost:8000'
    heartbeat_interval: int = 30
    reconnect_delay: int = 5
    max_reconnect_delay: int = 60
    node_id: Optional[str] = None

class NetworkingClient:
    def __init__(self, config: ClientConfig = None):
        self.config = config or ClientConfig()
        self.state = ConnectionState.DISCONNECTED
        self.websocket = None
        self.running = False
        self.heartbeat_task = None
        self.reconnect_delay = self.config.reconnect_delay
        
        # Callbacks
        self.on_task_assign = None
        self.on_verdict_notice = None
        self.on_cancel = None
        self.on_state_change = None
    
    async def connect(self):
        try:
            self.state = ConnectionState.CONNECTING
            logger.info(f'Connecting to {self.config.server_url}')
            
            self.websocket = await websockets.connect(self.config.server_url)
            logger.info('Connected to coordination server')
            return True
        except Exception as e:
            logger.error(f'Connection failed: {e}')
            self.state = ConnectionState.DISCONNECTED
            return False
    
    async def register(self, profile: Dict[str, Any], tier: int):
        if not self.websocket:
            logger.error('Cannot register: not connected')
            return False
        
        register_msg = {
            'type': 'register',
            'profile': profile,
            'tier': tier,
            'node_id': self.config.node_id or f'node-{int(time.time())}'
        }
        
        try:
            await self.websocket.send(json.dumps(register_msg))
            logger.info(f'Sent registration: Tier {tier}')
            self.state = ConnectionState.REGISTERED
            self._notify_state_change()
            return True
        except Exception as e:
            logger.error(f'Registration failed: {e}')
            return False
    
    async def send_heartbeat(self):
        if not self.websocket or self.state == ConnectionState.DISCONNECTED:
            return
        
        heartbeat_msg = {
            'type': 'heartbeat',
            'node_id': self.config.node_id,
            'state': self.state.value
        }
        
        try:
            await self.websocket.send(json.dumps(heartbeat_msg))
            logger.debug('Heartbeat sent')
        except Exception as e:
            logger.error(f'Heartbeat failed: {e}')
            await self.reconnect()
    
    async def send_status_update(self, task_id: str, state: str, 
                                 chunk_id: str = None, progress: int = 0):
        if not self.websocket:
            return
        
        msg = {
            'type': 'status_update',
            'task_id': task_id,
            'state': state,
            'chunk_id': chunk_id,
            'progress_percent': progress
        }
        
        try:
            await self.websocket.send(json.dumps(msg))
            logger.info(f'Status update: {task_id} -> {state}')
        except Exception as e:
            logger.error(f'Status update failed: {e}')
    
    async def send_result(self, task_id: str, chunk_id: str, 
                         output_ref: str, output_hash: str, timings: Dict = None):
        if not self.websocket:
            return
        
        msg = {
            'type': 'result_submit',
            'task_id': task_id,
            'chunk_id': chunk_id,
            'output_ref': output_ref,
            'output_hash': output_hash,
            'timings': timings or {}
        }
        
        try:
            await self.websocket.send(json.dumps(msg))
            logger.info(f'Result submitted: {chunk_id}')
        except Exception as e:
            logger.error(f'Result submission failed: {e}')
    
    async def handle_message(self, message: str):
        try:
            data = json.loads(message)
            msg_type = data.get('type')
            
            if msg_type == 'task_assign':
                logger.info(f'Received task assignment: {data.get("task_id")}')
                self.state = ConnectionState.BUSY
                self._notify_state_change()
                if self.on_task_assign:
                    self.on_task_assign(data)
            
            elif msg_type == 'verdict_notice':
                logger.info(f'Received verdict: {data.get("outcome")}')
                if self.on_verdict_notice:
                    self.on_verdict_notice(data)
            
            elif msg_type == 'cancel':
                logger.warning(f'Task cancelled: {data.get("task_id")}')
                if self.on_cancel:
                    self.on_cancel(data)
            
            elif msg_type == 'register_ack':
                logger.info('Registration acknowledged')
                self.state = ConnectionState.IDLE
                self._notify_state_change()
        
        except json.JSONDecodeError:
            logger.error(f'Invalid message: {message[:100]}')
        except Exception as e:
            logger.error(f'Message handling error: {e}')
    
    async def heartbeat_loop(self):
        while self.running:
            await self.send_heartbeat()
            await asyncio.sleep(self.config.heartbeat_interval)
    
    async def listen(self):
        while self.running:
            try:
                if not self.websocket:
                    await asyncio.sleep(1)
                    continue
                
                message = await asyncio.wait_for(
                    self.websocket.recv(), 
                    timeout=self.config.heartbeat_interval * 2
                )
                await self.handle_message(message)
            
            except asyncio.TimeoutError:
                continue
            except websockets.exceptions.ConnectionClosed:
                logger.warning('Connection closed')
                await self.reconnect()
            except Exception as e:
                logger.error(f'Listen error: {e}')
                await asyncio.sleep(1)
    
    async def reconnect(self):
        logger.info('Attempting reconnection...')
        self.state = ConnectionState.DISCONNECTED
        self._notify_state_change()
        
        if self.websocket:
            try:
                await self.websocket.close()
            except:
                pass
            self.websocket = None
        
        await asyncio.sleep(self.reconnect_delay)
        
        if await self.connect():
            self.reconnect_delay = self.config.reconnect_delay
            logger.info('Reconnected successfully')
        else:
            self.reconnect_delay = min(
                self.reconnect_delay * 2,
                self.config.max_reconnect_delay
            )
            logger.warning(f'Reconnect failed, retrying in {self.reconnect_delay}s')
    
    def _notify_state_change(self):
        if self.on_state_change:
            self.on_state_change(self.state)
    
    async def start(self, profile: Dict, tier: int):
        self.running = True
        
        if not await self.connect():
            logger.error('Initial connection failed')
            return False
        
        if not await self.register(profile, tier):
            logger.error('Registration failed')
            return False
        
        self.heartbeat_task = asyncio.create_task(self.heartbeat_loop())
        asyncio.create_task(self.listen())
        
        logger.info('Networking client started')
        return True
    
    async def stop(self):
        self.running = False
        
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
        
        if self.websocket:
            await self.websocket.close()
        
        logger.info('Networking client stopped')

async def main():
    client = NetworkingClient()
    
    test_profile = {
        'GPU': 'Test GPU',
        'VRAM': 12,
        'CUDA': True,
        'RAM': 16
    }
    
    def on_task(data):
        print(f'Task received: {data.get("task_id")}')
    
    def on_state(state):
        print(f'State: {state.value}')
    
    client.on_task_assign = on_task
    client.on_state_change = on_state
    
    await client.start(test_profile, tier=1)
    
    await asyncio.sleep(60)
    
    await client.stop()

if __name__ == '__main__':
    asyncio.run(main())

