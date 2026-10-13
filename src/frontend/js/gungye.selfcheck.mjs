/**
 * gungye.js 순수 헬퍼 자동 테스트 (v4.3.0). node gungye.selfcheck.mjs — DOM 접근 함수는 호출하지 않는다.
 */
import { lateStage, waitLabel, isGungyeTarget, MAX_LATE_MS } from "./gungye.js";

let n = 0;
function assert(cond, msg) {
  n++;
  if (!cond) { console.error(`❌ FAIL (${n}): ${msg}`); process.exit(1); }
  console.log(`✓ ${msg}`);
}

const S = Date.parse("2026-10-13T21:00:00+09:00");
const at = (min, sec = 0) => S + min * 60000 + sec * 1000;

assert(lateStage(S, at(-1)) === 0, "예정 시각 전 = 지각 아님");
assert(lateStage(S, S) === 0, "정각 = 지각 아님");
assert(lateStage(S, at(0, 1)) === 1, "1초 지각 = 1단계");
assert(lateStage(S, at(4, 59)) === 1, "4분 59초 = 1단계");
assert(lateStage(S, at(5)) === 2, "5분 = 2단계");
assert(lateStage(S, at(14, 59)) === 2, "14분 59초 = 2단계");
assert(lateStage(S, at(15)) === 3, "15분 = 3단계");
assert(lateStage(S, S + MAX_LATE_MS) === 3, "상한 정각까지 3단계");
assert(lateStage(S, S + MAX_LATE_MS + 1) === 0, "상한(3h) 초과 = 꾸미지 않음");
assert(lateStage(NaN, at(10)) === 0, "시각을 모르면 지각 아님");

assert(waitLabel(0) === "00:00", "0 → 00:00");
assert(waitLabel(61000) === "01:01", "61초 → 01:01");
assert(waitLabel(125 * 60000 + 3000) === "125:03", "100분 넘어도 분이 그대로 커진다");
assert(waitLabel(-5) === "00:00", "음수는 00:00");

assert(isGungyeTarget({ channel_key: "nonoka" }), "노노카 본인 예고");
assert(!isGungyeTarget({ channel_key: "arale", collab_with: ["nonoka"] }), "다른 멤버가 호스트인 합동은 대상 아님");
assert(!isGungyeTarget(null), "null 안전");

console.log(`\n✅ 모두 통과: ${n}/${n}`);
