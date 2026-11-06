// bgwarp.js — (bg-dome 3단계) 성간 이동 워프 기어의 속도 모형 · 좌석벨트 표시등 상태 · 워프 점프 연출 시간표. DOM · WebGL 없음(순수 계산, self-check = bgwarp.selfcheck.mjs).
// 정본 = devpapers ref/bg-dome/ufo-panel/Gear.dc.html(기어 · 떨림 · 표시등) · WarpJump_mock_v1.html(점프 A · B · C), 계획 ufo_panel_impl_plan.md 0번 2 · 3단계.
//
// 속도 모형(시안과 같은 식):
//   기어는 한 단씩 차례로 지난다(N → 3 이면 1 · 2 를 거쳐서). 중간 단 = 일정한 빠르기(한 단 폭 ÷ τ)로 통과, 목표 단 = 지수 접근 β += (목표 − β)(1 − e^(−dt/τ)).
//   τ: 보통 0.3초 · 레드존(4 · 5단)으로 올라갈 때 1.6초 · 레드존(β ≥ 0.85)에서 내려갈 때 0.16초(급제동).
// 떨림 세기 amp(px, 패널 흔들기 · 폰 진동 · 돔 흔들기는 4단계) — 레드존 가속 목표 1.8(τ 0.7초) · 급제동 목표 최대 5(τ 0.06초) · 끝나면 0 으로(τ 0.9초).
// 좌석벨트 표시등: 떨림이 있으면 켜짐 → 다 잦아들면 1.6초 깜빡인 뒤 꺼짐. 켜질 때 · 꺼질 때 「띵」 신호(ding)를 돌려준다(소리는 4단계).
// 워프 버튼: 레드존(β ≥ 0.85)이고 표시등이 꺼져 있으면 쓸 수 있다(운영자 11-06).

export const GEAR_BETA = [0, 0.3, 0.6, 0.8, 0.9, 0.99];
export const RED_BETA = 0.85;

export function createWarp() {
  return { gear: 0, stage: 0, beta: 0, mode: "idle", amp: 0, belt: "off", beltUntil: 0, moved: false };
}

/** 기어 바꾸기(0 = N). 같은 단을 다시 고르면 그대로 */
export function shiftGear(st, i) {
  const g = Math.max(0, Math.min(5, i | 0));
  if (g === st.gear && st.mode === "idle") return st;
  st.gear = g; st.mode = "go"; st.moved = true;
  return st;
}

export const isRed = (st) => st.beta >= RED_BETA;
export const warpReady = (st) => isRed(st) && st.belt === "off";

/** dt 초만큼 진행. 돌려주는 값 = 「띵」을 울릴 일("on" | "off" | null) */
export function tickWarp(st, dt, nowMs) {
  const V = GEAR_BETA, goal = V[st.gear];
  let b = st.beta, mode = st.mode;
  if (mode !== "idle") {
    const up = goal > b;
    let next = st.gear;
    if (up) { for (let k = 0; k <= st.gear; k++) if (V[k] > b + 1e-6) { next = k; break; } }
    else { for (let k = 5; k >= st.gear; k--) if (V[k] < b - 1e-6) { next = k; break; } }
    const prev = up ? next - 1 : next + 1;
    const red = up ? next >= 4 : b >= RED_BETA;
    mode = up ? (red ? "redAccel" : "accel") : (red ? "redDecel" : "decel");
    const tau = up ? (red ? 1.6 : 0.3) : (red ? 0.16 : 0.3);
    if (next === st.gear) {
      b += (goal - b) * (1 - Math.exp(-dt / tau));
      if (Math.abs(goal - b) < 0.003) { b = goal; mode = "idle"; }
    } else {
      const rate = Math.abs(V[next] - V[prev]) / tau;
      b = up ? Math.min(V[next], b + rate * dt) : Math.max(V[next], b - rate * dt);   // 다음 단 경계에서 멈춰 다음 틱에 그 단의 τ 로(경계 넘어 달려 나가지 않게)
    }
    st.stage = next;
  }
  const left = Math.abs(goal - b);
  let want = 0, att = 0.9;
  if (mode === "redAccel") { want = 1.8; att = 0.7; }
  if (mode === "redDecel") { want = 1.5 + 3.5 * Math.min(1, left / 0.3); att = 0.06; }
  st.amp += (want - st.amp) * (1 - Math.exp(-dt / att));
  if (want === 0 && st.amp < 0.05) st.amp = 0;
  let ding = null;
  if (st.amp > 0) { if (st.belt === "off") ding = "on"; st.belt = "on"; st.beltUntil = 0; }
  else if (st.belt === "on") { st.belt = "blink"; st.beltUntil = nowMs + 1600; }
  else if (st.belt === "blink" && nowMs >= st.beltUntil) { st.belt = "off"; ding = "off"; }
  st.beta = b; st.mode = mode;
  return ding;
}

/** N 으로 멈춰 다 잦아들었나(속도 0 · 떨림 0 · 표시등 꺼짐) — 그러면 기어 패널을 닫는다 */
export const stoppedAtN = (st) => st.moved && st.gear === 0 && st.mode === "idle" && st.amp === 0 && st.belt === "off";

// ── 워프 점프(WARP 버튼) — 세 연출을 같은 확률로(운영자 11-06 「모두 채택 · 같은 확률」). B 는 멈칫 없이 바로 급제동(운영자).
//   시간(ms)은 시안 WarpJump_mock_v1 그대로. 셰이더에 넘길 값을 시간표로 계산한다.
export const JUMP_KINDS = ["A", "B", "C"];
export const JUMP_MS = { A: 3900, B: 3600, C: 3800 };
const ss = (x) => (x <= 0 ? 0 : x >= 1 ? 1 : x * x * (3 - 2 * x));
const c01 = (x) => Math.max(0, Math.min(1, x));
/** 감속(옛 「도착」을 짧게): 0.99c → 0 */
export const decelBeta = (u) => 0.99 * (1 - ss(u)) * Math.exp(-2.2 * u);
export function pickJump(rand = Math.random) { return JUMP_KINDS[Math.min(2, Math.floor(rand() * 3))]; }

/**
 * 점프 연출 한 장면. t = 시작 뒤 ms, maxR = 화면 끝까지 반지름(px).
 * beta = 우주 속도 · ring = { r, alpha, width } 충격 고리 · flash = 흰 섬광 0~1 · red = 붉은 섬광 0~1 ·
 * repro = B 재투영 고리 반지름(px, 없으면 −1) · blur = B 바깥(옛 화면)의 방사 번짐 0~1 · tunnel = C 터널 위상(없으면 −1) · tunnelA = 터널 고리 세기 · done
 */
export function jumpFrame(kind, t, maxR) {
  const f = { beta: 0.99, ring: { r: 0, alpha: 0, width: 0 }, flash: 0, red: 0, repro: -1, blur: 0, tunnel: -1, tunnelA: 0, done: t >= JUMP_MS[kind] };
  if (kind === "A") {
    // 0~450 늘어남(β 를 더 올려 별이 앞쪽으로 몰림) · 450~620 빨려 듦 + 밝아짐 · 620 섬광 + 시안 · 분홍 충격 고리 · 이후 감속
    if (t < 620) {
      f.beta = 0.99 + 0.0085 * ss(t / 450) + 0.0013 * ss((t - 450) / 170);
      f.flash = 0.5 * ss((t - 450) / 170);
    } else {
      const after = t - 620, k = c01(after / 520);
      f.beta = decelBeta(c01(after / (JUMP_MS.A - 620)));
      f.ring = { r: maxR * ss(k), alpha: 1 - k, width: 10 * (1 - k) + 2 };
      f.flash = Math.max(0, 1 - after / 380);
    }
  } else if (kind === "B") {
    // 바로 급제동(짧은 분홍 섬광) · 0~1400 가운데서 흰 고리가 퍼짐 — 바깥(옛 레드존 화면)은 방사 번짐으로 계속 달리는 듯 · 띠는 도트로 걷힘 · 안쪽은 감속 중인 우주
    const k = c01(t / 1400);
    f.beta = decelBeta(c01(t / 2400)) * 0.95;
    f.repro = k < 1 ? maxR * ss(k) : -1;
    f.blur = 1 - k * 0.5;
    f.red = Math.max(0, 0.22 - t / 600);
  } else {
    // C: 0~700 터널(시안 · 분홍 고리가 바깥으로 달림) · 700~1120 붉은 충격파 + 붉은 섬광 · 이후 감속
    if (t < 700) {
      f.beta = 0.99; f.tunnel = (t / 520) % 1; f.tunnelA = ss(t / 700);
    } else {
      const after = t - 700, k = c01(after / 420);
      f.beta = decelBeta(c01(after / (JUMP_MS.C - 700)));
      f.ring = { r: maxR * ss(k), alpha: 1 - k, width: 22 * (1 - k) + 2 };
      f.red = Math.max(0, 0.45 - after / 500);
    }
  }
  return f;
}
