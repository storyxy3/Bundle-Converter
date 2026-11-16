import { appendFile, createReadStream, existsSync, readdirSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve, sep } from "node:path";

import { copyBasisTranscoder } from "/work/motion-bake/prsk3d/vite.basis.plugin";

const unityArtifactTypes = new Map([
  [".loader.js", "application/javascript"],
  [".wasm.gz", "application/wasm"],
  [".framework.js.gz", "application/javascript"],
  [".data.gz", "application/octet-stream"],
  [".worker.js.gz", "application/javascript"],
]);
// The one content root of every dev page, served at /virtual-live-content/:
//   original/          the original-bundle show shell's content (shows.json, AssetBundleInfo, master tables, bundles)
//   mysekai/<alias>/   MySEKAI contents (catalog.json, master.json, bundles/) for mysekai.html and its checks
const virtualLiveContentUrl = "/virtual-live-content/";
const virtualLiveContentRoot = resolve(
  process.env.PJSK_VIRTUAL_LIVE_CONTENT_ROOT ?? "/mnt/z/pjsk-virtual-live-demo",
);
// The Unity WebGL players (<name>/Build/), served at /unity/Haruki3DMV/Build/: this checkout's build folder unless
// HARUKI_UNITY_BUILD_ROOT names one shared by every checkout.
const unityBuildUrl = "/unity/Haruki3DMV/Build/";
const unityBuildRoot = resolve(process.env.HARUKI_UNITY_BUILD_ROOT ?? "unity/Haruki3DMV/Build");

// The one dev server (`bun run dev`): HQ (index.html), the original-bundle show shell (original.html), MySEKAI
// (mysekai.html), the capture harness (capture.html) and the CostumeShop tools (costume-shop-tools.html). It serves Unity's compressed build artifacts and the
// show content root, with cross-origin isolation for the threaded player, and the Basis transcoder under /basis.
// Production builds use vite.config.ts (package) and vite.capture.config.ts (capture page).
export default {
  cacheDir: "/work/motion-bake/task-W/vite-cache",
  optimizeDeps: { entries: ["index.html", "original.html", "mysekai.html", "capture.html", "costume-shop-tools.html"] },
  server: {
    host: "127.0.0.1",
    port: 4174,
    headers: {
      "Cross-Origin-Opener-Policy": "same-origin",
      "Cross-Origin-Embedder-Policy": "require-corp",
      "Cross-Origin-Resource-Policy": "same-origin",
    },
    watch: {
      usePolling: true,
      interval: 1000,
      ignored: [
        "**/unity/**",
        "**/docs/**",
      ],
    },
  },
  plugins: [copyBasisTranscoder("/work/motion-bake/task-W/basis"), {
    name: "unity-webgl-compression-headers",
    configureServer(server) {
      // ?perf=1 summaries from src/harness/perfProbe.ts, one JSON line each.
      const perfLog = process.env.HARUKI_PERF_LOG ?? resolve(tmpdir(), "haruki-perf.ndjson");
      server.middlewares.use("/__haruki-perf", (request, response) => {
        if (request.method !== "POST") {
          response.writeHead(405).end();
          return;
        }
        let body = "";
        request.setEncoding("utf8");
        request.on("data", chunk => { if (body.length < 65536) body += chunk; });
        request.on("end", () => appendFile(perfLog, body.replace(/\s*$/, "\n"), () => response.writeHead(204).end()));
      });
      // ?perf=1 console lines from src/harness/perfProbe.ts (the page's log, warnings and errors), one JSON line each.
      const consoleLog = process.env.HARUKI_CONSOLE_LOG ?? resolve(tmpdir(), "haruki-console.ndjson");
      server.middlewares.use("/__haruki-console", (request, response) => {
        if (request.method !== "POST") {
          response.writeHead(405).end();
          return;
        }
        let body = "";
        request.setEncoding("utf8");
        request.on("data", chunk => { if (body.length < 1 << 20) body += chunk; });
        request.on("end", () => appendFile(consoleLog, body.replace(/\s*$/, "\n"), () => response.writeHead(204).end()));
      });
      // HQ's lists: the Unity WebGL builds of the build root (newest first; threaded when a worker script is beside the
      // loader), the MySEKAI contents under the
      // content root's mysekai/ (each holding catalog.json and master.json) and whether original/shows.json exists.
      server.middlewares.use("/__hq/index.json", (_request, response) => {
        const builds = (existsSync(unityBuildRoot) ? readdirSync(unityBuildRoot) : []).flatMap(name => {
          const dir = resolve(unityBuildRoot, name, "Build");
          const files = existsSync(dir) && statSync(dir).isDirectory() ? readdirSync(dir) : [];
          const loader = files.find(file => file.endsWith(".loader.js"));
          return loader ? [{ name, path: `${unityBuildUrl}${name}/Build/`, modified: statSync(resolve(dir, loader)).mtimeMs,
            threads: files.some(file => /\.worker\.js(\.gz|\.br)?$/.test(file)) }] : [];
        }).sort((a, b) => b.modified - a.modified);
        const mysekaiRoot = resolve(virtualLiveContentRoot, "mysekai");
        const contents = (existsSync(mysekaiRoot) ? readdirSync(mysekaiRoot) : [])
          .filter(name => existsSync(resolve(mysekaiRoot, name, "catalog.json")) && existsSync(resolve(mysekaiRoot, name, "master.json")))
          .sort((a, b) => a.localeCompare(b, "en", { numeric: true }))
          .map(name => ({ name, path: `${virtualLiveContentUrl}mysekai/${name}/` }));
        const shows = existsSync(resolve(virtualLiveContentRoot, "original", "shows.json"));
        response.setHeader("Content-Type", "application/json");
        response.setHeader("Cache-Control", "no-cache");
        response.end(JSON.stringify({ builds, contents, shows }));
      });
      server.middlewares.use((request, response, next) => {
        const requestUrl = new URL(request.url ?? "/", "http://localhost");
        const requestPath = decodeURIComponent(requestUrl.pathname);
        const artifactType = [...unityArtifactTypes].find(([suffix]) =>
          requestPath.endsWith(suffix)
        )?.[1] ?? (/\/Build\/MysekaiUI\//.test(requestPath) ? "application/octet-stream" : undefined);
        const isCompressed = requestPath.endsWith(".gz");
        const isContent = requestPath.startsWith(virtualLiveContentUrl);
        const isBuild = requestPath.startsWith(unityBuildUrl);
        if (!artifactType && !isContent && !isBuild) {
          next();
          return;
        }

        const root = isContent ? virtualLiveContentRoot : isBuild ? unityBuildRoot : resolve(process.cwd());
        const relativePath = isContent ? requestPath.slice(virtualLiveContentUrl.length)
          : isBuild ? requestPath.slice(unityBuildUrl.length) : `.${requestPath}`;
        const filePath = resolve(root, relativePath);
        if (!filePath.startsWith(`${root}${sep}`)) {
          response.writeHead(403).end();
          return;
        }
        // A directory is not a served file; streaming one would kill the server (EISDIR).
        if (!existsSync(filePath) || !statSync(filePath).isFile()) {
          response.writeHead(404).end();
          return;
        }

        // A brotli copy beside the file (X.br, or X.br for a gzip artifact X.gz) is sent with
        // Content-Encoding: br; the browser hands the page the original bytes. Ranges address the
        // original bytes, so they are served from the file itself.
        const brotliPath = (isCompressed ? filePath.slice(0, -3) : filePath) + ".br";
        const brotli = !request.headers.range && /\bbr\b/.test(String(request.headers["accept-encoding"] ?? "")) &&
          existsSync(brotliPath);
        if (existsSync(brotliPath)) response.setHeader("Vary", "Accept-Encoding");
        const servedPath = brotli ? brotliPath : filePath;
        const file = statSync(servedPath);
        const size = file.size;
        const etag = `W/"${size.toString(16)}-${file.mtimeMs.toString(16)}${brotli ? "-br" : ""}"`;
        response.setHeader("ETag", etag);
        response.setHeader("Last-Modified", file.mtime.toUTCString());
        response.setHeader(
          "Content-Type",
          artifactType ?? (requestPath.endsWith(".json")
            ? "application/json"
            : requestPath.endsWith(".wav")
              ? "audio/wav"
              : "application/octet-stream"),
        );
        if (brotli) response.setHeader("Content-Encoding", "br");
        else if (isCompressed) response.setHeader("Content-Encoding", "gzip");
        response.setHeader("Accept-Ranges", "bytes");
        const hasTrustedContentHash = ["mvAsset", "mvSource", "harukiAsset", "harukiAudio", "streamingLiveAsset", "streamingLiveSource"].some((parameter) =>
          /^[0-9a-f]{64}$/.test(requestUrl.searchParams.get(parameter) ?? "")
        );
        response.setHeader(
          "Cache-Control",
          // Show and MySEKAI contents do not change in place: a changed MySEKAI content gets a new alias.
          isContent && (hasTrustedContentHash || requestPath.includes("/original/") ||
            requestPath.startsWith(`${virtualLiveContentUrl}mysekai/`))
            ? "public, max-age=31536000, immutable"
            : "no-cache",
        );
        response.setHeader("Cross-Origin-Opener-Policy", "same-origin");
        response.setHeader("Cross-Origin-Embedder-Policy", "require-corp");
        response.setHeader("Cross-Origin-Resource-Policy", "same-origin");
        const ifNoneMatch = request.headers["if-none-match"];
        const unchanged = ifNoneMatch
          ? ifNoneMatch.split(",").some(value => value.trim() === "*" ||
              value.trim().replace(/^W\//, "") === etag.slice(2))
          : request.headers["if-modified-since"] &&
            file.mtimeMs < Date.parse(request.headers["if-modified-since"]) + 1000;
        if ((request.method === "GET" || request.method === "HEAD") && unchanged) {
          response.writeHead(304).end();
          return;
        }
        // A weak ETag cannot satisfy If-Range; send the whole representation.
        const range = !request.headers["if-range"]
          ? request.headers.range?.match(/^bytes=(\d*)-(\d*)$/) : undefined;
        let start = 0;
        let end = size - 1;
        if (range) {
          if (!range[1] && !range[2]) {
            response.setHeader("Content-Range", `bytes */${size}`);
            response.writeHead(416).end();
            return;
          }
          if (!range[1]) {
            const suffixLength = Number(range[2]);
            start = Math.max(0, size - suffixLength);
          } else {
            start = Number(range[1]);
          }
          if (range[2] && range[1]) end = Math.min(size - 1, Number(range[2]));
          if (!Number.isSafeInteger(start) || !Number.isSafeInteger(end) ||
              start < 0 || start >= size || end < start) {
            response.setHeader("Content-Range", `bytes */${size}`);
            response.writeHead(416).end();
            return;
          }
          response.setHeader("Content-Range", `bytes ${start}-${end}/${size}`);
        }
        response.setHeader("Content-Length", end - start + 1);
        const status = range ? 206 : 200;
        if (request.method === "HEAD") {
          response.writeHead(status).end();
          return;
        }
        response.writeHead(status);
        // Larger reads reduce mounted-drive round trips without buffering the whole file.
        const highWaterMark = Math.min(1024 * 1024, Math.max(1, end - start + 1));
        createReadStream(servedPath, { start, end, highWaterMark }).pipe(response);
      });
    },
  }],
};
