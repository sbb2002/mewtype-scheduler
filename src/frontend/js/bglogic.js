// bglogic.js — (v4.9.8) 배경 장식 순수 로직: 장식 배치 · 낙서 선 · 흔들기 물리 · 센서 세기. DOM 없음(그리는 쪽은 bgdeco.js).
//
// 장식 = 로고에 있는 도형(동그라미 · 삼각형 · 물결 · 점 · 마름모)을 가장자리에 흩뿌린 것. 평소엔 CSS 로 느리게 떠다니고,
// 폰을 흔들면 장식마다 무작위 방향 · 속도로 튀어 나가 벽 · 다른 장식에 부딪히며 회전한다(속도 · 마찰 적분은 프레임마다).

export const KINDS = ["ring", "tri", "wave", "dot", "gem"];

// 장식 자리 — 화면 가로 · 세로의 비율. 가운데(카드가 있는 곳)는 비워 둔다.
export const SPOTS = [
  [0.08, 0.07], [0.92, 0.10], [0.05, 0.33], [0.95, 0.40], [0.09, 0.60], [0.91, 0.66],
  [0.50, 0.95], [0.20, 0.90], [0.80, 0.92], [0.05, 0.82], [0.96, 0.83],
];

export const SHAKE_THRESHOLD = 14;   // m/s² — 이 가속도를 넘으면 흔든 것
export const SHAKE_GAP_MS = 120;     // 흔들기 사이 최소 간격(연속으로 흔들 수 있다)

/** 같은 씨앗이면 같은 수열 — 화면을 다시 그려도 장식이 같은 모양 */
export function rng(seed) {
  let s = seed;
  return () => (s = (s * 16807) % 2147483647) / 2147483647;
}

/** 장식 크기 기준 = 화면 짧은 변 */
export function unitOf(W, H) { return Math.min(W, H) * 0.04; }

/** 장식 목록: 자리 · 종류 · 처음 각도 · 떠다니는 방향 · 주기 */
export function layout(W, H, seed = 21) {
  const r = rng(seed), u = unitOf(W, H);
  return SPOTS.map(([fx, fy], i) => ({
    kind: KINDS[i % 5],
    x: W * fx, y: H * fy, u,
    ang: Math.round(r() * 360),
    dx: (r() - 0.5) * u * 1.6, dy: (r() - 0.5) * u * 1.6,   // 떠다니는 폭(장식 크기의 ±0.8배)
    dur: 9 + r() * 7, delay: -r() * 12,                      // 9~16초 주기, 시작 시점도 제각각
  }));
}

/** 아래쪽 긴 낙서 선(지그재그) 경로 */
export function scribblePath(W, H, seed = 21) {
  const r = rng(seed + 99), n = 24, amp = H * 0.012;
  const x0 = W * 0.06, y0 = H * 0.97, x1 = W * 0.94, y1 = H * 0.92;
  const dx = x1 - x0, dy = y1 - y0, len = Math.hypot(dx, dy), nx = -dy / len, ny = dx / len;
  let d = "";
  for (let i = 0; i <= n; i++) {
    const t = i / n, o = (i % 2 ? 1 : -1) * amp * (0.35 + r() * 0.65), j = (r() - 0.5) * (len / n) * 0.9;
    const x = x0 + dx * t + nx * o + (dx / len) * j, y = y0 + dy * t + ny * o + (dy / len) * j;
    d += (i ? "L" : "M") + x.toFixed(1) + " " + y.toFixed(1);
  }
  return d;
}

// ── 흔들기 물리 ──────────────────────────────────────────────

/** 물리 상태 — layout() 의 장식 하나마다 */
export function makeBody(it, W, H) {
  return { cx: it.x, cy: it.y, r: it.u * 1.25, W, H, m: Math.min(W, H) * 0.04, sc: Math.min(W, H), ox: 0, oy: 0, vx: 0, vy: 0, th: 0, w: 0, drag: 1 };
}

/** 한 번 흔들 때의 충격: 장식마다 방향(0~360도) · 속도 · 마찰이 제각각. 속도는 쌓이되 상한(화면 짧은 변의 6배/초)이 있다. */
export function impulse(b, power, rand = Math.random) {
  const ang = rand() * Math.PI * 2, sp = b.sc * (1 + rand() * 3.2) * power;
  b.drag = 0.9 + rand() * 1.4;   // 마찰이 달라 멈추는 시점이 제각각
  b.vx += Math.cos(ang) * sp; b.vy += Math.sin(ang) * sp; b.w += (rand() - 0.5) * 8;
  const cap = b.sc * 6, v = Math.hypot(b.vx, b.vy);
  if (v > cap) { b.vx *= cap / v; b.vy *= cap / v; }
}

const clampW = (w) => Math.max(-10, Math.min(10, w));

/** dt 초만큼 진행. 하나라도 아직 움직이면 true */
export function step(bodies, dt, rand = Math.random) {
  for (const b of bodies) {
    const f = Math.exp(-b.drag * dt);
    b.vx *= f; b.vy *= f;
    b.w *= Math.exp(-0.7 * dt);   // 회전은 이동보다 오래 남는다
    b.ox += b.vx * dt; b.oy += b.vy * dt; b.th += b.w * dt;
    const spin = (v) => { b.w += (rand() < 0.5 ? -1 : 1) * Math.min(10, v / b.sc * 4); };   // 벽에 부딪히면 회전이 붙는다
    const x = b.cx + b.ox, y = b.cy + b.oy;
    if (x < b.m) { b.ox = b.m - b.cx; spin(Math.abs(b.vx)); b.vx = Math.abs(b.vx) * 0.8; }
    else if (x > b.W - b.m) { b.ox = b.W - b.m - b.cx; spin(Math.abs(b.vx)); b.vx = -Math.abs(b.vx) * 0.8; }
    if (y < b.m) { b.oy = b.m - b.cy; spin(Math.abs(b.vy)); b.vy = Math.abs(b.vy) * 0.8; }
    else if (y > b.H - b.m) { b.oy = b.H - b.m - b.cy; spin(Math.abs(b.vy)); b.vy = -Math.abs(b.vy) * 0.8; }
  }
  for (let i = 0; i < bodies.length; i++) for (let j = i + 1; j < bodies.length; j++) {   // 장식끼리 충돌(원으로 근사 · 같은 질량의 탄성 충돌)
    const p = bodies[i], q = bodies[j];
    const dx = q.cx + q.ox - p.cx - p.ox, dy = q.cy + q.oy - p.cy - p.oy, d = Math.hypot(dx, dy), min = p.r + q.r;
    if (d >= min || d < 0.01) continue;
    const nx = dx / d, ny = dy / d, push = (min - d) / 2;
    p.ox -= nx * push; p.oy -= ny * push; q.ox += nx * push; q.oy += ny * push;
    const rvx = q.vx - p.vx, rvy = q.vy - p.vy, vn = rvx * nx + rvy * ny;
    if (vn < 0) {   // 서로 다가오는 중일 때만
      const jn = -(1 + 0.85) * vn / 2;
      p.vx -= jn * nx; p.vy -= jn * ny; q.vx += jn * nx; q.vy += jn * ny;
      const vt = rvx * -ny + rvy * nx;   // 접선 속도 → 스치듯 부딪히면 회전이 생긴다
      p.w = clampW(p.w + vt / p.r * 0.5); q.w = clampW(q.w + vt / q.r * 0.5);
    }
  }
  return bodies.some((b) => Math.hypot(b.vx, b.vy) > 4 || Math.abs(b.w) > 0.05);
}

// ── 센서 ────────────────────────────────────────────────────

/** devicemotion 이벤트 → 흔들기 세기. 임계값 아래면 0, 그 위면 0.6~1.6 (세게 흔들수록 크다).
 *  acceleration(중력 제외)이 있으면 그것을, 없으면 accelerationIncludingGravity 에서 중력(9.8)을 뺀 값을 쓴다. */
export function shakePower(ev) {
  if (!ev) return 0;
  const a = ev.acceleration, g = ev.accelerationIncludingGravity;
  let mag = 0;
  if (a && a.x != null && a.y != null && a.z != null) mag = Math.hypot(a.x, a.y, a.z);
  else if (g && g.x != null && g.y != null && g.z != null) mag = Math.abs(Math.hypot(g.x, g.y, g.z) - 9.8);
  if (!(mag > SHAKE_THRESHOLD)) return 0;
  return Math.max(0.6, Math.min(1.6, mag / 15));
}
