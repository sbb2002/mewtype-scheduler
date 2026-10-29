// timetable.js — (v4.1.0) 오늘 타임테이블(PC) · 오늘 카드(모바일) · 이후 예고 펼치기 버튼.
// 예고판(5열 레인 보드)의 "오늘/7일 이내/7일 이후 버킷 + ON-AIR 영역"을 대체한다.
// 오늘 = KST 04:00 ~ 익일 04:00(오늘 예고), 그다음 하루 = 내일 예고. 그 밖의 예고는 "이후 예고"로 펼친다.
// 데이터는 textContent/createElement 로만 주입(XSS 방어, innerHTML 금지) — render.js 와 같은 규칙.
//
//  dayWindow(nowMs, offset)            → { ds, de }  오늘 구간(ms) · offset 1 = 내일 구간
//  classify(items, archive, nowMs, order) → { ds, de, live, ended, upcoming, tomorrow, later }
//  buildTimetable(ctx)                 → PC 편성 레일 (편지 배지 자리 = 왼쪽 칸의 .lane__avatar)
//  buildTodayCards(ctx, key)           → 모바일 오늘 카드(카운트다운 링)
//  buildFoldButton(counts, ctx)        → "이후 예고 N건 펼치기" 버튼 (상태는 #board 클래스로 — 캐러셀 클론에도 적용)
//  planLater(items, archive, now, order) → (v4.9.6) PC 표 보기 이후 예고 = 이번주 7일 + 먼 미래 + 날짜 미정
//  buildLaterTables(ctx, plan)         → (v4.9.6) 위 계획을 2열 표(이번주 · 먼 미래)로 — 점 하나 = 방송 하나
//  tickTimetable(boardEl, nowMs)       → 1분 틱: 지금 선 · 링 갱신. 오늘 구간이 끝났으면 true(재렌더 필요)
//  applyTimetableMarquees(boardEl)     → 블록 제목이 넘치면 한 줄 무한 흐름
//  closeCardPop()                      → 블록 카드 팝업 닫기

import { formatKST } from "./time.js";
import { KING_KEY, KING_RING_LATE, decorateBlock, decoratePopup, decorateCard } from "./king.js";   // (v4.3.1) 노노카 지각 이스터에그

const HOUR_MS = 3600000;
const DAY_MS = 86400000;
const KST_OFFSET_MS = 9 * HOUR_MS;
export const DAY_START_HOUR = 4;           // (v4.9.6) 예고보드의 하루 = 04:00 ~ 익일 04:00 (프론트 전용 — 모니터링 하루 경계 06:00 과 별개)
const LATE_ENDED_MIN = 10 * 60000;         // 종료 기록으로 인정하는 최소/최대 방송 길이
const LATE_ENDED_MAX = 12 * HOUR_MS;
const TRACK_PX = 888;                      // 블록 위치·폭을 환산하는 기준 트랙 폭 (실제 폭에 비례)
const W_FIXED = 250;                       // 종료 시각을 모르는 블록의 고정 폭 (「방송시작까지 n.n시간」이 들어가는 폭)
const W_MIN = 16;                          // 아무리 좁아도 이만큼은 보인다
const SOON_MS = HOUR_MS;                   // 1시간 이내 시작 = 노랑 강조

const KIND_LABEL = { game: "게임", talk: "잡담", song: "노래", collab: "합동", morning: "아침" };

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}

/* 아바타 URL을 표시/샘플링에 충분한 작은 크기로 정규화 (yt3 URL의 =sNNN 파라미터). */
export function avatarSized(url, size) {
  return typeof url === "string" ? url.replace(/=s\d+/, `=s${size}`) : url;
}

/* ── KST 표기 ─────────────────────────────────────────────────────── */
const _hm = new Intl.DateTimeFormat("ko-KR", { timeZone: "Asia/Seoul", hour: "2-digit", minute: "2-digit", hour12: false });
const _md = new Intl.DateTimeFormat("ko-KR", { timeZone: "Asia/Seoul", month: "2-digit", day: "2-digit", weekday: "short" });
const _ymd = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul" });
const hm = (ms) => _hm.format(new Date(ms));
function mdw(ms) {
  const p = Object.fromEntries(_md.formatToParts(new Date(ms)).map((x) => [x.type, x.value]));
  return `${p.month}/${p.day}(${p.weekday})`;
}
const ymd = (ms) => _ymd.format(new Date(ms));
/* 예고 블록 2번째 줄 — 카드 도넛 타이머와 같은 규칙(60분 미만 = 분 정수 · 이상 = 시간, 소수 한 자리 · 정각이면 정수) */
const startsIn = (min) => `방송시작까지 ${min < 60 ? `${min}분` : `${(min / 60).toFixed(min % 60 ? 1 : 0)}시간`}`;
function durLabel(ms) {
  const m = Math.round(ms / 60000);
  return m < 60 ? `${m}분` : `${Math.floor(m / 60)}시간${m % 60 ? ` ${m % 60}분` : ""}`;
}

/* ── 오늘 구간 ────────────────────────────────────────────────────── */
/* 오늘 구간(offset 0 = 오늘 예고, 1 = 내일 예고) */
export function dayWindow(nowMs, offset = 0) {
  const k = nowMs + KST_OFFSET_MS;
  const d = new Date(k);
  let base = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate(), DAY_START_HOUR);
  if (k < base) base -= DAY_MS;
  const ds = base - KST_OFFSET_MS + offset * DAY_MS;
  return { ds, de: ds + DAY_MS };
}

const itemMs = (iso) => (iso ? Date.parse(iso) : NaN);

/**
 * 아이템을 오늘 구간 기준으로 나눈다.
 *  live / ended / upcoming = 타임테이블에 놓이는 항목 { item, start, end }
 *  tomorrow = 내일 예고(다음 04:00 하루)의 예정 { item, start }, later = 이후 예고(그다음 04:00 이후 · 시각 미정) 원본 아이템 목록 (시작 시각순)
 * ended = preview.json 의 end 상태 + preview_archive.json 에서 오늘 04:00 이후 시작해 이미 끝난 방송.
 */
export function classify(items, archiveItems, nowMs, order) {
  const { ds, de } = dayWindow(nowMs);
  const live = [], ended = [], upcoming = [], tomorrow = [], later = [];
  const seen = new Set();
  const ok = (it) => it && it.channel_key && order.includes(it.channel_key);

  for (const item of items || []) {
    if (!ok(item)) continue;
    if (item.video_id) seen.add(item.video_id);
    if (item.state === "live") {
      const s = itemMs(item.actual_start || item.scheduled_start);
      if (isFinite(s)) live.push({ item, start: s, end: null });
    } else if (item.state === "end") {
      const s = itemMs(item.actual_start || item.scheduled_start);
      const e = itemMs(item.state_since);
      if (isFinite(s) && (!isFinite(e) || e > ds)) ended.push({ item, start: s, end: isFinite(e) ? e : null });
    } else if (item.state === "announced" || item.state === "upcoming" || item.state === "watching") {
      const s = itemMs(item.scheduled_start);
      if (item.time_tbd || !isFinite(s) || s >= de + DAY_MS) later.push(item);
      else if (s >= de) tomorrow.push({ item, start: s, end: null });
      else upcoming.push({ item, start: s, end: null });
    }
  }
  for (const item of archiveItems || []) {
    if (!ok(item) || (item.video_id && seen.has(item.video_id))) continue;
    const a = itemMs(item.actual_start);
    const e = itemMs(item.archived_at);
    if (!isFinite(a) || !isFinite(e) || a < ds || e > nowMs) continue;
    if (e - a < LATE_ENDED_MIN || e - a > LATE_ENDED_MAX) continue;
    ended.push({ item, start: a, end: e });
  }
  const byStart = (x, y) => x.start - y.start;
  live.sort(byStart); ended.sort(byStart); upcoming.sort(byStart); tomorrow.sort(byStart);
  later.sort((a, b) => {
    const x = itemMs(a.scheduled_start), y = itemMs(b.scheduled_start);
    if (!isFinite(x)) return isFinite(y) ? 1 : 0;
    if (!isFinite(y)) return -1;
    return x - y;
  });
  return { ds, de, live, ended, upcoming, tomorrow, later };
}

/* ── 이후 예고 · PC 표 보기 (v4.9.6) ─────────────────────────────────────
   날짜 경계 = KST 달력 00:00 (예고보드의 04:00 하루와 다르다). 이번주 = 일요일 ~ 토요일 7칸.
   오늘 · 내일 예고 구간에 든 예고는 먼 미래에 넣지 않는다(타임테이블 레일이 이미 보여 준다). */
const kstMidnight = (ms) => {
  const d = new Date(ms + KST_OFFSET_MS);
  return Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()) - KST_OFFSET_MS;
};
/* (v4.9.6) 계획 = { ws 이번주 일요일 00:00, we 다음 일요일 00:00, today 0~6(오늘 줄), days[7] = { ds, entries }, far = [{ ds, entries }], undated = [entry] }
   entry = { item, start, end, state("ended" | "live" | "upcoming"), keys }. 멤버 5인 채널 예고만 넣는다(order). */
export function planLater(items, archiveItems, nowMs, order) {
  const today0 = kstMidnight(nowMs);
  const dow = new Date(today0 + KST_OFFSET_MS).getUTCDay();   // 0 = 일
  const ws = today0 - dow * DAY_MS, we = ws + 7 * DAY_MS;
  const tomEnd = dayWindow(nowMs).de + DAY_MS;               // 내일 예고 구간 끝 — 이 전까지는 먼 미래가 아니다
  const days = Array.from({ length: 7 }, (_, i) => ({ ds: ws + i * DAY_MS, entries: [] }));
  const farBy = new Map();
  const undated = [];
  const seen = new Set();
  const ok = (it) => it && it.channel_key && order.includes(it.channel_key);
  const mk = (item, start, end, state) => ({ item, start, end, state, keys: itemKeys(item, order) });
  const place = (entry, canFar) => {
    const s = entry.start;
    if (s >= ws && s < we) days[Math.floor((s - ws) / DAY_MS)].entries.push(entry);
    else if (canFar && s >= we && s >= tomEnd) {
      const d = kstMidnight(s);
      if (!farBy.has(d)) farBy.set(d, []);
      farBy.get(d).push(entry);
    }
  };

  for (const item of items || []) {
    if (!ok(item)) continue;
    if (item.video_id) seen.add(item.video_id);
    if (item.state === "live") {
      const s = itemMs(item.actual_start || item.scheduled_start);
      if (isFinite(s)) place(mk(item, s, null, "live"), false);
    } else if (item.state === "end") {
      const s = itemMs(item.actual_start || item.scheduled_start);
      const e = itemMs(item.state_since);
      if (isFinite(s)) place(mk(item, s, isFinite(e) ? e : null, "ended"), false);
    } else if (item.state === "announced" || item.state === "upcoming" || item.state === "watching") {
      const s = itemMs(item.scheduled_start);
      if (isFinite(s)) place(mk(item, s, null, "upcoming"), true);
      else undated.push(mk(item, NaN, null, "upcoming"));
    }
  }
  // 보관함 — 같은 video_id 가 preview 에 있으면 건너뛴다 (classify 와 같은 규칙, 범위만 이번주)
  for (const item of archiveItems || []) {
    if (!ok(item) || (item.video_id && seen.has(item.video_id))) continue;
    const a = itemMs(item.actual_start), e = itemMs(item.archived_at);
    if (!isFinite(a) || !isFinite(e) || e > nowMs) continue;
    if (e - a < LATE_ENDED_MIN || e - a > LATE_ENDED_MAX) continue;
    place(mk(item, a, e, "ended"), false);
  }

  const byStart = (x, y) => x.start - y.start;
  days.forEach((d) => d.entries.sort(byStart));
  const far = [...farBy.entries()].sort((x, y) => x[0] - y[0]).map(([ds, entries]) => ({ ds, entries: entries.sort(byStart) }));
  return { ws, we, today: dow, days, far, undated };
}

/* (v4.9.6) 개수 — 머리 버튼 문구(「이번주 N · 먼 미래 M」)와 버튼 표시 조건(total 1건 이상)에 쓴다 */
export function laterCounts(plan) {
  const week = plan.days.reduce((n, d) => n + d.entries.length, 0);
  const rest = plan.far.reduce((n, f) => n + f.entries.length, 0) + plan.undated.length;
  return { week, rest, total: week + rest };
}

/* ── 항목 공통 헬퍼 ────────────────────────────────────────────────── */
export function itemKeys(item, order) {
  const keys = new Set([item.channel_key, ...(Array.isArray(item.collab_with) ? item.collab_with : [])]);
  return [...keys].filter((k) => k && order.includes(k));
}
const isCollab = (item) => item.kind === "collab" || (Array.isArray(item.collab_with) && item.collab_with.length > 0);
const shortName = (ch) => ((ch && ch.name_ko) || "").split(" ").pop();
const hasVideo = (item) => !!item.video_id;

function titleText(item, ctx) {
  if (item.title) return item.title_ko && item.title_ko !== item.title ? `${item.title_ko}　—　${item.title}` : item.title;
  if (isCollab(item)) {
    const names = itemKeys(item, ctx.order).filter((k) => k !== item.channel_key).map((k) => shortName(ctx.channels[k])).filter(Boolean);
    return names.length ? `합동 · ${names.join(", ")}` : "합동 예고";
  }
  const kind = KIND_LABEL[item.kind];
  return kind ? `${kind} 예고` : "방송 예고";
}

/* 상태 태그들 → 요소 배열 */
function tagsFor(entry, state) {
  const out = [];
  const add = (cls, text) => out.push(el("span", `tt-tag ${cls}`, text));
  const it = entry.item;
  if (state === "ended") add("tt-tag--end", "종료");
  if (isCollab(it)) add("tt-tag--collab", "합동");
  if (it.membership) add("tt-tag--mem", "회원 전용");
  if (state === "upcoming" && !hasVideo(it)) add("tt-tag--ann", "예고");
  return out;
}

function placeholderThumb(cls, ch) {
  const d = el("div", `${cls} tt-ph`);
  const a = el("span", "tt-ava tt-ph__ava");
  if (ch && ch.avatar) a.style.backgroundImage = `url("${avatarSized(ch.avatar, 176)}")`;
  d.appendChild(a);
  return d;
}
function thumbEl(item, cls, ctx) {
  if (item.thumbnail && !item.membership) {
    const d = el("div", cls);
    d.style.backgroundImage = `url("${item.thumbnail}")`;
    return d;
  }
  return placeholderThumb(cls, ctx.channels[item.channel_key]);
}

/* ── 블록 카드 팝업 (PC) ─────────────────────────────────────────────
   블록 호버 = 미리보기, 클릭 = 고정. 바깥 클릭 / Esc / 다시 클릭으로 닫힌다. 영상 이동은 팝업의 이미지·버튼으로만. */
let cpop = null, cpopOwner = null, cpopPinned = false, cpopTimer = 0, popWired = false;

export function closeCardPop() {
  clearTimeout(cpopTimer);
  if (cpop) cpop.remove();
  cpop = cpopOwner = null;
  cpopPinned = false;
}

/* (v4.9.6) 날짜를 붙인 시각 — 이후 예고 표의 점에서 연 팝업만 쓴다 (블록 팝업은 그대로) */
function datedLabel(entry, state) {
  if (!isFinite(entry.start)) return "날짜 미정";
  const it = entry.item;
  const d = mdw(entry.start);
  if (state === "live") return `LIVE · ${d} ${hm(entry.start)} 시작`;
  if (it.time_tbd) return `${d} 시각 미정`;
  if (entry.end) return `${d} ${hm(entry.start)} ~ ${hm(entry.end)}${ymd(entry.end) !== ymd(entry.start) ? " (익일)" : ""} · ${durLabel(entry.end - entry.start)}`;
  return `${d} ${hm(entry.start)}`;
}

function rangeLabel(entry, state, dated = false) {
  if (dated) return datedLabel(entry, state);   // (v4.9.6)
  if (state === "live") return `LIVE · ${hm(entry.start)} 시작`;
  if (entry.end) return `${hm(entry.start)} ~ ${hm(entry.end)}${ymd(entry.end) !== ymd(entry.start) ? " (익일)" : ""} · ${durLabel(entry.end - entry.start)}`;
  return hm(entry.start);
}

function showCardPop(entry, state, owner, pin, ctx, rowKey, dated = false) {
  if (cpop && cpopOwner === owner) {
    if (pin) { if (cpopPinned) closeCardPop(); else cpopPinned = true; }
    return;
  }
  if (cpop && cpopPinned) return;                 // 고정된 팝업이 있으면 호버로는 바꾸지 않음
  closeCardPop();
  const it = entry.item;
  cpopOwner = owner;
  cpopPinned = !!pin;
  cpop = el("div", "tt-pop" + (state === "ended" ? " tt-pop--ended" : ""));
  cpop.setAttribute("role", "dialog");
  const ch = ctx.channels[it.channel_key] || {};
  const url = hasVideo(it) && it.url ? it.url : null;

  let img;
  if (url) { img = el("a", "tt-pop__img"); img.href = url; img.target = "_blank"; img.rel = "noopener"; img.setAttribute("aria-label", "YouTube에서 영상 열기"); }
  else img = el("div", "tt-pop__img");
  if (it.thumbnail && !it.membership) img.style.backgroundImage = `url("${it.thumbnail}")`;
  else {
    img.classList.add("tt-ph");
    const pa = el("span", "tt-ava tt-ph__ava");
    if (ch.avatar) pa.style.backgroundImage = `url("${avatarSized(ch.avatar, 176)}")`;
    img.appendChild(pa);
  }
  cpop.appendChild(img);

  const body = el("div", "tt-pop__body");
  const nm = el("div", "tt-pop__nm");
  const keys = itemKeys(it, ctx.order);
  const faces = el("span", "tt-faces");
  for (const k of keys) {
    const a = el("span", "tt-face");
    const c = ctx.channels[k];
    if (c && c.avatar) a.style.backgroundImage = `url("${avatarSized(c.avatar, 176)}")`;
    faces.appendChild(a);
  }
  nm.append(faces, el("b", "", keys.map((k) => shortName(ctx.channels[k])).join(" · ") || shortName(ch)));
  for (const t of (state === "live" ? [el("span", "tt-tag tt-tag--live", "LIVE")] : []).concat(tagsFor(entry, state))) nm.appendChild(t);
  body.appendChild(nm);
  body.appendChild(el("div", "tt-pop__rg", rangeLabel(entry, state, dated)));
  body.appendChild(el("div", "tt-pop__ti", titleText(it, ctx)));
  if (url) {
    const btn = el("a", "tt-pop__btn", "▶ YouTube에서 보기");
    btn.href = url; btn.target = "_blank"; btn.rel = "noopener";
    body.appendChild(btn);
  } else {
    body.appendChild(el("span", "tt-pop__none", "아직 영상 링크가 없습니다"));
  }
  cpop.appendChild(body);
  if (rowKey === KING_KEY) decoratePopup(cpop, img, body, entry, state);   // (v4.3.1) 노노카 행의 팝업에만 — 높이가 정해진 뒤 위치를 재므로 여기서
  cpop.addEventListener("mouseenter", () => clearTimeout(cpopTimer));
  cpop.addEventListener("mouseleave", () => {
    if (!cpopPinned) { clearTimeout(cpopTimer); cpopTimer = setTimeout(closeCardPop, 150); }
  });
  document.body.appendChild(cpop);

  const r = owner.getBoundingClientRect();
  const w = Math.min(290, innerWidth - 24);
  const h = cpop.offsetHeight;
  const left = Math.min(Math.max(r.left + scrollX, 12 + scrollX), scrollX + innerWidth - w - 12);
  const below = r.bottom + h + 14 < innerHeight || r.top < h + 14;
  cpop.style.width = `${w}px`;
  cpop.style.left = `${left}px`;
  cpop.style.top = `${below ? r.bottom + scrollY + 8 : r.top + scrollY - h - 8}px`;
  if (!below) cpop.dataset.anchorBottom = String(r.top + scrollY - 8);   // (king.js) 위쪽에 놓인 팝업이 줄어들어도 블록에 붙어 있게 아래 가장자리를 기록
}

/* (v4.9.6) 블록 · 이후 예고 점 공용 팝업 연결 — 호버 = 미리보기, 클릭 · Enter · Space = 고정. dated = 날짜 붙인 시각(점에서만) */
function wirePop(node, entry, state, ctx, rowKey, dated = false) {
  node.addEventListener("click", (e) => { e.stopPropagation(); showCardPop(entry, state, node, true, ctx, rowKey, dated); });
  node.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); showCardPop(entry, state, node, true, ctx, rowKey, dated); }
  });
  node.addEventListener("mouseenter", () => { if (ttSliding) return; clearTimeout(cpopTimer); showCardPop(entry, state, node, false, ctx, rowKey, dated); });   // (v4.9.6) 넘기는 동안은 팝업 안 띄움
  node.addEventListener("mouseleave", () => {
    if (!cpopPinned) { clearTimeout(cpopTimer); cpopTimer = setTimeout(closeCardPop, 150); }
  });
}

function wirePopOnce() {
  if (popWired) return;
  popWired = true;
  document.addEventListener("click", (e) => {
    if (!cpop) return;
    if (cpop.contains(e.target) || (cpopOwner && cpopOwner.contains(e.target))) return;
    closeCardPop();
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeCardPop(); });
}

/* ── PC 편성 레일 ─────────────────────────────────────────────────── */
function blockEl(entry, state, ctx, geo, rowKey) {
  const it = entry.item;
  const b = el("div", `tt-blk tt-blk--${state}`);
  if (isCollab(it)) b.classList.add("tt-blk--collab");
  if (state === "upcoming" && entry.start - ctx.nowMs < SOON_MS && entry.start >= ctx.nowMs) b.classList.add("tt-blk--soon");
  b.setAttribute("role", "button");
  b.tabIndex = 0;
  b.setAttribute("aria-haspopup", "dialog");
  b.style.left = `${(geo.l / TRACK_PX) * 100}%`;
  b.style.width = `${(geo.w / TRACK_PX) * 100}%`;
  b.setAttribute("aria-label", `${titleText(it, ctx)} · ${rangeLabel(entry, state)}`);

  b.appendChild(thumbEl(it, "tt-blk__th", ctx));
  const tx = el("div", "tt-blk__tx");
  const head = el("div", "tt-blk__t");
  if (state === "live") head.appendChild(el("span", "tt-tag tt-tag--live", "LIVE"));
  else head.appendChild(el("span", "tt-blk__time", entry.end ? `${hm(entry.start)}~${hm(entry.end)}` : hm(entry.start)));
  for (const t of tagsFor(entry, state)) head.appendChild(t);
  tx.appendChild(head);
  if (state === "upcoming") {   // 2번째 줄 (king.js 가 「지각」 자리로 쓴다). 라이브 · 종료 블록은 빈 줄(.tt-blk__sp)로 제목 높이를 맞춘다
    const min = Math.max(0, Math.round((entry.start - ctx.nowMs) / 60000));
    const late = entry.start < ctx.nowMs;
    tx.appendChild(el("div", "tt-blk__rel" + (late ? " is-late" : ""), late ? "지각" : startsIn(min)));
  } else tx.appendChild(el("div", "tt-blk__sp"));
  const n = el("div", "tt-blk__n");
  const trk = el("span", "tt-blk__trk");
  trk.appendChild(el("span", "", titleText(it, ctx)));
  n.appendChild(trk);
  tx.appendChild(n);
  b.appendChild(tx);

  wirePop(b, entry, state, ctx, rowKey);   // (v4.9.6) 팝업 연결은 이 블록 · 이후 예고 점이 함께 쓴다
  if (rowKey === KING_KEY) decorateBlock(b, entry, state);   // (v4.3.1) 노노카 본인 행의 블록에만
  return b;
}

/* 한 멤버 행의 블록 배치: 길이를 알면 실제 길이, 모르면 고정 폭. 한 줄만 쓰므로 겹치면 앞 블록을 다음 시작에서 자른다. */
function layoutRow(entries, ctx) {
  const items = entries.map(({ entry, state }) => {
    const startPx = Math.min(1, Math.max(0, (entry.start - ctx.ds) / DAY_MS)) * TRACK_PX;
    let w, known = false;
    if (state === "live") w = Math.max(W_FIXED, ((ctx.nowMs - ctx.ds) / DAY_MS) * TRACK_PX - startPx);
    else if (entry.end) { w = Math.max(W_MIN, Math.min(1, (entry.end - ctx.ds) / DAY_MS) * TRACK_PX - startPx); known = true; }
    else w = W_FIXED;
    let l = startPx;
    if (!known && l + w > TRACK_PX) l = Math.max(0, TRACK_PX - w);       // 오른쪽 끝에 닿으면 끝에 맞춤
    return { entry, state, l, w };
  });
  items.sort((a, b) => a.l - b.l);
  items.forEach((it, i) => {
    const nx = items[i + 1];
    if (nx && it.l + it.w > nx.l - 3) it.w = Math.max(W_MIN, nx.l - it.l - 3);
  });
  return items;
}

/* ── 보기 방식 탭 [테이블 | 카드] (v4.4.0, PC 전용) ───────────────────── */
const VIEW_TABS = [
  { view: "table", label: "테이블", icon: ["M1.5 4a1.5 1.5 0 0 1 1.5-1.5h10A1.5 1.5 0 0 1 14.5 4v8a1.5 1.5 0 0 1-1.5 1.5H3A1.5 1.5 0 0 1 1.5 12z", "M1.5 6.5h13M1.5 10h13M6 6.5v7"] },
  { view: "cards", label: "카드", icon: ["M2.5 2h1.4a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H2.5a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1z", "M7.3 2h1.4a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H7.3a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1z", "M12.1 2h1.4a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1h-1.4a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1z"] },
];
function tabIcon(paths) {
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 16 16");
  svg.setAttribute("aria-hidden", "true");
  for (const d of paths) {
    const p = document.createElementNS(NS, "path");
    p.setAttribute("d", d);
    svg.appendChild(p);
  }
  return svg;
}
export function buildViewTabs(current, onSelect) {
  const box = el("div", "vt");
  box.setAttribute("role", "tablist");
  box.setAttribute("aria-label", "보기 방식");
  const btns = VIEW_TABS.map(({ view, label, icon }) => {
    const b = el("button", "vt__btn");
    b.type = "button";
    b.setAttribute("role", "tab");
    b.dataset.view = view;
    const on = view === current;
    b.setAttribute("aria-selected", String(on));
    b.tabIndex = on ? 0 : -1;
    b.append(tabIcon(icon), document.createTextNode(label));
    return b;
  });
  btns.forEach((b, i) => {
    b.addEventListener("click", () => { if (b.dataset.view !== current) onSelect(b.dataset.view); });
    b.addEventListener("keydown", (e) => {
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
      e.preventDefault();
      const n = btns[(i + (e.key === "ArrowRight" ? 1 : btns.length - 1)) % btns.length];
      if (n.dataset.view !== current) onSelect(n.dataset.view);
    });
  });
  box.append(...btns);
  return box;
}

/* 「오늘 예고」 머리줄 — 테이블 · 카드 보기 공용. 오른쪽 끝에 보기 방식 탭 (ctx.view · ctx.onViewChange).
   (v4.9.6) opts.day(0|1) = 오늘 · 내일 예고 제목 · 메타, opts.pager = 두 점 표시(표 보기 전용). 인자가 없으면 지금처럼 오늘 예고 */
export function buildBoardHead(ctx, opts = {}) {
  const day = opts.day ? 1 : 0;
  const head = el("div", "tt__head");
  head.appendChild(el("h2", "tt__title", day ? "내일 예고" : "오늘 예고"));
  if (opts.pager) {   // (v4.9.6) 두 점 — 오늘 · 내일 중 어디인지. --pg 는 끄는 동안 JS 가 옮긴다
    const pg = el("span", "tt__pg");
    pg.setAttribute("aria-hidden", "true");
    pg.style.setProperty("--pg", String(day));
    pg.append(el("i"), el("i"));
    head.appendChild(pg);
  }
  head.appendChild(el("span", "tt__meta", headMeta(ctx, day)));
  if (ctx.onViewChange) head.appendChild(buildViewTabs(ctx.view, ctx.onViewChange));
  return head;
}

/* (마이크로 인터랙션) 편성 레일이 가로로 넘칠 때 — 넘친 쪽 끝을 흐리게 지우고(mask, --ml · --mr) 그쪽 가장자리에 화살표 버튼
   (누르면 그쪽으로 320px). 처음 한 번은 오른쪽 화살표가 세 번 까딱인다(페이지를 연 동안 1회 — 75초마다 다시 그려도 반복하지 않게).
   끝까지 밀면 그쪽 흐림 · 화살표가 없어진다. 넘치지 않으면 아무것도 안 보인다. */
let ttRO = null, ttNudged = false;
function overflowArrow(side) {
  const b = el("button", `tt__arr tt__arr--${side}`);
  b.type = "button";
  b.disabled = true;
  b.setAttribute("aria-label", side === "l" ? "앞 시간 보기" : "뒤 시간 보기");
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 12 12");
  svg.setAttribute("aria-hidden", "true");
  const p = document.createElementNS("http://www.w3.org/2000/svg", "path");
  p.setAttribute("d", side === "l" ? "M8 2 4 6l4 4" : "M4 2l4 4-4 4");
  svg.appendChild(p);
  b.appendChild(svg);
  return b;
}
function wireOverflow(scroll) {
  const box = el("div", "tt__sw");
  const aL = overflowArrow("l"), aR = overflowArrow("r");
  box.append(scroll, aL, aR);
  const calm = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  const upd = () => {
    const max = scroll.scrollWidth - scroll.clientWidth, over = max > 2;
    const l = over ? Math.min(1, scroll.scrollLeft / 60) : 0, r = over ? Math.min(1, (max - scroll.scrollLeft) / 60) : 0;
    box.classList.toggle("is-over", over);
    box.style.setProperty("--ml", String(1 - 0.92 * l));
    box.style.setProperty("--mr", String(1 - 0.92 * r));
    aL.disabled = l <= 0.5;
    aR.disabled = r <= 0.5;
    if (!aR.disabled && !ttNudged && !calm && !nudgeBusy) { ttNudged = true; aR.classList.add("is-nudge"); }   // (v4.9.6) 일 이동 버튼이 이 렌더에서 까딱였으면 넘침 화살표는 다음 렌더로
  };
  const go = (dx) => scroll.scrollBy({ left: dx, behavior: calm ? "auto" : "smooth" });
  aL.addEventListener("click", () => go(-320));
  aR.addEventListener("click", () => go(320));
  scroll.addEventListener("scroll", upd, { passive: true });
  if (ttRO) ttRO.disconnect();   // 다시 그릴 때마다 새 레일만 지켜본다
  if (window.ResizeObserver) { ttRO = new ResizeObserver(upd); ttRO.observe(scroll); }
  requestAnimationFrame(upd);
  return box;
}

/* (v4.9.6) 머리줄 메타 — 0 = 오늘 예고(방송 중 · 종료 건수 포함), 1 = 내일 예고(다음 04:00 하루) */
function headMeta(ctx, day) {
  if (day) return `${mdw(ctx.de)} 04:00 ~ 익일 04:00 · 예정 ${ctx.tomorrow.length}건`;
  const nLive = ctx.live.length, nEnded = ctx.ended.length;
  return `${mdw(ctx.ds)} 04:00 ~ 익일 04:00 · 예정 ${ctx.upcoming.length}건` +
    (nLive ? ` · 방송 중 ${nLive}건` : "") + (nEnded ? ` · 종료 ${nEnded}건` : "");
}

/* (v4.9.6) 일 이동 버튼 상태 — 화살표 방향 · 비활성(내일 예정 0건) · 건수 알약 · 글자 */
let ttDay = 0, ttSliding = false, dayNudged = false, lastTomN = null, nudgeBusy = false, ttDragOff = null;
function syncDayBtn(btn, nTom) {
  btn.classList.toggle("is-back", ttDay === 1);
  btn.disabled = ttDay === 0 && nTom === 0;
  btn.setAttribute("aria-label", btn.disabled ? "내일 예정 없음" : ttDay ? "오늘 예고 보기" : `내일 예고 보기 (예정 ${nTom}건)`);
  const n = btn.querySelector(".tt__day-n");
  n.textContent = String(nTom);
  n.hidden = nTom === 0 || ttDay === 1;
}

/* (v4.9.6) 넘기기 판정 — dx = 끈 거리(px, 왼쪽 = 음수 = 내일 쪽), vx = 놓기 직전 속도(px/ms), w = 레일 폭, day = 지금 화면, canNext = 내일 예정이 1건 이상 */
export function swipeDecision(dx, vx, w, day, canNext) {
  if (day === 0 && canNext && dx < 0 && (-dx >= w * 0.25 || vx <= -0.5)) return "next";
  if (day === 1 && dx > 0 && (dx >= w * 0.25 || vx >= 0.5)) return "prev";
  return "stay";
}
/* (v4.9.6) 끄는 동안 띠가 따라오는 거리 — 더 갈 화면이 없는 쪽은 고무줄(30%, 최대 48px), 갈 수 있는 쪽은 1:1(레일 폭까지) */
export function dragFollow(dx, w, day, canNext) {
  const open = (day === 0 && dx < 0 && canNext) || (day === 1 && dx > 0);
  if (open) return Math.max(-w, Math.min(w, dx));
  return Math.sign(dx) * Math.min(48, Math.abs(dx) * 0.3);
}

/* (v4.9.6) 한 멤버의 항목 (화면별 목록에서) */
const mineOf = (items, key, order) => items.filter(({ entry }) => itemKeys(entry.item, order).includes(key));

/* (v4.9.6) 머리줄 글자 바꾸기 — 나가는 쪽으로 흐려지고 들어오는 쪽에서 다시 밝아진다. 움직임 줄이기면 바로 바꾼다 */
function swapText(node, text, dir, calm) {
  if (calm || !node.animate) { node.textContent = text; return; }
  node.animate([{ opacity: 1, transform: "none" }, { opacity: 0, transform: `translateX(${-6 * dir}px)` }], { duration: 80, easing: "ease-in" }).onfinish = () => {
    node.textContent = text;
    node.animate([{ opacity: 0, transform: `translateX(${6 * dir}px)` }, { opacity: 1, transform: "none" }], { duration: 80, easing: "ease-out" });
  };
}

/* (v4.9.6) 한 화면(pane) = 시간축 + 멤버별 트랙. day 0 = 오늘 예고(지금 선 · 지난 구간 음영 포함), day 1 = 내일 예고 */
function buildPane(pctx, items, day) {
  const pane = el("div", "tt__pane");
  pane.dataset.day = String(day);
  // 시간축: 04:00 부터 4시간마다. 자정은 강조 + 익일 날짜 (MID = 04:00 에서 자정까지 20시간)
  const MID = 24 - DAY_START_HOUR;
  const axis = el("div", "tt__axis");
  for (let h = 0; h <= 24; h += 4) {
    const t = pctx.ds + h * HOUR_MS;
    const tick = el("div", "tt__tick" + (h === 0 ? " is-first" : h === 24 ? " is-last" : "") + (h === MID ? " is-midnight" : ""));
    tick.style.left = `${(h / 24) * 100}%`;
    tick.appendChild(el("b", "", hm(t)));
    const sub = h === 0 ? mdw(t) : h === MID ? `자정 · 익일 ${mdw(t)}` : h === 24 ? `익일 ${mdw(t)}` : "";
    if (sub) tick.appendChild(document.createTextNode(sub));
    axis.appendChild(tick);
  }
  pane.appendChild(axis);

  for (const key of pctx.order) {
    if (!pctx.channels[key]) continue;
    const mine = mineOf(items, key, pctx.order);
    const track = el("div", "tt__track");
    track.dataset.channel = key;               // sampleLaneColor 가 --lane-color 를 채운다
    if (!mine.length) track.appendChild(el("div", "tt__empty", day ? "내일 예정 없음" : "오늘 예정 없음"));
    for (const g of layoutRow(mine, pctx)) track.appendChild(blockEl(g.entry, g.state, pctx, g, key));
    pane.appendChild(track);
  }

  // 지금 선 · 지난 구간 음영 — 오늘 화면에만 (positionNow 가 위치를 채운다)
  if (!day) {
    const ov = el("div", "tt__ov");
    ov.append(el("div", "tt__past"), el("div", "tt__now"), el("div", "tt__nowtag", `지금 ${hm(pctx.nowMs)}`));
    pane.appendChild(ov);
  }
  return pane;
}

export function buildTimetable(ctx) {
  wirePopOnce();
  if (ttDragOff) ttDragOff();                  // (v4.9.6) 이전 렌더의 끌기 상태 · 창 리스너 정리
  const calm = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  const nTom = ctx.tomorrow.length;
  if (!nTom) ttDay = 0;                        // (v4.9.6) 내일 예정이 0건이 되면 오늘로
  nudgeBusy = false;

  const sec = el("section", "tt");
  sec.appendChild(buildBoardHead(ctx, { day: ttDay, pager: true }));

  // (v4.9.6) 두 화면의 항목 — 0 = 오늘 예고(종료 · 방송 중 · 예정), 1 = 내일 예고(예정)
  const ctx1 = { ...ctx, ds: ctx.de, de: ctx.de + DAY_MS };
  const items0 = [
    ...ctx.ended.map((entry) => ({ entry, state: "ended" })),
    ...ctx.live.map((entry) => ({ entry, state: "live" })),
    ...ctx.upcoming.map((entry) => ({ entry, state: "upcoming" })),
  ];
  const items1 = ctx.tomorrow.map((entry) => ({ entry, state: "upcoming" }));

  const scroll = el("div", "tt__scroll");
  const grid = el("div", "tt__grid");
  grid.__tt = { ds: ctx.ds, de: ctx.de };
  grid.style.setProperty("--dawn-l", `${((24 - DAY_START_HOUR) / 24) * 100}%`);   // 익일 새벽 칸 시작 = 자정

  // 1열: 머리 칸 + 멤버 칸 5줄 — 넘기는 동안 움직이지 않는다
  const side = el("div", "tt__side");
  side.appendChild(el("div", "tt__corner"));
  for (const key of ctx.order) {
    const ch = ctx.channels[key];
    if (!ch) continue;
    const lane = el("section", "lane tt__lane");
    lane.dataset.channel = key;
    const header = el("header", "lane__header tt__who");
    const avatar = el("span", "lane__avatar");
    if (ch.avatar) avatar.style.backgroundImage = `url("${avatarSized(ch.avatar, 176)}")`;
    const nm = el("span", "tt__nm");
    const cnt = el("small");
    cnt.dataset.n0 = String(mineOf(items0, key, ctx.order).length);
    cnt.dataset.n1 = String(mineOf(items1, key, ctx.order).length);
    cnt.textContent = `${ttDay ? cnt.dataset.n1 : cnt.dataset.n0}건`;
    nm.append(el("b", "", shortName(ch)), cnt);
    header.append(avatar, nm);
    lane.appendChild(header);
    side.appendChild(lane);
  }

  // 2열: 두 화면을 가로로 잇는 띠 — 화면 한 장 = 레일 폭. 일 이동 = 띠를 옮긴다
  const rail = el("div", "tt__rail");
  const strip = el("div", "tt__strip");
  strip.style.transform = `translateX(${-50 * ttDay}%)`;
  strip.append(buildPane(ctx, items0, 0), buildPane(ctx1, items1, 1));
  rail.appendChild(strip);
  grid.append(side, rail);
  scroll.appendChild(grid);

  // (v4.9.6) 일 이동 버튼 — 내일 예고가 있는데 오늘 예고가 비었으면 처음 한 번 까딱인다
  const btn = el("button", "tt__day");
  btn.type = "button";
  const ic = el("span", "tt__day-ic");
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 12 12");
  svg.setAttribute("aria-hidden", "true");
  const chev = document.createElementNS(NS, "path");
  chev.setAttribute("d", "M4 2l4 4-4 4");
  svg.appendChild(chev);
  ic.appendChild(svg);
  const dayN = el("span", "tt__day-n");
  btn.append(ic, dayN);
  if (!dayNudged && !calm && ttDay === 0 && ctx.upcoming.length === 0 && nTom > 0) {
    dayNudged = true;
    btn.classList.add("is-nudge");
    nudgeBusy = true;                          // 이 렌더의 넘침 화살표 까딱임은 건너뛴다 (ttNudged 는 그대로 — 다음 렌더에 한다)
  }
  const sw = wireOverflow(scroll);
  const body = el("div", "tt__body");
  body.append(sw, btn);
  sec.appendChild(body);
  syncDayBtn(btn, nTom);
  // 건수가 바뀌었으면 알약을 한 번 튀긴다
  const pop = lastTomN !== null && nTom !== lastTomN && nTom > 0 && !calm;
  lastTomN = nTom;
  if (pop) {
    dayN.classList.add("is-pop");
    dayN.addEventListener("animationend", () => dayN.classList.remove("is-pop"), { once: true });
  }

  const title = sec.querySelector(".tt__title");
  const meta = sec.querySelector(".tt__meta");
  const pg = sec.querySelector(".tt__pg");
  const smalls = sec.querySelectorAll(".tt__nm small");

  // 띠 이동 — 끝나면 ttSliding 을 내린다 (transitionend 또는 시간 제한 중 먼저). 이전 이동의 끝 처리는 먼저 치운다
  let slideEnd = null;
  const moveStrip = (to, ms) => {
    if (slideEnd) slideEnd();
    strip.style.transition = calm ? "none" : `transform ${ms}ms cubic-bezier(0.2, 0.8, 0.2, 1)`;
    strip.style.transform = `translateX(${-50 * to}%)`;
    if (calm) { ttSliding = false; return; }   // 움직임 줄이기: 바로 옮겼으니 끌기 중 올린 표시도 내린다
    ttSliding = true;
    let t = 0;
    const end = (e) => {
      if (e && e.target !== strip) return;
      clearTimeout(t);
      strip.removeEventListener("transitionend", end);
      ttSliding = false;
      slideEnd = null;
    };
    t = setTimeout(end, ms + 20);
    strip.addEventListener("transitionend", end);
    slideEnd = () => {
      clearTimeout(t);
      strip.removeEventListener("transitionend", end);
      ttSliding = false;
      slideEnd = null;
    };
  };

  // 화면 넘기기 (버튼 · 끌기 공용)
  const switchDay = (to) => {
    closeCardPop();
    if (to === ttDay) {                        // 끌기에서 온 경우 제자리로
      moveStrip(ttDay, 200);
      pg.style.setProperty("--pg", String(ttDay));
      return;
    }
    const dir = to > ttDay ? 1 : -1;
    ttDay = to;
    moveStrip(to, 280);
    swapText(title, to ? "내일 예고" : "오늘 예고", dir, calm);
    swapText(meta, headMeta(ctx, to), dir, calm);
    pg.style.setProperty("--pg", String(to));
    for (const s of smalls) {
      s.textContent = `${to ? s.dataset.n1 : s.dataset.n0}건`;
      if (!calm && s.animate) s.animate([{ opacity: 0.2 }, { opacity: 1 }], { duration: 160 });
    }
    syncDayBtn(btn, nTom);
  };
  btn.addEventListener("click", () => switchDay(ttDay ? 0 : 1));

  // 마우스 끌기 (레일) — 누른 뒤 창 리스너를 걸고, 놓으면 푼다. 다시 그릴 때도 ttDragOff 로 푼다
  let drag = null;
  let suppress = false;                        // 끌고 놓은 뒤 이어지는 click 한 번을 막는다
  const onMove = (e) => {
    if (!drag) return;
    const dx = e.clientX - drag.x;
    if (!drag.moved) {
      if (Math.abs(dx) <= 5) return;
      drag.moved = true;
      if (slideEnd) slideEnd();
      rail.classList.add("is-dragging");
      pg.classList.add("is-live");
      closeCardPop();
      ttSliding = true;
      strip.style.transition = "none";
    }
    e.preventDefault();
    drag.pts.push({ x: e.clientX, t: e.timeStamp });
    if (drag.pts.length > 5) drag.pts.shift();
    if (calm) return;                          // 움직임 줄이기: 띠는 놓을 때만 옮긴다
    const f = dragFollow(dx, drag.w, ttDay, nTom > 0);
    strip.style.transform = `translateX(calc(${-50 * ttDay}% + ${f}px))`;
    pg.style.setProperty("--pg", String(Math.min(1, Math.max(0, ttDay - f / drag.w))));
  };
  const endDrag = () => {
    window.removeEventListener("pointermove", onMove);
    window.removeEventListener("pointerup", onUp);
    window.removeEventListener("pointercancel", onUp);
  };
  const onUp = (e) => {
    endDrag();
    const d = drag;
    drag = null;
    if (!d || !d.moved) return;
    rail.classList.remove("is-dragging");
    pg.classList.remove("is-live");
    const p0 = d.pts[0], p1 = d.pts[d.pts.length - 1];
    const vx = p1.t > p0.t && e.timeStamp - p1.t < 80 ? (p1.x - p0.x) / (p1.t - p0.t) : 0;   // 멈췄다 놓았으면 0 (render.js 캐러셀과 같은 방식)
    const dec = swipeDecision(p1.x - d.x, vx, d.w, ttDay, nTom > 0);
    suppress = true;
    setTimeout(() => { suppress = false; }, 0);
    if (dec === "next") switchDay(1);
    else if (dec === "prev") switchDay(0);
    else { moveStrip(ttDay, 200); pg.style.setProperty("--pg", String(ttDay)); }
  };
  rail.addEventListener("pointerdown", (e) => {
    if (e.pointerType !== "mouse" || e.button !== 0) return;
    if (sw.classList.contains("is-over")) return;          // 넘치는 표는 가로 스크롤 · 화살표가 맡는다
    if (e.target.closest(".tt-blk, button")) return;
    drag = { x: e.clientX, w: rail.clientWidth || 1, pts: [{ x: e.clientX, t: e.timeStamp }], moved: false };
    window.addEventListener("pointermove", onMove, { passive: false });
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
  });
  rail.addEventListener("click", (e) => { if (suppress) { e.preventDefault(); e.stopPropagation(); } }, true);
  ttDragOff = () => { endDrag(); drag = null; ttSliding = false; };

  positionNow(grid, ctx.nowMs);

  const legend = el("div", "tt__legend");
  sec.appendChild(legend);

  for (const [cls, text] of [
    ["tt-lg--end", "종료된 방송 (실제 시작~종료)"],
    ["tt-lg--live", "방송 중"],
    ["tt-lg--soon", "1시간 이내"],
    ["tt-lg--collab", "합동 (참여 멤버 행마다 표시)"],
  ]) {
    const s = el("span");
    s.append(el("i", cls), document.createTextNode(text));
    legend.appendChild(s);
  }
  legend.appendChild(el("span", "", "블록을 누르면 카드 팝업 (영상 이동은 팝업에서)"));
  return sec;
}

function positionNow(grid, nowMs) {
  const w = grid.__tt;
  if (!w) return;
  const p = Math.min(1, Math.max(0, (nowMs - w.ds) / DAY_MS)) * 100;
  const now = grid.querySelector(".tt__now");
  const tag = grid.querySelector(".tt__nowtag");
  const past = grid.querySelector(".tt__past");
  if (now) now.style.left = `${p}%`;
  if (tag) { tag.style.left = `${p}%`; tag.textContent = `지금 ${hm(nowMs)}`; }
  if (past) past.style.width = `${p}%`;
}

/* ── 모바일 오늘 카드 (카운트다운 링) ───────────────────────────────── */
function ringPct(startMs, nowMs) {
  return Math.max(0, Math.min(100, Math.round((1 - (startMs - nowMs) / DAY_MS) * 100)));
}
/* 예정 링: 1시간 넘게 남으면 24시간 기준으로 차오른다(레인 색). (v4.5.8) 1시간 이내는 분 단위 — 가득 찬 노랑 링이 남은 분에 맞춰
   12시부터 시계방향으로 비워져 0분에 빈 링(.is-min, --p = 남은 비율). 시작 시각이 지나면 빈 링 + 「지각」(.is-late).
   노노카 지각 이스터에그가 붙은 카드(data-king)는 「지각」 대신 king.js 의 KING_RING_LATE. */
function updateRing(card, nowMs) {
  const start = Number(card.dataset.start);
  const ring = card.querySelector(".tcard__ring");
  if (!ring || !isFinite(start)) return;
  const left = start - nowMs;
  const min = Math.max(0, Math.round(left / 60000));
  const late = left < 0;
  const minute = !late && left <= HOUR_MS;
  ring.classList.toggle("is-min", minute);
  ring.classList.toggle("is-late", late);
  ring.style.setProperty("--p", late ? "0" : minute ? ((left / HOUR_MS) * 100).toFixed(2) : String(ringPct(start, nowMs)));
  ring.style.setProperty("--rc", minute ? "var(--color-late)" : "var(--lane-color, var(--color-sched))");
  const b = ring.querySelector("b"), sm = ring.querySelector("small");   // 방송 중 링과 같은 2단: 「n시간 / 시작까지」(1시간 이내는 「n분」), 지나면 「지각」
  const [lateB, lateS] = card.dataset.king ? KING_RING_LATE : ["지각", ""];
  b.textContent = late ? lateB : minute ? `${min}분` : `${Math.floor(min / 60)}시간`;
  sm.textContent = late ? lateS : "시작까지";
  card.classList.toggle("tcard--soon", !late && left < SOON_MS);
}

/* 방송 중 경과 링: 12시부터 시계방향으로 60분간 채워지고, 다음 60분은 같은 방향으로 비워진다(2시간 주기 반복).
   글자는 시작 후 경과 분 + "방송중". --p = 현재 60분 구간 안 진행률(0~100) */
function paintCycleRing(ring, min) {
  const cycle = Math.floor(min / 60);
  ring.classList.toggle("is-fill", cycle % 2 === 0);
  ring.classList.toggle("is-erase", cycle % 2 === 1);
  ring.style.setProperty("--p", (((min - cycle * 60) / 60) * 100).toFixed(2));
  const b = ring.querySelector("b");
  if (b) b.textContent = `${Math.floor(min)}분`;
}
function updateLiveRing(card, nowMs) {
  const start = Number(card.dataset.start);
  const ring = card.querySelector(".tcard__ring--live");
  if (!ring || !isFinite(start)) return;
  paintCycleRing(ring, Math.max(0, (nowMs - start) / 60000));
}

function todayCard(entry, state, ctx, big, laneKey) {
  const it = entry.item;
  const a = el("a", `tcard tcard--${state}` + (big ? " tcard--big" : ""));
  const url = hasVideo(it) && it.url ? it.url : (ctx.channels[it.channel_key] || {}).channel_url || "#";
  a.href = url; a.target = "_blank"; a.rel = "noopener";
  a.dataset.start = String(entry.start);
  a.dataset.iso = new Date(entry.start).toISOString();
  a.dataset.state = state;

  const th = thumbEl(it, "tcard__th", ctx);
  if (isCollab(it)) {
    // 참여 멤버 아이콘: 이 레인의 본인은 빼고, 하단 선택 아이콘과 같은 고정 순서(아라레-유노-노노카-리츠-미야코).
    // 본인 외 참여자를 알 수 없으면(합동인데 게스트 미상) 빈 알약을 만들지 않는다.
    const present = new Set(itemKeys(it, ctx.order));
    const others = ctx.order.filter((k) => present.has(k) && k !== laneKey);
    if (others.length) {
      const nm = el("div", "tcard__collab", "");
      const faces = el("span", "tt-faces");
      for (const k of others) {
        const f = el("span", "tt-face");
        const c = ctx.channels[k];
        if (c && c.avatar) f.style.backgroundImage = `url("${avatarSized(c.avatar, 176)}")`;
        faces.appendChild(f);
      }
      nm.appendChild(faces);                    // 아이콘만 (이름 글자 없음). 합동 글자는 날짜 옆 태그
      nm.setAttribute("role", "img");
      nm.setAttribute("aria-label", `합동 · ${others.map((k) => shortName(ctx.channels[k])).join(", ")}`);
      th.appendChild(nm);
    }
  }
  // 이미지 오른쪽 아래 알약: [🔒 회원 전용] 왼쪽에 [LIVE | 종료]
  const pills = el("div", "tcard__pills");
  if (it.membership) {
    const lock = el("div", "tcard__pill tcard__pill--lock", "🔒");
    lock.setAttribute("role", "img");
    lock.setAttribute("aria-label", "회원 전용");
    pills.appendChild(lock);
  }
  if (state === "ended") pills.appendChild(el("div", "tcard__pill tcard__pill--end", "종료"));
  else if (state === "live") pills.appendChild(el("div", "tcard__pill tcard__pill--live", "LIVE"));
  if (pills.children.length) th.appendChild(pills);
  a.appendChild(th);

  const body = el("div", "tcard__body");
  // 날짜·시각은 모든 상태에서 같은 굵은 글씨. 상태(LIVE · 종료)는 이미지 알약, 남은 시간은 링이 보여 주므로 글자로 다시 쓰지 않는다.
  const when = el("div", "tcard__when");
  if (state === "ended" && entry.end) {
    // [날짜] [시작~종료] — 방송 시간은 글자가 아니라 오른쪽 링이 보여 준다
    const next = ymd(entry.end) !== ymd(entry.start) ? " (익일)" : "";
    when.appendChild(el("b", "", formatKST(a.dataset.iso).slice(0, 5)));
    when.appendChild(el("b", "", `${hm(entry.start)}~${hm(entry.end)}${next}`));
  } else {
    when.appendChild(el("b", "", formatKST(a.dataset.iso)));
  }
  // 태그는 합동 · 회원 전용만 (종료 · 예고 태그는 쓰지 않음). 모자라면 다음 줄로 내려간다.
  for (const t of tagsFor(entry, state)) {
    if (t.classList.contains("tt-tag--collab") || t.classList.contains("tt-tag--mem")) when.appendChild(t);
  }
  const main = el("div", "tcard__main");
  main.appendChild(when);
  main.appendChild(el("div", "tcard__ti", titleText(it, ctx)));
  body.appendChild(main);
  if (state === "upcoming") {                 // 남은 시간 링은 이미지가 아니라 제목 영역 오른쪽에
    const ring = el("div", "tcard__ring tcard__ring--up");
    const t = el("span");
    t.append(el("b"), el("small"));
    ring.appendChild(t);
    body.appendChild(ring);
  } else if (state === "live" || (state === "ended" && entry.end)) {
    // 방송 중 = 경과 링 ("N분" + "방송중"), 종료 = 끝난 순간에 멈춘 같은 링 (회색, "N분" + "방송")
    const ring = el("div", "tcard__ring tcard__ring--live" + (state === "ended" ? " tcard__ring--ended" : ""));
    const t = el("span");
    t.append(el("b"), el("small", "", state === "ended" ? "방송" : "방송중"));
    ring.appendChild(t);
    body.appendChild(ring);
    if (state === "ended") paintCycleRing(ring, (entry.end - entry.start) / 60000);
  }
  a.appendChild(body);
  if (laneKey === KING_KEY) decorateCard(a, th, main, entry, state);   // (v4.3.1) 노노카 레인의 카드에만
  if (state === "upcoming") updateRing(a, ctx.nowMs);
  else if (state === "live") updateLiveRing(a, ctx.nowMs);
  return a;
}

export function buildTodayCards(ctx, key, opts = {}) {
  const has = (e) => itemKeys(e.item, ctx.order).includes(key);
  const mE = ctx.ended.filter(has), mL = ctx.live.filter(has), mU = ctx.upcoming.filter(has);
  const mT = (ctx.tomorrow || []).filter(has);   // (v4.9.6) 내일 예고 — 오늘 예정 뒤에 구분선을 두고 잇는다
  const sec = el("section", "tt-today");
  const head = el("div", "tt__head");
  head.appendChild(el("h2", "tt__title", "오늘 예고"));
  head.appendChild(el("span", "tt__meta",
    // 카드 보기(opts.compact)는 날짜 · 구간이 보드 머리줄에 이미 있어 건수만 — 5열이라 좁다
    (opts.compact ? "" : `${mdw(ctx.ds)} 04:00 ~ 익일 04:00 · `) + `예정 ${mU.length}` + (mL.length ? ` · 방송 중 ${mL.length}` : "") + (mE.length ? ` · 종료 ${mE.length}` : "") + (mT.length ? ` · 내일 ${mT.length}` : "")));
  sec.appendChild(head);
  const all = [
    ...mE.map((entry) => ({ entry, state: "ended" })),
    ...mL.map((entry) => ({ entry, state: "live" })),
    ...mU.map((entry) => ({ entry, state: "upcoming" })),
  ];
  if (!all.length && !mT.length) { sec.appendChild(el("div", "tt-today__none", "오늘 남은 예고가 없습니다.")); return sec; }
  if (!all.length) sec.appendChild(el("div", "tt-today__none", "오늘 남은 예고가 없습니다."));   // (v4.9.6) 오늘은 비고 내일만 있는 경우
  const stack = el("div", "tt-today__stack");
  const bigIdx = all.findIndex((g) => g.state !== "ended");
  all.forEach((g, i) => stack.appendChild(todayCard(g.entry, g.state, ctx, i === bigIdx, key)));
  if (mT.length) {
    stack.appendChild(el("div", "tt-today__div", `내일 예고 · ${mdw(ctx.de)} 04:00 ~`));   // (v4.9.6) 내일 구분선
    // 오늘 종료 외 카드가 없으면 내일 첫 카드가 big (bigIdx < 0)
    mT.forEach((entry, i) => stack.appendChild(todayCard(entry, "upcoming", ctx, bigIdx < 0 && i === 0, key)));
  }
  sec.appendChild(stack);
  return sec;
}

/* ── 이후 예고 펼치기 버튼 ─────────────────────────────────────────── */
export function buildFoldButton(counts, ctx, opts = {}) {
  const btn = el("button", "tt-fold");
  btn.type = "button";
  btn.appendChild(el("i", "tt-fold__tri"));
  const total = counts.total;
  btn.appendChild(el("span", "tt-fold__open", opts.summary ? "이후 예고 펼치기" : `이후 예고 ${total}건 펼치기`));   // (v4.9.6) 표 보기는 건수를 오른쪽 요약에
  btn.appendChild(el("span", "tt-fold__close", "이후 예고 접기"));
  if (opts.summary) {   // (v4.9.6) 표 보기 — 「이번주 N · 먼 미래 M」 (멤버별 건수 대신)
    btn.appendChild(el("span", "tt-fold__cn", opts.summary));
  } else if (opts.perMember) {
    const cn = el("span", "tt-fold__cn");
    for (const key of ctx.order) {
      const ch = ctx.channels[key];
      if (!ch) continue;
      const s = el("span");
      const av = el("span", "tt-face");
      if (ch.avatar) av.style.backgroundImage = `url("${avatarSized(ch.avatar, 176)}")`;
      s.append(av, document.createTextNode(String(counts.byKey[key] || 0)));
      cn.appendChild(s);
    }
    btn.appendChild(cn);
  }
  return btn;
}

/* ── 이후 예고 표 (PC 표 보기 · v4.9.6) ─────────────────────────────────
   2열: 왼쪽 「이번주」(일 ~ 토 7줄 · 줄마다 점), 오른쪽 「먼 미래」(날짜 줄 · 날짜 미정 줄). 점 = 방송 하나, 합동은 참여 멤버 색으로 나뉜다. */
const WK_DOW = ["일", "월", "화", "수", "목", "금", "토"];
const pad2 = (n) => String(n).padStart(2, "0");
const kParts = (ms) => new Date(ms + KST_OFFSET_MS);   // UTC 필드 = KST 달력 값
const kMD = (ms) => { const d = kParts(ms); return `${pad2(d.getUTCMonth() + 1)}/${pad2(d.getUTCDate())}`; };
const kDow = (ms) => WK_DOW[kParts(ms).getUTCDay()];

/* 점 하나 — 상태 클래스(is-ended · is-live · is-tbd), 조각 = 참여 멤버(data-channel → render.js 가 --lane-color 를 채운다) */
function wkDot(entry, ctx) {
  const it = entry.item;
  const b = el("button", "wk2__dot");
  b.type = "button";
  b.setAttribute("aria-haspopup", "dialog");
  const tbd = !!it.time_tbd || !isFinite(entry.start);
  if (entry.state === "ended") b.classList.add("is-ended");
  else if (entry.state === "live") b.classList.add("is-live");
  if (tbd) b.classList.add("is-tbd");
  const keys = entry.keys.length ? entry.keys : [it.channel_key];
  const shape = el("span", "wk2__shape");   // (v4.9.6) 보이는 점(합동 = 알약). 합동 테두리는 이 모양에 두른다
  for (const k of keys) {
    const seg = el("span", "wk2__seg");
    seg.dataset.channel = k;
    shape.appendChild(seg);
  }
  b.appendChild(shape);
  if (isCollab(it)) b.classList.add("is-collab");   // (v4.9.6) 예고 카드 · 태그와 같은 보라(--color-collab) 테두리
  if (it.membership) {                               // (v4.9.6) 회원 전용 = 점 오른쪽 아래 작은 자물쇠
    const NS = "http://www.w3.org/2000/svg";
    const lock = document.createElementNS(NS, "svg");
    lock.setAttribute("class", "wk2__lock");
    lock.setAttribute("viewBox", "0 0 10 10");
    lock.setAttribute("aria-hidden", "true");
    const body = document.createElementNS(NS, "rect");
    body.setAttribute("x", "2"); body.setAttribute("y", "4.5"); body.setAttribute("width", "6"); body.setAttribute("height", "4.5"); body.setAttribute("rx", "1");
    const arc = document.createElementNS(NS, "path");
    arc.setAttribute("d", "M3.3 4.6V3.4a1.7 1.7 0 0 1 3.4 0v1.2");
    lock.append(body, arc);
    b.appendChild(lock);
  }
  const names = keys.map((k) => shortName(ctx.channels[k])).join(", ");
  b.setAttribute("aria-label", `${tbd ? "시각 미정" : hm(entry.start)} ${names}${it.membership ? " · 회원 전용" : ""} · ${titleText(it, ctx)}`);
  wirePop(b, entry, entry.state, ctx, it.channel_key, true);
  return b;
}

/* 줄 하나 = 왼쪽 날짜 칸 + 오른쪽 점 칸. 점이 없으면 빈 칸 */
function wkRow(dateNode, entries, cls, ctx) {
  const row = el("div", "wk2__row" + (cls ? ` ${cls}` : ""));
  row.appendChild(dateNode);
  const dots = el("div", "wk2__dots");
  for (const e of entries) dots.appendChild(wkDot(e, ctx));
  row.appendChild(dots);
  return row;
}

export function buildLaterTables(ctx, plan) {
  const wrap = el("div", "tt-later");   // 펼치기 · 접기 애니메이션이 이 이름을 쓴다 (render.js toggleLater)
  const grid = el("div", "wk2");

  // 이번주 — 일요일 ~ 토요일 7줄. 지난 줄은 흐리게, 오늘 줄은 「오늘」 알약
  const wk = el("section", "wk2__panel wk2__panel--week");
  const hd = el("div", "wk2__hd");
  const last = plan.we - DAY_MS;
  hd.append(el("b", "", "이번주"), el("span", "", `${kMD(plan.ws)}(${kDow(plan.ws)}) ~ ${kMD(last)}(${kDow(last)})`));
  wk.appendChild(hd);
  const tbl = el("div", "wk2__tbl");
  plan.days.forEach((d, i) => {
    const date = el("div", "wk2__date");
    date.append(el("b", "", kMD(d.ds)), el("span", "", kDow(d.ds)));
    if (i === plan.today) date.appendChild(el("span", "wk2__now", "오늘"));
    tbl.appendChild(wkRow(date, d.entries, i < plan.today ? "is-past" : i === plan.today ? "is-today" : "", ctx));
  });
  wk.appendChild(tbl);

  // 먼 미래 — 날짜별 줄(D-n 표시), 마지막에 날짜 미정 줄. 0건이면 안내 한 줄
  const far = el("section", "wk2__panel wk2__panel--far");
  const counts = laterCounts(plan);
  const fhd = el("div", "wk2__hd");
  fhd.append(el("b", "", "먼 미래"), el("span", "", `${counts.rest}건`));
  far.appendChild(fhd);
  if (!counts.rest) {
    far.appendChild(el("div", "wk2__none", "먼 미래 예고 없음"));
  } else {
    const ftbl = el("div", "wk2__tbl");
    const todayStart = plan.ws + plan.today * DAY_MS;
    const nowY = kParts(todayStart).getUTCFullYear();
    for (const f of plan.far) {
      const date = el("div", "wk2__date");
      const y = kParts(f.ds).getUTCFullYear();
      date.append(
        el("b", "", `${y === nowY ? "" : `${y}/`}${kMD(f.ds)}`),
        el("span", "", kDow(f.ds)),
        el("span", "wk2__dn", `D-${Math.round((f.ds - todayStart) / DAY_MS)}`),
      );
      ftbl.appendChild(wkRow(date, f.entries, "", ctx));
    }
    if (plan.undated.length) ftbl.appendChild(wkRow(el("div", "wk2__date", "날짜 미정"), plan.undated, "", ctx));
    far.appendChild(ftbl);
  }

  grid.append(wk, far);
  wrap.appendChild(grid);
  return wrap;
}

/* ── 틱 · 마키 ─────────────────────────────────────────────────────── */
export function tickTimetable(boardEl, nowMs) {
  const grid = boardEl.querySelector(".tt__grid");
  if (grid) positionNow(grid, nowMs);
  for (const card of boardEl.querySelectorAll(".tcard--upcoming")) updateRing(card, nowMs);
  for (const card of boardEl.querySelectorAll(".tcard--live")) updateLiveRing(card, nowMs);
  const de = boardEl.__ttDe;
  const roll = typeof de === "number" && nowMs >= de;
  if (roll) ttDay = 0;   // (v4.9.6) 오늘 구간이 끝났으면 표는 다시 오늘 예고로
  return roll;
}

/* 제목이 블록 폭을 넘치면 한 줄로 무한히 흐른다 (복제본을 붙이고 -50% 이동). 속도는 글자 길이에 비례. */
export function applyTimetableMarquees(boardEl) {
  for (const n of boardEl.querySelectorAll(".tt-blk__n")) {
    const trk = n.firstElementChild;
    if (!trk) continue;
    while (trk.children.length > 1) trk.lastElementChild.remove();
    n.classList.remove("is-marquee");
    const sp = trk.firstElementChild;
    if (n.clientWidth > 24 && sp.scrollWidth - 40 > n.clientWidth) {
      const dup = sp.cloneNode(true);
      dup.setAttribute("aria-hidden", "true");
      trk.appendChild(dup);
      n.classList.add("is-marquee");
      trk.style.setProperty("--dur", `${Math.max(8, sp.offsetWidth / 45)}s`);
    }
  }
}
