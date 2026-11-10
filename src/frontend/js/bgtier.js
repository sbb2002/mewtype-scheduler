// bgtier.js — (bg-dome, 11-10) 돔 배경 성능 등급. DOM · WebGL 없음(순수 판정 + 기기 저장 하나, self-check = bgtier.selfcheck.mjs).
// 등급(tier) 두 가지: "high" = 지금과 같은 풀 퍼포먼스 · "low" = CPU 부담을 줄인 낮은 퍼포먼스
//   (해상도 상한 1배 · 배경 보기 중 화면 갱신 30fps · 예고보드가 떠 있을 때(bg-peek 없음) 배경 정지).
// 등급 정하기: ① 주소 ?bgtier=low|high 가 최우선(확인용) ② 이 기기에 기억된 값(localStorage "bgtier") ③ 없으면 high 로 시작하고
//   배경 보기 중 프레임 간격을 재서 정한다(bgdomegl.js 가 measureTier 로 모은다). ?bgtier=reset 은 기억을 지우고 다시 잰다.
// 실측 판정(judge): 처음 1.5초 분량은 버리고(첫 준비 렉), 그 뒤 2초 분량이 모이면 판정 — 평균 45fps 미만이거나
//   50ms 넘는 프레임이 10% 넘으면 low.

export const TIER_KEY = "bgtier";
export const SKIP_MS = 1500;      // (bg-dome, 11-10) 판정에서 버리는 첫 분량(ms) — 첫 준비 렉
export const MIN_MS = 2000;       // (bg-dome, 11-10) 판정에 필요한 분량(ms)
export const SLOW_FPS = 45;       // (bg-dome, 11-10) 평균 이 값 미만이면 low
export const LONG_MS = 50;        // (bg-dome, 11-10) 「긴 프레임」 기준(ms)
export const LONG_RATIO = 0.10;   // (bg-dome, 11-10) 긴 프레임 비율이 이 값을 넘으면 low

/** 주소 · 기억값으로 등급을 고른다. measure = true 면 배경 보기 중 실측이 필요하다(주소 강제 · 기억값이 있으면 false). */
export function resolveTier(search, stored) {
  const v = new URLSearchParams(search || "").get("bgtier");
  if (v === "low" || v === "high") return { tier: v, measure: false };
  const s = v === "reset" ? null : stored;   // reset = 기억값을 무시하고 다시 잰다
  if (s === "low" || s === "high") return { tier: s, measure: false };
  return { tier: "high", measure: true };
}

/** 프레임 간격(ms) 표본으로 등급을 판정한다. 표본이 모자라면 null. */
export function judge(samples) {
  let acc = 0, sum = 0, n = 0, long = 0;
  for (const d of samples) {
    if (!Number.isFinite(d) || d < 0) continue;
    if (acc < SKIP_MS) { acc += d; continue; }   // 첫 1.5초 분량 버림
    sum += d; n++;
    if (d > LONG_MS) long++;
  }
  if (n === 0 || sum < MIN_MS) return null;
  const fps = n / (sum / 1000);
  return fps < SLOW_FPS || long / n > LONG_RATIO ? "low" : "high";
}

/** 기억된 등급 읽기 — 없거나 저장소를 못 쓰면 null */
export function readStoredTier() {
  try {
    const v = localStorage.getItem(TIER_KEY);
    return v === "low" || v === "high" ? v : null;
  } catch { return null; }
}

/** 등급 기억 — 저장소를 못 쓰면 조용히 넘어간다(다음 방문에 다시 잰다) */
export function writeStoredTier(tier) {
  try { localStorage.setItem(TIER_KEY, tier); } catch { /* 저장 불가 — 기억 없이 진행 */ }
}

/** 기억 지우기(?bgtier=reset) */
export function clearStoredTier() {
  try { localStorage.removeItem(TIER_KEY); } catch { /* 저장 불가 */ }
}
