"""Offline native reverse-reachability regression, no model or public network."""
import json
from hivemind import DHT
from petals.server.reachability import ReachabilityProtocol, check_direct_reachability


def main():
    gateway = DHT(start=True, host_maddrs=["/ip4/127.0.0.1/tcp/31331"],
        use_relay=False, use_auto_relay=False, auto_nat=False, nat_port_map=False)
    service = ReachabilityProtocol.attach_to_dht(gateway, await_ready=True)
    address = str(gateway.get_visible_maddrs()[0])
    options = dict(max_peers=1, host_maddrs=["/ip4/0.0.0.0/tcp/31330"],
        announce_maddrs=["/ip4/127.0.0.1/tcp/31330"], use_relay=False,
        use_auto_relay=False, auto_nat=False, nat_port_map=False, startup_timeout=10)
    try:
        results = {}
        for case, peers in (("legacy_bare_and_authenticated", [address.rsplit("/p2p/", 1)[0], address]),
                            ("authenticated_only", [address])):
            try:
                results[case] = check_direct_reachability(initial_peers=peers, **options)
            except Exception as exc:
                results[case] = type(exc).__name__ + ": " + str(exc)[-500:]
        print("CT_LAN_PROBE " + json.dumps(results), flush=True)
        assert results["authenticated_only"] is True, results
        from route_selection import prepare_route
        def no_relay(_):
            raise AssertionError("LAN incorrectly fell back to WSS")
        request = dict(bootstrap=[address.rsplit("/p2p/", 1)[0], address],
            advertise_maddrs=options["announce_maddrs"], relay={"fixture": "unreachable"})
        selected, handle = prepare_route(request, relay_factory=no_relay)
        assert selected["transport"] == "direct" and handle is None
        assert selected["bootstrap"] == [address]
        print("CT_LAN_SELECTION " + json.dumps({"transport": selected["transport"], "invalid_legacy_candidates_removed": True}), flush=True)
    finally:
        service.shutdown()
        gateway.shutdown()


if __name__ == "__main__":
    main()
