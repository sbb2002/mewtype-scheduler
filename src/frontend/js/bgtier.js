// bgtier.js — (bg-dome, 11-10) 돔 배경 성능 등급. DOM · WebGL 없음(순수 판정, self-check = bgtier.selfcheck.mjs).
// 등급(tier) 두 가지: "high" = 지금과 같은 풀 퍼포먼스 · "low" = CPU 부담을 줄인 낮은 퍼포먼스
//   (해상도 상한 1배 · 배경 보기 중 화면 갱신 30fps · 예고보드가 떠 있을 때(bg-peek 없음) 배경 정지).
//
// (11-13 운영자 「웹 첫 입장 시 매번 측정, 새로고침해도 측정. 일시적으로 원인 모르게 low 로 판정되어도 다시 high 로 판정될 수 있게」)
//   전엔 한 번 잰 값을 기기에 영구 저장했다 — 새 주소(Tailscale 포트)에서 첫 측정이 low 로 나와 S23 이 30fps 에 묶인 일이 있었다.
//   지금: ① 주소 ?bgtier=low|high 면 그 등급으로 고정(확인용) ② 아니면 들어올 때마다 high 로 시작해 배경 보기 중 계속 잰다(createTierMeter).
//   기기 저장은 하지 않는다. 옛 저장값(localStorage "bgtier")은 들어올 때 지운다(clearStoredTier).
//
// 실측 판정(judge): 한 회차 = 처음 1.5초 분량은 버리고(준비 렉), 그 뒤 2초 분량이 모이면 판정 — 평균 45fps 미만이거나
//   50ms 넘는 프레임이 10% 넘으면 low. high 인 동안은 회차를 계속 이어 잰다(나빠지면 low).
// 재시험*: low 가 되면 배경 보기 시간으로 20초 뒤 high 로 다시 올려 한 회차를 잰다 — high 면 그대로 high, 또 low 면 low 로 돌아가고
//   다음 재시험까지 40 · 80 · 160초(상한)로 늘린다. high 가 한 번 나오면 간격은 처음(20초)으로.
//   * 재시험 = low 상태에서 일정 시간 뒤 잠깐 high 로 올려 다시 재 보는 것. low 상태 그대로는 30fps 로 그려 실제 성능을 잴 수 없어서다.

export const TIER_KEY = "bgtier";   // 옛 저장 키 — 지금은 지우기만 한다
export const SKIP_MS = 1500;      // (bg-dome, 11-10) 판정에서 버리는 첫 분량(ms) — 준비 렉
export const MIN_MS = 2000;       // (bg-dome, 11-10) 판정에 필요한 분량(ms)
export const SLOW_FPS = 45;       // (bg-dome, 11-10) 평균 이 값 미만이면 low
export const LONG_MS = 50;        // (bg-dome, 11-10) 「긴 프레임」 기준(ms)
export const LONG_RATIO = 0.10;   // (bg-dome, 11-10) 긴 프레임 비율이 이 값을 넘으면 low
export const PROBE_MS = [20000, 40000, 80000, 160000];   // (11-13) low 뒤 재시험까지 배경 보기 시간(ms) — 연속으로 low 면 다음 칸, 끝 칸에서 멈춤

/** 주소로 등급을 고른다. fixed = true 면 주소가 정한 등급으로 고정(측정 안 함) */
export function resolveTier(search) {
  const v = new URLSearchParams(search || "").get("bgtier");
  if (v === "low" || v === "high") return { tier: v, fixed: true };
  return { tier: "high", fixed: false };
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

/**
 * 계속 재는 등급 측정기. start = 시작 등급, fixed = 주소로 고정(아무것도 바꾸지 않음).
 * tick(t, active) 를 rAF 마다 부른다 — active = 배경 보기 중 · 탭이 보임. 바뀐 등급("high" | "low")을 돌려주고, 안 바뀌면 null.
 * 배경 보기를 닫거나 탭이 가려지면 그 회차 표본은 버리고, 재시험 시계도 멈춘다(배경 보기 시간만 센다).
 */
export function createTierMeter(start = "high", fixed = false) {
  let tier = start, samples = [], lastT = 0, lowFor = 0, lowLastT = 0, strikes = 0, probing = false, changes = 0;
  const reset = () => { samples = []; lastT = 0; };
  return {
    get tier() { return tier; },
    get fixed() { return fixed; },
    /** 지금 재는 중인가(high 인 동안) */
    get measuring() { return !fixed && tier === "high"; },
    /** 재시험 회차인가(low 뒤 잠깐 high 로 올려 재는 중) */
    get probing() { return probing; },
    /** 다음 재시험까지 남은 배경 보기 시간(ms) — low 일 때만, 아니면 0 */
    get probeIn() { return tier === "low" && !fixed ? Math.max(0, PROBE_MS[Math.min(strikes, PROBE_MS.length - 1)] - lowFor) : 0; },
    get samples() { return samples.length; },
    /** 이번 방문에서 등급이 바뀐 횟수(확인용) */
    get changes() { return changes; },
    tick(t, active) {
      if (fixed) return null;
      if (!active) { reset(); lowLastT = 0; return null; }
      if (tier === "low") {
        if (lowLastT) lowFor += Math.min(250, t - lowLastT);   // 잠깐 멈춘 틈(백그라운드 등)은 크게 세지 않는다
        lowLastT = t;
        if (lowFor < PROBE_MS[Math.min(strikes, PROBE_MS.length - 1)]) return null;
        tier = "high"; probing = true; lowFor = 0; lowLastT = 0; reset(); changes++;
        return "high";
      }
      if (lastT) samples.push(t - lastT);
      lastT = t;
      const v = judge(samples);
      if (v == null) return null;
      reset();   // 다음 회차(처음 1.5초는 다시 버린다)
      if (v === "high") { probing = false; strikes = 0; return null; }
      if (probing) strikes++;   // 재시험에서도 low — 다음 재시험까지 더 기다린다
      probing = false; tier = "low"; lowFor = 0; lowLastT = 0; changes++;
      return "low";
    },
  };
}

/** 옛 저장값 지우기 — 등급은 더 이상 기기에 저장하지 않는다(11-13) */
export function clearStoredTier() {
  try { localStorage.removeItem(TIER_KEY); } catch { /* 저장 불가 */ }
}
