// bggyro.js — (bg-dome 시험) 폰 방향 센서 → 「보는 방향」(라디안).
// 보는 방향 = 폰 뒷면이 향하는 쪽. 좌우(yaw)는 나침반처럼 오른쪽으로 돌면 +, 위아래(pitch)는 위로 들면 +. 화면 기울임(roll)은 쓰지 않는다 — 배경이 기우뚱하면 어지럽다.
// 센서는 HTTPS(보안 연결)에서만 온다. 값이 한 번도 안 오면 gyroView() · gyroAbs() 가 null 이고 화면은 고정이다.
//
// 두 보기(실내 · 바깥) 모두 실제 방위(gyroAbs, 절대값)를 쓴다(11-05 시선 통일 · 방위 보정 통일). 기준 자세에서 돈 양(gyroView, 상대값)은 나침반 값이 없을 때의 대체.
// 방위는 Stardroid(옛 Google Sky Map)와 같은 순서로 구한다 — ref/bg-dome/stardroid_sensor_study.md:
//   ① 방위 원천 = 자이로 · 가속도계 · 자력계를 OS 가 섞은 값만 쓴다. 자력계 없이 자이로만 쌓은 값은 돌릴수록 오차가 쌓인다(11-04 운영자 실측 증상).
//      우선순위: AbsoluteOrientationSensor(쿼터니언*) → deviceorientationabsolute → iOS webkitCompassHeading → absolute 표시만 붙은 deviceorientation(마지막 수단).
//   ② 진북 보정 = 자북 방위 + 편각(bgmag.js WMM2025, 위치 · 날짜마다 자동 계산).
//   ③ 수동 보정(「방향 맞추기」) = 남은 오차만 더한다. 맞춘 장소 · 시각을 같이 저장하고, 다른 장소이거나 OFFSET_TTL_MS 가 지나면 버린다.
//   * 쿼터니언 = 3D 회전을 각도 셋 대신 숫자 넷으로 나타내는 방식. 폰을 세울 때 생기는 각도 꼬임이 없다

import { outdoorSite } from "./bgsite.js";
import { declinationRad } from "./bgmag.js";

const DEG = Math.PI / 180;
const YAW_FREEZE = 78 * DEG;   // 폰을 거의 눕히거나 세워 하늘 · 바닥을 수직으로 보면 좌우 방향이 정의되지 않아 흔들린다 → 그 동안은 좌우를 붙잡아 둔다
const FRESH_MS = 1000;         // 윗순위 원천이 이 시간 안에 값을 줬으면 아랫순위 값은 버린다
const OFFSET_TTL_MS = 3 * 3600 * 1000;   // 수동 보정 수명 — 주변 철근 · 전자기기 오차는 자리마다 달라 오래 두면 오히려 틀린다

let on = false, have = false, needBase = true, tiltX = 0, tiltY = 1;
let yawAcc = 0, lastYaw = null, rawPitch = 0, baseYaw = 0, basePitch = 0;
// 절대 방위(바깥 보기, 자북 기준) — 북쪽 = 0, 동쪽 = +π/2
let absOn = false, absHave = false, absYaw = 0, absPitch = 0;
const RANK = { sensor: 3, event: 2, ios: 2, flag: 1 };
const lastAt = { sensor: -1e9, event: -1e9, ios: -1e9, flag: -1e9 };
// 확인용 — 어떤 원천이 몇 번 왔고 마지막 값이 무엇인지(bgdomegl.js 가 ?bgdebug 일 때 콘솔에 3초마다 찍는다)
export const gyroDebug = {
  orient: 0, absolute: 0, compass: 0, absFlag: 0, sensor: 0, sensorErr: null,
  src: null, decl: null, offset: null, last: null, lastAbs: null,
};

const wrap = (a) => Math.atan2(Math.sin(a), Math.cos(a));
const now = () => (typeof performance !== "undefined" ? performance.now() : Date.now());

/** W3C 순서(Z · X' · Y'')의 회전에서 폰 뒷면 방향(-Z)만 계산한다. 세계 좌표: x = 동, y = 북, z = 위 */
export function forwardOf(alpha, beta, gamma) {
  const a = alpha * DEG, b = beta * DEG, g = gamma * DEG;
  const ca = Math.cos(a), sa = Math.sin(a), cb = Math.cos(b), sb = Math.sin(b), cg = Math.cos(g), sg = Math.sin(g);
  return [-ca * sg - sa * sb * cg, -sa * sg + ca * sb * cg, -cb * cg];
}

/** 같은 계산을 쿼터니언 [x, y, z, w](W3C Orientation Sensor 순서, 기기 → 지구 좌표 회전)에서 — 회전 행렬 셋째 열의 반대 */
export function forwardOfQuat(q) {
  const [x, y, z, w] = q;
  return [-2 * (x * z + w * y), -2 * (y * z - w * x), -(1 - 2 * (x * x + y * y))];
}

/** 원천 src 의 뒷면 방향 f 를 절대 방위로 받는다. 윗순위 원천이 최근에 값을 줬으면 무시 */
function takeAbsolute(f, src) {
  const t = now();
  for (const k in RANK) if (RANK[k] > RANK[src] && t - lastAt[k] < FRESH_MS) return;
  lastAt[src] = t;
  const pitch = Math.asin(Math.max(-1, Math.min(1, f[2])));
  if (Math.abs(pitch) < YAW_FREEZE) absYaw = Math.atan2(f[0], f[1]);
  absPitch = pitch;
  absHave = true;
  gyroDebug.src = src;
}

/** 안드로이드(크롬 계열): alpha 가 북쪽 기준인 별도 이벤트 */
function onAbsolute(e) {
  gyroDebug.absolute++;
  gyroDebug.lastAbs = [e.alpha, e.beta, e.gamma].map((v) => (v == null ? null : Math.round(v)));
  if (e.alpha == null || e.beta == null || e.gamma == null) return;
  takeAbsolute(forwardOf(e.alpha, e.beta, e.gamma), "event");
}

function onOrient(e) {
  gyroDebug.orient++;
  if (typeof e.webkitCompassHeading === "number") gyroDebug.compass++;
  if (e.absolute === true) gyroDebug.absFlag++;
  gyroDebug.last = [e.alpha, e.beta, e.gamma, e.webkitCompassHeading].map((v) => (v == null ? null : Math.round(v)));
  if (e.alpha == null || e.beta == null || e.gamma == null) return;
  if (absOn) {
    // iOS: webkitCompassHeading(북 기준 시계 방향 방위)로 alpha 를 북쪽 기준으로 바꾼다 — 자북 기준으로 알려져 있으나 실기기 확인 필요.
    // 그 밖에 absolute = true 만 붙은 값은 정말 자력계가 섞였는지 알 수 없어 마지막 수단으로만 쓴다.
    if (typeof e.webkitCompassHeading === "number" && e.webkitCompassHeading >= 0) takeAbsolute(forwardOf(360 - e.webkitCompassHeading, e.beta, e.gamma), "ios");
    else if (e.absolute === true) takeAbsolute(forwardOf(e.alpha, e.beta, e.gamma), "flag");
  }
  // 화면 기울임(roll) 재료 — 회전 행렬에서 폰 오른쪽(x) · 위쪽(y) 축의 「세계 위」 성분. 오일러 각 꼬임과 무관하다(bggyro.selfcheck.mjs)
  const cb = Math.cos(e.beta * DEG);
  tiltX = cb * Math.sin(e.gamma * DEG);   // = −(폰 오른쪽 축의 위 성분): 오른쪽이 내려가면 +
  tiltY = Math.sin(e.beta * DEG);         // = 폰 위쪽 축의 위 성분: 세워 들면 1
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

/** 1순위 원천 — Generic Sensor API(크롬 계열 안드로이드). 없거나 막히면 조용히 아랫순위 이벤트를 쓴다 */
function startSensor() {
  const AOS = window.AbsoluteOrientationSensor;
  if (typeof AOS !== "function") { gyroDebug.sensorErr = "none"; return; }
  try {
    const s = new AOS({ frequency: 60, referenceFrame: "device" });
    s.addEventListener("reading", () => {
      if (!s.quaternion) return;
      gyroDebug.sensor++;
      takeAbsolute(forwardOfQuat(s.quaternion), "sensor");
    });
    s.addEventListener("error", (e) => { gyroDebug.sensorErr = (e && e.error && e.error.name) || "error"; });
    s.start();
  } catch (err) {
    gyroDebug.sensorErr = (err && err.name) || "throw";
  }
}

/** 바깥 보기용 절대 방위 듣기 시작 */
export function startAbsolute() {
  startGyro();
  if (absOn) return;
  absOn = true;
  startSensor();
  if ("ondeviceorientationabsolute" in window) window.addEventListener("deviceorientationabsolute", onAbsolute);
}

// ── 진북 보정(편각) — 같은 위치 · 같은 날이면 다시 계산하지 않는다(Stardroid 도 하루 캐시)
let decl = 0, declLat = NaN, declLon = NaN, declDay = -1;
function declination() {
  const site = outdoorSite();
  if (!site) return 0;
  const day = Math.floor(Date.now() / 86400000);
  if (site.lat !== declLat || site.lon !== declLon || day !== declDay) {
    declLat = site.lat; declLon = site.lon; declDay = day;
    decl = declinationRad(site.lat, site.lon);
    gyroDebug.decl = Math.round(decl / DEG * 10) / 10;
  }
  return decl;
}

/** 지금 적용 중인 편각(도) — 위치를 아직 모르면 null */
export const declinationDeg = () => (outdoorSite() ? declination() / DEG : null);

// ── 수동 보정(「방향 맞추기」, bgview.js) — { rad, lat, lon, at } 를 기기에 기억한다.
// 옛 키 "bgheading"(편각까지 섞인 값, 장소 · 시각 없음)은 의미가 달라 읽지 않고 지운다.
const OFFSET_KEY = "bgheading2";
let manual = null;
try {
  localStorage.removeItem("bgheading");
  const v = JSON.parse(localStorage.getItem(OFFSET_KEY) || "null");
  if (v && Number.isFinite(v.rad) && Number.isFinite(v.lat) && Number.isFinite(v.lon) && Number.isFinite(v.at)) manual = v;
} catch { /* 저장소 없음 · 깨진 값 */ }

function dropManual(why) {
  manual = null;
  gyroDebug.offset = why;
  try { localStorage.removeItem(OFFSET_KEY); } catch { /* 저장 못 함 */ }
}

/** 지금 유효한 수동 보정(라디안). 다른 장소이거나 오래됐으면 이 자리에서 버리고 0 */
function manualOffset() {
  if (!manual) return 0;
  const site = outdoorSite();
  if (!site) return 0;   // 위치를 받기 전엔 판단 보류(적용도 안 함)
  if (site.lat !== manual.lat || site.lon !== manual.lon) { dropManual("다른 장소라 버림"); return 0; }
  if (Date.now() - manual.at > OFFSET_TTL_MS) { dropManual("오래돼 버림"); return 0; }
  gyroDebug.offset = Math.round(manual.rad / DEG);
  return manual.rad;
}

export const headingOffsetDeg = () => manualOffset() / DEG;
export const OFFSET_TTL_HOURS = OFFSET_TTL_MS / 3600000;

/** 보정 저장 — rad = 더할 각도(편각을 뺀 나머지). 0 이면 보정 지우기. 위치를 모르면 저장하지 않는다 */
export function setHeadingOffset(rad) {
  const site = outdoorSite();
  const r = wrap(rad);
  if (!r || !site) { dropManual(null); return; }
  manual = { rad: r, lat: site.lat, lon: site.lon, at: Date.now() };
  try { localStorage.setItem(OFFSET_KEY, JSON.stringify(manual)); } catch { /* 저장 못 해도 지금은 적용 */ }
}

/** 수동 보정 전 방위(진북 기준, 라디안) — 보정값을 새로 구할 때 쓴다. 나침반 값이 없으면 null */
export function rawHeading() { return absHave ? wrap(absYaw + declination()) : null; }

/** 보는 방향의 실제 방위 { yaw: 진북 = 0 · 동 = +π/2, pitch } (편각 · 수동 보정 포함) — 나침반 값이 아직 없으면 null */
export function gyroAbs() { return absHave ? { yaw: wrap(absYaw + declination() + manualOffset()), pitch: absPitch } : null; }

/** 지금 폰 자세를 새 기준(정면)으로 삼는다 */
export function rebase() { baseYaw = yawAcc; basePitch = rawPitch; }

/** 화면 기울임 { roll: 오른쪽이 내려가면 + (라디안), upright: 0 ~ 1 } — 핸들 돌리듯 옆으로 기울인 각도.
 *  upright = 화면 평면 안의 중력 세기(세워 들면 1, 눕히면 0) — 눕혀 들면 roll 이 의미 없으니 부르는 쪽이 세기를 줄인다. 센서 값이 없으면 null */
export function gyroTilt() {
  if (!have) return null;
  return { roll: Math.atan2(tiltX, tiltY), upright: Math.min(1, Math.hypot(tiltX, tiltY)) };
}

/** 기준에서 돈 양 { yaw, pitch } — 센서 값이 아직 없으면 null */
export function gyroView() { return have ? { yaw: yawAcc - baseYaw, pitch: rawPitch - basePitch, rawPitch } : null; }
