// bggyro.selfcheck.mjs — node src/frontend/js/bggyro.selfcheck.mjs
// 방위: ① 쿼터니언 계산 = 오일러 각 계산 ② 원천 우선순위 · 진북 보정(편각) ③ 없앤 수동 보정 값 정리.
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

// ①-2 화면 기울임(roll) = 회전 행렬에서 직접 구한 값(폰 오른쪽 축 · 위쪽 축의 「세계 위」 성분)과 같은지
const rotate = (q, v) => { const p = qmul(qmul(q, [v[0], v[1], v[2], 0]), [-q[0], -q[1], -q[2], q[3]]); return p.slice(0, 3); };
let worstRoll = 0;
g.startGyro();
for (const [al, be, ga] of [[0, 90, 0], [40, 80, 15], [200, 70, -25], [10, 100, 30], [300, 60, 20], [123, 45, -60]]) {
  listeners.deviceorientation({ alpha: al, beta: be, gamma: ga });
  const q = eulerQ(al, be, ga), xw = rotate(q, [1, 0, 0]), yw = rotate(q, [0, 1, 0]);
  const want = Math.atan2(-xw[2], yw[2]);
  worstRoll = Math.max(worstRoll, Math.abs(g.gyroTilt().roll - want));
}
check("화면 기울임 = 회전 행렬 기준", worstRoll < 1e-9, `최대 차 ${worstRoll.toExponential(1)}`);
listeners.deviceorientation({ alpha: 0, beta: 60, gamma: 20 });   // W3C: gamma + = 오른쪽이 내려감
check("오른쪽을 내리면 roll +", g.gyroTilt().roll > 0);
listeners.deviceorientation({ alpha: 0, beta: 90, gamma: 0 });
check("세워 들면 roll 0 · upright 1", Math.abs(g.gyroTilt().roll) < 1e-9 && Math.abs(g.gyroTilt().upright - 1) < 1e-9);

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

// ③ 없앤 수동 보정 — 남아 있던 값은 지우고 적용하지 않는다(새로고침 흉내 = 모듈 다시 불러오기)
store.set("bgheading2", JSON.stringify({ rad: 12 * DEG, lat: 37.6, lon: 127, at: Date.now() }));
const g2 = await import("./bggyro.js?reload");
g2.startAbsolute();
fakeNow += 10;
sensorInst.emit(eulerQ(...north));
check("옛 수동 보정(bgheading2) 지우고 적용 안 함", !store.has("bgheading2") && near(g2.gyroAbs().yaw, dec, 1e-9));

if (fail) { console.log(`\n${fail}건 실패`); process.exit(1); }
console.log("\n전부 통과");
