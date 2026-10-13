// gungye.js — (v4.3.0) 노노카 지각 이스터에그. 파일 이름은 처음 만든 「관심법」 때문에 gungye 로 남아 있다.
// 노노카 본인 예고(announced · upcoming · watching 중 예정 시각이 지난 것)를 단계별로 꾸민다.
//  모바일 = 오늘 카드(timetable.js todayCard) / PC = 블록 예고 팝업(timetable.js showCardPop).
// 연출은 두 가지(variant) — 페이지를 연 뒤 그 예고를 처음 지각으로 본 순간 확률로 하나 정하고 그 페이지 동안 유지한다:
//   king   (90%) 국왕 — 왕관 · 레드카펫 · 「신하 대기 +MM:SS」 · 「국왕 납시오!」
//   gungye (10%) 궁예 — 금빛 후광 · 눈 · 「관심법」 · 「미륵이 강림하셨도다!」
// 단계(두 연출 공통): 1 (0~5분) · 2 (5~15분) · 3 (15분~, 대기 시간 카운트업). 라이브로 바뀐 순간에는 강림 연출을 한 번 재생한다(지각을 본 경우만).
// 데이터는 textContent/createElement 로만 주입(XSS 방어, innerHTML 금지) — timetable.js 와 같은 규칙.
//
//  lateStage(startMs, nowMs)      → 0|1|2|3  (순수)
//  pickVariant(r)                 → "king"|"gungye"  (순수, r = 0~1 난수)
//  waitLabel(ms)                  → "MM:SS"   (순수)
//  isGungyeTarget(item)           → 노노카 본인 예고인가 (순수)
//  noteLate(entries, nowMs)       → 지각 중인 노노카 예고를 기억(연출 종류 · 라이브 전환 시 강림 연출 · 재방문 문구용)
//  decorateLate(root, thumb, msgParent, item, startMs, nowMs)   → 예정 상태 카드/팝업 꾸미기 + 1초 틱 등록
//  decorateArrival(root, thumb, msgParent, item)                 → 라이브 전환 카드/팝업 꾸미기

export const GUNGYE_KEY = "nonoka";
const MIN = 60000;
export const MAX_LATE_MS = 3 * 3600000;      // 예고는 예정 시각 + 3h 안에 정리되므로 그 이상은 꾸미지 않음
export const GUNGYE_RATE = 0.1;              // 궁예 연출이 나올 확률 (나머지는 국왕)
const STORE_PREFIX = "mew:gy:";
const REVISIT_TTL_MS = 24 * 3600000;

export function lateStage(startMs, nowMs) {
  const late = nowMs - startMs;
  if (!isFinite(late) || late <= 0 || late > MAX_LATE_MS) return 0;
  return late < 5 * MIN ? 1 : late < 15 * MIN ? 2 : 3;
}

export function pickVariant(r) {
  return r < GUNGYE_RATE ? "gungye" : "king";
}

export function waitLabel(ms) {
  const s = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(s / 60), r = s % 60;
  return `${m < 10 ? "0" : ""}${m}:${r < 10 ? "0" : ""}${r}`;
}

export function isGungyeTarget(item) {
  return !!item && item.channel_key === GUNGYE_KEY;
}

/* ── 이 페이지에서 본 지각 기억 ─────────────────────────────────────── */
const seen = new Map();          // item.id → { variant, wait, revisit, played }

function storeHas(id) {
  try {
    const v = Number(localStorage.getItem(STORE_PREFIX + id));
    return isFinite(v) && v > 0 && Date.now() - v < REVISIT_TTL_MS;
  } catch (e) { return false; }
}
function storeSet(id) {
  try { localStorage.setItem(STORE_PREFIX + id, String(Date.now())); } catch (e) { /* 저장소가 막혀 있어도 동작 */ }
}

function note(id, startMs, nowMs) {
  if (!id) return null;
  let rec = seen.get(id);
  if (!rec) { rec = { variant: pickVariant(Math.random()) }; seen.set(id, rec); }
  rec.wait = nowMs - startMs;
  if (lateStage(startMs, nowMs) === 3 && !("revisit" in rec)) {
    rec.revisit = storeHas(id);          // 이전에 15분+ 단계를 본 적이 있으면 두 번째 방문
    storeSet(id);
  }
  return rec;
}

export function noteLate(entries, nowMs) {
  for (const e of entries || []) {
    if (isGungyeTarget(e.item) && lateStage(e.start, nowMs) > 0) note(e.item.id, e.start, nowMs);
  }
}

/* ── DOM ──────────────────────────────────────────────────────────── */
const SVG_NS = "http://www.w3.org/2000/svg";

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}

function buildEye() {
  const eye = el("div", "gy-eye");
  const lid = el("div", "gy-lid");
  lid.append(el("span", "gy-pupil"), el("span", "gy-shut"), el("span", "gy-shut gy-shut--b"));
  eye.appendChild(lid);
  return eye;
}

function buildCrown() {
  const wrap = el("div", "gy-crown");
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", "0 0 48 40");
  svg.setAttribute("aria-hidden", "true");
  const body = document.createElementNS(SVG_NS, "path");
  body.setAttribute("d", "M3 32 L7 9 L16 20 L24 4 L32 20 L41 9 L45 32 Z");
  const base = document.createElementNS(SVG_NS, "rect");
  base.setAttribute("x", "3"); base.setAttribute("y", "34"); base.setAttribute("width", "42"); base.setAttribute("height", "5"); base.setAttribute("rx", "1.5");
  svg.append(body, base);
  wrap.appendChild(svg);
  return wrap;
}

/* 썸네일 위에 얹는 장식 */
function buildDecor(variant) {
  return variant === "gungye" ? [el("div", "gy-halo"), buildEye()] : [buildCrown()];
}

function buildMsg(variant, stage, startMs, rec) {
  const m = el("div", "gy-msg");
  if (variant === "gungye") {
    if (stage === 1) m.appendChild(el("b", "", "짐이 곧 오리라"));
    else if (stage === 2) m.appendChild(el("b", "", "관심법 발동 중…"));
    else {
      m.appendChild(el("b", "", rec && rec.revisit ? "또 왔느냐. 그대의 불충이 보이느니라" : "관심법으로 보니 그대, 또 새로고침을 하고 있구나"));
      m.appendChild(el("small", "", "미륵 강림까지"));
    }
  } else if (stage === 1) m.appendChild(el("b", "", "국왕 입장 준비 중"));
  else if (stage === 2) m.appendChild(el("b", "", "신하들은 기다리라 — 국왕은 원래 마지막에 입장한다"));
  else {
    m.appendChild(el("small", "", "국왕 행차가 길어지고 있습니다"));
    m.appendChild(el("b", "", "신하 대기 시간"));
  }
  if (stage === 3) {
    const c = el("span", "gy-cnt", `+${waitLabel(Date.now() - startMs)}`);
    c.dataset.gyStart = String(startMs);
    m.appendChild(c);
    if (variant === "king") m.appendChild(el("span", "gy-carpet"));
  }
  return m;
}

function clear(root) {
  root.querySelectorAll(".gy-halo, .gy-eye, .gy-crown, .gy-msg, .gy-spark").forEach((n) => n.remove());
  delete root.dataset.gyStage;
}

/* 예정 상태: 단계가 바뀌면 다시 그리고, 3단계면 카운터만 갱신 */
function paint(root, nowMs) {
  const g = root.__gy;
  if (!g) return;
  const stage = lateStage(g.startMs, nowMs);
  if (String(stage || "") === (root.dataset.gyStage || "")) {
    if (stage === 3) {
      const c = root.querySelector("[data-gy-start]");
      if (c) c.textContent = `+${waitLabel(nowMs - g.startMs)}`;
    }
    return;
  }
  clear(root);
  if (!stage) return;
  const rec = note(g.id, g.startMs, nowMs);
  const variant = rec ? rec.variant : "king";
  root.dataset.gyVar = variant;
  root.dataset.gyStage = String(stage);
  g.thumb.append(...buildDecor(variant));
  g.msgParent.appendChild(buildMsg(variant, stage, g.startMs, rec));
  if (variant === "gungye") wirePointer();
}

export function decorateLate(root, thumb, msgParent, item, startMs, nowMs) {
  root.__gy = { thumb, msgParent, id: item.id, startMs };
  root.dataset.gyId = item.id || "";
  paint(root, nowMs);
  startTicker();
}

export function decorateArrival(root, thumb, msgParent, item) {
  const rec = item && seen.get(item.id);
  if (!rec) return;                       // 이 페이지에서 지각을 본 적이 없으면 아무 것도 안 함
  const gungye = rec.variant === "gungye";
  root.dataset.gyVar = rec.variant;
  const wait = `신하 대기 +${waitLabel(rec.wait || 0)}`;
  const fin = () => {
    if (!root.isConnected) return;
    clear(root);
    root.dataset.gyStage = "live";
    const m = el("div", "gy-msg");
    m.appendChild(el("small", "", `${gungye ? "미륵 강림" : "국왕 입장 완료"} · ${wait}`));
    msgParent.appendChild(m);
  };
  if (rec.played) { fin(); return; }
  rec.played = true;
  clear(root);
  root.dataset.gyStage = "arrive";
  const m = el("div", "gy-msg");
  m.append(el("b", "", gungye ? "미륵이 강림하셨도다!" : "국왕 납시오!"), el("small", "", wait));
  thumb.append(...buildDecor(rec.variant));
  msgParent.appendChild(m);
  for (let i = 0; i < 24; i++) {
    const sp = el("span", "gy-spark");
    const a = Math.random() * Math.PI * 2, d = 40 + Math.random() * 90;
    sp.style.setProperty("--dx", `${(Math.cos(a) * d).toFixed(0)}px`);
    sp.style.setProperty("--dy", `${(Math.sin(a) * d).toFixed(0)}px`);
    thumb.appendChild(sp);
  }
  setTimeout(fin, 3800);
}

/* ── 1초 틱: 카운터 · 단계 전환. 꾸밀 대상이 화면에서 사라지면 스스로 멈춘다 ─────── */
let tickTimer = 0;
function startTicker() {
  if (tickTimer) return;
  tickTimer = setInterval(() => {
    const roots = document.querySelectorAll("[data-gy-id]");
    if (!roots.length) { clearInterval(tickTimer); tickTimer = 0; return; }
    const now = Date.now();
    for (const r of roots) paint(r, now);
  }, 1000);
}

/* ── (궁예) 눈동자가 마우스를 따라간다 (터치 기기는 CSS 가 좌우로 훑는다) ────────── */
let ptrWired = false, raf = 0, px = 0, py = 0;
function wirePointer() {
  if (ptrWired) return;
  ptrWired = true;
  window.addEventListener("pointermove", (e) => {
    if (e.pointerType === "touch") return;
    px = e.clientX; py = e.clientY;
    if (raf) return;
    raf = requestAnimationFrame(() => {
      raf = 0;
      for (const eye of document.querySelectorAll(".gy-eye")) {
        const r = eye.getBoundingClientRect();
        const dx = px - (r.left + r.width / 2), dy = py - (r.top + r.height / 2);
        const d = Math.hypot(dx, dy) || 1;
        const k = Math.min(1, d / 200) * 9;
        eye.style.setProperty("--px", `${((dx / d) * k).toFixed(1)}px`);
        eye.style.setProperty("--py", `${((dy / d) * k * 0.6).toFixed(1)}px`);
      }
    });
  }, { passive: true });
}
