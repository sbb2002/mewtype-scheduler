// 창 없는 크롬 + CDP 공통 도구
import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
export const HERE = dirname(fileURLToPath(import.meta.url));
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
export async function open(port = 9334) {
  mkdirSync(join(HERE, "prof_" + port), { recursive: true });
  const chrome = spawn("C:/Program Files/Google/Chrome/Application/chrome.exe", [`--remote-debugging-port=${port}`, `--user-data-dir=${join(HERE, "prof_" + port)}`, "--headless=new", "--no-first-run", "--window-size=1000,1040", "about:blank"], { stdio: "ignore" });
  let ws;
  for (let i = 0; i < 40 && !ws; i++) { try { const l = await (await fetch(`http://127.0.0.1:${port}/json`)).json(); const p = l.find((t) => t.type === "page"); if (p) ws = new WebSocket(p.webSocketDebuggerUrl); } catch {} if (!ws) await sleep(250); }
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  let seq = 0; const wait = new Map(); const logs = [];
  ws.onmessage = (m) => { const d = JSON.parse(m.data);
    if (d.id && wait.has(d.id)) { const [a, b] = wait.get(d.id); wait.delete(d.id); d.error ? b(new Error(d.error.message)) : a(d.result); }
    else if (d.method === "Runtime.consoleAPICalled") logs.push(d.params.type + ": " + d.params.args.map((a) => a.value ?? a.description ?? "").join(" ").slice(0, 400));
    else if (d.method === "Runtime.exceptionThrown") logs.push("EXC: " + (d.params.exceptionDetails.exception?.description || d.params.exceptionDetails.text).slice(0, 400));
    else if (d.method === "Log.entryAdded") logs.push("LOG " + d.params.entry.level + ": " + d.params.entry.text.slice(0, 400)); };
  const send = (method, params = {}) => new Promise((a, b) => { const id = ++seq; wait.set(id, [a, b]); ws.send(JSON.stringify({ id, method, params })); });
  const ev = async (x) => { const r = await send("Runtime.evaluate", { expression: x, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text); return r.result.value; };
  await send("Page.enable"); await send("Runtime.enable"); await send("Log.enable");
  await send("Emulation.setDeviceMetricsOverride", { width: 390, height: 800, deviceScaleFactor: 2, mobile: true });
  await send("Emulation.setTouchEmulationEnabled", { enabled: true, maxTouchPoints: 5 });
  let sid = null;
  const load = async (url, ls = {}) => { if (sid) await send("Page.removeScriptToEvaluateOnNewDocument", { identifier: sid });
    sid = (await send("Page.addScriptToEvaluateOnNewDocument", { source: `try{localStorage.clear();${Object.entries(ls).map(([k, v]) => `localStorage.setItem(${JSON.stringify(k)},${JSON.stringify(v)});`).join("")}}catch{}` })).identifier;
    await send("Page.navigate", { url }); await sleep(3500); };
  const shot = async (name) => { const r = await send("Page.captureScreenshot", { format: "jpeg", quality: 70 }); writeFileSync(join(HERE, name), Buffer.from(r.data, "base64")); };
  const close = async () => { try { await send("Browser.close"); } catch { chrome.kill(); } };
  return { send, ev, load, shot, close, logs };
}
