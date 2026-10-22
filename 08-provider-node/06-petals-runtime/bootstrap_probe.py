"""Check the actual libp2p handshake inside a provider's Docker network."""
import asyncio


async def reachable_bootstrap(candidates, attempts=2, create_peer=None):
    if create_peer is None:
        from hivemind.p2p import P2P
        create_peer = P2P.create
    errors = []
    for attempt in range(attempts):
        for address in dict.fromkeys(candidates):
            peer = None
            try:
                peer = await create_peer(
                    initial_peers=[address], no_listen=True, dht_mode="client",
                    use_relay=False, use_auto_relay=False, auto_nat=False,
                    nat_port_map=False, startup_timeout=20,
                )
                return [address]
            except Exception as exc:
                errors.append(f"{address}: {str(exc)[-350:]}")
            finally:
                if peer is not None:
                    await peer.shutdown()
        if attempt + 1 < attempts:
            await asyncio.sleep(1)
    raise RuntimeError(
        "Provider container could not complete the coordinator libp2p bootstrap handshake. "
        "Check the coordinator LAN address, TCP 31331 firewall access, and update the provider runtime. "
        + " | ".join(errors[-4:])
    )
