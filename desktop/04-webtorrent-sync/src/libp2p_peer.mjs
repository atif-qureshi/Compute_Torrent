import { joinRelayNetwork } from "./libp2p_network.mjs";

const [action, relayAddress] = process.argv.slice(2);
if (action !== "join") {
  console.error("Usage: node libp2p_peer.mjs join <coordinator-multiaddr>");
  process.exit(2);
}

try {
  const node = await joinRelayNetwork(relayAddress || "");
  console.log(JSON.stringify({ type: "libp2p_joined", peer_id: node.peerId.toString(), relay: relayAddress || null }));
  const stop = async () => {
    await node.stop();
    process.exit(0);
  };
  process.on("SIGINT", stop);
  process.on("SIGTERM", stop);
} catch (error) {
  console.error(error.message);
  process.exit(1);
}
