/* (v4.11.5) 길게 눌러 주소 복사 — 오늘 카드 · 이후 예고 카드 · 타임테이블 블록 · 표의 점 공용.
   부품에는 markCopy 로 data-copy-* 와 .lc 만 붙이고, 누름 처리는 document 위임 한 곳에서 한다
   (카드가 75초마다 다시 그려지고 캐러셀이 복제본을 만들어도 리스너를 다시 달 필요가 없다).
   처음 온 사람에게는 화면에 보이는 카드 하나에 말풍선으로 한 번 알려 준다(maybeShowCopyTip). 상세 docs/SPEC.md 「길게 눌러 주소 복사」 */
import { vibrate } from "./sheetdrag.js";
import { FALLBACK_CHANNEL_ORDER } from "./config.js";

const HOLD_MS = 500;    // 여기까지 누르면 복사
const FILL_AT = 150;    // 짧은 탭에 번쩍이지 않게 이만큼 지나서 채움 시작
const MOVE_PX = 8;      // 이만큼 움직이면 스크롤 · 끌기로 보고 취소
const TOAST_MS = 1600;
const TIP_MS = 6000;    // 말풍선이 떠 있는 시간
const TIP_DELAY_MS = 900;   // 첫 그리기가 자리 잡은 뒤에 띄운다
const TIP_KEY = "mew.tip.long-copy";   // 말풍선을 본 적 있음 — 사이트 기록 초기화 전까지 다시 안 띄운다. 저장소를 못 쓰면 이 페이지를 연 동안 한 번만
const NS = "http://www.w3.org/2000/svg";
// 알림이 덮지 않게 피하는 자리 — 제목 · 시각 · 링 · 배지 · 자물쇠 · 호버 팝업
const KEEP_CLEAR = ".tcard__main,.tcard__ring,.tcard__pills,.tcard__collab,.card__body,.card__badge,.tt-blk__tx,.wk2__lock,.tt-pop";

/** 복사할 주소 고르기(순수) — 영상이 확정된 예고는 영상 주소, 아니면 채널 주소. 쓸 주소가 없으면 null */
export function copyTarget(item, channelUrl) {
  const it = item || {};
  if (it.video_id && /^https?:\/\//.test(it.url || "")) return { url: it.url, kind: "video" };
  const url = channelUrl || it.url || "";
  return /^https?:\/\//.test(url) ? { url, kind: "channel" } : null;
}

/** 말풍선을 붙일 카드 고르기(순수) — 아라레부터 멤버 순서, 같은 멤버 안에서는 지금에 가까운 순서(방송 중 → 가장 가까운 예정 → 가장 최근 종료).
 *  list = [{ key, state: "live"|"upcoming"|"ended", start }] */
export function pickTipTarget(list, order) {
  const memberAt = (k) => { const i = order.indexOf(k); return i < 0 ? order.length : i; };
  const rank = { live: 0, upcoming: 1, ended: 2 };
  const startOf = (c) => (isFinite(c.start) ? c.start : Infinity);
  return [...list].sort((a, b) =>
    memberAt(a.key) - memberAt(b.key)
    || (rank[a.state] ?? 3) - (rank[b.state] ?? 3)
    || (a.state === "ended" ? startOf(b) - startOf(a) : startOf(a) - startOf(b)))[0] || null;
}

/** 말풍선 자리(순수) — 카드 위, 자리가 없으면 아래. 좌우는 화면 안, 꼬리는 카드 가운데를 가리킨다 */
export function tipPosition(rect, w, h, vw, vh) {
  const gap = 10;
  const below = rect.top < h + gap + 8 && rect.bottom + h + gap + 8 <= vh;
  const top = below ? rect.bottom + gap : Math.max(8, rect.top - h - gap);
  const cx = rect.left + rect.width / 2;
  const left = Math.max(12, Math.min(vw - w - 12, cx - w / 2));
  return { left, top, below, tail: Math.max(14, Math.min(w - 14, cx - left)) };
}

/** 부품 하나를 길게 누르기 대상으로 표시. state · start 는 말풍선 카드 고르기에 쓴다 */
export function markCopy(node, item, channelUrl, state, start) {
  const t = copyTarget(item, channelUrl);
  if (!t) return;
  node.dataset.copyUrl = t.url;
  node.dataset.copyKind = t.kind;
  if (state) node.dataset.copyState = state;
  if (isFinite(start)) node.dataset.copyStart = String(start);
  node.classList.add("lc");
}

const calm = () => !!(window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches);

/* 복사 — clipboard API, 안 되면 숨은 입력칸 */
function legacyCopy(text) {
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.readOnly = true;
  ta.className = "lc-hidden-input";
  document.body.appendChild(ta);
  const prev = document.activeElement;
  ta.focus({ preventScroll: true });
  ta.select();
  ta.setSelectionRange(0, text.length);
  let ok = false;
  try { ok = document.execCommand("copy"); } catch (_) {}
  ta.remove();
  if (prev && prev.focus) prev.focus({ preventScroll: true });
  return ok;
}
export async function copyNow(text) {   // (v4.11.7) 트윗 시트 「URL 복사」도 쓴다
  if (navigator.clipboard && navigator.clipboard.writeText) {
    try { await navigator.clipboard.writeText(text); return true; } catch (_) {}
  }
  return legacyCopy(text);
}

/* 채움 · 링 — 카드 · 블록은 채움, 작은 점은 손가락에 가리므로 바깥 링 */
function addWash(t, x, y) {
  const r = t.getBoundingClientRect();
  if (t.classList.contains("wk2__dot")) {
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("class", "lc-ring");
    svg.setAttribute("viewBox", "0 0 44 44");
    svg.style.left = `${r.left + r.width / 2}px`;
    svg.style.top = `${r.top + r.height / 2}px`;
    // 점의 멤버 색은 점이 아니라 조각(.wk2__seg)에 있다. 합동은 첫 멤버 색
    const c = getComputedStyle(t.querySelector(".wk2__seg") || t).getPropertyValue("--lane-color").trim();
    if (c) svg.style.setProperty("--lane-color", c);
    const circle = document.createElementNS(NS, "circle");
    circle.setAttribute("cx", "22"); circle.setAttribute("cy", "22"); circle.setAttribute("r", "18");
    svg.appendChild(circle);
    document.body.appendChild(svg);
    return svg;
  }
  const w = document.createElement("span");
  w.className = "lc-wash";
  const lx = x - r.left, ly = y - r.top;
  w.style.setProperty("--x", `${lx}px`);
  w.style.setProperty("--y", `${ly}px`);
  w.style.setProperty("--r", `${Math.hypot(Math.max(lx, r.width - lx), Math.max(ly, r.height - ly)) + 2}px`);
  t.appendChild(w);
  return w;
}
function dropWash(w) {
  if (!w) return;
  w.classList.add("is-out");
  setTimeout(() => w.remove(), 200);
}

/* 스크린리더 알림 칸 */
let liveEl = null;
function announce(text) {
  if (!liveEl) {
    liveEl = document.createElement("div");
    liveEl.className = "lc-live";
    liveEl.setAttribute("role", "status");
    liveEl.setAttribute("aria-live", "polite");
    document.body.appendChild(liveEl);
  }
  liveEl.textContent = text;
}

/* 알림 — 누른 부품 위 · 아래에 두되 읽어야 할 내용은 덮지 않는 빈자리로 옮긴다 */
let toastEl = null, toastT = 0;
function placeToast(n, target, x) {
  const w = n.offsetWidth, h = n.offsetHeight, vw = innerWidth, vh = innerHeight;
  let left = Math.min(vw - w - 12, Math.max(12, x - w / 2));
  const a = target.getBoundingClientRect();
  let top;
  if (a.top >= h + 12) top = a.top - h - 8;
  else if (a.bottom + h + 20 <= vh) top = a.bottom + 8;
  else top = a.top > vh - a.bottom ? 12 : vh - h - 12;
  top = Math.max(12, Math.min(vh - h - 12, top));
  const keep = [...document.querySelectorAll(KEEP_CLEAR)]
    .map((el) => el.getBoundingClientRect())
    .filter((r) => r.width && r.height && r.bottom > 0 && r.top < vh);
  const clear = (px, py) => keep.every((r) => px + w + 3 <= r.left || px - 3 >= r.right || py + h + 3 <= r.top || py - 3 >= r.bottom);
  if (!clear(left, top)) {
    let best = null;
    for (let py = 12; py <= vh - h - 12; py += 12) {
      for (const px of [left, 12, vw - w - 12]) {
        if (!clear(px, py)) continue;
        const d = Math.abs(py - top) + Math.abs(px - left);
        if (!best || d < best.d) best = { x: px, y: py, d };
      }
    }
    if (best) { left = best.x; top = best.y; }
  }
  n.style.left = `${left}px`;
  n.style.top = `${top}px`;
}
function toast(s, kind, title, sub) {
  if (toastEl) toastEl.remove();
  clearTimeout(toastT);
  const n = document.createElement("div");
  n.className = `lc-toast is-${kind}`;
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 20 20");
  svg.setAttribute("aria-hidden", "true");
  const path = document.createElementNS(NS, "path");
  path.setAttribute("d", kind === "ok" ? "M4 10.5 8.3 15 16 5.5" : kind === "wait" ? "M10 4v8m-3.5-3.5L10 12l3.5-3.5M5 16h10" : "M5 5l10 10M15 5 5 15");
  svg.appendChild(path);
  const tx = document.createElement("div");
  tx.textContent = title;
  if (sub) {
    const small = document.createElement("small");
    small.textContent = sub;
    tx.appendChild(small);
  }
  n.append(svg, tx);
  document.body.appendChild(n);
  placeToast(n, s.target, s.x);
  toastEl = n;
  announce(sub ? `${title} ${sub}` : title);
  if (kind !== "wait") hideToast(TOAST_MS);
}
function hideToast(ms) {
  clearTimeout(toastT);
  toastT = setTimeout(() => {
    const n = toastEl;
    if (!n) return;
    toastEl = null;
    n.classList.add("is-out");
    setTimeout(() => n.remove(), 200);
  }, ms);
}

/* 첫 안내 말풍선 */
let tipDone = false, tipT = 0, tipEl = null, tipHideT = 0, tipTarget = null;
function tipSeen() {
  if (tipDone) return true;
  try { return localStorage.getItem(TIP_KEY) === "1"; } catch (_) { return false; }
}
function markTipSeen() {
  tipDone = true;
  try { localStorage.setItem(TIP_KEY, "1"); } catch (_) {}
}
function closeTip() {
  clearTimeout(tipHideT);
  const n = tipEl;
  if (!n) return;
  tipEl = null;
  tipTarget = null;
  n.classList.add("is-out");
  setTimeout(() => n.remove(), 180);
}
/* 다른 시트 · 가로로 넘친 칸에 가려지지 않고 실제로 보이는 카드만 */
function tipCandidates() {
  const out = [];
  for (const el of document.querySelectorAll("#board .tcard.lc, #board .card.lc, #board .tt-blk.lc")) {
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    const cx = r.left + r.width / 2, cy = r.top + Math.min(r.height / 2, 24);
    if (cx < 0 || cx > innerWidth || cy < 0 || cy > innerHeight) continue;
    const hit = document.elementFromPoint(cx, cy);
    if (!hit || !hit.closest || hit.closest(".lc") !== el) continue;
    const box = el.closest("[data-channel]");
    out.push({ el, key: box ? box.dataset.channel : "", state: el.dataset.copyState, start: Number(el.dataset.copyStart) });
  }
  return out;
}
/* 말풍선은 카드를 따라간다 — 첫 방문 멤버 슬라이드 힌트 · 스크롤로 카드가 움직이고, 보관함 · 배너 도착으로 보드가 다시 그려져도 어긋나지 않게.
   카드가 다시 그려져 사라지면 같은 규칙으로 다시 고르고, 화면 밖으로 나가면 닫는다 */
function followTip() {
  const n = tipEl;
  if (!n) return;
  if (!tipTarget || !tipTarget.isConnected) {
    const pick = pickTipTarget(tipCandidates(), FALLBACK_CHANNEL_ORDER);
    tipTarget = pick && pick.el;
    if (!tipTarget) { closeTip(); return; }
  }
  const r = tipTarget.getBoundingClientRect();
  if (r.bottom < 0 || r.top > innerHeight || r.right < 0 || r.left > innerWidth) { closeTip(); return; }
  const p = tipPosition(r, n.offsetWidth, n.offsetHeight, innerWidth, innerHeight);
  n.style.left = `${p.left}px`;
  n.style.top = `${p.top}px`;
  n.style.setProperty("--tail", `${p.tail}px`);
  n.classList.toggle("is-below", p.below);
  requestAnimationFrame(followTip);
}
function showTip() {
  if (tipSeen() || tipEl || press || document.hidden) return;
  const pick = pickTipTarget(tipCandidates(), FALLBACK_CHANNEL_ORDER);
  if (!pick) return;   // 지금 보이는 카드가 없으면 다음 그리기 · 스크롤 때 다시
  markTipSeen();
  window.removeEventListener("scroll", onTipScroll, true);
  const n = document.createElement("div");
  n.className = "lc-tip";
  n.textContent = "길게 누르면 주소가 복사돼요";
  document.body.appendChild(n);
  tipEl = n;
  tipTarget = pick.el;
  announce(n.textContent);
  tipHideT = setTimeout(closeTip, TIP_MS);
  followTip();
}
function onTipScroll() {
  clearTimeout(tipT);
  tipT = setTimeout(showTip, 250);
}
/** 보드를 그린 뒤 부른다 — 본 적 없으면 잠시 뒤 말풍선을 띄운다 */
export function maybeShowCopyTip() {
  if (tipSeen() || tipEl) return;
  clearTimeout(tipT);
  tipT = setTimeout(showTip, TIP_DELAY_MS);
  window.addEventListener("scroll", onTipScroll, { capture: true, passive: true });   // 첫 화면에 카드가 없으면 스크롤해 보일 때
}

function finish(s, ok) {
  if (ok) {
    const ch = s.target.dataset.copyKind === "channel";
    toast(s, "ok", ch ? "채널 주소를 복사했어요" : "영상 주소를 복사했어요", ch ? "아직 영상 주소가 없어요" : "");
  } else {
    toast(s, "fail", "주소를 복사하지 못했어요", "브라우저가 막았어요. 다시 길게 눌러 주세요");
  }
}

let press = null;      // 지금 누르는 중인 상태
let waiting = null;    // 손을 떼면 다시 복사해 볼 상태 — 터치 누름 중에는 브라우저가 클립보드 쓰기를 거부할 수 있다
let eatClick = false;  // 길게 누른 뒤 따라오는 click 1회(링크 열기 · 카드 팝업)를 막는다

async function complete(q) {
  q.done = true;
  eatClick = true;
  markTipSeen();       // 직접 해 봤으면 더 알려 줄 필요가 없다
  q.target.classList.remove("is-press", "is-fill");
  if (!calm()) {
    q.target.classList.remove("is-done");
    void q.target.offsetWidth;
    q.target.classList.add("is-done");
  }
  vibrate(14);
  if (q.wash) {
    if (q.wash.classList.contains("lc-wash")) {
      const w = q.wash;
      w.classList.add("is-flash");
      setTimeout(() => w.remove(), 360);
    } else dropWash(q.wash);
  }
  const ok = await copyNow(q.url);
  if (ok) { finish(q, true); return; }
  if (press === q) {           // 아직 누르는 중 → 손을 떼는 순간 다시 시도
    waiting = q;
    toast(q, "wait", "손을 떼면 복사돼요", "");
  } else finish(q, false);
}

function cancel() {
  if (!press) return;
  const q = press;
  press = null;
  clearTimeout(q.t1);
  clearTimeout(q.t2);
  if (q.done) {
    setTimeout(() => { eatClick = false; }, 350);
    if (waiting === q) { waiting = null; hideToast(0); }
    return;
  }
  q.target.classList.remove("is-press", "is-fill");
  dropWash(q.wash);
}

async function release(q) {
  waiting = null;
  finish(q, await copyNow(q.url));
}

let wired = false;
export function initLongCopy() {
  if (wired) return;
  wired = true;
  document.addEventListener("pointerdown", (e) => {
    closeTip();
    if (e.button !== 0 || press) return;
    const t = e.target.closest && e.target.closest("[data-copy-url]");
    if (!t) return;
    eatClick = false;
    const q = press = { id: e.pointerId, target: t, url: t.dataset.copyUrl, x: e.clientX, y: e.clientY, touch: e.pointerType !== "mouse", wash: null, done: false };
    t.classList.add("is-press");
    q.t1 = setTimeout(() => {
      if (press !== q || !t.isConnected) return;
      t.classList.add("is-fill");
      q.wash = addWash(t, q.x, q.y);
      void q.wash.getBoundingClientRect();
      q.wash.classList.add("is-run");
    }, FILL_AT);
    q.t2 = setTimeout(() => {
      if (press === q && t.isConnected) complete(q);   // 다시 그려져 사라진 부품은 복사하지 않는다
    }, HOLD_MS);
  });
  window.addEventListener("pointermove", (e) => {
    if (!press || e.pointerId !== press.id || press.done) return;
    if (Math.hypot(e.clientX - press.x, e.clientY - press.y) > MOVE_PX) cancel();
  });
  window.addEventListener("pointerup", (e) => {
    if (!press || e.pointerId !== press.id) return;
    const q = press;
    if (!q.done) { cancel(); return; }
    press = null;
    setTimeout(() => { eatClick = false; }, 350);
    if (waiting === q && !(q.touch && "ontouchend" in window)) release(q);
  });
  // iOS 는 touchend 안에서야 사용자 동작으로 인정한다 — 터치의 재시도는 여기서
  window.addEventListener("touchend", () => { if (waiting && !press) release(waiting); });
  window.addEventListener("pointercancel", cancel);
  document.addEventListener("dragstart", (e) => { if (press) { e.preventDefault(); cancel(); } });
  document.addEventListener("contextmenu", (e) => { if (press && press.touch) e.preventDefault(); });   // PC 우클릭은 그대로
  document.addEventListener("animationend", (e) => { if (e.animationName === "lc-pop") e.target.classList.remove("is-done"); });
  document.addEventListener("click", (e) => {
    if (!eatClick || !e.target.closest || !e.target.closest("[data-copy-url]")) return;
    eatClick = false;
    e.preventDefault();
    e.stopPropagation();
  }, true);
}
