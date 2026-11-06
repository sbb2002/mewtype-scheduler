// node src/frontend/js/bgconsole.selfcheck.mjs — 콘솔 투영 사상(quadMatrix)이 상자 네 모서리를 화면 네 점에 정확히 보내는지.
import assert from "node:assert/strict";
import { quadMatrix } from "./bgconsole.js";

function apply(m, x, y) {
  const v = m.slice(9, -1).split(",").map(Number);   // matrix3d 열 우선 16개
  const X = v[0] * x + v[4] * y + v[12], Y = v[1] * x + v[5] * y + v[13], Wd = v[3] * x + v[7] * y + v[15];
  return [X / Wd, Y / Wd];
}

const cases = [
  [[[10, 20], [210, 20], [210, 220], [10, 220]], 200, 200],            // 평행 이동만
  [[[120, 300], [260, 300], [330, 420], [40, 420]], 200, 200],         // 비스듬히 본 바닥(사다리꼴)
  [[[50, 80], [150, 95], [140, 260], [60, 240]], 200, 290],            // 원근 있는 세로 판
];
for (const [p, w, h] of cases) {
  const m = quadMatrix(p, w, h);
  assert.ok(m, "사상이 만들어져야 한다");
  const got = [apply(m, 0, 0), apply(m, w, 0), apply(m, w, h), apply(m, 0, h)];
  got.forEach((g, i) => { assert.ok(Math.abs(g[0] - p[i][0]) < 0.01 && Math.abs(g[1] - p[i][1]) < 0.01, `모서리 ${i}: ${g} ≠ ${p[i]}`); });
}
assert.equal(quadMatrix([[0, 0], [0, 0], [0, 0], [0, 0]], 10, 10), null, "한 점으로 뭉치면 null");
console.log("bgconsole selfcheck OK");
