# Mock Coordination Server

**Purpose:** Development tool for early seeder app development (Phase 1-5)

## What it does
- Accepts WebSocket connections from seeder apps
- Receives `register` messages
- Sends fake `task_assign` messages
- Prints `status_update` and `result_submit` messages
- Enables seeder development before real server exists

## When to use
- Phase 1-5: Seeder app development and testing
- Testing seeder app changes without running full stack
- Debugging seeder networking issues

## Stack
- Python 3.12+
- websockets library (async WebSocket server)
- Simple console logging

## Files
- `mock_server.py` - Main server implementation
- `requirements.txt` - Python dependencies
- `README.md` - This file

## Usage

```bash
# Install dependencies
cd mock-server
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Run server
python mock_server.py

# Server listens on ws://localhost:8000
```

## Messages Supported

### Receives from seeder:
- `register` - Seeder profile and tier
- `heartbeat` - Periodic keepalive
- `status_update` - Task state changes
- `result_submit` - Task completion

### Sends to seeder:
- `task_assign` - Fake task with test data
- `verdict_notice` - Fake credit award (Phase 9)

## Testing Checklist
- [ ] Server accepts WebSocket connections
- [ ] Server receives and prints register message
- [ ] Server sends fake task_assign
- [ ] Server receives and prints status_update
- [ ] Server receives and prints result_submit
- [ ] Seeder can reconnect after disconnect

## Notes
- This is a development tool only, not part of production
- No database, no persistence
- Sends same fake task to every seeder
- Keep this forever for isolated seeder testing

---

*Created during Phase 0 (Foundations)*