// monitormines.selfcheck.mjs — node src/frontend/js/monitormines.selfcheck.mjs
import assert from "node:assert/strict";
import { createGame, placeMines, reveal, toggleFlag, count, neighbors, flagsUsed } from "./monitormines.js";

// 첫 누르기는 늘 안전
for (let t = 0; t < 200; t++) {
  const g = createGame();
  assert.equal(reveal(g, t % g.n), "open");
  assert.equal(g.mine.filter(Boolean).length, 3);
}
// 지뢰 고정 판으로 규칙 확인 — 지뢰 = 0, 1, 7(왼쪽 위 모서리 근처)
const fixed = () => { const g = createGame(); g.mine = new Array(g.n).fill(false); for (const i of [0, 1, 7]) g.mine[i] = true; return g; };
{
  const g = fixed();
  assert.equal(count(g, 8), 3);
  assert.equal(neighbors(g, 0).length, 3);
  // 먼 빈칸을 누르면 이어진 빈칸 + 테두리 숫자 칸이 함께 열리고, 지뢰는 열리지 않는다
  assert.equal(reveal(g, 34), "open");
  assert.ok(g.open[8] && g.open[2] && g.open[14], "테두리 숫자 칸도 열림");
  assert.ok(!g.open[0] && !g.open[1] && !g.open[7]);
  assert.equal(g.open.filter(Boolean).length, 32);
}
{
  // 깃발 — 최대 3개, 깃발 칸은 누르기가 먹지 않음, 틀린 3개면 아무 일 없음, 맞는 3개면 성공
  const g = fixed();
  reveal(g, 34);
  const g2 = fixed();
  assert.equal(toggleFlag(g2, 20), "flag");
  assert.equal(reveal(g2, 20), "none", "깃발 칸은 누르기 막힘");
  assert.equal(toggleFlag(g2, 0), "flag");
  assert.equal(toggleFlag(g2, 1), "flag");
  assert.equal(toggleFlag(g2, 7), "full");
  assert.equal(g2.state, "play", "틀린 3개면 계속");
  assert.equal(toggleFlag(g2, 20), "unflag");
  assert.equal(toggleFlag(g2, 7), "win");
  assert.equal(flagsUsed(g2), 3);
  // 지뢰를 누르면 터짐
  const g3 = fixed();
  assert.equal(reveal(g3, 1), "boom");
  assert.equal(g3.state, "boom");
  assert.equal(reveal(g3, 30), "none");
}
// 무작위 놓기는 safe 칸을 뺀다
{
  const g = createGame(); placeMines(g, 5, () => 0);
  assert.ok(!g.mine[5]);
}
console.log("monitormines self-check ok");
