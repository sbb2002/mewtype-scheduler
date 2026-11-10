// bgpeek.js — (bg-dome 시험) 폰 전용 「배경 보기」. 모양 · 움직임은 css/bgpeek.css.
// 지금 보는 예고 레인에서 위로 튕기면(플릭) 화면 구역이 가까운 가장자리로 걷히고 배경만 남는다. 다시 누르면 제자리로 돌아온다.
//
// 레인은 세로 스크롤 영역이라 튕김을 늘 가로채면 카드 목록을 못 내린다 → 손을 댄 순간 그 레인이 이미 맨 아래(또는 넘칠 내용이 없음)였을 때만 인정한다.
// 내용이 긴 레인은 끝까지 내린 뒤 한 번 더 위로 튕기면 걷힌다.

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
const CUE_KEY = "bgpeek-cue";
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
  if (!cue || cueSeen() || !PHONE.matches || peeking) return;
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
  if (peeking || !PHONE.matches) return;
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

function laneAtBottom(lane) {
  return lane.scrollTop + lane.clientHeight >= lane.scrollHeight - 2;
}

function onTouchStart(e) {
  touch = null;
  if (peeking || !PHONE.matches || e.touches.length !== 1) return;
  const lane = e.target.closest?.(".lane");
  if (!lane || lane.inert || !lane.classList.contains("lane--active")) return;   // 옆에 비친 레인 · 캐러셀이 아닐 때는 대상 아님
  const t = e.touches[0];
  touch = { x: t.clientX, y: t.clientY, t: e.timeStamp, lane, atBottom: laneAtBottom(lane) };
}

function onTouchEnd(e) {
  const g = touch;
  touch = null;
  if (!g || !g.atBottom || e.touches.length) return;
  const t = e.changedTouches[0];
  if (!t) return;
  const dy = g.y - t.clientY;                 // 위로 갈수록 +
  const dx = Math.abs(t.clientX - g.x);
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
  cue.innerHTML = `<div class="bgp-cue__hand"><i></i><i></i><i></i></div><span class="bgp-cue__txt">위로 밀어 배경 보기</span>`;   // 고정 문자열(데이터 아님)
  document.body.appendChild(cue);
  if (PHONE.matches && !cueSeen()) setTimeout(showCue, CUE_SHOW_MS);

  board.addEventListener("touchstart", onTouchStart, { passive: true });
  board.addEventListener("touchend", onTouchEnd, { passive: true });
  board.addEventListener("touchcancel", () => { touch = null; }, { passive: true });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") show(); });
  PHONE.addEventListener("change", () => { if (!PHONE.matches) show(); });   // PC 폭으로 바뀌면 바로 되돌린다
}
