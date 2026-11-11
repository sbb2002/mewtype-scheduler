// 헤드리스 크롬으로 돔 우주 바탕 캡처 — node shot.mjs <outdir> <mode...>
import { spawn } from "node:child_process";
import { writeFileSync } from "node:fs";
const out = process.argv[2], modes = process.argv.slice(3);
const chrome = spawn("C:/Program Files/Google/Chrome/Application/chrome.exe", ["--headless=new", "--remote-debugging-port=9339", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist", "--user-data-dir=" + out + "/prof", "--window-size=390,760", "about:blank"], { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
await sleep(2500);
const list = await (await fetch("http://127.0.0.1:9339/json")).json();
const ws = new WebSocket(list.find((t) => t.type === "page").webSocketDebuggerUrl);
await new Promise((r) => ws.onopen = r);
let id = 0; const pend = new Map();
ws.onmessage = (m) => { const d = JSON.parse(m.data); if (d.id && pend.has(d.id)) { pend.get(d.id)(d); pend.delete(d.id); } };
const send = (method, params = {}) => new Promise((r) => { const i = ++id; pend.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
await send("Runtime.enable"); ws.addEventListener("message", (m) => { const d = JSON.parse(m.data); if (d.method === "Runtime.exceptionThrown") console.log("EXC", JSON.stringify(d.params.exceptionDetails).slice(0, 300)); if (d.method === "Runtime.consoleAPICalled" && d.params.type === "error") console.log("ERR", JSON.stringify(d.params.args).slice(0, 300)); });
await send("Emulation.setDeviceMetricsOverride", { width: 390, height: 760, deviceScaleFactor: 2, mobile: true });
const ev = async (e) => (await send("Runtime.evaluate", { expression: e, awaitPromise: true, returnByValue: true })).result?.result?.value;
for (const mode of modes) {
  await send("Page.navigate", { url: `http://127.0.0.1:8102/src/frontend/?va=claude&bgdebug&bgunlock=all&bgindoor=space&bgspace=${mode}&bgtier=high` });
  await sleep(9000);
  await ev(`(()=>{const s=document.createElement('style');s.textContent='body>*:not(#bgdeco){visibility:hidden!important} #bgdeco *:not(.bgdm-gl){visibility:hidden!important} #bgdeco,.bgdm-gl{visibility:visible!important}';document.head.append(s);return 1})()`);
  for (const [az, alt] of JSON.parse(process.env.ANG)) {
    await ev(`window.__bgview && window.__bgview(${az},${alt})`);
    await sleep(5000);
    const st = await ev(`JSON.stringify(window.__bgdome ? {sets: window.__bgdome.state.sets} : null)`);
    const shot = await send("Page.captureScreenshot", { format: "jpeg", quality: 85 });
    writeFileSync(`${out}/${mode}_${az}_${alt}.jpg`, Buffer.from(shot.result.data, "base64"));
    console.log(mode, az, alt, st);
  }
}
ws.close(); chrome.kill();
