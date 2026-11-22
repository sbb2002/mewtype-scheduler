// bgstorylogic.js self-check — node src/frontend/js/bgstorylogic.selfcheck.mjs
import assert from "node:assert/strict";
import { emptyStory, parseStory, songOf, beginStory, addLine, converged, discover, LINE_KEYS, lineAngle } from "./bgstorylogic.js";
import { parseState, emptyState, saveUnlock, loadUnlock, DEEP_FIELDS } from "./bgunlock.js";

const playing = songOf({ state: "playing", id: "a1", title: "KEEP ON" });
const silent = songOf({ state: "paused", id: "a1", title: "KEEP ON" });
assert.deepEqual(playing, { on: true, id: "a1", title: "KEEP ON" });
assert.equal(silent.on, false);
assert.equal(songOf(null).on, false);
assert.equal(songOf({ state: "buffering", id: "b", title: "x" }).on, true);

// 1 출발 — 처음 한 번만, 이미 탐험한 곳은 조용히 채움
{
  const st = emptyStory();
  assert.deepEqual(beginStory(st, ["crab", "nope"], playing), { title: "KEEP ON" });
  assert.deepEqual(st.lines, ["crab"]);
  assert.deepEqual(st.song, { id: "a1", title: "KEEP ON" });
  assert.equal(beginStory(st, [], playing), null, "두 번째 진입엔 출발 장면 없음");
  const s2 = emptyStory();
  assert.deepEqual(beginStory(s2, [], silent), { title: null }, "무음 출발");
  assert.equal(s2.song, null);
}
// 2 추적 — 장소마다 한 번 · 딥필드만 · 다섯이면 겹침
{
  const st = emptyStory(); beginStory(st, [], silent);
  assert.equal(addLine(st, "orion"), true);
  assert.equal(addLine(st, "orion"), false, "재방문 = 다시 안 쌓임");
  assert.equal(addLine(st, "moon"), false);
  assert.equal(converged(st), false);
  for (const k of ["tara", "smacs", "pillars"]) addLine(st, k);
  assert.equal(converged(st), false);
  assert.equal(addLine(st, "crab"), true);
  assert.equal(converged(st), true, "순서 무관 다섯 개");
}
// 3 발견 — 한 번, 곡 비교, 무음도 완료
{
  const st = emptyStory(); beginStory(st, [], playing);
  const r = discover(st, playing);
  assert.deepEqual(r, { title: "KEEP ON", same: true });
  assert.equal(st.done, true);
  assert.equal(discover(st, playing), null, "끝난 뒤 다시 발견 장면 없음");
  assert.equal(addLine(st, "crab"), false, "끝난 뒤 방위선 적립 없음");
  assert.equal(beginStory(st, [], playing), null, "끝난 뒤 출발 장면 없음");
  const s2 = emptyStory(); beginStory(s2, [], playing);
  assert.deepEqual(discover(s2, songOf({ state: "playing", id: "zz", title: "Dream Voyage" })), { title: "Dream Voyage", same: false }, "곡이 바뀜");
  const s3 = emptyStory(); beginStory(s3, [], playing);
  assert.deepEqual(discover(s3, silent), { title: null, same: false }, "무음이어도 완료");
  assert.equal(s3.done, true);
  const s4 = emptyStory();   // 출발 장면 없이(배경 보기 진입 기록 없이) 바로 발견해도 끝난다
  assert.ok(discover(s4, silent));
}
// 저장 · 복원 — 해금 기록과 같이, 틀린 값은 버림, 해금 기록을 건드리지 않음
{
  assert.deepEqual(parseStory(null), emptyStory());
  assert.deepEqual(parseStory({ intro: true, lines: ["crab", "crab", "x"], done: false, song: { id: "a", title: 3 } }), { intro: true, lines: ["crab"], done: false, song: { id: "a", title: "" } });
  assert.equal(parseStory({ done: true }).intro, true, "done 이면 intro 도");
  const mem = new Map(); const store = { getItem: (k) => (mem.has(k) ? mem.get(k) : null), setItem: (k, v) => mem.set(k, v) };
  const s = emptyState(); s.unl.push("space", "hold"); s.vis.push("crab"); s.story.done = true; s.story.intro = true;
  assert.ok(saveUnlock(store, s));
  const back = loadUnlock(store);
  assert.deepEqual(back.unl, ["space", "hold"]);
  assert.deepEqual(back.vis, ["crab"]);
  assert.equal(back.story.done, true, "완료가 새로고침 뒤에도 남는다");
  const old = parseState('{"v":1,"unl":["space","hold","moon","earth"],"vis":["crab"],"found":["earthT"],"seen":{}}');
  assert.deepEqual(old.story, emptyStory(), "스토리 이전 저장값 = 스토리 처음부터, 해금은 그대로");
  assert.deepEqual(old.unl, ["space", "hold", "moon", "earth"]);
}
assert.deepEqual(LINE_KEYS, DEEP_FIELDS.map((d) => d.key), "방위선 자리 = 딥필드 순서");
assert.equal(new Set(LINE_KEYS.map(lineAngle)).size, 5);
console.log("bgstorylogic self-check ok");
