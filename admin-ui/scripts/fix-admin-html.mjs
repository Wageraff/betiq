/** После singlefile: inline script в конец body (в head #root ещё нет). */
import { readFileSync, writeFileSync } from "node:fs";

const path = new URL("../dist/index.html", import.meta.url);
let html = readFileSync(path, "utf8");

const m = html.match(/<script>[\s\S]*?<\/script>/);
if (!m) {
  console.error("fix-admin-html: no inline <script> found");
  process.exit(1);
}

const script = m[0];
html = html.replace(script, "");
html = html.replace(
  '<div id="root"></div>',
  '<div id="root"><p style="padding:2rem;color:#8b9bb4;font-family:system-ui,sans-serif">Loading…</p></div>',
);

const bodyClose = html.lastIndexOf("</body>");
if (bodyClose === -1) {
  console.error("fix-admin-html: no </body> found");
  process.exit(1);
}
html = html.slice(0, bodyClose) + `${script}\n` + html.slice(bodyClose);

writeFileSync(path, html);
console.log("fix-admin-html: moved script to end of body");
