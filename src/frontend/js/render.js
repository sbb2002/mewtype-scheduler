import { formatKST, relativeLabel } from "./time.js";
import { FALLBACK_CHANNEL_ORDER, FALLBACK_CHANNELS } from "./config.js";

const DAY_MS = 86400000;

/* 아바타 URL을 표시/샘플링에 충분한 작은 크기로 정규화 (yt3 URL의 =sNNN 파라미터). */
function avatarSized(url, size) {
  return typeof url === "string" ? url.replace(/=s\d+/, `=s${size}`) : url;
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
      // 모바일 캐러셀 클론까지 함께 반영 (같은 data-channel 전부)
      const key = laneEl.dataset.channel;
      const targets = key
        ? document.querySelectorAll(`#board .lane[data-channel="${CSS.escape(key)}"]`)
        : [laneEl];
      targets.forEach((el) => el.style.setProperty("--lane-color", rgb));
    } catch {
      /* tainted canvas — 폴백색 유지 */
    }
  };
  img.src = url;
}

/**
 * Create a card element (live or upcoming)
 * @param {Object} broadcast
 * @param {number} nowMs
 * @returns {HTMLAnchorElement}
 */
function createCard(broadcast, nowMs) {
  const a = document.createElement("a");
  a.href = broadcast.url;
  a.target = "_blank";
  a.rel = "noopener";
  a.className = broadcast.status === "live" ? "card card--live" : "card card--upcoming";

  const thumbWrap = document.createElement("div");
  thumbWrap.className = "card__thumb-wrap";

  const img = document.createElement("img");
  img.className = "card__thumb";
  img.src = broadcast.thumbnail;
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

  if (broadcast.status === "live") {
    const badge = document.createElement("span");
    badge.className = "card__badge card__badge--live";
    badge.textContent = "LIVE";
    thumbWrap.appendChild(badge);
  }
  a.appendChild(thumbWrap);

  const body = document.createElement("div");
  body.className = "card__body";

  const title = document.createElement("p");
  title.className = "card__title";
  title.textContent = broadcast.title;
  body.appendChild(title);

  const meta = document.createElement("p");
  meta.className = "card__meta";

  const timeStr = broadcast.status === "live"
    ? (broadcast.scheduled_start || broadcast.actual_start)
    : broadcast.scheduled_start;
  if (timeStr) {
    const timeEl = document.createElement("time");
    timeEl.className = "card__time";
    timeEl.dateTime = timeStr;
    timeEl.textContent = formatKST(timeStr);
    meta.appendChild(timeEl);
  }

  const relSpan = document.createElement("span");
  relSpan.className = "card__rel";
  if (broadcast.status === "live") {
    relSpan.textContent = "방송 중";
  } else if (broadcast.scheduled_start) {
    relSpan.textContent = relativeLabel(broadcast.scheduled_start, nowMs);
  } else {
    relSpan.textContent = "곧 시작";
  }
  meta.appendChild(relSpan);

  body.appendChild(meta);
  a.appendChild(body);
  return a;
}

/* ── 레인 헤더 (아바타 + 이름 + 핸들) ─────────────────────────────── */
function buildHeader(channelData) {
  const header = document.createElement("header");
  header.className = "lane__header";

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
  return header;
}

/* ── 라이브 영역 (빨간 테두리 존 · 비어있으면 OFF-AIR) ────────────── */
function buildLive(liveBroadcasts, nowMs) {
  const el = document.createElement("div");
  el.className = "lane__live";
  if (liveBroadcasts.length) {
    el.dataset.state = "on";
    for (const b of liveBroadcasts) el.appendChild(createCard(b, nowMs));
  } else {
    el.dataset.state = "off";
    const off = document.createElement("span");
    off.className = "lane__live-off";
    off.textContent = "OFF-AIR";
    el.appendChild(off);
  }
  return el;
}

/* ── 예고 3분할 (7일 이내 / 한 달 이내 / 그 이후) · 각 구간 개별 스크롤 ── */
const BUCKET_DEFS = [
  ["week", "7일 이내"],
  ["month", "한 달 이내"],
  ["later", "그 이후"],
];

function bucketKey(broadcast, nowMs) {
  if (!broadcast.scheduled_start) return "later";
  const delta = new Date(broadcast.scheduled_start).getTime() - nowMs;
  if (delta < 7 * DAY_MS) return "week";
  if (delta < 30 * DAY_MS) return "month";
  return "later";
}

function buildBuckets(upcoming, nowMs) {
  const wrap = document.createElement("div");
  wrap.className = "lane__buckets";

  // 세 구간은 항상 렌더 — 레인끼리 높이가 가지런하도록. 빈 구간은 "예고 없음".
  const groups = { week: [], month: [], later: [] };
  for (const b of upcoming) groups[bucketKey(b, nowMs)].push(b);

  for (const [key, label] of BUCKET_DEFS) {
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
      for (const b of groups[key]) {
        const li = document.createElement("li");
        li.className = "lane__item";
        li.appendChild(createCard(b, nowMs));
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

/**
 * 보드 전체 재구성.
 * @param {HTMLElement} boardEl
 * @param {Object} schedule
 * @param {number} nowMs
 */
export function renderBoard(boardEl, schedule, nowMs = Date.now()) {
  boardEl.innerHTML = "";

  const channelOrder = schedule.channel_order || FALLBACK_CHANNEL_ORDER;
  const channels = schedule.channels || FALLBACK_CHANNELS;

  const byChannel = {};
  for (const b of schedule.broadcasts || []) {
    (byChannel[b.channel_key] ||= []).push(b);
  }

  for (const key of channelOrder) {
    // schedule.json 에 빠진 필드(예: 아직 수집 안 된 avatar)는 폴백으로 필드 단위 보강
    const channelData = { ...(FALLBACK_CHANNELS[key] || {}), ...(channels[key] || {}) };
    if (!channelData.name && !channelData.name_ko) continue;

    const lane = document.createElement("section");
    lane.className = "lane";
    lane.dataset.channel = key;

    lane.appendChild(buildHeader(channelData));

    const list = byChannel[key] || [];
    const live = list.filter((b) => b.status === "live");
    const upcoming = list.filter((b) => b.status === "upcoming").sort(byScheduledAsc);

    lane.appendChild(buildLive(live, nowMs));
    lane.appendChild(buildBuckets(upcoming, nowMs));

    boardEl.appendChild(lane);
    sampleLaneColor(avatarSized(channelData.avatar, 88), lane);
  }

  carouselBoard = boardEl;
  initMobileCarousel(boardEl);
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
 * DOM 재구성 없이 .card--upcoming 의 .card__rel 텍스트만 갱신.
 * @param {HTMLElement} boardEl
 * @param {number} nowMs
 */
export function updateCountdowns(boardEl, nowMs = Date.now()) {
  for (const cardEl of boardEl.querySelectorAll(".card--upcoming")) {
    const relSpan = cardEl.querySelector(".card__rel");
    const timeEl = cardEl.querySelector(".card__time");
    if (relSpan && timeEl && timeEl.dateTime) {
      relSpan.textContent = relativeLabel(timeEl.dateTime, nowMs);
    }
  }
}
