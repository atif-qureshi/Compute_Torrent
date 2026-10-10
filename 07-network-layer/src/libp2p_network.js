import { createLibp2p } from "libp2p";
import { tcp } from "@libp2p/tcp";
import { noise } from "@libp2p/noise";
import { yamux } from "@chainsafe/libp2p-yamux";
import { identify } from "@libp2p/identify";
import { kadDHT, removePublicAddressesMapper } from "@libp2p/kad-dht";
import { circuitRelayServer, circuitRelayTransport } from "@libp2p/circuit-relay-v2";
import { bootstrap } from "@libp2p/bootstrap";
import { mdns } from "@libp2p/mdns";
import { multiaddr } from "@multiformats/multiaddr";

const DHT_PROTOCOL = "/computetorrent/lan/kad/1.0.0";
const dht = (clientMode) => kadDHT({
  protocol: DHT_PROTOCOL,
  clientMode,
  peerInfoMapper: removePublicAddressesMapper,
});

export async function createRelayNode({ port = 9100, advertiseHost = "127.0.0.1" } = {}) {
  const node = await createLibp2p({
    addresses: { listen: [`/ip4/0.0.0.0/tcp/${port}`] },
    transports: [tcp(), circuitRelayTransport()],
    connectionEncrypters: [noise()],
    streamMuxers: [yamux()],
    services: {
      identify: identify(),
      dht: dht(false),
      circuitRelay: circuitRelayServer({ maxReservations: 500 }),
    },
  });
  const peerId = node.peerId.toString();
  const address = `/ip4/${advertiseHost}/tcp/${port}/p2p/${peerId}`;
  return { node, peerId, address };
}

export async function joinRelayNetwork(bootstrapAddress) {
  const peerDiscovery = [mdns()];
  if (bootstrapAddress) {
    // Use an explicit coordinator as the LAN DHT bootstrap and circuit relay.
    peerDiscovery.unshift(bootstrap({ list: [bootstrapAddress], tagName: "computetorrent-relay", tagValue: 100 }));
  }
  const node = await createLibp2p({
    addresses: { listen: ["/ip4/0.0.0.0/tcp/0", "/p2p-circuit"] },
    transports: [tcp(), circuitRelayTransport()],
    connectionEncrypters: [noise()],
    streamMuxers: [yamux()],
    peerDiscovery,
    services: { identify: identify(), dht: dht(true) },
  });
  if (bootstrapAddress) {
    try { await node.dial(multiaddr(bootstrapAddress)); } catch (error) {
      await node.stop();
      throw new Error(`Could not connect to the LAN relay at ${bootstrapAddress}: ${error.message}`);
    }
  }
  return node;
}

export function relayStatus(node) {
  return node.getConnections().map((connection) => ({
    peer_id: connection.remotePeer.toString(),
    address: connection.remoteAddr.toString(),
    relayed: !connection.direct,
  }));
}
