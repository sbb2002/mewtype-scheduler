// birthdayui.js — (v4.10.0) 생일 스킨 화면. 생일 당일(KST 00:00~24:00)이면 화면 전체 배경을 그 멤버의 생일 장면으로 바꾸고,
// 기존 화면(소식 · 보드 · 플레이어)은 반투명 유리 패널로 그 위에 얹는다(css/birthday.css).
// 판정은 순수 로직 js/birthday.js, 장면은 멤버별 모듈(js/bdayscene-<키>.js — 생일 당일에만 불러온다).
//
// 「온전히 보기」: 🎂 버튼 하나 → 화려한 폭죽과 함께 화면 UI 를 부드럽게 숨기고 장면만 보여 준다(다시 누르기 · Esc · 빈 곳 누르기로 복귀).
// 방문할 때마다 첫 장면 준비가 끝나면 AUTO_FULL_MS 동안 먼저 온전히 보여 준다(저장하지 않음 — 새로 열 때마다 다시).
// 버튼 위치: 기본 = 오른쪽, 세로 73% 쯤(운영자가 정한 자리 — DEFAULT_POS. 멤버 줄 · 풋터 아래로는 못 내려간다). 0.5초 꾹 누르면 끌어서 옮길 수 있고, 놓으면 가까운 왼쪽/오른쪽 가장자리에 붙는다.
// 위치만 localStorage "bday-btn" 에 저장한다(생일 스킨이 뜬 날에만 쓰인다).

import { BIRTHDAYS, BIRTHDAY_SCENES_ENABLED, FALLBACK_CHANNELS } from "./config.js";
import { pickBirthdayScene, msToNextKstMidnight } from "./birthday.js";

// 장면이 완성된 멤버만 등록한다(config.js BIRTHDAY_SCENES_ENABLED 와 같이 켠다)
const SCENE_LOADERS = {
  yuno: () => import("./bdayscene-yuno.js").then((m) => m.mountYunoScene)   // 반환 = 장면 마운트 함수(host, opts) → { setStill, celebrate, finale, destroy, whenReady }
};

const AUTO_FULL_MS = 4500;
const HOLD_MS = 500;           // 이만큼(0.5초) 꾹 누르면 끌기 모드
const HOLD_CANCEL_PX = 10;     // 꾹 누르는 동안 이만큼 움직이면 취소(스크롤 · 우연한 끌림)
const EDGE = 12;               // 화면 가장자리 여백(px)
const POS_KEY = "bday-btn";
const NS = "http://www.w3.org/2000/svg";
const PAGE_UI = ["notice", "board", "player-dock", "player-frame", "foot", "pager-dots"];   // 온전히 보기에서 숨기는(inert) 화면 구역 id

let key = null;        // 지금 표시 중인 멤버 키
let host = null, ui = null, greet = null, ctrl = null, btnFull = null, hintEl = null, bodyRO = null;
let fullView = false, autoDone = false, suppressClick = false;
let autoTimer = 0, midnightTimer = 0, seq = 0;
const DEFAULT_POS = { side: "right", ratio: 0.73 };   // 기본 위치 — 운영자가 정한 자리(2026-10-31)
let pos = { ...DEFAULT_POS };   // 버튼 위치 — side: 붙은 가장자리, ratio: 세로 위치(화면 높이 대비. null 이면 맨 아래 허용 높이)
const reduceMq = window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)") : null;
const reduced = () => !!(reduceMq && reduceMq.matches);

function el(tag, attrs, text) {
  const e = document.createElement(tag);
  if (attrs) for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (text != null) e.textContent = text;
  return e;
}

function dateLabel(k) { return (BIRTHDAYS[k] || "").replace("-", "."); }
function memberName(k) { return (FALLBACK_CHANNELS[k] && FALLBACK_CHANNELS[k].name_ko) || k; }

function applyStill() { if (ctrl) ctrl.setStill(reduced()); }

function setPageInert(on) {
  for (const id of PAGE_UI) {
    const e = document.getElementById(id);
    if (e) { if (on) e.setAttribute("inert", ""); else e.removeAttribute("inert"); }
  }
}

/** 온전히 보기 켜고 끄기. fireworks = 버튼으로 전환할 때만(켤 때 화려하게, 돌아올 때 작게) */
function setFull(on, fireworks) {
  if (!ui || fullView === on) return;
  fullView = on;
  clearTimeout(autoTimer);
  const root = document.documentElement;
  if (on) root.setAttribute("data-bday-full", ""); else root.removeAttribute("data-bday-full");
  setPageInert(on);
  btnFull.setAttribute("aria-pressed", String(on));
  btnFull.setAttribute("aria-label", on ? "화면으로 돌아가기" : "배경 전체 보기");
  btnFull.title = (on ? "화면으로 돌아가기" : "배경 전체 보기") + " (0.5초 꾹 누르면 위치 이동)";
  btnFull.firstChild.textContent = on ? "✕" : "🎂";
  greet.setAttribute("aria-hidden", String(!on));
  if (fireworks && ctrl && !reduced()) { if (on) ctrl.finale(); else ctrl.celebrate(); }
}

function onDocClick(e) {
  if (fullView && ui && !ui.contains(e.target)) setFull(false);   // 온전히 보기 중 빈 곳을 누르면 복귀
}
function onKey(e) {
  if (e.key === "Escape" && fullView) setFull(false);
}

// ── 버튼 위치 · 끌기 ─────────────────────────────────────────────────────────────────────────
function loadPos() {
  try {
    const v = JSON.parse(localStorage.getItem(POS_KEY) || "null");
    if (v && (v.side === "left" || v.side === "right") && (v.ratio === null || (typeof v.ratio === "number" && v.ratio >= 0 && v.ratio <= 1))) pos = v;
  } catch (e) { /* 저장값이 없거나 깨졌으면 기본 위치 */ }
}
function savePos() {
  try { localStorage.setItem(POS_KEY, JSON.stringify(pos)); } catch (e) { /* 저장 못 해도 이번 방문엔 유지 */ }
}

/** 버튼이 있을 수 있는 영역 — 아래쪽은 멤버 줄(#pager-dots, 모바일) · 풋터 바로 위까지 */
function limits() {
  const size = ui.offsetWidth || 44;
  let bottom = window.innerHeight;
  for (const id of ["pager-dots", "foot"]) {
    const e = document.getElementById(id);
    if (e && !e.hidden && e.getClientRects().length > 0) {   // position:fixed 요소는 offsetParent 가 null 이라 getClientRects 로 보이는지 본다
      const r = e.getBoundingClientRect();
      if (r.height > 0) bottom = Math.min(bottom, r.top);
    }
  }
  return { size, minX: EDGE, maxX: window.innerWidth - size - EDGE, minY: EDGE, maxY: Math.max(EDGE, bottom - size - 10) };
}

function place(x, y, tilt) {
  ui.style.transform = "translate3d(" + Math.round(x) + "px, " + Math.round(y) + "px, 0)";
  if (tilt !== undefined) ui.style.setProperty("--tilt", tilt.toFixed(1) + "deg");
}

function restPosition() {
  if (!ui) return;
  const L = limits();
  const x = pos.side === "left" ? L.minX : L.maxX;
  const y = pos.ratio === null ? L.maxY : Math.min(L.maxY, Math.max(L.minY, pos.ratio * window.innerHeight));
  place(x, y, 0);
  ui.setAttribute("data-side", pos.side);    // 힌트 말풍선이 안쪽으로 뜨게
}

function attachDrag(btn) {
  let holdT = 0, startX = 0, startY = 0, offX = 0, offY = 0, pid = null, dragging = false, lastX = 0;
  const cancelHold = () => { clearTimeout(holdT); holdT = 0; btn.classList.remove("is-holding"); };
  const hint = (text) => { if (hintEl) { hintEl.textContent = text; hintEl.hidden = !text; } };

  btn.addEventListener("pointerdown", (e) => {
    if (e.pointerType === "mouse" && e.button !== 0) return;
    pid = e.pointerId; startX = e.clientX; startY = e.clientY; lastX = e.clientX;
    try { btn.setPointerCapture(pid); } catch (err) { /* 캡처 실패는 무시 */ }
    btn.classList.add("is-holding");               // 고리가 1초 동안 차오른다
    holdT = setTimeout(() => {
      holdT = 0; dragging = true;
      btn.classList.remove("is-holding");
      ui.classList.add("is-drag");
      const r = ui.getBoundingClientRect(); offX = startX - r.left; offY = startY - r.top;
      if (navigator.vibrate) navigator.vibrate(18);
      hint("옮길 곳에 놓으세요");
    }, HOLD_MS);
  });

  btn.addEventListener("pointermove", (e) => {
    if (e.pointerId !== pid) return;
    if (!dragging) {
      if (holdT && Math.hypot(e.clientX - startX, e.clientY - startY) > HOLD_CANCEL_PX) cancelHold();
      return;
    }
    const L = limits();
    const x = Math.min(window.innerWidth - L.size - EDGE / 2, Math.max(EDGE / 2, e.clientX - offX));
    const y = Math.min(L.maxY, Math.max(EDGE / 2, e.clientY - offY));
    const vx = e.clientX - lastX; lastX = e.clientX;
    place(x, y, Math.max(-12, Math.min(12, vx * 1.4)));    // 움직이는 방향으로 살짝 기울어진다
  });

  const end = (e) => {
    if (e.pointerId !== pid) return;
    pid = null;
    cancelHold();
    if (!dragging) return;
    dragging = false;
    suppressClick = true; setTimeout(() => { suppressClick = false; }, 0);   // 끌기를 마친 손가락 뗌은 클릭이 아니다
    const r = ui.getBoundingClientRect(), L = limits();
    pos.side = r.left + r.width / 2 < window.innerWidth / 2 ? "left" : "right";   // 가까운 가장자리에 붙는다
    pos.ratio = Math.min(L.maxY, Math.max(L.minY, r.top)) / window.innerHeight;
    ui.classList.remove("is-drag");
    ui.classList.add("is-settle");
    restPosition();                                  // 스프링으로 가장자리에 철썩
    setTimeout(() => { if (ui) ui.classList.remove("is-settle"); }, 520);
    if (navigator.vibrate) navigator.vibrate(10);
    hint("");
    savePos();
  };
  btn.addEventListener("pointerup", end);
  btn.addEventListener("pointercancel", end);
  btn.addEventListener("contextmenu", (e) => e.preventDefault());   // 모바일 길게 누름 메뉴 방지
}

function buildUi(k) {
  ui = el("div", { id: "bday-ui" });
  btnFull = el("button", { type: "button", class: "bday-btn", "aria-pressed": "false", "aria-label": "배경 전체 보기", title: "배경 전체 보기 (0.5초 꾹 누르면 위치 이동)" });
  btnFull.append(el("span", { class: "bday-btn__ico", "aria-hidden": "true" }, "🎂"));
  const ring = document.createElementNS(NS, "svg");           // 꾹 누를 때 차오르는 고리
  ring.setAttribute("class", "bday-ring");
  ring.setAttribute("viewBox", "0 0 44 44");
  ring.setAttribute("aria-hidden", "true");
  const c = document.createElementNS(NS, "circle");
  c.setAttribute("cx", "22"); c.setAttribute("cy", "22"); c.setAttribute("r", "20");
  ring.appendChild(c);
  btnFull.appendChild(ring);
  btnFull.addEventListener("click", () => { if (suppressClick) return; setFull(!fullView, true); });
  hintEl = el("span", { class: "bday-hint", role: "status", hidden: "" });
  ui.append(hintEl, btnFull);
  greet = el("div", { id: "bday-greet", "aria-hidden": "true" });
  greet.append(el("span", { class: "bday-greet__en" }, "Happy Birthday."), el("span", { class: "bday-greet__who" }, memberName(k) + " · " + dateLabel(k)));
  document.body.append(greet, ui);
  loadPos();
  restPosition();
  attachDrag(btnFull);
  window.addEventListener("resize", restPosition);
  if (window.ResizeObserver) { bodyRO = new ResizeObserver(restPosition); bodyRO.observe(document.body); }   // 풋터 · 멤버 줄이 나중에 그려져도 위치를 맞춘다
  document.addEventListener("click", onDocClick);
  document.addEventListener("keydown", onKey);
}

function setup(k) {
  const mySeq = ++seq;
  const load = SCENE_LOADERS[k];
  if (!load) return;
  key = k;
  host = el("div", { id: "bday-bg", "aria-hidden": "true" });
  document.body.prepend(host);
  document.documentElement.setAttribute("data-bday", k);
  buildUi(k);
  load().then((mount) => {
    if (mySeq !== seq || !host) return;       // 그새 정리됐으면(자정 · 끄기) 무시
    ctrl = mount(host, {});
    applyStill();
    return ctrl && ctrl.whenReady;
  }).then(() => {
    if (mySeq !== seq || !ctrl || autoDone) return;
    autoDone = true;
    if (!reduced()) {                         // 첫 장면 준비가 끝나면 화려한 폭죽과 함께 잠깐 온전히 보여 준다
      setFull(true, true);
      autoTimer = setTimeout(() => setFull(false), AUTO_FULL_MS);
    }
  }).catch((e) => {
    console.error("[birthday]", e);
    if (mySeq === seq) teardown();              // 장면이 못 뜨면 평소 화면 그대로 둔다
  });
}

function teardown() {
  seq++;
  clearTimeout(autoTimer);
  setFull(false);
  document.removeEventListener("click", onDocClick);
  document.removeEventListener("keydown", onKey);
  window.removeEventListener("resize", restPosition);
  if (bodyRO) { bodyRO.disconnect(); bodyRO = null; }
  if (ctrl) { try { ctrl.destroy(); } catch (e) { /* 정리 실패는 무시 */ } ctrl = null; }
  for (const n of [host, ui, greet]) if (n && n.parentNode) n.parentNode.removeChild(n);
  host = ui = greet = btnFull = hintEl = null;
  fullView = false;
  key = null;
  document.documentElement.removeAttribute("data-bday");
  document.documentElement.removeAttribute("data-bday-full");
  setPageInert(false);
}

/** 지금 생일 장면을 보여 줄지 다시 판정한다 — 자정을 넘기거나 잠들었다 깬 뒤에도 맞게 */
function evaluate() {
  const want = pickBirthdayScene(Date.now(), location.search, BIRTHDAYS, BIRTHDAY_SCENES_ENABLED);
  if (want !== key) {
    if (key) teardown();
    if (want) setup(want);
  }
  clearTimeout(midnightTimer);
  midnightTimer = setTimeout(evaluate, msToNextKstMidnight(Date.now()) + 1000);   // 다음 KST 자정 직후 재판정
}

export function initBirthday() {
  evaluate();
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") evaluate(); });
  if (reduceMq && reduceMq.addEventListener) reduceMq.addEventListener("change", applyStill);
}
