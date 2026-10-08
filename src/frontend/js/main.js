import { fetchPreview } from "./api.js";
import { renderBoard, renderFooter, updateCountdowns } from "./render.js";
import { renderNotices, setBanners, refreshBanners } from "./notices.js";
import { renderTweets, reapplyTweets } from "./tweets.js";
import { initNewSongBadge, PLAYER_BUTTON_EVENT } from "./playerbtn.js";
import { PREVIEW_URL, ARCHIVE_URL, NOTICES_URL, TWEETS_URL, BANNERS_URL, POLL_MS, COUNTDOWN_TICK_MS } from "./config.js";

const board = document.getElementById("board");
const foot = document.getElementById("foot");
const notice = document.getElementById("notice");

let lastSchedule = null;
let lastArchive = null;   // (v4.1.0) 오늘 이미 끝난 방송 표시용 — 없어도 보드는 그려진다
let lastJSON = null;   // 내용이 안 바뀌면 renderBoard 생략 (모바일 캐러셀 위치 보존)

/** 보드 재구성 + 그 위에 개인 트윗 편지 배지 재적용 (renderBoard 가 배지를 지우므로). */
function paintBoard() {
  renderBoard(board, lastSchedule, Date.now(), lastArchive);
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

/** (v4a) 행사 배너 폴링 — 소식 란 펼침 맨 위. 404/오류면 배너 없이 둔다. */
async function pollBanners() {
  const r = await fetchPreview(BANNERS_URL);
  try {
    setBanners(notice, r.ok ? r.data : null);
  } catch (e) {
    /* 배너 오류가 소식 · 보드를 막지 않게 */
  }
}

/** (v4.1.0) 지난 방송 아카이브 폴링 — 타임테이블의 종료(회색) 블록. 바뀌었을 때만 보드를 다시 그린다. */
async function pollArchive() {
  const r = await fetchPreview(ARCHIVE_URL);
  if (!r.ok) return;
  const j = JSON.stringify(r.data);
  if (j === JSON.stringify(lastArchive)) return;
  lastArchive = r.data;
  if (lastSchedule) paintBoard();
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

// 이스터에그: "y" 입력 후 10초 안에 "umewapower"를 입력하면 모니터 페이지가 새 탭으로 열린다.
// 메인 예고판과 링크로 안 이어진 페이지라 이 트리거를 아는 사람만 접근 가능.
function initMonitorEasterEgg() {
  const PHRASE = "umewapower";
  const WINDOW_MS = 10000;
  let buf = "";
  let timer = null;
  document.addEventListener("keydown", (e) => {
    const tag = (e.target && e.target.tagName) || "";
    if (tag === "INPUT" || tag === "TEXTAREA") return;
    if (e.key.length !== 1) return; // 화살표/Shift 등 특수키 무시
    const ch = e.key.toLowerCase();
    if (timer === null && ch === "y") {
      buf = "y";
      timer = setTimeout(() => { buf = ""; timer = null; }, WINDOW_MS);
      return;
    }
    if (timer === null) return; // 캡처 윈도우 밖 — 무시
    buf += ch;
    if (buf.length > PHRASE.length) buf = buf.slice(-PHRASE.length);
    if (buf === PHRASE) {
      clearTimeout(timer);
      timer = null;
      buf = "";
      window.open("monitor.html", "_blank", "noopener");
    }
  });
}

// 이스터에그(모바일용): 풋터 버전 표시(ver. ♾️)를 5초 안에 15번 탭 — 탭마다 랜덤 멤버
// 아이콘이 풍선처럼 떠오르며 사라진다(순수 시각 피드백, 카운트 자체는 안 보여줌).
function initMonitorTapEasterEgg() {
  const TAP_GOAL = 15;
  const WINDOW_MS = 5000;
  const ICONS = ["arale", "yuno", "nonoka", "ritsu", "miyako"];
  const versionEl = document.getElementById("foot-version");
  if (!versionEl) return;

  let count = 0;
  let windowTimer = null;

  function spawnBalloon(x, y) {
    const img = document.createElement("img");
    img.className = "balloon-icon";
    img.src = `assets/member_icons/${ICONS[Math.floor(Math.random() * ICONS.length)]}.png`;
    img.alt = "";
    img.style.left = `${x}px`;
    img.style.top = `${y}px`;
    document.body.appendChild(img);
    img.addEventListener("animationend", () => img.remove());
  }

  versionEl.addEventListener("click", (e) => {
    const rect = versionEl.getBoundingClientRect();
    spawnBalloon(rect.left + rect.width / 2, rect.top);

    if (count === 0) {
      windowTimer = setTimeout(() => { count = 0; windowTimer = null; }, WINDOW_MS);
    }
    count += 1;
    if (count >= TAP_GOAL) {
      clearTimeout(windowTimer);
      windowTimer = null;
      count = 0;
      window.open("monitor.html", "_blank", "noopener");
    }
  });
}

// (v4.2.0) PC 하단 플레이어 도크 — ≥768px 에서만 보이고, 모바일로 넘어가면 팝업 본체를 모달로 되돌린다.
let playerMod = null;
let dockIO = null;
function syncPlayerDock() {
  const dock = document.getElementById("player-dock");
  if (!dock) return;
  if (!window.matchMedia("(min-width: 768px)").matches) {
    dock.hidden = true;
    if (dockIO) { dockIO.disconnect(); dockIO = null; }
    if (playerMod) playerMod.unmountDock();
    return;
  }
  dock.hidden = false;
  if (playerMod) { playerMod.mountDock(dock).catch((e) => console.error("[player]", e)); return; }
  if (dockIO) return;
  const load = () => {
    if (dockIO) { dockIO.disconnect(); dockIO = null; }
    import("./player.js").then((m) => {
      playerMod = m;
      if (window.matchMedia("(min-width: 768px)").matches) return m.mountDock(dock);
    }).catch((e) => console.error("[player]", e));
  };
  if (typeof IntersectionObserver !== "function") { load(); return; }
  dockIO = new IntersectionObserver((es) => { if (es.some((e) => e.isIntersecting)) load(); }, { rootMargin: "400px 0px" });
  dockIO.observe(dock);
}

document.addEventListener("DOMContentLoaded", () => {
  initMonitorEasterEgg();
  initMonitorTapEasterEgg();
  poll();
  pollArchive();
  pollNotices();
  pollTweets();
  pollBanners();
  initNewSongBadge();   // 최근 7일 안에 등록된 신곡이 있으면 CD 버튼(모바일)에 NEW
  // (v4.2.0) 모바일: 하단 아이콘 줄의 「CD + 음표 >」 버튼 → 플레이어 팝업. 처음 눌렀을 때만 모듈을 불러온다(YouTube API 도 그때 로드).
  document.addEventListener(PLAYER_BUTTON_EVENT, () => {
    import("./player.js").then((m) => { playerMod = m; m.openPlayer(); }).catch((e) => console.error("[player]", e));
  });
  // PC: 버튼 없이 메인 화면 맨 아래 도크에 플레이어를 둔다. 도크가 화면 근처로 오면 그때 모듈을 불러온다(안 내려가 보면 YouTube 도 안 부른다).
  syncPlayerDock();
  if (window.matchMedia) window.matchMedia("(min-width: 768px)").addEventListener("change", syncPlayerDock);
  initDisclaimerRotator();
  positionDisclaimerPopup();
  window.addEventListener("resize", positionDisclaimerPopup);
  const fdiscEl = document.querySelector(".fdisc");
  if (fdiscEl) {
    fdiscEl.addEventListener("mouseenter", positionDisclaimerPopup);
    fdiscEl.addEventListener("focusin", positionDisclaimerPopup);
  }

  setInterval(poll, POLL_MS);
  setInterval(pollArchive, POLL_MS);
  setInterval(pollNotices, POLL_MS);
  setInterval(pollTweets, POLL_MS);
  setInterval(pollBanners, POLL_MS);

  // 1분마다 남은시간 텍스트 · 타임테이블 지금 선 갱신. 오늘 구간(KST 06:00)이 바뀌었으면 보드 재렌더.
  setInterval(() => {
    if (updateCountdowns(board) && lastSchedule) paintBoard();
    try { refreshBanners(notice); } catch (e) { /* D-day · 상태 갱신 실패는 무시 */ }
  }, COUNTDOWN_TICK_MS);

  // 모바일↔PC 경계(767px)를 넘으면 화면 구성(타임테이블 ↔ 한 명씩 슬라이드)이 달라지므로 재렌더.
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
    pollArchive();
    pollNotices();
    pollTweets();
    pollBanners();
  };
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") refetchAll();
  });
  window.addEventListener("pageshow", (e) => {
    if (e.persisted) refetchAll();
  });
});
