import { formatKST, relativeLabel } from "./time.js";
import { FALLBACK_CHANNEL_ORDER, FALLBACK_CHANNELS } from "./config.js";

/**
 * Create a card element (live or upcoming)
 * @param {Object} broadcast - Broadcast data
 * @param {number} nowMs - Current time in milliseconds
 * @returns {HTMLElement} - <a> card element
 */
function createCard(broadcast, nowMs) {
  const a = document.createElement("a");
  a.href = broadcast.url;
  a.target = "_blank";
  a.rel = "noopener";
  a.className = broadcast.status === "live" ? "card card--live" : "card card--upcoming";

  // Thumbnail wrapper
  const thumbWrap = document.createElement("div");
  thumbWrap.className = "card__thumb-wrap";

  const img = document.createElement("img");
  img.className = "card__thumb";
  img.src = broadcast.thumbnail;
  img.loading = "lazy";
  img.alt = "";
  // Onerror fallback: hqdefault -> mqdefault -> broken state
  img.onerror = function() {
    if (this.dataset.fallback) {
      this.classList.add("card__thumb--broken");
    } else {
      this.dataset.fallback = "1";
      this.src = this.src.replace("hqdefault", "mqdefault");
    }
  };

  thumbWrap.appendChild(img);

  // LIVE badge (only for live cards)
  if (broadcast.status === "live") {
    const badge = document.createElement("span");
    badge.className = "card__badge card__badge--live";
    badge.textContent = "LIVE";
    thumbWrap.appendChild(badge);
  }

  a.appendChild(thumbWrap);

  // Body
  const body = document.createElement("div");
  body.className = "card__body";

  const title = document.createElement("p");
  title.className = "card__title";
  title.textContent = broadcast.title;
  body.appendChild(title);

  const meta = document.createElement("p");
  meta.className = "card__meta";

  // Time
  let timeEl = null;
  if (broadcast.status === "live") {
    // For live: use scheduled_start or actual_start
    const timeStr = broadcast.scheduled_start || broadcast.actual_start;
    if (timeStr) {
      timeEl = document.createElement("time");
      timeEl.className = "card__time";
      timeEl.dateTime = timeStr;
      timeEl.textContent = formatKST(timeStr);
      meta.appendChild(timeEl);
    }
  } else {
    // For upcoming: use scheduled_start
    if (broadcast.scheduled_start) {
      timeEl = document.createElement("time");
      timeEl.className = "card__time";
      timeEl.dateTime = broadcast.scheduled_start;
      timeEl.textContent = formatKST(broadcast.scheduled_start);
      meta.appendChild(timeEl);
    }
  }

  // Relative label
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

/**
 * Render the entire board with all lanes and cards
 * @param {HTMLElement} boardEl - #board element
 * @param {Object} schedule - Schedule data
 * @param {number} nowMs - Current time in milliseconds (default: Date.now())
 */
export function renderBoard(boardEl, schedule, nowMs = Date.now()) {
  // Clear board
  boardEl.innerHTML = "";

  // Get channel order and channels
  const channelOrder = schedule.channel_order || FALLBACK_CHANNEL_ORDER;
  const channels = schedule.channels || FALLBACK_CHANNELS;

  // Group broadcasts by channel_key
  const broadcastsByChannel = {};
  for (const broadcast of schedule.broadcasts || []) {
    if (!broadcastsByChannel[broadcast.channel_key]) {
      broadcastsByChannel[broadcast.channel_key] = [];
    }
    broadcastsByChannel[broadcast.channel_key].push(broadcast);
  }

  // Create lanes
  for (const channelKey of channelOrder) {
    const channelData = channels[channelKey];
    if (!channelData) continue;

    const lane = document.createElement("section");
    lane.className = "lane";
    lane.dataset.channel = channelKey;

    // Header
    const header = document.createElement("header");
    header.className = "lane__header";

    const link = document.createElement("a");
    link.className = "lane__link";
    link.href = channelData.channel_url || "#";
    link.target = "_blank";
    link.rel = "noopener";

    const nameKo = document.createElement("span");
    nameKo.className = "lane__name-ko";
    nameKo.textContent = channelData.name_ko;
    link.appendChild(nameKo);

    const nameOrig = document.createElement("span");
    nameOrig.className = "lane__name-orig";
    nameOrig.textContent = channelData.name;
    link.appendChild(nameOrig);

    header.appendChild(link);
    lane.appendChild(header);

    // Live section
    const liveDiv = document.createElement("div");
    liveDiv.className = "lane__live";

    // Upcoming section
    const upcomingUl = document.createElement("ul");
    upcomingUl.className = "lane__upcoming";

    // Get broadcasts for this channel
    const broadcasts = broadcastsByChannel[channelKey] || [];

    // Separate live and upcoming
    const liveBroadcasts = broadcasts.filter(b => b.status === "live");
    const upcomingBroadcasts = broadcasts
      .filter(b => b.status === "upcoming")
      .sort((a, b) => {
        // Sort by scheduled_start ascending, nulls last
        if (a.scheduled_start === null) return 1;
        if (b.scheduled_start === null) return -1;
        return new Date(a.scheduled_start).getTime() - new Date(b.scheduled_start).getTime();
      });

    // Add live cards
    for (const broadcast of liveBroadcasts) {
      liveDiv.appendChild(createCard(broadcast, nowMs));
    }

    // Add upcoming cards or empty state
    if (upcomingBroadcasts.length === 0) {
      const emptyLi = document.createElement("li");
      emptyLi.className = "lane__empty";
      emptyLi.textContent = "예정된 방송이 없어요";
      upcomingUl.appendChild(emptyLi);
    } else {
      for (const broadcast of upcomingBroadcasts) {
        const li = document.createElement("li");
        li.className = "lane__item";
        li.appendChild(createCard(broadcast, nowMs));
        upcomingUl.appendChild(li);
      }
    }

    lane.appendChild(liveDiv);
    lane.appendChild(upcomingUl);
    boardEl.appendChild(lane);
  }
}

/**
 * Update footer with current time and stale status
 * @param {HTMLElement} footEl - #foot element
 * @param {Object} schedule - Schedule data
 * @param {Object} options - { stale: boolean }
 */
export function renderFooter(footEl, schedule, { stale = false } = {}) {
  const updatedSpan = footEl.querySelector("#foot-updated");
  const statusSpan = footEl.querySelector("#foot-status");

  if (updatedSpan) {
    // Show when the data itself was generated (KST), not the render time.
    const gen = schedule && schedule.generated_at;
    updatedSpan.textContent = gen
      ? `업데이트: ${formatKST(gen)}`
      : "업데이트: --/-- --:--";
  }

  if (statusSpan) {
    if (stale) {
      statusSpan.hidden = false;
      statusSpan.textContent = "업데이트 지연";
    } else {
      statusSpan.hidden = true;
    }
  }
}

/**
 * Update countdown text (.card__rel) for all upcoming cards without DOM rebuild
 * @param {HTMLElement} boardEl - #board element
 * @param {number} nowMs - Current time in milliseconds (default: Date.now())
 */
export function updateCountdowns(boardEl, nowMs = Date.now()) {
  const upcomingCards = boardEl.querySelectorAll(".card--upcoming");

  for (const cardEl of upcomingCards) {
    const relSpan = cardEl.querySelector(".card__rel");
    const timeEl = cardEl.querySelector(".card__time");

    if (relSpan && timeEl && timeEl.dateTime) {
      relSpan.textContent = relativeLabel(timeEl.dateTime, nowMs);
    }
  }
}
