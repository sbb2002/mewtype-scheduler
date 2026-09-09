import { fetchPreview } from "./api.js";
import { renderBoard, renderFooter, updateCountdowns } from "./render.js";
import { renderNotices } from "./notices.js";
import { renderTweets, reapplyTweets } from "./tweets.js";
import { PREVIEW_URL, NOTICES_URL, TWEETS_URL, POLL_MS, COUNTDOWN_TICK_MS } from "./config.js";

const board = document.getElementById("board");
const foot = document.getElementById("foot");
const notice = document.getElementById("notice");

let lastSchedule = null;
let lastJSON = null;   // 내용이 안 바뀌면 renderBoard 생략 (모바일 캐러셀 위치 보존)

/** 보드 재구성 + 그 위에 개인 트윗 편지 배지 재적용 (renderBoard 가 배지를 지우므로). */
function paintBoard() {
  renderBoard(board, lastSchedule);
  reapplyTweets(board);
}

/** (v2.8) 개인 트윗 폴링 — 스케줄과 독립. 404/오류면 배지 안 뜬다. */
async function pollTweets() {
  const r = await fetchPreview(TWEETS_URL);
  try {
    renderTweets(board, r.ok ? r.data : null);
  } catch (e) {
    /* 배지 오류가 메인 보드를 막지 않게 */
  }
}

/** 소식 티커 폴링 — 스케줄과 독립. 404/오류면 티커를 그냥 숨긴 채 둔다. */
async function pollNotices() {
  const r = await fetchPreview(NOTICES_URL);
  try {
    renderNotices(notice, r.ok ? r.data : null);
  } catch (e) {
    /* 티커 오류가 메인 보드를 막지 않게 */
  }
}

async function poll() {
  const result = await fetchPreview(PREVIEW_URL);

  if (result.ok) {
    lastSchedule = result.data;
    const j = JSON.stringify(result.data);
    if (j !== lastJSON) {
      lastJSON = j;
      paintBoard();
    }
    renderFooter(foot, lastSchedule, { stale: false });
  } else {
    if (lastSchedule) {
      renderFooter(foot, lastSchedule, { stale: true });
    } else {
      board.innerHTML = "";
      const msg = document.createElement("p");
      msg.textContent = "불러오는 중 문제가 발생했어요";
      msg.style.padding = "2rem";
      msg.style.textAlign = "center";
      msg.style.color = "var(--color-text-muted, #999)";
      board.appendChild(msg);
    }
  }
}

document.addEventListener("DOMContentLoaded", () => {
  poll();
  pollNotices();
  pollTweets();

  setInterval(poll, POLL_MS);
  setInterval(pollNotices, POLL_MS);
  setInterval(pollTweets, POLL_MS);

  // 1분마다 남은시간 텍스트 갱신. 카드가 다른 시간대 구간으로 넘어갔으면 보드 재렌더.
  setInterval(() => {
    if (updateCountdowns(board) && lastSchedule) paintBoard();
  }, COUNTDOWN_TICK_MS);

  // 모바일↔PC 경계(767px)를 넘으면 예고 버킷 구성이 달라지므로 재렌더.
  if (window.matchMedia) {
    window.matchMedia("(max-width: 767px)").addEventListener("change", () => {
      if (lastSchedule) paintBoard();
    });
  }
});
