// bgview.js — (bg-dome 시험) 배경 보는 방식 고르기: 「실내만 보기」 / 「바깥 보기」.
// 밝게/어둡게 버튼(theme.js, 소식 막대 마지막 칸)을 길게 누르면 버튼 아래에 작은 팝업이 뜬다. 짧게 누르면 지금처럼 테마만 바뀐다.
// 고른 값은 이 기기에 기억(localStorage "bgview")하고 BGVIEW_EVENT 로 알린다 — 배경(bgdomegl.js)이 듣는다.
// 팝업은 WebGL 돔 배경(기본 배경)이 떠 있을 때만 연다(?bg=classic · 시안 · WebGL 을 못 쓰는 기기는 제외). 다른 배경에서는 길게 눌러도 보통 누르기와 같다(테마 전환).
//
// 바깥 보기는 위치 권한이 있어야 쓴다(2026-11-04 운영자 결정): 고르는 순간 권한을 묻고, 거절하면 실내 보기로 되돌리며 안내한다.
// 이미 거절된 상태면 브라우저가 다시 묻지 않으므로 「브라우저 설정에서 허용」으로 안내한다. 위치를 못 받으면(신호 없음 · 시간 초과)도 실내 보기로 되돌린다.
// 다음 방문엔 저장된 값이 바깥 보기이고 권한이 이미 허용돼 있을 때만 조용히 위치를 받아 바깥 보기로 연다(그 밖은 실내 보기).

import { themeButton } from "./theme.js";
import { acquireSite, geoPermission, outdoorSite } from "./bgsite.js";
import { rawHeading, setHeadingOffset, headingOffsetDeg } from "./bggyro.js";
import { sunPosition, moonPosition } from "./bgastro.js";

export const BGVIEW_EVENT = "mew:bgview";   // detail = "indoor" | "outdoor"
const KEY = "bgview";
const HOLD_MS = 500;    // 주소 복사(longcopy.js)와 같은 길이
const MOVE_PX = 10;

const OPTIONS = [
  { value: "indoor", label: "실내만 보기", sub: "돔 안에서 둘러보기 · 흔들면 지금 방향이 정면" },
  { value: "outdoor", label: "바깥 보기", sub: "실제 방위 · 시간의 하늘과 해 · 달 (위치 권한 필요)" },
];

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
  if (bgView() !== "outdoor") return;
  if (await geoPermission() !== "granted") { setBgView("indoor"); return; }
  const { result } = await acquireSite();
  setBgView(result === "ok" ? "outdoor" : "indoor");
}

const domeReady = () => !!document.querySelector("#bgdeco .bgdm-gl");

function syncPop(value = bgView()) {
  if (!pop) return;
  for (const b of pop.querySelectorAll(".bgvw__opt")) b.setAttribute("aria-checked", String(b.dataset.value === value));
  // 방향 맞추기는 바깥 보기일 때만
  const cal = pop.querySelector(".bgvw__cal");
  cal.hidden = value !== "outdoor";
  const off = Math.round(headingOffsetDeg());
  const reset = pop.querySelector(".bgvw__reset");
  reset.hidden = !off;
  reset.querySelector(".bgvw__sub").textContent = `지금 보정 ${off > 0 ? "+" : ""}${off}°`;
}

/** 방향 맞추기: 사용자가 실제 해(없으면 달)를 겨누고 누른 순간, 계산 방위와 나침반 방위의 차이를 보정으로 기억한다 */
function calibrate() {
  const site = outdoorSite(), raw = rawHeading();
  if (!site || raw == null) { toast("나침반 값이 아직 없어요. 폰을 조금 움직인 뒤 다시 눌러 주세요.", 4000); return; }
  const now = new Date(), RAD = Math.PI / 180;
  const sun = sunPosition(now, site.lat, site.lon), moon = moonPosition(now, site.lat, site.lon);
  let target = null, name = "";
  if (sun.alt > -1 * RAD) { target = sun.az; name = "해"; }
  else if (moon.alt > 0) { target = moon.az; name = "달"; }
  if (target == null) { toast("지금은 해와 달이 모두 지평선 아래라 맞출 수 없어요.", 4500); return; }
  setHeadingOffset(target - raw);
  const off = Math.round(headingOffsetDeg());
  toast(`${name} 쪽으로 방향을 맞췄어요 (보정 ${off > 0 ? "+" : ""}${off}°). 이 기기에 기억해 둘게요.`, 4500);
}

function buildPop() {
  pop = document.createElement("div");
  pop.className = "bgvw";
  pop.setAttribute("role", "menu");
  pop.setAttribute("aria-label", "배경 보기");
  pop.hidden = true;
  const head = document.createElement("div");
  head.className = "bgvw__head";
  head.textContent = "배경 보기";
  pop.appendChild(head);
  for (const o of OPTIONS) {
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
    b.addEventListener("click", () => { close(); choose(o.value); });
    pop.appendChild(b);
  }
  // 방향 맞추기(바깥 보기 전용) — 나침반 오차 보정
  const cal = document.createElement("div");
  cal.className = "bgvw__cal";
  const mk = (cls, label, sub, fn) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = `bgvw__act ${cls}`;
    b.setAttribute("role", "menuitem");
    const t = document.createElement("span");
    t.className = "bgvw__label";
    t.textContent = label;
    const u = document.createElement("span");
    u.className = "bgvw__sub";
    u.textContent = sub;
    b.append(t, u);
    b.addEventListener("click", () => { close(); fn(); });
    cal.appendChild(b);
    return b;
  };
  mk("bgvw__fix", "방향 맞추기", "실제 해(밤엔 달)를 폰으로 겨눈 채 누르세요", calibrate);
  mk("bgvw__reset", "보정 지우기", "", () => { setHeadingOffset(0); toast("방향 보정을 지웠어요.", 3000); });
  pop.appendChild(cal);
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
  if (!pop) buildPop();
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
      if (!domeReady()) return;
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
