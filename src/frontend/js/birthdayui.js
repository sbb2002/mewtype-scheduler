// birthdayui.js — (v4.10.0) 생일 스킨 화면. 생일 당일(KST 00:00~24:00)이면 화면 전체 배경을 그 멤버의 생일 장면으로 바꾸고,
// 기존 화면(소식 · 보드 · 플레이어)은 반투명 유리 패널로 그 위에 얹는다(css/birthday.css).
// 판정은 순수 로직 js/birthday.js, 장면은 멤버별 모듈(js/bdayscene-<키>.js — 생일 당일에만 불러온다).
//
// 「온전히 보기」: 우하단 🎂 버튼 → 화면 UI 를 부드럽게 숨기고 장면만 보여 준다(다시 누르기 · Esc · 빈 곳 누르기로 복귀).
// 방문할 때마다 첫 장면 준비가 끝나면 AUTO_FULL_MS 동안 먼저 온전히 보여 준다(저장하지 않음 — 새로 열 때마다 다시).

import { BIRTHDAYS, BIRTHDAY_SCENES_ENABLED, FALLBACK_CHANNELS } from "./config.js";
import { pickBirthdayScene, msToNextKstMidnight } from "./birthday.js";

// 장면이 완성된 멤버만 등록한다(config.js BIRTHDAY_SCENES_ENABLED 와 같이 켠다)
const SCENE_LOADERS = {
  yuno: () => import("./bdayscene-yuno.js").then((m) => m.mountYunoScene)   // 반환 = 장면 마운트 함수(host, opts) → { setStill, celebrate, destroy, whenReady }
};

const AUTO_FULL_MS = 4500;
const PAGE_UI = ["notice", "board", "player-dock", "player-frame", "foot", "pager-dots"];   // 온전히 보기에서 숨기는(inert) 화면 구역 id

let key = null;        // 지금 표시 중인 멤버 키
let host = null, ui = null, greet = null, ctrl = null;
let btnFull = null, btnStill = null;
let fullView = false, manualStill = false, userOff = false, autoDone = false;
let autoTimer = 0, midnightTimer = 0, seq = 0;
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

function applyStill() { if (ctrl) ctrl.setStill(manualStill || reduced()); }

function setPageInert(on) {
  for (const id of PAGE_UI) {
    const e = document.getElementById(id);
    if (e) { if (on) e.setAttribute("inert", ""); else e.removeAttribute("inert"); }
  }
}

function setFull(on) {
  if (!ui || fullView === on) return;
  fullView = on;
  clearTimeout(autoTimer);
  const root = document.documentElement;
  if (on) root.setAttribute("data-bday-full", ""); else root.removeAttribute("data-bday-full");
  setPageInert(on);
  btnFull.setAttribute("aria-pressed", String(on));
  btnFull.setAttribute("aria-label", on ? "화면으로 돌아가기" : "배경 전체 보기");
  btnFull.textContent = on ? "✕" : "🎂";
  greet.setAttribute("aria-hidden", String(!on));
}

function onDocClick(e) {
  if (fullView && ui && !ui.contains(e.target)) setFull(false);   // 온전히 보기 중 빈 곳을 누르면 복귀
}
function onKey(e) {
  if (e.key === "Escape" && fullView) setFull(false);
}

function buildUi(k) {
  ui = el("div", { id: "bday-ui", role: "group", "aria-label": "생일 배경 컨트롤" });
  btnFull = el("button", { type: "button", class: "bday-btn bday-btn--main", "aria-pressed": "false", "aria-label": "배경 전체 보기" }, "🎂");
  btnFull.addEventListener("click", () => setFull(!fullView));
  const btnBurst = el("button", { type: "button", class: "bday-btn", "aria-label": "폭죽" }, "✨");
  btnBurst.addEventListener("click", () => { if (ctrl && !manualStill && !reduced()) ctrl.celebrate(); });
  btnStill = el("button", { type: "button", class: "bday-btn", "aria-pressed": "false", "aria-label": "움직임 멈춤" }, "⏸");
  btnStill.addEventListener("click", () => {
    manualStill = !manualStill;
    btnStill.setAttribute("aria-pressed", String(manualStill));
    btnStill.textContent = manualStill ? "▶" : "⏸";
    btnStill.setAttribute("aria-label", manualStill ? "움직임 재생" : "움직임 멈춤");
    applyStill();
  });
  const btnOff = el("button", { type: "button", class: "bday-btn", "aria-label": "생일 배경 끄기" }, "⛔");
  btnOff.addEventListener("click", () => { userOff = true; teardown(); });   // 이번 방문 동안만 끈다(저장 안 함)
  ui.append(btnFull, btnBurst, btnStill, btnOff);
  greet = el("div", { id: "bday-greet", "aria-hidden": "true" });
  greet.append(el("span", { class: "bday-greet__en" }, "Happy Birthday."), el("span", { class: "bday-greet__who" }, memberName(k) + " · " + dateLabel(k)));
  document.body.append(greet, ui);
  document.addEventListener("click", onDocClick);
  document.addEventListener("keydown", onKey);
  btnStill.setAttribute("aria-pressed", String(manualStill));
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
    if (mySeq !== seq || !host) { return; }   // 그새 정리됐으면(자정 · 끄기) 무시
    ctrl = mount(host, {});
    applyStill();
    return ctrl && ctrl.whenReady;
  }).then(() => {
    if (mySeq !== seq || !ctrl || autoDone) return;
    autoDone = true;
    if (!reduced()) {                         // 첫 장면 준비가 끝나면 잠깐 온전히 보여 준다
      setFull(true);
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
  if (ctrl) { try { ctrl.destroy(); } catch (e) { /* 정리 실패는 무시 */ } ctrl = null; }
  for (const n of [host, ui, greet]) if (n && n.parentNode) n.parentNode.removeChild(n);
  host = ui = greet = btnFull = btnStill = null;
  fullView = false;
  key = null;
  document.documentElement.removeAttribute("data-bday");
  document.documentElement.removeAttribute("data-bday-full");
  setPageInert(false);
}

/** 지금 생일 장면을 보여 줄지 다시 판정한다 — 자정을 넘기거나 잠들었다 깬 뒤에도 맞게 */
function evaluate() {
  const want = userOff ? null : pickBirthdayScene(Date.now(), location.search, BIRTHDAYS, BIRTHDAY_SCENES_ENABLED);
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
