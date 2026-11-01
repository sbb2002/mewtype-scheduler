// 길게 눌러 주소 복사 순수 로직 self-check — node src/frontend/js/longcopy.selfcheck.mjs
import assert from "node:assert/strict";
import { copyTarget, pickTipTarget, tipPosition } from "./longcopy.js";

const CH = "https://www.youtube.com/@arale_yumemita";
const V = "https://www.youtube.com/watch?v=abc";
assert.deepEqual(copyTarget({ video_id: "abc", url: V }, CH), { url: V, kind: "video" });
assert.deepEqual(copyTarget({ url: CH }, CH), { url: CH, kind: "channel" });          // 영상 미확정 = 채널 주소
assert.deepEqual(copyTarget({ video_id: "abc" }, CH), { url: CH, kind: "channel" });  // 주소가 비면 채널
assert.equal(copyTarget({}, ""), null);
assert.equal(copyTarget({ url: "#" }, undefined), null);
assert.equal(copyTarget({ video_id: "x", url: "javascript:alert(1)" }, undefined), null);

const order = ["arale", "yuno", "nonoka", "ritsu", "miyako"];
const c = (key, state, start) => ({ key, state, start });
// 아라레 먼저 — 다른 멤버가 더 가까워도
assert.equal(pickTipTarget([c("yuno", "live", 1), c("arale", "upcoming", 9)], order).key, "arale");
// 같은 멤버는 방송 중 → 가까운 예정 → 최근 종료
assert.equal(pickTipTarget([c("arale", "ended", 5), c("arale", "upcoming", 9), c("arale", "live", 3)], order).state, "live");
assert.equal(pickTipTarget([c("arale", "upcoming", 20), c("arale", "upcoming", 10)], order).start, 10);
assert.equal(pickTipTarget([c("arale", "ended", 5), c("arale", "ended", 7)], order).start, 7);
// 시각 미정은 시각 있는 예정 뒤
assert.equal(pickTipTarget([c("arale", "upcoming", NaN), c("arale", "upcoming", 10)], order).start, 10);
assert.equal(pickTipTarget([], order), null);

const r = (top, left = 100, width = 200, height = 100) => ({ top, left, width, height, bottom: top + height });
let p = tipPosition(r(300), 180, 34, 400, 800);
assert.equal(p.below, false); assert.equal(p.top, 256); assert.equal(p.left, 110); assert.equal(p.tail, 90);
p = tipPosition(r(10), 180, 34, 400, 800);             // 위에 자리가 없으면 아래
assert.equal(p.below, true); assert.equal(p.top, 120);
p = tipPosition(r(300, 0, 40), 180, 34, 400, 800);     // 왼쪽 끝 — 화면 안, 꼬리는 카드 쪽
assert.equal(p.left, 12); assert.equal(p.tail, 14);

console.log("longcopy selfcheck OK");
