// bgpeek.js — (bg-dome 시험) 폰 전용 「배경 보기」. 모양 · 움직임은 css/bgpeek.css.
// 빈 공간을 길게 누른 뒤, 파란 테두리가 켜진 상태에서 손을 떼지 않고 위로 플릭한다.
// 준비 전에 움직이면 일반 스크롤로 처리한다. 카드와 조작 요소에서는 준비하지 않는다.

import { bgTheme } from "./bgdeco.js";

const canPeek = () => bgTheme() !== "classic" || document.documentElement.hasAttribute("data-bday");

const PHONE = window.matchMedia("(max-width: 767px)");
const REDUCE = window.matchMedia("(prefers-reduced-motion: reduce)");
const PAGE_UI = ["notice", "board", "pager-dots", "foot", "player-frame"];   // 걷히는 화면 구역 id (bgpeek.css 와 같은 목록)

// 튕김 판정 — 위로 이만큼 이상, 이 속도 이상, 이 시간 안에, 가로보다 충분히 세로로
const MIN_DY = 48;        // px
const MIN_V = 0.45;       // px/ms
const MAX_MS = 450;
const MAX_SLOPE = 0.7;    // |dx| / dy 이 값보다 크면 가로 넘기기로 본다
const RETURN_MS = 620;    // 돌아오는 움직임(css --bgp-in 520ms + 레인 지연 50ms)이 끝날 때까지 누름 막이를 유지

let catcher = null;
let peeking = false;
let unlockT = 0;
let touch = null;

// 첫 방문 안내(운영자 11-10) — 위로 미는 손 모양 + 「위로 밀어 배경 보기」. 이 기기에서 처음 한 번만:
// 위로 튕겨 배경을 열면 바로 사라지고, 안내가 떠 있은 지 15초가 지나도 사라지며 다시 뜨지 않는다.
const CUE_KEY = "bgpeek-hold-flick-cue";
const CUE_SHOW_MS = 1200;   // 페이지가 자리 잡은 뒤 뜬다
const CUE_LIFE_MS = 15000;
let cue = null;
let cueT = 0;

function cueSeen() {
  try { return localStorage.getItem(CUE_KEY) === "1"; } catch { return false; }   // 저장 불가 기기는 매번 보여 준다
}

function dismissCue() {
  if (!cue || cue.hidden) return;
  clearTimeout(cueT);
  try { localStorage.setItem(CUE_KEY, "1"); } catch { /* 저장 불가 */ }
  cue.classList.remove("is-on");
  setTimeout(() => { if (!cue.classList.contains("is-on")) cue.hidden = true; }, 400);
}

function showCue() {
  if (!canPeek() || !cue || cueSeen() || !PHONE.matches || peeking) return;
  cue.hidden = false;
  requestAnimationFrame(() => cue.classList.add("is-on"));
  cueT = setTimeout(dismissCue, CUE_LIFE_MS);
}

const root = document.documentElement;

function setInert(on) {
  for (const id of PAGE_UI) {
    const e = document.getElementById(id);
    if (!e) continue;
    if (on) { e.setAttribute("inert", ""); e.dataset.bgpInert = "1"; }
    else if (e.dataset.bgpInert) { e.removeAttribute("inert"); delete e.dataset.bgpInert; }
  }
}

function hide() {
  if (!canPeek() || peeking || !PHONE.matches) return;
  if (root.hasAttribute("data-bday-full")) return;   // 생일 「온전히 보기」 중이면 이미 배경만 보인다
  dismissCue();   // 한 번 해 보면 안내는 끝
  peeking = true;
  clearTimeout(unlockT);
  document.activeElement?.blur?.();
  root.classList.add("bg-peek");
  setInert(true);
  catcher.hidden = false;
  if (navigator.vibrate && !REDUCE.matches) try { navigator.vibrate(8); } catch { /* 진동 미지원 */ }
}

function show() {
  if (!peeking) return;
  if (root.dataset.bgPinch) return;   // 두 손가락 줌(bgdomegl.js) 중 · 직후의 click 은 되돌리기가 아니다
  peeking = false;
  root.classList.remove("bg-peek");
  setInert(false);
  // 돌아오는 동안에도 누름 막이를 남겨 둔다 — 움직이는 카드가 엉겁결에 눌리지 않게
  clearTimeout(unlockT);
  unlockT = setTimeout(() => { if (!peeking) catcher.hidden = true; }, REDUCE.matches ? 200 : RETURN_MS);
}

const HOLD_MS = 500, HOLD_SLOP = 10;
const CONTENT = "a, button, input, textarea, select, [role=button], [contenteditable], .card, .tcard, .lane__item, .lane__header";
function cancelTouch() {
  if (touch) {
    clearTimeout(touch.timer);
    touch.lane.classList.remove("bgp-armed");
  }
  touch = null;
}
function onTouchStart(e) {
  cancelTouch();
  if (!canPeek() || peeking || !PHONE.matches || e.touches.length !== 1 || root.hasAttribute("data-bday-full")) return;
  const lane = e.target.closest?.(".lane--active");
  if (!lane || lane.inert || e.target.closest(CONTENT)) return;
  const t = e.touches[0];
  const g = touch = { id: t.identifier, x: t.clientX, y: t.clientY, lane, scrollTop: lane.scrollTop, armed: false, moving: false };
  g.timer = setTimeout(() => {
    if (touch !== g || !lane.isConnected || Math.abs(lane.scrollTop - g.scrollTop) > 2) { cancelTouch(); return; }
    g.armed = true;
    lane.classList.add("bgp-armed");
    if (navigator.vibrate && !REDUCE.matches) try { navigator.vibrate(8); } catch {}
  }, HOLD_MS);
}
function onTouchMove(e) {
  const g = touch;
  if (!g) return;
  const t = Array.from(e.touches).find(t => t.identifier === g.id);
  if (e.touches.length !== 1 || !t || !g.lane.isConnected) { cancelTouch(); return; }
  const dx = Math.abs(t.clientX - g.x), dy = Math.abs(t.clientY - g.y);
  if (!g.armed) {
    if (Math.hypot(dx, dy) > HOLD_SLOP || Math.abs(g.lane.scrollTop - g.scrollTop) > 2) cancelTouch();
    return;
  }
  if (dx > HOLD_SLOP && dx > dy * MAX_SLOPE) { cancelTouch(); return; }
  if (e.cancelable) e.preventDefault();
  if (!g.moving && dy > 3) { g.moving = true; g.t = e.timeStamp; }
}
function onTouchEnd(e) {
  const g = touch;
  const t = g && Array.from(e.changedTouches).find(t => t.identifier === g.id);
  cancelTouch();
  if (!g?.armed || !g.moving || !t || e.touches.length) return;
  const dy = g.y - t.clientY, dx = Math.abs(t.clientX - g.x);
  const dt = Math.max(1, e.timeStamp - g.t);
  if (dy < MIN_DY || dt > MAX_MS || dx > dy * MAX_SLOPE || dy / dt < MIN_V) return;
  hide();
}

// (11-09 운영자) 예고 메인 화면(보드 · 공지 · 하단 등 기본 요소)은 두 손가락 확대 · 축소를 하지 않는다. 배경 보기의 줌은 돔 안에서만(bgdomegl.js) —
// 배경 모드에서 줌을 했어도 페이지 요소는 절대 커지지 않는다. 안드로이드는 viewport 메타(user-scalable=no), iOS 사파리는 메타를 무시해서 제스처 이벤트로 막는다.
function blockPageZoom() {
  const stop = (e) => e.preventDefault();
  document.addEventListener("gesturestart", stop, { passive: false });
  document.addEventListener("gesturechange", stop, { passive: false });
  document.addEventListener("touchmove", (e) => { if (e.touches.length > 1) e.preventDefault(); }, { passive: false });
  window.addEventListener("wheel", (e) => { if (e.ctrlKey) e.preventDefault(); }, { passive: false });   // PC 트랙패드 · ctrl+휠 확대
}

export function initBgPeek() {
  const board = document.getElementById("board");
  if (!board || catcher) return;
  blockPageZoom();
  catcher = document.createElement("button");
  catcher.type = "button";
  catcher.id = "bg-peek-catch";
  catcher.hidden = true;
  catcher.setAttribute("aria-label", "화면 되돌리기");
  // 조작 패널(UFO)이 떠 있으면 바깥 누름은 패널만 닫는다 — 예고 화면으로 되돌리지 않는다(1동작 1액션, bgdomegl.js 가 받는다)
  catcher.addEventListener("click", () => {
    if (root.hasAttribute("data-bg-panel")) { document.dispatchEvent(new Event("bgpanel-dismiss")); return; }
    show();
  });
  document.body.appendChild(catcher);

  // 첫 방문 안내 — 손 모양은 장식이라 읽기 전용 · 터치 통과(pointer-events: none). 글자 · 손 모양 모두 정적 문자열
  cue = document.createElement("div");
  cue.id = "bg-peek-cue";
  cue.hidden = true;
  cue.setAttribute("aria-hidden", "true");
  cue.innerHTML = `<div class="bgp-cue__hand"><i></i><i></i><i></i></div><span class="bgp-cue__txt">빈 곳을 꾹 누른 채 위로 밀어 배경 보기</span>`;
  document.body.appendChild(cue);
  if (PHONE.matches && !cueSeen()) setTimeout(showCue, CUE_SHOW_MS);

  const syncTheme = () => {
    cancelTouch();
    clearTimeout(cueT);
    if (canPeek()) { cueT = setTimeout(showCue, CUE_SHOW_MS); return; }
    if (cue) { cue.classList.remove("is-on"); cue.hidden = true; }
    show();
  };
  document.addEventListener("mew:bgtheme", syncTheme);
  new MutationObserver(syncTheme).observe(root, { attributes: true, attributeFilter: ["data-bday"] });

  board.addEventListener("touchstart", onTouchStart, { passive: true });
  board.addEventListener("touchmove", onTouchMove, { passive: false });
  board.addEventListener("contextmenu", e => { if (touch?.armed) e.preventDefault(); });
  window.addEventListener("blur", cancelTouch);
  document.addEventListener("visibilitychange", cancelTouch);
  board.addEventListener("touchend", onTouchEnd, { passive: true });
  board.addEventListener("touchcancel", cancelTouch, { passive: true });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") show(); });
  PHONE.addEventListener("change", () => { if (!PHONE.matches) { cancelTouch(); show(); } });   // PC 폭으로 바뀌면 바로 되돌린다
}
