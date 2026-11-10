// 2단계 확인 — CPU ×1(하이엔드) · ×3(중간급) · ×6(저사양) 세 단계만. 데이터는 캐시 서버(8131)
import { open, sleep } from "../cdp.mjs";
const B = "http://127.0.0.1:8131/src/frontend/index.html?bgdebug";
const REC = `(() => { const pf = window.__pf = { ts: [], gl: 0, drew: false };
  for (const P of [window.WebGL2RenderingContext]) for (const m of ["drawArrays", "drawElements"]) { const o = P.prototype[m]; P.prototype[m] = function () { pf.drew = true; return o.apply(this, arguments); }; }
  const loop = (t) => { pf.ts.push(t); if (pf.drew) { pf.gl++; pf.drew = false; } requestAnimationFrame(loop); }; requestAnimationFrame(loop);
  pf.reset = () => { pf.ts = []; pf.gl = 0; pf.t0 = performance.now(); };
  pf.report = () => { const s = (performance.now() - pf.t0) / 1000; return { fps: +(pf.ts.length / s).toFixed(1), glFps: +(pf.gl / s).toFixed(1) }; }; })()`;
const LOOK = `window.__lookT = setInterval(() => { const t = performance.now() / 1000; __bgview(40 + 70 * Math.sin(t * 0.7), 18 + 16 * Math.sin(t * 1.1)); }, 16)`;
const c = await open(9344);
await c.send("Performance.enable");
const task = async () => { const { metrics } = await c.send("Performance.getMetrics"); return metrics.find((m) => m.name === "TaskDuration").value; };
await c.send("Emulation.setDeviceMetricsOverride", { width: 360, height: 800, deviceScaleFactor: 3, mobile: true });
const runs = [[1, ""], [3, ""], [6, ""], [6, "&bgtier=high"]];
for (const [rate, q] of runs) {
  await c.send("Emulation.setCPUThrottlingRate", { rate: 1 });
  c.logs.length = 0;
  await c.load(B + q, { "bgpeek-cue": "1" });
  await c.ev(REC); await sleep(3000);
  await c.send("Emulation.setCPUThrottlingRate", { rate });
  // 배경 보기 + 둘러보기: 등급 실측
  await c.ev(`document.documentElement.classList.add("bg-peek")`); await c.ev(LOOK); await sleep(1000);
  await c.ev(`__pf.reset()`); let t0 = await task(); await sleep(5000);
  const peek = { ...(await c.ev(`__pf.report()`)), busy: +(((await task()) - t0) / 5 * 100).toFixed(0) + "%" };
  const tierAfterPeek = await c.ev(`JSON.stringify({ tier: __bgtier.tier, measuring: __bgtier.measuring })`);
  // 예고보드로 돌아와 대기
  await c.ev(`clearInterval(__lookT); __bgview(null); document.documentElement.classList.remove("bg-peek")`); await sleep(2500);
  await c.ev(`__pf.reset()`); t0 = await task(); await sleep(6000);
  const board = { ...(await c.ev(`__pf.report()`)), busy: +(((await task()) - t0) / 6 * 100).toFixed(0) + "%" };
  await c.shot(`v2_board_x${rate}${q ? "_high" : ""}.jpg`);
  console.log(`CPU x${rate}${q}`, "| tier", tierAfterPeek, "| peek", JSON.stringify(peek), "| board", JSON.stringify(board), "| err", c.logs.filter((l) => /EXC/.test(l)).slice(0, 3));
}
await c.close(); process.exit(0);
