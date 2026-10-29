// weekpop.js — (v4.9.6) 모바일 「표」 버튼 · 이후 예고 시트.
// 모바일은 카드 보기로 고정이라 PC 표 보기의 이번주 테이블 · 먼 미래 테이블을 볼 수 없다 → 하단 멤버 아이콘 줄(#pager-dots)의
// 오른쪽 끝(플레이어 버튼 반대편)에 같은 모양의 버튼을 두고, 누르면 두 표를 세로로 쌓은 바텀 시트를 연다(플레이어 시트와 같은 움직임).
// 표 내용은 timetable.js 의 planLater · buildLaterTables 그대로 — 열 때마다 마지막 보드 데이터로 새로 그린다.
// 아이콘 · 내용은 createElement(NS) 로만 그린다(innerHTML 금지 규칙).

import { planLater, buildLaterTables, closeCardPop } from "./timetable.js";
import { wireSheetDrag } from "./sheetdrag.js";

const NS = "http://www.w3.org/2000/svg";
const LABEL = "이번주 · 먼 미래 예고 표";
const SHEET_MS = 320;

let data = null;            // renderBoard 가 넘겨 준 마지막 보드 데이터 { ctx, items, archiveItems }
let ui = null, isOpen = false, closeT = 0, lastFocus = null;

/** renderBoard 가 그릴 때마다 부른다 — 시트가 열려 있으면 새 데이터로 다시 그린다 */
export function setWeekData(ctx, items, archiveItems) {
  data = { ctx, items, archiveItems };
  if (isOpen) fill();
}

function svgEl(tag, attrs) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  return e;
}

/** 표(머리줄 + 세로 칸) 안에 점 두 개 + 오른쪽 꺾쇠(>) — 플레이어 버튼(CD + 음표 >)과 같은 틀 · 크기. 색은 currentColor */
function icon() {
  const svg = svgEl("svg", { viewBox: "0 0 40 24", "aria-hidden": "true", focusable: "false" });
  const line = { fill: "none", stroke: "currentColor", "stroke-width": "1.7", "stroke-linecap": "round", "stroke-linejoin": "round" };
  svg.appendChild(svgEl("rect", { ...line, x: "3", y: "4", width: "21", height: "16", rx: "2.5" }));   // 표 테두리
  svg.appendChild(svgEl("path", { ...line, d: "M3 9h21M10 9v11" }));                                       // 머리줄 · 날짜 칸
  svg.appendChild(svgEl("circle", { cx: "14.5", cy: "13", r: "1.6", fill: "currentColor" }));              // 점(방송)
  svg.appendChild(svgEl("circle", { cx: "19", cy: "16.5", r: "1.6", fill: "currentColor" }));
  svg.appendChild(svgEl("path", { ...line, d: "M33.5 8l4 4-4 4" }));                                        // >
  return svg;
}

/** 하단 멤버 아이콘 줄에 넣는 버튼 (render.js initMobileCarousel) */
export function createWeekButton() {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "player-btn week-btn";
  b.setAttribute("aria-label", LABEL);
  b.setAttribute("aria-haspopup", "dialog");
  b.title = LABEL;
  b.appendChild(icon());
  b.addEventListener("click", openWeek);
  return b;
}

function build() {
  if (ui) return;
  const scrim = document.createElement("div");
  scrim.className = "wk-scrim";
  scrim.hidden = true;
  const sheet = document.createElement("div");
  sheet.className = "wk-sheet";
  sheet.setAttribute("role", "dialog");
  sheet.setAttribute("aria-modal", "true");
  sheet.setAttribute("aria-labelledby", "wk-title");
  const head = document.createElement("div");
  head.className = "wk-sheet__head";
  const grab = document.createElement("i");
  grab.className = "wk-sheet__grab";
  grab.setAttribute("aria-hidden", "true");
  const title = document.createElement("h2");
  title.className = "wk-sheet__title";
  title.id = "wk-title";
  title.textContent = "이후 예고";
  const x = document.createElement("button");
  x.type = "button";
  x.className = "wk-sheet__x";
  x.textContent = "닫기";
  x.addEventListener("click", closeWeek);
  head.append(grab, title, x);
  const body = document.createElement("div");
  body.className = "wk-sheet__body";
  body.addEventListener("scroll", () => closeCardPop(), { passive: true });   // 카드 팝업은 문서 좌표에 고정이라 시트를 스크롤하면 닫는다
  sheet.append(head, body);
  scrim.appendChild(sheet);
  scrim.addEventListener("mousedown", (e) => { if (e.target === scrim) closeWeek(); });
  scrim.addEventListener("touchend", (e) => { if (e.target === scrim) { e.preventDefault(); closeWeek(); } });
  document.body.appendChild(scrim);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && isOpen && !document.querySelector(".tt-pop")) closeWeek(); }, true);   // 캡처 — 카드 팝업이 떠 있으면 Esc 는 팝업만 닫는다(timetable.js 가 닫음)
  wireSheetDrag({   // (마이크로 인터랙션) 머리줄을 아래로 끌어 내린다 — 플레이어 시트와 같다
    sheet,
    handles: [head],
    isOpen: () => isOpen,
    close: closeWeek,
    setScrim: (v) => {
      scrim.style.transition = v == null ? "" : "none";
      scrim.style.background = v == null ? "" : `rgba(0, 0, 0, ${(0.6 * v).toFixed(3)})`;
    },
  });
  ui = { scrim, sheet, body, x };
}

/** 표를 새로 그린다. 점 색(--lane-color)은 render.js sampleLaneColor 가 #board 안에만 넣으므로 보드의 멤버 레인에서 옮겨 온다 */
function fill() {
  if (!ui || !data) return;
  closeCardPop();
  const { ctx, items, archiveItems } = data;
  const nowMs = Date.now();
  const tables = buildLaterTables({ ...ctx, nowMs }, planLater(items, archiveItems, nowMs, ctx.order));
  ui.body.replaceChildren(tables);
  const board = document.getElementById("board");
  for (const seg of ui.body.querySelectorAll("[data-channel]")) {
    const lane = board && board.querySelector(`.lane[data-channel="${CSS.escape(seg.dataset.channel)}"]`);
    const c = lane && lane.style.getPropertyValue("--lane-color");
    if (c) seg.style.setProperty("--lane-color", c);
  }
}

export function openWeek() {
  build();
  if (isOpen || !data) return;
  clearTimeout(closeT);
  fill();
  lastFocus = document.activeElement;
  isOpen = true;
  ui.scrim.hidden = false;
  void ui.scrim.offsetWidth;                 // 시작 상태(아래쪽)를 먼저 확정해야 transition 이 돈다
  ui.scrim.classList.add("is-open");
  document.documentElement.classList.add("wk-lock");
  ui.body.scrollTop = 0;
  requestAnimationFrame(() => ui.x.focus({ preventScroll: true }));
}

export function closeWeek() {
  if (!ui || !isOpen) return;
  isOpen = false;
  closeCardPop();
  ui.scrim.classList.remove("is-open");
  document.documentElement.classList.remove("wk-lock");
  clearTimeout(closeT);
  closeT = setTimeout(() => { ui.scrim.hidden = true; }, SHEET_MS + 40);
  if (lastFocus && typeof lastFocus.focus === "function") lastFocus.focus({ preventScroll: true });
}
