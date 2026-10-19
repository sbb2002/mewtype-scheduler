// theme.js — (v4.6.0) 밝게 / 어둡게 전환 버튼. 색은 css/theme.css.
//
// 첫 테마는 index.html head 인라인 스크립트가 CSS 보다 먼저 <html data-theme> 에 넣는다(첫 화면 깜빡임 방지):
//   저장된 선택(localStorage "theme") → 없으면 기기 설정(prefers-color-scheme: light 면 밝게, 그 밖은 어둡게).
// 버튼을 누르면 반대 테마로 바꾸고 그 선택을 저장한다 — 다음 방문에도 유지. 한 번도 누르지 않았으면 기기 설정이 바뀔 때 따라간다.
// 버튼은 한 번만 만들고, 소식 막대(notices.js)가 다시 그려질 때마다 막대 마지막 칸에 같은 버튼을 옮겨 붙인다.

export const THEME_EVENT = "mew:theme";   // detail = "light" | "dark" — X 카드처럼 테마를 따로 불러오는 곳이 듣는다
const KEY = "theme";
const ANIM_MS = 350;

const SVG_NS = "http://www.w3.org/2000/svg";
let _btn = null;
let _animTimer = null;

function _saved() {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : null;
  } catch (e) {
    return null;   // 시크릿 모드 등 저장소를 못 쓰면 기기 설정만 따른다
  }
}

export function currentTheme() {
  return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}

function _syncButton() {
  if (!_btn) return;
  const dark = currentTheme() === "dark";
  _btn.setAttribute("aria-label", dark ? "밝은 화면으로 전환" : "어두운 화면으로 전환");
  _btn.setAttribute("aria-pressed", String(dark));
  _btn.title = dark ? "밝은 화면으로" : "어두운 화면으로";
}

function _apply(theme, animate) {
  if (theme === currentTheme()) return;
  const root = document.documentElement;
  if (animate) {
    root.classList.add("theme-anim");
    clearTimeout(_animTimer);
    _animTimer = setTimeout(() => root.classList.remove("theme-anim"), ANIM_MS);
  }
  root.dataset.theme = theme;
  _syncButton();
  document.dispatchEvent(new CustomEvent(THEME_EVENT, { detail: theme }));
}

function _icon(kind) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  svg.dataset.icon = kind;
  const add = (tag, attrs) => {
    const el = document.createElementNS(SVG_NS, tag);
    for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
    svg.appendChild(el);
  };
  if (kind === "dark") {
    add("path", { d: "M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z" });   // 달
  } else {
    add("circle", { cx: "12", cy: "12", r: "4" });                            // 해
    add("path", { d: "M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" });
  }
  return svg;
}

/** 소식 막대 마지막 칸에 붙일 전환 버튼 — 늘 같은 요소를 돌려준다. */
export function themeButton() {
  if (_btn) return _btn;
  _btn = document.createElement("button");
  _btn.type = "button";
  _btn.className = "ntc__theme";
  _btn.append(_icon("dark"), _icon("light"));
  _btn.addEventListener("click", () => {
    const next = currentTheme() === "dark" ? "light" : "dark";
    try { localStorage.setItem(KEY, next); } catch (e) { /* 저장 못 해도 지금 화면은 바꾼다 */ }
    _apply(next, true);
  });
  _syncButton();
  return _btn;
}

/** 직접 고른 적이 없으면 기기 설정이 바뀔 때 따라간다. main.js 가 한 번 부른다. */
export function initTheme() {
  if (!window.matchMedia) return;
  const mql = window.matchMedia("(prefers-color-scheme: light)");
  mql.addEventListener("change", (e) => {
    if (!_saved()) _apply(e.matches ? "light" : "dark", true);
  });
}
