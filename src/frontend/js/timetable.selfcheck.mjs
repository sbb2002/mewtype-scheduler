/**
 * timetable.js 순수 헬퍼 자동 테스트 (v4.1.0).
 * node timetable.selfcheck.mjs 로 실행. 프레임워크 없음. (DOM 접근 함수는 호출하지 않는다)
 */
import { dayWindow, classify, itemKeys, swipeDecision, dragFollow, planLater, laterCounts } from "./timetable.js";   // (v4.9.6) planLater · laterCounts 추가

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

// ── (v4.9.6) 이후 예고 · PC 표 보기 — 이번주(일 ~ 토, KST 달력 00:00) · 먼 미래 · 날짜 미정. now = 10/30(금) 01:00
const LN = kst("2026-10-30T01:00:00");
const up = (vid, ch, s, extra = {}) => ({ video_id: vid, channel_key: ch, state: "upcoming", scheduled_start: s, ...extra });
const PITEMS = [
  { video_id: "e1", channel_key: "arale", state: "end", actual_start: "2026-10-29T23:00:00+09:00", state_since: "2026-10-30T00:45:00+09:00" },
  { video_id: "l1", channel_key: "yuno", state: "live", actual_start: "2026-10-30T00:30:00+09:00" },
  up("u1", "ritsu", "2026-10-31T21:30:00+09:00"),
  up("u2", "miyako", "2026-10-31T00:00:00+09:00", { time_tbd: true }),
  up("u3", "arale", "2026-11-01T10:00:00+09:00"),
  up("u4", "nonoka", "2026-10-30T07:00:00+09:00"),
  up("u5", "yuno", "2026-12-24T19:00:00+09:00"),
  { video_id: "u6", channel_key: "ritsu", state: "upcoming" },   // 예정 시각 없음 → 날짜 미정
  { video_id: "c1", channel_key: "arale", state: "upcoming", scheduled_start: "2026-10-31T18:00:00+09:00", collab_with: ["yuno"] },
  { video_id: "x1", channel_key: "gamer", state: "upcoming", scheduled_start: "2026-10-31T18:00:00+09:00" },   // 멤버 아님 → 제외
];
const ARC = [
  { video_id: "a1", channel_key: "ritsu", actual_start: "2026-10-26T19:00:00+09:00", archived_at: "2026-10-26T21:10:00+09:00" },
  { video_id: "a2", channel_key: "ritsu", actual_start: "2026-10-24T19:00:00+09:00", archived_at: "2026-10-24T21:10:00+09:00" },   // 지난주 → 제외
  { video_id: "a3", channel_key: "ritsu", actual_start: "2026-10-27T19:00:00+09:00", archived_at: "2026-10-27T19:05:00+09:00" },   // 5분 → 제외
  { video_id: "e1", channel_key: "arale", actual_start: "2026-10-29T23:00:00+09:00", archived_at: "2026-10-30T00:45:00+09:00" },   // preview 와 같은 영상 → 한 번만
];
const P = planLater(PITEMS, ARC, LN, ORDER);
const ids = (i) => P.days[i].entries.map((e) => e.item.video_id);
const all = [...P.days.flatMap((d) => d.entries), ...P.far.flatMap((f) => f.entries), ...P.undated].map((e) => e.item.video_id);
assert(P.ws === kst("2026-10-25T00:00:00") && P.we === kst("2026-11-01T00:00:00") && P.today === 5, "금 01:00 → 이번주 10/25(일) ~ 11/1 00:00, 금요일 줄 = 5");
const e1 = P.days[4].entries.find((e) => e.item.video_id === "e1");
assert(ids(4).join() === "e1" && e1.state === "ended" && e1.end === kst("2026-10-30T00:45:00"), "목 23:00 시작 · 금 00:45 종료 → 목요일 줄 ended (end = state_since)");
assert(P.days[5].entries.some((e) => e.item.video_id === "l1" && e.state === "live"), "금 00:30 시작 방송 중 → 금요일 줄 live");
assert(ids(5).includes("u4"), "10/30 07:00 예정 → 금요일 줄(이번주 안)");
assert(ids(1).join() === "a1" && P.days[1].entries[0].end === kst("2026-10-26T21:10:00"), "보관함 10/26 19:00~21:10 → 월요일 줄 ended");
assert(!all.includes("a2") && !all.includes("a3"), "지난주 보관 · 5분짜리 보관은 넣지 않음");
assert(all.filter((v) => v === "e1").length === 1, "preview 와 같은 video_id 의 보관함은 건너뜀");
assert(ids(6).includes("u1") && ids(6).includes("u2"), "10/31 21:30 · 시각 미정(10/31) → 토요일 줄");
assert(P.days[6].entries.find((e) => e.item.video_id === "u2").item.time_tbd === true, "시각 미정 항목도 그날 줄(time_tbd 유지)");
const c1 = P.days[6].entries.find((e) => e.item.video_id === "c1");
assert(c1 && c1.keys.join() === "arale,yuno" && ids(6).filter((v) => v === "c1").length === 1, "합동 = 키 2개, 줄에는 한 번만");
assert(!all.includes("x1"), "멤버 5인이 아닌 채널은 제외");
assert(P.far.length === 2 && P.far[0].ds === kst("2026-11-01T00:00:00") && P.far[1].ds === kst("2026-12-24T00:00:00"), "먼 미래 = 날짜순 2줄 (11/1 · 12/24)");
assert(P.far[0].entries[0].item.video_id === "u3" && P.far[1].entries[0].item.video_id === "u5", "먼 미래 줄마다 그날 예고");
assert(P.undated.length === 1 && P.undated[0].item.video_id === "u6", "예정 시각이 없으면 날짜 미정");
assert(JSON.stringify(laterCounts(P)) === JSON.stringify({ week: 7, rest: 3, total: 10 }), "개수 — 이번주 7 · 먼 미래+날짜 미정 3 · 합 10");
// 토요일 10:00 — 오늘 · 내일 예고 구간(내일 = 11/1 04:00 ~ 11/2 04:00) 안은 먼 미래가 아니다
const P2 = planLater([
  up("s1", "arale", "2026-11-01T02:00:00+09:00"),
  up("s2", "arale", "2026-11-01T05:00:00+09:00"),
  up("s3", "arale", "2026-11-02T05:00:00+09:00"),
], [], kst("2026-10-31T10:00:00"), ORDER);
assert(P2.today === 6, "토요일 줄 = 6");
assert(P2.far.length === 1 && P2.far[0].entries[0].item.video_id === "s3", "토 10:00 기준 — 11/2 05:00 만 먼 미래 (11/1 새벽 · 아침은 내일 예고 구간)");

console.log(`\n✅ 모두 통과: ${n}/${n}`);
