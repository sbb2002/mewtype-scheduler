// bggyro.selfcheck.mjs — node src/frontend/js/bggyro.selfcheck.mjs
// 바깥 보기 방위: ① 쿼터니언 계산 = 오일러 각 계산 ② 원천 우선순위 ③ 진북 보정(편각) ④ 수동 보정의 장소 · 시간 만료.
// 브라우저 대신 가짜 window · navigator · localStorage · 센서를 깔고 모듈을 불러온다.

const store = new Map();
globalThis.localStorage = { getItem: (k) => (store.has(k) ? store.get(k) : null), setItem: (k, v) => store.set(k, String(v)), removeItem: (k) => store.delete(k) };
store.set("bgheading", "0.7");   // 옛 키 — 불러올 때 지워져야 한다
const listeners = {};
let sensorInst = null;
class FakeAOS {
  constructor() { this.quaternion = null; this.h = {}; sensorInst = this; }
  addEventListener(t, f) { this.h[t] = f; }
  start() {}
  emit(q) { this.quaternion = q; this.h.reading(); }
}
globalThis.window = { DeviceOrientationEvent: function () {}, AbsoluteOrientationSensor: FakeAOS, ondeviceorientationabsolute: null, addEventListener: (t, f) => { listeners[t] = f; } };
let pos = { latitude: 37.6, longitude: 127.0 };
// node 는 navigator · performance 를 읽기 전용으로 두므로 defineProperty 로 덮는다
Object.defineProperty(globalThis, "navigator", { configurable: true, value: { geolocation: { getCurrentPosition: (ok) => ok({ coords: pos }) }, permissions: { query: async () => ({ state: "granted" }) } } });
let fakeNow = 1000;
Object.defineProperty(globalThis, "performance", { configurable: true, value: { now: () => fakeNow } });

const g = await import("./bggyro.js");
const { acquireSite } = await import("./bgsite.js");
const { declinationRad } = await import("./bgmag.js");

let fail = 0;
const DEG = Math.PI / 180;
function check(name, ok, detail = "") { if (!ok) fail++; console.log(`${ok ? "ok  " : "FAIL"} ${name}${detail ? " — " + detail : ""}`); }
const near = (a, b, t) => Math.abs(Math.atan2(Math.sin(a - b), Math.cos(a - b))) <= t;

// ① 쿼터니언(Z · X' · Y'' 순서로 만든 것)과 오일러 각이 같은 뒷면 방향을 주는지 — 여러 자세
const qmul = (a, b) => [a[3] * b[0] + a[0] * b[3] + a[1] * b[2] - a[2] * b[1], a[3] * b[1] - a[0] * b[2] + a[1] * b[3] + a[2] * b[0], a[3] * b[2] + a[0] * b[1] - a[1] * b[0] + a[2] * b[3], a[3] * b[3] - a[0] * b[0] - a[1] * b[1] - a[2] * b[2]];
const axisQ = (ax, deg) => { const h = deg * DEG / 2, s = Math.sin(h); return [ax[0] * s, ax[1] * s, ax[2] * s, Math.cos(h)]; };
const eulerQ = (al, be, ga) => qmul(qmul(axisQ([0, 0, 1], al), axisQ([1, 0, 0], be)), axisQ([0, 1, 0], ga));
let worst = 0;
for (const [al, be, ga] of [[0, 0, 0], [0, 90, 0], [30, 80, 5], [200, 95, -10], [315, 60, 40], [123, -20, 170], [10, 179, -80]]) {
  const a = g.forwardOf(al, be, ga), b = g.forwardOfQuat(eulerQ(al, be, ga));
  worst = Math.max(worst, ...a.map((v, i) => Math.abs(v - b[i])));
}
check("쿼터니언 = 오일러 각(뒷면 방향)", worst < 1e-12, `최대 차 ${worst.toExponential(1)}`);

// 위치를 받고 바깥 보기 시작
await acquireSite();
g.startAbsolute();
check("옛 보정 키(bgheading) 지움", !store.has("bgheading"));
const dec = declinationRad(37.6, 127.0);
check("편각 자동(서울 약 −9°)", near(g.declinationDeg() * DEG, dec, 1e-12) && dec < -8 * DEG && dec > -10 * DEG, `${(dec / DEG).toFixed(2)}°`);

// ② 원천 우선순위 — 폰을 세워 정북(자북)을 겨눈 자세 = alpha 0 · beta 90
const north = [0, 90, 0], east = [270, 90, 0];   // alpha 는 반시계 → 동쪽을 보려면 alpha = 270
listeners.deviceorientationabsolute({ alpha: east[0], beta: east[1], gamma: east[2] });
check("이벤트만 있을 때 이벤트 사용", g.gyroDebug.src === "event" && near(g.gyroAbs().yaw, 90 * DEG + dec, 1e-9));
fakeNow += 10;
sensorInst.emit(eulerQ(...north));
check("센서가 오면 센서 사용", g.gyroDebug.src === "sensor" && near(g.gyroAbs().yaw, dec, 1e-9), `yaw ${(g.gyroAbs().yaw / DEG).toFixed(2)}°`);
fakeNow += 10;
listeners.deviceorientationabsolute({ alpha: east[0], beta: east[1], gamma: east[2] });
listeners.deviceorientation({ alpha: east[0], beta: east[1], gamma: east[2], absolute: true });
check("센서가 살아 있는 동안 이벤트 · absolute 표시값은 무시", g.gyroDebug.src === "sensor" && near(g.gyroAbs().yaw, dec, 1e-9));
fakeNow += 1500;   // 센서가 1초 넘게 끊김 → 이벤트로 내려간다
listeners.deviceorientationabsolute({ alpha: east[0], beta: east[1], gamma: east[2] });
listeners.deviceorientation({ alpha: north[0], beta: north[1], gamma: north[2], absolute: true });
check("센서가 끊기면 이벤트 사용, 그동안 absolute 표시값은 무시", g.gyroDebug.src === "event" && near(g.gyroAbs().yaw, 90 * DEG + dec, 1e-9));
fakeNow += 1500;   // 이벤트도 끊김
listeners.deviceorientation({ alpha: east[0], beta: east[1], gamma: east[2], absolute: true });
check("윗순위가 다 끊기면 absolute 표시값 사용(마지막 수단)", g.gyroDebug.src === "flag" && near(g.gyroAbs().yaw, 90 * DEG + dec, 1e-9));
fakeNow += 10;
sensorInst.emit(eulerQ(...north));

// ③ · ④ 수동 보정
check("수동 보정 전 방위 = 자북 + 편각", near(g.rawHeading(), dec, 1e-9));
g.setHeadingOffset(12 * DEG);
check("수동 보정 적용", near(g.gyroAbs().yaw, dec + 12 * DEG, 1e-9) && Math.round(g.headingOffsetDeg()) === 12);
check("수동 보정에 장소 · 시각 저장", (() => { const v = JSON.parse(store.get("bgheading2")); return v.lat === 37.6 && v.lon === 127 && Number.isFinite(v.at); })());
const saved = JSON.parse(store.get("bgheading2"));
store.set("bgheading2", JSON.stringify({ ...saved, at: Date.now() - 3.1 * 3600 * 1000 }));
const g2 = await import("./bggyro.js?expire");   // 새로고침 흉내(모듈 다시 불러오기 — bgsite 의 위치는 그대로)
g2.startAbsolute();
sensorInst.emit(eulerQ(...north));
check("3시간 넘은 보정은 버림", g2.headingOffsetDeg() === 0 && !store.has("bgheading2") && g2.gyroDebug.offset === "오래돼 버림");

store.set("bgheading2", JSON.stringify({ ...saved, at: Date.now() }));
const g3 = await import("./bggyro.js?fresh");
g3.startAbsolute();
sensorInst.emit(eulerQ(...north));
check("새로고침 뒤에도 같은 장소 · 3시간 안이면 유지", Math.round(g3.headingOffsetDeg()) === 12);
pos = { latitude: 35.7, longitude: 139.7 };
await acquireSite();
check("다른 장소면 버림", g3.headingOffsetDeg() === 0 && !store.has("bgheading2") && g3.gyroDebug.offset === "다른 장소라 버림");
g3.setHeadingOffset(0);
check("보정 지우기", g3.headingOffsetDeg() === 0);

if (fail) { console.log(`\n${fail}건 실패`); process.exit(1); }
console.log("\n전부 통과");
