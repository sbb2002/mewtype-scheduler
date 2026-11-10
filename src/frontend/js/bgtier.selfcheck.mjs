// bgtier.selfcheck.mjs — node src/frontend/js/bgtier.selfcheck.mjs
// (bg-dome, 11-10) 등급 판정 · 주소 우선순위 · 저장소 없는 환경의 안전 동작
import { resolveTier, judge, readStoredTier, writeStoredTier, clearStoredTier } from "./bgtier.js";

let fail = 0;
const ok = (c, m) => { if (!c) { fail++; console.error("FAIL", m); } };
const rep = (ms, n) => Array(n).fill(ms);

// 60fps 표본 → high (처음 1.5초 · 2초 이상 분량)
ok(judge(rep(1000 / 60, 300)) === "high", "60fps → high");
// 30fps → low
ok(judge(rep(1000 / 30, 300)) === "low", "30fps → low");
// 처음 1.5초만 느리고 그 뒤 60fps → high (첫 준비 렉은 버린다)
{
  const s = [...rep(100, 15), ...rep(1000 / 60, 300)];   // 느린 구간 1.5초 정확히 — 그 뒤는 빠름
  ok(judge(s) === "high", "처음 1.5초 느림 후 60fps → high");
}
// 간헐 긴 프레임 15% → low (평균은 45fps 이상이 되도록: 기본 12ms, 긴 프레임 60ms)
{
  const s = [];
  for (let i = 0; i < 400; i++) s.push(i % 100 < 15 ? 60 : 12);   // 긴 프레임 15%, 평균 약 19.2ms(약 52fps)
  ok(judge(s) === "low", "긴 프레임 15% → low");
}
// 긴 프레임 5%(평균 빠름) → high
{
  const s = [];
  for (let i = 0; i < 400; i++) s.push(i % 100 < 5 ? 60 : 16.7);
  ok(judge(s) === "high", "긴 프레임 5% → high");
}
// 표본 부족 → null (1.5초 이하, 또는 버린 뒤 2초 미만)
ok(judge([]) === null, "빈 표본 → null");
ok(judge(rep(16.7, 60)) === null, "1초 분량 → null");
ok(judge(rep(16.7, 100)) === null, "버린 뒤 2초 안 되면 null (1.67초 분량 전부 버림)");
ok(judge(rep(33.3, 50)) === null, "1.67초 분량 → null");
// 이상한 값(음수 · NaN)은 무시
ok(judge([NaN, -5, ...rep(1000 / 30, 300)]) === "low", "NaN · 음수 무시");

// resolveTier 우선순위: 주소 강제 > 기억값 > 기본(high + 실측)
{
  let r = resolveTier("?bgtier=low", "high");
  ok(r.tier === "low" && r.measure === false, "주소 low 가 기억 high 를 이김");
  r = resolveTier("?bgtier=high", "low");
  ok(r.tier === "high" && r.measure === false, "주소 high 가 기억 low 를 이김");
  r = resolveTier("", "low");
  ok(r.tier === "low" && r.measure === false, "기억값 low");
  r = resolveTier("", null);
  ok(r.tier === "high" && r.measure === true, "기억 없음 → high + 실측");
  r = resolveTier("?bgtier=reset", "low");
  ok(r.tier === "high" && r.measure === true, "reset 은 기억을 무시하고 다시 잰다");
  r = resolveTier("?bgtier=bogus", "low");
  ok(r.tier === "low" && r.measure === false, "알 수 없는 값은 무시하고 기억값을 쓴다");
  r = resolveTier("?bgdebug&bgtier=low", undefined);
  ok(r.tier === "low", "다른 파라미터와 함께 와도 읽는다");
}

// 저장소가 없는 환경(node 는 localStorage 가 없다) — 예외 없이 null · 무시
{
  let threw = false;
  try { ok(readStoredTier() === null, "저장소 없음 → null"); writeStoredTier("low"); clearStoredTier(); } catch { threw = true; }
  ok(!threw, "저장소 없어도 예외 없음");
}

console.log(fail ? `bgtier self-check 실패 ${fail}건` : "bgtier self-check 통과");
if (fail) process.exitCode = 1;
