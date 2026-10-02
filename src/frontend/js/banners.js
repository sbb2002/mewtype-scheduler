// banners.js — 소식 란을 펼쳤을 때 맨 위에 보이는 「행사 배너」 (v4a, 2026-10-02).
// 계약: docs/SPEC.md 계약 J (banners.json). 용어: docs/TERMINOLOGY.md 「행사 배너 용어」.
//
// 행사 카드 + 가챠 카드를 그린다. 데이터는 전부 textContent/속성 이스케이프로만 주입한다(XSS 방어, innerHTML 에 원문 직접 금지).
// 표시 상태는 저장값이 아니라 현재 시각으로 파생한다 — 백엔드 banners.derive 와 같은 규칙:
//   보류(hold.until 전) · 예정(시작 전) · 진행 중 / 그 밖(종료 · 보류 만료 · 시작·종료 없음)은 숨김.
// 이미지는 링크만 쓴다(자체 복사 안 함). 로드 실패하면 그 카드의 이미지 칸만 숨긴다.

const IMG_SLIDE_MS = 4500;      // 이미지가 여러 장이면 이 주기로 한 칸씩 밀려 넘어간다(marquee 처럼 가로 이동)
const _timers = [];

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

// 백엔드 banners.derive 와 같은 규칙 — 상태 ∈ hold | announced | live | gone | pending
export function bannerState(b, now) {
  const start = _ms(b.start_at), end = _ms(b.end_at);
  if (start == null || end == null) return end != null && now >= end ? "gone" : "pending";
  if (b.hold) {
    const until = _ms(b.hold.until);
    return until == null || now >= until ? "gone" : "hold";
  }
  if (now >= end) return "gone";
  return now < start ? "announced" : "live";
}

export function visibleBanners(data, now) {
  return ((data && data.banners) || [])
    .filter((b) => b && ["hold", "announced", "live"].includes(bannerState(b, now)))
    .sort((a, b) => (a.start_at || "").localeCompare(b.start_at || "") || String(a.id).localeCompare(String(b.id)));
}

function _daysLeft(targetMs, now) {
  return Math.ceil((targetMs - now) / 86400000);
}

function _chip(b, st, now) {
  const end = _ms(b.end_at), start = _ms(b.start_at);
  if (st === "hold") return { cls: "is-hold", label: "보류", dd: "개최 보류 중" };
  if (st === "announced") {
    const n = _daysLeft(start, now);
    return { cls: "is-sched", label: "예정", dd: n <= 0 ? "오늘 개최" : `개최까지 D-${n}` };
  }
  const hrs = Math.ceil((end - now) / 3600000);
  return { cls: "is-live", label: "진행 중", dd: hrs <= 24 ? `종료까지 ${Math.max(hrs, 1)}시간` : `종료까지 D-${_daysLeft(end, now)}` };
}

function _period(b, st) {
  const start = _ms(b.start_at), end = _ms(b.end_at);
  if (st === "hold") return `${_md(_ms(b.hold.anchor) ?? start)}(보류)`;
  return `${_stamp(start, !b.start_time_tbd)} ~ ${_stamp(end, true)}`;
}

function _gachaPeriod(g, b) {
  const gs = _ms(g.start_at), ge = _ms(g.end_at);
  const es = _ms(b.start_at), ee = _ms(b.end_at);
  const sameStart = gs == null || gs === es, sameEnd = ge == null || ge === ee;
  if (sameStart && sameEnd) return "";            // 행사와 기간이 같으면 적지 않는다
  const s = gs ?? es, e = ge ?? ee;
  return `${_stamp(s, true)} ~ ${_stamp(e, true)}`;
}

function _imgs(urls) {
  const list = (urls || []).filter((u) => typeof u === "string" && /^https?:\/\//.test(u));
  if (!list.length) return "";
  const one = (u) => `<img src="${_esc(u)}" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer">`;
  const loop = list.length > 1 ? list.concat(list[0]) : list;     // 마지막에 첫 장을 한 번 더 — 끊김 없이 한 바퀴
  return `<div class="bnr__img" data-n="${list.length}"><div class="bnr__strip">${loop.map(one).join("")}</div></div>`;
}

function _titles(ko, ja) {
  const main = ko || ja || "";
  const orig = ko && ja && ko !== ja ? `<div class="bnr__orig">${_esc(ja)}</div>` : "";
  return `<div class="bnr__name">${_esc(main)}</div>${orig}`;
}

function _eventCard(b, st, now) {
  const c = _chip(b, st, now);
  let bar = "";
  if (st === "live") {
    const s = _ms(b.start_at), e = _ms(b.end_at);
    const pct = Math.max(0, Math.min(100, ((now - s) / (e - s)) * 100));
    bar = `<div class="bnr__bar"><div class="bnr__fill" style="width:${pct.toFixed(1)}%"></div></div>`;
  }
  return (
    `<article class="bnr__card ${c.cls}" data-kind="event">` +
      _imgs(b.image_urls).replace('class="bnr__img"', 'class="bnr__img" data-chip="' + _esc(c.label) + '"') +
      `<div class="bnr__body">` +
        `<div class="bnr__eyebrow">행사</div>` +
        _titles(b.name_ko, b.name_ja) +
        `<div class="bnr__period"><span class="bnr__dates">${_esc(_period(b, st))}</span>` +
          `<span class="bnr__dday">${_esc(c.dd)}</span></div>` +
        bar +
      `</div>` +
    `</article>`
  );
}

function _gachaCard(g, b, st) {
  const per = _gachaPeriod(g, b);
  return (
    `<article class="bnr__card bnr__card--gacha ${st === "hold" ? "is-hold" : ""}" data-kind="gacha">` +
      _imgs(g.image_urls) +
      `<div class="bnr__body">` +
        `<div class="bnr__eyebrow">가챠</div>` +
        _titles(g.title_ko, g.title_ja) +
        (per ? `<div class="bnr__period"><span class="bnr__dates">${_esc(per)}</span></div>` : "") +
      `</div>` +
    `</article>`
  );
}

export function bannerHTML(list, now) {
  return list.map((b) => {
    const st = bannerState(b, now);
    return `<div class="bnr" data-id="${_esc(b.id)}">` + _eventCard(b, st, now) +
      (b.gachas || []).map((g) => _gachaCard(g, b, st)).join("") + `</div>`;
  }).join("");
}

// 배너가 바뀌었는지 비교하는 서명 — 상태 · D-day 문구까지 넣어 날짜가 바뀌면 다시 그린다
export function bannerSig(list, now) {
  return list.map((b) => {
    const st = bannerState(b, now);
    return [b.id, b.last_updated, st, _chip(b, st, now).dd].join(":");
  }).join("|");
}

export function stopBannerMotion() {
  while (_timers.length) clearInterval(_timers.pop());
}

// 이미지 로드 실패 → 그 카드의 이미지 칸만 숨김. 여러 장이면 일정 주기로 가로로 한 칸씩 이동(호버 중엔 멈춤).
export function mountBannerMotion(scope) {
  stopBannerMotion();
  const reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  scope.querySelectorAll(".bnr__img").forEach((box) => {
    const strip = box.querySelector(".bnr__strip");
    const imgs = strip ? Array.from(strip.querySelectorAll("img")) : [];
    imgs.forEach((im) => im.addEventListener("error", () => {
      im.remove();
      if (!strip.querySelector("img")) box.hidden = true;
    }, { once: true }));
    const n = Number(box.dataset.n || 1);
    if (n < 2 || reduce) return;
    let i = 0, paused = false;
    const go = (animate) => {
      strip.style.transition = animate ? "" : "none";
      strip.style.transform = `translateX(${-i * 100}%)`;
    };
    box.addEventListener("mouseenter", () => { paused = true; });
    box.addEventListener("mouseleave", () => { paused = false; });
    _timers.push(setInterval(() => {
      if (paused || document.hidden) return;
      i += 1;
      go(true);
      if (i === n) setTimeout(() => { i = 0; go(false); }, 620);      // 복제한 첫 장에 닿으면 조용히 처음으로
    }, IMG_SLIDE_MS));
  });
}
