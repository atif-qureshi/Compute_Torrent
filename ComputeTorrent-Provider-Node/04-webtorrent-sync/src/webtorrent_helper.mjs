import WebTorrent from "webtorrent";
import fs from "node:fs/promises";
import path from "node:path";

const [action, magnet, destination] = process.argv.slice(2);
if (action !== "download" || !magnet?.startsWith("magnet:?xt=urn:btih:") || !destination) {
  console.error("Usage: node webtorrent_helper.mjs download <magnet-uri> <workspace-dir>");
  process.exit(2);
}
const dir = path.resolve(destination);
await fs.mkdir(dir, { recursive: true });
const client = new WebTorrent();
const timer = setTimeout(() => { console.error("WebTorrent download timed out"); client.destroy(() => process.exit(3)); }, 1800000);
client.add(magnet, { path: dir }, (torrent) => {
  torrent.on("download", () => process.stderr.write(`${Math.round(torrent.progress * 100)}% ${torrent.downloadSpeed}\n`));
  torrent.on("error", (error) => { console.error(error.message); clearTimeout(timer); client.destroy(() => process.exit(4)); });
  torrent.on("done", async () => {
    const metadata = torrent.files.map((file) => ({ name: file.name, length: file.length }));
    await fs.writeFile(path.join(dir, ".computetorrent-manifest.json"), JSON.stringify(metadata));
    clearTimeout(timer);
    client.destroy(() => process.exit(0));
  });
});
