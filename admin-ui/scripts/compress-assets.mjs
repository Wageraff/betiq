/** Pre-gzip dist для отдачи с Content-Encoding: gzip и фиксированным Content-Length */
import { gzipSync } from "node:zlib";
import { readFileSync, writeFileSync, readdirSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const dist = join(dirname(fileURLToPath(import.meta.url)), "../dist");

function gzipFile(path) {
  const buf = readFileSync(path);
  const gz = gzipSync(buf, { level: 9 });
  writeFileSync(`${path}.gz`, gz);
  console.log(`gzipped ${path.replace(dist + "/", "")} (${buf.length} -> ${gz.length} bytes)`);
}

const index = join(dist, "index.html");
if (existsSync(index)) {
  gzipFile(index);
}

const assets = join(dist, "assets");
if (!existsSync(assets)) {
  process.exit(0);
}

for (const name of readdirSync(assets)) {
  if (!/\.(js|css)$/.test(name)) continue;
  gzipFile(join(assets, name));
}
