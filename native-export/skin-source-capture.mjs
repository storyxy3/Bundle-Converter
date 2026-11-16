// Drive the existing original-show page and save its real WebGL canvas and logs.
import { createRequire } from 'node:module';
import { mkdir, writeFile, appendFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const here = "/work/motion-bake/task-W";
const require = createRequire(path.join(here, '../prsk3d/package.json'));
const { chromium } = require('playwright');
const [show = 'mv610', ...args] = process.argv.slice(2);
const seconds = (args.length ? args : ['20', '60', '90']).map(Number);
if (!/^[\w-]+$/.test(show) || seconds.some(t => !Number.isFinite(t) || t < 0)) {
  throw new Error('Use a show ID and nonnegative finite seconds.');
}
const out = path.join(here, 'source-captures', `${new Date().toISOString().replace(/[:.]/g, '-')}-${show}`);
await mkdir(out, { recursive: true });
const consolePath = path.join(out, 'console.log');
await writeFile(consolePath, '');
let writes = Promise.resolve();
const log = (kind, message) => {
  const line = `${new Date().toISOString()} [${kind}] ${message}\n`;
  writes = writes.then(() => appendFile(consolePath, line));
};
const origin = `http://127.0.0.1:${process.env.RUNTIME_CHECK_PORT || 4186}`;
const summary = { show, seconds, url: `${origin}/original.html?show=${show}${process.env.RUNTIME_CHECK_QUERY ? "&" + process.env.RUNTIME_CHECK_QUERY : ""}`, screenshots: [], errors: [], httpErrors: [] };
console.log(`Output: ${out}`);
const browser = await chromium.launch({
  headless: true,
  executablePath: "/home/user/.cache/ms-playwright/chromium-1254/chrome-linux64/chrome",
  args: ['--enable-unsafe-swiftshader', '--use-angle=swiftshader', '--no-proxy-server',
    '--disable-background-networking', '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1'],
});
const page = await browser.newPage({ viewport: { width: 1440, height: 1100 }, deviceScaleFactor: 1 });
page.setDefaultTimeout(600000);
page.on('console', m => log(m.type(), m.text()));
page.on('pageerror', e => { summary.errors.push(String(e)); log('pageerror', e.stack || String(e)); });
page.on('requestfailed', r => log('requestfailed', `${r.url()} ${r.failure()?.errorText}`));
page.on('response', r => {
  if (r.status() === 404 && r.request().method() === 'HEAD' && r.url().endsWith('/HarukiMV.worker.js.gz')) {
    log('probe', 'Expected missing worker: single-threaded player.');
  } else if (r.status() >= 400) { summary.httpErrors.push(`${r.status()} ${r.url()}`); log('http', `${r.status()} ${r.url()}`); }
});
// Do not let catalog URLs, redirects or page resources contact other hosts.
await page.route('**/*', route => {
  const url = new URL(route.request().url());
  if (url.origin === origin || ['data:', 'blob:'].includes(url.protocol)) return route.continue();
  log('blocked', url.href);
  return route.abort('blockedbyclient');
});
await page.addInitScript(() => {
  window.addEventListener('haruki-mv', event => {
    const value = event.detail;
    if (value?.type === 'state' && value.payload) {
      window.captureState = JSON.parse(value.payload);
      window.captureStateAt = performance.now();
    }
  });
});

const actor = process.env.W_ACTOR || 'ichika';
const master = '/work/haruki-sekai-master/master/';
const { readFile } = await import('node:fs/promises');
await page.route('**/shows-scene.json', async route => {
 const response = await route.fetch(); const doc = await response.json();
 const entry = doc.shows.find(s => s.id === 'scene-ext-motion');
 entry.scene.cast.performers[0].member = actor === 'ichika'
 ? {characterId:1,unit:'light_sound',headCostume3dId:1,hairCostume3dId:201,bodyCostume3dId:2}
 : {characterId:21,unit:'piapro',headCostume3dId:121,hairCostume3dId:221,bodyCostume3dId:42};
 await route.fulfill({response,json:doc});
});
await page.route('**/scene-ext-motion-master.json', async route => {
 const response = await route.fetch(); const doc = await response.json();
 for (const key of ['gameCharacters','gameCharacterUnits','costume3ds','costume3dModels'])
  doc[key] = JSON.parse(await readFile(master+key+'.json','utf8'));
 // Use the actual combined source face bundles, retaining source texture/material rendering.
 for (const m of doc.costume3dModels) {
  if (m.costume3dId === 1 && m.unit === 'light_sound') {m.assetbundleName='01/0001';m.headCostume3dAssetbundleType='head_and_hair';}
  if (m.costume3dId === 201 && m.unit === 'light_sound') m.assetbundleName='01/0001';
  if (m.costume3dId === 221 && m.unit === 'piapro') m.assetbundleName='21/0001';
 }
 await route.fulfill({response,json:doc});
});
let heartbeat;
try {
  await page.goto(summary.url, { waitUntil: 'domcontentloaded', timeout: 120000 });
  heartbeat = setInterval(() => {
    page.locator('#status').textContent({ timeout: 5000 }).then(s => console.log(`Status: ${s}`)).catch(() => {});
  }, 15000);
  // Surface the page's own failure immediately instead of waiting ten minutes.
  const wait = async (predicate, arg) => {
    await page.waitForFunction(({ source, arg }) => {
      const error = document.querySelector('#error');
      if (error && !error.hidden && error.textContent) throw new Error(error.textContent);
      return (0, eval)(`(${source})`)(arg);
    }, { source: predicate.toString(), arg }, { timeout: 600000 });
  };
  await wait(() => window.harukiBridge && !document.querySelector('#load').disabled &&
    document.querySelector('#status').textContent.includes('播放器已就绪'));
  summary.crossOriginIsolated = await page.evaluate(() => crossOriginIsolated);
  if (!summary.crossOriginIsolated) throw new Error('Missing cross-origin isolation headers.');
  if (await page.locator('#show').inputValue() !== show) throw new Error(`Unknown show: ${show}`);
  await page.locator('#load').click();
  await wait(() => document.body.dataset.ready === 'true');
  await wait(() => window.captureState?.durationSeconds > 0);
  summary.durationSeconds = await page.evaluate(() => window.captureState.durationSeconds);
  // RUNTIME_CHECK_VIEWER=<preset id>: switch the viewer camera (original | centre | left | right) after loading.
  if (process.env.RUNTIME_CHECK_VIEWER) {
    // The page control may be collapsed: set the same camera through the bridge (mvViewerCameraPresets.ts orbit()).
    const yaw = { centre: 180, left: 240, right: 120 }[process.env.RUNTIME_CHECK_VIEWER];
    await page.evaluate(yaw => window.harukiBridge.setViewerCamera(yaw === undefined ? { mode: "original" } : {
      mode: "orbit", target: { kind: "area", offset: { x: 0, y: 1.15, z: 0 } }, yawDegrees: yaw, pitchDegrees: -1.3,
      distance: 8.5, fieldOfView: 25, focus: "target", framing: {} }), yaw);
    summary.viewerCamera = process.env.RUNTIME_CHECK_VIEWER;
  }
  await page.evaluate(() => window.harukiBridge.setViewerCamera({mode:'fixed',position:{x:0,y:1.1,z:4},target:{kind:'point',point:{x:0,y:.9,z:0}},fieldOfView:30,focus:'target'}));
  summary.actor=actor;
  if (seconds.some(t => t > summary.durationSeconds)) throw new Error('Requested seconds exceed show duration.');
  // Verify the playback clock actually advances, then freeze it for exact seeks.
  const start = await page.evaluate(() => window.captureState.timeSeconds);
  await page.locator('#play').click();
  await wait(start => window.captureState?.state === 'playing' && window.captureState.timeSeconds > start + 0.3, start);
  summary.played = await page.evaluate(() => window.captureState);
  await page.locator('#play').click();
  await wait(() => document.body.dataset.playbackState === 'paused');
  for (const second of seconds) {
    const before = await page.evaluate(second => {
      const before = window.captureState.frameCount;
      const timeline = document.querySelector('#timeline');
      timeline.value = String(second);
      timeline.dispatchEvent(new Event('input', { bubbles: true }));
      timeline.dispatchEvent(new Event('change', { bubbles: true }));
      return before;
    }, second);
    await wait(({ second, before }) => Math.abs(window.captureState.timeSeconds - second) < 0.06 &&
      window.captureState.frameCount >= before + 3 && document.body.dataset.playbackState === 'paused', { second, before });
    summary.cameraStates = summary.cameraStates ?? {};
    summary.cameraStates[second] = await page.evaluate(() => window.harukiBridge.getViewerCameraState?.()).catch(e => String(e));
    const file = `${show}-${String(second).replace('.', '_')}s.png`;
    await page.locator('#live').screenshot({ path: path.join(out, file), timeout: 120000 });
    summary.screenshots.push({ file, requestedSeconds: second, state: await page.evaluate(() => window.captureState) });
    console.log(`Saved ${file}`);
  }
  await page.screenshot({ path: path.join(out, 'page.png'), fullPage: true, timeout: 120000 });
  summary.renderer = await page.evaluate(() => {
    const gl = document.querySelector('#live').getContext('webgl2');
    const ext = gl?.getExtension('WEBGL_debug_renderer_info');
    return ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : 'unavailable';
  });
  if (summary.errors.length || summary.httpErrors.length) throw new Error('Browser or HTTP errors; see console.log and capture.json.');
  summary.success = true;
} catch (error) {
  summary.success = false;
  summary.failure = error.stack || String(error);
  log('failure', summary.failure);
  await page.screenshot({ path: path.join(out, 'failure.png'), fullPage: true, timeout: 30000 }).catch(() => {});
  process.exitCode = 1;
  console.error(summary.failure);
} finally {
  clearInterval(heartbeat);
  await writeFile(path.join(out, 'capture.json'), JSON.stringify(summary, null, 2) + '\n');
  await browser.close();
  await writes;
}
