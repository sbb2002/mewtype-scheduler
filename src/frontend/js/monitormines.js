// monitormines.js — 모니터링 페이지 「모두 열기」 지뢰찾기의 규칙(순수, DOM 없음 · self-check = monitormines.selfcheck.mjs).
// 정본 = devpapers docs/plan/bg-dome/hud_implementation.md 「모두 열기」(운영자 11-09). 판 = 5 × 7(가로 7 · 세로 5), 지뢰 3개.
//   누르기 = 지뢰면 터짐 · 아니면 둘레 8칸 지뢰 수(0 = 빈칸). 빈칸이면 이어진 빈칸이 연쇄로 열리고 그 테두리 숫자 칸도 함께 열린다(일반 규칙).
//   첫 누르기는 늘 안전 — 지뢰는 첫 누르기 뒤에 그 칸을 빼고 놓는다(일반 관례).
//   길게 누르기 = 깃발(최대 3개, 깃발 칸은 누르기가 먹지 않음, 다시 길게 누르면 뺌). 깃발 3개가 모두 지뢰 위면 성공.
//   맞았는지는 깃발 3개가 모두 맞을 때까지 어떤 표시도 하지 않는다(틀린 3개면 아무 일 없이 계속).

export const ROWS = 5, COLS = 7, MINES = 3, MAX_FLAGS = 3;

export function createGame(rows = ROWS, cols = COLS, mines = MINES) {
  return { rows, cols, mines, n: rows * cols, mine: null, open: new Array(rows * cols).fill(false), flag: new Array(rows * cols).fill(false), state: "play" };
}
export function neighbors(g, i) {
  const r = Math.floor(i / g.cols), c = i % g.cols, out = [];
  for (let dr = -1; dr <= 1; dr++) for (let dc = -1; dc <= 1; dc++) {
    if (!dr && !dc) continue;
    const rr = r + dr, cc = c + dc;
    if (rr >= 0 && rr < g.rows && cc >= 0 && cc < g.cols) out.push(rr * g.cols + cc);
  }
  return out;
}
/** 지뢰 놓기 — safe 칸을 뺀 칸에서 무작위 */
export function placeMines(g, safe, rand = Math.random) {
  const pool = [];
  for (let i = 0; i < g.n; i++) if (i !== safe) pool.push(i);
  g.mine = new Array(g.n).fill(false);
  for (let k = 0; k < g.mines; k++) { const j = Math.floor(rand() * pool.length); g.mine[pool[j]] = true; pool.splice(j, 1); }
}
export const count = (g, i) => neighbors(g, i).filter((j) => g.mine[j]).length;
export const flagsUsed = (g) => g.flag.filter(Boolean).length;

/** 누르기. 돌려줌 = "boom" | "open" | "none"(이미 열림 · 깃발 · 끝난 판) */
export function reveal(g, i, rand) {
  if (g.state !== "play" || g.open[i] || g.flag[i]) return "none";
  if (!g.mine) placeMines(g, i, rand);
  if (g.mine[i]) { g.state = "boom"; g.open[i] = true; return "boom"; }
  const stack = [i];
  while (stack.length) {
    const j = stack.pop();
    if (g.open[j] || g.flag[j]) continue;
    g.open[j] = true;
    if (count(g, j) === 0) for (const k of neighbors(g, j)) if (!g.open[k] && !g.mine[k]) stack.push(k);
  }
  return "open";
}
/** 길게 누르기 = 깃발 꽂기 · 빼기. 돌려줌 = "flag" | "unflag" | "full"(3개 다 씀) | "none" | "win" */
export function toggleFlag(g, i) {
  if (g.state !== "play" || g.open[i]) return "none";
  if (g.flag[i]) { g.flag[i] = false; return "unflag"; }
  if (flagsUsed(g) >= MAX_FLAGS) return "full";
  g.flag[i] = true;
  if (g.mine && flagsUsed(g) === g.mines && g.flag.every((f, k) => !f || g.mine[k])) { g.state = "win"; return "win"; }
  return "flag";
}
