/** Pre-gzip dist/assets/*.{js,css} для отдачи с Content-Encoding: gzip */
import { gzipSync } from "node:zlib";
import { readFileSync, writeFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

const dir = new URL("../dist/assets", import.meta.url);
let files;
try {
  files = readdirSync(dir);
} catch {
  process.exit(0);
}

for (const name of files) {
  if (!/\.(js|css)$/.test(name)) continue;
  const path = join(dir.pathname, name);
  const buf = readFileSync(path);
  writeFileSync(`${path}.gz`, gzipSync(buf, { level: 9 }));
  console.log(`gzipped ${name} (${buf.length} -> ${gzipSync(buf, { level: 9 }).length} bytes)`);
}
