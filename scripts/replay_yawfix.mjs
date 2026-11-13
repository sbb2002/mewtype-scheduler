// replay_yawfix.mjs — (실험 브랜치 bg-dome-claude-test) 시선 튐 기록 CSV 를 다시 재생해 지금 방식과 「움직임 연동 방위 보정」(bgyawfix.js)을 비교한다.
//   node scripts/replay_yawfix.mjs <기록.csv> [--sweep] [--series 출력.csv] [--k 0.2 --wStill 8 --wMove 8 --tStill 500 --vMax 15]
//   기록 CSV 형식 = src/frontend/js/bggazelog.js 머리 주석(aos · ros · view · mark 줄을 쓴다). 각도 인자는 도(°) · 시간은 ms.
//
// 지금 방식 = 프레임마다 절대 방위(aos)를 목표로, 새 방식 = bgyawfix 의 r + b 를 목표로 — 둘 다 같은 화면 감쇠(updateView 와 같은 식, 배율 1 이면 0.08 초)를 거친다.
// 지표(모두 도):
//   혼자 움직임 = 프레임마다 (화면 방위 변화 − 「상대 방위를 같은 감쇠에 통과시킨 값」의 변화). 사용자가 폰을 돌린 몫(감쇠 지연 포함)을 빼고 남은 화면 움직임.
//   정지 중 = 상대 방위 회전 속도(0.2 초 평균)가 STILL_DPS 미만인 프레임.
//   표시 앞 = 운영자가 「튐」 을 누르기 전 1.5 초 동안 혼자 움직인 누적 각의 최대.
//   절대 오차 = |화면 목표 − 절대 방위|. 지금 방식은 0(절대 방위를 그대로 따르므로), 새 방식이 치르는 값. 정지 중 프레임만 센다(회전 중엔 두 센서 시각 차로 커진다).
import fs from "node:fs";
import { createYawFix, wrap } from "../src/frontend/js/bgyawfix.js";

const DEG = Math.PI / 180, RAD = 180 / Math.PI;
const STILL_DPS = 8;          // 지표용 정지 판정(°/초) — 보정기 인자와 별개로 고정
const YAW_FREEZE = 78;        // bggyro.js 와 같은 값(°)

const args = process.argv.slice(2);
const file = args[0];
const opt = (name, def) => { const i = args.indexOf("--" + name); return i < 0 ? def : Number(args[i + 1]); };
const seriesOut = (() => { const i = args.indexOf("--series"); return i < 0 ? null : args[i + 1]; })();

// ── 기록 읽기 ──
const ev = [], marks = [];
for (const line of fs.readFileSync(file, "utf8").split(/\r?\n/)) {
  const c = line.split(",");
  if (c.length < 3) continue;
  const t = Number(c[0]), k = c[1];
  if (k === "aos" || k === "ros") ev.push({ t, k, yaw: Number(c[2]) * DEG, pitch: Number(c[3]) });
  else if (k === "view") ev.push({ t, k, tele: Number(c[7]) || 1 });
  else if (k === "mark") marks.push(t);
}
ev.sort((x, y) => x.t - y.t);

function run(p, keepSeries = false) {
  const fix = createYawFix({ k: p.k, wStill: p.wStill * DEG, wMove: p.wMove * DEG, tStill: p.tStill, vMax: p.vMax * DEG });
  let aYaw = null, rYaw = null, lastT = null;
  let dOld = null, dNew = null, dR = null, prevOld = null, prevNew = null, prevR = null;
  const rHist = [];            // 지표용 회전 속도
  const fr = [];               // 프레임별 기록
  for (const e of ev) {
    if (e.k === "aos") { const fz = Math.abs(e.pitch) >= YAW_FREEZE; if (!fz) aYaw = e.yaw; fix.onAbs(e.t, e.yaw, fz); continue; }
    if (e.k === "ros") { const fz = Math.abs(e.pitch) >= YAW_FREEZE; if (!fz) rYaw = e.yaw; fix.onRel(e.t, e.yaw, fz); if (!fz) rHist.push([e.t, e.yaw]); continue; }
    // view = 프레임
    if (aYaw == null || rYaw == null) continue;
    const dt = lastT == null ? 1 / 60 : Math.min(0.1, (e.t - lastT) / 1000);
    lastT = e.t;
    const kk = 1 - Math.exp(-dt / (0.08 + 0.36 * Math.log(e.tele) / Math.log(30)));
    const tOld = aYaw, tNew = fix.yaw() ?? aYaw;
    dOld = dOld == null ? tOld : dOld + wrap(tOld - dOld) * kk;
    dNew = dNew == null ? tNew : dNew + wrap(tNew - dNew) * kk;
    dR = dR == null ? rYaw : dR + wrap(rYaw - dR) * kk;   // 기준 = 상대 방위만 감쇠한 화면
    // 회전 속도(0.2 초 창)
    while (rHist.length > 2 && e.t - rHist[0][0] > 200) rHist.shift();
    let ang = 0; for (let i = 1; i < rHist.length; i++) ang += Math.abs(wrap(rHist[i][1] - rHist[i - 1][1]));
    const span = rHist.length > 1 ? (rHist[rHist.length - 1][0] - rHist[0][0]) / 1000 : 0;
    const dps = span > 0 ? ang / span * RAD : 0;
    const f = { t: e.t, still: dps < STILL_DPS, dps, a: aYaw, r: rYaw, old: dOld, nw: dNew, tNew, selfOld: 0, selfNew: 0 };
    if (prevR != null) {
      const dr = wrap(dR - prevR);
      f.selfOld = wrap(dOld - prevOld) - dr;
      f.selfNew = wrap(dNew - prevNew) - dr;
    }
    prevOld = dOld; prevNew = dNew; prevR = dR;
    fr.push(f);
  }

  // ── 지표 ──
  const sum = (arr) => arr.reduce((s, x) => s + x, 0);
  const still = fr.filter((f) => f.still);
  const travel = (key) => sum(still.map((f) => Math.abs(f[key]))) * RAD;
  // 정지 중 혼자 움직인 최대 속도(0.1 초 창 누적 / 0.1)
  const peak = (key) => {
    let best = 0;
    for (let i = 0; i < fr.length; i++) {
      if (!fr[i].still) continue;
      let s = 0;
      for (let j = i; j < fr.length && fr[j].t - fr[i].t <= 100; j++) s += fr[j][key];
      best = Math.max(best, Math.abs(s) * RAD / 0.1);
    }
    return best;
  };
  const markJump = (key) => marks.map((m) => {
    let s = 0, best = 0;
    for (const f of fr) { if (f.t < m - 1500 || f.t > m) continue; s += f[key]; best = Math.max(best, Math.abs(s)); }
    return best * RAD;
  });
  const err = still.map((f) => Math.abs(wrap(f.tNew - f.a)) * RAD).sort((x, y) => x - y);
  const q = (arr, p) => arr.length ? arr[Math.min(arr.length - 1, Math.floor(arr.length * p))] : NaN;
  const res = {
    p, frames: fr.length, stillFrames: still.length,
    travelOld: travel("selfOld"), travelNew: travel("selfNew"),
    peakOld: peak("selfOld"), peakNew: peak("selfNew"),
    markOld: markJump("selfOld"), markNew: markJump("selfNew"),
    errMed: q(err, 0.5), err95: q(err, 0.95), errMax: err[err.length - 1] ?? NaN,
    errOver5: err.filter((x) => x > 5).length / Math.max(1, err.length),
    dbg: null,
  };
  if (keepSeries) res.series = fr;
  return res;
}

const base = { k: opt("k", 0.2), wStill: opt("wStill", 8), wMove: opt("wMove", 8), tStill: opt("tStill", 500), vMax: opt("vMax", 15) };
const f1 = (x) => (Number.isFinite(x) ? x.toFixed(1) : "-");
const f2 = (x) => (Number.isFinite(x) ? x.toFixed(2) : "-");

if (args.includes("--sweep")) {
  console.log("k\twStill\twMove\ttStill\tvMax\t정지중혼자(누적°)\t최대속도°/s\t표시앞최대°(평균)\t절대오차 중앙/95%/최대\t>5°비율");
  const rows = [];
  for (const k of [0.05, 0.1, 0.2, 0.3])
    for (const ws of [5, 8, 12])
      for (const ts of [300, 500, 1000])
        for (const vm of [5, 15, 30]) {
          const r = run({ k, wStill: ws, wMove: ws, tStill: ts, vMax: vm });
          rows.push(r);
        }
  const r0 = rows[0];
  console.log(`(지금 방식)\t\t\t\t\t${f1(r0.travelOld)}\t${f1(r0.peakOld)}\t${f1(r0.markOld.reduce((s, x) => s + x, 0) / Math.max(1, r0.markOld.length))}\t0/0/0\t0`);
  for (const r of rows) {
    const mAvg = r.markNew.reduce((s, x) => s + x, 0) / Math.max(1, r.markNew.length);
    console.log(`${r.p.k}\t${r.p.wStill}\t${r.p.wMove}\t${r.p.tStill}\t${r.p.vMax}\t${f1(r.travelNew)}\t${f1(r.peakNew)}\t${f1(mAvg)}\t${f1(r.errMed)}/${f1(r.err95)}/${f1(r.errMax)}\t${f2(r.errOver5)}`);
  }
} else {
  const r = run(base, !!seriesOut);
  console.log(`파일 ${file}`);
  console.log(`인자 k=${base.k} wStill=${base.wStill}°/s wMove=${base.wMove}°/s tStill=${base.tStill}ms vMax=${base.vMax}°/s`);
  console.log(`프레임 ${r.frames} (정지 ${r.stillFrames})`);
  console.log(`정지 중 혼자 움직인 누적: 지금 ${f1(r.travelOld)}° → 새 ${f1(r.travelNew)}°`);
  console.log(`정지 중 혼자 움직인 최대 속도(0.1 초): 지금 ${f1(r.peakOld)}°/s → 새 ${f1(r.peakNew)}°/s`);
  console.log(`표시 앞 1.5 초 혼자 움직인 최대(표시별): 지금 [${r.markOld.map(f1).join(", ")}] → 새 [${r.markNew.map(f1).join(", ")}]`);
  console.log(`새 방식 절대 오차: 중앙 ${f2(r.errMed)}° · 95% ${f2(r.err95)}° · 최대 ${f2(r.errMax)}° · 5° 넘는 비율 ${f2(r.errOver5)}`);
  if (seriesOut) {
    const lines = ["t,still,dps,a,r,old,new,target_new"];
    for (const f of r.series) lines.push([f.t, f.still ? 1 : 0, f.dps.toFixed(2), ...[f.a, f.r, f.old, f.nw, f.tNew].map((x) => (x * RAD).toFixed(3))].join(","));
    fs.writeFileSync(seriesOut, lines.join("\n") + "\n");
    console.log(`프레임 기록 → ${seriesOut}`);
  }
}
