import { fetchSchedule } from "./api.js";
import { renderBoard, renderFooter, updateCountdowns } from "./render.js";
import { DATA_URL, POLL_MS, COUNTDOWN_TICK_MS } from "./config.js";

const board = document.getElementById("board");
const foot = document.getElementById("foot");

let lastSchedule = null;
let lastJSON = null;   // 내용이 안 바뀌면 renderBoard 생략 (모바일 캐러셀 위치 보존)

/**
 * Poll for new schedule data and update UI
 */
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

  // Set up recurring polls
  setInterval(poll, POLL_MS);

  // Set up countdown updates
  setInterval(() => updateCountdowns(board), COUNTDOWN_TICK_MS);
});
