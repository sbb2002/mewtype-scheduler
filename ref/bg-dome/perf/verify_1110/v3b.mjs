import { open, sleep } from "../cdp.mjs";
const c = await open(9347);
await c.send("Emulation.setDeviceMetricsOverride", { width: 390, height: 800, deviceScaleFactor: 2, mobile: true });
await c.load("http://127.0.0.1:8131/src/frontend/index.html?bgdebug&bgtier=high", { "bgpeek-cue": "1" }); await sleep(2500);
await c.ev(`document.documentElement.classList.add("bg-peek")`); await sleep(1500);
await c.ev(`__bglive(["arale","yuno","nonoka","ritsu","miyako"])`);
let i = 0;
for (const az of [18, 90, 162, 234, 306]) {
  await c.ev(`__bgview(${az}, -35)`); await sleep(1300);
  // 맥동 최고점 근처를 기다린다(주기 2.8s) — 두 장 중 밝은 쪽을 쓴다
  await c.shot(`v3b_${i}a.jpg`); await sleep(1400); await c.shot(`v3b_${i}b.jpg`); i++;
}
await c.close(); process.exit(0);
