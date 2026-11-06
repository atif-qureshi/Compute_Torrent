import { createLibp2p } from "libp2p";
import { tcp } from "@libp2p/tcp";
import { noise } from "@libp2p/noise";
import { yamux } from "@chainsafe/libp2p-yamux";
import { identify } from "@libp2p/identify";
import { kadDHT, removePublicAddressesMapper } from "@libp2p/kad-dht";
import { circuitRelayTransport } from "@libp2p/circuit-relay-v2";
import { bootstrap } from "@libp2p/bootstrap";
import { mdns } from "@libp2p/mdns";
import { multiaddr } from "@multiformats/multiaddr";

const dht = () => kadDHT({
  protocol: "/computetorrent/lan/kad/1.0.0",
  clientMode: true,
  peerInfoMapper: removePublicAddressesMapper,
});

export async function joinRelayNetwork(bootstrapAddress) {
  const peerDiscovery = [mdns()];
  if (bootstrapAddress) {
    peerDiscovery.unshift(bootstrap({ list: [bootstrapAddress], tagName: "computetorrent-relay", tagValue: 100 }));
  }
  const node = await createLibp2p({
    addresses: { listen: ["/ip4/0.0.0.0/tcp/0", "/p2p-circuit"] },
    transports: [tcp(), circuitRelayTransport()],
    connectionEncrypters: [noise()],
    streamMuxers: [yamux()],
    peerDiscovery,
    services: { identify: identify(), dht: dht() },
  });
  if (bootstrapAddress) {
    try { await node.dial(multiaddr(bootstrapAddress)); } catch (error) {
      await node.stop();
      throw new Error(`Could not connect to the LAN relay at ${bootstrapAddress}: ${error.message}`);
    }
  }
  return node;
}
