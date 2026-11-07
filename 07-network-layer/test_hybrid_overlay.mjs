// Disposable loopback overlay peers; no live services or multicast discovery.
// Ping validates native overlay TCP/Noise only, not Petals RPC or WAN relay.
import test from 'node:test';
import assert from 'node:assert/strict';
import { createRelayNode } from './src/libp2p_network.js';
import { joinRelayNetwork } from '../08-provider-node/04-webtorrent-sync/src/libp2p_network.mjs';

test('provider establishes an authenticated direct overlay connection', { timeout: 20000 }, async () => {
  const relay = await createRelayNode({ port: 0 });
  let provider;
  try {
    const address = relay.node.getMultiaddrs().find(a => a.toString().startsWith('/ip4/127.0.0.1/'));
    assert.ok(address, 'loopback listener must be present');
    provider = await joinRelayNetwork(address.toString(), { discoverLan: false });
    const connection = provider.getConnections().find(c => c.remotePeer.toString() === relay.peerId);
    assert.ok(connection, 'expected relay identity must be connected');
    assert.equal(connection.remoteAddr.toString().includes('/p2p-circuit'), false);
    assert.ok(Number.isFinite(await provider.services.ping.ping(relay.node.peerId)));
  } finally {
    if (provider) await provider.stop();
    await relay.node.stop();
  }
});
