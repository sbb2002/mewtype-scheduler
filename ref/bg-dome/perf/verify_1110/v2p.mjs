import { open, sleep } from "../cdp.mjs";
const c = await open(9345);
await c.send("Emulation.setDeviceMetricsOverride", { width: 360, height: 800, deviceScaleFactor: 3, mobile: true });
await c.load("http://127.0.0.1:8131/src/frontend/index.html?bgdebug&bgtier=low", { "bgpeek-cue": "1" }); await sleep(2500);
await c.send("Emulation.setCPUThrottlingRate", { rate: 6 });
await c.send("Profiler.enable"); await c.send("Profiler.setSamplingInterval", { interval: 500 });
const prof = async (label) => {
  await c.send("Profiler.start"); await sleep(4000); const { profile } = await c.send("Profiler.stop");
  const byId = new Map(profile.nodes.map((n) => [n.id, n])); const self = new Map();
  const dt = profile.timeDeltas; profile.samples.forEach((id, i) => { const n = byId.get(id); const k = `${n.callFrame.functionName || "(anon)"} ${n.callFrame.url.split("/").pop()}:${n.callFrame.lineNumber + 1}`; self.set(k, (self.get(k) || 0) + (dt[i] || 0)); });
  const tot = [...self.values()].reduce((a, b) => a + b, 0);
  console.log("==", label); [...self.entries()].sort((a, b) => b[1] - a[1]).slice(0, 14).forEach(([k, v]) => console.log((v / tot * 100).toFixed(1) + "%", k));
};
await c.ev(`document.documentElement.classList.add("bg-peek"); window.__lookT = setInterval(() => { const t = performance.now() / 1000; __bgview(40 + 70 * Math.sin(t * 0.7), 18 + 16 * Math.sin(t * 1.1)); }, 16)`); await sleep(1000);
await prof("peek x6 low");
await c.ev(`clearInterval(__lookT); __bgview(null); document.documentElement.classList.remove("bg-peek")`); await sleep(2500);
await prof("board x6 low");
await c.close(); process.exit(0);
