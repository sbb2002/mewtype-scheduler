// banners.js — 소식 란을 펼쳤을 때 맨 위에 보이는 「행사 배너」 (v4a, 2026-10-02). 디자인 = 아티팩트 「행사 배너 절충안 상세」.
// 계약: docs/SPEC.md 계약 J (banners.json). 용어: docs/TERMINOLOGY.md 「행사 배너 용어」.
//
// 카드 1장: 흐린 이미지 배경 + 절취선으로 나뉜 [행사 이미지 | 정보]. 정보 칸 순서 = 행사 제목 · 날짜 → 딸린 가챠 → 종료 일정 박스 →
// 진행 막대(말풍선 · 점선). 데이터는 전부 textContent/속성 이스케이프로만 주입한다(XSS 방어).
//
// 표시 상태는 저장값이 아니라 현재 시각으로 파생한다(백엔드 banners.derive 와 같은 규칙):
//   hold(보류) · sched(개최 전, 종료일을 몰라도 올림) · live · warn(먼저 끝나는 종료 3일(달력) 전부터, 노랑) ·
//   urgent(먼저 끝나는 종료를 넘김 — 늦은 종료만 남음, 빨강. 남은 시간은 보통 카드처럼 D-n, 당일만 시간 · 분 — v4.6.0) ·
//   done(모두 종료, 그날 자정까지 회색 「종료」) · gone/pending(안 보임)
// 행사 · 가챠 중 어느 쪽이 먼저 끝나도 같은 규칙이다(prima aurora 는 가챠가 먼저 — 점선 뒤 25일이 빨강 + 「행사 종료까지 D-n」).
// 진행 막대 = 시작 → **늦게 끝나는 종료**를 100%로, 먼저 끝나는 종료 시점에 점선(항상 막대 위, 막대 세로 폭 안), 점선~100% 는 /// 무늬.
// 말풍선 꼬리는 막대의 현재 위치. D-n 은 한국 시간 달력 날짜 차이. 이미지는 X 트윗의 행사 키비주얼 링크만 쓴다(가챠 이미지 없음).
// (v4.5.11) 가챠 단독 배너(gacha_only — 인게임 이벤트 없이 열린 한시 가챠)는 「행사」가 아니라 「가챠」로 적고, 카드 · 탭에 종류 배지(행사 / 가챠)를
// 색으로 구분해 붙인다. 가챠 단독 배너는 가챠 이미지도 쓴다(백엔드가 붙임).

const IMG_SLIDE_MS = 5000;      // 이미지가 여러 장이면 5초 머문 뒤 다음 이미지가 오른쪽으로 밀려 들어온다(한쪽 방향, 무한 반복)
const SLIDE_MS = 650;
const DAY = 86400000, HOUR = 3600000, MIN = 60000, OFF = 9 * HOUR;   // KST
const _timers = [];
const _ros = [];

function _esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function _ms(iso) {
  const t = Date.parse(iso || "");
  return isNaN(t) ? null : t;
}

const _fmtDate = new Intl.DateTimeFormat("ko-KR", { timeZone: "Asia/Seoul", month: "2-digit", day: "2-digit", weekday: "short" });
const _fmtTime = new Intl.DateTimeFormat("ko-KR", { timeZone: "Asia/Seoul", hour: "2-digit", minute: "2-digit", hour12: false });
function _parts(ms) {
  const d = _fmtDate.formatToParts(ms), t = _fmtTime.formatToParts(ms);
  const g = (arr, k) => (arr.find((p) => p.type === k) || {}).value || "";
  return { m: g(d, "month"), d: g(d, "day"), w: g(d, "weekday"), hh: g(t, "hour"), mm: g(t, "minute") };
}
const _md = (ms) => { const p = _parts(ms); return `${p.m}.${p.d}`; };
function _stamp(ms, withTime) {
  const p = _parts(ms);
  return `${p.m}.${p.d}(${p.w})` + (withTime ? ` ${p.hh}:${p.mm}` : "");
}
// (v4.5.11) 배너 종류 — 이벤트 배너 = 「행사」, 가챠 단독 배너 = 「가챠」
const _kind = (b) => (b && b.gacha_only ? "gacha" : "event");
const KIND_LABEL = { event: "행사", gacha: "가챠" };
const _dd = (target, now) => Math.floor((target + OFF) / DAY) - Math.floor((now + OFF) / DAY);   // 달력 기준 D-n(당일 = 0)

// 행사 종료 + 가챠 자체 종료(없으면 행사와 같음)를 시각 순으로. 같은 시각은 하나로 합친다.
function _endpoints(b) {
  const out = [];
  const add = (label, t) => { if (t != null && !out.some((o) => o.t === t)) out.push({ label, t }); };
  add(KIND_LABEL[_kind(b)], _ms(b.end_at));
  (b.gachas || []).forEach((g) => add("가챠", _ms(g.end_at)));
  return out.sort((a, c) => a.t - c.t);
}

// 달력 D-n, 당일은 시간(60분 안이면 분). (v4.6.0) 빨강 구간도 같은 규칙 — 전엔 항상 시간이라 점선 뒤가 길면 「588시간」이 됐다
function _remain(label, target, now) {
  const left = target - now, n = _dd(target, now);
  if (left < HOUR) return `${label} 종료까지 ${Math.max(1, Math.ceil(left / MIN))}분`;
  if (n <= 0) return `${label} 종료까지 ${Math.ceil(left / HOUR)}시간`;
  return `${label} 종료까지 D-${n}`;
}

// 현재 시각에서 카드의 모든 표시 정보를 계산한다.
export function bannerInfo(b, now) {
  const start = _ms(b.start_at), end = _ms(b.end_at);
  const hold = b.hold ? _ms(b.hold.until) : null;
  const base = { st: "gone", pct: 0, bubble: "", chip: "", eps: [], early: null, late: null, start };
  if (start == null || (end == null && !b.hold && now >= start)) return Object.assign(base, { st: "pending" });
  if (b.hold) return hold == null || now >= hold ? base : Object.assign(base, { st: "hold" });
  if (end == null) {                                           // 개최 전 · 종료일 미정 — 시작 일시를 먼저 알려준다
    const before = start - now, bd = _dd(start, now);
    const t = before < HOUR ? `개최까지 ${Math.max(1, Math.ceil(before / MIN))}분` : bd <= 0 ? `개최까지 ${Math.ceil(before / HOUR)}시간` : `개최까지 D-${bd}`;
    return Object.assign(base, { st: "sched", chip: t });
  }
  const eps = _endpoints(b), early = eps[0], late = eps[eps.length - 1];
  const mid = ((Math.floor((late.t + OFF) / DAY) + 1) * DAY) - OFF;   // 늦은 종료가 속한 날의 다음 날 00:00 KST
  const span = late.t - start;
  const pct = span > 0 ? Math.max(0, Math.min(100, ((now - start) / span) * 100)) : 100;
  const cutPct = eps.length > 1 ? ((early.t - start) / span) * 100 : null;
  const info = Object.assign(base, { pct, eps, early, late, cutPct });
  if (now >= mid) return Object.assign(info, { st: "gone" });
  if (now >= late.t) return Object.assign(info, { st: "done", pct: 100, chip: "모두 종료 · 자정까지 표시" });
  if (now < start) {
    const before = start - now, bd = _dd(start, now);
    const t = before < HOUR ? `개최까지 ${Math.max(1, Math.ceil(before / MIN))}분` : bd <= 0 ? `개최까지 ${Math.ceil(before / HOUR)}시간` : `개최까지 D-${bd}`;
    return Object.assign(info, { st: "sched", pct: 0, bubble: t });
  }
  if (eps.length > 1 && now >= early.t) return Object.assign(info, { st: "urgent", bubble: _remain(late.label, late.t, now) });
  if (_dd(early.t, now) <= 3) return Object.assign(info, { st: "warn", bubble: _remain(early.label, early.t, now) });
  return Object.assign(info, { st: "live", chip: _remain(early.label, early.t, now) });
}

// 백엔드 banners.derive 와 같은 규칙 — 상태 ∈ hold | sched | live | warn | urgent | done | gone | pending
export function bannerState(b, now) { return bannerInfo(b, now).st; }

export function visibleBanners(data, now) {
  return ((data && data.banners) || [])
    .filter((b) => b && !["gone", "pending"].includes(bannerState(b, now)))
    .sort((a, b) => (a.start_at || "").localeCompare(b.start_at || "") || String(a.id).localeCompare(String(b.id)));
}

const STATE_LABEL = { hold: "보류", sched: "예정", live: "진행 중", warn: "진행 중", urgent: "진행 중", done: "종료" };
const RANK = { urgent: 0, warn: 1, live: 2, sched: 3, done: 4, hold: 5 };   // 처음 열 탭을 고르는 순서(급한 순). 탭 줄 자체의 순서는 시작 시각순(visibleBanners)
const TAB_VISIBLE = 3;                                                      // 탭이 한 번에 보이는 개수 — 넘으면 좌우 화살표로 한 칸씩 이동
const _sel = { id: null, off: 0 };

function _titles(ko, ja, cls) {
  const main = ko || ja || "";
  const orig = ko && ja && ko !== ja ? `<div class="bnr__orig">${_esc(ja)}</div>` : "";
  return `<div class="bnr__name ${cls || ""}">${_esc(main)}</div>${orig}`;
}

function _gachaBlocks(b) {
  return (b.gachas || []).map((g) =>
    `<div class="bnr__glass"><div class="bnr__tagline"><i class="bnr__kind" data-kind="gacha">가챠</i>함께 진행</div>${_titles(g.title_ko, g.title_ja, "bnr__name--sub")}</div>`
  ).join("");
}

function _period(b, info) {
  const start = _ms(b.start_at), end = _ms(b.end_at);
  if (info.st === "hold") return `${_md(_ms(b.hold.anchor) ?? start)}(보류)`;
  const s = `${_stamp(start, !b.start_time_tbd)}`;
  if (info.st === "sched") {
    return `<b class="bnr__open">${_esc(s)} 개최</b>` + (end == null ? " · 종료일 미정" : ` · ${_esc(_stamp(end, true))} 종료`);
  }
  return end == null ? `${_esc(s)} 개최 · 종료일 미정` : `${_esc(s)} ~ ${_esc(_stamp(end, true))} 종료`;
}

// 종료 일정 박스 — 행사(가챠 단독 배너면 가챠) 종료 + (가챠마다) 가챠 종료. 가챠에 자체 종료가 없으면 행사와 같은 시각을 그대로 적는다.
function _endBoxes(b, info, now) {
  const evEnd = _ms(b.end_at);
  const k = KIND_LABEL[_kind(b)];
  const boxes = [{ label: `${k} 종료`, t: evEnd, who: k }];
  (b.gachas || []).forEach((g) => boxes.push({ label: "가챠 종료", t: _ms(g.end_at) ?? evEnd, who: "가챠" }));
  return boxes.map((x) => {
    let cls = "";
    if (x.t == null) cls = "is-tbd";
    else if (info.st === "done" || now >= x.t) cls = "is-over";
    else if (info.st === "warn" && info.early && x.t === info.early.t) cls = "is-hot";
    else if (info.st === "urgent" && info.late && x.t === info.late.t) cls = "is-hot";
    const txt = x.t == null ? "미정" : _stamp(x.t, true);
    return `<div class="bnr__end ${cls}"><small>${_esc(x.label)}</small><b>${_esc(txt)}</b></div>`;
  }).join("");
}

function _prog(info) {
  if (info.st === "hold" || info.st === "pending" || !info.eps.length) return "";
  const cut = info.cutPct != null ? `<div class="bnr__cut"></div>` : "";
  const bubble = info.bubble ? `<div class="bnr__bubble"><div class="bnr__bd">${_esc(info.bubble)}</div></div>` : "";
  return `<div class="bnr__prog${info.bubble ? " has-bubble" : ""}" style="--pct:${info.pct.toFixed(2)}%;--cut:${(info.cutPct ?? 100).toFixed(2)}%">` +
    bubble + `<div class="bnr__bar${info.cutPct != null ? " has-cut" : ""}"><i></i></div>${cut}</div>`;   // (v4.6.0) 동그란 손잡이 없앰 — 채움 끝이 현재 위치
}

function _card(b, now, active) {
  const info = bannerInfo(b, now);
  const imgs = (b.image_urls || []).filter((u) => typeof u === "string" && /^https?:\/\//.test(u));
  const left = imgs.length
    ? `<div class="bnr__left"><div class="bnr__img" data-n="${imgs.length}">` +
        imgs.map((u) => `<img src="${_esc(u)}" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer" draggable="false">`).join("") +
        `<span class="bnr__state">${_esc(STATE_LABEL[info.st] || "")}</span></div></div><div class="bnr__mid"></div>`
    : "";
  const bg = imgs.length ? `<div class="bnr__bg" data-bg="${_esc(imgs[0])}"></div>` : "";
  const chip = info.chip ? ` <span class="bnr__chip">· ${_esc(info.chip)}</span>` : "";
  const ends = info.st === "hold" ? "" : `<div class="bnr__ends">${_endBoxes(b, info, now)}</div>`;
  return (
    `<article class="bnr__card" data-st="${info.st}" data-kind="${_kind(b)}" data-id="${_esc(b.id)}"${active ? ' data-active="true"' : ""}>` + bg + left +
      `<div class="bnr__right">` +
        `<div class="bnr__eyebrow"><span class="bnr__kind" data-kind="${_kind(b)}">${KIND_LABEL[_kind(b)]}</span>${b.gacha_only ? `<span class="bnr__kindnote">이벤트 없이 열린 한정 가챠</span>` : ""}</div>` + _titles(b.name_ko, b.name_ja) +
        `<div class="bnr__dates">${_period(b, info)}${chip}</div>` +
        _gachaBlocks(b) + ends + _prog(info) +
      `</div>` +
    `</article>`
  );
}

// 탭 줄의 남은 시간 문구 — 카드 안의 말풍선 · 칩과 같은 기준(달력 D-n, 당일은 시간 · 분)
function _tabRemain(info, now) {
  if (info.st === "hold") return "개최 보류";
  if (info.st === "done") return "모두 종료";
  if (info.st === "sched") {
    const n = _dd(info.start, now);
    return n > 0 ? `D-${n} 개최` : `${Math.max(1, Math.ceil((info.start - now) / HOUR))}시간 뒤 개최`;
  }
  const e = info.st === "urgent" ? info.late : info.early, left = e.t - now, n = _dd(e.t, now);
  const who = e.label;
  if (left < HOUR) return `${who} ${Math.max(1, Math.ceil(left / MIN))}분 뒤 종료`;
  if (n <= 0) return `${who} ${Math.ceil(left / HOUR)}시간 뒤 종료`;
  return `${who} D-${n} 종료`;
}

function _tab(b, info, now, sel) {
  return `<button class="bnr__tab" role="tab" type="button" data-st="${info.st}" data-kind="${_kind(b)}" aria-selected="${sel}" tabindex="${sel ? 0 : -1}">` +
    `<span class="bnr__tabtop"><i></i>${_esc(STATE_LABEL[info.st] || "")} · ${_esc(_tabRemain(info, now))}</span>` +
    `<span class="bnr__tabname"><i class="bnr__kind" data-kind="${_kind(b)}">${KIND_LABEL[_kind(b)]}</i>${_esc(b.name_ko || b.name_ja || "")}</span></button>`;
}

// PC 는 탭 줄 + 선택한 카드 1장(나머지는 CSS 로 숨김), 모바일(≤640px)은 탭 줄을 숨기고 카드를 전부 세로로 쌓는다.
// 선택은 모듈 상태(_sel)에 둬서 폴링으로 다시 그려져도 유지한다. 처음 · 선택한 행사가 사라졌을 때는 가장 급한 행사(RANK).
export function bannerHTML(list, now) {
  const infos = list.map((b) => bannerInfo(b, now));
  let idx = list.findIndex((b) => b.id === _sel.id);
  if (idx < 0) {
    idx = 0;
    infos.forEach((i, k) => { if ((RANK[i.st] ?? 9) < (RANK[infos[idx].st] ?? 9)) idx = k; });
    _sel.off = 0;
  }
  _sel.id = list[idx].id;
  const maxOff = Math.max(0, list.length - TAB_VISIBLE);
  if (idx < _sel.off) _sel.off = idx;
  if (idx >= _sel.off + TAB_VISIBLE) _sel.off = idx - TAB_VISIBLE + 1;
  _sel.off = Math.max(0, Math.min(maxOff, _sel.off));
  const many = list.length > TAB_VISIBLE;
  const bar = list.length < 2 ? "" :
    `<div class="bnr__tabbar" role="tablist">` +
      (many ? `<button class="bnr__arrow" type="button" data-d="-1" aria-label="이전 행사 탭"${_sel.off <= 0 ? " disabled" : ""}>‹</button>` : "") +
      `<div class="bnr__tabvp"><div class="bnr__tabtrack" style="--off:${_sel.off}">${list.map((b, k) => _tab(b, infos[k], now, k === idx)).join("")}</div></div>` +
      (many ? `<button class="bnr__arrow" type="button" data-d="1" aria-label="다음 행사 탭"${_sel.off >= maxOff ? " disabled" : ""}>›</button>` : "") +
    `</div>` +
    `<div class="bnr__dots" aria-hidden="true">${list.map((_, k) => `<i${k === idx ? ' class="on"' : ""}></i>`).join("")}</div>`;
  return `<div class="bnr${bar ? " has-tabs" : ""}">` + bar + list.map((b, k) => _card(b, now, k === idx)).join("") + `</div>`;
}

// 배너가 바뀌었는지 비교하는 서명 — 상태 · 말풍선 · 칩 · 진행률(정수)이 바뀌면 다시 그린다
export function bannerSig(list, now) {
  return list.map((b) => {
    const i = bannerInfo(b, now);
    return [b.id, b.last_updated, i.st, i.bubble, i.chip, Math.round(i.pct)].join(":");
  }).join("|");
}

export function stopBannerMotion() {
  while (_timers.length) clearInterval(_timers.pop());
  while (_ros.length) _ros.pop().disconnect();
}

// 말풍선 본체는 막대 안에 머물게 밀고, 꼬리는 막대의 현재 위치에 그대로 둔다.
function _shiftBubbles(scope) {
  scope.querySelectorAll(".bnr__prog").forEach((p) => {
    const bd = p.querySelector(".bnr__bd");
    if (!bd) return;
    const pw = p.getBoundingClientRect().width, w = bd.getBoundingClientRect().width;
    const x = (parseFloat(p.style.getPropertyValue("--pct")) / 100) * pw;
    const left = Math.max(0, Math.min(pw - w, x - w / 2));
    bd.style.setProperty("--shift", `${left - x}px`);
  });
}

// 탭 · 화살표 동작 — 다시 그리지 않고 선택 표시 · 카드 노출 · 탭 줄 위치만 바꾼다(선택은 _sel 에 보존).
// 카드 높이가 바뀌므로 소식 목록이 펼침 높이를 다시 재도록 이벤트를 올린다.
// 모바일(≤640px)은 화살표 대신 탭 줄 자체를 가로 스크롤(손가락 스와이프 · 마우스 드래그)한다 — 탭을 고르면 그 탭이 보이게 스크롤.
const _mobile = () => !!(window.matchMedia && window.matchMedia("(max-width: 640px)").matches);

function _wireTabScroll(root) {
  const vp = root.querySelector(".bnr__tabvp"), bar = root.querySelector(".bnr__tabbar");
  if (!vp || !bar) return;
  const edge = () => bar.classList.toggle("at-end", vp.scrollLeft + vp.clientWidth >= vp.scrollWidth - 4);
  vp.addEventListener("scroll", edge, { passive: true });
  edge();
  let down = null, moved = false;   // 마우스 드래그 — 터치는 브라우저 기본 스크롤이 처리
  vp.addEventListener("pointerdown", (e) => {
    if (e.pointerType !== "mouse" || e.button !== 0 || !_mobile()) return;
    down = { x: e.clientX, left: vp.scrollLeft }; moved = false;
  });
  vp.addEventListener("pointermove", (e) => {
    if (!down) return;
    const dx = e.clientX - down.x;
    if (!moved && Math.abs(dx) < 5) return;
    if (!moved) { moved = true; vp.classList.add("is-drag"); vp.setPointerCapture(e.pointerId); }
    vp.scrollLeft = down.left - dx;
  });
  const end = () => { if (!down) return; down = null; vp.classList.remove("is-drag"); };
  vp.addEventListener("pointerup", end);
  vp.addEventListener("pointercancel", end);
  vp.addEventListener("click", (e) => { if (moved) { e.stopPropagation(); e.preventDefault(); moved = false; } }, true);   // 드래그 끝의 클릭은 탭 선택으로 안 친다
}

function _wireTabs(scope) {
  scope.querySelectorAll(".bnr.has-tabs").forEach((root) => {
    const tabs = Array.from(root.querySelectorAll(".bnr__tab")), cards = Array.from(root.querySelectorAll(".bnr__card"));
    const track = root.querySelector(".bnr__tabtrack"), prev = root.querySelector('.bnr__arrow[data-d="-1"]'), next = root.querySelector('.bnr__arrow[data-d="1"]');
    const vp = root.querySelector(".bnr__tabvp"), dots = Array.from(root.querySelectorAll(".bnr__dots i"));
    const maxOff = Math.max(0, tabs.length - TAB_VISIBLE);
    _wireTabScroll(root);
    const paint = (focus) => {
      const idx = Math.max(0, cards.findIndex((c) => c.dataset.id === _sel.id));
      tabs.forEach((t, k) => { t.setAttribute("aria-selected", String(k === idx)); t.tabIndex = k === idx ? 0 : -1; });
      cards.forEach((c, k) => { if (k === idx) c.setAttribute("data-active", "true"); else c.removeAttribute("data-active"); });
      dots.forEach((d, k) => d.classList.toggle("on", k === idx));
      track.style.setProperty("--off", _sel.off);
      if (_mobile()) {
        const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        vp.scrollTo({ left: tabs[idx].offsetLeft, behavior: reduce ? "auto" : "smooth" });   // track 이 position:relative 라 offsetLeft 가 track 기준
      }
      if (prev) prev.disabled = _sel.off <= 0;
      if (next) next.disabled = _sel.off >= maxOff;
      if (focus) tabs[idx].focus({ preventScroll: true });
      _shiftBubbles(root);
      root.dispatchEvent(new CustomEvent("mew:banners-resize", { bubbles: true }));
    };
    const select = (k, focus) => {
      if (k < 0 || k >= cards.length) return;
      _sel.id = cards[k].dataset.id;
      if (k < _sel.off) _sel.off = k;
      if (k >= _sel.off + TAB_VISIBLE) _sel.off = k - TAB_VISIBLE + 1;
      paint(focus);
    };
    tabs.forEach((t, k) => {
      t.addEventListener("click", () => select(k, false));
      t.addEventListener("keydown", (e) => {
        if (e.key === "ArrowRight") { e.preventDefault(); select(k + 1, true); }
        else if (e.key === "ArrowLeft") { e.preventDefault(); select(k - 1, true); }
      });
    });
    root.querySelectorAll(".bnr__arrow").forEach((a) => a.addEventListener("click", () => {
      _sel.off = Math.max(0, Math.min(maxOff, _sel.off + Number(a.dataset.d)));
      paint(false);
    }));
    const i0 = cards.findIndex((c) => c.dataset.id === _sel.id);
    if (_mobile() && i0 > 0) vp.scrollLeft = tabs[i0].offsetLeft;   // 다시 그려진 뒤에도 고른 탭이 보이게
  });
}

// 흐린 배경 이미지 지정 · 이미지 로드 실패 시 이미지 칸만 숨김 · 여러 장이면 5초 머문 뒤 다음 이미지가 오른쪽으로 밀려 들어옴
// (항상 같은 방향, 무한 반복, 호버 중엔 멈춤, 움직임 줄이기 설정이면 고정).
export function mountBannerMotion(scope) {
  stopBannerMotion();
  const reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  scope.querySelectorAll(".bnr__bg").forEach((bg) => {
    const u = bg.dataset.bg;
    if (u) bg.style.backgroundImage = `url("${encodeURI(u)}")`;
  });
  _shiftBubbles(scope);
  _wireTabs(scope);
  if (window.ResizeObserver) {
    const ro = new ResizeObserver(() => _shiftBubbles(scope));
    scope.querySelectorAll(".bnr__prog").forEach((p) => ro.observe(p));
    _ros.push(ro);
  }
  scope.querySelectorAll(".bnr__img").forEach((box) => {
    const imgs = Array.from(box.querySelectorAll("img"));
    imgs.forEach((im, i) => { im.style.transform = i === 0 ? "translateX(0)" : "translateX(-100%)"; });
    imgs.forEach((im) => im.addEventListener("error", () => {
      im.remove();
      if (!box.querySelector("img")) box.hidden = true;
    }, { once: true }));
    if (imgs.length < 2 || reduce) return;
    let cur = 0, busy = false, paused = false;
    box.addEventListener("mouseenter", () => { paused = true; });
    box.addEventListener("mouseleave", () => { paused = false; });
    _timers.push(setInterval(() => {
      const live = Array.from(box.querySelectorAll("img"));
      if (paused || busy || document.hidden || live.length < 2) return;
      const a = live[cur % live.length], b = live[(cur + 1) % live.length];
      busy = true;
      const ease = "cubic-bezier(.4,0,.2,1)";
      const out = a.animate([{ transform: "translateX(0)" }, { transform: "translateX(100%)" }], { duration: SLIDE_MS, easing: ease, fill: "forwards" });
      const inn = b.animate([{ transform: "translateX(-100%)" }, { transform: "translateX(0)" }], { duration: SLIDE_MS, easing: ease, fill: "forwards" });
      inn.onfinish = () => {
        a.style.transform = "translateX(-100%)";
        b.style.transform = "translateX(0)";
        out.cancel(); inn.cancel();
        cur += 1; busy = false;
      };
    }, IMG_SLIDE_MS));
  });
}
