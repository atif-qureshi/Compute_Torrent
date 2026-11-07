"""Job-scoped outbound WSS transport for unmodified Petals TCP streams.

Gateway listeners are loopback-only; workers can dial only the fixed gateway,
and gateway streams can dial only the local worker. No caller-selected targets.
TLS terminates at an operator ingress; native Hivemind TLS remains end to end.
"""
import asyncio
from contextlib import suppress
import hmac
import secrets
import ssl
import struct
import time
from urllib.parse import urlsplit

from websockets.legacy.client import Connect
from websockets.legacy.server import serve

CHUNK = 65536
FRAME = CHUNK + 5
OPEN, DATA, FIN, RESET, READY = range(5)


class NoRedirect(Connect):
    def handle_redirect(self, uri):
        raise ValueError("Relay redirects are disabled")


def relay_url(value):
    parsed = urlsplit(value)
    if (parsed.scheme != "wss" or not parsed.hostname or parsed.username is not None
            or parsed.query or parsed.fragment or parsed.path.rstrip("/") != "/ws/petals-relay"):
        raise ValueError("Configure a certificate-verified wss:// endpoint ending /ws/petals-relay")
    return value.rstrip("/")


class Mux:
    """Bounded TCP multiplexing with explicit half-close and backpressure."""
    def __init__(self, ws, target, *, initiator_even, max_streams=16, byte_limit=2**30):
        self.ws, self.target = ws, target
        self.parity = 0 if initiator_even else 1
        self.next_id = 2 if initiator_even else 1
        self.max_streams, self.remaining = max_streams, byte_limit
        self.streams, self.tasks = {}, set()
        self.send_lock = asyncio.Lock()
        self.closed = False

    async def send(self, op, sid, data=b""):
        async with self.send_lock:
            await self.ws.send(struct.pack("!BI", op, sid) + data)

    def task(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task

    async def attach(self, reader, writer):
        if self.closed or len(self.streams) >= self.max_streams:
            writer.close()
            return
        sid = self.next_id
        self.next_id += 2
        if sid >= 2**32:
            writer.close()
            return
        state = dict(reader=reader, writer=writer, ready=asyncio.Event(), local_fin=False, remote_fin=False)
        self.streams[sid] = state
        try:
            await self.send(OPEN, sid)
            await asyncio.wait_for(state["ready"].wait(), 15)
            if sid in self.streams:
                await self.pump(sid, state)
        except Exception:
            await self.drop(sid, notify=True)

    async def pump(self, sid, state):
        try:
            while data := await state["reader"].read(CHUNK):
                await self.send(DATA, sid, data)
            state["local_fin"] = True
            await self.send(FIN, sid)
            if state["remote_fin"]:
                await self.drop(sid)
        except Exception:
            await self.drop(sid, notify=True)

    async def drop(self, sid, notify=False):
        state = self.streams.pop(sid, None)
        if state:
            state["ready"].set()
            if state["writer"]:
                state["writer"].close()
            if notify and not self.closed:
                with suppress(Exception):
                    await self.send(RESET, sid)

    async def open_remote(self, sid):
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(*self.target), 5)
            if self.closed or sid not in self.streams:
                writer.close()
                return
            state = self.streams[sid]
            state.update(reader=reader, writer=writer)
            await self.send(READY, sid)
            await self.pump(sid, state)
        except Exception:
            await self.drop(sid, notify=True)

    async def run(self):
        try:
            async for raw in self.ws:
                if not isinstance(raw, bytes) or not 5 <= len(raw) <= FRAME:
                    raise ValueError("Invalid relay frame")
                op, sid = struct.unpack("!BI", raw[:5])
                payload = raw[5:]
                self.remaining -= len(payload)
                if self.remaining < 0 or not sid or (op != DATA and payload):
                    raise ValueError("Relay quota or framing violation")
                state = self.streams.get(sid)
                if op == OPEN:
                    if (sid % 2 == self.parity or state is not None
                            or len(self.streams) >= self.max_streams):
                        raise ValueError("Invalid or excessive relay stream")
                    self.streams[sid] = dict(ready=asyncio.Event(), writer=None, local_fin=False, remote_fin=False)
                    self.task(self.open_remote(sid))
                elif state is None:
                    # Late frames after a reset are harmless; unknown opens are not.
                    if op not in {RESET, FIN, DATA, READY}:
                        raise ValueError("Unknown relay operation")
                elif op == READY:
                    state["ready"].set()
                elif op == RESET:
                    await self.drop(sid)
                elif op == DATA:
                    if not state["writer"] or state["remote_fin"] or not payload:
                        raise ValueError("Relay stream is not open")
                    state["writer"].write(payload)
                    await asyncio.wait_for(state["writer"].drain(), 30)
                elif op == FIN:
                    if not state["writer"]:
                        raise ValueError("Relay stream is not open")
                    state["remote_fin"] = True
                    if state["writer"].can_write_eof():
                        state["writer"].write_eof()
                    else:
                        raise ValueError("TCP half-close unavailable")
                    if state["local_fin"]:
                        await self.drop(sid)
                else:
                    raise ValueError("Unknown relay operation")
        finally:
            self.closed = True
            for state in self.streams.values():
                state["ready"].set()
                if state["writer"]:
                    state["writer"].close()
            self.streams.clear()
            for task in tuple(self.tasks):
                task.cancel()
            await asyncio.gather(*tuple(self.tasks), return_exceptions=True)


class Broker:
    def __init__(self, public_url, gateway=("127.0.0.1", 31331), max_leases=32):
        self.public_url = relay_url(public_url)
        self.gateway, self.max_leases = gateway, max_leases
        self.leases = {}

    async def create(self, job_id, node_id, ttl=7200, public_url=None):
        public_url = relay_url(public_url or self.public_url)
        await self.expire()
        if len(self.leases) >= self.max_leases:
            raise ValueError("Relay capacity exhausted")
        route_id, token = secrets.token_hex(16), secrets.token_urlsafe(32)
        route = dict(job_id=job_id, node_id=node_id, token=token,
                     deadline=time.monotonic() + min(max(int(ttl), 10), 7200), mux=None, ws=None)
        async def accept(reader, writer):
            mux = route["mux"]
            if mux is None or time.monotonic() >= route["deadline"]:
                writer.close()
                return
            await mux.attach(reader, writer)
        route["listener"] = await asyncio.start_server(accept, "127.0.0.1", 0, backlog=16)
        self.leases[route_id] = route
        port = route["listener"].sockets[0].getsockname()[1]
        return dict(id=route_id, token=token, url=public_url + "/" + route_id,
                    advertise_maddrs=[f"/ip4/127.0.0.1/tcp/{port}"],
                    expires_at=time.time() + min(max(int(ttl), 10), 7200))

    async def revoke(self, route_id):
        route = self.leases.pop(route_id, None)
        if route:
            route["listener"].close()
            await route["listener"].wait_closed()
            if route["ws"]:
                await route["ws"].close(code=1008, reason="Relay lease ended")

    async def expire(self):
        for key, route in tuple(self.leases.items()):
            if time.monotonic() >= route["deadline"]:
                await self.revoke(key)

    async def accept(self, ws, path):
        key = path.removeprefix("/ws/petals-relay/")
        route = self.leases.get(key)
        headers = ws.request_headers.get_all("Authorization")
        if (not path.startswith("/ws/petals-relay/") or route is None or route["ws"] is not None
                or time.monotonic() >= route["deadline"] or len(headers) != 1
                or not hmac.compare_digest(headers[0], "Bearer " + route["token"])):
            await ws.close(code=1008, reason="Relay access rejected")
            return
        route["ws"] = ws
        route["mux"] = Mux(ws, self.gateway, initiator_even=True)
        try:
            await ws.send(b"CT_RELAY_1")
            await asyncio.wait_for(route["mux"].run(), max(0, route["deadline"] - time.monotonic()))
        except (Exception, asyncio.CancelledError):
            pass
        finally:
            await self.revoke(key)

    async def close(self):
        for key in tuple(self.leases):
            await self.revoke(key)


class Worker:
    def __init__(self, lease, tls=None, target=("127.0.0.1", 31330)):
        parsed = urlsplit(lease["url"])
        relay_url(parsed._replace(path="/ws/petals-relay").geturl())
        if target[0] != "127.0.0.1":
            raise ValueError("Worker forwarding target must be local")
        self.lease, self.target = lease, target
        self.tls = tls or ssl.create_default_context()
        if not self.tls.check_hostname or self.tls.verify_mode != ssl.CERT_REQUIRED:
            raise ValueError("Relay TLS verification is mandatory")
        self.ready = asyncio.Event()
        self.bootstrap_port = None

    async def run(self):
        async with NoRedirect(self.lease["url"], ssl=self.tls,
                extra_headers={"Authorization": "Bearer " + self.lease["token"]},
                max_size=FRAME, max_queue=4, open_timeout=15, close_timeout=5,
                ping_interval=15, ping_timeout=30) as ws:
            if await asyncio.wait_for(ws.recv(), 15) != b"CT_RELAY_1":
                raise ValueError("Unexpected relay protocol")
            mux = Mux(ws, self.target, initiator_even=False)
            async with await asyncio.start_server(mux.attach, "127.0.0.1", 0, backlog=16) as listener:
                self.bootstrap_port = listener.sockets[0].getsockname()[1]
                self.ready.set()
                await mux.run()


async def serve_broker(broker, host="0.0.0.0", port=8003, tls=None):
    return await serve(broker.accept, host, port, ssl=tls, max_size=FRAME,
                       max_queue=4, ping_interval=15, ping_timeout=30, close_timeout=5)
