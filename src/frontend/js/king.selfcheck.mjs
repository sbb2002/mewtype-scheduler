/**
 * king.js 순수 로직 자동 테스트 (v4.3.1). node king.selfcheck.mjs 로 실행. 프레임워크 없음. (DOM 함수는 호출하지 않는다)
 */
import { KING_KEY, ARRIVE_MS, HOLD_MS, MAX_LATE_MS, kingTarget, lateStage, mmss, phaseOf, speech, blockLabel } from "./king.js";

let n = 0;
function assert(cond, msg) {
  n++;
  if (!cond) { console.error(`❌ FAIL (${n}): ${msg}`); process.exit(1); }
  console.log(`✓ ${msg}`);
}
const MIN = 60000;
const t0 = Date.parse("2026-10-16T12:00:00Z");

// ── 대상: 노노카 본인 방송, 시각 미정 제외
assert(KING_KEY === "nonoka", "대상 키는 nonoka");
assert(kingTarget({ channel_key: "nonoka" }), "노노카 본인 방송은 대상");
assert(!kingTarget({ channel_key: "arale", collab_with: ["nonoka"] }), "다른 멤버 방송의 게스트는 대상 아님");
assert(!kingTarget({ channel_key: "nonoka", time_tbd: true }), "시각 미정은 대상 아님");
assert(!kingTarget(null), "null 안전");

// ── 지각 단계: ~3분 · 3~5분 · 5~10분 · 10~20분 · 20분~
assert(lateStage(0) === 0 && lateStage(-5000) === 0, "정시 · 이전은 연출 없음");
assert(lateStage(1000) === 1 && lateStage(3 * MIN - 1) === 1, "0~3분 = 1단계");
assert(lateStage(3 * MIN) === 2 && lateStage(5 * MIN - 1) === 2, "3~5분 = 2단계");
assert(lateStage(5 * MIN) === 3 && lateStage(10 * MIN - 1) === 3, "5~10분 = 3단계");
assert(lateStage(10 * MIN) === 4 && lateStage(20 * MIN - 1) === 4, "10~20분 = 4단계");
assert(lateStage(20 * MIN) === 5 && lateStage(MAX_LATE_MS) === 5, "20분~ = 5단계");
assert(lateStage(MAX_LATE_MS + 1) === 0, "3시간을 넘으면 연출 없음");
assert(lateStage(NaN) === 0, "NaN 안전");

// ── 시간 표기
assert(mmss(0) === "00:00" && mmss(61000) === "01:01" && mmss(12 * MIN + 34000) === "12:34", "mmss");
assert(mmss(-5) === "00:00", "음수는 00:00");

// ── 국면: 예고(upcoming) = 지각 단계
const item = (extra) => ({ channel_key: "nonoka", scheduled_start: new Date(t0).toISOString(), ...extra });
let p = phaseOf(item(), "upcoming", t0 + 4 * MIN);
assert(p && p.phase === "wait" && p.stage === 2 && p.late === 4 * MIN, "예정 +4분 → wait 2단계");
assert(phaseOf(item(), "upcoming", t0 - MIN) === null, "예정 시각 전에는 연출 없음");
assert(phaseOf(item({ channel_key: "arale" }), "upcoming", t0 + MIN) === null, "다른 멤버는 null");
assert(phaseOf(item(), "ended", t0 + MIN) === null, "종료 상태는 null");

// ── 국면: 라이브 = 지각 후 입장, 입장 후 3분까지만
const live = (lateMin) => item({ actual_start: new Date(t0 + lateMin * MIN).toISOString() });
p = phaseOf(live(8), "live", t0 + 8 * MIN + 5000);
assert(p && p.phase === "live" && p.waited === 8 * MIN && p.since === 5000, "8분 늦게 입장 → live, 기다린 시간 8분");
assert(phaseOf(live(8), "live", t0 + 8 * MIN + HOLD_MS - 1) !== null, "입장 후 2분59초까지는 유지");
assert(phaseOf(live(8), "live", t0 + 8 * MIN + HOLD_MS) === null, "입장 후 3분이 되면 평소 모습(null)");
assert(phaseOf(live(0.5), "live", t0 + 40000) === null, "30초만 늦은 입장은 연출 없음(1분 미만)");
assert(phaseOf(live(1), "live", t0 + MIN + 1000) !== null, "정확히 1분 늦은 입장부터 연출");
assert(phaseOf(item(), "live", t0 + 5 * MIN) === null, "actual_start 없는 라이브는 null");
assert(phaseOf(live(8), "live", t0 + 8 * MIN - 10000).since === 0, "시계가 느려 입장 전으로 보여도 since 는 0");
assert(ARRIVE_MS < HOLD_MS, "입장 연출은 유지 시간 안에 끝난다");

// ── 대신의 말: 단계마다 있고, 카운터는 3단계부터
for (let s = 1; s <= 5; s++) assert(speech("wait", s).length > 0, `${s}단계 말이 있다`);
assert(speech("wait", 1).some((x) => x[1] === "전하께서 곧 납시오~"), "1단계 = 정한 문구");
assert(speech("wait", 2).some((x) => x[1] === "전하께서 곧 행차할 것이오!") && speech("wait", 2).some((x) => x[1] === "잠시 대기들 하시오!"), "2단계 = 정한 문구");
assert(!speech("wait", 2).some((x) => x[0] === "c"), "2단계까지는 카운터 없음");
for (let s = 3; s <= 5; s++) assert(speech("wait", s).some((x) => x[0] === "c"), `${s}단계는 대기 시간 카운터`);
assert(speech("arrive", 0, 8 * MIN).some((x) => x[1] === "전하 납시오!" && x[2] === "big"), "입장 = 전하 납시오!");
assert(speech("arrive", 0, 8 * MIN).some((x) => x[1].includes("+08:00")), "입장 말에 기다린 시간");
assert(speech("live", 0, 8 * MIN).some((x) => x[1].includes("08:00")), "입장 후 말에 기다린 시간");
assert(speech("wait", 3).every((x) => x[0] !== "k" || x[1] === "대신이 고하오"), "말하는 이는 대신");

// ── PC 블록 글자
assert(blockLabel(1, 0) === "행차 준비" && blockLabel(2, 0) === "행차 준비", "1~2단계 = 행차 준비");
assert(blockLabel(3, 6 * MIN) === "대기 +06:00" && blockLabel(5, 25 * MIN) === "대기 +25:00", "3단계부터 대기 시간");

console.log(`\n✅ 모두 통과: ${n}/${n}`);
