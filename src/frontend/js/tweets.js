// tweets.js — 멤버 트윗 시트 (self-reply 핫픽스, ui_spec.md).
// 보드에서 멤버 아바타 · 이름 · 트윗 배지를 누르면 「트윗 시트」가 열린다. 폰 = 아래에서 올라오는 시트(끌어 닫기), PC = 가운데 뜨는 팝업 보드.
// 시트는 하나만 만들어 두고 JS 가 채운다(createElement · textContent 만 — innerHTML 로 데이터를 넣지 않는다).
// 순수 로직(글타래 묶기 · 첨부 문구 · 색 · 시각 표기 · 새 글 자리)은 tweetlogic.js.
//
//  renderTweets(boardEl, data)  — 폴링마다. data 를 캐시하고 배지 · 열린 시트를 갱신(표시 서명이 같으면 시트를 다시 그리지 않는다).
//  reapplyTweets(boardEl)       — renderBoard 직후. 캐시된 data 로 배지만 다시 붙인다.
//  makeXCard · loadXCards · stopXCards — 소식 팝업(notices.js)이 쓰는 X 공식 카드. 트윗 시트의 원문 면도 같은 카드를 쓴다.
//
// 계약: tweets[ck] = [ <메시지>, … ] 최신이 뒤(계약 I). 메시지별 expires_at 이 지난 것은 뺀다. reply_to_id 는 자기 답글의 원글 id.
// 읽음 = 시트를 닫을 때 · 멤버를 바꿀 때(mew:twread, 4일 보존). 면 저장값 = mew:tllang(ko · orig). 엿보기 횟수 = mew:twpeek.
// (v4.9.1) PC 팝업 = 머리 줄로 옮기기 · 위아래 가장자리로 대칭 높이 조절(mew:twh) · X 카드 덮개(카드 위에서 밀기).
//   열린 시트에 새 글이 오면 새 글만 끼운다(_patchFeed) — 맨 아래였으면 아래에서 올라오고, 아니면 ↓ 동그라미(.tws__fab).
// (v4.9.3) 두 면 겹쳐 밀기 · 번역 면에 사진 · 영상 · 인용(X 카드와 같은 뼈대 · 치수로 위치 맞춤) · 시각은 말풍선 바닥 줄 한 번 ·
//   날짜 구분선 · 열면 맨 아래(멤버별 자리 기억) · 올리면 ↓ 동그라미. 영상 칸만 누른다(원문 카드로 + 같은 칸 글로우).

import { FALLBACK_CHANNELS, FALLBACK_CHANNEL_ORDER } from "./config.js";
import { THEME_EVENT, currentTheme } from "./theme.js";
import { wireSheetDrag, vibrate } from "./sheetdrag.js";
import * as L from "./tweetlogic.js";

const RKEY = "mew:twread";
const TLANG_KEY = "mew:tllang";
const PEEK_KEY = "mew:twpeek";
const READ_TTL_MS = 4 * 24 * 3600 * 1000;   // 읽음 기록 보존 4일(트윗 수명 48h 보다 넉넉히)
const MAX_THREAD = 50;                       // 노출 상한(백엔드 xtweet.MAX_THREAD 와 같게)
const PEEK_MAX = 2;                          // 엿보기는 처음 두 번만
const HKEY = "mew:twh";                      // (v4.9.1) PC 팝업 높이(px) — 사용자가 가장자리를 끌어 정한 값
const MIN_H = 360;                           // PC 팝업 최소 높이(창이 더 작으면 창 - 16px)
const EASE = "cubic-bezier(0.2, 0.8, 0.2, 1)";
const SPRING = "cubic-bezier(0.25, 1.4, 0.45, 1)";   // 놓을 때만 쓰는 튕김
const NS = "http://www.w3.org/2000/svg";

const EMBED_ORIGINS = ["https://platform.twitter.com", "https://platform.x.com"];
const CARD_TIMEOUT_MS = 15000;   // 이 안에 렌더링 신호가 없으면 「X에서 보기」 링크를 띄운다

const _st = { data: null, board: null, wired: false };
let S = null;                    // 트윗 시트 상태(처음 열 때 한 번 만든다)
let _drag = null;                // 면 끌기 중인 컨트롤러(한 번에 하나) — window 리스너는 한 번만 단다
let _mdrag = null;               // 멤버 칩 줄 끌기
let _globalWired = false;

/* ── DOM 헬퍼 (innerHTML 없음) ─────────────────────────────────────── */
function _el(tag, o, kids) {
  const e = document.createElement(tag);
  if (o) {
    if (o.cls) e.className = o.cls;
    if (o.text != null) e.textContent = o.text;
    if (o.id) e.id = o.id;
    if (o.attrs) for (const k of Object.keys(o.attrs)) e.setAttribute(k, o.attrs[k]);
    if (o.on) for (const k of Object.keys(o.on)) e.addEventListener(k, o.on[k]);
  }
  for (const c of [].concat(kids || [])) if (c) e.append(c);
  return e;
}
/** 아이콘: paths = 선 그리기(stroke) 또는 채우기(fill: true). viewBox 는 호출하는 쪽이 정한다 */
function _icon(vb, paths, fill) {
  const s = document.createElementNS(NS, "svg");
  s.setAttribute("viewBox", vb);
  s.setAttribute("aria-hidden", "true");
  s.setAttribute("focusable", "false");
  for (const d of paths) {
    const p = document.createElementNS(NS, "path");
    p.setAttribute("d", d);
    if (fill) p.setAttribute("fill", "currentColor");
    else {
      p.setAttribute("fill", "none");
      p.setAttribute("stroke", "currentColor");
      p.setAttribute("stroke-width", "1.4");
      p.setAttribute("stroke-linecap", "round");
      p.setAttribute("stroke-linejoin", "round");
    }
    s.append(p);
  }
  return s;
}
const IC = {
  reply: () => _icon("0 0 12 12", ["M3 1.5v4.2a2 2 0 0 0 2 2h4.2", "M7.2 5.5l2 2.2-2 2.2"]),
  photo: () => _icon("0 0 14 14", ["M2 4.5A1.5 1.5 0 0 1 3.5 3h1l.8-1h3.4l.8 1h1A1.5 1.5 0 0 1 12 4.5v5A1.5 1.5 0 0 1 10.5 11h-7A1.5 1.5 0 0 1 2 9.5z", "M9 7a2 2 0 1 1-4 0 2 2 0 0 1 4 0z"]),
  video: () => _icon("0 0 14 14", ["M2 4a1.5 1.5 0 0 1 1.5-1.5h5A1.5 1.5 0 0 1 10 4v6a1.5 1.5 0 0 1-1.5 1.5h-5A1.5 1.5 0 0 1 2 10z", "M10 6l2.5-1.5v5L10 8"]),
  x: () => _icon("0 0 24 24", ["M18.9 2.6h3.3l-7.2 8.2 8.5 11.3h-6.7l-5.2-6.8-6 6.8H1.3l7.7-8.8L.7 2.6h6.9l4.7 6.2 5.6-6.2Zm-1.2 17.7h1.9L7.2 4.4H5.2l12.5 15.9Z"], true),
  close: () => _icon("0 0 20 20", ["M5 5l10 10M15 5L5 15"]),
  down: () => _icon("0 0 20 20", ["M10 4v11", "M5 10.5l5 5 5-5"]),
  play: () => _icon("0 0 14 14", ["M4 2.2v9.6L11.8 7z"], true),
};
const _reduce = () => !!(window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches);
const _mobile = () => !!(window.matchMedia && window.matchMedia("(max-width: 767px)").matches);
/** 숫자 배지가 늘 때 한 번 톡 커졌다 돌아온다 */
const _pop = (el) => {
  if (el && el.animate && !_reduce()) el.animate([{ transform: "scale(1)" }, { transform: "scale(1.4)", offset: 0.35 }, { transform: "scale(1)" }], { duration: 380, easing: "cubic-bezier(0.3, 1.5, 0.5, 1)" });
};

/* ── 계약 I 하위호환: tweets[ck] → 메시지 배열 ───────────────────── */
function _list(v) {
  if (Array.isArray(v)) return v.filter((m) => m && m.text);
  if (v && typeof v === "object" && v.text) return [v];
  return [];
}

/* ── 읽음 상태 (뷰어별 localStorage) ─────────────────────────────────
   { id: readAtEpochMs }. 시간 기반으로만 정리한다 — "지금 안 보이는 id" 를 즉시 지우면
   폴링이 잠깐 빈 tweets.json 을 받았을 때 읽음 기록이 통째로 날아간다. */
function _readMap() {
  let o;
  try { o = JSON.parse(localStorage.getItem(RKEY) || "{}") || {}; } catch { return {}; }
  const now = Date.now();
  const cut = now - READ_TTL_MS;
  let changed = false;
  for (const k of Object.keys(o)) {
    const v = o[k];
    if (typeof v !== "number" || v < 1e11) { o[k] = now; changed = true; }  // v2 형식(1) → 지금 읽은 것으로 승계
    else if (v < cut) { delete o[k]; changed = true; }
  }
  if (changed) _writeMap(o);
  return o;
}
function _writeMap(o) {
  try { localStorage.setItem(RKEY, JSON.stringify(o)); } catch { /* private mode 등 */ }
}
/** 목록을 읽음으로 기록하고 배지를 다시 붙인다(시트를 닫을 때 · 멤버를 바꿀 때) */
function _markReadAll(list) {
  const o = _readMap();
  let changed = false;
  for (const m of list || []) if (!o[m.id]) { o[m.id] = Date.now(); changed = true; }
  if (!changed) return;
  _writeMap(o);
  if (_st.board) _applyBadges();
}
/** 면 저장값 — 머리 줄의 「번역 · 원문」 탭이 쓰고 이어받는다("ko" · "orig"). 못 읽으면 번역 */
function _getFace() {
  try { return L.faceOf(localStorage.getItem(TLANG_KEY)); } catch { return 0; }
}
function _setFace(face) {
  try { localStorage.setItem(TLANG_KEY, L.langOf(face)); } catch { /* 저장 못 해도 동작 */ }
}

/* ── 유틸 ────────────────────────────────────────────────────────── */
/** data → { ck: [메시지…] }. 만료 지난 것 빼기 · 게시 시각순 · 상한(MAX_THREAD, 최신 쪽) */
function _visible(data) {
  const now = Date.now();
  const out = {};
  const t = (data && data.tweets) || {};
  for (const ck of Object.keys(t)) {
    const msgs = _list(t[ck])
      .filter((m) => { const e = Date.parse(m.expires_at); return isNaN(e) || e > now; })
      .sort((a, b) => L.tOf(a) - L.tOf(b))
      .slice(-MAX_THREAD);
    if (msgs.length) out[ck] = msgs;
  }
  return out;
}
function _unreadCount(list, rd) {
  let n = 0;
  for (const m of list || []) if (!rd[m.id]) n++;
  return n;
}
/** 멤버 색: 예고판이 아바타에서 뽑아 .lane 에 넣는 --lane-color. 없으면 폴백 바탕 · 글자색은 대비로 */
function _palette(ck) {
  return L.paletteFor(_laneColor(ck));
}
function _laneColor(ck) {
  if (_st.board) {
    for (const lane of _st.board.querySelectorAll(`.lane[data-channel="${CSS.escape(ck)}"]`)) {
      const raw = getComputedStyle(lane).getPropertyValue("--lane-color").trim();
      if (raw) return raw;
    }
  }
  return "";
}
/** (v4.9.1) 멤버 칩의 왼쪽 원 = 예고판 네임플레이트 아바타(.lane__avatar)와 같은 이미지. 보드에 없으면 config 의 avatar */
function _avatarImg(ck) {
  const av = _st.board && _st.board.querySelector(`.lane[data-channel="${CSS.escape(ck)}"] .lane__avatar`);
  if (av && av.style.backgroundImage) return av.style.backgroundImage;
  const u = (FALLBACK_CHANNELS[ck] || {}).avatar;
  return u ? `url("${u}")` : "none";
}
function _lanes(ck) {
  // data-no-badge = 이후 예고 열(PC) — 배지는 타임테이블 왼쪽 칸 / 모바일 레인에만 붙는다
  return _st.board ? _st.board.querySelectorAll(`.lane[data-channel="${CSS.escape(ck)}"]:not([data-no-badge])`) : [];
}
// 원문 앵커: 메시지 URL → 없으면 X 프로필(x.com/<handle>) → 둘 다 없으면 비활성. 유튜브로는 안 감.
function _srcUrl(m) {
  return m.url || (m.handle ? "https://x.com/" + m.handle : "");
}
function _setSrc(el, m) {
  const u = _srcUrl(m);
  if (u) {
    el.href = u;
    el.classList.remove("is-disabled");
    el.removeAttribute("aria-disabled");
    el.tabIndex = 0;
  } else {
    el.removeAttribute("href");
    el.classList.add("is-disabled");
    el.setAttribute("aria-disabled", "true");
    el.tabIndex = -1;
  }
}

/* ── X 공식 카드 (소식 팝업과 공용) ─────────────────────────────────────
   카드 = iframe(X 임베드). 높이는 임베드가 twttr.private.resize 로 알려 주는 값을 그대로 쓴다.
   영상이 든 카드를 한꺼번에 띄우면 브라우저가 멈추므로 화면 근처에 올 때만 불러온다(IntersectionObserver).
   테마를 바꾸면 이미 열린 카드도 같은 테마로 다시 부른다. 15초 안에 신호가 없으면 「X에서 보기」 링크. */
let _embedWired = false;
function _isNumId(id) { return /^[0-9]{5,25}$/.test(String(id || "")); }
function _embedSrc(id) {   // X 카드도 사이트 테마(밝게/어둡게)로 불러온다
  return "https://platform.twitter.com/embed/Tweet.html?id=" + id + "&theme=" + currentTheme() + "&dnt=true&lang=ko&hideThread=true&frame=false";
}
function _wireEmbedResize() {
  if (_embedWired) return;
  _embedWired = true;
  window.addEventListener("message", (e) => {
    if (!EMBED_ORIGINS.includes(e.origin)) return;
    let d = e.data;
    if (typeof d === "string") { try { d = JSON.parse(d); } catch { return; } }
    const p = d && d["twttr.embed"];
    if (!p || p.method !== "twttr.private.resize") return;
    const h = p.params && p.params[0] && p.params[0].height;
    if (!h) return;
    for (const f of document.querySelectorAll("iframe.lane__thread__embed")) {
      if (f.contentWindow !== e.source) continue;
      const wrap = f.parentElement;
      const sc = wrap.closest(".tws__feed");
      const atBottom = sc && (sc.scrollHeight - sc.clientHeight - sc.scrollTop) < 8;
      wrap.style.minHeight = h + "px";
      wrap.dataset.ready = "1";
      wrap.dataset.h = String(h);
      const art = wrap.closest(".tws-tw");
      if (art && art._align) art._align();         // (v4.9.3) 실제 카드 높이로 번역 면 본문 자리를 다시 맞춘다
      const fb = wrap.querySelector(".lane__thread__xlink");
      if (fb) fb.remove();
      if (atBottom) sc.scrollTop = sc.scrollHeight;    // 늦게 로드된 카드 때문에 맨 아래 고정이 풀리지 않게
    }
  });
}
// 테마를 바꾸면 이미 열린 X 카드도 같은 테마로 다시 불러온다(카드 높이는 다시 받은 resize 신호로 맞춰진다)
document.addEventListener(THEME_EVENT, () => {
  for (const f of document.querySelectorAll("iframe.lane__thread__embed")) {
    const id = f.parentElement && f.parentElement.dataset.id;
    if (id) f.src = _embedSrc(id);
  }
});
function _loadCard(wrap) {
  if (wrap.querySelector("iframe")) return;
  _wireEmbedResize();
  const f = document.createElement("iframe");
  f.className = "lane__thread__embed";
  f.src = _embedSrc(wrap.dataset.id);
  f.title = "X 트윗";
  f.setAttribute("allow", "autoplay; fullscreen");
  f.setAttribute("allowfullscreen", "");
  f.setAttribute("scrolling", "no");
  f.addEventListener("load", () => { wrap.dataset.loaded = "1"; });   // 문서는 열렸다 — 높이 신호만 늦을 뿐 실패가 아니다
  wrap.appendChild(f);
  setTimeout(() => {
    if (wrap.dataset.ready || wrap.dataset.loaded || !wrap.isConnected || wrap.querySelector(".lane__thread__xlink")) return;
    const a = document.createElement("a");
    a.className = "lane__thread__xlink";
    a.target = "_blank";
    a.rel = "noopener";
    a.textContent = "카드가 열리지 않아요 · X에서 보기";
    if (wrap.dataset.href) a.href = wrap.dataset.href;
    wrap.appendChild(a);
  }, CARD_TIMEOUT_MS);
}
/** 카드 자리 하나. 숫자 id 면 임베드 자리(높이는 글 내용으로 어림), 아니면 「X에서 원문 보기」 링크 */
function _xCard(m) {
  const wrap = document.createElement("div");
  wrap.className = "lane__thread__xcard";
  const href = _srcUrl(m);
  if (_isNumId(m.id)) {
    wrap.dataset.id = String(m.id);
    if (href) wrap.dataset.href = href;
    wrap.style.minHeight = L.estimateCardH(m) + "px";
    const sk = document.createElement("div");
    sk.className = "lane__thread__xskel";
    sk.textContent = "X 카드 불러오는 중…";
    wrap.appendChild(sk);
  } else {                                            // 합성 id(숫자 아님)는 임베드할 수 없다 → 링크만
    wrap.classList.add("is-plain");
    const a = document.createElement("a");
    a.className = "lane__thread__xlink";
    a.target = "_blank";
    a.rel = "noopener";
    a.textContent = "X에서 원문 보기 ↗";
    _setSrc(a, m);
    wrap.appendChild(a);
  }
  return wrap;
}
/** 시트 · 팝업에서 닫을 때 X 카드 iframe 을 지운다(재생 중인 영상도 멈춘다) */
function _stopCards(root) {
  if (!root) return;
  for (const f of root.querySelectorAll("iframe.lane__thread__embed")) f.remove();
}

/* ── 배지 · 보드 ───────────────────────────────────────────────────── */
/** 배지(.lane__tw) · 아바타 링(.has-tweet) 을 메시지 상태에 맞춘다. 읽음 처리되면 배지가 작아지며 사라진다(B4). */
function _applyBadges() {
  const board = _st.board;
  if (!board) return;
  const vis = _visible(_st.data);
  const rd = _readMap();
  for (const ck of FALLBACK_CHANNEL_ORDER) {
    const list = vis[ck];
    for (const lane of _lanes(ck)) {
      const avatar = lane.querySelector(".lane__avatar");
      if (!avatar) continue;
      avatar.classList.toggle("has-tweet", !!(list && list.length));   // 트윗이 있으면(읽음 여부 무관) 아바타에 얇은 링
      let badge = lane.querySelector(".lane__tw");
      if (!list || !list.length) {
        if (badge) { if (badge.__cancelOut) badge.__cancelOut(); badge.remove(); }
        continue;
      }
      const unreadN = _unreadCount(list, rd);
      const unread = unreadN > 0;
      const sig = list.map((m) => m.id).join(",") + "|" + unreadN;
      const nm = (FALLBACK_CHANNELS[ck] || {}).name_ko || ck;
      if (badge && !unread && badge.classList.contains("is-unread") && !badge.__out) {
        // B4: 읽음 처리 → 배지가 작아지며 사라진다. 최종 상태(읽은 상태)는 애니메이션과 상관없이 맞춘다:
        // 애니메이션 끝 · 260ms 시간 제한 중 먼저 오는 쪽에서 한 번만 실행(탭이 가려져 onfinish 가 안 와도 남지 않게).
        const setRead = () => {
          badge.classList.remove("is-unread");
          badge.classList.add("is-read");
          badge.textContent = "";
          badge.setAttribute("aria-label", nm + ` 읽은 트윗 (스레드 ${list.length}건)`);
          badge.dataset.sig = list.map((m) => m.id).join(",") + "|0";
        };
        badge.classList.remove("is-unread");
        if (_reduce()) { setRead(); continue; }   // 움직임 줄이기: 애니메이션 없이 바로 최종 상태
        badge.__out = true;
        let a = null, t = 0;
        const cancel = () => {   // 취소 = 애니메이션 · 타이머 정리(최종 상태는 맞추지 않는다)
          clearTimeout(t);
          if (a) { a.onfinish = null; a.cancel(); a = null; }
          badge.__out = false;
          badge.__cancelOut = null;
        };
        const finish = () => {   // 최종 상태 — __out 이 살아 있을 때만 한 번 실행
          if (!badge.__out) return;
          cancel();
          setRead();
        };
        badge.__cancelOut = cancel;
        a = badge.animate([{ transform: "scale(1)" }, { transform: "scale(0)" }],
          { duration: 200, easing: "ease-in", fill: "forwards" });
        a.onfinish = finish;
        t = setTimeout(finish, 260);
        continue;
      }
      if (badge && badge.__out) {
        if (!unread) continue;                 // 사라지는 중 — 끝나면 최종 상태가 맞춰진다
        badge.__cancelOut();                   // 사라지는 중 다시 안 읽은 글이 생김 → 취소하고 아래서 정상 갱신
      }
      const wantCls = unread ? "is-unread" : "is-read";
      if (badge && badge.dataset.sig === sig && badge.classList.contains(wantCls)) continue;   // 같은 상태면 그대로(콩콩 애니메이션 유지)
      if (!badge) {
        badge = document.createElement("button");
        badge.type = "button";
        badge.className = "lane__tw";
        lane.querySelector(".lane__header").appendChild(badge);
      }
      badge.dataset.sig = sig;
      badge.classList.toggle("is-unread", unread);
      badge.classList.toggle("is-read", !unread);
      badge.setAttribute("aria-label", nm + (unread ? ` 읽지 않은 트윗 ${unreadN}건` : " 읽은 트윗") + ` (스레드 ${list.length}건)`);
      // 같은 크기의 원: 안 읽음 1건 = 빈 원, 2건 이상 = 숫자 원, 모두 읽음 = 표시 없음
      badge.textContent = unreadN >= 2 ? String(unreadN) : "";
    }
  }
}
/** 배지 + 열린 시트 갱신. 열린 시트는 표시 서명이 바뀐 때만 다시 그린다(X 카드 재로드 방지). */
function _apply() {
  if (!_st.board) return;
  _applyBadges();
  _refreshOpen();
  if (!_st.wired) _wire();
}

/* ── 트윗 시트 ───────────────────────────────────────────────────────
   구조(ui_spec.md §4): .tws-scrim · section.tws > .tws__grab · .tws__head · nav.tws__members · .tws__feed · .tws__newchip · .tws__hint */
function _ensureSheet() {
  if (S) return S;
  const s = {
    open: false, ck: null, from: null, sig: "", face: 0, anchor: null, watch: null, cardIO: null,
    peekT: 0, peekEl: null, peekMem: 0, pendT: [], hintT: 0, hintShown: false, chips: {}, memOn: false,
    units: [], unitEls: [], pending: [], cnt: {}, tx: 0, ty: 0, geo: null,   // (v4.9.1) 그린 글타래 · ↓ 동그라미 대기 글 · 칩 수 · PC 위치
    unitDays: [], pos: {}, fabRaf: 0,                                        // (v4.9.3) 글타래별 날짜 · 멤버별 스크롤 자리 · 동그라미 맞추기
  };
  S = s;
  s.scrim = _el("div", { cls: "tws-scrim", on: { click: () => _close() } });
  s.grab = _el("div", { cls: "tws__grab", attrs: { "aria-hidden": "true" } }, [_el("i")]);
  s.av = _el("span", { cls: "tws__av", attrs: { "aria-hidden": "true" } });
  s.nm = _el("div", { cls: "tws__nm", id: "tws-nm" });
  s.hd = _el("div", { cls: "tws__hd" });
  s.pill = _el("i", { cls: "tws__seg-pill", attrs: { "aria-hidden": "true" } });
  s.koBtn = _el("button", { cls: "tws__seg-b", text: "번역", attrs: { type: "button", "aria-pressed": "true" }, on: { click: () => _setAll(0) } });
  s.xBtn = _el("button", { cls: "tws__seg-b", text: "원문", attrs: { type: "button", "aria-pressed": "false" }, on: { click: () => _setAll(1) } });
  s.seg = _el("div", { cls: "tws__seg", attrs: { role: "group", "aria-label": "모든 글 보기 전환(글 하나만 바꾸려면 그 글을 옆으로 밀기)" } }, [s.pill, s.koBtn, s.xBtn]);
  s.closeBtn = _el("button", { cls: "tws__close", attrs: { type: "button", "aria-label": "닫기" }, on: { click: () => _close() } }, [IC.close()]);
  s.head = _el("div", { cls: "tws__head" }, [
    _el("div", { cls: "tws__who" }, [s.av, _el("div", { cls: "tws__id" }, [s.nm, s.hd])]),
    s.seg, s.closeBtn,
  ]);
  s.mpill = _el("span", { cls: "tws__mpill", attrs: { "aria-hidden": "true" } });
  s.members = _el("nav", { cls: "tws__members", attrs: { "aria-label": "멤버" } }, [s.mpill]);
  for (const ck of FALLBACK_CHANNEL_ORDER) {
    const meta = FALLBACK_CHANNELS[ck] || {};
    const chip = _el("button", { cls: "tws__chip", attrs: { type: "button", "data-ck": ck }, on: { click: () => _switchTo(ck) } }, [
      _el("span", { cls: "tws__chip-av", attrs: { "aria-hidden": "true" } }),
      _el("span", { text: L.shortName(meta.name_ko) || ck }),
    ]);
    s.chips[ck] = chip;
    s.members.append(chip);
  }
  s.feed = _el("div", { cls: "tws__feed" });
  s.newChip = _el("button", { cls: "tws__newchip", attrs: { type: "button" }, on: { click: () => _jumpNew() } });
  s.hint = _el("div", { cls: "tws__hint", attrs: { role: "status" } });
  // (v4.9.1) ↓ 동그라미 · 새 글 알림(화면 낭독기 — 숫자만이 아니라 「누구 새 글 N개」 한 문장) · PC 위아래 가장자리 손잡이
  s.fabN = _el("b", { cls: "tws__fab-n" });
  s.fab = _el("button", { cls: "tws__fab", attrs: { type: "button", tabindex: "-1", "aria-label": "새 글, 맨 아래로" }, on: { click: () => _toBottom() } },
    [_el("span", { cls: "tws__fab-in" }, [IC.down(), s.fabN])]);
  s.live = _el("div", { cls: "tws__live", attrs: { role: "status", "aria-atomic": "true" } });
  s.hread = _el("span", { cls: "tws__hread" });
  s.rzT = _el("div", { cls: "tws__rz tws__rz--t", attrs: { "aria-hidden": "true" } });
  s.rzB = _el("div", { cls: "tws__rz tws__rz--b", attrs: { "aria-hidden": "true" } }, [s.hread]);
  s.measure = _el("div", { cls: "tws__measure", attrs: { "aria-hidden": "true" } });   // (v4.9.3) 원문 높이를 재는 숨은 칸
  s.sheet = _el("section", { cls: "tws", attrs: { role: "dialog", "aria-modal": "true", "aria-labelledby": "tws-nm", tabindex: "-1" } },
    [s.rzT, s.grab, s.head, s.members, s.feed, s.newChip, s.fab, s.hint, s.live, s.rzB, s.measure]);
  document.body.append(s.scrim, s.sheet);

  // 폰: 손잡이 · 머리 줄을 아래로 끌어 닫기(sheetdrag.js). PC 는 끌어 닫기 없음
  wireSheetDrag({
    sheet: s.sheet,
    handles: [s.grab, s.head],
    dir: "down",
    isOpen: () => s.open && _mobile(),
    close: () => _close(),
    setScrim: (v) => {
      s.scrim.classList.toggle("is-drag", v != null);
      s.scrim.style.opacity = v == null ? "" : String(v);
    },
  });
  // 멤버 칩 줄: 마우스 · 펜은 끌기(터치는 CSS pan-x), 끈 뒤의 클릭은 무시
  s.members.addEventListener("pointerdown", (e) => {
    if (e.pointerType === "touch" || e.button > 0) return;
    _mdrag = { x: e.clientX, s: s.members.scrollLeft, on: false };
  });
  s.members.addEventListener("click", (e) => { if (s.memOn) { s.memOn = false; e.preventDefault(); e.stopPropagation(); } }, true);
  s.members.addEventListener("scroll", () => _fadeMembers(), { passive: true });
  s.feed.addEventListener("scroll", () => {
    _fadeEdges();
    _seenPending();
    if (!s.fabRaf) s.fabRaf = requestAnimationFrame(() => { s.fabRaf = 0; _fabSync(); });   // (v4.9.3) 올리면 ↓ 동그라미
  }, { passive: true });
  // (v4.9.1) PC: 머리 줄을 잡아 옮기기 · 위아래 가장자리를 끌어 높이 바꾸기(더블클릭 = 창의 90%로)
  s.head.addEventListener("pointerdown", (e) => {
    if (!s.open || _mobile() || e.button > 0) return;
    if (e.target instanceof Element && e.target.closest("button, a")) return;
    s.geo = { kind: "move", id: e.pointerId, x: e.clientX, y: e.clientY, tx: s.tx, ty: s.ty };
    _geoStart(s.head, e.pointerId, "is-moving");
  });
  for (const rz of [s.rzT, s.rzB]) {
    rz.addEventListener("pointerdown", (e) => {
      if (!s.open || _mobile() || e.button > 0) return;
      s.geo = { kind: "size", id: e.pointerId, y: e.clientY, h: s.sheet.offsetHeight, dir: rz === s.rzB ? 1 : -1, el: rz };
      rz.classList.add("is-on");
      _geoStart(rz, e.pointerId, "is-sizing");
      _readout(s.geo.h);
    });
    rz.addEventListener("dblclick", () => {
      if (!s.open || _mobile()) return;
      try { localStorage.removeItem(HKEY); } catch { /* 지우지 못해도 이번 화면은 90% */ }
      s.sheet.style.height = "";
      _geom();
    });
  }
  // 엿보기는 어떤 조작이든 즉시 취소
  s.sheet.addEventListener("pointerdown", () => _cancelPeek(), true);
  s.sheet.addEventListener("keydown", () => _cancelPeek(), true);
  s.sheet.addEventListener("wheel", () => _cancelPeek(), { capture: true, passive: true });
  s.newChip.setAttribute("aria-live", "polite");
  _wireGlobal();
  return s;
}
function _wireGlobal() {
  if (_globalWired) return;
  _globalWired = true;
  window.addEventListener("pointermove", (e) => {
    if (_drag) _drag.move(e);
    if (_mdrag) _memMove(e);
    if (S && S.geo) _geoMove(e);
  });
  window.addEventListener("pointerup", (e) => {
    if (_drag) _drag.up();
    _memEnd();
    if (S && S.geo) _geoEnd(e);
  });
  window.addEventListener("pointercancel", (e) => {
    if (_drag) _drag.cancel();
    _memEnd();
    if (S && S.geo) _geoEnd(e);
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && S && S.open) _close(); });
  // (v4.9.4) 카드 조작 중(.is-live)인 X 카드 밖을 누르면 덮개를 다시 덮는다 — 폰은 mouseleave 가 없어서
  document.addEventListener("pointerdown", (e) => {
    if (!S || !S.open) return;
    for (const c of S.feed.querySelectorAll(".lane__thread__xcard.is-live")) if (!c.contains(e.target)) c.classList.remove("is-live");
  }, true);
  window.addEventListener("resize", () => {
    if (!S) return;
    if (S.open) _geom();   // 창이 줄면 팝업 높이 · 위치를 창 안으로(폰 폭으로 넘어가면 PC 값을 지운다)
    if (S.open) { clearTimeout(S.alignT); S.alignT = setTimeout(_alignAll, 150); }   // (v4.9.3) 폭이 바뀌면 두 면 위치를 다시
    _syncPills(true);
    _fadeEdges();
    _fadeMembers();
  });
}

function _head() {
  const s = S, ck = s.ck, meta = FALLBACK_CHANNELS[ck] || {};
  const pal = _palette(ck);
  s.sheet.style.setProperty("--m", pal.bg);
  s.sheet.style.setProperty("--mi", pal.ink);
  s.sheet.style.setProperty("--paper", pal.paper);
  s.nm.textContent = meta.name_ko || ck;
  const list = _visible(_st.data)[ck] || [];
  const handle = list.length ? list[list.length - 1].handle : "";
  s.hd.textContent = (handle ? "@" + handle + " · " : "") + "최근 48시간";
  s.av.style.backgroundImage = meta.avatar ? `url("${meta.avatar}")` : "none";
  _syncSeg(true);
}
function _syncSeg(instant) {
  const s = S;
  s.koBtn.setAttribute("aria-pressed", String(s.face === 0));
  s.xBtn.setAttribute("aria-pressed", String(s.face === 1));
  _placePill(s.pill, s.face === 0 ? s.koBtn : s.xBtn, instant);
}

/** 멤버 칩 상태 · 알약(A5) · 칩 줄을 현재 칩이 보이게. pop = 새 글 수가 늘어난 칩의 숫자를 톡 키운다(폴링 갱신).
 *  반환: 새 글 수가 늘어난 멤버 [{ ck, n }] (pop 일 때만) */
function _members(instant, pop) {
  const s = S, vis = _visible(_st.data), rd = _readMap(), grew = [];
  for (const ck of FALLBACK_CHANNEL_ORDER) {
    const chip = s.chips[ck], list = vis[ck] || [];
    chip.setAttribute("aria-current", String(ck === s.ck));
    chip.setAttribute("aria-disabled", String(!list.length));   // 트윗 없는 멤버는 흐리게 · 누를 수 없게
    chip.classList.toggle("is-empty", !list.length);
    const av = chip.querySelector(".tws__chip-av");                // 네임플레이트 아바타 + 레인 색 테두리
    av.style.backgroundImage = _avatarImg(ck);
    av.style.setProperty("--lc", _laneColor(ck) || L.FALLBACK_BG);
    const n = ck === s.ck ? 0 : _unreadCount(list, rd);
    const was = s.cnt[ck] || 0;
    s.cnt[ck] = n;
    let b = chip.querySelector("b");
    if (n) {
      if (!b) { b = _el("b"); chip.append(b); }
      b.textContent = String(n);
      b.setAttribute("aria-label", `새 글 ${n}개`);
      if (pop && n > was) { _pop(b); grew.push({ ck, n }); }
    } else if (b) b.remove();
  }
  _placePill(s.mpill, s.chips[s.ck], instant);
  _keepChip(instant);
  _fadeMembers();
  return grew;
}
/** 칩 줄이 현재 칩을 보이게 — 페이지 전체는 스크롤하지 않도록 줄의 scrollLeft 만 맞춘다 */
function _keepChip(instant) {
  const s = S, chip = s.chips[s.ck];
  if (!chip) return;
  const mem = s.members, pad = 12;
  const vl = mem.scrollLeft, vr = vl + mem.clientWidth, l = chip.offsetLeft, r = l + chip.offsetWidth;
  let to = vl;
  if (l - pad < vl) to = l - pad;
  else if (r + pad > vr) to = r + pad - mem.clientWidth;
  if (Math.abs(to - vl) > 0.5) mem.scrollTo({ left: to, behavior: instant || _reduce() ? "auto" : "smooth" });
}
/** 넘칠 때만 양 끝 흐림 — 끝에 닿은 쪽은 at-l / at-r 로 끈다 */
function _fadeMembers() {
  const s = S; if (!s) return;
  const mem = s.members, over = mem.scrollWidth > mem.clientWidth + 1;
  mem.classList.toggle("at-l", !over || mem.scrollLeft <= 1);
  mem.classList.toggle("at-r", !over || mem.scrollLeft + mem.clientWidth >= mem.scrollWidth - 1);
}
function _memMove(e) {
  const s = S, dx = e.clientX - _mdrag.x;
  if (!_mdrag.on) {
    if (Math.abs(dx) < 8) return;
    _mdrag.on = true;
    s.memOn = true;
    s.members.classList.add("is-grabbing");
    document.body.classList.add("no-select");
  }
  window.getSelection && window.getSelection().removeAllRanges();
  s.members.scrollLeft = _mdrag.s - dx;
}
function _memEnd() {
  if (!_mdrag) return;
  const was = _mdrag.on;
  _mdrag = null;
  if (was && S) {
    setTimeout(() => { if (S) S.memOn = false; }, 0);   // 끈 뒤의 click 한 번만 막는다 — 칩 밖에서 놓아도 다음 클릭이 막히지 않게
    S.members.classList.remove("is-grabbing");
    document.body.classList.remove("no-select");
    window.getSelection && window.getSelection().removeAllRanges();
  }
}
/** 알약 위치 · 크기 — 선택 요소의 offset 으로 맞춘다(instant 면 미끄러짐 없이) */
function _placePill(pill, el, instant) {
  if (!pill || !el) return;
  if (instant) pill.style.transition = "none";
  pill.style.top = el.offsetTop + "px";
  pill.style.height = el.offsetHeight + "px";
  pill.style.width = el.offsetWidth + "px";
  pill.style.transform = "translateX(" + el.offsetLeft + "px)";
  if (instant) { void pill.offsetWidth; pill.style.transition = ""; }
}
function _syncPills(instant) {
  if (!S) return;
  _placePill(S.mpill, S.chips[S.ck], instant);
  _syncSeg(instant);
}

/** 피드 위 · 아래 끝 흐림(C3) — 끝에 닿은 쪽은 흐림을 끈다 */
function _fadeEdges() {
  const f = S && S.feed; if (!f) return;
  f.classList.toggle("at-top", f.scrollTop <= 1);
  f.classList.toggle("at-bottom", f.scrollTop + f.clientHeight >= f.scrollHeight - 1);
}

/** 안내 한 줄(세션당 한 번 — 원문 면으로 처음 밀었을 때) */
function _hint(msg) {
  const s = S;
  s.hint.textContent = msg;
  s.hint.classList.add("is-on");
  clearTimeout(s.hintT);
  s.hintT = setTimeout(() => s.hint.classList.remove("is-on"), 2600);
}

/** 알약 · 칩 · 면 같은 짧은 움직임용 애니메이션 — 진행 중이면 먼저 끊는다 */
function _stopT(el) {
  if (el._anim) { try { el._anim.cancel(); } catch { /* 이미 끝남 */ } el._anim = null; }
  el.style.transform = "";
}
function _runT(el, frames, opts) {
  _stopT(el);
  const a = el.animate(frames, opts);
  el._anim = a;
  a.onfinish = () => { if (el._anim === a) el._anim = null; };
  return a;
}
const _buzz = () => vibrate(10);

/* ── 글(article) 하나 ─────────────────────────────────────────────────
   (v4.9.3) 두 면(번역 · X 원문)을 같은 칸에 겹친다. 뒤 면은 투명하게 제자리에 둔다 — 옆으로 밀어 두면 브라우저가 X 카드를
   그리지 않아 높이 신호가 오지 않는다(10-28 실측). 바꿀 때 앞 면만 옆으로 밀려 나가며 흐려진다(겹쳐 밀기).
   번역 면은 X 카드와 같은 뼈대 · 치수(tweetlogic XM)로 그리고, 본문 · 인용 본문 칸은 원문 높이만큼 자리를 잡아(_align)
   넘겨도 사진 · 인용 · 시각이 같은 자리에 온다. 높이 = 두 면 중 큰 쪽(grid). */
function _article(m, prev, isRoot, unread, now) {
  const s = S;
  const ms = L.tOf(m);
  const hasPosted = !!L.postedIso(m);
  const ck = m.channel_key || s.ck;
  const meta0 = FALLBACK_CHANNELS[ck] || {};
  const att = L.attachments(m);
  const own = L.mediaItems(m.media);
  const qItems = L.mediaItems(m.quote && m.quote.media);
  const hasQuote = (q) => !!(q && (q.text || q.text_ko));
  const timeShort = hasPosted ? L.hmLabel(ms) : L.unpostedLabel(ms);
  const timeFull = (t) => (hasPosted ? L.fullLabel(ms, t) : L.unpostedLabel(ms));

  // 번역 면: 머리 줄 → (자기 답글 줄) → 번역 본문 → 미디어 격자 → 인용 상자 → 바닥 줄(시각 · 원문 링크) — X 카드와 같은 순서
  const av = _el("span", { cls: "tws-ko__av", attrs: { "aria-hidden": "true" } });
  av.style.backgroundImage = _avatarImg(ck);
  const head = _el("div", { cls: "tws-ko__head" }, [
    av,
    _el("div", { cls: "tws-ko__id" }, [
      _el("div", { cls: "tws-ko__nm", text: meta0.name_ko || ck }),
      _el("div", { cls: "tws-ko__hd", text: m.handle ? "@" + m.handle : "" }),
    ]),
    _el("span", { cls: "tws-ko__tag", text: "번역" }),
  ]);
  const koKids = [head];
  if (m.reply_to_id) {   // X 카드의 「@핸들 님에게 보내는 답글」 줄 자리 — 바로 위 글과의 간격을 쓴다
    koKids.push(_el("div", { cls: "tws-ko__re" }, [IC.reply(), document.createTextNode(prev && hasPosted ? "이어서 · " + L.gapLabel(ms - L.tOf(prev)) : "이어서 쓴 글")]));
  }
  const koTxt = _el("p", { cls: "tws-ko__txt", text: m.text_ko || "번역 준비 중…" });
  koKids.push(koTxt);
  const onVideo = (cell, inQuote) => goVideo(cell, inQuote);
  const ownBox = own.length ? _grid(own, false, onVideo) : null;
  if (ownBox) koKids.push(ownBox);
  let quoteNode = null, koQt = null, qBox = null;
  if (hasQuote(m.quote)) {
    quoteNode = document.createTextNode(m.quote.text_ko || "번역 준비 중…");
    koQt = _el("div", { cls: "tws-ko__qt" }, [quoteNode]);
    qBox = qItems.length ? _grid(qItems, true, onVideo) : null;
    koKids.push(_el("div", { cls: "tws-ko__q" }, [_el("div", { cls: "tws-ko__qi" }, [_el("b", { cls: "tws-ko__qh", text: "인용한 글" }), koQt]), qBox]));
  }
  const timeEl = _el("span", { cls: "tws-ko__time", text: timeShort, attrs: { title: timeFull(now) } });
  const openA = _el("a", { cls: "tws-tw__open", attrs: { target: "_blank", rel: "noopener", "aria-label": "X 에서 원문 열기" } }, [IC.x(), _el("span", { text: "원문" })]);
  _setSrc(openA, m);
  koKids.push(_el("div", { cls: "tws-ko__foot" }, [timeEl, openA]));
  const ko = _el("section", { cls: "tws-tw__face is-front", attrs: { "aria-label": "번역" } }, [_el("div", { cls: "tws-ko" }, koKids)]);

  const xcard = _xCard(m);
  const xface = _el("section", { cls: "tws-tw__face is-back", attrs: { "aria-label": "X 원문 카드", "aria-hidden": "true" } }, [xcard]);
  xface.inert = true;
  // (v4.9.1) X 카드 덮개: 카드 머리(작성자 줄)를 뺀 나머지를 투명하게 덮어 밀기 손잡이로 쓴다 —
  // X 카드는 iframe 이라 그 위에서 누른 마우스 · 손가락을 바깥이 받지 못한다. 끌지 않고 한 번 누르면 덮개가 비켜 카드 조작으로(.is-live),
  // 마우스가 카드를 벗어나거나 카드 밖을 누르면 다시 덮인다. (v4.9.4) 폰 · 터치에도 씌운다 — v4.9.3 에서 글 위 시각 줄(손가락 손잡이)을
  // 없앤 뒤로 폰 원문 면에서는 아래 점 줄만 밀 수 있어 「원문 카드에서 좌우로 밀리지 않는다」가 됐다.
  let dragged = false;
  if (xcard.dataset.id) {
    const cover = _el("div", { cls: "tws-xcover", attrs: { "aria-hidden": "true" } });
    cover.addEventListener("click", () => { if (!dragged) xcard.classList.add("is-live"); });
    xcard.addEventListener("mouseleave", () => xcard.classList.remove("is-live"));
    xcard.append(cover);
  }
  const track = _el("div", { cls: "tws-tw__track" }, [ko, xface]);
  const dots = _el("div", { cls: "tws-tw__dots", attrs: { "aria-hidden": "true" } }, [_el("i", { cls: "on" }), _el("i")]);
  const art = _el("article", {
    cls: "tws-tw" + (isRoot ? " is-root" : ""),
    attrs: {
      tabindex: "0", "data-id": String(m.id), "aria-roledescription": "트윗, 좌우로 밀어 번역 · 원문 전환",
      "aria-label": (m.reply_to_id ? "이어진 글, " : "") + timeFull(now) + (unread ? ", 새 글" : "") + (att.text ? ", " + att.text : ""),
    },
  }, [track, dots]);

  /* 두 면 위치 맞추기: 본문 · 인용 본문 칸 = 원문 높이(숨은 칸으로 잼 → X 카드 높이 신호가 오면 거꾸로 계산한 값).
     카드 자리 높이도 같은 계산으로 잡는다. 번역이 더 길어 밀린 양은 영상 글로우 자리 보정에 쓴다. */
  const ratioOf = (box) => Number(box && box.dataset.ratio) || 0;
  art._align = () => {
    const w = track.clientWidth;
    if (!w) return;
    const cw = w - 2 * L.XM.border - 2 * L.XM.side;
    const qT = koQt ? _measureH((m.quote && m.quote.text) || "", cw - 2 * L.XM.border - 2 * L.XM.qPad, true) : 0;
    const p = {
      w, reply: !!m.reply_to_id, n: own.length, ratio: ratioOf(ownBox),
      quote: koQt ? { textH: qT, n: qItems.length, ratio: ratioOf(qBox) } : null,
    };
    const xh = Number(xcard.dataset.h) || 0;
    const tH = xh ? L.xTextH(xh, p) : _measureH(m.text || "", cw, false);
    koTxt.style.minHeight = tH + "px";
    if (koQt) koQt.style.minHeight = qT + "px";
    if (!xh && xcard.dataset.id) xcard.style.minHeight = L.predictCardH({ ...p, textH: tH }) + "px";
    art._shift = Math.max(0, koTxt.offsetHeight - tH);
    art._qshift = koQt ? Math.max(0, koQt.offsetHeight - qT) : 0;
  };
  // 화면 근처에 오면 번역 면 그림을 넣는다(X 카드 불러오기와 같은 때). 1칸이면 그림 크기를 읽어 비율을 정한다.
  art._paint = () => {
    for (const box of [ownBox, qBox]) if (box) _paintGrid(box, art);
  };
  // (v4.9.1) 폴링 갱신 때 다시 그리지 않고 고친다: 시각 · 번역 · 인용 번역 · 원문 링크.
  // 미디어 · 인용 유무 · 답글 여부가 바뀌었으면 false — 호출한 쪽이 시트를 다시 그린다.
  const mediaSig = (x) => [L.mediaItems(x.media).map((i) => i.url).join(","), L.mediaItems(x.quote && x.quote.media).map((i) => i.url).join(","), !!x.reply_to_id].join("|");
  const sig0 = mediaSig(m);
  art._retime = (t) => { timeEl.title = timeFull(t); };
  art._update = (m2) => {
    if (mediaSig(m2) !== sig0 || hasQuote(m2.quote) !== !!quoteNode) return false;
    koTxt.textContent = m2.text_ko || "번역 준비 중…";
    if (quoteNode) quoteNode.nodeValue = m2.quote.text_ko || "번역 준비 중…";
    _setSrc(openA, m2);
    return true;
  };

  /* ── 겹쳐 밀기 ── */
  const faces = [ko, xface];
  let face = 0, busy = 0, pastMid = false, g = null;
  const clearDots = () => { for (const d of dots.children) d.style.width = ""; dots.classList.remove("is-drag"); };
  const setDots = (t) => {   // t = 원문 면 쪽으로 간 정도(0~1)
    if (_reduce() || t <= 0.001 || t >= 0.999) { clearDots(); return; }
    dots.classList.add("is-drag");
    dots.children[0].style.width = (14 - 8 * t).toFixed(2) + "px";   // A2: 끄는 동안 점 폭 연속 변화
    dots.children[1].style.width = (6 + 8 * t).toFixed(2) + "px";
  };
  const pulseDot = (k) => { if (!_reduce()) dots.children[k].animate([{ transform: "scale(1.25)" }, { transform: "scale(1)" }], { duration: 120, easing: "ease-out" }); };
  /** 앞 · 뒤 면을 확정한다(끼어 있던 움직임 · 끄는 중 모양은 지운다) */
  const mark = (f) => {
    if (f === 0) xcard.classList.remove("is-live");   // 번역으로 돌아오면 덮개를 다시 덮는다
    faces.forEach((x, i) => {
      const on = i === f;
      x.classList.toggle("is-front", on);
      x.classList.toggle("is-back", !on);
      x.classList.remove("is-going");
      x.inert = !on;
      if (on) x.removeAttribute("aria-hidden"); else x.setAttribute("aria-hidden", "true");
      x.style.transform = "";
      x.style.opacity = "";
    });
    dots.children[0].classList.toggle("on", f === 0);
    dots.children[1].classList.toggle("on", f === 1);
    clearDots();
    pastMid = false;
  };
  function setFace(i, smooth) {
    if (busy) { clearTimeout(busy); busy = 0; mark(face); }
    const from = face;
    face = i;
    art._face = i;
    if (from === i || !smooth || _reduce()) { mark(i); return; }
    const front = faces[from], back = faces[i];
    front.classList.add("is-going");
    front.style.transform = "translateX(" + (i === 1 ? -40 : 40) + "%)";
    front.style.opacity = "0";
    back.classList.add("is-going");
    back.style.transform = "none";
    back.style.opacity = "1";
    dots.children[0].classList.toggle("on", i === 0);
    dots.children[1].classList.toggle("on", i === 1);
    busy = setTimeout(() => { busy = 0; mark(i); }, 300);
  }
  /** 손을 놓았는데 문턱을 못 넘음 → 앞 면이 제자리로 튕겨 돌아온다 */
  const springBack = () => {
    const front = faces[face];
    if (!_reduce()) { front.classList.add("is-spring"); setTimeout(() => front.classList.remove("is-spring"), 440); }
    mark(face);
  };
  /** (v4.9.3) 영상 칸 → 그 글만 원문 면 + 카드의 같은 영상 칸 자리에 글로우 한 번. 사진 칸은 누르지 않는다 */
  function goVideo(cell, inQuote) {
    if (dragged) return;
    let x = 0, y = 0;
    for (let e = cell; e && e !== ko; e = e.offsetParent) { x += e.offsetLeft; y += e.offsetTop; }
    y -= art._shift || 0;                       // 번역이 원문보다 길어 밀린 만큼 카드 쪽 자리로
    if (inQuote) y -= art._qshift || 0;
    const box = { x, y, w: cell.offsetWidth, h: cell.offsetHeight };
    xcard.classList.add("is-live");               // 다음 한 번 누름이 바로 카드(영상 재생)에 닿게(덮개를 미리 비킴)
    setFace(1, true);
    setTimeout(() => {
      if (!xface.isConnected) return;
      const gl = _el("div", { cls: "tws-glow", attrs: { "aria-hidden": "true" } });
      Object.assign(gl.style, { left: box.x + "px", top: box.y + "px", width: box.w + "px", height: box.h + "px" });
      xface.append(gl);
      const done = () => gl.remove();
      gl.addEventListener("animationend", done);
      setTimeout(done, 1500);                  // 탭이 가려져 animationend 가 안 와도 남지 않게
    }, _reduce() ? 0 : 300);
  }
  art._setFace = setFace;
  art._face = 0;
  art._front = () => faces[face];
  art.addEventListener("keydown", (e) => {
    if (e.target !== art) return;
    if (e.key === "ArrowRight") { setFace(1, true); e.preventDefault(); }
    if (e.key === "ArrowLeft") { setFace(0, true); e.preventDefault(); }
  });
  // 끌기: 마우스 · 손가락 · 펜 모두(번역 면 · 점 줄 · PC 덮개 위). 손가락이 X 카드 위면 iframe 이 가져간다.
  const ctl = {
    move(e) {
      if (!g) return;
      const dx = e.clientX - g.x, dy = e.clientY - g.y;
      if (!g.on) {
        if (Math.abs(dx) < 8 || Math.abs(dx) < Math.abs(dy)) return;
        g.on = true; dragged = true;
        if (busy) { clearTimeout(busy); busy = 0; mark(face); }
        track.classList.add("is-grabbing");
        document.body.classList.add("no-select");
      }
      window.getSelection && window.getSelection().removeAllRanges();
      const t = dx / Math.max(1, track.clientWidth);
      const want = face === 0 ? t < 0 : t > 0;
      const k = Math.min(1, Math.abs(t));
      const front = faces[face], back = faces[1 - face];
      if (want) {
        front.style.transform = "translateX(" + (t * 100).toFixed(2) + "%)";
        front.style.opacity = String(Math.max(0, 1 - k * 1.2));
        back.style.opacity = String(Math.min(1, k * 1.6));
        back.style.transform = "scale(" + (0.985 + 0.015 * k).toFixed(4) + ")";
      } else if (!_reduce()) {                  // A3: 더 갈 면이 없는 쪽 = 고무줄
        front.style.transform = "translateX(" + (Math.sign(dx) * Math.min(24, Math.abs(dx) / 3)).toFixed(2) + "px)";
      }
      setDots(want ? (face === 0 ? k : 1 - k) : face);
      const past = want && k > 0.25;
      if (past !== pastMid) { pastMid = past; if (past) { pulseDot(1 - face); _buzz(); } }
      g.t = t;
    },
    up() {
      const was = g && g.on, t = g ? g.t || 0 : 0;
      g = null;
      if (_drag === ctl) _drag = null;
      if (!was) return;
      setTimeout(() => { dragged = false; }, 0);   // 끈 직후 덮개 · 영상 칸에 떨어지는 click 한 번은 무시
      track.classList.remove("is-grabbing");
      document.body.classList.remove("no-select");
      window.getSelection && window.getSelection().removeAllRanges();
      const to = L.swipeTo(face, t);
      if (to === face) { springBack(); return; }
      setFace(to, true);
      if (to === 1 && !S.hintShown) {
        S.hintShown = true;
        _hint("카드를 옆으로 밀면 번역으로 돌아와요. 카드 속 영상 · 링크는 한 번 누른 뒤 다시 누르세요.");
      }
    },
    cancel() {
      const was = g && g.on;
      g = null;
      if (_drag === ctl) _drag = null;
      if (!was) return;
      dragged = false;
      track.classList.remove("is-grabbing");
      document.body.classList.remove("no-select");
      mark(face);
    },
  };
  const startDrag = (e) => {
    _stopT(faces[face]);
    if (e.button > 0 || (e.target instanceof Element && e.target.closest("a"))) return;
    g = { x: e.clientX, y: e.clientY, on: false };
    _drag = ctl;
  };
  track.addEventListener("pointerdown", startDrag);
  dots.addEventListener("pointerdown", startDrag);
  track.addEventListener("click", (e) => { if (dragged) { e.preventDefault(); e.stopPropagation(); } }, true);
  // 트랙패드 가로: 가로로 60px 넘게 모이면 한 번 넘기고 400ms 쉰다(세로 휠은 피드 스크롤로)
  let acc = 0, rest = 0, accT = 0;
  track.addEventListener("wheel", (e) => {
    if (Math.abs(e.deltaX) <= Math.abs(e.deltaY)) return;
    e.preventDefault();
    const t0 = Date.now();
    if (t0 < rest) return;
    if (t0 - accT > 250) acc = 0;
    accT = t0;
    acc += e.deltaX;
    if (Math.abs(acc) > 60) { setFace(acc > 0 ? 1 : 0, true); acc = 0; rest = t0 + 400; }
  }, { passive: false });
  return art;
}
/** 미디어 격자. 사진 = div[role=img](누르지 않음), 영상 = button(▶ — 누르면 원문 카드의 같은 칸으로).
 *  그림은 화면 근처에 올 때 넣는다(_paintGrid). 내려받기 막기: <img> 를 쓰지 않고 배경 그림 + 우클릭 · 끌기 막기 */
function _grid(items, inQuote, onVideo) {
  const g = L.gridOf(items.length);
  const box = _el("div", { cls: "tws-md " + g.cls });
  box.addEventListener("contextmenu", (e) => e.preventDefault());
  box.addEventListener("dragstart", (e) => e.preventDefault());
  items.slice(0, g.shown).forEach((it, i) => {
    const cell = it.video
      ? _el("button", { cls: "tws-md__cell is-video", attrs: { type: "button", "aria-label": "영상, 원문 카드에서 재생" } }, [_el("span", { cls: "tws-md__play", attrs: { "aria-hidden": "true" } }, [IC.play()])])
      : _el("div", { cls: "tws-md__cell", attrs: { role: "img", "aria-label": "사진" } });
    cell.dataset.src = L.smallUrl(it.url);
    if (i === 3 && g.more) cell.append(_el("span", { cls: "tws-md__more", text: "+" + g.more, attrs: { "aria-hidden": "true" } }));
    if (it.video) cell.addEventListener("click", () => onVideo(cell, inQuote));
    box.append(cell);
  });
  return box;
}
function _paintGrid(box, art) {
  for (const cell of box.querySelectorAll(".tws-md__cell[data-src]")) {
    cell.style.backgroundImage = `url("${cell.dataset.src.replace(/["\\]/g, "")}")`;
    cell.dataset.painted = cell.dataset.src;
    cell.removeAttribute("data-src");
  }
  if (!box.classList.contains("g1") || box.dataset.ratio) return;
  const src = box.firstElementChild && box.firstElementChild.dataset.painted;
  if (!src) return;
  const im = new Image();                     // 크기만 읽는다(화면에는 두지 않는다)
  im.onload = () => {
    const r = L.singleRatio(im.naturalWidth, im.naturalHeight);
    box.dataset.ratio = String(r);
    _keepBottom(() => { box.style.aspectRatio = String(r); if (art._align) art._align(); });
  };
  im.src = src;
}
/** 원문 높이를 X 카드와 같은 글꼴 · 크기 · 폭으로 잰다(숨은 칸 — 화면에 그리지 않는다). quote = 인용 본문(15px/20px) */
function _measureH(text, width, quote) {
  const el = S && S.measure;
  if (!el || !text || !(width > 0)) return 0;
  el.className = "tws__measure" + (quote ? " is-quote" : "");
  el.style.width = width + "px";
  el.textContent = text;
  const h = Math.ceil(el.getBoundingClientRect().height);
  el.textContent = "";
  return h;
}
/** 피드가 맨 아래였으면 fn(높이를 바꾸는 일) 뒤에도 맨 아래를 지킨다 */
function _keepBottom(fn) {
  const f = S && S.feed;
  const was = !!f && f.scrollHeight - f.clientHeight - f.scrollTop < 8;
  fn();
  if (was && S.open) f.scrollTop = f.scrollHeight;
}

/* ── 피드 그리기 ───────────────────────────────────────────────────── */
/** 시트 목록을 다시 그린다. fresh = 열 때 · 멤버를 바꿀 때(v4.9.3: 처음이면 맨 아래, 다시 온 멤버면 기억한 자리),
 *  아니면 폴링으로 갱신 — 각 글의 면 · 피드 스크롤 위치를 유지한다. */
function _renderFeed(fresh) {
  const s = S;
  const feed = s.feed;
  const faces = new Map();
  const prevTop = feed.scrollTop;
  if (!fresh) for (const a of feed.querySelectorAll(".tws-tw")) faces.set(a.dataset.id, a._face || 0);
  if (s.watch) { s.watch.disconnect(); s.watch = null; }
  if (s.cardIO) { s.cardIO.disconnect(); s.cardIO = null; }
  _stopCards(feed);
  feed.replaceChildren();
  const list = _visible(_st.data)[s.ck] || [];
  const rd = _readMap();
  const isRead = (m) => !!rd[m.id];
  const units = L.chains(list);
  const anchor = L.firstUnread(units, isRead);
  const now = Date.now();
  const arts = [], unitEls = [];
  let anchorEl = null;
  for (const u of units) {
    const wrap = u.length > 1 ? _chainWrap(u.length) : null;
    let one = null;
    u.forEach((m, i) => {
      if (anchor && !anchorEl && String(m.id) === anchor.id) {
        anchorEl = _el("div", { cls: "tws__new", text: "여기부터 새 글" });
        if (fresh && !_reduce()) anchorEl.classList.add("draw");   // B4: 여는 때 한 번 양쪽 선이 그어진다
        if (anchor.inChain && wrap) wrap.append(anchorEl);
        else feed.append(anchorEl);
      }
      const art = _article(m, i > 0 ? u[i - 1] : null, !!wrap && i === 0, !isRead(m), now);
      arts.push(art);
      (wrap || feed).append(art);
      one = art;
    });
    if (wrap) feed.append(wrap);
    unitEls.push(wrap || one);
  }
  s.anchor = anchorEl;
  s.units = units.map((u) => u.map((m) => String(m.id)));   // (v4.9.1) 다음 폴링 때 새 글만 끼우려고 그린 모양을 기억
  s.unitEls = unitEls;
  s.unitDays = units.map((u) => L.dayLabel(L.tOf(u[u.length - 1])));
  _days();
  s.pending = [];
  s.newChip.textContent = "새 글 " + _unreadCount(list, rd) + "개 ↓";
  s.newChip.classList.remove("is-on");
  requestAnimationFrame(() => {
    if (!S || S !== s) return;
    for (const a of arts) {
      const want = faces.has(a.dataset.id) ? faces.get(a.dataset.id) : s.face;
      a._setFace(want, false);
      a._align();
    }
    if (fresh) {
      // (v4.9.3) 처음이면 맨 아래 — 「여기부터 새 글」 선은 표시만. 이 멤버를 연 동안 다시 왔으면 기억한 자리
      const tgt = L.restoreTarget(s.pos[s.ck], arts.map((a) => a.dataset.id));
      const el = tgt && feed.querySelector(`.tws-tw[data-id="${CSS.escape(tgt.id)}"]`);
      feed.scrollTop = el ? el.getBoundingClientRect().top - feed.getBoundingClientRect().top + feed.scrollTop + tgt.off : feed.scrollHeight;
    } else feed.scrollTop = prevTop;
    _fadeEdges();
    _watch();
    _fabSync();
  });
}
/** (v4.9.3) 날짜 구분선 — 날짜가 바뀌는 글타래 앞에(「여기부터 새 글」 선이 바로 앞이면 그 선 앞에) */
function _days() {
  const s = S;
  for (const d of s.feed.querySelectorAll(".tws__day")) d.remove();
  let prev = "";
  s.unitEls.forEach((el, i) => {
    const d = s.unitDays[i];
    if (!el || d === prev) return;
    prev = d;
    const at = s.anchor && el.previousElementSibling === s.anchor ? s.anchor : el;
    at.before(_el("div", { cls: "tws__day", text: d, attrs: { role: "separator" } }));
  });
}
/** (v4.9.3) 멤버를 떠날 때 지금 자리를 기억한다 — 맨 아래면 맨 아래, 아니면 위 가장자리에 걸친 글 + 어긋남 */
function _savePos() {
  const s = S, f = s.feed;
  if (!s.ck) return;
  if (_atBottom()) { s.pos[s.ck] = { bottom: true }; return; }
  const top = f.getBoundingClientRect().top;
  for (const a of f.querySelectorAll(".tws-tw")) {
    const r = a.getBoundingClientRect();
    if (r.bottom > top + 1) { s.pos[s.ck] = { id: a.dataset.id, off: top - r.top }; return; }
  }
}
/** (v4.9.3) 그린 글 전부 두 면 위치를 다시 맞춘다(창 폭이 바뀌었을 때) */
function _alignAll() {
  if (!S || !S.open) return;
  _keepBottom(() => { for (const a of S.feed.querySelectorAll(".tws-tw")) if (a._align) a._align(); });
}
function _chainWrap(n) {
  return _el("div", { cls: "tws-chain" + (_reduce() ? "" : " wait"), attrs: { role: "group", "aria-label": `글타래: 원글과 이어진 글 ${n - 1}개` } });
}

/* ── 새 글 도착 (v4.9.1) ──────────────────────────────────────────────
   폴링으로 글이 늘면 이미 그린 글(X 카드 iframe 포함)은 그대로 두고 새 글만 끼운다(L.reconcileUnits 가 계획).
   끼울 수 없으면(글이 빠짐 · 글타래 안에 끼어듦 · 뿌리가 바뀜 · 첨부나 인용 유무가 바뀜) false → 다시 그린다(_renderFeed).
   맨 아래에 있었으면 새 글이 아래에서 올라오고 피드가 따라 내려간다. 아니면 화면 아래쪽 새 글 수를 ↓ 동그라미에 띄운다. */
function _patchFeed(list) {
  const s = S, feed = s.feed;
  const units = L.chains(list);
  const plan = L.reconcileUnits(s.units, units.map((u) => u.map((m) => String(m.id))));
  if (!plan) return false;
  const byId = new Map();
  for (const a of feed.querySelectorAll(".tws-tw")) byId.set(a.dataset.id, a);
  const now = Date.now();
  for (const m of list) {
    const a = byId.get(String(m.id));
    if (!a) continue;
    if (!a._update(m)) return false;
    a._retime(now);
  }
  const wasBottom = _atBottom();
  const rd = _readMap();
  const added = [], newWraps = [], els = [];
  plan.forEach((p, i) => {
    const u = units[i];
    let el = p.from >= 0 ? s.unitEls[p.from] : null;
    if (p.add.length) {
      const isChain = (x) => !!x && x.classList.contains("tws-chain");
      if (u.length > 1 && !isChain(el)) {          // 글 하나였던 자리에 답글이 붙음 · 새 글타래 → 묶음을 만든다
        const wrap = _chainWrap(u.length);
        if (el) { el.replaceWith(wrap); wrap.append(el); el.classList.add("is-root"); }
        el = wrap;
        newWraps.push(wrap);
      } else if (isChain(el)) el.setAttribute("aria-label", `글타래: 원글과 이어진 글 ${u.length - 1}개`);
      for (let j = u.length - p.add.length; j < u.length; j++) {
        const m = u[j];
        const art = _article(m, j > 0 ? u[j - 1] : null, u.length > 1 && j === 0, !rd[m.id], now);
        added.push(art);
        if (isChain(el)) el.append(art); else el = art;
      }
    }
    els.push({ el, keep: p.keep });
  });
  // 순서 맞추기: 제자리(keep)가 아닌 옛 글타래만 떼었다 다시 끼운다. 「여기부터 새 글」 선은 바로 뒤 글타래를 따라간다
  const anchorFor = s.anchor && s.anchor.parentNode === feed ? s.anchor.nextElementSibling : null;
  for (const d of feed.querySelectorAll(".tws__day")) d.remove();   // (v4.9.3) 순서를 맞춘 뒤 다시 넣는다
  for (const { el, keep } of els) if (!keep && el.parentNode === feed) el.remove();
  let cur = null;
  const put = (node) => {
    const want = cur ? cur.nextElementSibling : feed.firstElementChild;
    if (want !== node) { if (cur) cur.after(node); else feed.prepend(node); }
    cur = node;
  };
  for (const { el } of els) { if (el === anchorFor) put(s.anchor); put(el); }
  s.units = units.map((u) => u.map((m) => String(m.id)));
  s.unitEls = els.map((x) => x.el);
  s.unitDays = units.map((u) => L.dayLabel(L.tOf(u[u.length - 1])));
  _days();
  _observe(added, newWraps);
  requestAnimationFrame(() => {
    if (!S || !S.open) return;
    for (const a of added) { a._setFace(s.face, false); a._align(); }
    _arrive(added, wasBottom);
    _fadeEdges();
  });
  return true;
}
function _atBottom() {
  const f = S.feed;
  return f.scrollHeight - f.clientHeight - f.scrollTop < 24;
}
/** 새로 끼운 글 · 글타래를 관찰에 넣는다(글타래 세로줄 · X 카드 불러오기) */
function _observe(arts, wraps) {
  const s = S;
  if (!s.watch || !s.cardIO) {
    for (const w of wraps) w.classList.remove("wait");
    for (const a of arts) { a.querySelectorAll(".lane__thread__xcard[data-id]").forEach(_loadCard); if (a._paint) a._paint(); }
    return;
  }
  for (const w of wraps) if (w.classList.contains("wait")) s.watch.observe(w);
  for (const a of arts) s.cardIO.observe(a);
}
function _arrive(arts, wasBottom) {
  const s = S, feed = s.feed;
  if (!arts.length) return;
  const name = L.shortName((FALLBACK_CHANNELS[s.ck] || {}).name_ko);
  if (wasBottom && !s.pending.length) {
    for (const a of arts) _anim(a, "is-arriving");
    feed.scrollTo({ top: feed.scrollHeight, behavior: _reduce() ? "auto" : "smooth" });
    _say(`${name} 새 글 ${arts.length}개가 도착했어요`);
    return;
  }
  const fr = feed.getBoundingClientRect();
  for (const a of arts) {
    const r = a.getBoundingClientRect();
    if (r.top >= fr.bottom - 8) s.pending.push(a);      // 화면 아래 → ↓ 동그라미가 데려간다
    else if (r.bottom > fr.top) _anim(a, "is-arriving"); // 화면 안에 끼어든 글은 그 자리에서 올라온다
  }
  if (s.pending.length) {
    _fabSync(true);
    _say(`${name} 새 글 ${s.pending.length}개 — 맨 아래로 버튼으로 이동`);
  }
}
/** 한 번만 도는 CSS 애니메이션 클래스(끝나면 뗀다). 움직임 줄이기는 CSS 쪽에서 투명도만 */
function _anim(el, cls) {
  el.classList.remove(cls);
  void el.offsetWidth;
  el.classList.add(cls);
  const done = (e) => { if (e.target !== el) return; el.classList.remove(cls); el.removeEventListener("animationend", done); };
  el.addEventListener("animationend", done);
}
/** ↓ 동그라미 맞추기(v4.9.3): 기다리는 새 글이 있으면 숫자 · 흔들기(.is-count), 없어도 맨 아래에서 160px 넘게 올라가 있으면
 *  「맨 아래로」만, 아니면 거둔다(L.fabMode). bump = 수가 늘 때 숫자를 톡 키운다 */
function _fabSync(bump) {
  const s = S, f = s.fab, n = s.pending.length;
  const mode = L.fabMode(s.feed.scrollHeight - s.feed.clientHeight - s.feed.scrollTop, n);
  if (mode === "off") {
    if (document.activeElement === f) s.sheet.focus({ preventScroll: true });
    f.classList.remove("is-on", "is-count");
    f.tabIndex = -1;
    return;
  }
  const was = Number(s.fabN.textContent) || 0;
  f.classList.toggle("is-count", mode === "count");
  s.fabN.textContent = mode === "count" ? String(n) : "";
  f.setAttribute("aria-label", mode === "count" ? `새 글 ${n}개, 맨 아래로` : "맨 아래로");
  f.tabIndex = 0;
  if (mode === "count") s.newChip.classList.remove("is-on");   // 「새 글 N개 ↓」 칩과 겹치지 않게 — 숫자 동그라미가 우선
  if (!f.classList.contains("is-on")) f.classList.add("is-on");
  else if (bump && mode === "count" && n > was) _pop(s.fabN);
}
function _toBottom() {
  const f = S.feed;
  f.scrollTo({ top: f.scrollHeight, behavior: _reduce() ? "auto" : "smooth" });
  // (v4.9.3) 내려가는 동안 지나친 X 카드가 실제 높이로 커지면 바닥이 밀린다 — 다 내려간 뒤 한 번 더 맨 아래로
  let done = false;
  const fin = () => {
    if (done) return;
    done = true;
    f.removeEventListener("scrollend", fin);
    if (S.open && f.scrollHeight - f.clientHeight - f.scrollTop > 8) f.scrollTop = f.scrollHeight;
  };
  f.addEventListener("scrollend", fin);
  setTimeout(fin, 1200);   // scrollend 를 모르는 브라우저
}
/** 맨 아래까지 내려와 기다리던 새 글을 만났다 — 어느 글이 새로 왔는지 테두리를 한 번 빛내고 동그라미를 거둔다 */
function _seenPending() {
  const s = S;
  if (!s.pending.length || !_atBottom()) return;
  for (const a of s.pending) if (a.isConnected) _anim(a, "is-fresh");
  s.pending = [];
  _fabSync();
}
function _say(text) {
  const el = S.live;
  el.textContent = "";
  setTimeout(() => { el.textContent = text; }, 30);   // 같은 문장이어도 다시 읽히게
}

/** 관찰 세 가지: 글타래 세로줄 한 번 그리기(C1) · 「새 글」 자리가 아래에 있을 때 칩(C2) · 화면 근처 글의 X 카드 불러오기(§5-5) */
function _watch() {
  const s = S;
  if (typeof IntersectionObserver === "undefined") {
    s.feed.querySelectorAll(".tws-chain").forEach((c) => c.classList.remove("wait"));
    s.feed.querySelectorAll(".tws-tw").forEach((a) => { a.querySelectorAll(".lane__thread__xcard[data-id]").forEach(_loadCard); if (a._paint) a._paint(); });
    return;
  }
  s.watch = new IntersectionObserver((entries) => {
    for (const en of entries) {
      const el = en.target;
      if (el === s.anchor) {
        s.newChip.classList.toggle("is-on", !s.fab.classList.contains("is-count") && !en.isIntersecting && !!en.rootBounds && en.boundingClientRect.top >= en.rootBounds.bottom);
        continue;
      }
      if (!en.isIntersecting) continue;
      s.watch.unobserve(el);
      el.classList.remove("wait");
      el.classList.add("draw");
    }
  }, { root: s.feed, threshold: 0 });
  if (s.anchor) s.watch.observe(s.anchor);
  else s.newChip.classList.remove("is-on");
  for (const c of s.feed.querySelectorAll(".tws-chain.wait")) s.watch.observe(c);

  s.cardIO = new IntersectionObserver((entries) => {
    for (const en of entries) {
      if (!en.isIntersecting) continue;
      s.cardIO.unobserve(en.target);
      en.target.querySelectorAll(".lane__thread__xcard[data-id]").forEach(_loadCard);
      if (en.target._paint) en.target._paint();   // (v4.9.3) 번역 면 사진 · 영상 썸네일도 이때
    }
  }, { root: s.feed, rootMargin: "100% 0px" });   // 화면 위아래 한 화면 안쪽의 글만 — 원문 면이 가로로 밀려 있어도 글 자체를 본다
  for (const a of s.feed.querySelectorAll(".tws-tw")) s.cardIO.observe(a);
}
function _jumpNew() {
  const s = S;
  if (!s.anchor) return;
  const f = s.feed;
  f.scrollTo({ top: f.scrollTop + s.anchor.getBoundingClientRect().top - f.getBoundingClientRect().top - 10, behavior: _reduce() ? "auto" : "smooth" });
}
/** 모든 글 면 전환(머리 줄 탭): 화면에 보이는 글만 위에서 40ms 간격, 나머지는 즉시. 선택은 mew:tllang 에 남는다 */
function _setAll(face) {
  const s = S;
  s.face = face;
  _setFace(face);
  _syncSeg(false);
  for (const t of s.pendT) clearTimeout(t);
  s.pendT = [];
  const f = s.feed, fr = f.getBoundingClientRect();
  let k = 0;
  for (const a of f.querySelectorAll(".tws-tw")) {
    const r = a.getBoundingClientRect();
    if (s.open && r.bottom > fr.top && r.top < fr.bottom) {
      const d = 40 * k++;
      if (d) s.pendT.push(setTimeout(() => a._setFace(face, true), d));
      else a._setFace(face, true);
    } else a._setFace(face, false);
  }
}
/** A1: 처음 두 번 열 때 보이는 첫 글을 24px 밀었다 돌아온다. 조작하면 취소 */
function _peek() {
  const s = S;
  if (_reduce()) return;
  let n = s.peekMem;
  try { n = Math.max(n, Number(localStorage.getItem(PEEK_KEY)) || 0); } catch { /* 읽기 실패: 이 화면에서 센 값만 */ }
  if (n >= PEEK_MAX) return;
  s.peekMem = n + 1;
  try { localStorage.setItem(PEEK_KEY, String(n + 1)); } catch { /* 저장 실패해도 보여 준다 */ }
  s.peekT = setTimeout(() => {
    s.peekT = 0;
    const fr = s.feed.getBoundingClientRect();
    const art = [...s.feed.querySelectorAll(".tws-tw")].find((a) => { const r = a.getBoundingClientRect(); return r.bottom > fr.top + 8 && r.top < fr.bottom - 8; });
    const tr = art && art._front && art._front();   // (v4.9.3) 겹쳐 밀기 — 앞 면만 엿본다
    if (!tr || !s.open) return;
    s.peekEl = tr;
    _runT(tr, [{ transform: "translateX(0px)" }, { transform: "translateX(-24px)", offset: 0.5 }, { transform: "translateX(0px)" }], { duration: 260, easing: EASE });
  }, 360);
}
function _cancelPeek() {
  const s = S; if (!s) return;
  clearTimeout(s.peekT);
  s.peekT = 0;
  if (s.peekEl) _stopT(s.peekEl);
  s.peekEl = null;
}

/* ── 열기 · 닫기 · 멤버 바꾸기 ──────────────────────────────────────── */
function _open(ck, from) {
  const list = _visible(_st.data)[ck];
  if (!list || !list.length) return;
  const s = _ensureSheet();
  if (s.open) return;
  s.ck = ck;
  s.from = from || null;
  s.face = _getFace();
  s.sig = L.sigOf(list);
  s.cnt = {};
  s.pos = {};                  // (v4.9.3) 멤버별 스크롤 자리는 연 동안만 기억
  s.tx = 0; s.ty = 0;          // 위치는 열 때마다 가운데, 높이만 기억(mew:twh)
  _head();
  _members(true);
  _geom();
  // PC: 누른 아바타 쪽에서 커지며 나온다(B2)
  if (!_mobile() && from) {
    const r = s.sheet.getBoundingClientRect(), a = from.getBoundingClientRect();
    s.sheet.style.transformOrigin = ((a.left + a.width / 2 - r.left) / Math.max(1, r.width) * 100).toFixed(1) + "% " + ((a.top + a.height / 2 - r.top) / Math.max(1, r.height) * 100).toFixed(1) + "%";
  } else s.sheet.style.transformOrigin = "";
  s.open = true;
  _renderFeed(true);
  s.sheet.classList.add("is-open");
  s.scrim.classList.add("is-on");
  s.scrim.style.opacity = "";
  _lock(true);
  setTimeout(() => { if (S && S.open) s.sheet.focus({ preventScroll: true }); }, 30);
  _peek();
}
function _close() {
  const s = S;
  if (!s || !s.open) return;
  s.open = false;
  const ck = s.ck;
  _markReadAll(_visible(_st.data)[ck] || []);   // 닫으면 읽음 처리 → 배지가 줄어든다(B4)
  s.sheet.classList.remove("is-open");
  s.scrim.classList.remove("is-on");
  s.scrim.style.opacity = "";
  _lock(false);
  _cancelPeek();
  s.newChip.classList.remove("is-on");
  s.pending = [];
  s.fab.classList.remove("is-on", "is-count");
  s.fab.tabIndex = -1;
  if (s.watch) { s.watch.disconnect(); s.watch = null; }
  if (s.cardIO) { s.cardIO.disconnect(); s.cardIO = null; }
  _stopCards(s.feed);                                  // 닫으면 X 카드(재생 중인 영상 포함) 를 지운다
  const back = s.from;
  s.from = null;
  const target = _focusTarget(back, ck);
  if (target) target.focus({ preventScroll: true });
}
/** 닫을 때 포커스 복귀: 연 요소 → 같은 레인의 레인 링크(.lane__link) → 레인 안 첫 포커스 가능 요소. 없으면 null.
 *  배지(.lane__tw)는 닫으면서 읽음 처리되어 숨겨질 수 있으므로 후보에서 뺀다. */
const _FOCUSABLE_SEL = "a[href], button, input, select, textarea, [tabindex]";
function _canFocus(el) {
  return !!el && el.isConnected && el.matches(_FOCUSABLE_SEL) && !el.disabled && el.tabIndex >= 0 && el.getClientRects().length > 0;
}
function _focusTarget(back, ck) {
  if (_canFocus(back) && !back.classList.contains("lane__tw")) return back;
  const own = back && back.closest ? back.closest(".lane") : null;
  const lanes = own ? [own] : [..._lanes(ck)];
  for (const lane of lanes) {
    const link = lane.querySelector(".lane__link");
    if (_canFocus(link)) return link;
    for (const el of lane.querySelectorAll(_FOCUSABLE_SEL)) {
      if (!el.classList.contains("lane__tw") && _canFocus(el)) return el;
    }
  }
  return null;
}
function _switchTo(ck) {
  const s = S;
  if (!s || !s.open || ck === s.ck) return;
  if (!(_visible(_st.data)[ck] || []).length) return;
  const keys = FALLBACK_CHANNEL_ORDER;
  const dir = keys.indexOf(ck) > keys.indexOf(s.ck) ? 1 : -1;
  _savePos();                                          // (v4.9.3) 돌아오면 이 자리로
  _markReadAll(_visible(_st.data)[s.ck] || []);        // 멤버를 바꾸면 그 전 멤버는 읽음
  s.ck = ck;
  s.sig = L.sigOf(_visible(_st.data)[ck] || []);
  _head();
  _members(false);
  _renderFeed(true);
  const feed = s.feed;
  feed.classList.remove("is-swapping");
  feed.style.setProperty("--from", (dir * 24) + "px");   // 칩 방향에서 24px 미끄러져 들어온다
  void feed.offsetWidth;
  feed.classList.add("is-swapping");
}
/** 폴링 뒤: 시트가 열려 있으면 멤버 칩의 새 글 수는 늘 맞추고(v4.9.1 — 전엔 보고 있는 멤버 글이 그대로면 칩도 안 바뀌었다),
 *  글 목록은 표시 서명이 바뀐 때만 — 새 글만 끼우고(_patchFeed), 안 되면 다시 그린다. 트윗이 모두 사라졌으면 닫는다. */
function _refreshOpen() {
  const s = S;
  if (!s || !s.open) return;
  const list = _visible(_st.data)[s.ck];
  if (!list || !list.length) { _close(); return; }
  const grew = _members(true, true);
  if (grew.length) {
    _say(grew.map(({ ck, n }) => `${L.shortName((FALLBACK_CHANNELS[ck] || {}).name_ko) || ck} 새 글 ${n}개`).join(", "));
  }
  const sig = L.sigOf(list);
  if (sig === s.sig) return;
  s.sig = sig;
  _head();
  if (!_patchFeed(list)) _renderFeed(false);
}

/* ── 스크롤 잠금 · PC 팝업 위치 · 높이 (v4.9.1) ────────────────────────
   잠금: 스크롤바가 보이면 잠그는 동안 그 자리를 비워 둔다(html.tw-gutter = scrollbar-gutter: stable) —
   스크롤바가 사라지며 배경이 오른쪽으로 밀렸다 돌아오던 것(PC). 스크롤바가 화면 위에 겹치는 환경(폰 · macOS)은 폭이 0 이라 할 일 없음.
   위치 · 높이: 머리 줄을 잡아 옮기고(--tx · --ty, 열 때마다 가운데로), 위 · 아래 가장자리를 끌어 높이를 바꾼다.
   팝업은 가운데 기준(translate -50%)이라 높이만 바꾸면 위아래가 같이 늘어난다 — 한쪽을 d 끌면 높이는 2d.
   높이 = mew:twh(사용자가 정한 값, px) → 없으면 창의 90%. 창보다 크면 줄여 쓴다(저장값은 그대로). 폰 폭이면 쓰지 않는다. */
function _lock(on) {
  const root = document.documentElement;
  if (on) {
    if (innerWidth - root.clientWidth > 0) root.classList.add("tw-gutter");
    document.body.classList.add("tw-modal-open");
  } else {
    document.body.classList.remove("tw-modal-open");
    root.classList.remove("tw-gutter");
  }
}
function _savedH() {
  try { const v = Number(localStorage.getItem(HKEY)); return v > 0 ? v : 0; } catch { return 0; }
}
function _clampH(h) {
  const hi = innerHeight - 16, lo = Math.min(MIN_H, hi);
  return Math.round(Math.max(lo, Math.min(hi, h)));
}
/** 머리 줄은 늘 창 안에, 가로로는 80px 이상 창 안에 */
function _clampPos(tx, ty) {
  const s = S, vw = document.documentElement.clientWidth, vh = innerHeight;
  const w = s.sheet.offsetWidth, h = s.sheet.offsetHeight, hh = s.head.offsetHeight;
  const cx = vw / 2, cy = vh / 2;
  tx = Math.max(80 - (cx + w / 2), Math.min(vw - 80 - (cx - w / 2), tx));
  ty = Math.max(8 - (cy - h / 2), Math.min(vh - 8 - hh - (cy - h / 2), ty));
  return [Math.round(tx), Math.round(ty)];
}
function _geom() {
  const s = S, st = s.sheet.style;
  if (_mobile()) { st.height = ""; st.removeProperty("--tx"); st.removeProperty("--ty"); return; }
  st.height = _clampH(_savedH() || innerHeight * 0.9) + "px";
  [s.tx, s.ty] = _clampPos(s.tx, s.ty);
  st.setProperty("--tx", s.tx + "px");
  st.setProperty("--ty", s.ty + "px");
}
function _geoStart(el, id, cls) {
  try { el.setPointerCapture(id); } catch { /* 이미 놓았으면 무시 */ }
  S.sheet.classList.add("is-geo", cls);
  document.body.classList.add("no-select");
  if (cls === "is-sizing") document.body.classList.add("tw-ns");
}
function _geoMove(e) {
  const s = S, g = s.geo;
  if (e.pointerId !== g.id) return;
  if (g.kind === "move") {
    [s.tx, s.ty] = _clampPos(g.tx + e.clientX - g.x, g.ty + e.clientY - g.y);
    s.sheet.style.setProperty("--tx", s.tx + "px");
    s.sheet.style.setProperty("--ty", s.ty + "px");
  } else {
    const h = _clampH(g.h + 2 * (e.clientY - g.y) * g.dir);
    s.sheet.style.height = h + "px";
    const [tx, ty] = _clampPos(s.tx, s.ty);   // 옮겨 둔 팝업이 커져 머리 줄이 창 밖으로 나가면 그만큼만 밀어 넣는다
    if (tx !== s.tx || ty !== s.ty) {
      s.tx = tx; s.ty = ty;
      s.sheet.style.setProperty("--tx", tx + "px");
      s.sheet.style.setProperty("--ty", ty + "px");
    }
    _readout(h);
  }
}
function _geoEnd(e) {
  const s = S, g = s.geo;
  if (e.pointerId !== g.id) return;
  s.geo = null;
  if (g.kind === "size") {
    g.el.classList.remove("is-on");
    try { localStorage.setItem(HKEY, String(s.sheet.offsetHeight)); } catch { /* 저장 못 해도 이번 화면은 그대로 */ }
    _fadeEdges();
  }
  s.sheet.classList.remove("is-geo", "is-moving", "is-sizing");
  document.body.classList.remove("no-select", "tw-ns");
}
function _readout(h) {
  S.hread.textContent = `높이 ${Math.round(h)}px · 창의 ${Math.round((h / innerHeight) * 100)}%`;
}

/* ── 트윗 없는 네임플레이트를 눌렀을 때 ──────────────────────────────
   네임플레이트가 고개를 젓듯 흔들리고(.is-nope), 「OO의 새 트윗이 아직 없어요」가 1.7초 떴다 사라진다(.tw-nope). 진동 8ms. */
let _nopeEl = null, _nopeT = 0;
function _noTweet(target, ck) {
  if (!_reduce()) { target.classList.remove("is-nope"); void target.offsetWidth; target.classList.add("is-nope"); }
  vibrate(8);
  if (!_nopeEl) {
    _nopeEl = document.createElement("div");
    _nopeEl.className = "tw-nope";
    _nopeEl.setAttribute("role", "status");
    _nopeEl.addEventListener("animationend", () => _nopeEl.classList.remove("on"));
    document.body.appendChild(_nopeEl);
  }
  const name = L.shortName((FALLBACK_CHANNELS[ck] || {}).name_ko);
  _nopeEl.textContent = `${name ? name + "의 " : ""}새 트윗이 아직 없어요`;
  _nopeEl.classList.remove("on", "below");
  const r = target.getBoundingClientRect(), w = _nopeEl.offsetWidth, h = _nopeEl.offsetHeight;
  const left = Math.max(8, Math.min(innerWidth - w - 8, r.left + r.width / 2 - w / 2));
  const below = r.top - h - 10 < 8;
  _nopeEl.classList.toggle("below", below);
  _nopeEl.style.left = left + "px";
  _nopeEl.style.top = (below ? r.bottom + 10 : r.top - h - 10) + "px";
  _nopeEl.style.setProperty("--tail-x", Math.max(10, Math.min(w - 10, r.left + r.width / 2 - left)) + "px");
  void _nopeEl.offsetWidth;
  _nopeEl.classList.add("on");
  clearTimeout(_nopeT);
  _nopeT = setTimeout(() => _nopeEl.classList.remove("on"), 1800);
}

/* ── 이벤트 배선 (한 번만 — #board 는 세션 내내 같은 노드) ───────── */
function _wire() {
  const board = _st.board;
  _st.wired = true;
  // 클릭 — 캡처 단계에서 아바타 · 배지 · 이름을 잡아 앵커 기본 이동을 막고 시트를 연다. 레일 버튼(YouTube · X)은 그대로 통과.
  board.addEventListener("click", (e) => {
    const lane = e.target.closest(".lane");
    if (!lane || lane.hasAttribute("data-no-badge")) return;
    const ck = lane.dataset.channel;
    const plate = e.target.closest(".lane__tw, .lane__avatar, .lane__link, .tt__nm");
    if (!_visible(_st.data)[ck]) {                       // 트윗 없음 → 「새 트윗 없음」 알림(트윗 목록을 받은 뒤에만)
      if (plate && _st.data !== undefined) _noTweet(plate.closest(".lane__link, .tt__who") || plate, ck);
      return;
    }
    if (!plate) return;
    e.preventDefault();
    e.stopPropagation();
    _open(ck, plate);
  }, true);
}

/* ── public ─────────────────────────────────────────────────────── */
export function renderTweets(boardEl, data) {
  _st.board = boardEl;
  if (data !== undefined) _st.data = data;
  _apply();
}
export function reapplyTweets(boardEl) {
  _st.board = boardEl;
  _apply();
}

/* ── (소식 팝업 · 트윗 시트 공용) X 공식 카드 ─────────────────────────
   카드 만들기 · 불러오기 · 정리만 내보낸다. 테마 전환 · 높이 신호 · 15초 실패 링크는 같은 코드가 처리한다. */
/** X 카드 자리(숫자 id 면 임베드 자리, 아니면 「X에서 원문 보기」 링크). href = 원문 트윗 주소 */
export function makeXCard(id, href) { return _xCard({ id, url: href || "" }); }
/** root 안의 X 카드 자리를 지금 불러온다(iframe 생성) */
export function loadXCards(root) {
  if (!root) return;
  root.querySelectorAll(".lane__thread__xcard[data-id]").forEach(_loadCard);
}
/** root 안의 X 카드 iframe 을 지운다(닫을 때) */
export function stopXCards(root) { _stopCards(root); }
