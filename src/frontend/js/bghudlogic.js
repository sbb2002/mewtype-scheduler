// bghudlogic.js — (bg-dome 해금 2단계) 시선 HUD 의 순수 계산. DOM 없음(self-check = bghudlogic.selfcheck.mjs).
// 정본 = devpapers ref/bg-dome/hud/hud_f5.html(F5 시안) · HUD_IDEAS.md 「F5 에서 정한 것」.
//
// 좌표: 돔 좌표 = bgdomegl.js basis() 와 같음 — x 오른쪽(동), y 위, z 앞(북). 방위 az 는 북 0° 에서 시계 방향, 고도 alt 는 수평 0°.
// 우주 좌표 = 셰이더 spaceBase(uSpaceRot * d) 의 좌표 — 돔 → 우주 = M · d, 우주 → 돔 = Mᵀ · s(M = spaceRot, 열 우선 3×3).

const DEG = Math.PI / 180;

export function dirFromAzAlt(az, alt) {
  const a = az * DEG, e = alt * DEG, c = Math.cos(e);
  return [c * Math.sin(a), Math.sin(e), c * Math.cos(a)];
}
export function azAltOf(d) {
  return [((Math.atan2(d[0], d[2]) / DEG) % 360 + 360) % 360, Math.asin(Math.max(-1, Math.min(1, d[1]))) / DEG];
}
/** 두 방향 사이 각(도) */
export function sepDeg(a, b) {
  const c = a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  return Math.acos(Math.max(-1, Math.min(1, c))) / DEG;
}
/** 돔 → 우주(M · d) */
export function toSpace(m, d) { return [m[0] * d[0] + m[3] * d[1] + m[6] * d[2], m[1] * d[0] + m[4] * d[1] + m[7] * d[2], m[2] * d[0] + m[5] * d[1] + m[8] * d[2]]; }
/** 우주 → 돔(Mᵀ · s) */
export function toDome(m, s) { return [m[0] * s[0] + m[1] * s[1] + m[2] * s[2], m[3] * s[0] + m[4] * s[1] + m[5] * s[2], m[6] * s[0] + m[7] * s[1] + m[8] * s[2]]; }
/** 방위 차(−180 ~ 180) */
export const wrap180 = (d) => ((d % 360) + 540) % 360 - 180;

/** 시선(fwd)에서 허용 각(tol) 안의 대상 중 가장 가까운 것. 대상 = { dir, tol, hidden? } */
export function pickHit(fwd, targets) {
  let best = null, bd = Infinity;
  for (const t of targets) {
    if (t.hidden) continue;
    const d = sepDeg(fwd, t.dir);
    if (d < t.tol && d < bd) { bd = d; best = t; }
  }
  return best;
}

/**
 * 바라보기 판정(F5 그대로): 대상이 허용 각 안이면 링이 FILL 초에 차고, 벗어나면 DECAY 초에 걸쳐 줄어 0 이면 사라진다.
 * 다 차면 「잡힘」 — 시선이 LEAVE_DEG 안이면 유지, 밖으로 LEAVE_S 초 넘게 나가 있으면 풀린다(폰을 들고 버튼을 누르다 조준이 풀리지 않게).
 * 잡힌 동안 다른 대상을 겨누면 그 대상으로 넘어간다.
 */
export const FILL_S = 2, DECAY_S = 3, LEAVE_DEG = 15, LEAVE_S = 3;
export function createDwell() {
  return { focus: null, v: 0, lock: null, left: 0 };
}
/** 한 걸음. hit = pickHit 결과, sepToLock = 시선과 잡힌 대상 사이 각. 돌려줌 = 이번에 새로 잡힌 대상(없으면 null) */
export function stepDwell(st, hit, sepToLock, dt) {
  if (st.lock) {
    if (hit && hit !== st.lock && hit.id !== st.lock.id) { st.lock = null; st.focus = hit; st.v = 0; st.left = 0; }
    else if (sepToLock > LEAVE_DEG) { st.left += dt; if (st.left > LEAVE_S) { st.lock = null; st.focus = null; st.v = 0; st.left = 0; } return null; }
    else { st.left = 0; return null; }
  }
  if (hit) {
    if (!st.focus || st.focus.id !== hit.id) { st.focus = hit; st.v = 0; }
    st.v = Math.min(1, st.v + dt / FILL_S);
    if (st.v >= 1) { st.lock = hit; st.left = 0; return hit; }
  } else if (st.focus) {
    st.v -= dt / DECAY_S;
    if (st.v <= 0) { st.v = 0; st.focus = null; }
  }
  return null;
}
/** 잡힘 · 링 상태를 비운다(배경 보기를 닫거나 패널이 뜰 때) */
export function resetDwell(st) { st.focus = null; st.v = 0; st.lock = null; st.left = 0; }

/**
 * 방위 테이프 위 힌트 점 — 못 찾은 대상의 방위 차(테이프 보이는 폭 ±half 밖이면 끝에 붙임) · 가까울수록 진하게(60° 에서 0.35).
 * 돌려줌 = [{ dx(−half ~ half), out(−1 · 0 · 1), alpha, below }]
 */
export function beacons(yawDeg, fwd, targets, half) {
  const out = [];
  for (const t of targets) {
    if (t.found || t.noBeacon) continue;
    const [az, alt] = azAltOf(t.dir);
    const dh = wrap180(az - yawDeg);
    const o = dh < -half ? -1 : dh > half ? 1 : 0;
    out.push({ dx: Math.max(-half, Math.min(half, dh)), out: o, alpha: 0.35 + 0.65 * (1 - Math.min(1, sepDeg(fwd, t.dir) / 60)), below: !!t.below || alt < -2 });
  }
  return out;
}

/** a 를 b 로 돌리는 돌림 행렬(열 우선 3×3, R · a = b, 로드리게스). a · b 는 단위 벡터 */
export function rotFromTo(a, b) {
  const v = [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
  const c = a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  if (c < -0.999999) {   // 정반대 — a 에 수직인 아무 축으로 180°
    const p = Math.abs(a[0]) < 0.9 ? [1, 0, 0] : [0, 1, 0];
    let x = [a[1] * p[2] - a[2] * p[1], a[2] * p[0] - a[0] * p[2], a[0] * p[1] - a[1] * p[0]];
    const l = Math.hypot(...x); x = x.map((q) => q / l);
    return [2 * x[0] * x[0] - 1, 2 * x[0] * x[1], 2 * x[0] * x[2], 2 * x[1] * x[0], 2 * x[1] * x[1] - 1, 2 * x[1] * x[2], 2 * x[2] * x[0], 2 * x[2] * x[1], 2 * x[2] * x[2] - 1];
  }
  const k = 1 / (1 + c);
  // 행 우선 R = I + [v]× + [v]×² · k → 열 우선으로
  const r = [
    [1 - k * (v[1] * v[1] + v[2] * v[2]), -v[2] + k * v[0] * v[1], v[1] + k * v[0] * v[2]],
    [v[2] + k * v[0] * v[1], 1 - k * (v[0] * v[0] + v[2] * v[2]), -v[0] + k * v[1] * v[2]],
    [-v[1] + k * v[0] * v[2], v[0] + k * v[1] * v[2], 1 - k * (v[0] * v[0] + v[1] * v[1])],
  ];
  return [r[0][0], r[1][0], r[2][0], r[0][1], r[1][1], r[2][1], r[0][2], r[1][2], r[2][2]];
}
/** 열 우선 3×3 곱 a · b */
export function mulM(a, b) {
  const o = new Array(9);
  for (let col = 0; col < 3; col++) for (let row = 0; row < 3; row++) o[col * 3 + row] = a[row] * b[col * 3] + a[3 + row] * b[col * 3 + 1] + a[6 + row] * b[col * 3 + 2];
  return o;
}
/** 우주 돌림 m0 을 고쳐 우주 방향 s 가 돔 방향 t 에 맺히게 한다(toDome(결과, s) = t) — 워프 도착 때 사진이 보이는 자리에 오게 */
export function aimSpace(m0, s, t) { return mulM(m0, rotFromTo(t, toDome(m0, s))); }
