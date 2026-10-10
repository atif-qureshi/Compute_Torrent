import express from "express";
import WebTorrent from "webtorrent";
import fs from "node:fs";
import path from "node:path";
import { createRelayNode, relayStatus } from "./libp2p_network.js";

const app = express();
app.use(express.json({ limit: "1mb" }));
const client = new WebTorrent();
const activeSwarms = new Map();
const root = path.resolve(process.env.SWARM_DATA_DIR || "/data");
const trackers = (process.env.WEBTORRENT_TRACKERS || "wss://tracker.openwebtorrent.com,wss://tracker.webtorrent.dev")
  .split(",").map((value) => value.trim()).filter(Boolean);
const relayPort = Number(process.env.LIBP2P_PORT || 9100);
const relayHost = process.env.LIBP2P_ADVERTISE_HOST || "127.0.0.1";
const safeKey = (value) => typeof value === "string" && /^[A-Za-z0-9._-]{1,140}$/.test(value);

const relay = await createRelayNode({ port: relayPort, advertiseHost: relayHost });
console.log(`ComputeTorrent LAN DHT/relay: ${relay.address}`);

app.post("/create-swarm", (req, res) => {
  const { task_id, files } = req.body || {};
  if (!safeKey(task_id) || !Array.isArray(files) || files.length === 0 || files.length > 64) {
    return res.status(400).json({ error: "Valid task_id and one to 64 relative file paths are required" });
  }
  const filePaths = [];
  for (const relative of files) {
    if (typeof relative !== "string" || path.isAbsolute(relative)) return res.status(400).json({ error: "Paths must be relative to the swarm data directory" });
    const resolved = path.resolve(root, relative);
    if (!resolved.startsWith(root + path.sep) || !fs.existsSync(resolved) || !fs.statSync(resolved).isFile()) {
      return res.status(400).json({ error: "File is missing or outside the swarm data directory" });
    }
    filePaths.push(resolved);
  }
  const old = activeSwarms.get(task_id);
  if (old) return res.json({ task_id, swarm_id: old.infoHash, magnet_uri: old.magnetURI });
  client.seed(filePaths, { private: true, announce: trackers }, (torrent) => {
    activeSwarms.set(task_id, torrent);
    res.json({ task_id, swarm_id: torrent.infoHash, infohash: torrent.infoHash, magnet_uri: torrent.magnetURI });
  });
});

app.post("/teardown-swarm", (req, res) => {
  const { task_id } = req.body || {};
  const torrent = activeSwarms.get(task_id);
  if (!torrent) return res.status(404).json({ error: "Swarm not found" });
  torrent.destroy(() => { activeSwarms.delete(task_id); res.json({ task_id, status: "torn_down" }); });
});

app.get("/swarm-status/:task_id", (req, res) => {
  const torrent = activeSwarms.get(req.params.task_id);
  if (!torrent) return res.status(404).json({ error: "Swarm not found" });
  res.json({ task_id: req.params.task_id, swarm_id: torrent.infoHash, peers: torrent.numPeers,
    uploaded: torrent.uploaded, downloaded: torrent.downloaded, progress: torrent.progress });
});

app.get("/health", (_req, res) => res.json({ status: "ok", active_swarms: activeSwarms.size }));
app.get("/peer-info", (_req, res) => res.json({
  peer_id: relay.peerId,
  multiaddr: relay.address,
  protocol: "/computetorrent/lan/kad/1.0.0",
  relay: "circuit-relay-v2",
  peers: relayStatus(relay.node),
}));
app.get("/network-status", (_req, res) => res.json({
  peer_id: relay.peerId,
  relay: "circuit-relay-v2",
  dht_protocol: "/computetorrent/lan/kad/1.0.0",
  connected_peers: relayStatus(relay.node),
  connected_peer_count: relayStatus(relay.node).length,
}));
const server = app.listen(Number(process.env.PORT || 4001), "0.0.0.0");
console.log(`ComputeTorrent swarm service listening on ${process.env.PORT || 4001}; root=${root}`);

async function shutdown() {
  server.close();
  for (const torrent of activeSwarms.values()) torrent.destroy();
  await relay.node.stop();
  client.destroy(() => process.exit(0));
}
process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
