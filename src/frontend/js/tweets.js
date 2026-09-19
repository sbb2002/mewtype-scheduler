// tweets.js — 예고판 상단 멤버 개인 트윗 "편지 배지" + 메신저형 스레드 (v3.1).
// tweets.json (계약 I): tweets[ck] = [ <메시지>, … ] 최신이 뒤, 유닛당 저장 상한 xtweet.MAX_THREAD.
//   화면에는 메시지별 expires_at(받은 시각 + 24h)이 안 지난 것을 최대 MAX_THREAD 건까지 노출 —
//   안 읽은 메시지 폭주 방지는 말풍선 스크롤(css: 2/3 뷰포트 높이 초과 시 스크롤)이 맡는다.
//   v2.8 단건(dict)도 _list() 가 [dict] 로 감싸 하위호환.
// 계약·목업: docs/plan/v2_8_personal_tweets.md · docs/SPEC.md §계약 I
//
//  renderTweets(boardEl, data)  — 폴링마다. data 를 캐시하고 배지를 재적용.
//  reapplyTweets(boardEl)       — renderBoard 직후. 캐시된 data 로 배지만 다시 붙임.
//
// PC: 아바타/배지 호버 = 스레드 패널 펼침, 클릭 = 고정(X/Esc/바깥클릭으로 닫힘), 여러 개 동시.
// 모바일: 배지 탭 = 상단 시트 + 백드롭. 배경 = 유닛 --lane-color, 글자색은 대비로 자동.
// 안 읽은 메시지 2건+ 이면 배지에 카운트. 만료·404·빈 파일이면 배지 안 뜬다.

import { FALLBACK_CHANNELS, FALLBACK_CHANNEL_ORDER } from "./config.js";

const ENV_CLOSED = '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M3 4.75h18c1.24 0 2.25 1.01 2.25 2.25v.63l-11.02 6.9a.8.8 0 0 1-.86 0L.75 7.63V7c0-1.24 1.01-2.25 2.25-2.25Z"/><path d="M23.25 9.75V17c0 1.24-1.01 2.25-2.25 2.25H3A2.25 2.25 0 0 1 .75 17V9.75l10.64 6.66a1.15 1.15 0 0 0 1.22 0l10.64-6.66Z"/></svg>';
const ENV_OPEN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2.75 10.5v8.25c0 1.1.9 2 2 2h14.5c1.1 0 2-.9 2-2V10.5"/><path d="M2.75 10.5 12 4l9.25 6.5"/><path d="m2.75 10.5 8.4 5.9c.51.36 1.19.36 1.7 0l8.4-5.9"/></svg>';
// 원문 링크 아이콘 = X (notice 의 x path 재활용).
const X_SVG = '<svg class="src__ic" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M18.9 2.6h3.3l-7.2 8.2 8.5 11.3h-6.7l-5.2-6.8-6 6.8H1.3l7.7-8.8L.7 2.6h6.9l4.7 6.2 5.6-6.2Zm-1.2 17.7h1.9L7.2 4.4H5.2l12.5 15.9Z"/></svg>';

const RKEY = "mew:twread";
const TLANG_KEY = "mew:tllang";  // ponytail: 번역 토글 기억
const READ_TTL_MS = 4 * 24 * 3600 * 1000;   // 읽음 기록 보존 4일(트윗 TTL 24h 훨씬 넘김)
const MAX_THREAD = 50;                       // 노출 상한(백엔드 xtweet.MAX_THREAD 와 동일)
const GROUP_GAP_MS = 2 * 60 * 1000;         // 연속 메시지 묶음 간격
const _st = { data: null, board: null, wired: false, pinned: new Set(), peek: null, bubbles: new Map(), tlang: "ko" };
let _toast = null, _backdrop = null;

/* ── 계약 I 하위호환: tweets[ck] → 메시지 배열 ───────────────────── */
function _list(v) {
  if (Array.isArray(v)) return v.filter((m) => m && m.text);
  if (v && typeof v === "object" && v.text) return [v];
  return [];
}

/* ── 읽음 상태 (뷰어별 localStorage) ─────────────────────────────────
   { id: readAtEpochMs }. 시간 기반으로만 정리한다 — "지금 안 보이는 id" 를
   즉시 지우면(v2 방식) 폴링이 잠깐 빈/오래된 tweets.json 을 물었을 때 읽음
   기록이 통째로 날아간다. 오래된 항목만 자연 소멸시킨다. */
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
function _isRead(id) { return !!_readMap()[id]; }
function _markReadAll(list) {
  const o = _readMap();
  let changed = false;
  for (const m of list || []) if (!o[m.id]) { o[m.id] = Date.now(); changed = true; }
  if (!changed) return;
  _writeMap(o);
  if (_st.board) _apply();          // 배지를 '열린 편지'로
}

/* ── 번역 언어 토글 (뷰어별 localStorage) — 디폴트 한글, 전역 ─────── */
function _getTlang() {
  try { return localStorage.getItem(TLANG_KEY) === "orig" ? "orig" : "ko"; } catch { return "ko"; }
}
function _setTlang(lang) {
  try { localStorage.setItem(TLANG_KEY, lang); } catch { /* private mode 등 */ }
  _st.tlang = lang;
}
function _tlOn() { return _st.tlang === "ko"; }
function _tlGlyph() { return _tlOn() ? "번역 ON" : "번역 OFF"; }
function _tlAria() { return _tlOn() ? "번역 끄기" : "번역 켜기"; }

/** 번역 ON/OFF 전환 - 열려 있는 모든 패널·시트에 반영. 재렌더하지 않는다(X 카드가 다시 로드되지 않게). */
function _flipLang() {
  _setTlang(_tlOn() ? "orig" : "ko");
  const vis = _visible(_st.data);
  for (const [ck, b] of _st.bubbles) _syncTl(b, vis[ck]);
  if (_toast) { const ck = _toast.dataset.ck; if (ck) _syncTl(_toast, vis[ck]); }
}

/* ── 유틸 ────────────────────────────────────────────────────────── */
function _mobile() {
  return window.matchMedia && window.matchMedia("(max-width: 767px)").matches;
}
/** data → { ck: [메시지…] }. 메시지별 expires_at(24h) 필터 + received_at 오름차순 + 상한(MAX_THREAD). */
function _visible(data) {
  const now = Date.now();
  const out = {};
  const t = (data && data.tweets) || {};
  for (const ck of Object.keys(t)) {
    const msgs = _list(t[ck])
      .filter((m) => { const e = Date.parse(m.expires_at); return isNaN(e) || e > now; })
      .sort((a, b) => (a.received_at || "").localeCompare(b.received_at || ""))
      .slice(-MAX_THREAD);
    if (msgs.length) out[ck] = msgs;
  }
  return out;
}
function _ago(iso) {
  const t = Date.parse(iso);
  if (isNaN(t)) return "";
  const m = Math.max(0, Math.round((Date.now() - t) / 60000));
  if (m < 1) return "방금";
  if (m < 60) return m + "분 전";
  const h = Math.round(m / 60);
  if (h < 24) return h + "시간 전";
  return Math.round(h / 24) + "일 전";
}
function _hm(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return "";
  try {
    return new Intl.DateTimeFormat("ko-KR", {
      timeZone: "Asia/Seoul", hour: "2-digit", minute: "2-digit", hour12: false,
    }).format(d);
  } catch { return ""; }
}
/** 유닛 색: 예고판 헤더가 아바타에서 추출해 넣는 --lane-color 재사용 + 대비로 글자색 결정. */
function _palette(laneEl) {
  const raw = laneEl ? getComputedStyle(laneEl).getPropertyValue("--lane-color").trim() : "";
  const m = raw.match(/(\d+)[ ,]+(\d+)[ ,]+(\d+)/);
  if (!m) return { bg: "#3a3a3e", ink: "#ffffff" };
  const [r, g, b] = [m[1], m[2], m[3]].map(Number);
  const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
  const L = 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
  return { bg: `rgb(${r} ${g} ${b})`, ink: L > 0.42 ? "#17171b" : "#ffffff" };
}
function _lanes(ck) {
  return _st.board ? _st.board.querySelectorAll(`.lane[data-channel="${CSS.escape(ck)}"]`) : [];
}
// 원문 앵커: 메시지 URL → 없으면 X 프로필(x.com/<handle>) → 둘 다 없으면 비활성. 유튜브로는 안 감.
function _setSrc(el, m) {
  const u = m.url || (m.handle ? "https://x.com/" + m.handle : "");
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

/* ── 트윗 = 번역 말풍선 + X 공식 카드 (v3.8.0b) ─────────────────────────────
   법률 자문에 따라 트윗의 요소(원문 텍스트·이미지·영상·참조 트윗의 미디어)를 우리가 다시 조립해 그리지 않는다.
   화면에는 ① 원문 트윗에 대한 번역(참조 트윗은 번역만, 안쪽 말풍선) ② X 공식 임베드 카드 ③ 디스클레이머만 나온다.
   원문·미디어는 X 카드가 보여 준다. 저장 데이터(tweets.json 의 text/media/quote/video)는 유지보수용으로 그대로 두되 화면에는 쓰지 않는다.
   X 카드는 iframe 이 필요한 높이를 twttr.private.resize 메시지로 알려주므로 그 값을 그대로 쓰고(상한 없음 - 패널 스크롤에 맡김),
   폭 250px 미만이면 렌더링 자체를 못 하므로(실측) PC 패널 폭을 320px 로 한다. 영상이 든 카드 여러 개를 한꺼번에 띄우면
   브라우저가 멈춰(실측) 화면에 들어올 때만(IntersectionObserver) 불러온다. */
const ISSUES_URL = "https://github.com/sbb2002/mewtype-scheduler/issues";
const FOOT_HTML = '비공식 팬 번역 · 비영리 운영 · 삭제 요청 시 예고 없이 서비스가 중단될 수 있습니다 · ' +
  '<a href="' + ISSUES_URL + '" target="_blank" rel="noopener">문의·삭제 요청 (GitHub Issues)</a>';
const EMBED_ORIGINS = ["https://platform.twitter.com", "https://platform.x.com"];
const CARD_EST_H = 230;          // 카드가 실제 높이를 알려주기 전 자리표시 높이(짧은 텍스트 트윗 실측)
const CARD_TIMEOUT_MS = 15000;   // 이 안에 렌더링 신호가 없으면 "X에서 보기" 링크를 띄운다
let _embedWired = false;

function _srcUrl(m) {
  return m.url || (m.handle ? "https://x.com/" + m.handle : "");
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
      const sc = wrap.closest(".lane__bubble__scroll, .tw-toast__scroll");
      const atBottom = sc && (sc.scrollHeight - sc.clientHeight - sc.scrollTop) < 8;
      wrap.style.height = h + "px";
      wrap.dataset.ready = "1";
      const fb = wrap.querySelector(".lane__thread__xlink");
      if (fb) fb.remove();
      if (atBottom) sc.scrollTop = sc.scrollHeight;    // 늦게 로드된 카드 때문에 맨 아래 고정이 풀리지 않게
    }
  });
}
function _isNumId(id) { return /^[0-9]{5,25}$/.test(String(id || "")); }
function _embedSrc(id) {
  return "https://platform.twitter.com/embed/Tweet.html?id=" + id + "&theme=dark&dnt=true&lang=ko&hideThread=true&frame=false";
}
function _loadCard(wrap) {
  if (wrap.querySelector("iframe")) return;
  _wireEmbedResize();
  const f = document.createElement("iframe");
  f.className = "lane__thread__embed";
  f.src = _embedSrc(wrap.dataset.id);
  f.title = "X 트윗";
  f.setAttribute("allow", "autoplay; fullscreen");
  f.setAttribute("allowfullscreen", "");
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
function _watchCards(scrollEl) {
  const cards = scrollEl.querySelectorAll(".lane__thread__xcard[data-id]");
  if (!cards.length) return;
  if (typeof IntersectionObserver === "undefined") { cards.forEach(_loadCard); return; }
  const io = new IntersectionObserver((entries) => {
    for (const en of entries) {
      if (!en.isIntersecting) continue;
      io.unobserve(en.target);
      _loadCard(en.target);
    }
  }, { root: scrollEl, rootMargin: "300px 0px" });
  scrollEl.__io = io;
  cards.forEach((c) => io.observe(c));
}
function _stopCards(root) {
  if (!root) return;
  const scrolls = root.querySelectorAll(".lane__bubble__scroll, .tw-toast__scroll");
  for (const sc of scrolls) { if (sc.__io) { sc.__io.disconnect(); sc.__io = null; } }
  for (const f of root.querySelectorAll("iframe.lane__thread__embed")) f.remove();
}
function _tlBubble(m) {
  const row = document.createElement("div");
  row.className = "lane__thread__msg";
  const lab = document.createElement("span");
  lab.className = "lab";
  lab.textContent = "번역";
  row.appendChild(lab);
  const tx = document.createElement("span");
  tx.className = "txt";
  tx.textContent = m.text_ko || "번역 준비 중…";      // 번역이 없으면 원문을 대신 보여 주지 않는다(재조립 금지)
  row.appendChild(tx);
  if (m.quote && m.quote.text) {                      // 참조 트윗은 번역 텍스트만 안쪽 말풍선으로 - 이미지 등 미디어는 X 카드에서
    const q = document.createElement("div");
    q.className = "lane__thread__quote";
    q.textContent = m.quote.text_ko || "번역 준비 중…";
    row.appendChild(q);
  }
  const a = document.createElement("a");
  a.className = "ori";
  a.target = "_blank";
  a.rel = "noopener";
  a.setAttribute("aria-label", "원문");
  a.innerHTML = X_SVG;
  _setSrc(a, m);
  row.appendChild(a);
  return row;
}
function _xCard(m) {
  const wrap = document.createElement("div");
  wrap.className = "lane__thread__xcard";
  const href = _srcUrl(m);
  if (_isNumId(m.id)) {
    wrap.dataset.id = m.id;
    if (href) wrap.dataset.href = href;
    wrap.style.height = CARD_EST_H + "px";
    const sk = document.createElement("div");
    sk.className = "lane__thread__xskel";
    sk.textContent = "X 카드 불러오는 중…";
    wrap.appendChild(sk);
  } else {                                            // 합성 id(숫자 아님)는 임베드할 수 없다 -> 링크만
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

/* ── 스레드 렌더 (말풍선·시트 공용) ──────────────────────────────── */
function _groupMsgs(list) {
  const out = [];
  for (const m of list) {
    const g = out[out.length - 1];
    const prev = g && g[g.length - 1];
    if (prev && Math.abs(Date.parse(m.received_at) - Date.parse(prev.received_at)) <= GROUP_GAP_MS) g.push(m);
    else out.push([m]);
  }
  return out;
}
function _renderThread(scrollEl, list) {
  if (!scrollEl) return;
  if (scrollEl.__io) { scrollEl.__io.disconnect(); scrollEl.__io = null; }
  scrollEl.textContent = "";
  const groups = _groupMsgs(list);
  groups.forEach((g, gi) => {
    const gw = document.createElement("div");
    gw.className = "lane__thread__grp";
    for (const m of g) {
      const unit = document.createElement("div");
      unit.className = "lane__thread__unit";
      unit.appendChild(_tlBubble(m));                 // 번역이 먼저(즉시 보임)
      unit.appendChild(_xCard(m));                    // X 공식 카드는 그 아래에서 뒤늦게 붙는다
      gw.appendChild(unit);
    }
    const last = g[g.length - 1];
    const tm = document.createElement("time");
    tm.className = "lane__thread__t";
    tm.dateTime = last.received_at || "";
    tm.textContent = _hm(last.received_at) + (gi === groups.length - 1 ? " · " + _ago(last.received_at) : "");
    gw.appendChild(tm);
    scrollEl.appendChild(gw);
  });
  scrollEl.scrollTop = scrollEl.scrollHeight;   // 최신이 아래 -> 열면 맨 아래
  _watchCards(scrollEl);
}
function _syncTl(container, list) {
  const btn = container.querySelector(".lane__bubble__tl, .tw-toast__tl");
  if (!btn) return;
  btn.hidden = !(list && list.some((m) => m.text_ko));
  btn.textContent = _tlGlyph();
  btn.setAttribute("aria-label", _tlAria());
  container.classList.toggle("tl-off", !_tlOn());     // CSS 가 번역 말풍선을 숨긴다
}

/* ── 배지 적용 ───────────────────────────────────────────────────── */
function _apply() {
  const board = _st.board;
  if (!board) return;
  const vis = _visible(_st.data);

  for (const ck of FALLBACK_CHANNEL_ORDER) {
    const list = vis[ck];
    for (const lane of _lanes(ck)) {
      const avatar = lane.querySelector(".lane__avatar");
      if (!avatar) continue;
      let badge = lane.querySelector(".lane__tw");
      if (!list || !list.length) {
        if (badge) badge.remove();
        continue;
      }
      const unreadN = list.reduce((n, m) => n + (_isRead(m.id) ? 0 : 1), 0);
      const unread = unreadN > 0;
      const sig = list.map((m) => m.id).join(",") + "|" + unreadN;
      const wantCls = unread ? "is-unread" : "is-read";
      // 같은 스레드 + 같은 읽음상태면 그대로 둔다(콩콩 애니메이션 유지).
      if (badge && badge.dataset.sig === sig && badge.classList.contains(wantCls)) continue;
      if (!badge) {
        badge = document.createElement("button");
        badge.type = "button";
        badge.className = "lane__tw";
        lane.querySelector(".lane__header").appendChild(badge);
      }
      badge.dataset.sig = sig;
      badge.classList.toggle("is-unread", unread);
      badge.classList.toggle("is-read", !unread);
      const nm = (FALLBACK_CHANNELS[ck] || {}).name_ko || ck;
      badge.setAttribute("aria-label",
        nm + (unread ? ` 읽지 않은 트윗 ${unreadN}건` : " 읽은 트윗") + ` (스레드 ${list.length}건)`);
      badge.innerHTML = unread ? ENV_CLOSED : ENV_OPEN;
      // 카운트 pill — 안 읽은 게 2건 이상일 때만
      if (unreadN >= 2) {
        const cnt = document.createElement("span");
        cnt.className = "lane__tw-count";
        cnt.textContent = String(unreadN);
        badge.appendChild(cnt);
      }
    }
  }

  // 열려 있던 패널 중 트윗이 사라졌으면 정리
  for (const ck of [..._st.pinned]) if (!vis[ck]) { _st.pinned.delete(ck); _closeBubble(ck); }
  if (_st.peek && !vis[_st.peek]) { _closeBubble(_st.peek); _st.peek = null; }
  for (const ck of _st.bubbles.keys()) _fillBubble(ck, vis[ck]);
  _repositionAll();

  if (!_st.wired) _wire();
}

/* ── PC 스레드 패널 (#board 에 absolute 로 얹음 — 헤더 overflow 클리핑 회피) ── */
function _bubble(ck) {
  let b = _st.bubbles.get(ck);
  if (b) return b;
  b = document.createElement("div");
  b.className = "lane__bubble";
  b.dataset.ck = ck;
  b.innerHTML =
    '<div class="lane__bubble__head">' +
      '<span class="lane__bubble__who"></span>' +
      '<span class="lane__bubble__ctrl">' +
        '<button class="lane__bubble__tl" type="button" hidden></button>' +
        '<button class="lane__bubble__x" type="button" aria-label="닫기">✕</button>' +
      '</span>' +
    '</div>' +
    '<div class="lane__bubble__scroll"></div>' +
    '<div class="lane__bubble__foot">' + FOOT_HTML + '</div>';
  b.querySelector(".lane__bubble__x").addEventListener("click", () => {
    _st.pinned.delete(ck);
    _closeBubble(ck);
  });
  b.querySelector(".lane__bubble__tl").addEventListener("click", () => { _flipLang(); return false; });
  _st.board.appendChild(b);
  _st.bubbles.set(ck, b);
  return b;
}
function _fillBubble(ck, list) {
  const b = _st.bubbles.get(ck);
  if (!b || !list || !list.length) return;
  const lane = _lanes(ck)[0];
  const pal = _palette(lane);
  b.style.setProperty("--tw-bg", pal.bg);
  b.style.setProperty("--tw-ink", pal.ink);
  b.querySelector(".lane__bubble__who").textContent = (FALLBACK_CHANNELS[ck] || {}).name_ko || ck;
  // 75초 폴링마다 열린 패널이 다시 채워진다 — 그때마다 다시 그리면 X 카드가 계속 재로드되므로(무겁고 깜빡임)
  // 표시 내용(id·번역)이 바뀐 경우에만 스레드를 다시 그린다.
  const sc = b.querySelector(".lane__bubble__scroll");
  const sig = list.map((m) => [m.id, m.text_ko || "", (m.quote && m.quote.text_ko) || ""].join("|")).join("~");
  if (b.__sig !== sig || !sc.firstChild) {
    _renderThread(sc, list);
    b.__sig = sig;
  }
  _syncTl(b, list);
}
function _positionBubble(ck) {
  const b = _st.bubbles.get(ck);
  const lane = _lanes(ck)[0];
  if (!b || !lane) return;
  const badge = lane.querySelector(".lane__tw") || lane.querySelector(".lane__avatar");
  const header = lane.querySelector(".lane__header");
  const rr = _st.board.getBoundingClientRect();
  let left = badge.getBoundingClientRect().left - rr.left + _st.board.scrollLeft;
  const top = header.getBoundingClientRect().bottom - rr.top + _st.board.scrollTop + 6;
  const maxLeft = _st.board.clientWidth - b.offsetWidth - 8;
  if (left > maxLeft) left = Math.max(4, maxLeft);
  b.style.left = left + "px";
  b.style.top = top + "px";
}
function _repositionAll() {
  for (const ck of _st.bubbles.keys()) _positionBubble(ck);
}
function _showBubble(ck) {
  const vis = _visible(_st.data);
  if (!vis[ck]) return;
  const b = _bubble(ck);
  _fillBubble(ck, vis[ck]);
  b.classList.toggle("is-pinned", _st.pinned.has(ck));
  requestAnimationFrame(() => {
    // 이 프레임이 오기 전에 닫힘 요청(빠른 호버-이탈 등)이 있었으면 다시 열지 않는다.
    if (!_st.pinned.has(ck) && _st.peek !== ck) return;
    _positionBubble(ck);
    b.classList.add("is-open");
    const s = b.querySelector(".lane__bubble__scroll");
    if (s) s.scrollTop = s.scrollHeight;          // 레이아웃 후 맨 아래 보정
  });
}
function _closeBubble(ck) {
  if (_st.pinned.has(ck) || _st.peek === ck) return;   // 아직 열려 있어야 함
  const b = _st.bubbles.get(ck);
  if (!b) return;
  _stopCards(b);                         // 패널을 닫으면 X 카드(재생 중인 영상 포함)도 지운다
  b.classList.remove("is-open");
  const done = () => {
    b.removeEventListener("transitionend", done);
    // 예약 후 다시 열렸으면(재호버/재클릭) 취소 — 지금 보이는 말풍선을 잘못 지우지 않게.
    if (_st.pinned.has(ck) || _st.peek === ck) return;
    b.remove();
    _st.bubbles.delete(ck);
  };
  b.addEventListener("transitionend", done);
  setTimeout(done, 260);
}
function _togglePin(ck) {
  if (_st.pinned.has(ck)) {
    _st.pinned.delete(ck);
    _closeBubble(ck);
  } else {
    _st.pinned.add(ck);
    _markReadAll(_visible(_st.data)[ck] || []);
    _showBubble(ck);
  }
}
function _closeAllPins() {
  for (const ck of [..._st.pinned]) { _st.pinned.delete(ck); _closeBubble(ck); }
}

/* ── 모바일 시트 ─────────────────────────────────────────────────── */
function _ensureToast() {
  if (_toast) return;
  _backdrop = document.createElement("div");
  _backdrop.className = "tw-backdrop";
  _backdrop.addEventListener("click", _closeToast);
  _toast = document.createElement("article");
  _toast.className = "tw-toast";
  _toast.setAttribute("role", "dialog");
  _toast.setAttribute("aria-modal", "true");
  _toast.innerHTML =
    '<div class="tw-toast__head">' +
      '<span class="tw-toast__avatar"></span>' +
      '<span class="tw-toast__id"><b class="nm"></b><span class="hd"></span></span>' +
      '<button class="tw-toast__tl" type="button" hidden></button>' +
      '<button class="tw-toast__x" type="button" aria-label="닫기">✕</button>' +
    '</div>' +
    '<div class="tw-toast__scroll"></div>' +
    '<div class="tw-toast__foot">' + FOOT_HTML + '</div>';
  _toast.querySelector(".tw-toast__x").addEventListener("click", _closeToast);
  _toast.querySelector(".tw-toast__tl").addEventListener("click", () => { _flipLang(); return false; });
  document.body.append(_backdrop, _toast);
}
function _openToast(ck) {
  const list = _visible(_st.data)[ck];
  if (!list || !list.length) return;
  _ensureToast();
  _toast.dataset.ck = ck;
  const lane = _lanes(ck)[0];
  const pal = _palette(lane);
  const meta = FALLBACK_CHANNELS[ck] || {};
  _toast.style.setProperty("--tw-bg", pal.bg);
  _toast.style.setProperty("--tw-ink", pal.ink);
  const av = _toast.querySelector(".tw-toast__avatar");
  av.style.backgroundImage = meta.avatar ? `url("${meta.avatar}")` : "none";
  _toast.querySelector(".nm").textContent = meta.name_ko || ck;
  const lastHandle = list[list.length - 1].handle;
  _toast.querySelector(".hd").textContent = lastHandle ? "@" + lastHandle : "";
  const sc = _toast.querySelector(".tw-toast__scroll");
  _renderThread(sc, list);
  _syncTl(_toast, list);
  document.body.classList.add("tw-modal-open");
  requestAnimationFrame(() => { sc.scrollTop = sc.scrollHeight; });
  _markReadAll(list);
}
function _closeToast() {
  _stopCards(_toast);
  document.body.classList.remove("tw-modal-open");
}

/* ── 이벤트 배선 (한 번만 — #board 는 세션 내내 같은 노드) ───────── */
function _wire() {
  const board = _st.board;
  _st.wired = true;

  // 클릭 — 캐러셀 클론 포함 위임. 캡처 단계에서 앵커(.lane__link) 기본 내비를 가로챈다.
  board.addEventListener("click", (e) => {
    const lane = e.target.closest(".lane");
    if (!lane) return;
    const ck = lane.dataset.channel;
    if (!_visible(_st.data)[ck]) return;                 // 트윗 없음 → 유튜브 그대로
    if (!e.target.closest(".lane__tw, .lane__avatar")) return;  // 이름·레일 등 → 그대로
    e.preventDefault();
    e.stopPropagation();
    if (_mobile()) { _openToast(ck); return; }
    // 호버로 열려 있던/열리던 중이었어도 클릭은 항상 고정(pinned) 패널로 넘긴다 —
    // 같은 노드를 그대로 재사용(_bubble)하므로 끊김 없이 이어짐.
    if (_st.peek === ck) _st.peek = null;
    _togglePin(ck);
  }, true);

  // PC 호버 — 있는 동안 펼침. 이미 열려있거나(peek) 고정돼(pinned) 있으면 재진입 무시
  // (열리는 애니메이션 도중 재호버/재클릭으로 상태가 꼬이는 걸 막음 — 애초에 트리거를 잠근다).
  board.addEventListener("pointerover", (e) => {
    if (_mobile()) return;
    const lane = e.target.closest(".lane");
    if (!lane || !e.target.closest(".lane__tw, .lane__avatar")) return;
    const ck = lane.dataset.channel;
    if (!_visible(_st.data)[ck]) return;
    if (_st.pinned.has(ck) || _st.peek === ck) return;
    _st.peek = ck;
    _showBubble(ck);
  });
  // 레인 밖으로 나가도 그 채널의 말풍선 패널(.lane__bubble, #board 의 형제 노드라
  // lane.contains() 로는 못 잡음)로 이동한 거면 유지 — 패널 위에서 스크롤·번역 버튼
  // 클릭이 가능해야 하므로. 패널에서 레인으로 되돌아가는 경우도 동일하게 유지.
  board.addEventListener("pointerout", (e) => {
    const lane = e.target.closest(".lane");
    const bubbleEl = e.target.closest(".lane__bubble");
    if (!lane && !bubbleEl) return;
    const ck = lane ? lane.dataset.channel : bubbleEl.dataset.ck;
    if (_st.peek !== ck) return;   // 이 채널이 호버로 열린 상태가 아니면(핀 등) 상관 안 함
    const rt = e.relatedTarget;
    const laneEl = lane || _lanes(ck)[0];
    const b = _st.bubbles.get(ck);
    if (rt && ((laneEl && laneEl.contains(rt)) || (b && b.contains(rt)))) return;
    _st.peek = null;
    _closeBubble(ck);
  });

  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    _closeAllPins();
    _closeToast();
  });
  document.addEventListener("click", (e) => {
    if (e.target.closest(".lane__tw, .lane__avatar, .lane__bubble")) return;
    _closeAllPins();
  });
  window.addEventListener("resize", () => {
    if (_mobile()) _closeAllPins();
    else _repositionAll();
  });
}

/* ── public ─────────────────────────────────────────────────────── */
export function renderTweets(boardEl, data) {
  _st.board = boardEl;
  _st.tlang = _getTlang();
  if (data !== undefined) _st.data = data;
  _apply();
}
export function reapplyTweets(boardEl) {
  _st.board = boardEl;
  _st.tlang = _getTlang();
  _apply();
}
