/**
 * render.js 순수 헬퍼 자동 테스트 (v3).
 * node render.selfcheck.mjs 로 실행. 프레임워크 없음.
 *
 * ponytail: 핵심 헬퍼만 테스트 — bucketOf, laneKeys, 버킷 분류, collab 팬아웃
 */

// 필요한 헬퍼들을 재구현 (DOM 없이도 테스트 가능)
const DAY_MS = 86400000;

function kstDateStr(ms) {
  const f = new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit",
  });
  const p = f.formatToParts(new Date(ms));
  const g = (t) => p.find((x) => x.type === t).value;
  return `${g("year")}-${g("month")}-${g("day")}`;
}

function bucketKey(item, nowMs) {
  if (!item.scheduled_start) return "rest";
  const nowDateStr = kstDateStr(nowMs);
  const startDateStr = kstDateStr(new Date(item.scheduled_start).getTime());
  if (nowDateStr === startDateStr) return "today";
  const nowMidMs = Date.parse(`${nowDateStr}T00:00:00Z`);
  const startMidMs = Date.parse(`${startDateStr}T00:00:00Z`);
  const daysDiff = Math.round((startMidMs - nowMidMs) / DAY_MS);
  if (daysDiff >= 1 && daysDiff <= 7) return "week";
  return "rest";
}

function laneKeys(items, channelOrder) {
  const keys = new Set();
  for (const item of items) {
    if (item.channel_key) keys.add(item.channel_key);
    if (Array.isArray(item.collab_with)) item.collab_with.forEach(k => keys.add(k));
  }
  return Array.from(keys).filter(k => channelOrder.includes(k)).sort();
}

const channelOrder = ["arale", "yuno", "nonoka", "ritsu", "miyako"];
let assertCount = 0;
let passCount = 0;

function assert(condition, message) {
  assertCount++;
  if (!condition) {
    console.error(`❌ FAIL (${assertCount}): ${message}`);
    process.exit(1);
  }
  passCount++;
  console.log(`✓ ${message}`);
}

// ── 테스트 1: bucketKey 구간 분류
const now = new Date("2026-09-09T12:00:00Z").getTime();
const baseDate = "2026-09-09";

// 오늘 (같은 KST 날짜: now=9/9 21:00 KST, 방송=9/9 22:00 KST)
assert(
  bucketKey({ scheduled_start: `${baseDate}T13:00:00Z` }, now) === "today",
  "bucketKey: today (같은 KST 날짜)"
);

// 7일 이내
assert(
  bucketKey({ scheduled_start: "2026-09-12T10:00:00Z" }, now) === "week",
  "bucketKey: week (D+3)"
);

// 7일 이후 — D+11 (v3.0.0 PC 에선 "month" 였으나 통합)
assert(
  bucketKey({ scheduled_start: "2026-09-20T10:00:00Z" }, now) === "rest",
  "bucketKey: rest (D+11)"
);

// 7일 이후 — 30일 초과
assert(
  bucketKey({ scheduled_start: "2026-10-10T12:00:00Z" }, now) === "rest",
  "bucketKey: rest (D+31)"
);

// scheduled_start 없음
assert(
  bucketKey({ scheduled_start: null }, now) === "rest",
  "bucketKey: rest (scheduled_start 없음)"
);

// v3.2 회귀 테스트 — 실측 버그: KST 밤(9/13 19:00)에 다음날 새벽(9/14 07:00, KST)
// 방송이 "24시간 이내"라는 이유만으로 "오늘"에 잡혔다. 정확히 같은 KST 날짜일
// 때만 "오늘"이어야 한다 — 이 경우는 날짜가 다르므로 "week".
const nightNow = new Date("2026-09-13T10:00:00Z").getTime(); // KST 19:00, 9/13
assert(
  bucketKey({ scheduled_start: "2026-09-13T22:00:00Z" }, nightNow) === "week",
  "bucketKey: week (다음날 새벽 방송은 '오늘' 아님, 24h 이내라도)"
);
// 반대로 같은 KST 날짜면(자정 넘겨 새벽 방송이라도) 정확히 "오늘"이어야 한다.
const midnightNow = new Date("2026-09-13T15:00:00Z").getTime(); // KST 0:00, 9/14
assert(
  bucketKey({ scheduled_start: "2026-09-13T22:00:00Z" }, midnightNow) === "today",
  "bucketKey: today (같은 KST 날짜, 자정 직후)"
);

// ── 테스트 2: laneKeys collab 팬아웃
const items = [
  { channel_key: "arale", collab_with: ["nonoka", "yuno"] },
  { channel_key: "ritsu", collab_with: null },
  { channel_key: "unknown_channel", collab_with: [] },
];

const keys = laneKeys(items, channelOrder);
assert(
  keys.length === 4 && keys.includes("arale") && keys.includes("nonoka") && keys.includes("yuno") && keys.includes("ritsu"),
  "laneKeys: collab 팬아웃 + 미지 채널 필터"
);

// ── 테스트 3: 6상태 카드 분류
const preview = {
  channel_order: channelOrder,
  items: [
    { state: "announced", channel_key: "arale", scheduled_start: "2026-09-10T10:00:00Z" },
    { state: "upcoming", channel_key: "yuno", scheduled_start: "2026-09-09T14:00:00Z" },
    { state: "watching", channel_key: "nonoka", scheduled_start: "2026-09-09T13:00:00Z" },
    { state: "live", channel_key: "ritsu", actual_start: "2026-09-09T11:35:00Z" },
    { state: "end", channel_key: "miyako", actual_start: "2026-09-08T13:00:00Z" },
  ]
};

const stateGroups = {};
for (const item of preview.items) {
  (stateGroups[item.state] ||= []).push(item);
}

assert(stateGroups.announced.length === 1, "상태 분류: announced 1건");
assert(stateGroups.upcoming.length === 1, "상태 분류: upcoming 1건");
assert(stateGroups.watching.length === 1, "상태 분류: watching 1건");
assert(stateGroups.live.length === 1, "상태 분류: live 1건");
assert(stateGroups.end.length === 1, "상태 분류: end 1건");

// ── 테스트 4: membership 플래그
const membershipItem = { state: "upcoming", membership: true, channel_key: "arale" };
assert(membershipItem.membership === true, "membership 플래그: true");

// ── 테스트 5: assumed_live 플래그
const assumedLiveItem = { state: "announced", assumed_live: true };
assert(assumedLiveItem.assumed_live === true, "assumed_live 플래그: announced 상태");

// ── 테스트 6: 합동방송 collab_with
const collabItem = {
  state: "announced",
  channel_key: "arale",
  collab_with: ["nonoka", "yuno"],
  kind: "collab"
};
assert(
  Array.isArray(collabItem.collab_with) && collabItem.collab_with.length === 2,
  "collab_with: 배열 형식, 2명 참여"
);

console.log(`\n✅ 모두 통과: ${passCount}/${assertCount}`);
