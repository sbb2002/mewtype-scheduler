// bgyawfix.selfcheck.mjs — node src/frontend/js/bgyawfix.selfcheck.mjs
// 움직임 연동 방위 보정: ① 정지 중 절대 방위 계단 → 화면 그대로 ② 돌리면 새 보정량으로 수렴 ③ 끊김 뒤 재시작 = 바로 맞춤 ④ ±180° 넘김
import { createYawFix, wrap } from "./bgyawfix.js";

const DEG = Math.PI / 180;
let fails = 0;
const ok = (cond, msg) => { if (!cond) { fails++; console.error("✗", msg); } else console.log("✓", msg); };
const near = (x, y, tol = 0.05) => Math.abs(wrap(x - y)) < tol * DEG;

// 30ms 간격으로 상대 · 절대 판독을 번갈아 넣는다. rel(t) · abs(t) = 도
function feed(fix, t0, t1, rel, abs) {
  for (let t = t0; t < t1; t += 30) { fix.onRel(t, rel(t) * DEG); fix.onAbs(t + 5, abs(t) * DEG); }
}

{ // ① 정지 중 계단
  const fix = createYawFix();
  feed(fix, 0, 2000, () => 10, () => 40);            // 보정량 30°
  ok(near(fix.yaw(), 40 * DEG), "처음: 화면 = 절대 방위(40°)");
  feed(fix, 2000, 5000, () => 10, (t) => (t < 2600 ? 40 : 49));   // 정지 중 절대 방위만 +9° 계단
  ok(near(fix.yaw(), 40 * DEG), "정지 중 +9° 계단: 화면은 40° 그대로");
  ok(near(fix.debug().eHat, 39 * DEG), "목표 보정량은 39° 로 갱신");

  // ② 돌리면 수렴: 초당 60° 로 2초(120°) 돌린다. k = 0.2 → 9° 차이는 45° 돌리면 다 맞는다
  feed(fix, 5000, 7000, (t) => 10 + (t - 5000) * 0.06, (t) => 49 + (t - 5000) * 0.06);
  const r = 10 + 120 - 0.06 * 30;   // 마지막 판독 시각의 상대 방위(대략)
  ok(Math.abs(wrap(fix.debug().b - 39 * DEG)) < 0.2 * DEG, "회전 뒤 반영 보정량 ≈ 39°");
  ok(fix.yaw() != null && Math.abs(wrap(fix.yaw() - (r + 39) * DEG)) < 2 * DEG, "회전 뒤 화면 ≈ 상대 + 39°");
}

{ // ③ 끊김 뒤 재시작
  const fix = createYawFix();
  feed(fix, 0, 1000, () => 0, () => 20);
  feed(fix, 5000, 6000, () => 100, () => 50);         // 4초 끊김 → 상대 기준이 새로 잡힘, 보정량 −50°
  ok(near(fix.yaw(), 50 * DEG), "끊김 뒤: 화면 = 절대 방위(50°)로 바로 맞춤");
  ok(fix.debug().resets === 2, "재시작 횟수 2");
}

{ // ④ ±180° 넘김
  const fix = createYawFix();
  feed(fix, 0, 1000, () => 175, () => -175);         // 보정량 +10°
  ok(near(fix.yaw(), -175 * DEG), "±180° 넘는 보정량: 화면 = −175°");
  feed(fix, 1000, 3000, () => 175, (t) => (t < 1500 ? -175 : 178));   // 정지 중 −7° 계단(−175 → 178)
  ok(near(fix.yaw(), -175 * DEG), "±180° 걸친 계단도 정지 중엔 그대로");
}

{ // 손떨림(문턱 아래 흔들림)에선 보정이 반영되지 않는다
  const fix = createYawFix();
  feed(fix, 0, 1000, () => 0, () => 0);
  feed(fix, 1000, 4000, (t) => 0.5 * Math.sin(t / 100), () => 6);   // 진폭 0.5° · 최대 약 5°/초 떨림, 절대만 +6°
  ok(Math.abs(fix.debug().b) < 0.01 * DEG, "손떨림 중엔 반영 보정량 0 유지");
}

if (fails) { console.error(`실패 ${fails}`); process.exit(1); }
console.log("bgyawfix self-check 통과");
