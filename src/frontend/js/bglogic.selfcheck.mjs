/**
 * bglogic.js 순수 로직 자동 테스트 (v4.9.8). node bglogic.selfcheck.mjs 로 실행. 프레임워크 없음.
 */
import { SPOTS, KINDS, layout, scribblePath, makeBody, impulse, step, shakePower, rng, SHAKE_THRESHOLD } from "./bglogic.js";

let n = 0;
function assert(cond, msg) {
  n++;
  if (!cond) { console.error(`❌ FAIL (${n}): ${msg}`); process.exit(1); }
  console.log(`✓ ${msg}`);
}

// ── 배치
const L = layout(390, 844);
assert(L.length === SPOTS.length, "장식 수 = 자리 수");
assert(L.every((it) => KINDS.includes(it.kind)), "종류는 다섯 가지 안");
assert(L.every((it) => it.x >= 0 && it.x <= 390 && it.y >= 0 && it.y <= 844), "모두 화면 안");
assert(L.every((it) => !(it.x > 390 * 0.2 && it.x < 390 * 0.8 && it.y > 844 * 0.1 && it.y < 844 * 0.6)), "가운데(카드 자리)는 비어 있다");
assert(JSON.stringify(layout(390, 844)) === JSON.stringify(L), "같은 씨앗이면 같은 배치");
assert(L.every((it) => it.dur >= 9 && it.dur <= 16 && it.delay <= 0), "주기 9~16초 · 시작은 이미 진행 중");
assert(scribblePath(390, 844).startsWith("M") && scribblePath(390, 844) === scribblePath(390, 844), "낙서 선은 M 으로 시작 · 같은 씨앗이면 같음");

// ── 센서 세기
assert(shakePower(null) === 0 && shakePower({}) === 0, "이벤트가 비어도 안전");
assert(shakePower({ acceleration: { x: 3, y: 3, z: 3 } }) === 0, "임계값 아래는 흔들기 아님");
const hard = shakePower({ acceleration: { x: 30, y: 0, z: 0 } });
assert(hard > 1 && hard <= 1.6, "세게 흔들면 1~1.6");
assert(shakePower({ acceleration: { x: 100, y: 0, z: 0 } }) === 1.6, "세기 상한 1.6");
const lo = shakePower({ acceleration: { x: SHAKE_THRESHOLD + 0.1, y: 0, z: 0 } });
assert(lo >= 0.6 && lo < 1, "임계값 바로 위는 1 미만(약하게)");
assert(shakePower({ acceleration: { x: null, y: null, z: null }, accelerationIncludingGravity: { x: 0, y: 9.8, z: 0 } }) === 0, "가만히 있을 때(중력만)는 0");
assert(shakePower({ acceleration: null, accelerationIncludingGravity: { x: 0, y: 9.8 + 20, z: 0 } }) > 0, "중력 포함값만 있어도 판정");

// ── 물리
const bodies = () => layout(390, 844).map((it) => makeBody(it, 390, 844));
const rnd = rng(5);
let B = bodies();
B.forEach((b) => impulse(b, 1, rnd));
assert(B.some((b) => Math.hypot(b.vx, b.vy) > 0), "충격을 받으면 속도가 생긴다");
assert(new Set(B.map((b) => b.drag.toFixed(3))).size === B.length, "마찰이 장식마다 다르다");
assert(new Set(B.map((b) => Math.atan2(b.vy, b.vx).toFixed(2))).size === B.length, "방향이 장식마다 다르다");
let moving = true, t = 0;
while (moving && t < 60) { moving = step(B, 1 / 60, rnd); t += 1 / 60; }
assert(!moving && t < 30, `결국 멈춘다 (${t.toFixed(1)}초)`);
assert(B.every((b) => { const x = b.cx + b.ox, y = b.cy + b.oy; return x >= b.m - 0.01 && x <= 390 - b.m + 0.01 && y >= b.m - 0.01 && y <= 844 - b.m + 0.01; }), "멈춘 뒤에도 모두 화면 안");
assert(B.some((b) => Math.abs(b.th) > 0.1), "부딪히며 회전했다");

B = bodies();
for (let k = 0; k < 40; k++) B.forEach((b) => impulse(b, 1.6, rnd));
assert(B.every((b) => Math.hypot(b.vx, b.vy) <= b.sc * 6 + 1e-6), "연속으로 흔들어도 속도 상한(짧은 변 × 6)");

// 정면충돌: 서로 다가오면 튕겨 나가고, 멀어지는 중이면 건드리지 않는다
const p = makeBody({ x: 100, y: 400, u: 15 }, 390, 844), q = makeBody({ x: 125, y: 400, u: 15 }, 390, 844);
p.vx = 100; q.vx = -100; step([p, q], 0.001, () => 0.5);
assert(p.vx < 0 && q.vx > 0, "다가오던 두 장식은 서로 튕겨 반대로 간다");
const p2 = makeBody({ x: 100, y: 400, u: 15 }, 390, 844), q2 = makeBody({ x: 125, y: 400, u: 15 }, 390, 844);
p2.vx = -100; q2.vx = 100; step([p2, q2], 0.001, () => 0.5);
assert(p2.vx < 0 && q2.vx > 0, "멀어지는 중이면 속도를 건드리지 않는다");

console.log(`\n✅ ${n}개 통과`);
