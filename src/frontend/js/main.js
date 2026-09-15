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
    positionDisclaimerPopup();
  } else {
    if (lastSchedule) {
      renderFooter(foot, lastSchedule, { stale: true });
      positionDisclaimerPopup();
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

/** 하단 디스클레이머 — 5개 항목을 끊김(개별 전환) 없이 하나로 이어붙여 천천히
 * 연속 marquee 로 흘린다. 정적 콘텐츠(폴링 대상 아님) — 한 번만 초기화. */
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
  // 일반 스페이스는 CSS 상 연속 공백이 1칸으로 붕괴되므로(nowrap 도 collapse 는 적용됨)
  // 줄바꿈 없는 고정폭 공백(NBSP)으로 문구 사이 여백을 확보한다.
  const GAP = " ".repeat(10);
  const text = Array.from(items).map((li) => "· " + li.textContent).join(GAP);
  inner.textContent = "";
  const a = document.createElement("span");
  a.className = "seg";
  a.textContent = text;
  inner.appendChild(a);
  const b = a.cloneNode(true);
  b.setAttribute("aria-hidden", "true");
  inner.appendChild(b);
  inner.style.setProperty("--dur", Math.max(30, text.length * 0.6).toFixed(1) + "s");
  cur.classList.add("is-marquee");
}

/** 팝업(.fdisc__list) 가로 폭을 "업데이트 시각 오른쪽 끝 ~ 버전(♾️) 왼쪽 끝"에 맞춤.
 * PC 레이아웃 전용(모바일은 화면 중앙 고정폭 — css 미디어쿼리가 따로 덮어씀). */
function positionDisclaimerPopup() {
  const fdisc = document.querySelector(".fdisc");
  const updated = document.getElementById("foot-updated");
  const version = document.getElementById("foot-version");
  if (!fdisc || !updated || !version) return;
  if (window.matchMedia && window.matchMedia("(max-width: 767px)").matches) return;

  const fRect = fdisc.getBoundingClientRect();
  const uRect = updated.getBoundingClientRect();
  const vRect = version.getBoundingClientRect();
  fdisc.style.setProperty("--fdisc-list-left", `${uRect.right - fRect.left}px`);
  fdisc.style.setProperty("--fdisc-list-width", `${Math.max(0, vRect.left - uRect.right)}px`);
}

document.addEventListener("DOMContentLoaded", () => {
  poll();
  pollNotices();
  pollTweets();
  initDisclaimerRotator();
  positionDisclaimerPopup();
  window.addEventListener("resize", positionDisclaimerPopup);
  const fdiscEl = document.querySelector(".fdisc");
  if (fdiscEl) {
    fdiscEl.addEventListener("mouseenter", positionDisclaimerPopup);
    fdiscEl.addEventListener("focusin", positionDisclaimerPopup);
  }

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
