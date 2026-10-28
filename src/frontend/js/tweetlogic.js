// tweetlogic.js — 트윗 시트(멤버 트윗 보기 창)의 순수 로직. DOM · window · config.js 를 쓰지 않는다.
// tweets.js 가 가져다 쓰고, tweetlogic.selfcheck.mjs 가 node 에서 직접 검사한다(V1-C).
//
// 여기 있는 것: 글타래 묶기 · 끌어올리기(chains) · 첨부 개수 문구(attachments) · 글자색 · 번역 칸 바탕(paletteFor) ·
//   시각 표기(KST) · 카드 자리 높이 어림(estimateCardH) · 새 글 자리(firstUnread) · 면 저장값(mew:tllang ↔ 면 번호) · 표시 서명(sigOf) ·
//   열린 시트 갱신 계획(reconcileUnits — 새 글만 끼우기) ·
//   (v4.9.3) 번역 면 미디어 격자 · X 카드 치수로 두 면 위치 맞추기(predictCardH · xTextH) · 스크롤 자리 · ↓ 동그라미 · 밀기 판정 · 날짜 구분선.

export const KST_MS = 9 * 3600e3;
export const CARD_EST_H = 230;          // X 카드가 높이를 알려주기 전 자리 높이(짧은 텍스트 트윗 실측)
export const FALLBACK_BG = "#3a3a3e";   // 레인 색이 없을 때 바탕
export const INK_DARK = "#17171b";
export const INK_LIGHT = "#ffffff";
const TW_EPOCH_MS = 1288834974657;      // X Snowflake 기준 시각(ms)

/* ── 게시 시각 ─────────────────────────────────────────────────────────
   posted_at → Snowflake id 에서 계산 → 못 얻으면 "" (호출하는 쪽이 받은 시각 received_at 으로 대신하고 「등록」으로 구분).
   BigInt 리터럴(22n)은 쓰지 않는다 — 지원 안 하는 브라우저에서 모듈 전체가 죽지 않게. */
export function postedIso(m) {
  if (!m) return "";
  if (m.posted_at) return m.posted_at;
  const id = String(m.id || "");
  if (/^\d{15,}$/.test(id) && typeof BigInt === "function") {
    try {
      const ms = Number(BigInt(id) >> BigInt(22)) + TW_EPOCH_MS;
      return new Date(ms).toISOString().replace(/\.\d{3}Z$/, "Z");
    } catch { /* 아래 빈 값 */ }
  }
  return "";
}
/** 표시 · 정렬에 쓰는 시각 문자열 — 게시 시각 우선, 없으면 받은 시각 */
export function whenIso(m) { return postedIso(m) || (m && m.received_at) || ""; }
/** 정렬용 ms (못 읽으면 0) */
export function tOf(m) { return Date.parse(whenIso(m)) || 0; }

/* ── 글타래 묶기 · 끌어올리기 ─────────────────────────────────────────
   reply_to_id 가 목록 안 글이면 같은 글타래(뿌리까지). 글타래 안은 게시 시각순, 글타래 자리 = 가장 늦은 글 시각
   (답글이 달리면 글타래가 맨 아래로 올라온다). 원글이 목록에 없으면 답글은 혼자.
   순환(서로 가리킴 · 자기 자신)은 그 글을 혼자 둔다 — 무한 반복 없음.
   반환: [ [글, 글, …], … ] — 안쪽 배열 하나가 한 덩어리(글타래 또는 단독 글), 화면 위에서 아래 순서. */
export function chains(list) {
  const byId = new Map();
  for (const m of list || []) if (m && m.id != null) byId.set(String(m.id), m);
  const rootOf = (m) => {
    const seen = new Set([String(m.id)]);
    let cur = m;
    for (;;) {
      const pid = cur.reply_to_id ? String(cur.reply_to_id) : "";
      if (!pid || !byId.has(pid)) return cur;   // 원글 없음 · 남의 글 · 옛 데이터
      if (seen.has(pid)) return m;              // 순환 → 이 글은 혼자
      seen.add(pid);
      cur = byId.get(pid);
    }
  };
  const groups = new Map();
  for (const m of list || []) {
    if (!m) continue;
    const key = String(rootOf(m).id);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(m);
  }
  const units = [...groups.values()].map((u) => u.sort((a, b) => tOf(a) - tOf(b)));
  units.sort((a, b) => tOf(a[a.length - 1]) - tOf(b[b.length - 1]));
  return units;
}

/* ── 첨부 세기 ────────────────────────────────────────────────────────
   media · quote.media 는 URL 목록. 영상은 썸네일 URL 로만 저장된다(video_thumb · amplify 가 들어간 주소). 나머지 = 사진.
   (v4.9.3) 번역 면에 미디어를 그리게 되어 개수 문구는 글의 화면 낭독용 이름에만 쓴다. */
export function isVideoUrl(u) { return /video_thumb|amplify/.test(String(u || "")); }
function _kinds(urls) {
  let p = 0, v = 0;
  for (const u of Array.isArray(urls) ? urls : []) { if (isVideoUrl(u)) v++; else p++; }
  return { p, v };
}
/** → { text: "사진 2장 · 인용 글 사진 1장", photo: 전체 사진 수, video: 전체 영상 수 }. 아무것도 없으면 text "" */
export function attachments(m) {
  const own = _kinds(m && m.media), q = _kinds(m && m.quote && m.quote.media), parts = [];
  if (own.p) parts.push(`사진 ${own.p}장`);
  if (own.v) parts.push(`영상 ${own.v}개`);
  if (q.p || q.v) parts.push("인용 글 " + [q.p ? `사진 ${q.p}장` : "", q.v ? `영상 ${q.v}개` : ""].filter(Boolean).join(" · "));
  return { text: parts.join(" · "), photo: own.p + q.p, video: own.v + q.v };
}

/* ── 색 · 대비 ────────────────────────────────────────────────────────
   글자색 = 검정 · 흰색 중 바탕과 대비가 더 큰 쪽(「밝기 0.42 기준」은 중간 밝기 색에서 대비가 4.5:1 아래로 떨어졌다).
   번역 칸 바탕(--paper) = 글자와 반대쪽으로 섞는다. */
export function parseRgb(s) {
  const m = String(s || "").match(/(\d+(?:\.\d+)?)[\s,]+(\d+(?:\.\d+)?)[\s,]+(\d+(?:\.\d+)?)/);
  return m ? [+m[1], +m[2], +m[3]] : null;
}
function _lum(r, g, b) {
  const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}
export function contrast(l1, l2) { const hi = Math.max(l1, l2), lo = Math.min(l1, l2); return (hi + 0.05) / (lo + 0.05); }
/** 바탕 rgb 문자열("rgb(225 187 139)" · "225,187,139") → 글자색. 못 읽으면 흰색(폴백 바탕이 어두운 색이라 흰색이 맞다) */
export function inkFor(rgb) {
  const c = parseRgb(rgb);
  if (!c) return INK_LIGHT;
  const L = _lum(c[0], c[1], c[2]);
  const dark = _lum(23, 23, 27);   // #17171b
  return contrast(L, dark) >= contrast(L, 1) ? INK_DARK : INK_LIGHT;
}
/** 글자색 → 번역 칸 바탕. 검정 글자면 밝게, 흰 글자면 어둡게 */
export function paperFor(ink) { return ink === INK_DARK ? "rgba(255, 255, 255, 0.38)" : "rgba(0, 0, 0, 0.2)"; }
/** 레인 색 문자열 → { bg, ink, paper }. 색이 없으면 폴백 바탕(#3a3a3e) */
export function paletteFor(rgb) {
  const c = parseRgb(rgb);
  const bg = c ? `rgb(${c[0]} ${c[1]} ${c[2]})` : FALLBACK_BG;
  const ink = inkFor(c ? bg : "");
  return { bg, ink, paper: paperFor(ink) };
}

/* ── 시각 표기 (KST) ──────────────────────────────────────────────── */
export function kstParts(ms) {
  const d = new Date(ms + KST_MS);
  return { y: d.getUTCFullYear(), mo: d.getUTCMonth() + 1, d: d.getUTCDate(), h: d.getUTCHours(), mi: d.getUTCMinutes() };
}
const _p2 = (n) => String(n).padStart(2, "0");
export function hmLabel(ms) { const p = kstParts(ms); return `${_p2(p.h)}:${_p2(p.mi)}`; }
export function isSameKstDay(a, b) {
  const x = kstParts(a), y = kstParts(b);
  return x.y === y.y && x.mo === y.mo && x.d === y.d;
}
/** 방금 · N분 전 · N시간 전 · N일 전 */
export function agoLabel(ms, now) {
  const m = Math.max(0, Math.round((now - ms) / 60000));
  if (m < 1) return "방금";
  if (m < 60) return `${m}분 전`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}시간 전`;
  return `${Math.floor(h / 24)}일 전`;
}
/** 시각 부분: 오늘(KST) = HH:MM, 그 밖 = M/D HH:MM */
export function clockLabel(ms, now) {
  if (isSameKstDay(ms, now)) return hmLabel(ms);
  const p = kstParts(ms);
  return `${p.mo}/${p.d} ${hmLabel(ms)}`;
}
/** 글 하나의 시각 줄: 「HH:MM · N분 전」 · 「M/D HH:MM · N시간 전」 */
export function postedLabel(ms, now) { return `${clockLabel(ms, now)} · ${agoLabel(ms, now)}`; }
/** 간격 문구(답글): 「30분 뒤」 · 「7시간 31분 뒤」 · 「2일 뒤」 */
export function gapLabel(diffMs) {
  const m = Math.max(0, Math.round(diffMs / 60000));
  if (m < 60) return `${m}분 뒤`;
  const hh = Math.floor(m / 60), mm = m % 60;
  if (hh < 24) return `${hh}시간${mm ? ` ${mm}분` : ""} 뒤`;
  return `${Math.floor(hh / 24)}일 뒤`;
}
/** 답글 시각 줄: 「이어서 · 시각 · 간격」 (간격 = 바로 위 글과의 차이) */
export function replyLabel(ms, prevMs, now) { return `이어서 · ${clockLabel(ms, now)} · ${gapLabel(ms - prevMs)}`; }
/** 게시 시각을 모르는 글: 「HH:MM 등록」 */
export function unpostedLabel(ms) { return `${hmLabel(ms)} 등록`; }

/* ── 카드 자리 높이 어림 ─────────────────────────────────────────────
   X 카드는 불러오기 전에 자리를 잡아 둔다. 사진 · 인용 여부로 대략 맞춘다(실제 높이는 X 가 알려준다). */
export function estimateCardH(m) {
  let h = CARD_EST_H;
  const own = _kinds(m && m.media), q = _kinds(m && m.quote && m.quote.media);
  const n = own.p + own.v;
  if (n === 1) h += 180;
  else if (n >= 2) h += 200;
  if (m && m.quote) { h += 90; if (q.p + q.v > 0) h += 150; }
  return h;
}

/* ── 번역 면 미디어 · 두 면 위치 맞추기 (v4.9.3) ─────────────────────────
   번역 면에 사진 · 영상(썸네일)을 X 카드와 같은 격자로 그리고, 번역 면 칸들이 X 카드의 같은 칸과 같은 높이에 오게 한다.
   X 카드 실측(2026-10-28, 카드 폭 362 · 512 · 548px 에서 같음 — 폭과 무관):
     테두리 1 · 안쪽 위 12 / 옆 16 · 머리 줄 48 · 12 뒤 (답글이면 「님에게 보내는 답글」 24 뒤) 본문 20px/24px ·
     12 뒤 미디어(2~4칸 = 16:9 묶음, 1칸 = 원래 비율 · 세로는 정사각형, 칸 사이 2 · 테두리 1) ·
     12 뒤 인용 상자(테두리 1 · 여백 12 · 이름 줄 26 · 본문 15px/20px · 12 뒤 미디어를 아래에 붙임(테두리 없음), 미디어 없으면 여백 12) ·
     8 뒤 시각 줄 20 · 그 아래 100(반응 · 답글 버튼 · 아래 테두리 — 7개 글에서 모두 같음). */
export const XM = { border: 1, pad: 12, side: 16, head: 48, gap: 12, reply: 24, qPad: 12, qHead: 26, timeGap: 8, time: 20, below: 100 };

/** URL 목록 → [{ url, video }] (영상 = 썸네일 주소) */
export function mediaItems(urls) {
  return (Array.isArray(urls) ? urls : []).filter((u) => typeof u === "string" && u).map((u) => ({ url: u, video: isVideoUrl(u) }));
}
/** pbs.twimg.com 그림은 작은 크기(name=small)로 요청한다. 다른 주소는 그대로 */
export function smallUrl(u) {
  const s = String(u || "");
  if (!/^https:\/\/pbs\.twimg\.com\//.test(s)) return s;
  if (/[?&]name=/.test(s)) return s.replace(/([?&]name=)[^&]*/, "$1small");
  return s + (s.includes("?") ? "&" : "?") + "name=small";
}
/** 칸 수 → { cls: "g1"~"g4" (없으면 ""), shown: 그릴 칸 수(최대 4), more: 넷째 칸에 붙일 「+N」 } — X 는 글 하나에 최대 4개 */
export function gridOf(n) {
  const k = Math.max(0, Math.floor(Number(n) || 0)), shown = Math.min(4, k);
  return { cls: shown ? "g" + shown : "", shown, more: Math.max(0, k - 4) };
}
/** 1칸 비율(가로 ÷ 세로). 세로로 길면 정사각형(1)으로 자른다. 크기를 모르면 16:9 */
export function singleRatio(w, h) {
  return w > 0 && h > 0 ? Math.max(1, w / h) : 16 / 9;
}
/** 미디어 묶음 높이(테두리 포함). w = 묶음 바깥 폭, border = 테두리(본문 1 · 인용 안 0) */
export function mediaBoxH(n, w, ratio, border = 1) {
  if (!(n > 0) || !(w > 0)) return 0;
  const inner = w - 2 * border;
  return Math.round(n >= 2 ? (inner * 9) / 16 : inner / (ratio || 16 / 9)) + 2 * border;
}
/** 인용 상자 높이. qw = 상자 바깥 폭 */
export function quoteBoxH(q, qw) {
  const b = XM.border;
  return b + XM.qPad + XM.qHead + (q.textH || 0) + XM.qPad + (q.n ? mediaBoxH(q.n, qw - 2 * b, q.ratio, 0) : 0) + b;
}
/** 본문 밖 고정 치수의 합(본문 높이만 빼고 카드 전체). p = { w: 카드 폭, reply, n, ratio, quote: { textH, n, ratio } | null } */
function _fixedH(p) {
  const cw = p.w - 2 * XM.border - 2 * XM.side;
  let h = XM.border + XM.pad + XM.head + XM.gap + (p.reply ? XM.reply : 0);
  if (p.n) h += XM.gap + mediaBoxH(p.n, cw, p.ratio, 1);
  if (p.quote) h += XM.gap + quoteBoxH(p.quote, cw);
  return h + XM.timeGap + XM.time + XM.below;
}
/** X 카드 높이 어림 = 고정 치수 + 본문 높이(p.textH) */
export function predictCardH(p) { return _fixedH(p) + (p.textH || 0); }
/** X 카드가 알려 준 실제 높이에서 본문 높이를 거꾸로 계산한다(음수면 0) */
export function xTextH(cardH, p) { return Math.max(0, Math.round(cardH - _fixedH(p))); }

/** 열린 시트가 기억한 멤버별 자리 → 되돌릴 글 { id, off } 또는 null(= 맨 아래). ids = 지금 그린 글 id 들 */
export function restoreTarget(pos, ids) {
  if (!pos || pos.bottom || pos.id == null) return null;
  return (ids || []).map(String).includes(String(pos.id)) ? { id: String(pos.id), off: Number(pos.off) || 0 } : null;
}
/** ↓ 동그라미: dist = 맨 아래까지 남은 px, pending = 기다리는 새 글 수 → "count"(숫자 · 흔들기) · "plain"(맨 아래로) · "off" */
export const FAB_DIST = 160;
export function fabMode(dist, pending) {
  if (pending > 0) return "count";
  return dist > FAB_DIST ? "plain" : "off";
}
/** 밀기를 놓았을 때 갈 면. t = 끈 거리 ÷ 폭(왼쪽 −). 갈 수 있는 쪽으로 25% 를 넘겨야 넘어간다 */
export function swipeTo(face, t) {
  const want = face === 0 ? t < 0 : t > 0;
  return want && Math.abs(t) > 0.25 ? 1 - face : face;
}
const _WD = ["일", "월", "화", "수", "목", "금", "토"];
/** 날짜 구분선: 「10월 28일 (화)」 (KST) */
export function dayLabel(ms) {
  const p = kstParts(ms), wd = new Date(ms + KST_MS).getUTCDay();
  return `${p.mo}월 ${p.d}일 (${_WD[wd]})`;
}
/** 시각을 올렸을 때(title): 「10/28 21:02 · 3분 전」 */
export function fullLabel(ms, now) {
  const p = kstParts(ms);
  return `${p.mo}/${p.d} ${hmLabel(ms)} · ${agoLabel(ms, now)}`;
}

/* ── 새 글 자리 ──────────────────────────────────────────────────────
   units = chains() 결과(화면 순서). 첫 안 읽은 글 앞에 「여기부터 새 글」을 둔다.
   반환 { id, inChain } — inChain 이면 글타래 안(그 답글 앞). 안 읽은 글이 없으면 null. */
export function firstUnread(units, isRead) {
  for (const u of units || []) {
    for (let i = 0; i < u.length; i++) {
      if (!isRead(u[i])) return { id: String(u[i].id), inChain: u.length > 1 && i > 0 };
    }
  }
  return null;
}

/* ── 면 저장값 (mew:tllang: "ko" = 번역, "orig" = 원문) ──────────────── */
export function faceOf(v) { return v === "orig" ? 1 : 0; }
export function langOf(face) { return face === 1 ? "orig" : "ko"; }

/* ── 표시 서명 — 75초 폴링마다 같으면 다시 그리지 않는다 ─────────────── */
export function sigOf(list) {
  return (list || []).map((m) => [m.id, m.text_ko || "", (m.quote && m.quote.text_ko) || "", m.reply_to_id || ""].join("|")).join("~");
}

/* ── 열린 시트 갱신 계획 (v4.9.1) ─────────────────────────────────────
   폴링으로 글이 늘었을 때 이미 그린 글(X 카드 iframe 포함)을 그대로 두고 새 글만 끼울 수 있는지 본다.
   old · next = 글타래 단위의 id 배열들(chains 결과를 id 로). 옛 글타래는 하나도 빠짐없이 새 글타래 하나의 앞부분이어야 한다
   (같은 뿌리 · 같은 순서 · 뒤에만 덧붙음). 아니면 null — 글이 빠졌거나 글타래 안에 끼어들었거나 뿌리가 바뀐 것이니 다시 그린다.
   반환: 새 글타래마다 { from: 옛 글타래 번호(-1 = 새 글타래), add: 뒤에 붙는 새 id 들, keep: 제자리에 둬도 되는가 }.
   keep = 옛 글타래 중 순서를 지키는 가장 긴 줄(LIS)에 든 것 — 나머지만 옮긴다(옮기면 그 X 카드는 다시 불러와진다). */
export function reconcileUnits(old, next) {
  const oldUnits = (old || []).map((u) => u.map(String));
  const byRoot = new Map();
  oldUnits.forEach((u, i) => byRoot.set(u[0], i));
  const oldIds = new Set(oldUnits.flat());
  const used = new Set();
  const plan = [];
  for (const raw of next || []) {
    const u = raw.map(String);
    const k = byRoot.has(u[0]) ? byRoot.get(u[0]) : -1;
    const o = k >= 0 ? oldUnits[k] : [];
    if (k >= 0 && (used.has(k) || o.length > u.length || o.some((id, i) => u[i] !== id))) return null;
    const add = u.slice(o.length);
    if (add.some((id) => oldIds.has(id))) return null;
    if (k >= 0) used.add(k);
    plan.push({ from: k, add, keep: false });
  }
  if (used.size !== oldUnits.length) return null;
  // 옛 순서를 지키는 가장 긴 줄(O(n²) — 글타래는 많아야 50개)
  const idx = plan.map((p, i) => (p.from >= 0 ? i : -1)).filter((i) => i >= 0);
  const len = idx.map(() => 1), prev = idx.map(() => -1);
  let best = -1;
  for (let a = 0; a < idx.length; a++) {
    for (let b = 0; b < a; b++) {
      if (plan[idx[b]].from < plan[idx[a]].from && len[b] + 1 > len[a]) { len[a] = len[b] + 1; prev[a] = b; }
    }
    if (best < 0 || len[a] > len[best]) best = a;
  }
  for (let a = best; a >= 0; a = prev[a]) plan[idx[a]].keep = true;
  return plan;
}

/* ── 이름 · 칩 ─────────────────────────────────────────────────────── */
/** 「나카마치 아라레」 → 「아라레」 (마지막 낱말) */
export function shortName(nameKo) {
  const parts = String(nameKo || "").trim().split(/\s+/);
  return parts[parts.length - 1] || "";
}
