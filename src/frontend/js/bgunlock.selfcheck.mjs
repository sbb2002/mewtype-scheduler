// bgunlock.selfcheck.mjs — node src/frontend/js/bgunlock.selfcheck.mjs
import assert from "node:assert/strict";
import { emptyState, parseState, legacyUnlocks, unlock, has, arrive, randomDest, chooserItems, allDeepVisited, unlockAll, loadUnlock, saveUnlock, keyOfIdx, DEEP_FIELDS, onFound, ZODIAC } from "./bgunlock.js";

// 저장 글 읽기 — 틀린 값은 버린다
{
  const s = parseState('{"unl":["space","nope","hold"],"vis":["crab","crab","mars"],"found":["saturn"],"seen":{"holdNotice":true,"x":true}}');
  assert.deepEqual(s.unl, ["space", "hold"]);
  assert.deepEqual(s.vis, ["crab"]);
  assert.deepEqual(s.seen, { holdNotice: true });
  assert.deepEqual(parseState("{bad"), emptyState());
}
// 옛 사용자 = 패널 기억이 있으면 세 하늘 · 길게 누르기 열림
assert.deepEqual(legacyUnlocks(null, null), []);
assert.deepEqual(legacyUnlocks("pink", null), ["space", "hold", "earth"]);
{
  const mem = { "bgindoor": "space" }, st = { getItem: (k) => mem[k] ?? null, setItem: (k, v) => { mem[k] = v; } };
  const s = loadUnlock(st);
  assert.ok(has(s, "space") && has(s, "hold") && has(s, "earth") && !has(s, "moon"));
  saveUnlock(st, s);
  delete mem.bgindoor;
  assert.ok(has(loadUnlock(st), "earth"), "저장한 뒤엔 저장값을 쓴다");
}
// 처음엔 고르기 창 없음 → 바로 무작위
{
  const s = emptyState();
  assert.equal(chooserItems(s, "space"), null);
  // 무작위 = 지금 있는 곳을 뺀 딥필드, 가 본 곳도 나온다
  const seen = new Set();
  for (let i = 0; i < 500; i++) seen.add(randomDest(s, "crab"));
  assert.ok(!seen.has("crab") && seen.size === 4 && !seen.has("moon"));
  // 도착 기록
  assert.equal(arrive(s, "crab"), "deep");
  assert.equal(arrive(s, "crab"), null);
  const items = chooserItems(s, "crab");
  assert.deepEqual(items.map((x) => x.key), ["random", "crab", "space"]);
  assert.equal(items[1].here, true);
  assert.deepEqual(chooserItems(s, "space").map((x) => x.key), ["random", "crab"], "기본 우주에선 「기본 우주로」 없음");
}
// 다섯 곳을 다 가 보면 무작위 = 달 궤도, 도착하면 달 궤도 해금 → 다음 무작위는 다시 딥필드
{
  const s = emptyState();
  for (const d of DEEP_FIELDS) arrive(s, d.key);
  assert.ok(allDeepVisited(s));
  assert.equal(randomDest(s, "tara"), "moon");
  assert.equal(arrive(s, "moon"), "moon");
  assert.equal(arrive(s, "moon"), null);
  assert.notEqual(randomDest(s, "moon"), "moon");
  assert.ok(chooserItems(s, "moon").some((x) => x.key === "moon" && x.here));
}
// 해금 · 모두 열기
{
  const s = emptyState();
  assert.equal(unlock(s, "space"), true);
  assert.equal(unlock(s, "space"), false);
  assert.equal(unlock(s, "bogus"), false);
  unlockAll(s, ["saturn"]);
  assert.equal(s.unl.length, 7);
  assert.ok(allDeepVisited(s) && s.found.includes("saturn"));
}
assert.equal(keyOfIdx(1), "moon");
assert.equal(keyOfIdx(0), "smacs");
assert.equal(keyOfIdx(-1), null);
console.log("bgunlock self-check ok");
// 찾기 규칙
{
  const s = emptyState();
  let r = onFound(s, { id: "saturn", unlock: "space" });
  assert.ok(r.fresh && r.k === "NEW" && has(s, "space") && r.toast);
  r = onFound(s, { id: "saturn", unlock: "space" });
  assert.ok(!r.fresh && r.k === "" && !r.toast, "다시 잡으면 이름만");
  for (const z of ZODIAC.slice(0, 4)) { r = onFound(s, { id: z.id, zod: true, who: z.who }); assert.equal(r.k, "별자리"); assert.ok(!has(s, "light")); }
  r = onFound(s, { id: ZODIAC[4].id, zod: true, who: ZODIAC[4].who });
  assert.ok(has(s, "light") && r.toast === "별빛 조명 열림");
  r = onFound(s, { id: "earthT", unlock: "earth" });
  assert.ok(has(s, "earth") && has(s, "ymmt") && has(s, "freenav"));
  r = onFound(s, { id: "d_crab" });
  assert.ok(r.fresh && r.k === "" && !r.toast);
}
console.log("bgunlock onFound ok");
