// Мини-статический сервер для случая, когда есть только папка со сборкой, без URL.
// SPA-фолбэк: неизвестный путь без расширения → index.html.
import { createServer } from "node:http";
import { readFile, stat } from "node:fs/promises";
import { join, normalize, extname, resolve } from "node:path";

const TYPES = {
  ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css",
  ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
  ".gif": "image/gif", ".webp": "image/webp", ".avif": "image/avif", ".ico": "image/x-icon", ".woff": "font/woff",
  ".woff2": "font/woff2", ".ttf": "font/ttf", ".otf": "font/otf", ".mp4": "video/mp4", ".webm": "video/webm", ".txt": "text/plain",
  ".map": "application/json", ".wasm": "application/wasm",
};

export function serveDir(dir, port = 0) {
  const root = resolve(dir);
  const server = createServer(async (req, res) => {
    try {
      let p = decodeURIComponent(new URL(req.url, "http://x").pathname);
      let file = normalize(join(root, p));
      if (!file.startsWith(root)) { res.writeHead(403).end(); return; }
      let st = await stat(file).catch(() => null);
      if (st && st.isDirectory()) { file = join(file, "index.html"); st = await stat(file).catch(() => null); }
      if (!st && !extname(p)) {
        const html = file + ".html";
        st = await stat(html).catch(() => null);
        file = st ? html : join(root, "index.html");
        st = st || (await stat(file).catch(() => null));
      }
      if (!st) { res.writeHead(404).end("not found"); return; }
      res.writeHead(200, { "content-type": TYPES[extname(file).toLowerCase()] || "application/octet-stream" });
      res.end(await readFile(file));
    } catch (e) {
      res.writeHead(500).end(String(e));
    }
  });
  return new Promise((ok) => server.listen(port, "127.0.0.1", () => ok({ url: `http://127.0.0.1:${server.address().port}`, close: () => server.close() })));
}
