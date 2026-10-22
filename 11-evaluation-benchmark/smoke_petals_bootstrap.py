"""Real Docker/libp2p bootstrap check without downloading any model weights."""
import json
import re
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def gateway_health():
    values = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key] = value.strip().strip('"')
    request = urllib.request.Request("http://127.0.0.1:8002/health", headers={
        "Authorization": "Bearer " + values["COMPUTETORRENT_API_TOKEN"]})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


def main():
    health = gateway_health()
    assert health.get("status") == "ready" and health.get("network_revision") == 2, health
    # This check runs on the coordinator PC, through Docker Desktop's host
    # publishing path. A remote provider must use the LAN bootstrap unchanged.
    peers = [re.sub(r"^/ip4/[^/]+/tcp/31331", "/dns4/host.docker.internal/tcp/31331", address)
             for address in health["bootstrap"]]
    code = """import asyncio,json,sys
from bootstrap_probe import reachable_bootstrap
async def check():
    peers=json.loads(sys.argv[1])
    results=await asyncio.gather(reachable_bootstrap(peers), reachable_bootstrap(peers))
    print(json.dumps({'real_libp2p_handshakes':len(results),'bootstrap':results}),flush=True)
asyncio.run(check())
"""
    subprocess.run(["docker", "run", "--rm", "--name", "ct-bootstrap-check",
                    "--label", "computetorrent.role=network-check", "--memory", "2g", "--cpus", "2",
                    "--add-host", "host.docker.internal:host-gateway", "computetorrent-petals:local",
                    "python", "-u", "-c", code, json.dumps(peers)], check=True, timeout=180)


if __name__ == "__main__":
    main()
