// bggyro.js — (bg-dome 시험) 폰 방향 센서(deviceorientation) → 「보는 방향」. 기준 자세에서 얼마나 돌았는지만 준다(라디안).
// 보는 방향 = 폰 뒷면이 향하는 쪽. 좌우(yaw)는 나침반처럼 오른쪽으로 돌면 +, 위아래(pitch)는 위로 들면 +. 화면 기울임(roll)은 쓰지 않는다 — 배경이 기우뚱하면 어지럽다.
// 센서는 HTTPS(보안 연결)에서만 온다. 값이 한 번도 안 오면 gyroView() 가 null 이고 화면은 고정이다.

const DEG = Math.PI / 180;
const YAW_FREEZE = 78 * DEG;   // 폰을 거의 눕히거나 세워 하늘 · 바닥을 수직으로 보면 좌우 방향이 정의되지 않아 흔들린다 → 그 동안은 좌우를 붙잡아 둔다

let on = false, have = false, needBase = true;
let yawAcc = 0, lastYaw = null, rawPitch = 0, baseYaw = 0, basePitch = 0;
// 절대 방위(바깥 보기) — 북쪽 = 0, 동쪽 = +π/2
let absOn = false, absHave = false, absYaw = 0, absPitch = 0;

const wrap = (a) => Math.atan2(Math.sin(a), Math.cos(a));

/** W3C 순서(Z · X' · Y'')의 회전에서 폰 뒷면 방향(-Z)만 계산한다. 세계 좌표: x = 동, y = 북, z = 위 */
export function forwardOf(alpha, beta, gamma) {
  const a = alpha * DEG, b = beta * DEG, g = gamma * DEG;
  const ca = Math.cos(a), sa = Math.sin(a), cb = Math.cos(b), sb = Math.sin(b), cg = Math.cos(g), sg = Math.sin(g);
  return [-ca * sg - sa * sb * cg, -sa * sg + ca * sb * cg, -cb * cg];
}

function setAbsolute(alpha, beta, gamma) {
  const [fx, fy, fz] = forwardOf(alpha, beta, gamma);
  const pitch = Math.asin(Math.max(-1, Math.min(1, fz)));
  if (Math.abs(pitch) < YAW_FREEZE) absYaw = Math.atan2(fx, fy);
  absPitch = pitch;
  absHave = true;
}

/** 안드로이드(크롬 계열): alpha 가 북쪽 기준인 별도 이벤트 */
function onAbsolute(e) {
  if (e.alpha == null || e.beta == null || e.gamma == null) return;
  setAbsolute(e.alpha, e.beta, e.gamma);
}

function onOrient(e) {
  if (e.alpha == null || e.beta == null || e.gamma == null) return;
  if (absOn) {
    // iOS: webkitCompassHeading(북 기준 시계 방향 방위)로 alpha 를 북쪽 기준으로 바꾼다. 일부 브라우저는 이 이벤트 자체가 절대값(absolute = true)
    if (typeof e.webkitCompassHeading === "number" && e.webkitCompassHeading >= 0) setAbsolute(360 - e.webkitCompassHeading, e.beta, e.gamma);
    else if (e.absolute === true) setAbsolute(e.alpha, e.beta, e.gamma);
  }
  const [fx, fy, fz] = forwardOf(e.alpha, e.beta, e.gamma);
  const pitch = Math.asin(Math.max(-1, Math.min(1, fz)));
  if (Math.abs(pitch) < YAW_FREEZE) {
    const yaw = Math.atan2(fx, fy);
    if (lastYaw != null) yawAcc += wrap(yaw - lastYaw);   // 한 바퀴를 넘어도 끊기지 않게 누적
    lastYaw = yaw;
  }
  rawPitch = pitch;
  have = true;
  if (needBase) { needBase = false; rebase(); }
}

/** 센서 듣기 시작. iOS 권한은 부르는 쪽(bgdeco.js)이 첫 터치 때 받아 둔다. */
export function startGyro() {
  if (on || typeof window.DeviceOrientationEvent === "undefined") return;
  on = true;
  window.addEventListener("deviceorientation", onOrient);
}

/** 바깥 보기용 절대 방위 듣기 시작 */
export function startAbsolute() {
  startGyro();
  if (absOn) return;
  absOn = true;
  if ("ondeviceorientationabsolute" in window) window.addEventListener("deviceorientationabsolute", onAbsolute);
}

/** 보는 방향의 실제 방위 { yaw: 북 = 0 · 동 = +π/2, pitch } — 나침반 값이 아직 없으면 null */
export function gyroAbs() { return absHave ? { yaw: absYaw, pitch: absPitch } : null; }

/** 지금 폰 자세를 새 기준(정면)으로 삼는다 */
export function rebase() { baseYaw = yawAcc; basePitch = rawPitch; }

/** 기준에서 돈 양 { yaw, pitch } — 센서 값이 아직 없으면 null */
export function gyroView() { return have ? { yaw: yawAcc - baseYaw, pitch: rawPitch - basePitch } : null; }
