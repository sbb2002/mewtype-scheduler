import { fetchSchedule } from "./api.js";
import { renderBoard, renderFooter, updateCountdowns } from "./render.js";
import { renderNotices } from "./notices.js";
import { DATA_URL, NOTICES_URL, POLL_MS, COUNTDOWN_TICK_MS } from "./config.js";

const board = document.getElementById("board");
const foot = document.getElementById("foot");
const notice = document.getElementById("notice");

let lastSchedule = null;
let lastJSON = null;   // 내용이 안 바뀌면 renderBoard 생략 (모바일 캐러셀 위치 보존)

/**
 * Poll for new schedule data and update UI
 */
async function pollNotices() {
  // 소식은 스케줄과 독립. 404/오류면 티커를 그냥 숨긴 채 둔다.
  const r = await fetchSchedule(NOTICES_URL);
  try {
    renderNotices(notice, r.ok ? r.data : null);
  } catch (e) {
    /* 티커 오류가 메인 보드를 막지 않게 */
  }
}

async function poll() {
  const result = await fetchSchedule(DATA_URL);

  if (result.ok) {
    // Success: update with new data
    lastSchedule = result.data;
    const j = JSON.stringify(result.data);
    if (j !== lastJSON) {
      lastJSON = j;
      renderBoard(board, lastSchedule);
    }
    renderFooter(foot, lastSchedule, { stale: false });
  } else {
    // Failure
    if (lastSchedule) {
      // We have previous data: mark as stale
      renderFooter(foot, lastSchedule, { stale: true });
    } else {
      // First load failure: show error in board
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

// Initialize on DOMContentLoaded
document.addEventListener("DOMContentLoaded", () => {
  // Initial poll
  poll();
  pollNotices();

  // Set up recurring polls
  setInterval(poll, POLL_MS);
  setInterval(pollNotices, POLL_MS);

  // 1분마다 남은시간 텍스트 갱신 (사용자 장치 시계 기준).
  // 시간이 흘러 카드가 다른 시간대 구간으로 넘어갔으면 보드 재렌더.
  setInterval(() => {
    if (updateCountdowns(board) && lastSchedule) renderBoard(board, lastSchedule);
  }, COUNTDOWN_TICK_MS);
});
