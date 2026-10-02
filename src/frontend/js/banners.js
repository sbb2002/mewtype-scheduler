// banners.js — 소식 란을 펼쳤을 때 맨 위에 보이는 「행사 배너」 (v4a, 2026-10-02). 디자인 = 아티팩트 「행사 배너 절충안 상세」.
// 계약: docs/SPEC.md 계약 J (banners.json). 용어: docs/TERMINOLOGY.md 「행사 배너 용어」.
//
// 카드 1장: 흐린 이미지 배경 + 절취선으로 나뉜 [행사 이미지 | 정보]. 정보 칸 순서 = 행사 제목 · 날짜 → 딸린 가챠 → 종료 일정 박스 →
// 진행 막대(말풍선 · 점선). 데이터는 전부 textContent/속성 이스케이프로만 주입한다(XSS 방어).
//
// 표시 상태는 저장값이 아니라 현재 시각으로 파생한다(백엔드 banners.derive 와 같은 규칙):
//   hold(보류) · sched(개최 전, 종료일을 몰라도 올림) · live · warn(먼저 끝나는 종료 3일(달력) 전부터, 노랑) ·
//   urgent(먼저 끝나는 종료를 넘김 — 늦은 종료만 남음, 빨강) · done(모두 종료, 그날 자정까지 회색 「종료」) · gone/pending(안 보임)
// 진행 막대 = 시작 → **늦게 끝나는 종료**를 100%로, 먼저 끝나는 종료 시점에 점선(항상 막대 위, 막대 세로 폭 안), 점선~100% 는 /// 무늬.
// 말풍선 꼬리는 막대의 현재 위치. D-n 은 한국 시간 달력 날짜 차이. 이미지는 X 트윗의 행사 키비주얼 링크만 쓴다(가챠 이미지 없음).

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
const _dd = (target, now) => Math.floor((target + OFF) / DAY) - Math.floor((now + OFF) / DAY);   // 달력 기준 D-n(당일 = 0)

// 행사 종료 + 가챠 자체 종료(없으면 행사와 같음)를 시각 순으로. 같은 시각은 하나로 합친다.
function _endpoints(b) {
  const out = [];
  const add = (label, t) => { if (t != null && !out.some((o) => o.t === t)) out.push({ label, t }); };
  add("이벤트", _ms(b.end_at));
  (b.gachas || []).forEach((g) => add("가챠", _ms(g.end_at)));
  return out.sort((a, c) => a.t - c.t);
}

// hoursOnly(빨강 구간): 달력 D-n 대신 항상 시간(60분 안이면 분)으로 — 「가챠 종료까지 n시간」
function _remain(label, target, now, hoursOnly) {
  const left = target - now, n = _dd(target, now);
  if (left < HOUR) return `${label} 종료까지 ${Math.max(1, Math.ceil(left / MIN))}분`;
  if (hoursOnly || n <= 0) return `${label} 종료까지 ${Math.ceil(left / HOUR)}시간`;
  return `${label} 종료까지 D-${n}`;
}

// 현재 시각에서 카드의 모든 표시 정보를 계산한다.
export function bannerInfo(b, now) {
  const start = _ms(b.start_at), end = _ms(b.end_at);
  const hold = b.hold ? _ms(b.hold.until) : null;
  const base = { st: "gone", pct: 0, bubble: "", chip: "", eps: [], early: null, late: null };
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
  if (eps.length > 1 && now >= early.t) return Object.assign(info, { st: "urgent", bubble: _remain(late.label, late.t, now, true) });
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

function _titles(ko, ja, cls) {
  const main = ko || ja || "";
  const orig = ko && ja && ko !== ja ? `<div class="bnr__orig">${_esc(ja)}</div>` : "";
  return `<div class="bnr__name ${cls || ""}">${_esc(main)}</div>${orig}`;
}

function _gachaBlocks(b) {
  return (b.gachas || []).map((g) =>
    `<div class="bnr__glass"><div class="bnr__tagline"><i>가챠</i>함께 진행</div>${_titles(g.title_ko, g.title_ja, "bnr__name--sub")}</div>`
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

// 종료 일정 박스 — 행사 종료 + (가챠마다) 가챠 종료. 가챠에 자체 종료가 없으면 행사와 같은 시각을 그대로 적는다.
function _endBoxes(b, info, now) {
  const evEnd = _ms(b.end_at);
  const boxes = [{ label: "행사 종료", t: evEnd, who: "이벤트" }];
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
    bubble + `<div class="bnr__bar${info.cutPct != null ? " has-cut" : ""}"><i></i></div>${cut}<div class="bnr__knob"></div></div>`;
}

function _card(b, now) {
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
    `<article class="bnr__card" data-st="${info.st}" data-id="${_esc(b.id)}">` + bg + left +
      `<div class="bnr__right">` +
        `<div class="bnr__eyebrow">행사</div>` + _titles(b.name_ko, b.name_ja) +
        `<div class="bnr__dates">${_period(b, info)}${chip}</div>` +
        _gachaBlocks(b) + ends + _prog(info) +
      `</div>` +
    `</article>`
  );
}

export function bannerHTML(list, now) {
  return `<div class="bnr">` + list.map((b) => _card(b, now)).join("") + `</div>`;
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
