// bgwarp.selfcheck.mjs — node src/frontend/js/bgwarp.selfcheck.mjs
import { createWarp, shiftGear, tickWarp, warpReady, stoppedAtN, isRed, GEAR_BETA, jumpFrame, JUMP_MS, pickJump, decelBeta, gearPos } from "./bgwarp.js";

let fail = 0;
const ok = (c, m) => { if (!c) { fail++; console.error("FAIL", m); } };

// 레일 위치: a단 속도 = 정확히 a단 눈금(운영자 11-06 버그), 단 사이는 선형, 범위 밖은 끝에 붙음
{
  GEAR_BETA.forEach((v, a) => ok(Math.abs(gearPos(v) - a) < 1e-9, `gearPos(${v}) = ${a}단 ` + gearPos(v)));
  ok(Math.abs(gearPos(0.85) - 3.5) < 1e-9, "레드존 문턱 0.85 = 3.5단 " + gearPos(0.85));
  ok(gearPos(-1) === 0 && gearPos(1.2) === 5, "범위 밖");
  let prev = -1, mono = true; for (let b = 0; b <= 0.99; b += 0.001) { const p = gearPos(b); if (p < prev) mono = false; prev = p; }
  ok(mono, "β 가 늘면 위치도 는다");
}
const run = (st, sec, t0 = 0) => { let t = t0; const dt = 1 / 60; for (let i = 0; i < sec * 60; i++) { t += dt * 1000; tickWarp(st, dt, t); } return t; };

// N → 3 은 1 · 2 를 차례로 지난다
{
  const st = createWarp(); shiftGear(st, 3);
  const seen = new Set(); let t = 0;
  for (let i = 0; i < 300; i++) { t += 1000 / 60; tickWarp(st, 1 / 60, t); seen.add(st.stage); }
  ok(seen.has(1) && seen.has(2) && seen.has(3), "N→3 거침 " + [...seen]);
  ok(Math.abs(st.beta - GEAR_BETA[3]) < 1e-9 && st.mode === "idle", "3단 도착 " + st.beta);
}
// 중간 단은 등속(1 → 2 구간 속도 일정)
{
  const st = createWarp(); shiftGear(st, 3);
  const bs = []; let t = 0;
  for (let i = 0; i < 120; i++) { t += 1000 / 60; tickWarp(st, 1 / 60, t); bs.push(st.beta); }
  const mid = bs.map((b, i) => [b, i ? b - bs[i - 1] : 0]).filter(([b]) => b > 0.32 && b < 0.58).map(([, d]) => d);
  ok(mid.length > 3 && Math.max(...mid) - Math.min(...mid) < 1e-9, "중간 단 등속");
}
// 레드존: 올라가며 떨림 → 표시등 켜짐 · 띵 on → 다 잦아들면 깜빡 1.6초 → 꺼짐 · 띵 off → 워프 가능
{
  const st = createWarp(); shiftGear(st, 5);
  let t = 0, dingOn = 0, dingOff = 0, readyAt = -1;
  for (let i = 0; i < 60 * 20; i++) { t += 1000 / 60; const d = tickWarp(st, 1 / 60, t); if (d === "on") dingOn++; if (d === "off") dingOff++; if (readyAt < 0 && warpReady(st)) readyAt = t; }
  ok(isRed(st) && st.beta === 0.99, "5단 0.99c");
  ok(dingOn === 1 && dingOff === 1, `띵 on ${dingOn} off ${dingOff}`);
  ok(readyAt > 0 && st.belt === "off", "표시등 꺼진 뒤 워프 가능");
  // 레드존 밖(3단)으로 내리면 급제동 → 워프 불가
  shiftGear(st, 3); tickWarp(st, 1 / 60, t + 16);
  let brake = false; for (let i = 0; i < 60; i++) { t += 1000 / 60; tickWarp(st, 1 / 60, t); if (st.mode === "redDecel") brake = true; }
  ok(brake, "레드존에서 내리면 급제동");
  run(st, 6, t);
  ok(!warpReady(st), "레드존 밖이면 워프 불가");
}
// 느린 프레임(dt 0.25초)이어도 단 경계를 넘어 달려 나가지 않고, 가속 중(레드존 진입 전후)엔 워프 불가
{
  const st = createWarp(); shiftGear(st, 5);
  let t = 0, early = false, maxJump = 0, prev = 0;
  for (let i = 0; i < 200; i++) { t += 250; tickWarp(st, 0.25, t); if (warpReady(st) && st.mode !== "idle") early = true; if (st.beta < 0.85) maxJump = Math.max(maxJump, st.beta - prev); prev = st.beta; }
  ok(!early, "가속 중 워프 불가");
  ok(st.beta === 0.99 && warpReady(st), "결국 0.99c · 워프 가능");
}
// N 으로 멈추면 stoppedAtN
{
  const st = createWarp(); shiftGear(st, 2); let t = run(st, 3); shiftGear(st, 0); run(st, 6, t);
  ok(stoppedAtN(st), "N 정지");
  ok(!stoppedAtN(createWarp()), "처음(움직인 적 없음)은 정지 아님");
}
// 점프: 세 연출 모두 끝에 속도 0 근처 · done · 같은 확률 고르기
{
  for (const k of ["A", "B", "C"]) {
    const end = jumpFrame(k, JUMP_MS[k] - 1, 900), done = jumpFrame(k, JUMP_MS[k], 900);
    ok(end.beta < 0.02, `${k} 끝 속도 ${end.beta}`);
    ok(done.done && !jumpFrame(k, 10, 900).done, `${k} done`);
    ok(jumpFrame(k, 0, 900).beta >= 0.94, `${k} 시작 속도`);
  }
  ok(jumpFrame("B", 0, 900).repro >= 0 && jumpFrame("B", 0, 900).red > 0, "B 는 시작부터 고리 · 급제동(멈칫 없음)");
  const cnt = { A: 0, B: 0, C: 0 }; let s = 1;
  const rand = () => { s = (s * 16807) % 2147483647; return s / 2147483647; };
  for (let i = 0; i < 30000; i++) cnt[pickJump(rand)]++;
  ok(Object.values(cnt).every((n) => Math.abs(n - 10000) < 400), "같은 확률 " + JSON.stringify(cnt));
  ok(decelBeta(0) === 0.99 && decelBeta(1) === 0, "감속 0.99 → 0");
}
console.log(fail ? `bgwarp selfcheck ${fail} FAIL` : "bgwarp selfcheck OK");
if (fail) process.exit(1);
