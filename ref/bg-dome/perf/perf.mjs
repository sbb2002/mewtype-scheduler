// bg-dome 기기별 성능 측정 — 전용 크롬을 띄우고 CDP 로 뷰포트 · DPR · CPU 제한 배율을 바꿔 가며 잰다.
// 사용: node perf.mjs [결과.json] [배율 목록 "1,2,4"]
import { spawn } from "node:child_process";
import { writeFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = process.argv[2] || join(HERE, "result.json");
const RATES = (process.argv[3] || "1,1.5,2,3,4,6,8,12").split(",").map(Number);
const BASE = "http://localhost:8102/src/frontend/";
const PORT = 9333;
const CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const log = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a);

mkdirSync(join(HERE, "prof"), { recursive: true });
const chrome = spawn(CHROME, [
  `--remote-debugging-port=${PORT}`, `--user-data-dir=${join(HERE, "prof")}`, "--no-first-run", "--no-default-browser-check",
  "--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding", "--disable-background-timer-throttling",
  "--headless=new", "--window-size=1000,1040", "about:blank",   // 창 없이(사용자 화면 위에 뜨지 않게)
], { stdio: "ignore" });

let ws, seq = 0; const wait = new Map(); const evts = [];
async function connect() {
  for (let i = 0; i < 40; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${PORT}/json`)).json();
      const page = list.find((t) => t.type === "page");
      if (page) { ws = new WebSocket(page.webSocketDebuggerUrl); break; }
    } catch { /* 아직 안 뜸 */ }
    await sleep(250);
  }
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  ws.onmessage = (m) => {
    const d = JSON.parse(m.data);
    if (d.id && wait.has(d.id)) { const [res, rej] = wait.get(d.id); wait.delete(d.id); d.error ? rej(new Error(d.error.message)) : res(d.result); }
    else if (d.method) evts.push(d);
  };
}
const send = (method, params = {}) => new Promise((res, rej) => { const id = ++seq; wait.set(id, [res, rej]); ws.send(JSON.stringify({ id, method, params })); });
async function ev(expr) {
  const r = await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true });
  if (r.exceptionDetails) throw new Error("page: " + (r.exceptionDetails.exception?.description || r.exceptionDetails.text));
  return r.result.value;
}
async function waitEvent(name, ms) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) { const i = evts.findIndex((e) => e.method === name); if (i >= 0) { evts.splice(i, 1); return true; } await sleep(50); }
  return false;
}
async function taskMetrics() {
  const { metrics } = await send("Performance.getMetrics");
  const g = (n) => metrics.find((m) => m.name === n)?.value || 0;
  return { task: g("TaskDuration"), script: g("ScriptDuration"), layout: g("LayoutDuration"), style: g("RecalcStyleDuration"), heap: g("JSHeapUsedSize") };
}

// 페이지에 심는 기록기 — rAF 간격 · WebGL 그리기 횟수 · 긴 작업
const RECORDER = `(() => {
  const pf = window.__pf = { ts: [], draws: 0, drawFrames: 0, lt: [], firstDraw: null };
  let drew = false;
  for (const P of [window.WebGLRenderingContext, window.WebGL2RenderingContext]) { if (!P) continue;
    for (const m of ["drawArrays", "drawElements"]) { const o = P.prototype[m]; P.prototype[m] = function () { pf.draws++; drew = true; if (pf.firstDraw == null) pf.firstDraw = performance.now(); return o.apply(this, arguments); }; } }
  const loop = (t) => { pf.ts.push(t); if (drew) { pf.drawFrames++; drew = false; } requestAnimationFrame(loop); };
  requestAnimationFrame(loop);
  try { new PerformanceObserver((l) => { for (const e of l.getEntries()) pf.lt.push(e.duration); }).observe({ entryTypes: ["longtask"] }); } catch {}
  pf.reset = () => { pf.ts.length = 0; pf.draws = 0; pf.drawFrames = 0; pf.lt.length = 0; pf.t0 = performance.now(); };
  pf.report = () => {
    const d = []; for (let i = 1; i < pf.ts.length; i++) d.push(pf.ts[i] - pf.ts[i - 1]);
    d.sort((a, b) => a - b); const q = (p) => d.length ? d[Math.min(d.length - 1, Math.floor(d.length * p))] : null;
    const sec = (performance.now() - pf.t0) / 1000;
    return { sec, fps: d.length / sec, p50: q(0.5), p95: q(0.95), max: d[d.length - 1] ?? null, over25: d.filter((x) => x > 25).length / Math.max(1, d.length), over50: d.filter((x) => x > 50).length / Math.max(1, d.length),
      glFps: pf.drawFrames / sec, glCalls: pf.draws / Math.max(1, pf.drawFrames), ltN: pf.lt.length, ltMs: pf.lt.reduce((a, b) => a + b, 0), ltMax: Math.max(0, ...pf.lt) };
  };
})();`;

let scriptId = null;
async function load(query, ls) {
  if (scriptId) await send("Page.removeScriptToEvaluateOnNewDocument", { identifier: scriptId });
  const seed = `try { localStorage.clear(); ${Object.entries(ls).map(([k, v]) => `localStorage.setItem(${JSON.stringify(k)}, ${JSON.stringify(v)});`).join(" ")} } catch {}`;
  scriptId = (await send("Page.addScriptToEvaluateOnNewDocument", { source: seed + RECORDER })).identifier;
  evts.length = 0;
  const t0 = Date.now();
  await send("Page.navigate", { url: BASE + query });
  const loaded = await waitEvent("Page.loadEventFired", 120000);
  const loadMs = Date.now() - t0;
  let firstDraw = null;
  if (!query.includes("bg=classic")) for (let i = 0; i < 300 && firstDraw == null; i++) { firstDraw = await ev("window.__pf && __pf.firstDraw"); if (firstDraw == null) await sleep(200); }
  return { loaded, loadMs, firstDrawMs: firstDraw && Math.round(firstDraw) };
}
const round = (o) => Object.fromEntries(Object.entries(o).map(([k, v]) => [k, typeof v === "number" ? Math.round(v * 100) / 100 : v]));
async function measure(ms, during) {
  await ev("__pf.reset()");
  const m0 = await taskMetrics(), t0 = Date.now();
  if (during) await during(ms); else await sleep(ms);
  const m1 = await taskMetrics(), wall = (Date.now() - t0) / 1000;
  const r = await ev("__pf.report()");
  return round({ ...r, busy: (m1.task - m0.task) / wall, script: (m1.script - m0.script) / wall, layout: (m1.layout - m0.layout + m1.style - m0.style) / wall, heapMB: m1.heap / 1048576 });
}

async function peekOn(vw, vh) {
  // 실제 조작처럼 — 지금 레인을 끝까지 내린 뒤 위로 튕긴다. 안 되면 클래스만 붙인다(돔은 이 클래스만 본다)
  await ev(`(() => { const l = document.querySelector(".lane--active"); if (l) l.scrollTop = 1e6; })()`);
  const x = Math.round(vw / 2), y0 = Math.round(vh * 0.6);
  const t = Date.now() / 1000;
  await send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x, y: y0 }], timestamp: t });
  for (let i = 1; i <= 4; i++) await send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [{ x, y: y0 - i * 50 }], timestamp: t + i * 0.02 });
  await send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [], timestamp: t + 0.1 });
  await sleep(300);
  let how = "flick";
  if (!(await ev(`document.documentElement.classList.contains("bg-peek")`))) { await ev(`document.documentElement.classList.add("bg-peek")`); how = "class"; }
  return how;
}
const LOOK_ON = `window.__lookT = setInterval(() => { const t = performance.now() / 1000; __bgview(40 + 70 * Math.sin(t * 0.7), 18 + 16 * Math.sin(t * 1.1)); }, 16)`;
const LOOK_OFF = `clearInterval(window.__lookT); window.__bgview && __bgview(null)`;

async function pinchFor(ms, vw, vh) {
  const cx = vw / 2, cy = vh / 2, t0 = Date.now();
  const pts = (d) => [{ x: cx - d / 2, y: cy, id: 1 }, { x: cx + d / 2, y: cy, id: 2 }];
  await send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: pts(120) });
  while (Date.now() - t0 < ms) {
    const d = 160 + 110 * Math.sin((Date.now() - t0) / 1000 * 1.6);   // 벌렸다 오므렸다
    send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: pts(d) }).catch(() => {});   // 응답을 기다리지 않는다(기다리면 프레임에 묶여 측정이 왜곡됨)
    await sleep(33);
  }
  await send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
}
async function scrollFor(ms, vw, vh) {
  const t0 = Date.now(); let dir = -1;
  while (Date.now() - t0 < ms) {
    await send("Input.synthesizeScrollGesture", { x: Math.round(vw / 2), y: Math.round(vh * 0.55), yDistance: dir * 350, speed: 900, gestureSourceType: "touch" }).catch(() => {});
    dir = -dir;
  }
}

const UA_PHONE = "Mozilla/5.0 (Linux; Android 14; SM-A546N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36";
const WIN = 6000;

async function runDevice(dev) {
  const { name, w, h, dpr, rate, mobile = true } = dev;
  log(`▶ ${name} (${w}×${h} @${dpr}, CPU ×${rate})`);
  await send("Emulation.setDeviceMetricsOverride", { width: w, height: h, deviceScaleFactor: dpr, mobile });
  await send("Emulation.setTouchEmulationEnabled", { enabled: mobile, maxTouchPoints: 5 });
  await send("Emulation.setUserAgentOverride", mobile ? { userAgent: UA_PHONE } : { userAgent: "" }).catch(() => {});
  await send("Emulation.setCPUThrottlingRate", { rate });
  const res = { ...dev, runs: {}, loads: {} };
  const rec = async (key, ms, during) => { const r = await measure(ms, during); res.runs[key] = r; log(`  ${key.padEnd(22)} fps ${String(r.fps).padStart(5)} p95 ${String(r.p95).padStart(6)}ms  gl ${String(r.glFps).padStart(5)}/s  busy ${Math.round(r.busy * 100)}%  긴작업 ${r.ltN}(${Math.round(r.ltMs)}ms)`); save(); };
  const settle = () => sleep(Math.min(9000, 3000 + rate * 500));
  const ls0 = { "bgpeek-cue": "1" };

  // 1) 옛 배경(돔 없음) — 기준선
  res.loads.classic = await load("?bg=classic", ls0); await settle();
  await rec("메인 대기 · 옛 배경", WIN);

  // 2) 버츄얼 스페이스(첫 방문 기본 장면)
  res.loads.pink = await load("?bgdebug&bgunlock=all", ls0); await settle();
  await rec("메인 대기 · 돔", WIN);
  await rec("메인 레인 스크롤 · 돔", WIN, (ms) => scrollFor(ms, w, h));
  if (mobile) {
    res.peekHow = await peekOn(w, h); await sleep(1500);
    await rec("배경 보기 대기", WIN);
    await ev(LOOK_ON); await sleep(500);
    await rec("둘러보기 · 버츄얼", WIN);
    await ev(LOOK_OFF);
    const tg = await ev(`(() => { const t = __bgunlock.targets[0]; if (!t) return null; __bgview(t.az, t.alt); return t; })()`);
    if (tg) { await sleep(600); await rec("HUD 조준 · 잡힘", WIN); res.hud = await ev("JSON.stringify(__bgunlock.hud || null)").catch(() => null); }
    await ev(LOOK_OFF);
    await rec("두 손가락 줌", WIN, (ms) => pinchFor(ms, w, h));

    // 3) 초행성X(우주) — 둘러보기 · 성간 이동
    res.loads.space = await load("?bgdebug&bgunlock=all&bgindoor=space", { ...ls0, bgindoor: "space" }); await settle();
    await peekOn(w, h); await sleep(1500);
    await ev(LOOK_ON); await sleep(500);
    await rec("둘러보기 · 초행성X", WIN);
    await ev(LOOK_OFF);
    await ev("__bggear(3)"); await sleep(2500);
    await rec("성간 이동 3단", WIN);
    await ev("__bggear(5)"); await sleep(2500);
    await rec("성간 이동 5단", WIN);

    // 4) 지구(바깥) — 지형 포함
    res.loads.earth = await load("?bgdebug&bgunlock=all", { ...ls0, bgview: "outdoor" }); await settle(); await sleep(3000);
    await peekOn(w, h); await sleep(1500);
    await ev(LOOK_ON); await sleep(500);
    await rec("둘러보기 · 지구", WIN);
    await ev(LOOK_OFF);
  }
  log("  로드", JSON.stringify(res.loads));
  return res;
}

const all = { when: new Date().toISOString(), env: {}, devices: [] };
function save() { writeFileSync(OUT, JSON.stringify(all, null, 2)); }

try {
  await connect();
  await send("Page.enable"); await send("Runtime.enable"); await send("Performance.enable");
  // 예열(캐시 채우기) + 환경 기록
  await send("Emulation.setDeviceMetricsOverride", { width: 360, height: 800, deviceScaleFactor: 3, mobile: true });
  await load("?bgdebug&bgunlock=all", {}); await sleep(4000);
  await load("?bgdebug&bgunlock=all&bgindoor=space", { bgindoor: "space" }); await sleep(3000);
  await load("?bgdebug&bgunlock=all", { bgview: "outdoor" }); await sleep(5000);
  all.env = await ev(`(() => { const c = document.createElement("canvas"); const g = c.getContext("webgl2") || c.getContext("webgl"); const x = g && g.getExtension("WEBGL_debug_renderer_info");
    return { ua: navigator.userAgent, cores: navigator.hardwareConcurrency, gpu: x ? g.getParameter(x.UNMASKED_RENDERER_WEBGL) : null, canvas: [...document.querySelectorAll("canvas")].map((k) => k.width + "x" + k.height) }; })()`);
  log("환경", JSON.stringify(all.env));

  const devices = [];
  for (const r of RATES) devices.push({ name: `폰 360×800 · CPU ×${r}`, w: 360, h: 800, dpr: 3, rate: r });
  if (!process.argv[3]) {
    devices.push({ name: "큰 폰 430×932 · CPU ×1", w: 430, h: 932, dpr: 3, rate: 1 });
    devices.push({ name: "큰 폰 430×932 · CPU ×4", w: 430, h: 932, dpr: 3, rate: 4 });
    devices.push({ name: "PC 1920×1080 · CPU ×1", w: 1920, h: 1080, dpr: 1, rate: 1, mobile: false });
    devices.push({ name: "PC 1920×1080 · CPU ×4", w: 1920, h: 1080, dpr: 1, rate: 4, mobile: false });
  }
  for (const d of devices) {
    try { all.devices.push(await runDevice(d)); } catch (e) { log("  ✗ 실패", e.message); all.devices.push({ ...d, error: e.message }); }
    save();
  }
} finally {
  save();
  try { await send("Browser.close"); } catch { chrome.kill(); }
  log("끝 →", OUT);
  process.exit(0);
}
