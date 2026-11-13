// bgtier.selfcheck.mjs — node src/frontend/js/bgtier.selfcheck.mjs
// (bg-dome, 11-10) 등급 판정 · 주소 고정 / (11-13) 매 방문 측정 · low 뒤 재시험 · 저장소 없는 환경의 안전 동작
import { resolveTier, judge, createTierMeter, clearStoredTier, PROBE_MS } from "./bgtier.js";

let fail = 0;
const ok = (c, m) => { if (!c) { fail++; console.error("FAIL", m); } };
const rep = (ms, n) => Array(n).fill(ms);

// ── judge(11-10 그대로)
ok(judge(rep(1000 / 60, 300)) === "high", "60fps → high");
ok(judge(rep(1000 / 30, 300)) === "low", "30fps → low");
ok(judge([...rep(100, 15), ...rep(1000 / 60, 300)]) === "high", "처음 1.5초 느림 후 60fps → high");
{ const s = []; for (let i = 0; i < 400; i++) s.push(i % 100 < 15 ? 60 : 12); ok(judge(s) === "low", "긴 프레임 15% → low"); }
{ const s = []; for (let i = 0; i < 400; i++) s.push(i % 100 < 5 ? 60 : 16.7); ok(judge(s) === "high", "긴 프레임 5% → high"); }
ok(judge([]) === null, "빈 표본 → null");
ok(judge(rep(16.7, 60)) === null, "1초 분량 → null");
ok(judge(rep(16.7, 100)) === null, "버린 뒤 2초 안 되면 null");
ok(judge([NaN, -5, ...rep(1000 / 30, 300)]) === "low", "NaN · 음수 무시");

// ── resolveTier — 주소만 본다(기기 저장 없음)
{
  let r = resolveTier("?bgtier=low"); ok(r.tier === "low" && r.fixed, "주소 low → 고정");
  r = resolveTier("?bgtier=high"); ok(r.tier === "high" && r.fixed, "주소 high → 고정");
  r = resolveTier(""); ok(r.tier === "high" && !r.fixed, "주소 없음 → high 로 시작 · 측정");
  r = resolveTier("?bgtier=reset"); ok(r.tier === "high" && !r.fixed, "옛 reset 값 → 그냥 측정");
  r = resolveTier("?bgdebug&bgtier=low"); ok(r.tier === "low", "다른 파라미터와 함께 와도 읽는다");
}

// ── createTierMeter — 프레임 간격 dt 로 ms 만큼 돌린다. 바뀐 등급 목록을 돌려준다
function run(m, ms, dt, active = true, t0 = { t: 0 }) {
  const out = [];
  for (let e = 0; e < ms; e += dt) { t0.t += dt; const v = m.tick(t0.t, active); if (v) out.push(v); }
  return out;
}
{
  // 빠른 기기 — 계속 high, 바뀜 없음
  const m = createTierMeter(), c = { t: 0 };
  ok(run(m, 20000, 1000 / 60, true, c).length === 0 && m.tier === "high", "60fps 20초 → 계속 high");
}
{
  // 일시적으로 느려짐(4초) → low → 20초 뒤 재시험에서 빠르면 high 로 돌아온다(운영자 요구)
  const m = createTierMeter(), c = { t: 0 };
  const a = run(m, 4000, 1000 / 20, true, c);
  ok(a.join() === "low" && m.tier === "low", "느린 4초 → low");
  ok(m.probeIn > 0 && m.probeIn <= PROBE_MS[0], "low 뒤 재시험 대기");
  const b = run(m, PROBE_MS[0] + 100, 1000 / 60, true, c);
  ok(b.join() === "high" && m.probing, "20초 뒤 재시험 → high 로 올림");
  run(m, 4000, 1000 / 60, true, c);
  ok(m.tier === "high" && !m.probing, "재시험에서 빠름 → high 유지");
}
{
  // 정말 느린 기기 — 재시험마다 low, 간격이 20 → 40 → 80 → 160(상한)으로 늘어난다
  const m = createTierMeter(), c = { t: 0 };
  run(m, 4000, 1000 / 20, true, c);
  ok(m.tier === "low", "느린 기기 → low");
  const waits = [];
  for (let i = 0; i < 5; i++) {
    waits.push(Math.round(m.probeIn / 1000));
    run(m, m.probeIn + 50, 1000 / 20, true, c);   // 재시험 시점까지(low 동안)
    ok(m.tier === "high" && m.probing, `재시험 ${i + 1} 시작`);
    run(m, 4000, 1000 / 20, true, c);             // 재시험 회차도 느림
    ok(m.tier === "low", `재시험 ${i + 1} → 다시 low`);
  }
  ok(waits.join() === "20,40,80,160,160", "재시험 간격 20 · 40 · 80 · 160 · 160초: " + waits.join());
}
{
  // 배경 보기를 닫은 동안은 재시험 시계가 멈춘다
  const m = createTierMeter(), c = { t: 0 };
  run(m, 4000, 1000 / 20, true, c);
  const before = m.probeIn;
  run(m, 60000, 1000 / 60, false, c);
  ok(m.tier === "low" && m.probeIn === before, "배경 보기 밖 60초 → 재시험 시계 그대로");
}
{
  // 주소 고정이면 아무것도 바꾸지 않는다
  const m = createTierMeter("low", true), c = { t: 0 };
  ok(run(m, 60000, 1000 / 60, true, c).length === 0 && m.tier === "low" && !m.measuring, "주소 low 고정 → 그대로");
}

// 저장소가 없는 환경(node) — 예외 없음
{ let threw = false; try { clearStoredTier(); } catch { threw = true; } ok(!threw, "저장소 없어도 예외 없음"); }

console.log(fail ? `bgtier self-check 실패 ${fail}건` : "bgtier self-check 통과");
if (fail) process.exitCode = 1;
