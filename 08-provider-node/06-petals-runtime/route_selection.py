"""Select a fresh route at assignment time; never migrate an active KV session."""
import asyncio
import re
import threading

from relay_transport import Worker


class RelayHandle:
    def __init__(self, lease):
        self.client = Worker(lease)
        self.ready = threading.Event()
        self.failed = threading.Event()
        self.loop = None
        self.task = None
        self.error = None
        self.thread = threading.Thread(target=self.run, daemon=True)

    def run(self):
        async def main():
            self.loop = asyncio.get_running_loop()
            self.task = asyncio.create_task(self.client.run())
            ready = asyncio.create_task(self.client.ready.wait())
            try:
                done, _ = await asyncio.wait([self.task, ready], timeout=20,
                                             return_when=asyncio.FIRST_COMPLETED)
                if self.task in done:
                    await self.task
                    raise RuntimeError("Relay closed during startup")
                if ready not in done:
                    raise RuntimeError("Relay connection timed out")
                self.ready.set()
                await self.task
                raise RuntimeError("Relay connection ended")
            finally:
                ready.cancel()
                self.task.cancel()
                await asyncio.gather(self.task, ready, return_exceptions=True)
        try:
            asyncio.run(main())
        except BaseException as exc:
            self.error = type(exc).__name__
            status = getattr(exc, "status_code", None)
            if status is not None:
                self.error += f" (HTTP {status})"
            received = getattr(exc, "rcvd", None)
            if received is not None:
                self.error += f" (close {received.code})"
            self.failed.set()
            self.ready.set()

    def start(self):
        self.thread.start()
        if not self.ready.wait(25) or self.failed.is_set():
            self.stop()
            raise RuntimeError("Authenticated Petals relay could not connect: " + (self.error or "startup timeout")
                               + ". Check the configured relay TLS endpoint and lease.")

    def stop(self):
        if self.loop and self.task and not self.loop.is_closed():
            self.loop.call_soon_threadsafe(self.task.cancel)
        if self.thread.is_alive():
            self.thread.join(timeout=5)


def prepare_route(request, direct_probe=None, relay_factory=RelayHandle):
    """Require positive reverse reachability before preferring LAN over WSS."""
    # Legacy gateway health included bare /tcp endpoints alongside /p2p IDs.
    # Passing even one bare endpoint makes the pinned daemon reject the entire
    # initial_peers list before it can perform any reachability checks.
    peers = request.get("bootstrap", [])
    if not isinstance(peers, list):
        raise ValueError("Gateway bootstrap must be a list")
    authenticated = list(dict.fromkeys(p for p in peers if isinstance(p, str) and re.fullmatch(
        r"/(?:ip4|dns4)/[A-Za-z0-9.-]+/tcp/[0-9]{1,5}/p2p/[A-Za-z0-9]{16,128}(?:/p2p-circuit/p2p/[A-Za-z0-9]{16,128})?", p)))
    if not authenticated:
        raise ValueError("Gateway supplied no identity-qualified Petals bootstrap address")
    request = {**request, "bootstrap": authenticated}
    lease = request.get("relay")
    policy = request.get("network_policy", "auto")
    if policy not in {"auto", "direct", "relay"}:
        raise ValueError("Invalid Petals route policy")
    if not lease:
        if policy == "relay":
            raise ValueError("Relay was requested but not configured")
        return {**request, "transport": "direct"}, None
    if policy != "relay":
        if direct_probe is None:
            from petals.server.reachability import check_direct_reachability
            direct_probe = check_direct_reachability
        try:
            reachable = direct_probe(initial_peers=request["bootstrap"], max_peers=1,
                host_maddrs=["/ip4/0.0.0.0/tcp/31330"], announce_maddrs=request["advertise_maddrs"],
                use_relay=False, use_auto_relay=False, auto_nat=False,
                nat_port_map=False, startup_timeout=10)
        except Exception:
            reachable = False
        if reachable is True:
            return {**request, "transport": "direct"}, None
        if policy == "direct":
            raise RuntimeError("Direct Petals route failed reverse reachability")
    peer_ids = {p.rsplit("/p2p/", 1)[-1] for p in request["bootstrap"] if "/p2p/" in p}
    if len(peer_ids) != 1 or not re.fullmatch(r"[A-Za-z0-9]{16,128}", next(iter(peer_ids), "")):
        raise ValueError("Relay bootstrap requires one expected gateway identity")
    handle = relay_factory(lease)
    handle.start()
    try:
        bootstrap = f"/ip4/127.0.0.1/tcp/{handle.client.bootstrap_port}/p2p/{next(iter(peer_ids))}"
        return {**request, "transport": "wss", "bootstrap": [bootstrap],
                "advertise_maddrs": lease["advertise_maddrs"]}, handle
    except BaseException:
        handle.stop()
        raise
