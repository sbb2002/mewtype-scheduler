// playerbtn.js — (v4.2.0) 「CD + 음표 >」 아이콘 버튼.
// 모바일: 하단 멤버 아이콘(#pager-dots) 줄의 맨 왼쪽 / PC: 화면 좌상단(고정).
// 눌렀을 때의 동작은 아래 PLAYER_BUTTON_EVENT 를 main.js 가 받아 player.js(openPlayer)를 여는 것.
// 아이콘은 createElementNS 로만 그린다(innerHTML 금지 규칙).

import { fetchPreview } from "./api.js";
import { SONGS_URL, SONGS_FALLBACK_URL } from "./config.js";
import { hasNewSong } from "./songs.js";

const NS = "http://www.w3.org/2000/svg";
export const PLAYER_BUTTON_LABEL = "음악 · 플레이어";
export const PLAYER_BUTTON_EVENT = "mew:player-open";   // 클릭 시 document 로 발행 — main.js 가 받아 플레이어 팝업을 연다

function svgEl(tag, attrs) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  return e;
}

/** CD(바깥 원 · 가운데 구멍 · 빛 반사) + 음표 + 오른쪽 꺾쇠(>). 색은 currentColor. */
function icon() {
  const svg = svgEl("svg", { viewBox: "0 0 40 24", "aria-hidden": "true", focusable: "false" });
  const line = { fill: "none", stroke: "currentColor", "stroke-width": "1.7", "stroke-linecap": "round", "stroke-linejoin": "round" };
  svg.appendChild(svgEl("circle", { ...line, cx: "10", cy: "12", r: "8" }));            // CD
  svg.appendChild(svgEl("circle", { ...line, cx: "10", cy: "12", r: "2.2" }));          // 가운데 구멍
  svg.appendChild(svgEl("path", { ...line, "stroke-width": "1.3", d: "M5.2 8.2a6 6 0 0 1 3-2" }));   // 빛 반사
  svg.appendChild(svgEl("ellipse", { cx: "23", cy: "17.4", rx: "2.6", ry: "2.1", fill: "currentColor", stroke: "none" }));   // 음표 머리
  svg.appendChild(svgEl("path", { ...line, d: "M25.4 17V5.2c0 2.6 3.6 2.4 3.6 5.6" }));                                      // 음표 기둥 · 꼬리
  svg.appendChild(svgEl("path", { ...line, d: "M33.5 8l4 4-4 4" }));                                                          // >
  return svg;
}

/**
 * @param {string} cls 추가 클래스 (위치/크기는 CSS 가 정한다)
 * @returns {HTMLButtonElement}
 */
let hasNew = false;   // 최근 7일 안에 등록된 신곡이 있는가 — 켜지면 <html data-new-song> + 버튼 접근성 이름에 반영

function applyNew() {
  if (hasNew) document.documentElement.setAttribute("data-new-song", "");
  else document.documentElement.removeAttribute("data-new-song");
  const label = hasNew ? `${PLAYER_BUTTON_LABEL} (신곡 NEW)` : PLAYER_BUTTON_LABEL;
  for (const b of document.querySelectorAll(".player-btn")) { b.setAttribute("aria-label", label); b.title = label; }
}

/** 곡 목록(data 브랜치 songs.json, 없으면 정적 파일)을 한 번 읽어 NEW 배지를 켠다. 실패하면 조용히 배지 없음. 버튼이 다시 그려져도 CSS 가 속성을 보고 배지를 그린다. */
export async function initNewSongBadge() {
  try {
    let r = await fetchPreview(SONGS_URL);
    if (!(r.ok && r.data && Array.isArray(r.data.songs))) r = await fetchPreview(SONGS_FALLBACK_URL);
    if (!(r.ok && r.data && Array.isArray(r.data.songs))) return;
    hasNew = hasNewSong(r.data.songs);
    applyNew();
  } catch (e) { /* 배지는 부가 기능 — 실패해도 버튼은 그대로 */ }
}

export function createPlayerButton(cls = "") {
  const b = document.createElement("button");
  b.type = "button";
  b.className = ("player-btn " + cls).trim();
  const label = hasNew ? `${PLAYER_BUTTON_LABEL} (신곡 NEW)` : PLAYER_BUTTON_LABEL;
  b.setAttribute("aria-label", label);
  b.title = label;
  b.appendChild(icon());
  b.addEventListener("click", () => document.dispatchEvent(new CustomEvent(PLAYER_BUTTON_EVENT)));
  return b;
}
