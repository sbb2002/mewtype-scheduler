/**
 * timetable.js 순수 헬퍼 자동 테스트 (v4.1.0).
 * node timetable.selfcheck.mjs 로 실행. 프레임워크 없음. (DOM 접근 함수는 호출하지 않는다)
 */
import { dayWindow, classify, itemKeys } from "./timetable.js";

let n = 0;
function assert(cond, msg) {
  n++;
  if (!cond) { console.error(`❌ FAIL (${n}): ${msg}`); process.exit(1); }
  console.log(`✓ ${msg}`);
}

const kst = (s) => Date.parse(s + "+09:00");
const ORDER = ["arale", "yuno", "nonoka", "ritsu", "miyako"];

// ── 오늘 구간 = KST 06:00 ~ 익일 06:00
let w = dayWindow(kst("2026-10-05T21:35:00"));
assert(w.ds === kst("2026-10-05T06:00:00") && w.de === kst("2026-10-06T06:00:00"), "21:35 → 당일 06:00 ~ 익일 06:00");
w = dayWindow(kst("2026-10-06T05:59:00"));
assert(w.ds === kst("2026-10-05T06:00:00"), "05:59 는 아직 전날 구간");
w = dayWindow(kst("2026-10-06T06:00:00"));
assert(w.ds === kst("2026-10-06T06:00:00"), "06:00 정각부터 새 구간");
assert(w.de - w.ds === 86400000, "구간 길이 24h");

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
assert(r.later.map((i) => i.channel_key).join() === "nonoka,ritsu", "이후 예고 2건 (시각 미정 + 구간 밖), 날짜순");
assert(r.ended.length === 2, "종료 = preview end + 아카이브(오늘 끝난 것만)");
assert(r.ended.some((e) => e.item.video_id === "A1" && e.end - e.start === 2 * 3600000), "아카이브 종료 방송은 실제 시작~종료 길이");
assert(!r.ended.some((e) => e.item.video_id === "A2" || e.item.video_id === "A3"), "어제 · 5분짜리 기록은 제외");
assert(r.ended.filter((e) => e.item.video_id === "E1").length === 1, "같은 영상은 중복 표시 안 함");

// ── 합동 팬아웃 키
const keys = itemKeys({ channel_key: "arale", collab_with: ["yuno", "ritsu", "bogus"] }, ORDER);
assert(keys.length === 3 && keys.includes("yuno") && !keys.includes("bogus"), "합동은 참여 멤버(알려진 채널)만");

console.log(`\n✅ 모두 통과: ${n}/${n}`);
