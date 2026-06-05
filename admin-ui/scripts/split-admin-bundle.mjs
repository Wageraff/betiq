/**
 * Разбить бандл на части <25 KB и загрузить через fetch (нельзя резать по <script src>).
 */
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const CHUNK_BYTES = 18_000;
const dist = join(dirname(fileURLToPath(import.meta.url)), "../dist");
const indexPath = join(dist, "index.html");
const chunksDir = join(dist, "c");

let html = readFileSync(indexPath, "utf8");
const m = html.match(/<script>([\s\S]*?)<\/script>/);
if (!m) {
  console.error("split-admin-bundle: no inline <script> found");
  process.exit(1);
}

const code = m[1];
mkdirSync(chunksDir, { recursive: true });

const parts = [];
for (let i = 0; i < code.length; i += CHUNK_BYTES) {
  parts.push(code.slice(i, i + CHUNK_BYTES));
}

parts.forEach((part, i) => {
  writeFileSync(join(chunksDir, `${i}.js`), part, "utf8");
});

const loader = `<script>
(async function () {
  var root = document.getElementById("root");
  var code = "";
  try {
    for (var i = 0; i < ${parts.length}; i++) {
      var r = await fetch("/admin/c/" + i + ".js");
      if (!r.ok) throw new Error("chunk " + i + ": " + r.status);
      code += await r.text();
    }
    var el = document.createElement("script");
    el.textContent = code;
    document.body.appendChild(el);
  } catch (e) {
    root.innerHTML = '<p style="padding:2rem;color:#f87171">Load error: ' + e + '</p>';
  }
})();
</script>`;

html = html.replace(/<script>[\s\S]*?<\/script>/, loader);
html = html.replace(
  '<div id="root"></div>',
  '<div id="root"><p style="padding:2rem;color:#8b9bb4;font-family:system-ui,sans-serif">Loading…</p></div>',
);

writeFileSync(indexPath, html);
console.log(
  `split-admin-bundle: ${parts.length} chunks (${code.length} bytes, ~${CHUNK_BYTES} each)`,
);
