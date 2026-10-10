"""
Mock Coordination Server for ComputeTorrent MVP
Development tool for Phase 1-5 seeder app testing
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import Set
import websockets
from websockets.server import WebSocketServerProtocol

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Connected seeders
connected_seeders: Set[WebSocketServerProtocol] = set()

# Fake task data for testing
FAKE_TASK = {
    "type": "task_assign",
    "task_id": "mock-task-001",
    "chunk_ids": ["chunk-1"],
    "swarm_id": "mock-swarm-001",
    "model_ref": "test-model-v1",
    "task_kind": "inference",
    "chunk_hashes": {"chunk-1": "abc123"},
    "deadline": "2024-12-31T23:59:59Z",
    "model_version_id": "model-v1",
    "adapter_id": None,
    "privacy_level": 1,
    "decoding_settings": {"temperature": 0.7, "max_tokens": 100}
}


async def handle_register(websocket: WebSocketServerProtocol, data: dict):
    """Handle seeder registration"""
    profile = data.get("profile", {})
    tier = data.get("tier")
    
    logger.info(f"🟢 REGISTER received from {websocket.remote_address}")
    logger.info(f"   Profile: GPU={profile.get('GPU')}, VRAM={profile.get('VRAM')}, "
               f"RAM={profile.get('RAM')}, CUDA={profile.get('CUDA')}")
    logger.info(f"   Tier: {tier}")
    
    # Send acknowledgment
    ack = {
        "type": "register_ack",
        "status": "ok",
        "seeder_id": f"mock-seeder-{len(connected_seeders)}",
        "message": "Registration successful (mock server)"
    }
    await websocket.send(json.dumps(ack))
    logger.info(f"   ✅ Sent registration acknowledgment")


async def handle_heartbeat(websocket: WebSocketServerProtocol, data: dict):
    """Handle heartbeat"""
    node_id = data.get("node_id")
    state = data.get("state")
    
    logger.info(f"💓 HEARTBEAT from {node_id}: state={state}")
    
    # Optionally send a fake task after first heartbeat
    # Uncomment to auto-assign tasks:
    # if state == "idle":
    #     await websocket.send(json.dumps(FAKE_TASK))
    #     logger.info(f"   📤 Sent fake task assignment")


async def handle_status_update(websocket: WebSocketServerProtocol, data: dict):
    """Handle task status update"""
    task_id = data.get("task_id")
    state = data.get("state")
    chunk_id = data.get("chunk_id")
    progress = data.get("progress_percent")
    
    logger.info(f"📊 STATUS_UPDATE: task={task_id}, chunk={chunk_id}, "
               f"state={state}, progress={progress}%")


async def handle_result_submit(websocket: WebSocketServerProtocol, data: dict):
    """Handle result submission"""
    task_id = data.get("task_id")
    chunk_id = data.get("chunk_id")
    output_ref = data.get("output_ref")
    output_hash = data.get("output_hash")
    timings = data.get("timings", {})
    
    logger.info(f"✅ RESULT_SUBMIT: task={task_id}, chunk={chunk_id}")
    logger.info(f"   Output: {output_ref}, Hash: {output_hash}")
    logger.info(f"   Timings: download={timings.get('download')}s, "
               f"run={timings.get('run')}s")
    
    # Send fake verdict (for Phase 9 testing)
    verdict = {
        "type": "verdict_notice",
        "task_id": task_id,
        "chunk_id": chunk_id,
        "outcome": "PASS",
        "credits_earned": 10,
        "new_balance": 100,
        "message": "Good work! (mock verdict)"
    }
    await websocket.send(json.dumps(verdict))
    logger.info(f"   📤 Sent fake verdict: +10 credits")


async def handle_message(websocket: WebSocketServerProtocol, message: str):
    """Route incoming messages to appropriate handlers"""
    try:
        data = json.loads(message)
        msg_type = data.get("type")
        
        handlers = {
            "register": handle_register,
            "heartbeat": handle_heartbeat,
            "status_update": handle_status_update,
            "result_submit": handle_result_submit
        }
        
        handler = handlers.get(msg_type)
        if handler:
            await handler(websocket, data)
        else:
            logger.warning(f"❓ Unknown message type: {msg_type}")
            
    except json.JSONDecodeError:
        logger.error(f"❌ Invalid JSON received: {message[:100]}")
    except Exception as e:
        logger.error(f"❌ Error handling message: {e}")


async def handler(websocket: WebSocketServerProtocol):
    """Main WebSocket connection handler"""
    connected_seeders.add(websocket)
    remote = websocket.remote_address
    logger.info(f"🔌 New connection from {remote}")
    logger.info(f"   Total connected: {len(connected_seeders)}")
    
    try:
        async for message in websocket:
            await handle_message(websocket, message)
            
    except websockets.exceptions.ConnectionClosed:
        logger.info(f"🔌 Connection closed: {remote}")
    finally:
        connected_seeders.remove(websocket)
        logger.info(f"   Total connected: {len(connected_seeders)}")


async def send_fake_task_command():
    """Interactive command to send fake task to all connected seeders"""
    while True:
        await asyncio.sleep(30)
        # You can extend this to send tasks on command


async def main():
    """Start the mock coordination server"""
    host = "localhost"
    port = 8000
    
    logger.info("=" * 60)
    logger.info("🚀 Mock Coordination Server Starting")
    logger.info("=" * 60)
    logger.info(f"Listening on: ws://{host}:{port}")
    logger.info(f"Started at: {datetime.now().isoformat()}")
    logger.info("Press Ctrl+C to stop")
    logger.info("=" * 60)
    
    async with websockets.serve(handler, host, port):
        await asyncio.Future()  # Run forever


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n👋 Mock server stopped")
