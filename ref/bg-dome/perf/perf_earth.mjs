// 지구(바깥) 둘러보기만 다시 잰다 — 위치 권한을 주고 실제 경로(chooseBgView)로 들어간다
import { open, sleep, HERE } from "./cdp.mjs";
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
const REC = readFileSync(join(HERE, "perf.mjs"), "utf8").match(/const RECORDER = `([\s\S]*?)`;\r?\n/)[1];
const c = await open(9335);
await c.send("Performance.enable");
await c.send("Browser.grantPermissions", { permissions: ["geolocation"] });
await c.send("Emulation.setGeolocationOverride", { latitude: 37.55, longitude: 126.98, accuracy: 30 });
await c.send("Emulation.setDeviceMetricsOverride", { width: 360, height: 800, deviceScaleFactor: 3, mobile: true });
await c.send("Page.addScriptToEvaluateOnNewDocument", { source: REC });
const tm = async () => { const { metrics } = await c.send("Performance.getMetrics"); return metrics.find((m) => m.name === "TaskDuration").value; };
const out = [];
for (const kind of ["city", "mountain", "sea"]) for (const rate of [1, 1.5, 2, 3, 4, 6, 8]) {
  await c.send("Emulation.setCPUThrottlingRate", { rate: 1 });
  await c.load(`http://localhost:8102/src/frontend/?bgdebug&bgunlock=all&bgground=${kind}`, { "bgpeek-cue": "1" });
  await c.ev(`document.documentElement.classList.add("bg-peek")`);
  await c.ev(`import("/src/frontend/js/bgview.js").then((m) => m.chooseBgView("outdoor")).then(() => 1)`);
  await sleep(9000);   // 전환 · 지형 굽기가 끝날 때까지
  await c.send("Emulation.setCPUThrottlingRate", { rate });
  await c.ev(`window.__lookT = setInterval(() => { const t = performance.now() / 1000; __bgview(270 + 70 * Math.sin(t * 0.7), 4 + 16 * Math.sin(t * 1.1)); }, 16)`);
  await sleep(1500); await c.ev("__pf.reset()");
  const a = await tm(), t0 = Date.now(); await sleep(6000); const b = await tm(), wall = (Date.now() - t0) / 1000;
  const r = await c.ev("__pf.report()"); const isOut = await c.ev("__bgdome.state.outdoor");
  const row = { kind, rate, outdoor: isOut, fps: +r.fps.toFixed(1), p95: +r.p95.toFixed(1), glFps: +r.glFps.toFixed(1), busy: +((b - a) / wall).toFixed(2), ltN: r.ltN, ltMs: Math.round(r.ltMs) };
  out.push(row); console.log(JSON.stringify(row)); writeFileSync(join(HERE, "result_earth.json"), JSON.stringify(out, null, 2));
}
await c.close(); process.exit(0);
