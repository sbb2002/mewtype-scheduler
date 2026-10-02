// banners.js — 소식 란을 펼쳤을 때 맨 위에 보이는 「행사 배너」 (v4a, 2026-10-02).
// 계약: docs/SPEC.md 계약 J (banners.json). 용어: docs/TERMINOLOGY.md 「행사 배너 용어」.
//
// 행사 카드 1장 안에 딸린 가챠를 하위 블록으로 보인다. 데이터는 전부 textContent/속성 이스케이프로만 주입한다(XSS 방어).
// 표시 상태는 저장값이 아니라 현재 시각으로 파생한다 — 백엔드 banners.derive 와 같은 규칙:
//   보류(hold.until 전) · 예정(시작 전) · 진행 중 / 그 밖(종료 · 보류 만료 · 시작·종료 없음)은 숨김.
// 이미지는 X 트윗에서 걸린 행사 키비주얼(링크만, 자체 복사 안 함)만 쓴다. 가챠 이미지는 쓰지 않는다. 로드 실패하면 이미지 칸만 숨긴다.
// 종료 D-3(남은 시간 3일 이하)부터 진행 막대 · 칩을 빨간색으로 칠한다(.is-urgent).

const IMG_SLIDE_MS = 5000;      // 이미지가 여러 장이면 5초 머문 뒤 다음 이미지가 오른쪽으로 밀려 들어온다(한쪽 방향, 무한 반복)
const SLIDE_MS = 650;
const URGENT_MS = 3 * 86400000;
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
const _hm = (ms) => { const p = _parts(ms); return `${p.hh}:${p.mm}`; };
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

const _isUrgent = (b, st, now) => st === "live" && _ms(b.end_at) - now <= URGENT_MS;

function _chip(b, st, now) {
  const end = _ms(b.end_at), start = _ms(b.start_at);
  if (st === "hold") return { cls: "is-hold", label: "보류", dd: "개최 보류 중" };
  if (st === "announced") {
    const n = Math.ceil((start - now) / 86400000);
    return { cls: "is-sched", label: "예정", dd: n <= 0 ? "오늘 개최" : `개최까지 D-${n}` };
  }
  const hrs = Math.ceil((end - now) / 3600000);
  const dd = hrs <= 24 ? `종료까지 ${Math.max(hrs, 1)}시간` : `종료까지 D-${Math.ceil((end - now) / 86400000)}`;
  return { cls: _isUrgent(b, st, now) ? "is-urgent" : "is-live", label: "진행 중", dd };
}

function _period(b, st) {
  const start = _ms(b.start_at), end = _ms(b.end_at);
  if (st === "hold") return `${_md(_ms(b.hold.anchor) ?? start)}(보류)`;
  return `${_stamp(start, !b.start_time_tbd)} ~ ${_stamp(end, true)} 종료`;   // 행사 종료 시각을 말로 못박는다(가챠 종료는 아래 하위 블록에 따로)
}

// 가챠는 행사 안에 포함된 하위 블록 — 행사와 같은 부분은 적지 않고 **다른 부분만** 적는다.
// 같은 날이면 시각만("종료 11:59"), 날짜가 다르면 날짜까지("종료 10.09(금) 11:59"). 전부 같으면 아무것도 안 적는다.
function _gachaNote(g, b) {
  const gs = _ms(g.start_at), ge = _ms(g.end_at), es = _ms(b.start_at), ee = _ms(b.end_at);
  const fmt = (ms, ref) => (_md(ms) === _md(ref) ? _hm(ms) : _stamp(ms, true));
  const out = [];
  if (gs != null && gs !== es) out.push(`시작 ${fmt(gs, es)}`);
  if (ge != null && ge !== ee) out.push(`종료 ${fmt(ge, ee)}`);
  return out.join(" · ");
}

function _imgs(urls, label) {
  const list = (urls || []).filter((u) => typeof u === "string" && /^https?:\/\//.test(u));
  if (!list.length) return "";
  const one = (u) => `<img src="${_esc(u)}" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer" draggable="false">`;
  return `<div class="bnr__img" data-n="${list.length}" data-chip="${_esc(label)}">${list.map(one).join("")}</div>`;
}

function _titles(ko, ja) {
  const main = ko || ja || "";
  const orig = ko && ja && ko !== ja ? `<div class="bnr__orig">${_esc(ja)}</div>` : "";
  return `<div class="bnr__name">${_esc(main)}</div>${orig}`;
}

function _gachaBlock(b, st) {
  return (b.gachas || []).map((g) => {
    const note = st === "hold" ? "" : _gachaNote(g, b);
    return (
      `<div class="bnr__sub">` +
        `<span class="bnr__subtag"><i>가챠</i>함께 진행</span>` +
        _titles(g.title_ko, g.title_ja).replace("bnr__name", "bnr__name bnr__name--sub") +
        (note ? `<div class="bnr__gnote">${_esc(note)}</div>` : "") +
      `</div>`
    );
  }).join("");
}

function _card(b, st, now) {
  const c = _chip(b, st, now);
  let bar = "";
  if (st === "live") {
    const s = _ms(b.start_at), e = _ms(b.end_at);
    const pct = Math.max(0, Math.min(100, ((now - s) / (e - s)) * 100));
    bar = `<div class="bnr__bar"><div class="bnr__fill" style="width:${pct.toFixed(1)}%"></div></div>`;
  }
  return (
    `<article class="bnr__card ${c.cls}" data-id="${_esc(b.id)}">` +
      _imgs(b.image_urls, c.label) +
      `<div class="bnr__body">` +
        `<div class="bnr__eyebrow">행사</div>` +
        _titles(b.name_ko, b.name_ja) +
        `<div class="bnr__period"><span class="bnr__dates">${_esc(_period(b, st))}</span>` +
          `<span class="bnr__dday">${_esc(c.dd)}</span></div>` +
        bar +
        _gachaBlock(b, st) +
      `</div>` +
    `</article>`
  );
}

export function bannerHTML(list, now) {
  return `<div class="bnr">` + list.map((b) => _card(b, bannerState(b, now), now)).join("") + `</div>`;
}

// 배너가 바뀌었는지 비교하는 서명 — 상태 · D-day 문구까지 넣어 날짜가 바뀌면(D-3 빨강 포함) 다시 그린다
export function bannerSig(list, now) {
  return list.map((b) => {
    const st = bannerState(b, now);
    const c = _chip(b, st, now);
    return [b.id, b.last_updated, st, c.dd, c.cls].join(":");
  }).join("|");
}

export function stopBannerMotion() {
  while (_timers.length) clearInterval(_timers.pop());
  while (_ros.length) _ros.pop().disconnect();
}

// PC(폭 641px 이상): 이미지 칸을 오른쪽 텍스트 영역 높이까지 키운다. 16:9 비율은 그대로(잘리지 않음), 세로 중앙 정렬은 CSS(align-self:center).
// 가로가 카드의 절반을 넘으면 거기서 멈추고(높이는 비율대로 줄어 중앙에 놓인다). 모바일은 CSS 가 위쪽 꽉 찬 이미지로 처리하므로 인라인 크기를 지운다.
function _layoutImages(scope) {
  const mobile = window.matchMedia && window.matchMedia("(max-width: 640px)").matches;
  scope.querySelectorAll(".bnr__card").forEach((card) => {
    const box = card.querySelector(".bnr__img");
    if (!box) return;
    if (mobile) { box.style.width = ""; box.style.height = ""; return; }
    const body = card.querySelector(".bnr__body");
    const h = body ? body.getBoundingClientRect().height : 0;
    const maxW = card.getBoundingClientRect().width * 0.5;
    if (!h || !maxW) return;
    const w = Math.min((h * 16) / 9, maxW);
    box.style.width = `${Math.round(w)}px`;
    box.style.height = `${Math.round((w * 9) / 16)}px`;
  });
}

// 이미지 로드 실패 → 이미지 칸만 숨김. 여러 장이면 5초 머문 뒤 다음 이미지가 왼쪽에서 들어오며 현재 이미지가 오른쪽으로 밀려 나간다
// (항상 같은 방향, 무한 반복, 호버 중엔 멈춤, 움직임 줄이기 설정이면 고정).
export function mountBannerMotion(scope) {
  stopBannerMotion();
  const reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  _layoutImages(scope);
  if (window.ResizeObserver) {
    const ro = new ResizeObserver(() => _layoutImages(scope));
    scope.querySelectorAll(".bnr__card").forEach((c) => ro.observe(c));
    scope.querySelectorAll(".bnr__body").forEach((c) => ro.observe(c));
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
