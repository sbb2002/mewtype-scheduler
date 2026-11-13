// bgmusic.selfcheck.mjs — node src/frontend/js/bgmusic.selfcheck.mjs
import assert from "node:assert/strict";
import { nextMusic, soloOf, rimGradient, rgbOf } from "./bgmusic.js";

const off = { on: false, members: [] };
// 재생 → 켜짐, 멤버 그대로
let m = nextMusic(off, { state: "playing", members: ["yuno"] });
assert.deepEqual(m, { on: true, members: ["yuno"] });
assert.equal(soloOf(m), "yuno");
// 버퍼링은 앞 상태를 이어 간다(멤버가 비어 오면 앞 멤버)
assert.deepEqual(nextMusic(m, { state: "buffering", members: [] }), { on: true, members: ["yuno"] });
// 꺼진 상태에서 버퍼링은 켜지 않는다
assert.equal(nextMusic(off, { state: "buffering", members: ["yuno"] }).on, false);
// 일시정지 · 끝 → 꺼짐
assert.equal(nextMusic(m, { state: "paused", members: ["yuno"] }).on, false);
assert.equal(nextMusic(m, { state: "ended", members: ["yuno"] }).on, false);
// 멤버 없는 곡은 켜지 않는다 · 잘못된 값은 버린다
assert.equal(nextMusic(off, { state: "playing", members: [] }).on, false);
assert.deepEqual(nextMusic(off, { state: "playing", members: ["arale", 3, "", null] }).members, ["arale"]);
assert.deepEqual(nextMusic(off, null), off);
// 솔로 판정 — 둘 이상 · 꺼짐이면 null
assert.equal(soloOf({ on: true, members: ["arale", "ritsu"] }), null);
assert.equal(soloOf({ on: false, members: ["arale"] }), null);
// 그라데이션
const C = { arale: "#FFD27A", yuno: "#FF6688", ritsu: "#6296EC" };
assert.equal(rimGradient([], C), "");
assert.equal(rimGradient(["nobody"], C), "");
assert.match(rimGradient(["yuno"], C), /^linear-gradient\(90deg, transparent, #FF6688 18%, #FF6688 82%, transparent\)$/);
assert.equal(rimGradient(["arale", "ritsu"], C), "linear-gradient(90deg, transparent, #FFD27A 25%, #6296EC 75%, transparent)");
assert.equal(rimGradient(["arale", "bad", "yuno"], { ...C, bad: "red" }), "linear-gradient(90deg, transparent, #FFD27A 25%, #FF6688 75%, transparent)");
// 색 변환
assert.equal(rgbOf("#FF6688"), "255,102,136");
assert.equal(rgbOf("nope"), null);
console.log("bgmusic self-check 통과");
