// timetable.js — (v4.1.0) 오늘 타임테이블(PC) · 오늘 카드(모바일) · 이후 예고 펼치기 버튼.
// 예고판(5열 레인 보드)의 "오늘/7일 이내/7일 이후 버킷 + ON-AIR 영역"을 대체한다.
// 오늘 = KST 06:00 ~ 익일 06:00 (모니터링 하루 경계와 같음). 그 밖의 예고는 "이후 예고"로 펼친다.
// 데이터는 textContent/createElement 로만 주입(XSS 방어, innerHTML 금지) — render.js 와 같은 규칙.
//
//  dayWindow(nowMs)                    → { ds, de }  오늘 구간(ms)
//  classify(items, archive, nowMs, order) → { ds, de, live, ended, upcoming, later }
//  buildTimetable(ctx)                 → PC 편성 레일 (편지 배지 자리 = 왼쪽 칸의 .lane__avatar)
//  buildTodayCards(ctx, key)           → 모바일 오늘 카드(카운트다운 링)
//  buildFoldButton(counts, ctx)        → "이후 예고 N건 펼치기" 버튼 (상태는 #board 클래스로 — 캐러셀 클론에도 적용)
//  tickTimetable(boardEl, nowMs)       → 1분 틱: 지금 선 · 링 갱신. 오늘 구간이 끝났으면 true(재렌더 필요)
//  applyTimetableMarquees(boardEl)     → 블록 제목이 넘치면 한 줄 무한 흐름
//  closeCardPop()                      → 블록 카드 팝업 닫기

import { formatKST } from "./time.js";

const HOUR_MS = 3600000;
const DAY_MS = 86400000;
const KST_OFFSET_MS = 9 * HOUR_MS;
const DAY_START_HOUR = 6;                  // monitor_log.DAY_START_HOUR 와 같은 하루 경계
const LATE_ENDED_MIN = 10 * 60000;         // 종료 기록으로 인정하는 최소/최대 방송 길이
const LATE_ENDED_MAX = 12 * HOUR_MS;
const TRACK_PX = 888;                      // 블록 위치·폭을 환산하는 기준 트랙 폭 (실제 폭에 비례)
const W_FIXED = 210;                       // 종료 시각을 모르는 블록의 고정 폭
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
const relShort = (min) => (min < 60 ? `${min}분` : `${(min / 60).toFixed(min % 60 ? 1 : 0)}h`);
function durLabel(ms) {
  const m = Math.round(ms / 60000);
  return m < 60 ? `${m}분` : `${Math.floor(m / 60)}시간${m % 60 ? ` ${m % 60}분` : ""}`;
}

/* ── 오늘 구간 ────────────────────────────────────────────────────── */
export function dayWindow(nowMs) {
  const k = nowMs + KST_OFFSET_MS;
  const d = new Date(k);
  let base = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate(), DAY_START_HOUR);
  if (k < base) base -= DAY_MS;
  const ds = base - KST_OFFSET_MS;
  return { ds, de: ds + DAY_MS };
}

const itemMs = (iso) => (iso ? Date.parse(iso) : NaN);

/**
 * 아이템을 오늘 구간 기준으로 나눈다.
 *  live / ended / upcoming = 타임테이블에 놓이는 항목 { item, start, end }
 *  later = 이후 예고(구간 밖·시각 미정) 원본 아이템 목록 (시작 시각순)
 * ended = preview.json 의 end 상태 + preview_archive.json 에서 오늘 06:00 이후 시작해 이미 끝난 방송.
 */
export function classify(items, archiveItems, nowMs, order) {
  const { ds, de } = dayWindow(nowMs);
  const live = [], ended = [], upcoming = [], later = [];
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
      if (item.time_tbd || !isFinite(s) || s >= de) later.push(item);
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
  live.sort(byStart); ended.sort(byStart); upcoming.sort(byStart);
  later.sort((a, b) => {
    const x = itemMs(a.scheduled_start), y = itemMs(b.scheduled_start);
    if (!isFinite(x)) return isFinite(y) ? 1 : 0;
    if (!isFinite(y)) return -1;
    return x - y;
  });
  return { ds, de, live, ended, upcoming, later };
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

function rangeLabel(entry, state) {
  if (state === "live") return `LIVE · ${hm(entry.start)} 시작`;
  if (entry.end) return `${hm(entry.start)} ~ ${hm(entry.end)}${ymd(entry.end) !== ymd(entry.start) ? " (익일)" : ""} · ${durLabel(entry.end - entry.start)}`;
  return hm(entry.start);
}

function showCardPop(entry, state, owner, pin, ctx) {
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
  body.appendChild(el("div", "tt-pop__rg", rangeLabel(entry, state)));
  body.appendChild(el("div", "tt-pop__ti", titleText(it, ctx)));
  if (url) {
    const btn = el("a", "tt-pop__btn", "▶ YouTube에서 보기");
    btn.href = url; btn.target = "_blank"; btn.rel = "noopener";
    body.appendChild(btn);
  } else {
    body.appendChild(el("span", "tt-pop__none", "아직 영상 링크가 없습니다"));
  }
  cpop.appendChild(body);
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
function blockEl(entry, state, ctx, geo) {
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
  if (state === "upcoming") {
    const min = Math.max(0, Math.round((entry.start - ctx.nowMs) / 60000));
    head.appendChild(el("span", "tt-blk__rel", entry.start >= ctx.nowMs ? relShort(min) : "지각"));
  }
  for (const t of tagsFor(entry, state)) head.appendChild(t);
  tx.appendChild(head);
  const n = el("div", "tt-blk__n");
  const trk = el("span", "tt-blk__trk");
  trk.appendChild(el("span", "", titleText(it, ctx)));
  n.appendChild(trk);
  tx.appendChild(n);
  b.appendChild(tx);

  b.addEventListener("click", (e) => { e.stopPropagation(); showCardPop(entry, state, b, true, ctx); });
  b.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); showCardPop(entry, state, b, true, ctx); }
  });
  b.addEventListener("mouseenter", () => { clearTimeout(cpopTimer); showCardPop(entry, state, b, false, ctx); });
  b.addEventListener("mouseleave", () => {
    if (!cpopPinned) { clearTimeout(cpopTimer); cpopTimer = setTimeout(closeCardPop, 150); }
  });
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

export function buildTimetable(ctx) {
  wirePopOnce();
  const sec = el("section", "tt");
  const nLive = ctx.live.length, nEnded = ctx.ended.length;
  const head = el("div", "tt__head");
  head.appendChild(el("h2", "tt__title", "오늘 예고"));
  head.appendChild(el("span", "tt__meta",
    `${mdw(ctx.ds)} 06:00 ~ 익일 06:00 · 예정 ${ctx.upcoming.length}건` +
    (nLive ? ` · 방송 중 ${nLive}건` : "") + (nEnded ? ` · 종료 ${nEnded}건` : "")));
  sec.appendChild(head);

  const scroll = el("div", "tt__scroll");
  const grid = el("div", "tt__grid");
  grid.__tt = { ds: ctx.ds, de: ctx.de };

  // 시간축: 06:00 부터 3시간마다. 자정은 강조 + 익일 날짜
  grid.appendChild(el("div"));
  const axis = el("div", "tt__axis");
  for (let h = 0; h <= 24; h += 3) {
    const t = ctx.ds + h * HOUR_MS;
    const tick = el("div", "tt__tick" + (h === 0 ? " is-first" : h === 24 ? " is-last" : "") + (h === 18 ? " is-midnight" : ""));
    tick.style.left = `${(h / 24) * 100}%`;
    tick.appendChild(el("b", "", hm(t)));
    const sub = h === 0 ? mdw(t) : h === 18 ? `자정 · 익일 ${mdw(t)}` : h === 24 ? `익일 ${mdw(t)}` : "";
    if (sub) tick.appendChild(document.createTextNode(sub));
    axis.appendChild(tick);
  }
  grid.appendChild(axis);

  const all = [
    ...ctx.ended.map((entry) => ({ entry, state: "ended" })),
    ...ctx.live.map((entry) => ({ entry, state: "live" })),
    ...ctx.upcoming.map((entry) => ({ entry, state: "upcoming" })),
  ];
  for (const key of ctx.order) {
    const ch = ctx.channels[key];
    if (!ch) continue;
    const mine = all.filter(({ entry }) => itemKeys(entry.item, ctx.order).includes(key));

    const lane = el("section", "lane tt__lane");
    lane.dataset.channel = key;
    const header = el("header", "lane__header tt__who");
    const avatar = el("span", "lane__avatar");
    if (ch.avatar) avatar.style.backgroundImage = `url("${avatarSized(ch.avatar, 176)}")`;
    const nm = el("span", "tt__nm");
    nm.append(el("b", "", shortName(ch)), el("small", "", `${mine.length}건`));
    header.append(avatar, nm);
    lane.appendChild(header);
    grid.appendChild(lane);

    const track = el("div", "tt__track");
    track.dataset.channel = key;               // sampleLaneColor 가 --lane-color 를 채운다
    if (!mine.length) track.appendChild(el("div", "tt__empty", "오늘 예정 없음"));
    for (const g of layoutRow(mine, ctx)) track.appendChild(blockEl(g.entry, g.state, ctx, g));
    grid.appendChild(track);
  }

  // 지금 선 · 지난 구간 음영 · 자정 점선
  const ov = el("div", "tt__ov");
  const past = el("div", "tt__past");
  const now = el("div", "tt__now");
  const nowTag = el("div", "tt__nowtag", `지금 ${hm(ctx.nowMs)}`);
  ov.append(past, now, nowTag, el("div", "tt__mid"));
  grid.appendChild(ov);
  scroll.appendChild(grid);
  sec.appendChild(scroll);
  positionNow(grid, ctx.nowMs);

  const legend = el("div", "tt__legend");
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
  sec.appendChild(legend);
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
function updateRing(card, nowMs) {
  const start = Number(card.dataset.start);
  const ring = card.querySelector(".tcard__ring");
  if (!ring || !isFinite(start)) return;
  const min = Math.max(0, Math.round((start - nowMs) / 60000));
  ring.style.setProperty("--p", String(ringPct(start, nowMs)));
  ring.style.setProperty("--rc", min < 60 && start >= nowMs ? "var(--color-late)" : "var(--lane-color, var(--color-sched))");
  ring.querySelector("span").textContent = start >= nowMs ? relShort(min) : "지각";
  card.classList.toggle("tcard--soon", start >= nowMs && start - nowMs < SOON_MS);
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
    const ring = el("div", "tcard__ring");
    ring.appendChild(el("span"));
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
  if (state === "upcoming") updateRing(a, ctx.nowMs);
  else if (state === "live") updateLiveRing(a, ctx.nowMs);
  return a;
}

export function buildTodayCards(ctx, key) {
  const has = (e) => itemKeys(e.item, ctx.order).includes(key);
  const mE = ctx.ended.filter(has), mL = ctx.live.filter(has), mU = ctx.upcoming.filter(has);
  const sec = el("section", "tt-today");
  const head = el("div", "tt__head");
  head.appendChild(el("h2", "tt__title", "오늘 예고"));
  head.appendChild(el("span", "tt__meta",
    `${mdw(ctx.ds)} 06:00 ~ 익일 06:00 · 예정 ${mU.length}` + (mL.length ? ` · 방송 중 ${mL.length}` : "") + (mE.length ? ` · 종료 ${mE.length}` : "")));
  sec.appendChild(head);
  const all = [
    ...mE.map((entry) => ({ entry, state: "ended" })),
    ...mL.map((entry) => ({ entry, state: "live" })),
    ...mU.map((entry) => ({ entry, state: "upcoming" })),
  ];
  if (!all.length) { sec.appendChild(el("div", "tt-today__none", "오늘 남은 예고가 없습니다.")); return sec; }
  const stack = el("div", "tt-today__stack");
  const bigIdx = all.findIndex((g) => g.state !== "ended");
  all.forEach((g, i) => stack.appendChild(todayCard(g.entry, g.state, ctx, i === bigIdx, key)));
  sec.appendChild(stack);
  return sec;
}

/* ── 이후 예고 펼치기 버튼 ─────────────────────────────────────────── */
export function buildFoldButton(counts, ctx, opts = {}) {
  const btn = el("button", "tt-fold");
  btn.type = "button";
  btn.appendChild(el("i", "tt-fold__tri"));
  const total = counts.total;
  btn.appendChild(el("span", "tt-fold__open", `오늘 이후 예고 ${total}건 펼치기`));
  btn.appendChild(el("span", "tt-fold__close", "오늘 이후 예고 접기"));
  if (opts.perMember) {
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

/* ── 틱 · 마키 ─────────────────────────────────────────────────────── */
export function tickTimetable(boardEl, nowMs) {
  const grid = boardEl.querySelector(".tt__grid");
  if (grid) positionNow(grid, nowMs);
  for (const card of boardEl.querySelectorAll(".tcard--upcoming")) updateRing(card, nowMs);
  for (const card of boardEl.querySelectorAll(".tcard--live")) updateLiveRing(card, nowMs);
  const de = boardEl.__ttDe;
  return typeof de === "number" && nowMs >= de;
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
