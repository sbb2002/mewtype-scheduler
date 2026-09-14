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

/** 하단 디스클레이머 — 고정 문구 옆의 나머지 항목을 4초 간격으로 1개씩 순환 표시.
 * 한 줄 폭을 넘치면(2줄로 꺾이는 대신) notice 티커와 같은 방식의 무한 marquee 로.
 * 정적 콘텐츠(폴링 대상 아님) — 한 번만 초기화. */
function initDisclaimerRotator() {
  const cur = document.querySelector(".fdisc__cur");
  const items = document.querySelectorAll(".fdisc__list li");
  if (!cur || !items.length) return;
  let inner = cur.querySelector(".fdisc__cur-in");
  if (!inner) {
    inner = document.createElement("span");
    inner.className = "fdisc__cur-in";
    cur.appendChild(inner);
  }
  let i = 0;
  const show = () => {
    const text = "· " + items[i].textContent;
    i = (i + 1) % items.length;
    cur.classList.remove("is-marquee");
    inner.style.animation = "none";
    inner.textContent = "";
    const a = document.createElement("span");
    a.className = "seg";
    a.textContent = text;
    inner.appendChild(a);
    // 한 프레임 뒤 측정 — 애니메이션 none 해제도 여기서 (레이아웃 확정 후).
    requestAnimationFrame(() => {
      inner.style.animation = "";
      if (inner.scrollWidth > cur.clientWidth + 4) {
        const b = a.cloneNode(true);
        b.setAttribute("aria-hidden", "true");
        inner.appendChild(b);
        inner.style.setProperty("--dur", Math.max(9, text.length * 0.42).toFixed(1) + "s");
        cur.classList.add("is-marquee");
      }
    });
  };
  show();
  setInterval(show, 4000);
}

document.addEventListener("DOMContentLoaded", () => {
  poll();
  pollNotices();
  pollTweets();
  initDisclaimerRotator();

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

  // 모바일에서 다른 앱/탭으로 갔다 오면 setInterval 이 백그라운드 중 멈추거나
  // 크게 스로틀링돼(브라우저 스펙상 보장 안 됨), 복귀 직후엔 아주 오래된 lastSchedule
  // 로 카운트다운을 계산해 "372시간 지각" 같은 값이 잠깐 보인다(다음 poll 까지, 최대
  // POLL_MS 후 자연 복구 — 그 전엔 화면에 그대로 노출됨). 포그라운드 복귀를 감지해
  // 즉시 재조회해서 그 창을 없앤다. bfcache 복원(iOS 뒤로가기 등)은 visibilitychange
  // 가 안 뜰 수 있어 pageshow(persisted) 도 같이 건다.
  const refetchAll = () => {
    poll();
    pollNotices();
    pollTweets();
  };
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") refetchAll();
  });
  window.addEventListener("pageshow", (e) => {
    if (e.persisted) refetchAll();
  });
});
