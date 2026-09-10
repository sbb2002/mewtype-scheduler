import { formatKST, relativeLabel, elapsedLabel, isLate } from "./time.js";
import { FALLBACK_CHANNEL_ORDER, FALLBACK_CHANNELS } from "./config.js";

const DAY_MS = 86400000;

/* (v2.3) scheduled 카드 방송종류 라벨. unknown = 라벨 없이 아이콘만. */
const KIND_LABEL = {
  game: "게임",
  talk: "잡담",
  song: "노래",
  collab: "합동",
  morning: "아침",
  unknown: "",
};

/* 아바타 URL을 표시/샘플링에 충분한 작은 크기로 정규화 (yt3 URL의 =sNNN 파라미터). */
function avatarSized(url, size) {
  return typeof url === "string" ? url.replace(/=s\d+/, `=s${size}`) : url;
}

/* (v3.0.2) 레인 헤더 이동 레일 아이콘. innerHTML 금지 규칙 → createElementNS 로만. */
const YT_ICON_D =
  "M23 12s0-3.6-.46-5.3a2.78 2.78 0 0 0-1.95-1.96C18.9 4.28 12 4.28 12 4.28s-6.9 0-8.6.46A2.78 2.78 0 0 0 1.46 6.7C1 8.4 1 12 1 12s0 3.6.46 5.3a2.78 2.78 0 0 0 1.95 1.96c1.7.46 8.6.46 8.6.46s6.9 0 8.6-.46a2.78 2.78 0 0 0 1.95-1.96C23 15.6 23 12 23 12ZM9.75 15.5v-7l6 3.5-6 3.5Z";
const X_ICON_D =
  "M18.9 2.6h3.3l-7.2 8.2 8.5 11.3h-6.7l-5.2-6.8-6 6.8H1.3l7.7-8.8L.7 2.6h6.9l4.7 6.2 5.6-6.2Zm-1.2 17.7h1.9L7.2 4.4H5.2l12.5 15.9Z";

function svgIcon(d) {
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  const path = document.createElementNS(NS, "path");
  path.setAttribute("fill", "currentColor");
  path.setAttribute("d", d);
  svg.appendChild(path);
  return svg;
}

/**
 * 아바타 평균색을 뽑아 lane 요소의 --lane-color 로 설정 (live-translator 방식).
 * CORS 읽기 실패(canvas taint) 시 조용히 무시 → CSS 폴백색 사용.
 */
function sampleLaneColor(url, laneEl) {
  if (!url) return;
  const img = new Image();
  img.crossOrigin = "anonymous";
  img.onload = () => {
    try {
      const c = document.createElement("canvas");
      c.width = c.height = 16;
      const ctx = c.getContext("2d");
      ctx.drawImage(img, 0, 0, 16, 16);
      const d = ctx.getImageData(0, 0, 16, 16).data;
      let r = 0, g = 0, b = 0, n = 0;
      for (let i = 0; i < d.length; i += 4) { r += d[i]; g += d[i + 1]; b += d[i + 2]; n++; }
      const rgb = `rgb(${(r / n) | 0} ${(g / n) | 0} ${(b / n) | 0})`;
      // 같은 방송인의 레인(캐러셀 클론 포함) + 하단 페이지 도트에 반영
      const key = laneEl.dataset.channel;
      const sel = key
        ? `#board .lane[data-channel="${CSS.escape(key)}"], #pager-dots .dot[data-channel="${CSS.escape(key)}"]`
        : null;
      const targets = sel ? document.querySelectorAll(sel) : [laneEl];
      targets.forEach((el) => el.style.setProperty("--lane-color", rgb));
    } catch {
      /* tainted canvas — 폴백색 유지 */
    }
  };
  img.src = url;
}

/**
 * v3 아이템을 카드로 렌더. 6상태 + membership/collab/assumed_live 조합 지원.
 * @param {Object} item
 * @param {number} nowMs
 * @param {Object} [channelData]  announced 카드의 채널 링크용
 * @param {string} [laneKey]      렌더 중인 레인의 channel_key (합동 카드 상대 표기용)
 * @returns {HTMLAnchorElement}
 */
function createCard(item, nowMs, channelData, laneKey) {
  const a = document.createElement("a");
  a.target = "_blank";
  a.rel = "noopener";

  // ── announced (예고) — URL 있을 수도 없을 수도. 실물 영상 확정 아님 ──
  if (item.state === "announced") {
    // (v2.4~v3) kind=="collab" 또는 collab_with 존재 = 합동방송
    const isCollab = item.kind === "collab" || (Array.isArray(item.collab_with) && item.collab_with.length > 0);
    // ponytail: assumed_live 는 announced+upcoming 중 90분 지각 강등된 아이템 표시
    a.className = item.assumed_live
      ? "card card--announced card--sched-live"
      : "card card--announced";
    if (isCollab) a.classList.add("card--collab");
    a.href = item.url || (channelData && channelData.channel_url) || "#";

    // 썸네일 자리 — membership 이면 자물쇠, 아니면 아이콘
    const thumbWrap = document.createElement("div");
    thumbWrap.className = "card__thumb-wrap";
    if (item.membership) {
      const lock = document.createElement("span");
      lock.className = "card__icon";
      lock.textContent = "🔒";
      thumbWrap.appendChild(lock);
    } else {
      const icon = document.createElement("span");
      icon.className = "card__icon";
      icon.textContent = "📺";
      thumbWrap.appendChild(icon);
    }
    const badge = document.createElement("span");
    badge.className = isCollab ? "card__badge card__badge--collab" : "card__badge card__badge--announced";
    badge.textContent = isCollab ? "합동" : "예고";
    thumbWrap.appendChild(badge);
    a.appendChild(thumbWrap);

    const body = document.createElement("div");
    body.className = "card__body";

    if (item.membership) {
      const chip = document.createElement("span");
      chip.className = "card__chip";
      chip.textContent = "🔒 회원 전용 방송";
      body.appendChild(chip);
    }

    let label = KIND_LABEL[item.kind] || "";
    if (isCollab) {
      const participants = [item.channel_key, ...(Array.isArray(item.collab_with) ? item.collab_with : [])];
      const others = participants.filter((k) => k && k !== laneKey);
      if (item.title) {
        label = `합동 · ${item.title}`;
      } else if (others.length >= 4) {
        label = "합동 · 전원";
      } else {
        const names = others
          .map((k) => (FALLBACK_CHANNELS[k] || {}).name_ko)
          .filter(Boolean)
          .join(", ");
        label = names ? `합동 · ${names}` : "합동";
      }
    }
    if (label) {
      const title = document.createElement("p");
      title.className = "card__title card__title--label";
      title.textContent = label;
      body.appendChild(title);
    }

    const meta = document.createElement("p");
    meta.className = "card__meta";
    if (item.time_tbd && item.scheduled_start) {
      const dateEl = document.createElement("span");
      dateEl.className = "card__time";
      dateEl.textContent = item.scheduled_start.slice(5, 10).replace("-", "/");
      meta.appendChild(dateEl);
      const rel = document.createElement("span");
      rel.className = "card__rel";
      rel.textContent = item.assumed_live ? "방송 중 (추정)" : "시간 미정";
      meta.appendChild(rel);
    } else if (item.scheduled_start) {
      const timeEl = document.createElement("time");
      timeEl.className = "card__time";
      timeEl.dateTime = item.scheduled_start;
      timeEl.appendChild(document.createTextNode(formatKST(item.scheduled_start)));
      meta.appendChild(timeEl);
      const rel = document.createElement("span");
      rel.className = "card__rel";
      rel.textContent = item.assumed_live
        ? "방송 중 (추정)"
        : relativeLabel(item.scheduled_start, nowMs);
      meta.appendChild(rel);
    } else {
      const rel = document.createElement("span");
      rel.className = "card__rel";
      rel.textContent = "시간 미정";
      meta.appendChild(rel);
    }
    body.appendChild(meta);
    a.appendChild(body);
    return a;
  }

  // ── upcoming/watching (예정) / live (방송 중) / end (방송 종료) — 실물 영상 있음 ──
  const isWatching = item.state === "watching";
  const isLive = item.state === "live";
  const isEnd = item.state === "end";

  a.className = "card";
  if (isLive) {
    a.classList.add("card--live");
  } else if (isEnd) {
    a.classList.add("card--end");
  } else if (isWatching) {
    a.classList.add("card--watching");
  } else {
    a.classList.add("card--upcoming");
  }

  if (item.membership) a.classList.add("card--membership");

  a.href = item.url;

  // 썸네일 영역
  const thumbWrap = document.createElement("div");
  thumbWrap.className = "card__thumb-wrap";

  if (item.membership) {
    // membership 은 썸네일 자리에 자물쇠 + 배지
    const lock = document.createElement("span");
    lock.className = "card__icon";
    lock.textContent = "🔒";
    thumbWrap.appendChild(lock);
  } else if (item.thumbnail) {
    const img = document.createElement("img");
    img.className = "card__thumb";
    img.src = item.thumbnail;
    img.loading = "lazy";
    img.alt = "";
    img.onerror = function () {
      if (this.dataset.fallback) {
        this.classList.add("card__thumb--broken");
      } else {
        this.dataset.fallback = "1";
        this.src = this.src.replace("hqdefault", "mqdefault");
      }
    };
    thumbWrap.appendChild(img);
  }

  if (isLive) {
    const badge = document.createElement("span");
    badge.className = "card__badge card__badge--live";
    badge.textContent = "LIVE";
    thumbWrap.appendChild(badge);
  } else if (isWatching) {
    const badge = document.createElement("span");
    badge.className = "card__badge card__badge--watching";
    badge.textContent = "대기 중";
    thumbWrap.appendChild(badge);
  } else if (isEnd) {
    // end 상태는 배지 없음
  }

  a.appendChild(thumbWrap);

  const body = document.createElement("div");
  body.className = "card__body";

  const title = document.createElement("p");
  title.className = "card__title";
  title.textContent = item.title;
  body.appendChild(title);

  const meta = document.createElement("p");
  meta.className = "card__meta";

  // 시각 표시: live/end 는 actual_start, 나머지는 scheduled_start
  const timeStr = (isLive || isEnd)
    ? (item.actual_start || item.scheduled_start)
    : item.scheduled_start;
  if (timeStr) {
    const timeEl = document.createElement("time");
    timeEl.className = "card__time";
    timeEl.dateTime = timeStr;
    timeEl.textContent = formatKST(timeStr);
    meta.appendChild(timeEl);
  }

  const relSpan = document.createElement("span");
  relSpan.className = "card__rel";
  if (isLive) {
    // actual_start 가 있으면 경과 시간 표시
    relSpan.textContent = item.actual_start ? elapsedLabel(item.actual_start, nowMs) : "방송 중";
  } else if (isEnd) {
    relSpan.textContent = "방송 종료";
  } else if (isWatching) {
    // watching 도 relativeLabel 사용 (대기 중 배지가 상태 표시)
    relSpan.textContent = relativeLabel(item.scheduled_start, nowMs);
    relSpan.classList.toggle("card__rel--late", isLate(item.scheduled_start, nowMs));
  } else if (item.scheduled_start) {
    // upcoming/announced
    relSpan.textContent = relativeLabel(item.scheduled_start, nowMs);
    if (item.state === "upcoming") {
      relSpan.classList.toggle("card__rel--late", isLate(item.scheduled_start, nowMs));
    }
  } else {
    relSpan.textContent = "곧 시작";
  }
  meta.appendChild(relSpan);

  body.appendChild(meta);
  a.appendChild(body);
  return a;
}

/* ── 레인 헤더 (아바타 + 이름 + 핸들 + 우측 이동 레일) ────────────── */
function buildHeader(channelData) {
  const header = document.createElement("header");
  header.className = "lane__header";

  // .lane__link = 아바타 + 이름 (YouTube 채널로 이동). 아바타는 tweets.js 가
  // 트윗 있을 때 말풍선 토글로 가로챈다(없으면 이 앵커대로 YouTube).
  const link = document.createElement("a");
  link.className = "lane__link";
  link.href = channelData.channel_url || "#";
  link.target = "_blank";
  link.rel = "noopener";

  const avatar = document.createElement("span");
  avatar.className = "lane__avatar";
  if (channelData.avatar) {
    avatar.style.backgroundImage = `url("${avatarSized(channelData.avatar, 176)}")`;
  }
  link.appendChild(avatar);

  const metaWrap = document.createElement("span");
  metaWrap.className = "lane__meta";

  const nameLine = document.createElement("span");
  nameLine.className = "lane__name-line";
  const nameKo = document.createElement("span");
  nameKo.className = "lane__name-ko";
  nameKo.textContent = channelData.name_ko || "";
  const nameOrig = document.createElement("span");
  nameOrig.className = "lane__name-orig";
  nameOrig.textContent = channelData.name || "";
  nameLine.append(nameKo, nameOrig);

  const handle = document.createElement("span");
  handle.className = "lane__handle";
  handle.textContent = channelData.handle ? `@${channelData.handle}` : "";

  metaWrap.append(nameLine, handle);
  link.appendChild(metaWrap);
  header.appendChild(link);

  // (v3.0.2) 우측 세로 이동 레일 — YouTube 채널 · X 계정. 별도 앵커라
  // tweets.js 클릭 위임(.lane__tw/.lane__avatar 만 처리)은 그냥 통과한다.
  const nav = document.createElement("nav");
  nav.className = "lane__nav";
  nav.setAttribute("aria-label", `${channelData.name_ko || "채널"} 바로가기`);

  const ytLink = document.createElement("a");
  ytLink.className = "lane__nav-btn lane__nav-yt";
  ytLink.href = channelData.channel_url || "#";
  ytLink.target = "_blank";
  ytLink.rel = "noopener";
  ytLink.setAttribute("aria-label", "YouTube 채널");
  ytLink.appendChild(svgIcon(YT_ICON_D));

  const xLink = document.createElement("a");
  xLink.className = "lane__nav-btn lane__nav-x";
  // X 핸들 필드가 따로 없어 YouTube 핸들(*_yumemita)을 재사용 — tweets.js _setSrc 와 동일 규칙.
  xLink.href = channelData.handle ? `https://x.com/${channelData.handle}` : "#";
  xLink.target = "_blank";
  xLink.rel = "noopener";
  xLink.setAttribute("aria-label", "X 계정");
  xLink.appendChild(svgIcon(X_ICON_D));

  nav.append(ytLink, xLink);
  header.appendChild(nav);
  return header;
}

/* ── 라이브 영역 (빨간 테두리 존 · 비어있으면 OFF-AIR) ────────────── */
function buildLive(liveItems, endedItems, nowMs, channelData, laneKey) {
  const el = document.createElement("div");
  el.className = "lane__live";
  // 빨간 테두리는 실제 live 가 있을 때만 켠다. end(방송 종료) 카드는 존에 남기되 소등.
  el.dataset.state = liveItems.length ? "on" : "off";
  for (const b of liveItems) el.appendChild(createCard(b, nowMs, channelData, laneKey));
  for (const b of endedItems) el.appendChild(createCard(b, nowMs, channelData, laneKey));
  if (!liveItems.length && !endedItems.length) {
    const off = document.createElement("span");
    off.className = "lane__live-off";
    off.textContent = "OFF-AIR";
    el.appendChild(off);
  }
  return el;
}

/* ── 예고 시간대별 분할 (오늘 / 7일 이내 / 7일 이후). PC·모바일 동일.
   v3.0.0 까진 PC 만 "한 달 이내"/"그 이후" 로 4분할했으나 통합(화면 규격 무관 3분할). ── */
const BUCKET_DEFS = [
  ["today", "오늘"],
  ["week", "7일 이내"],
  ["rest", "7일 이후"],
];

function bucketKey(item, nowMs) {
  if (!item.scheduled_start) return "rest";
  const delta = new Date(item.scheduled_start).getTime() - nowMs;
  if (delta < DAY_MS) return "today";
  if (delta < 7 * DAY_MS) return "week";
  return "rest";
}

function buildBuckets(pending, nowMs, channelData, laneKey) {
  const wrap = document.createElement("div");
  wrap.className = "lane__buckets";

  const defs = BUCKET_DEFS;
  const groups = {};
  for (const [key] of defs) groups[key] = [];
  for (const i of pending) (groups[bucketKey(i, nowMs)] ||= []).push(i);

  for (const [key, label] of defs) {
    const sec = document.createElement("section");
    sec.className = "lane__bucket";
    sec.dataset.bucket = key;

    const h = document.createElement("h3");
    h.className = "lane__bucket-label";
    h.textContent = label;
    sec.appendChild(h);

    const list = document.createElement("ul");
    list.className = "lane__bucket-list";
    if (groups[key].length === 0) {
      const none = document.createElement("li");
      none.className = "lane__bucket-none";
      none.textContent = "예고 없음";
      list.appendChild(none);
    } else {
      for (const i of groups[key]) {
        const li = document.createElement("li");
        li.className = "lane__item";
        li.appendChild(createCard(i, nowMs, channelData, laneKey));
        list.appendChild(li);
      }
    }
    sec.appendChild(list);
    wrap.appendChild(sec);
  }
  return wrap;
}

function byScheduledAsc(a, b) {
  if (a.scheduled_start === b.scheduled_start) return 0;
  if (!a.scheduled_start) return 1;
  if (!b.scheduled_start) return -1;
  return new Date(a.scheduled_start).getTime() - new Date(b.scheduled_start).getTime();
}

// ponytail: bucketOf 순수 헬퍼. selfcheck 에서 테스트용.
export function bucketOf(item, nowMs) {
  return bucketKey(item, nowMs);
}

// ponytail: laneKeys 순수 헬퍼. selfcheck 에서 테스트용.
export function laneKeys(items, channelOrder) {
  const keys = new Set();
  for (const item of items) {
    if (item.channel_key) keys.add(item.channel_key);
    if (Array.isArray(item.collab_with)) item.collab_with.forEach(k => keys.add(k));
  }
  return Array.from(keys).filter(k => channelOrder.includes(k)).sort();
}

/**
 * 보드 전체 재구성 (v3).
 * @param {HTMLElement} boardEl
 * @param {Object} preview - {channel_order, channels, items}
 * @param {number} nowMs
 */
export function renderBoard(boardEl, preview, nowMs = Date.now()) {
  boardEl.innerHTML = "";

  const channelOrder = preview.channel_order || FALLBACK_CHANNEL_ORDER;
  const channels = preview.channels || FALLBACK_CHANNELS;

  // v3: 합동방송은 참여 멤버 전원(channel_key + collab_with) 레인에 팬아웃.
  // 모르는 channel_key 는 무시.
  const byChannel = {};
  for (const item of preview.items || []) {
    if (!item.channel_key || !channelOrder.includes(item.channel_key)) continue;
    const keys = new Set([item.channel_key, ...(Array.isArray(item.collab_with) ? item.collab_with : [])]);
    for (const k of keys) {
      if (k && channelOrder.includes(k)) (byChannel[k] ||= []).push(item);
    }
  }

  for (const key of channelOrder) {
    const channelData = { ...(FALLBACK_CHANNELS[key] || {}), ...(channels[key] || {}) };
    if (!channelData.name && !channelData.name_ko) continue;

    const lane = document.createElement("section");
    lane.className = "lane";
    lane.dataset.channel = key;

    lane.appendChild(buildHeader(channelData));

    const list = byChannel[key] || [];
    const live = list.filter((i) => i.state === "live");
    // announced/upcoming/watching 을 버킷으로 분류
    const pending = list
      .filter((i) => i.state === "announced" || i.state === "upcoming" || i.state === "watching")
      .sort(byScheduledAsc);
    // end 상태는 별도 영역 없음(pending 에 섞이지 않음)
    const ended = list.filter((i) => i.state === "end");

    lane.appendChild(buildLive(live, ended, nowMs, channelData, key));
    lane.appendChild(buildBuckets(pending, nowMs, channelData, key));

    boardEl.appendChild(lane);
    sampleLaneColor(avatarSized(channelData.avatar, 88), lane);
  }

  applyMarquees(boardEl);
  carouselBoard = boardEl;
  initMobileCarousel(boardEl);
}

/* 제목이 카드 폭을 넘치면 흐르는 marquee 로 전환 (PC). 줄바꿈되는 모바일은
   scrollWidth ≈ clientWidth 라 자동으로 건너뜀. */
function applyMarquees(boardEl) {
  for (const t of boardEl.querySelectorAll(".card__title")) {
    if (t.classList.contains("card__title--marquee")) continue;
    if (t.scrollWidth - t.clientWidth <= 4) continue;   // 넘치지 않으면 그대로

    const text = t.textContent;
    t.textContent = "";
    const track = document.createElement("span");
    track.className = "card__title-track";
    const a = document.createElement("span");
    a.textContent = text;
    const b = document.createElement("span");
    b.textContent = text;
    b.setAttribute("aria-hidden", "true");
    track.append(a, b);
    t.appendChild(track);
    t.classList.add("card__title--marquee");

    // 한 벌 폭(+ padding-right 2.5rem ≈ 40px) 기준 ~55px/s 로 흐르게 → 길수록 오래
    const copyW = a.getBoundingClientRect().width + 40;
    t.style.setProperty("--marquee-dur", `${Math.max(6, Math.round(copyW / 55))}s`);
  }
}

/* ─── 모바일 캐러셀 (방송인 1명씩 가로 스와이프 · 5명 무한 회전) ───────────
   폰(<768px)에서만. 태블릿/데스크톱(≥768px)은 클론/도트 없이 5열 그리드 그대로.
   위치 계산은 폭이 아니라 실제 DOM 기하( getBoundingClientRect )로 해서
   좌우 패딩·옆 유닛 미리보기(peek)·gap 이 있어도 정확히 한 칸씩 스냅. */

let activeIdx = 0;                 // 마지막으로 보던 방송인 (재렌더/회전 넘어가도 유지)
let carouselBoard = null;
const mqlPhone = window.matchMedia("(max-width: 767px)");
mqlPhone.addEventListener("change", () => {
  if (carouselBoard) initMobileCarousel(carouselBoard);
});

function clearCarousel(boardEl) {
  boardEl.querySelectorAll(".lane--clone").forEach((n) => n.remove());
  boardEl.classList.remove("board--carousel");
  if (boardEl._carouselCleanup) { boardEl._carouselCleanup(); boardEl._carouselCleanup = null; }
  const dots = document.getElementById("pager-dots");
  if (dots) { dots.innerHTML = ""; dots.hidden = true; }
}

function initMobileCarousel(boardEl) {
  clearCarousel(boardEl);
  if (!mqlPhone.matches) return;

  const reals = [...boardEl.querySelectorAll(".lane")];
  const n = reals.length;
  if (n < 2) return;

  boardEl.classList.add("board--carousel");

  // 앞뒤에 클론 1개씩 → 끝에서 반대편으로 순간이동해 무한 회전
  const headClone = reals[n - 1].cloneNode(true);   // 맨 앞에 '마지막' 방송인
  const tailClone = reals[0].cloneNode(true);       // 맨 뒤에 '처음' 방송인
  for (const c of [headClone, tailClone]) {
    c.classList.add("lane--clone");
    c.setAttribute("aria-hidden", "true");
  }
  boardEl.insertBefore(headClone, reals[0]);
  boardEl.appendChild(tailClone);

  // DOM 순서: [headClone(=마지막), real0..real(n-1), tailClone(=처음)]
  const slides = () => [...boardEl.querySelectorAll(".lane")];
  const padLeft = () => {
    const v = parseFloat(getComputedStyle(boardEl).scrollPaddingLeft);
    return Number.isFinite(v) ? v : 42;   // CSS: calc(--m-pad 1rem + --m-peek 26px)
  };

  // 스냅 기준선(보드 왼쪽 + scroll-padding-left)에 슬라이드 di 의 왼쪽을 맞추는 scrollLeft
  const targetFor = (di) => {
    const s = slides()[di];
    if (!s) return boardEl.scrollLeft;
    const off = s.getBoundingClientRect().left - boardEl.getBoundingClientRect().left - padLeft();
    return boardEl.scrollLeft + off;
  };
  const goDom = (di, smooth) => {
    const left = targetFor(di);
    if (smooth) boardEl.scrollTo({ left, behavior: "smooth" });
    else boardEl.scrollLeft = left;
  };
  const jumpReal = (i) => goDom(i + 1, false);
  const glideReal = (i) => goDom(i + 1, true);

  // 현재 스냅된 슬라이드의 DOM 인덱스 (기준선에 가장 가까운 것)
  const currentDom = () => {
    const base = boardEl.getBoundingClientRect().left + padLeft();
    let bi = 0, bd = Infinity;
    slides().forEach((s, di) => {
      const d = Math.abs(s.getBoundingClientRect().left - base);
      if (d < bd) { bd = d; bi = di; }
    });
    return bi;
  };

  activeIdx = ((activeIdx % n) + n) % n;
  jumpReal(activeIdx);                                  // 즉시
  requestAnimationFrame(() => jumpReal(activeIdx));     // 레이아웃 후
  setTimeout(() => jumpReal(activeIdx), 60);            // 스냅 보정 후 (rAF 미실행 대비)

  // 도트 인디케이터
  const dots = document.getElementById("pager-dots");
  const setActiveDot = (i) => {
    dots?.querySelectorAll(".dot").forEach((d, di) => d.classList.toggle("dot--on", di === i));
  };
  if (dots) {
    dots.hidden = false;
    dots.innerHTML = "";
    reals.forEach((lane, i) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "dot";
      const key = lane.dataset.channel;
      if (key) btn.dataset.channel = key;
      // 아바타 색이 이미 샘플링됐으면 그 값, 아니면 나중에 sampleLaneColor 가 채움
      const c = getComputedStyle(lane).getPropertyValue("--lane-color").trim();
      if (c) btn.style.setProperty("--lane-color", c);
      btn.setAttribute(
        "aria-label",
        (lane.querySelector(".lane__name-ko")?.textContent || `${i + 1}번`) + " 보기"
      );
      btn.addEventListener("click", () => glideReal(i));
      dots.appendChild(btn);
    });
    setActiveDot(activeIdx);
  }

  // 스크롤: active 갱신 + 클론에 닿으면 멈춘 뒤 반대편 실제 슬라이드로 순간이동
  let settle = null;
  const onScroll = () => {
    const di = currentDom();
    let real = di - 1;
    if (real < 0) real = n - 1;
    else if (real > n - 1) real = 0;
    if (real !== activeIdx) { activeIdx = real; setActiveDot(real); }

    clearTimeout(settle);
    settle = setTimeout(() => {
      const d = currentDom();
      if (d <= 0) jumpReal(n - 1);
      else if (d >= n + 1) jumpReal(0);
    }, 90);
  };
  boardEl.addEventListener("scroll", onScroll, { passive: true });

  const onResize = () => jumpReal(activeIdx);
  window.addEventListener("resize", onResize);

  boardEl._carouselCleanup = () => {
    boardEl.removeEventListener("scroll", onScroll);
    window.removeEventListener("resize", onResize);
    clearTimeout(settle);
  };
}

/**
 * @param {HTMLElement} footEl
 * @param {Object} schedule
 * @param {{stale?: boolean}} opts
 */
export function renderFooter(footEl, schedule, { stale = false } = {}) {
  const updatedSpan = footEl.querySelector("#foot-updated");
  const statusSpan = footEl.querySelector("#foot-status");

  if (updatedSpan) {
    const gen = schedule && schedule.generated_at;
    updatedSpan.textContent = gen ? `업데이트: ${formatKST(gen)}` : "업데이트: --/-- --:--";
  }
  if (statusSpan) {
    statusSpan.hidden = !stale;
    if (stale) statusSpan.textContent = "업데이트 지연";
  }
}

/**
 * v3 카운트다운 갱신 (재렌더 필요 시 true 반환).
 * @param {HTMLElement} boardEl
 * @param {number} nowMs
 */
export function updateCountdowns(boardEl, nowMs = Date.now()) {
  let bucketChanged = false;
  for (const cardEl of boardEl.querySelectorAll(".card")) {
    const relSpan = cardEl.querySelector(".card__rel");
    const timeEl = cardEl.querySelector(".card__time");
    if (!relSpan || !timeEl || !timeEl.dateTime) continue;

    // assumed_live 는 "방송 중 (추정)" 고정
    if (cardEl.classList.contains("card--sched-live")) continue;

    // live: elapsedLabel / 나머지: relativeLabel
    if (cardEl.classList.contains("card--live")) {
      relSpan.textContent = elapsedLabel(timeEl.dateTime, nowMs);
    } else if (cardEl.classList.contains("card--end")) {
      relSpan.textContent = "방송 종료";
    } else {
      // announced/upcoming/watching
      relSpan.textContent = relativeLabel(timeEl.dateTime, nowMs);
      // announced 는 late 토글 스킵, upcoming/watching 은 토글
      if (!cardEl.classList.contains("card--announced")) {
        relSpan.classList.toggle("card__rel--late", isLate(timeEl.dateTime, nowMs));
      }
    }

    // 구간 변화 감지
    const cur = cardEl.closest(".lane__bucket")?.dataset.bucket;
    if (cur && bucketKey({ scheduled_start: timeEl.dateTime }, nowMs) !== cur) {
      bucketChanged = true;
    }
  }
  return bucketChanged;
}
