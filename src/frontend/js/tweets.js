// tweets.js — 예고판 상단 멤버 개인 트윗 "편지 배지" (v2.8).
// tweets.json 을 읽어 각 유닛 아바타 우상단에 파란 편지 배지를 붙인다.
// 계약·목업: docs/plan/v2_8_personal_tweets.md
//
//  renderTweets(boardEl, data)  — 폴링마다. data 를 캐시하고 배지를 재적용.
//  reapplyTweets(boardEl)       — renderBoard 직후. 캐시된 data 로 배지만 다시 붙임.
//
// PC: 아바타/배지 호버 = 말풍선 펼침, 클릭 = 고정(X/Esc/바깥클릭으로 닫힘), 여러 개 동시 열림.
// 모바일: 배지 탭 = 상단 토스트(메신저 알림풍) + 백드롭. 배경 = 유닛 --lane-color, 글자색은 대비로 자동.
// 만료(expires_at 지남)·404·빈 파일이면 배지 안 뜬다.

import { FALLBACK_CHANNELS, FALLBACK_CHANNEL_ORDER } from "./config.js";

const ENV_CLOSED = '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M3 4.75h18c1.24 0 2.25 1.01 2.25 2.25v.63l-11.02 6.9a.8.8 0 0 1-.86 0L.75 7.63V7c0-1.24 1.01-2.25 2.25-2.25Z"/><path d="M23.25 9.75V17c0 1.24-1.01 2.25-2.25 2.25H3A2.25 2.25 0 0 1 .75 17V9.75l10.64 6.66a1.15 1.15 0 0 0 1.22 0l10.64-6.66Z"/></svg>';
const ENV_OPEN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2.75 10.5v8.25c0 1.1.9 2 2 2h14.5c1.1 0 2-.9 2-2V10.5"/><path d="M2.75 10.5 12 4l9.25 6.5"/><path d="m2.75 10.5 8.4 5.9c.51.36 1.19.36 1.7 0l8.4-5.9"/></svg>';

const RKEY = "mew:twread";
const TLANG_KEY = "mew:tllang";  // ponytail: 번역 토글 기억
const _st = { data: null, board: null, wired: false, pinned: new Set(), peek: null, bubbles: new Map(), tlang: "orig" };
let _toast = null, _backdrop = null;

/* ── 읽음 상태 (뷰어별 localStorage) ─────────────────────────────── */
function _readMap() {
  try { return JSON.parse(localStorage.getItem(RKEY) || "{}") || {}; } catch { return {}; }
}
function _writeMap(o) {
  try { localStorage.setItem(RKEY, JSON.stringify(o)); } catch { /* private mode 등 */ }
}
function _isRead(id) { return !!_readMap()[id]; }
function _markRead(id) {
  const o = _readMap();
  if (o[id]) return;
  o[id] = 1;
  _writeMap(o);
  if (_st.board) _apply();          // 배지를 '열린 편지'로
}

/* ── 번역 언어 토글 (뷰어별 localStorage) ──────────────────────────── */
function _getTlang() {
  try { return localStorage.getItem(TLANG_KEY) || "orig"; } catch { return "orig"; }
}
function _setTlang(lang) {
  try { localStorage.setItem(TLANG_KEY, lang); } catch { /* private mode 등 */ }
  _st.tlang = lang;
}

/* ── 유틸 ────────────────────────────────────────────────────────── */
function _mobile() {
  return window.matchMedia && window.matchMedia("(max-width: 767px)").matches;
}
function _visible(data) {
  const now = Date.now();
  const out = {};
  const t = (data && data.tweets) || {};
  for (const ck of Object.keys(t)) {
    const n = t[ck];
    if (!n || !n.text) continue;
    const e = Date.parse(n.expires_at);
    if (!isNaN(e) && e <= now) continue;
    out[ck] = n;
  }
  return out;
}
function _esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
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
function _channelUrl(ck) {
  return (FALLBACK_CHANNELS[ck] || {}).channel_url || "#";
}
// 원문 링크: 실제 트윗 URL → 없으면 X 프로필(수동 ingest 는 트윗 URL 이 없음) → 채널.
function _srcUrl(t, ck) {
  if (t.url) return t.url;
  if (t.handle) return "https://x.com/" + t.handle;
  return _channelUrl(ck);
}

/* ── 배지 적용 ───────────────────────────────────────────────────── */
function _apply() {
  const board = _st.board;
  if (!board) return;
  const vis = _visible(_st.data);
  const validIds = new Set(Object.values(vis).map((n) => n.id));

  // 읽음맵 정리 (현재 안 보이는 트윗 id 제거)
  const rm = _readMap();
  let pruned = false;
  for (const k of Object.keys(rm)) if (!validIds.has(k)) { delete rm[k]; pruned = true; }
  if (pruned) _writeMap(rm);

  for (const ck of FALLBACK_CHANNEL_ORDER) {
    const t = vis[ck];
    for (const lane of _lanes(ck)) {
      const avatar = lane.querySelector(".lane__avatar");
      if (!avatar) continue;
      let badge = lane.querySelector(".lane__tw");
      if (!t) {
        if (badge) badge.remove();
        continue;
      }
      const unread = !_isRead(t.id);
      const wantCls = unread ? "is-unread" : "is-read";
      // 같은 트윗 + 같은 읽음상태면 그대로 둔다(콩콩 애니메이션 유지).
      if (badge && badge.dataset.twId === t.id && badge.classList.contains(wantCls)) continue;
      if (!badge) {
        badge = document.createElement("button");
        badge.type = "button";
        badge.className = "lane__tw";
        lane.querySelector(".lane__header").appendChild(badge);
      }
      badge.dataset.twId = t.id;
      badge.classList.toggle("is-unread", unread);
      badge.classList.toggle("is-read", !unread);
      badge.setAttribute("aria-label",
        ((FALLBACK_CHANNELS[ck] || {}).name_ko || ck) + (unread ? " 읽지 않은 트윗" : " 읽은 트윗"));
      badge.innerHTML = unread ? ENV_CLOSED : ENV_OPEN;
    }
  }

  // 열려 있던 말풍선 중 트윗이 사라졌으면 정리
  for (const ck of [..._st.pinned]) if (!vis[ck]) { _st.pinned.delete(ck); _closeBubble(ck); }
  if (_st.peek && !vis[_st.peek]) { _closeBubble(_st.peek); _st.peek = null; }
  for (const ck of _st.bubbles.keys()) _fillBubble(ck, vis[ck]);
  _repositionAll();

  if (!_st.wired) _wire();
}

/* ── PC 말풍선 (#board 에 absolute 로 얹음 — 헤더 overflow 클리핑 회피) ── */
function _bubble(ck) {
  let b = _st.bubbles.get(ck);
  if (b) return b;
  b = document.createElement("div");
  b.className = "lane__bubble";
  b.dataset.ck = ck;
  b.innerHTML =
    '<button class="lane__bubble__x" type="button" aria-label="닫기">✕</button>' +
    '<p class="lane__bubble__text"></p>' +
    '<div class="lane__bubble__foot"><span class="ago"></span>' +
    '<a class="src" target="_blank" rel="noopener">원문 →</a></div>';
  b.querySelector(".lane__bubble__x").addEventListener("click", () => {
    _st.pinned.delete(ck);
    _closeBubble(ck);
  });
  _st.board.appendChild(b);
  _st.bubbles.set(ck, b);
  return b;
}
function _fillBubble(ck, t) {
  const b = _st.bubbles.get(ck);
  if (!b || !t) return;
  const lane = _lanes(ck)[0];
  const pal = _palette(lane);
  b.style.setProperty("--tw-bg", pal.bg);
  b.style.setProperty("--tw-ink", pal.ink);

  const hasKo = !!t.text_ko;
  const text = _st.tlang === "ko" && hasKo ? t.text_ko : t.text;
  b.querySelector(".lane__bubble__text").textContent = text;
  b.querySelector(".ago").textContent = _ago(t.received_at);
  b.querySelector(".src").href = _srcUrl(t, ck);

  // 번역 토글 버튼
  let btn = b.querySelector(".lane__bubble__tl");
  if (hasKo) {
    if (!btn) {
      btn = document.createElement("button");
      btn.type = "button";
      btn.className = "lane__bubble__tl";
      btn.setAttribute("aria-label", "원문/번역");
      btn.onclick = () => { _toggleTlang(ck, b, t); return false; };
      b.querySelector(".lane__bubble__foot").insertBefore(btn, b.querySelector(".src"));
    }
    btn.textContent = _st.tlang === "ko" ? "원문" : "번역";
  } else if (btn) {
    btn.remove();
  }
}

function _toggleTlang(ck, b, t) {
  _setTlang(_st.tlang === "ko" ? "orig" : "ko");
  const text = _st.tlang === "ko" ? t.text_ko : t.text;
  b.querySelector(".lane__bubble__text").textContent = text;
  b.querySelector(".lane__bubble__tl").textContent = _st.tlang === "ko" ? "원문" : "번역";
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
  requestAnimationFrame(() => { _positionBubble(ck); b.classList.add("is-open"); });
}
function _closeBubble(ck) {
  if (_st.pinned.has(ck) || _st.peek === ck) return;   // 아직 열려 있어야 함
  const b = _st.bubbles.get(ck);
  if (!b) return;
  b.classList.remove("is-open");
  const done = () => { b.remove(); _st.bubbles.delete(ck); b.removeEventListener("transitionend", done); };
  b.addEventListener("transitionend", done);
  setTimeout(done, 260);
}
function _togglePin(ck) {
  if (_st.pinned.has(ck)) {
    _st.pinned.delete(ck);
    _closeBubble(ck);
  } else {
    _st.pinned.add(ck);
    _markRead(_visible(_st.data)[ck].id);
    _showBubble(ck);
  }
}
function _closeAllPins() {
  for (const ck of [..._st.pinned]) { _st.pinned.delete(ck); _closeBubble(ck); }
}

/* ── 모바일 토스트 ───────────────────────────────────────────────── */
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
      '<button class="tw-toast__x" type="button" aria-label="닫기">✕</button>' +
    '</div>' +
    '<p class="tw-toast__text"></p>' +
    '<div class="tw-toast__foot"><span class="ago"></span>' +
    '<a class="src" target="_blank" rel="noopener">원문 보기 →</a></div>';
  _toast.querySelector(".tw-toast__x").addEventListener("click", _closeToast);
  document.body.append(_backdrop, _toast);
}
function _openToast(ck) {
  const t = _visible(_st.data)[ck];
  if (!t) return;
  _ensureToast();
  const lane = _lanes(ck)[0];
  const pal = _palette(lane);
  const meta = FALLBACK_CHANNELS[ck] || {};
  _toast.style.setProperty("--tw-bg", pal.bg);
  _toast.style.setProperty("--tw-ink", pal.ink);
  const av = _toast.querySelector(".tw-toast__avatar");
  av.style.backgroundImage = meta.avatar ? `url("${meta.avatar}")` : "none";
  _toast.querySelector(".nm").textContent = meta.name_ko || ck;
  _toast.querySelector(".hd").textContent = t.handle ? "@" + t.handle : "";

  const hasKo = !!t.text_ko;
  const text = _st.tlang === "ko" && hasKo ? t.text_ko : t.text;
  _toast.querySelector(".tw-toast__text").textContent = text;
  _toast.querySelector(".ago").textContent = _ago(t.received_at);
  _toast.querySelector(".src").href = _srcUrl(t, ck);

  // 번역 토글 버튼
  let btn = _toast.querySelector(".tw-toast__tl");
  if (hasKo) {
    if (!btn) {
      btn = document.createElement("button");
      btn.type = "button";
      btn.className = "tw-toast__tl";
      btn.setAttribute("aria-label", "원문/번역");
      btn.onclick = () => { _toggleToastTlang(t); return false; };
      _toast.querySelector(".tw-toast__foot").insertBefore(btn, _toast.querySelector(".src"));
    }
    btn.textContent = _st.tlang === "ko" ? "원문" : "번역";
  } else if (btn) {
    btn.remove();
  }

  document.body.classList.add("tw-modal-open");
  _markRead(t.id);
}

function _toggleToastTlang(t) {
  _setTlang(_st.tlang === "ko" ? "orig" : "ko");
  const text = _st.tlang === "ko" ? t.text_ko : t.text;
  _toast.querySelector(".tw-toast__text").textContent = text;
  const btn = _toast.querySelector(".tw-toast__tl");
  if (btn) btn.textContent = _st.tlang === "ko" ? "원문" : "번역";
}
function _closeToast() {
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
    if (!e.target.closest(".lane__tw, .lane__avatar")) return;  // 이름 등 → 유튜브 그대로
    e.preventDefault();
    e.stopPropagation();
    if (_mobile()) _openToast(ck);
    else _togglePin(ck);
  }, true);

  // PC 호버 — 있는 동안 펼침
  board.addEventListener("pointerover", (e) => {
    if (_mobile()) return;
    const lane = e.target.closest(".lane");
    if (!lane || !e.target.closest(".lane__tw, .lane__avatar")) return;
    const ck = lane.dataset.channel;
    if (!_visible(_st.data)[ck]) return;
    _st.peek = ck;
    _showBubble(ck);
  });
  board.addEventListener("pointerout", (e) => {
    const lane = e.target.closest(".lane");
    if (!lane) return;
    if (e.relatedTarget && lane.contains(e.relatedTarget)) return;  // 레인 안 이동
    const ck = lane.dataset.channel;
    if (_st.peek === ck) { _st.peek = null; _closeBubble(ck); }
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
