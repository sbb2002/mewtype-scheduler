/**
 * timetable.js 순수 헬퍼 자동 테스트 (v4.1.0).
 * node timetable.selfcheck.mjs 로 실행. 프레임워크 없음. (DOM 접근 함수는 호출하지 않는다)
 */
import { dayWindow, classify, itemKeys, swipeDecision, dragFollow } from "./timetable.js";

let n = 0;
function assert(cond, msg) {
  n++;
  if (!cond) { console.error(`❌ FAIL (${n}): ${msg}`); process.exit(1); }
  console.log(`✓ ${msg}`);
}

const kst = (s) => Date.parse(s + "+09:00");
const ORDER = ["arale", "yuno", "nonoka", "ritsu", "miyako"];

// ── 오늘 구간 = KST 04:00 ~ 익일 04:00
let w = dayWindow(kst("2026-10-05T21:35:00"));
assert(w.ds === kst("2026-10-05T04:00:00") && w.de === kst("2026-10-06T04:00:00"), "21:35 → 당일 04:00 ~ 익일 04:00");
w = dayWindow(kst("2026-10-06T03:59:00"));
assert(w.ds === kst("2026-10-05T04:00:00"), "03:59 는 아직 전날 구간");
w = dayWindow(kst("2026-10-06T04:00:00"));
assert(w.ds === kst("2026-10-06T04:00:00"), "04:00 정각부터 새 구간");
assert(w.de - w.ds === 86400000, "구간 길이 24h");
// (v4.9.6) 내일 구간 = offset 1
w = dayWindow(kst("2026-10-29T05:00:00"), 1);
assert(w.ds === kst("2026-10-30T04:00:00") && w.de === kst("2026-10-31T04:00:00"), "05:00 의 내일 구간 = 10-30 04:00 ~ 10-31 04:00");
w = dayWindow(kst("2026-10-29T05:00:00"));
assert(w.ds === kst("2026-10-29T04:00:00"), "offset 0 은 오늘 구간 그대로");
// 실제 날짜는 10/30 이지만 04:00 전 → 오늘 예고 = 10/29 04:00 ~ 10/30 04:00, 내일 예고 = 10/30 04:00 ~ 10/31 04:00
w = dayWindow(kst("2026-10-30T01:00:00"));
assert(w.ds === kst("2026-10-29T04:00:00") && w.de === kst("2026-10-30T04:00:00"), "10/30 01:00 → 오늘 예고 = 10/29 04:00 ~ 10/30 04:00");
w = dayWindow(kst("2026-10-30T01:00:00"), 1);
assert(w.ds === kst("2026-10-30T04:00:00") && w.de === kst("2026-10-31T04:00:00"), "10/30 01:00 → 내일 예고 = 10/30 04:00 ~ 10/31 04:00");

// ── 분류
const now = kst("2026-10-05T21:35:00");
const items = [
  { channel_key: "yuno", state: "live", actual_start: "2026-10-05T13:32:00Z", scheduled_start: "2026-10-05T13:30:00Z", video_id: "L1" },
  { channel_key: "arale", state: "announced", scheduled_start: "2026-10-05T14:30:00Z" },                       // 23:30 KST → 오늘
  { channel_key: "ritsu", state: "upcoming", scheduled_start: "2026-10-06T12:00:00Z", video_id: "U1" },       // 익일 21:00 → 이후
  { channel_key: "nonoka", state: "announced", scheduled_start: "2026-10-05T15:00:00Z", time_tbd: true },     // 시각 미정 → 이후
  { channel_key: "miyako", state: "end", actual_start: "2026-10-04T21:59:00Z", state_since: "2026-10-04T23:10:00Z", video_id: "E1" },
  { channel_key: "unknown", state: "announced", scheduled_start: "2026-10-05T14:30:00Z" },                    // 모르는 채널 → 무시
];
const archive = [
  { channel_key: "miyako", actual_start: "2026-10-05T08:00:00Z", archived_at: "2026-10-05T10:00:00Z", video_id: "A1" },   // 오늘 이미 끝남
  { channel_key: "arale", actual_start: "2026-10-04T08:00:00Z", archived_at: "2026-10-04T10:00:00Z", video_id: "A2" },   // 어제 → 제외
  { channel_key: "yuno", actual_start: "2026-10-05T01:00:00Z", archived_at: "2026-10-05T01:05:00Z", video_id: "A3" },     // 5분 → 너무 짧아 제외
  { channel_key: "miyako", actual_start: "2026-10-04T21:59:00Z", archived_at: "2026-10-04T23:10:00Z", video_id: "E1" },   // preview 와 중복 → 제외
];
const r = classify(items, archive, now, ORDER);
assert(r.live.length === 1 && r.live[0].item.video_id === "L1", "live 1건");
assert(r.upcoming.length === 1 && r.upcoming[0].item.channel_key === "arale", "오늘 예정 = 아라레 23:30");
assert(r.tomorrow.length === 1 && r.tomorrow[0].item.video_id === "U1", "익일 21:00 ritsu = 내일 예고 1건 (04:00 하루 안)");
assert(r.later.length === 1 && r.later[0].channel_key === "nonoka", "이후 예고 1건 (시각 미정 nonoka)");
assert(r.ended.length === 2, "종료 = preview end + 아카이브(오늘 끝난 것만)");
assert(r.ended.some((e) => e.item.video_id === "A1" && e.end - e.start === 2 * 3600000), "아카이브 종료 방송은 실제 시작~종료 길이");
assert(!r.ended.some((e) => e.item.video_id === "A2" || e.item.video_id === "A3"), "어제 · 5분짜리 기록은 제외");
assert(r.ended.filter((e) => e.item.video_id === "E1").length === 1, "같은 영상은 중복 표시 안 함");

// ── 합동 팬아웃 키
const keys = itemKeys({ channel_key: "arale", collab_with: ["yuno", "ritsu", "bogus"] }, ORDER);
assert(keys.length === 3 && keys.includes("yuno") && !keys.includes("bogus"), "합동은 참여 멤버(알려진 채널)만");

// ── (v4.9.6) 내일 예고 구간 분류 · 종료 넘어가기 (now = 10-29 23:00)
const now2 = kst("2026-10-29T23:00:00");
const items2 = [
  { channel_key: "arale", state: "announced", scheduled_start: new Date(kst("2026-10-30T03:59:00")).toISOString() },                                // 04:00 전 = 오늘 예고
  { channel_key: "yuno", state: "announced", scheduled_start: new Date(kst("2026-10-30T10:00:00")).toISOString() },                                // 내일 10:00 (배열은 먼저 두어 정렬 확인)
  { channel_key: "ritsu", state: "announced", scheduled_start: new Date(kst("2026-10-30T04:00:00")).toISOString() },                               // 내일 04:00 = 내일 예고 시작
  { channel_key: "miyako", state: "announced", scheduled_start: new Date(kst("2026-10-31T04:00:00")).toISOString() },                              // 그다음 하루 → 이후 예고
  { channel_key: "nonoka", state: "announced", scheduled_start: "2026-10-30T00:00:00Z", time_tbd: true },                                           // 시각 미정 → 이후 예고
];
const r2 = classify(items2, [], now2, ORDER);
assert(r2.upcoming.length === 1 && r2.upcoming[0].item.channel_key === "arale" && r2.upcoming[0].end === null, "10-30 03:59 → 오늘 예정(upcoming)");
assert(r2.tomorrow.map((e) => e.item.channel_key).join() === "ritsu,yuno", "10-30 04:00 · 10:00 → 내일 예고, 시작순 정렬");
assert(r2.tomorrow.every((e) => typeof e.start === "number" && e.end === null), "내일 예고 항목은 start 있고 end === null");
assert(r2.later.map((i) => i.channel_key).join() === "nonoka,miyako", "10-31 04:00 · 시각 미정(time_tbd) → 이후 예고, scheduled_start 순");
assert(!r2.tomorrow.some((e) => e.item.channel_key === "nonoka") && !r2.upcoming.some((e) => e.item.channel_key === "nonoka"), "시각 미정은 오늘 · 내일 칸에 안 들어간다");

const endItem = { channel_key: "arale", state: "end", actual_start: new Date(kst("2026-10-29T23:00:00")).toISOString(), state_since: new Date(kst("2026-10-30T01:00:00")).toISOString(), video_id: "E2" };
assert(classify([endItem], [], kst("2026-10-30T03:59:00"), ORDER).ended.length === 1, "종료 방송은 04:00 전까지 종료 칸에 남는다");
assert(classify([endItem], [], kst("2026-10-30T04:00:00"), ORDER).ended.length === 0, "04:00 이 되면 종료 칸에서 빠진다");

// ── (v4.9.6) 일 넘기기 판정 · 끌기 거리 (w = 800)
assert(swipeDecision(-200, 0, 800, 0, true) === "next", "넘기기: 레일 25% 끌면 다음(내일) 화면 (경계 포함)");
assert(swipeDecision(-199, 0, 800, 0, true) === "stay", "넘기기: 25% 미만 · 느리면 제자리");
assert(swipeDecision(-50, -0.6, 800, 0, true) === "next", "넘기기: 짧아도 빠르게 튕기면 다음");
assert(swipeDecision(-400, 0, 800, 0, false) === "stay", "넘기기: 내일 예정 0건이면 다음 화면으로 안 간다");
assert(swipeDecision(300, 0, 800, 0, true) === "stay", "넘기기: 오늘 화면에서 오른쪽은 갈 곳 없음");
assert(swipeDecision(200, 0, 800, 1, true) === "prev", "넘기기: 내일 화면에서 오른쪽 25% 끌면 오늘");
assert(swipeDecision(-300, 0, 800, 1, true) === "stay", "넘기기: 내일 화면에서 왼쪽은 갈 곳 없음");
assert(swipeDecision(50, 0.6, 800, 1, true) === "prev", "넘기기: 내일 화면에서 빠르게 튕기면 오늘");
assert(dragFollow(-100, 800, 0, true) === -100, "끌기: 갈 수 있는 쪽은 1:1");
assert(dragFollow(-100, 800, 0, false) === -30, "끌기: 내일 0건이면 고무줄 30%");
assert(dragFollow(500, 800, 0, true) === 48, "끌기: 갈 곳 없는 쪽은 최대 48px");
assert(dragFollow(100, 800, 1, true) === 100, "끌기: 내일 화면에서 오른쪽은 1:1");
assert(dragFollow(-1000, 800, 0, true) === -800, "끌기: 1:1 도 레일 폭에서 멈춤");

console.log(`\n✅ 모두 통과: ${n}/${n}`);
