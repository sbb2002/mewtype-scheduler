// bgview.js — (bg-dome 시험) 배경 고르기.
// ① 밝게/어둡게 버튼(theme.js, 소식 막대 마지막 칸)을 길게 누르면 「배경 테마」 팝업(기본 · UFO · 생일) — 11-06 운영자. 짧게 누르면 지금처럼 밝기만 바뀐다.
// ② UFO 테마 안의 실내(버츄얼 스페이스 · 초행성X) · 바깥(지구) 고르기는 UFO 조작 패널(bgpanel.js)이 아래 setIndoorBg · chooseBgView 를 부른다.
// 고른 값은 이 기기에 기억(localStorage "bgview")하고 BGVIEW_EVENT 로 알린다 — 배경(bgdomegl.js)이 듣는다.
//
// 바깥 보기는 위치 권한이 있어야 쓴다(2026-11-04 운영자 결정): 고르는 순간 권한을 묻고, 거절하면 실내 보기로 되돌리며 안내한다.
// 이미 거절된 상태면 브라우저가 다시 묻지 않으므로 「브라우저 설정에서 허용」으로 안내한다. 위치를 못 받으면(신호 없음 · 시간 초과)도 실내 보기로 되돌린다.
// 다음 방문엔 저장된 값이 바깥 보기이고 권한이 이미 허용돼 있을 때만 조용히 위치를 받아 바깥 보기로 연다(그 밖은 실내 보기).
//
// 방위 보정은 두 보기 공통(2026-11-05 운영자) — 시선이 둘 다 실제 방위라서(bgdomegl.js updateView).
// 진북 보정(편각)은 위치가 있어야 계산되므로, 실내 보기라도 위치 권한이 이미 허용돼 있으면 조용히 위치를 받아 둔다(새로 묻지 않는다).
// 수동 「방향 맞추기」는 없앴다(2026-11-05 운영자 「방송 확인 앱이지 별자리 앱이 아니다 — 기능만 복잡해진다」).
// 남은 오차는 폰의 나침반 자체 보정(8자 그리기)에 맡기고, 팝업에 안내 한 줄만 둔다.

import { themeButton } from "./theme.js";
import { acquireSite, geoPermission } from "./bgsite.js";
import { declinationDeg } from "./bggyro.js";
import { bgTheme, setBgTheme } from "./bgdeco.js";
import { birthdayToday, birthdayOn, setBirthdayOn } from "./birthdayui.js";

export const BGVIEW_EVENT = "mew:bgview";   // detail = "indoor" | "outdoor"
const KEY = "bgview";
// (11-06 운영자) 실내 배경 = 버츄얼 스페이스(분홍 구름, "pink") · 초행성X(우주, "space"). UFO 조작 패널에서 고르고 이 기기에 기억한다.
// 처음(기억 없음)은 분홍 — 옛 「방문마다 20% 우주」는 없앴다.
export const BGINDOOR_EVENT = "mew:bgindoor";   // detail = "pink" | "space"
const INDOOR_KEY = "bgindoor";

export function indoorBg() {
  try { return localStorage.getItem(INDOOR_KEY) === "space" ? "space" : "pink"; } catch { return "pink"; }
}
export function setIndoorBg(v) {
  const value = v === "space" ? "space" : "pink";
  try { localStorage.setItem(INDOOR_KEY, value); } catch { /* 저장 못 함 */ }
  document.dispatchEvent(new CustomEvent(BGINDOOR_EVENT, { detail: value }));
}
const HOLD_MS = 500;    // 주소 복사(longcopy.js)와 같은 길이
const MOVE_PX = 10;

// (11-06 운영자) 길게 누르기 팝업 = 「배경 테마」 고르기. 실내 · 바깥(버츄얼 스페이스 · 초행성X · 지구)은 UFO 조작 패널(bgpanel.js)로 옮겼다.
// 생일 칸은 생일 이스터에그가 켜지는 날에만. 시작 우선순위 = 생일 > 기억한 테마 > UFO.
function themeOptions() {
  const b = birthdayToday();
  return [
    { value: "classic", label: "기본", sub: "분홍 · 파랑 바탕에 떠다니는 도형" },
    { value: "dome", label: "UFO", sub: "돔 안에서 둘러보기 · 가운데 조종대로 하늘 고르기" },
    ...(b ? [{ value: "birthday", label: "생일", sub: b.label }] : []),
  ];
}
const currentTheme = () => (birthdayOn() ? "birthday" : bgTheme());

function chooseTheme(value) {
  if (value === currentTheme()) return;
  wipeDown(() => {
    if (value === "birthday") { setBirthdayOn(true); return; }
    if (birthdayOn()) setBirthdayOn(false);
    setBgTheme(value);
  });
}

// (11-06 운영자 「촥 바뀌지 말고 위에서부터 서서히」) 테마를 바꿀 때 옛 화면을 한 장으로 찍어 두고(View Transitions),
// 그 사진이 위에서부터 아래로 부드럽게 걷히며 새 테마가 드러난다. 모양은 bgdeco.css 의 html.bg-wipe.
// 지원하지 않는 브라우저 · 움직임 줄이기 설정이면 예전처럼 바로 바뀐다.
function wipeDown(change) {
  const root = document.documentElement;
  const reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (!document.startViewTransition || reduce) { change(); return; }
  root.classList.add("bg-wipe");
  const vt = document.startViewTransition(change);
  const done = () => root.classList.remove("bg-wipe");
  vt.finished.then(done, done);
}

let pop = null, press = null, eatClick = false, toastEl = null, toastT = 0, busy = false;

export function bgView() {
  try { return localStorage.getItem(KEY) === "outdoor" ? "outdoor" : "indoor"; } catch { return "indoor"; }
}

/** 보는 방식을 바꾸고 알린다. 저장을 못 하는 환경(시크릿 모드 등)이어도 지금 화면은 바꾼다. */
export function setBgView(v) {
  const value = v === "outdoor" ? "outdoor" : "indoor";
  try { localStorage.setItem(KEY, value); } catch { /* 저장 못 함 */ }
  syncPop(value);
  document.dispatchEvent(new CustomEvent(BGVIEW_EVENT, { detail: value }));
}

/** 짧은 안내(화면 아래 가운데, 몇 초 뒤 사라짐) */
function toast(text, ms = 4200) {
  if (!toastEl) {
    toastEl = document.createElement("div");
    toastEl.className = "bgvw-toast";
    toastEl.setAttribute("role", "status");
    document.body.appendChild(toastEl);
  }
  toastEl.textContent = text;
  toastEl.classList.add("is-on");
  clearTimeout(toastT);
  if (ms) toastT = setTimeout(() => toastEl.classList.remove("is-on"), ms);
}

/** iOS 는 방향 센서 권한을 「누른 그 순간」 안에서만 물을 수 있다 → 바깥 보기를 누른 click 안에서 바로 부른다 */
function askOrientation() {
  const DOE = window.DeviceOrientationEvent;
  if (DOE && typeof DOE.requestPermission === "function") return DOE.requestPermission().catch(() => "denied");
  return Promise.resolve("granted");
}

/** 바깥(지구) · 실내 고르기 — UFO 조작 패널도 이걸 부른다. 바깥은 위치 권한을 묻고, 거절 · 실패면 실내(지금 실내 배경 그대로)에 남는다 */
export function chooseBgView(value) { return choose(value); }

async function choose(value) {
  if (value !== "outdoor") { setBgView("indoor"); return; }
  if (busy) return;
  busy = true;
  const ori = askOrientation();
  toast("위치를 확인하는 중…", 0);
  const { result, before } = await acquireSite();
  await ori;   // 방향 센서를 거절해도 위치가 있으면 바깥 하늘은 그린다(방향만 고정)
  busy = false;
  if (result === "ok") {
    setBgView("outdoor");
    toast("바깥 보기 — 폰을 세워 하늘을 비추면 실제 자리에 해 · 달이 보여요. 레인을 위로 튕겨 걷으면 가리는 것 없이 볼 수 있어요.", 6500);
    return;
  }
  setBgView("indoor");
  if (result === "denied") {
    toast(before === "denied"
      ? "바깥 보기는 위치 권한이 있어야 쓸 수 있어요. 브라우저 설정의 사이트 권한에서 위치를 허용해 주세요."
      : "바깥 보기는 위치 권한을 허용해야 쓸 수 있어요. 실내 보기로 돌아갑니다.", 6000);
  } else if (result === "unsupported") {
    toast("이 브라우저는 위치를 알려 주지 않아 바깥 보기를 쓸 수 없어요.", 5000);
  } else {
    toast("위치를 가져오지 못했어요. 잠시 뒤 다시 골라 주세요. 실내 보기로 돌아갑니다.", 5000);
  }
}

/** 지난번에 바깥 보기였고 권한이 그대로면 조용히 다시 연다 */
async function restore() {
  const granted = await geoPermission() === "granted";
  if (bgView() !== "outdoor") {
    // 실내 보기 — 이미 허용된 위치만 조용히 받아 방위 보정(편각 · 수동 보정)에 쓴다. 못 받아도 그대로 실내 보기
    if (granted) { await acquireSite(); syncPop(); }
    return;
  }
  if (!granted) { setBgView("indoor"); return; }
  const { result } = await acquireSite();
  setBgView(result === "ok" ? "outdoor" : "indoor");
}

function syncPop() {
  if (!pop) return;
  const cur = currentTheme();
  for (const b of pop.querySelectorAll(".bgvw__opt")) b.setAttribute("aria-checked", String(b.dataset.value === cur));
  // 방향 안내(UFO 테마일 때만) — 진북 보정(편각)은 자동이라 얼마나 더하고 있는지만 덧붙인다
  const note = pop.querySelector(".bgvw__note");
  note.hidden = cur !== "dome";
  const dec = declinationDeg();
  note.textContent = "방향이 어긋나면 폰으로 공중에 8자를 몇 번 그려 주세요."
    + (dec == null ? "" : ` 진북 보정 ${dec > 0 ? "+" : ""}${dec.toFixed(1)}° 는 자동이에요.`);
}

/** 팝업을 만든다 — 생일 칸이 날마다 달라지므로 열 때마다 새로 */
function buildPop() {
  pop?.remove();
  pop = document.createElement("div");
  pop.className = "bgvw";
  pop.setAttribute("role", "menu");
  pop.setAttribute("aria-label", "배경 테마");
  pop.hidden = true;
  const head = document.createElement("div");
  head.className = "bgvw__head";
  head.textContent = "배경 테마";
  pop.appendChild(head);
  for (const o of themeOptions()) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "bgvw__opt";
    b.dataset.value = o.value;
    b.setAttribute("role", "menuitemradio");
    const t = document.createElement("span");
    t.className = "bgvw__label";
    t.textContent = o.label;
    const s = document.createElement("span");
    s.className = "bgvw__sub";
    s.textContent = o.sub;
    b.append(t, s);
    b.addEventListener("click", () => { close(); chooseTheme(o.value); });
    pop.appendChild(b);
  }
  const note = document.createElement("p");
  note.className = "bgvw__note";
  pop.appendChild(note);
  document.body.appendChild(pop);
}

function place() {
  const r = themeButton().getBoundingClientRect();
  const w = pop.offsetWidth, h = pop.offsetHeight, m = 8;
  let left = r.right - w;
  left = Math.max(m, Math.min(window.innerWidth - w - m, left));
  let top = r.bottom + 6;
  if (top + h > window.innerHeight - m) top = Math.max(m, r.top - h - 6);   // 아래 자리가 모자라면 위로
  pop.style.left = `${Math.round(left)}px`;
  pop.style.top = `${Math.round(top)}px`;
}

function open() {
  buildPop();
  syncPop();
  pop.hidden = false;
  place();
  requestAnimationFrame(() => pop.classList.add("is-open"));
  if (navigator.vibrate) try { navigator.vibrate(8); } catch { /* 진동 미지원 */ }
}

function close() {
  if (!pop || pop.hidden) return;
  pop.classList.remove("is-open");
  pop.hidden = true;
}

function cancelPress() {
  if (!press) return;
  clearTimeout(press.t);
  press = null;
}

export function initBgView() {
  const btn = themeButton();   // 늘 같은 요소 — 소식 막대가 다시 그려져도 리스너가 유지된다
  btn.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    cancelPress();
    eatClick = false;
    const q = press = { id: e.pointerId, x: e.clientX, y: e.clientY };
    q.t = setTimeout(() => {
      if (press !== q) return;
      press = null;
      eatClick = true;   // 손을 뗄 때 오는 click 은 테마 전환으로 치지 않는다
      open();
    }, HOLD_MS);
  });
  window.addEventListener("pointermove", (e) => {
    if (press && e.pointerId === press.id && Math.hypot(e.clientX - press.x, e.clientY - press.y) > MOVE_PX) cancelPress();
  });
  window.addEventListener("pointerup", cancelPress);
  window.addEventListener("pointercancel", cancelPress);
  // 대상 요소에서는 capture 리스너가 먼저 돈다 → theme.js 의 click(테마 전환)보다 앞에서 막는다
  btn.addEventListener("click", (e) => {
    if (!eatClick) return;
    eatClick = false;
    e.preventDefault();
    e.stopImmediatePropagation();
  }, true);
  btn.addEventListener("contextmenu", (e) => e.preventDefault());   // 폰에서 길게 누를 때 뜨는 메뉴 막기
  document.addEventListener("pointerdown", (e) => {
    if (pop && !pop.hidden && !pop.contains(e.target) && !btn.contains(e.target)) close();
  }, true);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });
  window.addEventListener("resize", close);
  restore();
  window.addEventListener("scroll", close, { passive: true, capture: true });
}
