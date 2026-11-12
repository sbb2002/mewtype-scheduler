// bggazelog.js — (실험 브랜치 bg-dome-claude-test 전용 · main 병합 금지) 시선 튐 조사용 기록기. 주소에 ?debug=True 가 있을 때만 bgdomegl.js 가 불러온다.
// 센서 원천별 값과 화면에 그린 시선을 같은 시계(performance.now)로 적어 확인용 서버(scripts/serve_gazelog.py)의 POST /__gazelog 로 보낸다.
// 오른쪽 아래 「튐」 버튼 = 운영자가 화면이 혼자 움직였다고 본 순간을 표시(mark 줄).
//
// CSV 한 줄 = t(ms), kind, 값들. kind 별 값:
//   aos  = AbsoluteOrientationSensor(자력계 포함): yaw°, pitch°, qx, qy, qz, qw
//   ros  = RelativeOrientationSensor(자력계 없음): yaw°, pitch°, qx, qy, qz, qw   — yaw 기준은 임의(변화량만 비교)
//   doa  = deviceorientationabsolute: alpha, beta, gamma
//   do   = deviceorientation: alpha, beta, gamma, absolute(1/0)
//   dm   = devicemotion: 회전 속도 alpha, beta, gamma(°/s), 중력 포함 가속도 x, y, z(m/s²)
//   mag  = Magnetometer(브라우저가 허용할 때만): x, y, z(µT), 세기
//   view = 프레임마다: 앱이 쓰는 방위°(gyroAbs, 편각 포함), 고도°, 화면에 그린 방위°, 고도°, 원천(sensor/event/ios/flag), 배율
//   mark = 「튐」 버튼 누름: 누른 횟수
//   info = 시작 정보 · 센서 오류
import { forwardOfQuat, gyroAbs, gyroDebug } from "./bggyro.js";

const RAD = 180 / Math.PI;
const f2 = (v) => (v == null || Number.isNaN(v) ? "" : Math.round(v * 100) / 100);
const f4 = (v) => (v == null || Number.isNaN(v) ? "" : Math.round(v * 1e4) / 1e4);

export function startGazeLog(getView) {
  const sid = new Date().toISOString().replace(/[-:T]/g, "").slice(0, 14) + "_" + Math.random().toString(36).slice(2, 6);
  let buf = [], sent = 0, fail = 0, marks = 0;
  const row = (kind, ...v) => buf.push([Math.round(performance.now() * 10) / 10, kind, ...v].join(","));
  row("info", "start", Date.now(), JSON.stringify(navigator.userAgent).replace(/,/g, ";"));

  // ── 화면: 오른쪽 아래 버튼 + 상태 줄 ──
  const box = document.createElement("div");
  box.style.cssText = "position:fixed;right:10px;bottom:calc(10px + env(safe-area-inset-bottom,0px));z-index:2147483647;display:flex;flex-direction:column;align-items:flex-end;gap:6px;font:12px/1.3 ui-monospace,monospace;pointer-events:none";
  const stat = document.createElement("div");
  stat.style.cssText = "background:rgba(0,0,0,.6);color:#fff;padding:3px 6px;border-radius:6px;white-space:pre;text-align:right";
  const btn = document.createElement("button");
  btn.type = "button";
  btn.textContent = "튐";
  btn.style.cssText = "pointer-events:auto;width:76px;height:76px;border-radius:50%;border:3px solid #fff;background:#e23b3b;color:#fff;font:700 24px system-ui,sans-serif;touch-action:manipulation;-webkit-user-select:none;user-select:none";
  box.append(stat, btn);
  document.body.append(box);
  const stop = (e) => e.stopPropagation();
  for (const t of ["touchstart", "touchmove", "touchend", "pointerup", "click", "mousedown"]) btn.addEventListener(t, stop);
  btn.addEventListener("pointerdown", (e) => {
    e.stopPropagation();
    e.preventDefault();
    marks++;
    row("mark", marks);
    btn.style.background = "#fff"; btn.style.color = "#e23b3b";
    setTimeout(() => { btn.style.background = "#e23b3b"; btn.style.color = "#fff"; }, 250);
    if (navigator.vibrate) navigator.vibrate(30);
    flush();
  });

  // ── 보내기 ──
  let busy = false;
  async function flush() {
    if (busy || !buf.length) return;
    busy = true;
    const lines = buf; buf = [];
    try {
      const r = await fetch("/__gazelog?sid=" + sid, { method: "POST", headers: { "Content-Type": "text/plain" }, body: lines.join("\n") + "\n" });
      if (!r.ok) throw new Error(String(r.status));
      sent += lines.length; fail = 0;
    } catch {
      fail++; buf = lines.concat(buf);
      if (buf.length > 200000) buf = buf.slice(-200000);
    }
    busy = false;
  }
  setInterval(flush, 1000);
  document.addEventListener("visibilitychange", () => { if (document.hidden) flush(); });

  // ── 원천별 기록 ──
  const cnt = { aos: 0, ros: 0, doa: 0, do: 0, dm: 0, mag: 0 };
  const sensors = {};
  function quatSensor(kind, Cls) {
    if (sensors[kind]) return;
    if (typeof Cls !== "function") { row("info", kind, "none"); sensors[kind] = "none"; return; }
    try {
      const s = new Cls({ frequency: 60, referenceFrame: "device" });
      s.addEventListener("reading", () => {
        const q = s.quaternion; if (!q) return;
        const f = forwardOfQuat(q);
        cnt[kind]++;
        row(kind, f2(Math.atan2(f[0], f[1]) * RAD), f2(Math.asin(Math.max(-1, Math.min(1, f[2]))) * RAD), f4(q[0]), f4(q[1]), f4(q[2]), f4(q[3]));
      });
      s.addEventListener("error", (e) => { row("info", kind, "error", (e.error && e.error.name) || ""); sensors[kind] = null; });
      s.start();
      sensors[kind] = s;
    } catch (err) { row("info", kind, "throw", err && err.name); }
  }
  function magSensor() {
    if (sensors.mag) return;
    if (typeof window.Magnetometer !== "function") { row("info", "mag", "none"); sensors.mag = "none"; return; }
    try {
      const s = new window.Magnetometer({ frequency: 20 });
      s.addEventListener("reading", () => { cnt.mag++; row("mag", f2(s.x), f2(s.y), f2(s.z), f2(Math.hypot(s.x, s.y, s.z))); });
      s.addEventListener("error", (e) => { row("info", "mag", "error", (e.error && e.error.name) || ""); sensors.mag = null; });
      s.start();
      sensors.mag = s;
    } catch (err) { row("info", "mag", "throw", err && err.name); }
  }
  const startSensors = () => { quatSensor("aos", window.AbsoluteOrientationSensor); quatSensor("ros", window.RelativeOrientationSensor); magSensor(); };
  startSensors();
  window.addEventListener("pointerdown", startSensors, { once: true, capture: true });   // 권한이 첫 터치 뒤에 열리는 기기 대비 — 한 번 더 시도
  window.addEventListener("deviceorientationabsolute", (e) => { cnt.doa++; row("doa", f2(e.alpha), f2(e.beta), f2(e.gamma)); });
  window.addEventListener("deviceorientation", (e) => { cnt.do++; row("do", f2(e.alpha), f2(e.beta), f2(e.gamma), e.absolute ? 1 : 0); });
  window.addEventListener("devicemotion", (e) => {
    const r = e.rotationRate || {}, a = e.accelerationIncludingGravity || {};
    cnt.dm++;
    row("dm", f2(r.alpha), f2(r.beta), f2(r.gamma), f2(a.x), f2(a.y), f2(a.z));
  });

  // ── 프레임마다: 앱이 쓰는 방위와 화면에 그린 시선 ──
  let lastStat = 0;
  function frame(now) {
    const a = gyroAbs(), v = getView();
    row("view", a ? f2(a.yaw * RAD) : "", a ? f2(a.pitch * RAD) : "", f2(v.yaw * RAD), f2(v.pitch * RAD), gyroDebug.src || "", f2(v.tele));
    if (now - lastStat > 500) {
      lastStat = now;
      stat.textContent = `REC ${sent}${fail ? " 전송실패 " + fail : ""}\nsrc ${gyroDebug.src || "-"} · 튐 ${marks}\naos ${cnt.aos} ros ${cnt.ros} mag ${cnt.mag}\ndoa ${cnt.doa} do ${cnt.do} dm ${cnt.dm}`;
      stat.style.background = fail ? "rgba(200,0,0,.8)" : "rgba(0,0,0,.6)";
    }
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}
