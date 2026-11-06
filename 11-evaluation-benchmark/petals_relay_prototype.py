"""Isolated Phase 3 reverse-stream prototype. No production entry point."""
import asyncio
from contextlib import suppress
from dataclasses import dataclass
import hmac
import ssl
import time
from urllib.parse import urlsplit

from websockets.legacy.client import Connect

CHUNK = 64 * 1024


@dataclass(frozen=True)
class Route:
    route_id: str
    ingress_token: str
    worker_token: str
    expires_at: float
    byte_limit: int


class RelayConnect(Connect):
    def handle_redirect(self, uri):
        raise ValueError("Relay redirects are disabled")


class Relay:
    """A broker for one pre-authorized, single-use TCP stream pair."""

    def __init__(self, route):
        self.route = route
        self.claimed = set()
        self.channels = {}
        self.ready = asyncio.Event()
        self.remaining = route.byte_limit

    async def accept(self, ws, path):
        role = {f"/{self.route.route_id}/ingress": "ingress",
                f"/{self.route.route_id}/worker": "worker"}.get(path)
        token = {"ingress": self.route.ingress_token, "worker": self.route.worker_token}.get(role)
        header = ws.request_headers.get_all("Authorization")
        if (not token or role in self.claimed or len(header) != 1
                or not hmac.compare_digest(header[0].encode(), ("Bearer " + token).encode())
                or time.monotonic() >= self.route.expires_at):
            await ws.close(code=1008, reason="Relay ticket rejected")
            return
        self.claimed.add(role)
        self.channels[role] = ws
        try:
            if len(self.channels) == 2:
                for channel in self.channels.values():
                    await channel.send("ready")
                self.ready.set()
            await asyncio.wait_for(self._forward(ws, role),
                                   timeout=max(0, self.route.expires_at - time.monotonic()))
        except asyncio.TimeoutError:
            await ws.close(code=1008, reason="Relay lease expired")
        finally:
            other = self.channels.get("worker" if role == "ingress" else "ingress")
            if other is not None:
                await other.close()

    async def _forward(self, ws, role):
        await self.ready.wait()
        other = self.channels["worker" if role == "ingress" else "ingress"]
        async for payload in ws:
            if not isinstance(payload, bytes) or not payload or len(payload) > min(CHUNK, self.remaining):
                await ws.close(code=1008, reason="Relay payload rejected")
                return
            self.remaining -= len(payload)
            await other.send(payload)


async def _bridge(ws, reader, writer):
    async def upload():
        while chunk := await reader.read(CHUNK):
            await ws.send(chunk)

    async def download():
        async for payload in ws:
            if not isinstance(payload, bytes):
                raise ValueError("Unexpected relay message")
            writer.write(payload)
            await writer.drain()

    tasks = [asyncio.create_task(upload()), asyncio.create_task(download())]
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        writer.close()
        with suppress(OSError):
            await writer.wait_closed()


def _connect(url, token, tls):
    if (urlsplit(url).scheme != "wss" or not tls.check_hostname
            or tls.verify_mode != ssl.CERT_REQUIRED):
        raise ValueError("Relay requires certificate and hostname verified WSS")
    return RelayConnect(url, ssl=tls, extra_headers={"Authorization": "Bearer " + token},
                   max_size=CHUNK, max_queue=4, open_timeout=5)


async def ingress(url, token, tls, reader, writer):
    try:
        async with _connect(url, token, tls) as ws:
            if await ws.recv() != "ready":
                raise ValueError("Unexpected relay handshake")
            await _bridge(ws, reader, writer)
    finally:
        writer.close()
        with suppress(OSError):
            await writer.wait_closed()


async def worker(url, token, tls, destination):
    # This prototype only dials an operator-configured loopback target.
    if destination[0] not in {"127.0.0.1", "::1"}:
        raise ValueError("Relay worker target must be loopback")
    async with _connect(url, token, tls) as ws:
        if await ws.recv() != "ready":
            raise ValueError("Unexpected relay handshake")
        reader, writer = await asyncio.wait_for(asyncio.open_connection(*destination), timeout=5)
        await _bridge(ws, reader, writer)
