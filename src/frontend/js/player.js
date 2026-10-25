// player.js — (v4.2.0) 유메미타 플레이어: 팝업(재생부 + 검색·정렬·목록) · 팝업을 내린 뒤의 플로팅 프레임.
// 모바일: 열기는 playerbtn.js 가 발행하는 `mew:player-open` 이벤트 → main.js 가 이 모듈을 지연 import 해 openPlayer() 를 부른다.
// PC(≥768px): 버튼 없이 메인 화면 맨 아래 도크(#player-dock)에 팝업 본체를 상시 표시(mountDock). 도크가 화면 밖이면 재생 중인 프레임은 플로팅으로 남는다.
//
// 설계 원칙 (YouTube API 정책 — 개발자 정책 III.I.5 · III.I.7 · III.I.9, 필수 최소 기능):
//  - 재생은 YouTube IFrame Player API 의 임베드 프레임만 쓴다. 광고는 프레임 안에서 YouTube 가 처리 — 건너뛰기를 대신하지 않는다.
//  - 프레임은 숨기지 않는다(백그라운드 재생 금지). 팝업을 내리면 같은 프레임이 플로팅으로 남는다. 크기는 항상 200×200 이상.
//  - (v4.7.6) 모바일 플로팅 창은 화면 좌우 끝으로 밀어 넣을 수 있다 — 넣어도 영상 끝 14px 와 손잡이 탭이 화면에 남고 재생은 계속된다(운영자 결정 2026-10-24).
//  - 프레임 위에는 아무것도 덮지 않는다. 끌기 · 더블클릭용 손잡이 줄은 프레임 바깥(위)에 따로 붙는다.
//  - 프레임 요소는 한 번 만들면 옮기지 않는다(옮기면 iframe 이 다시 로드돼 재생이 끊긴다). 팝업 ↔ 플로팅은 CSS 위치만 바꾼다.
// 재생목록: 목록의 곡을 누르면 재생목록에 순서대로 쌓이고(같은 곡도 여러 번 쌓인다), 재생은 1번부터 순서대로 이어진다.
// 곡이 끝나면 재생목록의 다음 곡으로 넘어가고, 마지막이면 멈춘다. 재생목록 밖의 곡은 끝나면 멈춘다(추천 영상으로 넘어가지 않게 처음 화면으로 되돌림).
// 반복(BPM 과 같은 3단계): 꺼짐 → 한 곡(같은 곡 처음부터) → 전체(마지막 곡 뒤에 1번으로).
// 데이터는 textContent / createElement 로만 주입한다(XSS 방어, innerHTML 금지).

import { fetchPreview } from "./api.js";
import { SONGS_URL, SONGS_FALLBACK_URL, FALLBACK_CHANNELS } from "./config.js";
import { KIND_LABEL, displayKo, isNewSong, prepareSong, viewSongs, matchRange, kstDate, omakaseOrder, mediaCandidates, hasMv } from "./songs.js";
import { wireSheetDrag } from "./sheetdrag.js";   // (마이크로 인터랙션) 모바일 시트 끌어 내리기

const FLOAT_W = 356;                      // 플로팅 프레임 너비(16:9 에서 높이 200 이 되는 값)
const FLOAT_H = 200;                      // 플로팅 프레임 높이 — YouTube 임베드 최소 200×200 을 채운다
const MIN_SLOT_H = 200;                   // 팝업 안 프레임 최소 높이 (좁은 화면에서도 200 이상)
const NS = "http://www.w3.org/2000/svg";
// (v4.7.6) 모바일 가장자리 넣기 — 수치는 ref 데모(player-edge-tuck.html)와 같다
const TUCK_TAB = 24;     // 넣었을 때 남는 손잡이 탭 폭
const TUCK_VIS = 14;     // 넣었을 때 화면 안에 남는 영상 폭 (영상 일부가 보이게 — 운영자 결정 2026-10-24)
const TUCK_ARM = 56;     // 화면 끝에 닿은 뒤 이만큼 더 밀면 「다 참」 — 놓으면 들어간다
const TUCK_PUSH = 44;    // 미는 동안 창이 화면 밖으로 밀려 들어가는 최대 거리(저항)
const TUCK_PULL = 44;    // 넣은 탭을 바깥으로 이만큼 끌면 꺼낸다
const TUCK_INSET = 16;   // 꺼냈을 때 화면 끝과의 간격
const tuckable = () => !st.dock && window.matchMedia && matchMedia("(max-width: 767px)").matches;   // 모바일 플로팅에서만
const floatW = () => el.fmain.offsetWidth;          // 탭을 뺀 본체 폭 (프레임 폭은 넣으면 탭만큼 넓어진다)
const tuckedLeft = (side) => side === "l" ? -(floatW() - TUCK_VIS) : innerWidth - TUCK_TAB - TUCK_VIS;   // 넣었을 때 프레임 left
const clamp = (v, a, b) => Math.min(Math.max(v, a), b);
const vibrate = (ms) => { try { if (navigator.vibrate) navigator.vibrate(ms); } catch (e) { /* 무시 */ } };
const calm = () => !!(window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches);   // 움직임 줄이기
const isPhone = () => !!(window.matchMedia && matchMedia("(max-width: 767px)").matches);
const restartCls = (e, cls) => { e.classList.remove(cls); void e.offsetWidth; e.classList.add(cls); };   // 같은 애니메이션을 처음부터 다시
const GRIP_TIP_KEY = "mew.tip.grip-dblclick";   // (마이크로 인터랙션) 손잡이 더블클릭 안내를 본 적 있음 — 이 브라우저에 기록이 남아 있는 동안 다시 안 띄운다
const MEDIA_KEY = "mew.player.media";           // (v4.8.3) 고른 영상 종류 "audio" | "mv" — 이 브라우저에 남는다
const MV_TIP_KEY = "mew.tip.mv-mode";           // (v4.8.3) MV 로 처음 바꿀 때 안내를 본 적 있음 — GRIP_TIP_KEY 와 같은 방식

const st = {
  raw: [],
  songs: [],          // prepareSong 결과
  loadError: false,
  query: "",
  kind: "all",
  sortBy: "date",
  dir: "desc",
  curId: null,        // 곡 id — 곡을 구별하는 값(재생목록 · 들은 곡 · 선택 상태)
  vid: null,          // (v4.8.3) 지금 프레임에 올린 영상 ID — YouTube 호출은 전부 이 값으로
  cands: [],          // (v4.8.3) 이 곡의 남은 재생 후보 영상 ID (vid 제외) — 재생 불가면 여기서 다음 것을 올린다
  media: readMediaPref(),   // (v4.8.3) "audio" | "mv" — [음원 | MV] 전환 (localStorage mew.player.media)
  playing: false,
  started: false,     // 한 번이라도 재생을 시작했는가 — 팝업을 내린 뒤 플로팅 프레임을 남길지 결정
  popOpen: false,
  closing: false,     // 모바일 시트가 내려가는 중 — 끝날 때까지 프레임은 재생부 자리를 따른다
  dock: null,         // PC 하단 도크 컨테이너(#player-dock). 있으면 팝업 본체가 거기 상시 표시된다
  slotVisible: false, // 도크의 재생부가 화면에 보이는가
  tab: "songs",       // 모바일 아래 영역 탭 — "songs" | "queue" (팝업을 다시 열어도 유지). PC 에서는 안 쓴다
  shuffle: false,
  repeat: "off",      // "off" | "one" | "all" — 버튼을 누를 때마다 순환 (BPM 과 같다)
  queue: [],          // 재생목록 — 곡 id 를 쌓은 순서대로(같은 곡을 여러 번 쌓을 수 있다)
  played: new Set(),  // 셔플 한 바퀴 동안 이미 재생한 재생목록 위치들 — 남은 곡 중에서만 무작위로 고른다
  qi: -1,           // 지금 곡의 재생목록 위치(0부터). -1 = 지금 곡이 재생목록에서 고른 것이 아님 — 같은 곡이 여럿일 수 있어 id 가 아니라 위치로 센다
  omaOpen: false,     // 랜덤플리 오마카세 말풍선이 열려 있는가
  omaBusy: false,     // 뒤섞임 연출 + 5초 쿨타임 중 — 버튼 잠금
  fpos: null,         // 플로팅 프레임을 끌어 옮긴 위치 {x,y}. null 이면 CSS 기본(오른쪽 아래)
  tuck: null,         // (v4.7.6) 모바일 가장자리 넣기 — "l" | "r" | null. 넣은 상태에서도 st.fpos.y 를 높이로 쓴다
  pos: 0,
  dur: 0,
  error: null,        // {id, code} — 임베드 불가 등 재생 오류
};

const el = {};        // 만들어 둔 DOM 참조
let built = false;
let yt = null;        // YT.Player
let ytReady = false;
let ytPromise = null;
let tickTimer = null;
let lastFocus = null;
let loadPromise = null;
let wantPlay = false;  // 플레이어가 준비되기 전에 요청된 곡의 자동 재생 여부
let listenedId = null; // (v4.8.1) 이번에 고른 곡의 재생을 이미 기록했는가 — 일시정지 후 다시 재생 · 한 곡 반복은 새로 기록하지 않는다

// (v4.8.1) 들은 곡 기록 — localStorage `ymmt_listened` = {곡 id: 마지막으로 재생한 날(KST "YYYY-MM-DD")}. 랜덤플리 오마카세가 순서를 정할 때 읽는다.
// 이 브라우저에만 남는다. 저장소를 못 쓰면(차단 · 시크릿 창) 기록 없이 동작 — 오마카세는 전부 안 들은 곡으로 보고 섞는다.
const LISTENED_KEY = "ymmt_listened";
function readListened() {
  try {
    const v = JSON.parse(localStorage.getItem(LISTENED_KEY) || "{}");
    return v && typeof v === "object" && !Array.isArray(v) ? v : {};
  } catch (e) { return {}; }
}
function markListened(id) {
  try {
    const v = readListened();
    v[id] = kstDate();
    localStorage.setItem(LISTENED_KEY, JSON.stringify(v));
  } catch (e) { /* 기록 못 해도 재생은 그대로 */ }
}

// (v4.8.3) 영상 종류 기억 — 저장소를 못 쓰면 음원으로 시작하고, 고른 값은 이 페이지를 연 동안만 유지된다.
function readMediaPref() { try { return localStorage.getItem(MEDIA_KEY) === "mv" ? "mv" : "audio"; } catch (e) { return "audio"; } }
function writeMediaPref(v) { try { localStorage.setItem(MEDIA_KEY, v); } catch (e) { /* 이 페이지를 연 동안만 */ } }
function mvTipSeen() { try { return localStorage.getItem(MV_TIP_KEY) === "1"; } catch (e) { return false; } }

// ── DOM 헬퍼 ─────────────────────────────────────────────────────────
function h(tag, props = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (v == null || v === false) continue;
    if (k === "class") e.className = v;
    else if (k === "text") e.textContent = v;
    else if (k === "on") for (const [ev, fn] of Object.entries(v)) e.addEventListener(ev, fn);
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const c of kids.flat()) if (c != null && c !== false) e.append(c);
  return e;
}

const ICONS = {
  play: ["M7 4v16l13-8z"],
  pause: ["M6 4h4v16H6zM14 4h4v16h-4z"],
  prev: ["M6 4h2v16H6zM20 4v16L9 12z"],
  next: ["M16 4h2v16h-2zM4 4v16l11-8z"],
  shuffle: ["M3 7h4l10 10h4v2h-5L6 9H3zM3 15h3l2-2 1.4 1.4L7 17H3zM17 7h4v2h-4L14 12l-1.4-1.4z"],
  repeat: ["M7 7h10v3l4-4-4-4v3H5v6h2zM17 17H7v-3l-4 4 4 4v-3h12v-6h-2z"],
  note: ["M9 18V4.6L20 2.6V16H18V5.9L11 7.2V18Z", "M9 18a2.5 2.5 0 1 1-5 0 2.5 2.5 0 1 1 5 0z", "M20 16a2.5 2.5 0 1 1-5 0 2.5 2.5 0 1 1 5 0z"],   // (v4.8.3) 음표 — 채운 모양 세 조각
  film: ["M3 5h18a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1zM9.5 9v6l5-3z"],   // (v4.8.3) 화면 + 재생 삼각형(evenodd 로 뚫는다)
  search: null,
};
const EVENODD = new Set(["film"]);

function icon(name, cls = "mp-ico") {
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  svg.setAttribute("class", cls);
  if (name === "search") {
    const c = document.createElementNS(NS, "circle");
    c.setAttribute("cx", "10"); c.setAttribute("cy", "10"); c.setAttribute("r", "6");
    c.setAttribute("fill", "none"); c.setAttribute("stroke", "currentColor"); c.setAttribute("stroke-width", "2");
    const l = document.createElementNS(NS, "path");
    l.setAttribute("d", "M15 15l5 5"); l.setAttribute("stroke", "currentColor"); l.setAttribute("stroke-width", "2");
    svg.append(c, l);
    return svg;
  }
  for (const d of ICONS[name]) {
    const p = document.createElementNS(NS, "path");
    p.setAttribute("d", d);
    p.setAttribute("fill", "currentColor");
    if (EVENODD.has(name)) p.setAttribute("fill-rule", "evenodd");
    svg.append(p);
  }
  if (name === "repeat") {   // 반복 화살표 안의 글자 — 한 곡 "1" · 전체 "A" (paintControls 가 채운다)
    const t = document.createElementNS(NS, "text");
    t.setAttribute("class", "mp-rpt");
    t.setAttribute("x", "12"); t.setAttribute("y", "15"); t.setAttribute("font-size", "7"); t.setAttribute("font-weight", "700");
    t.setAttribute("text-anchor", "middle"); t.setAttribute("fill", "currentColor"); t.textContent = "";
    svg.append(t);
  }
  return svg;
}

function iconBtn(name, label, cls, onClick) {
  return h("button", { type: "button", class: cls, "aria-label": label, title: label, on: { click: onClick } }, icon(name));
}

/** 꺾쇠 svg — 가장자리 빛 띠(mp-edge__chev)와 넣은 탭(mp-ftab__chev) 공용. cls 가 빈 문자열이면 class 를 달지 않는다. */
function chevSvg(cls, vb, d, sw) {
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", vb);
  if (cls) svg.setAttribute("class", cls);
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  const p = document.createElementNS(NS, "path");
  p.setAttribute("d", d);
  p.setAttribute("fill", "none");
  p.setAttribute("stroke", "currentColor");
  p.setAttribute("stroke-width", sw);
  p.setAttribute("stroke-linecap", "round");
  p.setAttribute("stroke-linejoin", "round");
  svg.append(p);
  return svg;
}

/** 넣었을 때 화면 끝에 남는 손잡이 탭 — 누르기 · 바깥으로 끌기 = 꺼냄. 평소엔 폭 0(CSS). */
function tuckTab(side) {
  return h("button", { type: "button", class: `mp-ftab mp-ftab--${side}`, "aria-label": "플레이어 꺼내기", title: "눌러서 꺼내기", tabindex: "-1" },
    h("span", { class: "mp-ftab__in" },
      chevSvg("mp-ftab__chev", "0 0 14 14", "M5 2l5 5-5 5", "2"),
      h("span", { class: "mp-ftab__eq" }, h("i"), h("i"), h("i")),
      h("span", { "aria-hidden": "true", text: "⠿" }),
    ));
}

const fmt = (t) => {
  t = Math.max(0, Math.floor(t || 0));
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`;
};

// ── 데이터 ───────────────────────────────────────────────────────────
function loadSongs() {
  if (loadPromise) return loadPromise;
  const valid = (r) => r.ok && r.data && Array.isArray(r.data.songs);
  // data 브랜치 songs.json(신곡 자동 등록) 우선, 없으면 정적 파일
  loadPromise = fetchPreview(SONGS_URL).then((r) => (valid(r) ? r : fetchPreview(SONGS_FALLBACK_URL))).then((r) => {
    if (!valid(r)) { st.loadError = true; loadPromise = null; return; }
    st.loadError = false;
    st.raw = r.data.songs;
    st.songs = st.raw.map((s) => prepareSong(s));
  });
  return loadPromise;
}

const view = () => viewSongs(st.songs, { query: st.query, kind: st.kind, sortBy: st.sortBy, dir: st.dir });
const curSong = () => st.songs.find((s) => s.id === st.curId) || null;

/** 멤버 표시 — 이름(성 제외)과 색. 색은 타임테이블 레인 색(아바타 평균색)을 그대로 쓴다. 그룹은 소식·합동과 같은 바이올렛. */
function memberOf(key) {
  if (!key) return null;
  if (key === "group") return { name: "夢限大みゅーたいぷ", color: "var(--color-collab)" };
  const ch = FALLBACK_CHANNELS[key];
  if (!ch) return null;
  const lane = document.querySelector(`.lane[data-channel="${CSS.escape(key)}"]`);
  const c = lane ? getComputedStyle(lane).getPropertyValue("--lane-color").trim() : "";
  return { name: ch.name_ko.split(" ").pop(), color: c || "var(--color-text-muted)" };
}

/** 부른 사람들(멤버 표시 목록) — singers 가 있으면 그 멤버들, 없으면 who 하나. 멤버가 아니면 빈 배열 (v4.8.3). */
function memberList(s) {
  const keys = Array.isArray(s.singers) && s.singers.length ? s.singers : [s.who];
  return keys.map((k) => memberOf(k)).filter(Boolean);
}
/** 재생부 메타용 노드 — 점(멤버마다 하나) + 이름「아라레, 리츠」 + 「 · 」(종류 · 날짜와 잇기). 멤버가 없으면 빈 배열. */
function memberNodes(s) {
  const ms = memberList(s);
  if (!ms.length) return [];
  return [...ms.map((m) => h("span", { class: "mp-dot", style: `--mc:${m.color}` })), ms.map((m) => m.name).join(", "), " · "];
}

// ── YouTube IFrame API ───────────────────────────────────────────────
function loadYT() {
  if (ytPromise) return ytPromise;
  ytPromise = new Promise((resolve, reject) => {
    if (window.YT && window.YT.Player) { resolve(window.YT); return; }
    const prev = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = () => { if (typeof prev === "function") prev(); resolve(window.YT); };
    const s = document.createElement("script");
    s.src = "https://www.youtube.com/iframe_api";
    s.onerror = () => reject(new Error("YouTube API 로드 실패"));
    document.head.append(s);
    setTimeout(() => reject(new Error("YouTube API 시간 초과")), 10000);
  }).catch((e) => { ytPromise = null; throw e; });
  return ytPromise;
}

async function ensurePlayer(videoId, autoplay) {
  if (yt) return;
  try {
    const YT = await loadYT();
    if (yt) return;
    const vars = { playsinline: 1, rel: 0 };
    if (/^https?:$/.test(location.protocol)) vars.origin = location.origin;
    yt = new YT.Player(el.ytTarget, {
      width: "100%",
      height: "100%",
      videoId,
      playerVars: vars,
      events: {
        onReady: () => {
          ytReady = true;
          const f = yt.getIframe();
          if (f) f.setAttribute("title", "YouTube 플레이어");
          // 로딩 중에 다른 영상이 골라졌으면 그 영상으로 바꾼다
          try {
            if (st.vid && st.vid !== videoId) loadVid(st.vid, wantPlay);
            else { watchStart(videoId, wantPlay); if (wantPlay) yt.playVideo(); }
          } catch (e) { /* 자동 재생 거부는 YouTube 쪽 컨트롤로 */ }
          startTick();
        },
        onStateChange: onYtState,
        onError: () => onUnplayable(),   // (v4.8.3) 오류 코드가 무엇이든 재생 불가 — 후보 · 안내 · 다음 곡으로 처리
      },
    });
  } catch (e) {
    st.error = { id: st.vid, code: "api" };   // 플레이어 API 로드 실패만 「YouTube 에서 보기」 오류로 남긴다
    paint();
  }
}

function onYtState(e) {
  const S = window.YT.PlayerState;
  if (e.data === S.PLAYING || e.data === S.BUFFERING) { st.playing = true; st.started = true; st.error = null; }
  if (e.data === S.PLAYING) { skipRun = 0; watchStop(); }   // 실제로 재생이 시작됐을 때만 감시 해제 — 프리미어 대기 영상도 잠깐 BUFFERING 을 거친다(2026-10-25 실측)
  if (e.data === S.PLAYING && st.curId && listenedId !== st.curId) { listenedId = st.curId; markListened(st.curId); }   // (v4.8.1) 곡이 재생되는 시점에 기록
  else if (e.data === S.PAUSED || e.data === S.CUED) st.playing = false;
  else if (e.data === S.ENDED) {
    if (st.repeat === "one") { yt.seekTo(0, true); yt.playVideo(); return; }
    if (nextInQueue()) return;   // 재생목록의 다음 곡(셔플 · 전체 반복 포함). 재생목록 밖이면 멈춘다
    st.playing = false;
    st.pos = 0;
    yt.cueVideoById(st.vid);   // 처음 화면으로 되돌려 멈춘다 — 끝 화면의 추천 영상으로 넘어가지 않게
  }
  paint();
}

function startTick() {
  if (tickTimer) return;
  tickTimer = setInterval(() => {
    if (!yt || !ytReady || typeof yt.getCurrentTime !== "function") return;
    if (trackDrag) return;   // 끄는 중엔 재생 위치로 덮어쓰지 않는다
    st.pos = yt.getCurrentTime() || 0;
    st.dur = yt.getDuration() || 0;
    paintProgress();
  }, 500);
}

/** 곡 선택. autoplay=true 면 바로 재생(사용자 조작 직후에만), false 면 첫 화면만 불러 둔다. */
/** qi = 이 곡의 재생목록 위치(재생목록에서 고른 경우). 아니면 -1. */
function selectSong(id, autoplay, qi = -1) {
  if (!skipping) skipRun = 0;   // 사용자가 고른 곡이면 재생 불가 연속 넘김을 처음부터 다시 센다
  hideSkip();
  deadId = null;
  st.curId = id;
  st.qi = qi;
  listenedId = null;   // 새로 고른 곡은 재생이 시작될 때 다시 기록한다
  st.pos = 0;
  st.dur = 0;
  st.error = null;
  if (autoplay) st.started = true;
  wantPlay = autoplay;
  const song = st.songs.find((x) => x.id === id);
  const cands = song ? mediaCandidates(song, st.media) : [id];   // (v4.8.3) 음원 · MV 후보를 시도 순서대로 — 고를 때마다 무작위
  st.cands = cands.slice(1);
  st.vid = cands[0];   // 플레이어가 준비되기 전에 골라도 onReady 가 이 영상으로 맞춘다
  if (!yt) ensurePlayer(cands[0], autoplay);
  else if (ytReady) loadVid(cands[0], autoplay);
  paint();
}

// ── (v4.8.3) 영상 올리기 · 재생 불가 처리 ─────────────────────────────
const WATCH_MS = 8000;   // 자동 재생을 요청한 뒤 이 안에 재생이 없고 길이도 0 이면 재생 불가로 본다 (그 밖의 멈춤)
const WATCH_FAST_MS = 2000;   // 프리미어 대기 영상(getVideoData().isPremiere · 길이 0)은 2초에 판정 — 운영자 결정 2026-10-25(8초는 너무 길다)
const SKIP_MS = 3000;    // 재생 불가 안내를 보여 주는 시간 — 지나면 다음 곡
let watch = null;        // {vid, timer} — 재생 불가 감시 중인 영상
let skipRun = 0;         // 재생 불가로 연속 넘긴 횟수 — 곡 수를 넘으면 멈춘다(반복 목록이 전부 재생 불가일 때 무한 순환 방지)
let skipping = false;    // 재생 불가 뒤 넘기는 중 — 이때의 selectSong 은 skipRun 을 지우지 않는다
let skipTimer = 0;
let deadId = null;       // 불러 두기만 했는데 후보가 모두 재생 불가였던 곡 id — ▶ 를 누르면 다시 골라(자동 재생) 안내 · 넘김을 탄다

function watchStop() { if (watch) { clearTimeout(watch.fast); clearTimeout(watch.timer); watch = null; } }
/** 자동 재생을 요청해 올린 영상을 지켜본다 — 2초에 프리미어 대기 판정, WATCH_MS 에 일반 판정. cue 만 하는 경우(autoplay=false)는 지키지 않는다. */
function watchStart(vid, autoplay) {
  watchStop();
  if (!autoplay) return;
  const w = { vid, fast: 0, timer: 0 };
  w.fast = setTimeout(() => watchCheck(w, true), WATCH_FAST_MS);
  w.timer = setTimeout(() => watchCheck(w, false), WATCH_MS);
  watch = w;
}
function watchCheck(w, fast) {
  if (watch !== w) return;
  if (!fast) watch = null;
  if (st.vid !== w.vid || !yt || !ytReady) return;
  let state, dur, premiere;
  try { state = yt.getPlayerState(); dur = yt.getDuration() || 0; premiere = !!(yt.getVideoData() || {}).isPremiere; } catch (e) { return; }
  const S = window.YT.PlayerState;
  if (state === S.PLAYING || dur > 0) return;
  if (!fast || premiere) onUnplayable();   // 재생을 시작 못 했고 길이도 없음 — 프리미어 대기면 2초, 그 밖은 8초(실측: 상태 -1 · 길이 0 · isPremiere)
}

/** 영상 하나를 프레임에 올린다. autoplay 면 재생을 요청하고 재생 불가 감시를 건다. */
function loadVid(vid, autoplay) {
  st.vid = vid;
  watchStart(vid, autoplay);
  try { autoplay ? yt.loadVideoById(vid) : yt.cueVideoById(vid); } catch (e) { /* 오류는 onError 로 */ }
}

/** 재생 불가 — 오류(onError) 또는 감시 실패. 남은 후보가 있으면 문구 없이 다음 후보를 올리고, 다 떨어지면 안내 뒤 다음 곡(넘어갈 곡이 없으면 멈춘다). */
function onUnplayable() {
  watchStop();
  if (st.cands.length) { loadVid(st.cands.shift(), wantPlay); paint(); return; }
  st.playing = false;
  st.pos = 0;
  st.dur = 0;
  if (!wantPlay) { deadId = st.curId; paint(); return; }   // 불러 두기만 한 곡(첫 화면 등) — 사용자가 틀기 전엔 안내 · 넘김 없이 둔다(▶ 를 누르면 togglePlay 가 다시 고른다)
  const more = st.qi >= 0 ? queueHasNext() : listHasNext();
  showSkip(more ? "이 곡은 지금 재생이 불가능해요… 다음 곡으로 넘어갈게요!" : "이 곡은 지금 재생이 불가능해요.");
  skipTimer = setTimeout(() => { skipTimer = 0; hideSkip(); if (more) skipAway(); }, SKIP_MS);
  paint();
}
/** 재생 불가 안내 뒤 다음 곡으로 — 재생목록 안이면 재생목록 규칙, 밖이면 목록 다음 곡. 연속으로 곡 수만큼 넘겼으면 멈춘다. */
function skipAway() {
  skipRun += 1;
  if (skipRun > (st.qi >= 0 ? st.queue.length : view().length)) return;   // 재생목록 안이면 재생목록 곡 수, 밖이면 목록 곡 수만큼 넘겼으면 멈춘다
  skipping = true;
  try {
    if (st.qi >= 0) nextInQueue();
    else { const id = listNext(); if (id) selectSong(id, true); }
  } finally { skipping = false; }
}
/** 재생목록 안에서 다음 곡으로 넘어간다(셔플 · 다음 · 전체 반복). 넘어갔으면 true. 재생목록 밖(qi < 0)이면 false. */
function nextInQueue() {
  if (st.qi < 0) return false;
  if (st.shuffle) {   // 아직 안 들은 곡 중 무작위, 다 들었으면 전체 반복일 때만 새 바퀴
    const n = pickShuffle();
    if (n >= 0) { playQueueAt(n); return true; }
    if (st.repeat === "all") { playQueueAt(pickShuffle(true)); return true; }
    return false;
  }
  if (st.qi + 1 < st.queue.length) { playQueueAt(st.qi + 1); return true; }   // 재생목록의 다음 곡
  if (st.repeat === "all") { playQueueAt(0); return true; }                    // 마지막 뒤에 1번으로
  return false;
}
/** nextInQueue 가 넘어갈 곡이 있는가 (고르지 않고 확인만). */
function queueHasNext() {
  if (st.qi < 0) return false;
  if (st.shuffle) return st.repeat === "all" || st.queue.some((_, k) => k !== st.qi && !st.played.has(k));
  return st.qi + 1 < st.queue.length || st.repeat === "all";
}
/** 재생목록 밖 — 목록에서 지금 곡 다음 곡(셔플이면 지금 곡 말고 무작위). 없으면 null. */
function listNext() {
  const list = view();
  if (!listHasNext()) return null;
  if (st.shuffle) { const others = list.filter((s) => s.id !== st.curId); return others[Math.floor(Math.random() * others.length)].id; }
  const i = list.findIndex((s) => s.id === st.curId);
  return list[(i + 1) % list.length].id;
}
function listHasNext() { return view().some((s) => s.id !== st.curId); }

/** 재생 불가 안내 — 플로팅 창이면 창 바로 위에, 그 밖이면 재생부 컨트롤 아래에 띄운다. */
function showSkip(text) {
  if (!el.skip) return;
  el.skipT.textContent = text;
  el.skip.hidden = false;
  placeSkip();
  restartCls(el.skip, "is-on");
}
function hideSkip() {
  clearTimeout(skipTimer);
  skipTimer = 0;
  if (el.skip) { el.skip.hidden = true; el.skip.classList.remove("is-on"); }
}
/** 안내 자리 — 플로팅 창이면 body 에 고정 위치로(손잡이 위 8px, 영상 위는 덮지 않는다), 그 밖에서는 재생부 안 흐름(.mp-err 위쪽). */
function placeSkip() {
  if (!el.skip) return;
  if (el.frame.classList.contains("is-float") && !el.frame.hidden) {
    if (el.skip.parentElement !== document.body) document.body.append(el.skip);
    const g = el.grip.getBoundingClientRect(), w = el.skip.offsetWidth;
    el.skip.classList.add("is-fixed");
    el.skip.style.left = `${clamp(g.left, 8, Math.max(8, innerWidth - w - 8))}px`;
    el.skip.style.bottom = `${innerHeight - g.top + 8}px`;
  } else if (el.skip.parentElement !== el.stage) {
    el.stage.insertBefore(el.skip, el.err);
    el.skip.classList.remove("is-fixed");
    el.skip.style.left = "";
    el.skip.style.bottom = "";
  }
}

/** [음원 | MV] 전환 — 저장한다. 영상이 재생 중이거나 중간까지 들었으면 **그 영상은 그대로** 두고 「다음 영상부터 …로 재생됩니다.」를 띄운다(운영자 결정 2026-10-25).
 *  아직 틀지 않은 곡(처음 화면)이면 지금 곡을 그 모드로 바로 다시 불러 둔다(MV 가 없는 곡이면 그대로). MV 로 처음 바꿀 때는 MV 안내를 한 번 함께 보인다. */
let mvTipShown = false, mvTipTimer = 0;
function setMedia(mode) {
  if (mode === st.media) return;
  st.media = mode;
  writeMediaPref(mode);
  const first = mode === "mv" && !mvTipShown && !mvTipSeen();   // 처음 MV 로 바꿀 때 한 번만 안내
  if (first) {
    mvTipShown = true;
    try { localStorage.setItem(MV_TIP_KEY, "1"); } catch (e) { /* 이 페이지를 연 동안만 */ }
  }
  const HINT = "MV가 있는 곡은 MV로, 없는 곡은 음원으로 보여줘요";
  const s = curSong();
  if (s && (st.playing || st.pos > 0)) {
    showMediaTip(`다음 영상부터 ${mode === "mv" ? "MV로" : "음원으로"} 재생됩니다.`, first ? HINT : "", first ? 4500 : 2600);
    paint();
    return;
  }
  if (first) showMediaTip(HINT, "", 4500);
  if (s && hasMv(s)) selectSong(st.curId, false, st.qi);
  else paint();
}
/** 전환 버튼 아래 말풍선 — main(굵게) + sub(작게, 없으면 숨김)를 ms 동안. */
function showMediaTip(main, sub, ms) {
  el.mvTipMain.textContent = main;
  el.mvTipSub.textContent = sub;
  el.mvTipSub.hidden = !sub;
  el.mvTip.style.animationDuration = `${ms}ms`;
  el.mvTip.hidden = false;
  restartCls(el.mvTip, "is-on");
  clearTimeout(mvTipTimer);
  mvTipTimer = setTimeout(() => { el.mvTip.classList.remove("is-on"); el.mvTip.hidden = true; }, ms);
}

function togglePlay() {
  if (!st.curId && !st.queue.length) return;
  // 재생목록이 있는데 지금 곡이 그 안에 없으면 1번부터 시작한다(멈춰 있을 때만 — 재생 중 일시정지는 그대로)
  if (st.queue.length && !st.playing && st.qi < 0) { playQueueAt(0); return; }
  st.started = true;
  if (deadId && deadId === st.curId) { selectSong(st.curId, true, st.qi); return; }   // (v4.8.3) 불러 둘 때 재생 불가였던 곡 — 다시 골라 후보 · 안내 · 넘김을 탄다
  if (yt && ytReady) {
    if (st.playing) yt.pauseVideo();
    else { wantPlay = true; watchStart(st.vid, true); yt.playVideo(); }   // (v4.8.3) 처음 화면만 불러 둔 영상을 ▶ 로 틀 때도 재생 불가 감시 · 폴백 후보도 자동 재생
  } else {
    selectSong(st.curId, true);
  }
  paint();
}

function go(dir) {
  if (st.queue.length) {   // 재생목록이 있으면 그 안에서 이동 (셔플이면 무작위)
    const q = st.queue;
    let next;
    if (st.shuffle) {
      next = pickShuffle();
      if (next < 0) next = pickShuffle(true);   // 한 바퀴를 다 들었으면 새 바퀴
    } else {
      next = st.qi < 0 ? 0 : (st.qi + dir + q.length) % q.length;
    }
    playQueueAt(next);
    return;
  }
  const list = view();
  if (!list.length) return;
  let next;
  if (st.shuffle && list.length > 1) {
    do { next = list[Math.floor(Math.random() * list.length)]; } while (next.id === st.curId);
  } else {
    const i = list.findIndex((s) => s.id === st.curId);
    next = i < 0 ? list[0] : list[(i + dir + list.length) % list.length];
  }
  selectSong(next.id, true);
}

// ── 재생목록 ─────────────────────────────────────────────────────────
/** 곡 누름 — 재생목록 맨 뒤에 쌓는다(같은 곡을 또 눌러도 또 쌓인다 — 빠지지 않음). **재생목록이 비어 있다가 처음 들어가는 곡은 쌓이면서 바로 재생한다**(누른 직후라 자동 재생이 막히지 않는다). 이후 곡은 쌓기만 한다. */
function addToQueue(id) {
  st.queue.push(id);
  if (st.queue.length === 1) selectSong(id, true, 0);
  else paint();
  pulseBadge();   // 추가됐음을 배지로 알린다 — 탭은 그대로(곡 목록)
}
/** 셔플로 다음에 틀 재생목록 위치. 이번 바퀴에 아직 안 튼 곡 중 무작위 — 없으면 -1.
 *  newRound=true 면 바퀴를 새로 시작해(지금 곡만 들은 것으로) 남은 곡 중에서 고른다(곡이 하나뿐이면 그 곡). */
function pickShuffle(newRound = false) {
  if (newRound) st.played = new Set(st.qi >= 0 ? [st.qi] : []);
  const rest = [];
  for (let k = 0; k < st.queue.length; k++) if (!st.played.has(k) && k !== st.qi) rest.push(k);
  if (rest.length) return rest[Math.floor(Math.random() * rest.length)];
  return newRound && st.queue.length ? (st.qi >= 0 ? st.qi : 0) : -1;
}
/** 재생목록의 i 번째 곡으로 이동 · 재생. */
function playQueueAt(i) {
  if (i < 0 || i >= st.queue.length) return;
  st.played.add(i);
  selectSong(st.queue[i], true, i);
}
/** i 번째 항목을 뺀다. 지금 곡이 빠지면 그 곡은 끝까지 재생되고 거기서 멈춘다(재생목록에서 고른 곡이 아니게 됨). */
function removeFromQueue(i) {
  if (i < 0 || i >= st.queue.length) return;
  st.queue.splice(i, 1);
  st.played = new Set([...st.played].filter((k) => k !== i).map((k) => (k > i ? k - 1 : k)));   // 위치가 한 칸씩 당겨진다
  if (i < st.qi) st.qi -= 1;
  else if (i === st.qi) st.qi = -1;
  paint();
}
/** (마이크로 인터랙션) 재생목록 줄을 접으며 뺀다 — ✕ · 밀어서 빼기 공용. 접히는 동안 목록이 다시 그려져도 같은 곡 위치를 다시 찾는다. */
function removeAnimated(i, li) {
  const id = st.queue[i];
  const done = () => {
    const k = st.queue[i] === id ? i : st.queue.indexOf(id);
    if (k >= 0) removeFromQueue(k);
  };
  if (!li || calm()) { done(); return; }
  li.inert = true;
  li.style.overflow = "hidden";
  li.animate([{ height: li.offsetHeight + "px", opacity: 1 }, { height: "0px", opacity: 0 }],
    { duration: 240, easing: "cubic-bezier(.4,0,.2,1)", fill: "forwards" }).onfinish = done;
}
/** 「비우기」 — 줄들이 차례로 떨어진 뒤 비우고, 5초 동안 「되돌리기」를 띄운다.
 *  되돌리면 비운 곡들을 원래 순서대로 앞에 다시 넣는다(비운 뒤 새로 담은 곡은 그 뒤에 남는다). */
let undoSaved = null, undoTimer = 0;
function clearQueue() {
  if (!st.queue.length) return;
  const saved = { queue: [...st.queue], played: new Set(st.played), qi: st.qi, curId: st.curId };
  const go = () => {
    el.qClear.disabled = false;
    st.queue = [];
    st.played = new Set();
    st.qi = -1;
    paint();
    showUndo(saved);
  };
  const rows = calm() ? [] : [...el.qList.querySelectorAll(".mp-q__item")].slice(0, 14);
  if (!rows.length) { go(); return; }
  el.qClear.disabled = true;
  let last = null;
  rows.forEach((li, k) => {
    last = li.animate([{ opacity: 1, transform: "none" }, { opacity: 0, transform: "translateY(10px)" }],
      { duration: 180, delay: k * 35, easing: "ease-in", fill: "forwards" });
  });
  last.onfinish = go;
}
function showUndo(saved) {
  undoSaved = saved;
  el.undoT.textContent = `재생목록 ${saved.queue.length}곡을 비웠습니다`;
  el.undo.hidden = false;
  restartCls(el.undo, "is-in");
  clearTimeout(undoTimer);
  undoTimer = setTimeout(hideUndo, 5000);
}
function hideUndo() {
  clearTimeout(undoTimer);
  undoSaved = null;
  if (el.undo) el.undo.hidden = true;
}
function undoClear() {
  const s = undoSaved;
  if (!s) return;
  hideUndo();
  st.queue = s.queue.concat(st.queue);
  st.played = new Set(s.played);
  if (st.qi >= 0) st.qi += s.queue.length;
  else if (st.curId === s.curId && s.qi >= 0) st.qi = s.qi;
  paint();
  pulseBadge();
  if (!calm()) [...el.qList.querySelectorAll(".mp-q__item")].slice(0, 14).forEach((li, k) =>
    li.animate([{ opacity: 0, transform: "translateY(8px)" }, { opacity: 1, transform: "none" }],
      { duration: 220, delay: k * 35, easing: "ease-out", fill: "backwards" }));
}

// ── 랜덤플리 오마카세 ────────────────────────────────────────────────
const OMA_LABEL = "랜덤플리 오마카세";
const OMA_COOLDOWN_MS = 5000;   // 연타 방지 — 칩을 고른 시점부터 5초 (BPM 오마카세와 같다)
const OMA_ROLL_MS = 620;        // 뒤섞임 연출 길이 (css .mp-oma.rolling 과 맞춘다)

function setOmaLabel(text) {
  el.omaT.replaceChildren(...[...text].map((c) => h("i", { text: c })));   // 글자마다 span — 뒤섞을 때 글자 단위로 움직인다
}
function omaPool(kind) { return kind === "all" ? st.songs : st.songs.filter((s) => s.kind === kind); }
function openOma() {
  if (st.omaBusy || !st.songs.length) return;
  for (const k of Object.keys(el.omaCount)) el.omaCount[k].textContent = `${omaPool(k).length}곡`;
  st.omaOpen = true;
  el.omaBub.hidden = false;
  el.oma.setAttribute("aria-expanded", "true");
}
function closeOma() {
  st.omaOpen = false;
  el.omaBub.hidden = true;
  el.oma.setAttribute("aria-expanded", "false");
}
function toggleOma() { st.omaOpen ? closeOma() : openOma(); }

/** 고른 종류의 모든 곡을 재생목록에 넣고(기존 재생목록은 덮어씀) 1번부터 재생한다. 재생은 클릭 직후(사용자 조작 안)에 시작해야 자동 재생이 막히지 않는다.
 *  (v4.8.1) 순서 = songs.js omakaseOrder — 7일 동안 안 들은 곡을 섞어 앞에 두고, 그 사이에 7일 이내에 들었던 곡을 50% 확률로 한 곡씩 끼운다. */
function omakase(kind) {
  const pool = omaPool(kind);
  closeOma();
  if (st.omaBusy || !pool.length) return;
  st.omaBusy = true;
  st.queue = omakaseOrder(pool.map((s) => s.id), readListened(), kstDate());
  st.played = new Set();
  st.qi = -1;
  playQueueAt(0);
  setTab("queue");   // 만든 재생목록을 바로 보여준다 (모바일 탭 — PC 는 두 칸이 같이 보여 영향 없음)
  pulseBadge();
  // 연출: 뒤섞임 → 5초 쿨타임 파이
  const calm = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  el.oma.disabled = true;
  el.oma.classList.remove("rolling");
  void el.oma.offsetWidth;                      // 연속 실행에서도 애니메이션이 처음부터
  el.oma.classList.add("rolling", "cooldown");
  let timer = 0;
  if (!calm) timer = setInterval(() => setOmaLabel([...OMA_LABEL].sort(() => Math.random() - 0.5).join("")), 70);
  setTimeout(() => { clearInterval(timer); setOmaLabel(OMA_LABEL); el.oma.classList.remove("rolling"); }, OMA_ROLL_MS);
  setTimeout(() => { st.omaBusy = false; el.oma.classList.remove("cooldown"); paintControls(); }, OMA_COOLDOWN_MS);
}

// ── 화면 구성 ────────────────────────────────────────────────────────
function build() {
  if (built) return;
  built = true;

  el.titleEl = h("h2", { class: "mp-pop__title", id: "mp-title", text: "유메미타 플레이어" });
  el.closeBtn = h("button", { type: "button", class: "mp-x", text: "내리기 ▾", on: { click: closePlayer } });

  // 재생부
  el.slot = h("div", { class: "mp-slot" });   // 프레임이 이 자리 위에 겹쳐 놓인다
  el.sTitle = h("div", { class: "mp-song__title" });
  el.sMeta = h("div", { class: "mp-song__meta" });
  el.sKo = h("div", { class: "mp-song__ko" });
  el.cur = h("span", { class: "mp-mono", text: "0:00" });
  el.dur = h("span", { class: "mp-mono", text: "0:00" });
  el.fill = h("i");
  el.thumb = h("b", { class: "mp-track__th", "aria-hidden": "true" });                   // (마이크로 인터랙션) 손가락으로 끄는 동안만 보이는 손잡이
  el.trackTip = h("span", { class: "mp-track__tip mp-mono", "aria-hidden": "true" });     // 손가락 위로 따라오는 시간 말풍선
  el.track = h("div", { class: "mp-track", role: "slider", "aria-label": "재생 위치", tabindex: "0", on: { keydown: onTrackKey } }, el.fill, el.thumb, el.trackTip);
  el.bPlay = h("button", { type: "button", class: "mp-main", on: { click: togglePlay } });
  el.bShuffle = h("button", { type: "button", class: "mp-tog", "aria-label": "셔플 (이전·다음 버튼이 무작위 곡으로)", title: "셔플", on: { click: () => {
    st.shuffle = !st.shuffle; st.played = new Set(st.qi >= 0 ? [st.qi] : []); paintControls();
    sayCtl(el.bShuffle, st.shuffle ? "셔플 켜짐" : "셔플 꺼짐", st.shuffle ? "이전 · 다음이 무작위 곡으로" : "재생목록 순서대로");
    if (!calm()) restartCls(el.bShuffle, "is-bop");
  } } }, icon("shuffle"));
  el.bRepeat = h("button", { type: "button", class: "mp-tog", on: { click: () => {
    st.repeat = st.repeat === "off" ? "one" : st.repeat === "one" ? "all" : "off"; paintControls();
    const next = st.repeat === "off" ? "one" : st.repeat === "one" ? "all" : "off";
    sayCtl(el.bRepeat, RPT_LABEL[st.repeat], `다시 누르면 ${RPT_LABEL[next]}`);
    if (!calm()) restartCls(el.bRepeat.querySelector("svg"), "is-spin");
  } } }, icon("repeat", "mp-ico mp-ico--rpt"));
  el.ctlTip = h("div", { class: "mp-ctltip", role: "status" });   // (마이크로 인터랙션) 반복 · 셔플 상태 말풍선
  // 랜덤플리 오마카세 — 버튼 + 말풍선(전체/오리지널/커버)
  el.omaT = h("span", { class: "mp-oma__t" });
  el.oma = h("button", { type: "button", class: "mp-oma", "aria-haspopup": "dialog", "aria-expanded": "false", on: { click: toggleOma } }, h("span", { class: "mp-oma__e", "aria-hidden": "true", text: "🎁" }), el.omaT);
  setOmaLabel(OMA_LABEL);
  el.omaCount = {};
  el.omaBub = h("div", { class: "mp-bubble", role: "dialog", "aria-label": "랜덤플리 종류", hidden: true },
    h("div", { class: "mp-bubble__h", text: "어떤 곡으로 섞을까요?" }),
    h("div", { class: "mp-bubble__chips" }, ...[["all", "전체"], ["original", "오리지널"], ["cover", "커버"]].map(([k, l]) => {
      el.omaCount[k] = h("small");
      return h("button", { type: "button", class: "mp-chip", on: { click: () => omakase(k) } }, l, el.omaCount[k]);
    })),
  );
  el.omaWrap = h("div", { class: "mp-oma-wrap" }, el.omaBub, el.oma);
  el.err = h("div", { class: "mp-err", role: "status", hidden: true });
  el.skipIco = h("span", { class: "mp-skip__ico", "aria-hidden": "true", text: "!" });   // (v4.8.3) 재생 불가 안내 — 자리는 placeSkip 이 정한다
  el.skipT = h("span", { class: "mp-skip__t" });
  el.skip = h("div", { class: "mp-skip", role: "status", hidden: true }, el.skipIco, el.skipT, h("i", { class: "mp-skip__bar", "aria-hidden": "true" }));
  // (v4.8.4) [음원 | MV] 스위치 — 버튼 하나. 어디를 눌러도 반대 모드로 간다(setMedia). 손잡이(i.mp-media__thumb)가 옮겨 가며 두 라벨을 가린다
  el.mThumb = h("i", { class: "mp-media__thumb", "aria-hidden": "true" });
  el.mLabA = h("span", { class: "mp-media__lab mp-media__lab--a" }, icon("note"), h("span", { text: "음원" }));
  el.mLabM = h("span", { class: "mp-media__lab mp-media__lab--m" }, icon("film"), h("span", { text: "MV" }));
  el.media = h("button", { type: "button", role: "switch", class: "mp-media", "aria-label": "MV 로 보기", on: { click: () => setMedia(st.media === "mv" ? "audio" : "mv") } }, el.mThumb, el.mLabA, el.mLabM);
  el.mvTipMain = h("span");
  el.mvTipSub = h("small", { hidden: true });
  el.mvTip = h("div", { class: "mp-mvtip", role: "status", hidden: true }, el.mvTipMain, el.mvTipSub);   // 전환 안내 · MV 첫 안내 (showMediaTip)
  el.qCount = h("span", { class: "mp-q__count" });
  el.qClear = h("button", { type: "button", class: "mp-link", text: "비우기", on: { click: clearQueue } });
  el.qList = h("ol", { class: "mp-q__list" });
  for (const ev of ["wheel", "touchmove"]) el.qList.addEventListener(ev, () => { qUserAt = Date.now(); }, { passive: true });   // 사용자가 목록을 직접 훑는 중
  el.undoT = h("span");
  el.undo = h("div", { class: "mp-undo", role: "status", hidden: true },   // (마이크로 인터랙션) 「비우기」 뒤 5초 되돌리기
    el.undoT, h("button", { type: "button", class: "mp-undo__b", text: "되돌리기", on: { click: undoClear } }), h("i", { class: "mp-undo__bar" }));
  el.qBox = h("section", { class: "mp-q", "aria-label": "재생목록" },
    h("div", { class: "mp-q__head" }, h("strong", { text: "재생목록" }), el.qCount, el.qClear),
    el.qList,
    el.undo,
  );
  el.stage = h("section", { class: "mp-stage" },
    el.slot,
    h("div", { class: "mp-song" }, h("div", { class: "mp-song__txt" }, el.sTitle, el.sMeta, el.sKo), el.media, el.mvTip),
    h("div", { class: "mp-bar" }, el.cur, el.track, el.dur),
    h("div", { class: "mp-ctl" }, el.ctlTip, h("div", { class: "mp-grp" }, el.bShuffle, iconBtn("prev", "이전 곡", "mp-btn", () => go(-1)), el.bPlay, iconBtn("next", "다음 곡", "mp-btn", () => go(1)), el.bRepeat), el.omaWrap),
    el.err,
  );

  // 목록부
  el.q = h("input", { id: "mp-q", type: "search", placeholder: "곡명 · 독음(가나·한글) 검색", autocomplete: "off", "aria-label": "곡 검색", on: { input: (e) => { st.query = e.target.value; paintList(); } } });
  el.kinds = h("div", { class: "mp-chips", role: "group", "aria-label": "종류" });
  el.sort = h("div", { class: "mp-sort", role: "group", "aria-label": "정렬" });
  el.list = h("ul", { class: "mp-list" });
  el.count = h("div", { class: "mp-count" });
  el.lib = h("section", { class: "mp-lib", id: "mp-panel-songs" },
    h("div", { class: "mp-tools" },
      h("label", { class: "mp-search" }, icon("search", "mp-ico mp-ico--s"), el.q),
      h("div", { class: "mp-row2" }, el.kinds, el.sort),
    ),
    el.list,
    el.count,
  );

  // 탭 — 곡 목록 | 재생목록(배지 = 재생목록 곡 수). 모바일 · PC 공통(v4.2.2). 재생부(stage)는 영상 · 곡 정보 · 컨트롤만 갖고, 목록 둘은 오른쪽(PC) / 아래(모바일) 한 칸을 탭으로 나눠 쓴다.
  el.badge = h("span", { class: "mp-badge", text: "0" });
  el.tabSongs = h("button", { type: "button", class: "mp-tab", role: "tab", id: "mp-tab-songs", "aria-controls": "mp-panel-songs", on: { click: () => setTab("songs"), keydown: onTabKey } }, "곡 목록");
  el.tabQueue = h("button", { type: "button", class: "mp-tab", role: "tab", id: "mp-tab-queue", "aria-controls": "mp-panel-queue", on: { click: () => setTab("queue"), keydown: onTabKey } }, "재생목록 ", el.badge);
  el.tabBar = h("div", { class: "mp-tabs", role: "tablist", "aria-label": "곡 목록 또는 재생목록" }, el.tabSongs, el.tabQueue);
  el.qPanel = h("div", { class: "mp-qpanel", id: "mp-panel-queue", hidden: true }, el.qBox);
  el.panels = h("div", { class: "mp-panels" }, el.lib, el.qPanel);
  el.side = h("div", { class: "mp-side" }, el.tabBar, el.panels);

  el.head = h("div", { class: "mp-pop__head" }, h("i", { class: "mp-pop__grab", "aria-hidden": "true" }), el.titleEl, el.closeBtn);   // 모바일: 머리줄을 끌어 내린다
  el.pop = h("div", { class: "mp-pop", role: "dialog", "aria-modal": "true", "aria-labelledby": "mp-title" },
    el.head,
    el.body = h("div", { class: "mp-pop__body" }, el.stage, el.side),
  );
  el.scrim = h("div", { class: "mp-scrim", id: "player-pop", hidden: true, on: { mousedown: (e) => { if (e.target === el.scrim) closePlayer(); } } }, el.pop);

  // 플로팅 프레임 — 한 번 만들고 옮기지 않는다
  el.ytTarget = h("div");
  el.gName = h("span", { class: "mp-grip__name" });
  el.gPos = h("span", { class: "mp-grip__pos" });   // 재생목록에서 고른 곡이면 「(n/m)」
  el.gTitle = h("span", { class: "mp-grip__title" }, el.gName, el.gPos);
  el.grip = h("div", { class: "mp-grip", title: "끌어서 이동 · 더블클릭하면 팝업으로" },
    h("span", { class: "mp-grip__dots", "aria-hidden": "true", text: "⠿" }),
    el.gTitle,
    el.gBtns = h("span", { class: "mp-grip__btns" },
      iconBtn("prev", "이전 곡", "mp-gbtn", () => go(-1)),
      iconBtn("next", "다음 곡", "mp-gbtn", () => go(1)),
      h("button", { type: "button", class: "mp-gbtn", "aria-label": "팝업 열기", title: "팝업 열기", text: "▴", on: { click: () => { markGripTipSeen(); hideGripTip(); openPlayer(); } } }),
      h("button", { type: "button", class: "mp-gbtn", "aria-label": "플레이어 닫기 (정지)", title: "닫기 (정지)", text: "✕", on: { click: dismissFrame } }),
    ),
  );
  el.ytBox = h("div", { class: "mp-yt" }, el.ytTarget);
  el.fmain = h("div", { class: "mp-frame__main" }, el.grip, el.ytBox);   // 본체 — 폭은 CSS(플로팅일 때만 고정)
  el.tabL = tuckTab("l");   // 오른쪽에 넣었을 때 남는 탭 (프레임 왼쪽 끝)
  el.tabR = tuckTab("r");   // 왼쪽에 넣었을 때 남는 탭 (프레임 오른쪽 끝)
  el.frame = h("div", { class: "mp-frame", id: "player-frame", hidden: true }, el.tabL, el.fmain, el.tabR);
  // 가장자리 빛 띠 — 넣는 동안 화면 끝에 뜬다 (프레임 밖, body 에 붙는다)
  el.edge = h("div", { class: "mp-edge", "aria-hidden": "true" },
    h("div", { class: "mp-edge__glow" }), h("div", { class: "mp-edge__lip" }),
    h("div", { class: "mp-edge__chev" }, ...[0, 1, 2].map(() => chevSvg("", "0 0 12 14", "M8 2 3 7l5 5", "2.2"))));

  // (마이크로 인터랙션) PC 플로팅 손잡이 더블클릭 안내 — 처음 한 번만(GRIP_TIP_KEY)
  el.coach = h("div", { class: "mp-coach", role: "status", hidden: true },
    h("span", { class: "mp-coach__tap", "aria-hidden": "true" }, h("i"), h("i")), "더블클릭하면 아래 플레이어로 이동합니다");

  document.body.append(el.scrim, el.frame, el.edge, el.coach);

  initGripDrag();
  initTrackDrag();
  initQueueSwipe();
  wireSheetDrag({   // (마이크로 인터랙션) 모바일 시트 — 머리줄을 아래로 끌어 내린다(재생은 계속). PC 도크는 해당 없음
    sheet: el.pop,
    handles: [el.head],
    isOpen: () => st.popOpen && !st.dock && isPhone(),
    close: closePlayer,
    setScrim: (v) => {
      el.scrim.style.transition = v == null ? "" : "none";
      el.scrim.style.background = v == null ? "" : `rgba(0, 0, 0, ${(0.6 * v).toFixed(3)})`;
    },
    onMove: () => followFrame(SHEET_MS + 200),   // 프레임이 재생부 자리를 따라온다(튕겨 돌아가는 동안 포함)
  });
  el.scrim.addEventListener("keydown", trapFocus);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && st.omaOpen) { closeOma(); return; } if (e.key === "Escape" && st.popOpen) closePlayer(); });
  document.addEventListener("click", (e) => { if (st.omaOpen && !el.omaWrap.contains(e.target)) closeOma(); });
  window.addEventListener("resize", () => { clampFloat(); layoutFrame(); });
  el.body.addEventListener("scroll", () => { if (st.popOpen) layoutFrame(); }, { passive: true });   // 모바일 모달은 본문이 스크롤된다 — 프레임이 재생부 자리를 따라가게
  if (typeof ResizeObserver === "function") new ResizeObserver(layoutFrame).observe(el.slot);
  paintTabs();
}

/** 탭 상태 반영 — 선택된 탭의 패널만 보인다(모바일 · PC 공통). */
function paintTabs() {
  if (!built) return;
  const songs = st.tab !== "queue";
  el.tabSongs.setAttribute("aria-selected", String(songs));
  el.tabQueue.setAttribute("aria-selected", String(!songs));
  el.tabSongs.tabIndex = songs ? 0 : -1;
  el.tabQueue.tabIndex = songs ? -1 : 0;
  el.lib.hidden = !songs;
  el.qPanel.hidden = songs;
  for (const [p, t] of [[el.lib, el.tabSongs], [el.qPanel, el.tabQueue]]) {
    p.setAttribute("role", "tabpanel");
    p.setAttribute("aria-labelledby", t.id);
  }
}

function setTab(t) {
  st.tab = t;
  paintTabs();
  if (t === "queue") { qFocusKey = null; focusQueueCur(); }   // 모바일: 재생목록 탭을 열면 지금 곡 위치로
}

/** 탭 바 키보드 — 좌우 화살표로 옮기며 포커스도 따라간다(WAI-ARIA 탭 패턴). */
function onTabKey(e) {
  if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
  e.preventDefault();
  const t = st.tab === "songs" ? "queue" : "songs";
  setTab(t);
  (t === "songs" ? el.tabSongs : el.tabQueue).focus();
}

/** 재생목록에 곡이 쌓이면 배지를 한 번 맥박 — 클래스를 뗐다 다시 붙여 같은 애니메이션을 다시 돌린다. */
function pulseBadge() {
  if (!built) return;
  el.badge.classList.remove("pulse");
  void el.badge.offsetWidth;
  el.badge.classList.add("pulse");
}

// ── 그리기 ───────────────────────────────────────────────────────────
function paint() {
  paintStage();
  paintControls();
  paintQueue();
  paintList();
  paintGrip();
  layoutFrame();
}

function paintStage() {
  const s = curSong();
  el.sTitle.replaceChildren(s ? s.title : "곡을 고르세요", ...(s && isNewSong(s) ? [" ", newPill()] : []));
  el.sMeta.replaceChildren();
  el.sKo.textContent = s ? displayKo(s) : "";
  if (s) {
    el.sMeta.append(...memberNodes(s), `${KIND_LABEL[s.kind] || s.kind} · ${s.date}`);
  }
  el.err.hidden = !st.error;
  el.err.replaceChildren();
  if (st.error) {
    const url = `https://youtu.be/${st.error.id || st.vid}`;
    el.err.append(
      st.error.code === "api" ? "YouTube 플레이어를 불러오지 못했습니다. " : "이 영상은 임베드 재생이 제한되어 있을 수 있습니다. ",
      h("a", { href: url, target: "_blank", rel: "noopener noreferrer", text: "YouTube 에서 보기" }),
    );
  }
  paintProgress();
}

function paintProgress() {
  const r = st.dur > 0 ? Math.min(1, st.pos / st.dur) : 0;
  el.fill.style.width = `${r * 100}%`;
  el.cur.textContent = fmt(st.pos);
  el.dur.textContent = fmt(st.dur);
  el.track.setAttribute("aria-valuenow", String(Math.floor(st.pos)));
  el.track.setAttribute("aria-valuemax", String(Math.floor(st.dur)));
}

function paintControls() {
  el.frame.classList.toggle("is-playing", st.playing);   // 손잡이 탭의 재생 막대 애니메이션 (playerpop.css)
  el.bPlay.replaceChildren(icon(st.playing ? "pause" : "play"));
  el.bPlay.setAttribute("aria-label", st.playing ? "일시정지" : "재생");
  el.oma.disabled = st.omaBusy || !st.songs.length;
  el.bShuffle.setAttribute("aria-pressed", String(st.shuffle));
  el.media.setAttribute("aria-checked", String(st.media === "mv"));   // (v4.8.4) [음원 | MV] 스위치 — MV 면 손잡이가 오른쪽 칸으로
  el.media.classList.toggle("is-mv", st.media === "mv");
  const rp = st.repeat;
  el.bRepeat.setAttribute("aria-pressed", String(rp !== "off"));
  const lab = rp === "off" ? "반복 (꺼짐) — 누르면 한 곡 반복" : rp === "one" ? "한 곡 반복 (켜짐) — 누르면 전체 반복" : "전체 반복 (켜짐) — 누르면 끄기";
  el.bRepeat.setAttribute("aria-label", lab);
  el.bRepeat.title = lab;
  const t = el.bRepeat.querySelector(".mp-rpt");
  if (t) t.textContent = rp === "one" ? "1" : rp === "all" ? "A" : "";
}

let qUserAt = 0;       // 사용자가 재생목록을 직접 스크롤한 마지막 시각 — 이후 4초는 자동 포커스를 건너뛴다
let qFocusKey = null;  // 마지막으로 포커스한 「곡 + 위치」 — 곡이 바뀔 때만 움직이게 한다

/** 재생 중인 곡 줄이 목록 보이는 영역의 위 12%~아래 88% 밖이면 위 1/3 지점으로 부드럽게 스크롤한다(목록 안에서만). */
function focusQueueCur() {
  if (!built || st.qi < 0 || el.qPanel.hidden) return;
  const key = st.curId + ":" + st.qi;
  if (key === qFocusKey) return;
  if (Date.now() - qUserAt < 4000) return;
  const cur = el.qList.children[st.qi];
  const vh = el.qList.clientHeight;
  if (!cur || !vh) return;
  qFocusKey = key;
  const lr = el.qList.getBoundingClientRect(), cr = cur.getBoundingClientRect();   // 화면에 보이는 위치 기준
  const rel = cr.top - lr.top - el.qList.clientTop;
  if (rel >= vh * 0.12 && rel + cr.height <= vh * 0.88) return;
  const to = Math.max(0, Math.min(el.qList.scrollHeight - vh, rel + el.qList.scrollTop - vh / 3 + cr.height / 2));
  el.qList.scrollTo({ top: to, behavior: calm() ? "auto" : "smooth" });
}

function paintQueue() {
  if (!built) return;
  el.badge.textContent = String(st.queue.length);
  el.qCount.textContent = st.queue.length ? `${st.queue.length}곡` : "";
  el.qClear.hidden = !st.queue.length;
  if (!st.queue.length) {
    el.qList.replaceChildren(h("li", { class: "mp-q__empty", text: "오른쪽 목록에서 곡을 누르면 여기에 쌓입니다. 재생은 1번부터 순서대로 이어집니다." }));
    qFocusKey = null;
    return;
  }
  el.qList.replaceChildren(...st.queue.map((id, i) => {
    const s = st.songs.find((x) => x.id === id);
    if (!s) return null;
    const cur = i === st.qi;   // 같은 곡이 여러 번 있어도 위치로 구분
    // (마이크로 인터랙션) 밑판(.mp-q__under 「빼기」) 위에 윗판(.mp-q__fg) — 모바일에서 윗판을 왼쪽으로 밀면 밑판이 드러나며 빠진다(initQueueSwipe)
    return h("li", { class: "mp-q__item" + (cur ? " is-cur" : ""), "data-i": String(i) },
      h("span", { class: "mp-q__under", "aria-hidden": "true" }, trashIcon(), "빼기"),
      h("div", { class: "mp-q__fg" },
        h("button", { type: "button", class: "mp-q__main", "aria-current": cur ? "true" : null, on: { click: () => { qUserAt = 0; playQueueAt(i); } } },
          h("span", { class: "mp-mono mp-q__n", text: cur && st.playing ? "▶" : String(i + 1) }),
          h("span", { class: "mp-q__title", text: s.title })),
        h("button", { type: "button", class: "mp-q__x", "aria-label": `${s.title} 재생목록에서 빼기`, title: "빼기", text: "✕", on: { click: (e) => removeAnimated(i, e.currentTarget.closest("li")) } })));
  }));
  focusQueueCur();
}

function paintGrip() {
  const s = curSong();
  el.gName.textContent = s ? s.title : "";
  el.gPos.textContent = s && st.qi >= 0 ? ` (${st.qi + 1}/${st.queue.length})` : "";
}

function paintTools() {
  el.kinds.replaceChildren(...[["all", "전체"], ["original", "오리지널"], ["cover", "커버"], ["new", "신곡"]].map(([k, l]) =>
    h("button", { type: "button", "aria-pressed": String(st.kind === k), text: l, on: { click: () => { st.kind = k; paintTools(); paintList(); } } })));
  const arrow = st.dir === "asc" ? " ↑" : " ↓";
  el.sort.replaceChildren(h("span", { text: "정렬" }), ...[["name", "이름순"], ["date", "날짜순"]].map(([k, l]) =>
    h("button", {
      type: "button", "aria-pressed": String(st.sortBy === k), text: l + (st.sortBy === k ? arrow : ""),
      on: { click: () => {
        if (st.sortBy === k) st.dir = st.dir === "asc" ? "desc" : "asc";
        else { st.sortBy = k; st.dir = k === "date" ? "desc" : "asc"; }
        paintTools(); paintList();
      } },
    })));
}

/** text 를 query 일치 구간만 <mark> 로 감싸 노드 배열로 돌려준다. */
function highlight(text, query) {
  const r = matchRange(text, query);
  if (!r) return [text];
  return [text.slice(0, r[0]), h("mark", { text: text.slice(r[0], r[1]) }), text.slice(r[1])];
}

function paintList() {
  if (!built) return;
  if (st.loadError) {
    el.list.replaceChildren(h("li", { class: "mp-empty" }, "곡 목록을 불러오지 못했습니다. ", h("button", { type: "button", class: "mp-link", text: "다시 시도", on: { click: retryLoad } })));
    el.count.textContent = "";
    return;
  }
  const list = view();
  const q = st.query.trim();
  if (!list.length) {
    el.list.replaceChildren(h("li", { class: "mp-empty", text: st.songs.length ? "검색 결과가 없습니다. 철자를 바꾸거나 종류 필터를 확인해 보세요." : "곡 목록을 불러오는 중…" }));
  } else {
    el.list.replaceChildren(...list.map((s, i) => songRow(s, i, q)));
  }
  el.count.textContent = st.songs.length ? `${list.length} / ${st.songs.length}곡 · 독음 ${st.songs.filter((s) => s.reading).length}곡 입력됨` : "";
}

/** 발매일 +14일 안의 곡 표시 — 곡 줄 · 재생 중 곡 제목 옆. */
function newPill() {
  return h("span", { class: "mp-new", text: "NEW" });
}

function songRow(s, i, q) {
  const cur = s.id === st.curId;
  const ms = memberList(s);
  const sub = h("span", { class: "mp-item__sub" },
    ...ms.map((m) => h("span", { class: "mp-dot", style: `--mc:${m.color}` })),
    ms.length ? h("span", { text: ms.map((m) => m.name).join(", ") }) : null,
    h("span", { text: KIND_LABEL[s.kind] || s.kind }),
    h("span", { class: "mp-mono", text: s.date }),
    hasMv(s) ? h("span", { class: "mp-mvtag", text: "MV" }) : null,   // (v4.8.3) MV 가 있는 곡 표시 — 재생목록 줄에는 안 붙인다
  );
  const qns = st.queue.flatMap((x, k) => (x === s.id ? [k + 1] : []));   // 재생목록에서의 번호들(같은 곡이 여러 번일 수 있다)
  if (qns.length) {   // 글자 수 상한: 1번이면 「N번」, 여럿이면 「N번 외 K」(N = 가장 앞 번호). 전체 번호는 툴팁 · 접근성 이름으로만
    const all = `재생목록 ${qns.join("·")}번`;
    const label = qns.length === 1 ? `재생목록 ${qns[0]}번` : `재생목록 ${qns[0]}번 외 ${qns.length - 1}`;
    sub.append(h("span", { class: "mp-q-badge", title: all, role: "img", "aria-label": all, text: label }));
  }
  const main = h("button", { type: "button", class: "mp-item__main", "aria-current": cur ? "true" : null, title: "재생목록에 추가", on: { click: () => addToQueue(s.id) } },
    h("span", { class: "mp-item__n mp-mono", text: cur && st.playing ? "▶" : String(i + 1) }),
    h("span", { class: "mp-item__body" }, h("span", { class: "mp-item__title" }, ...highlight(s.title, q), ...(isNewSong(s) ? [" ", newPill()] : [])), sub,
      displayKo(s) ? h("span", { class: "mp-item__ko" }, ...highlight(displayKo(s), q)) : null),
  );
  return h("li", { class: "mp-item" + (cur ? " is-cur" : "") }, main);
}

// ── 프레임 배치 ──────────────────────────────────────────────────────
/** 모달 본문이 스크롤될 때 재생부(프레임)가 본문 영역 밖으로 삐져나가 헤더 · 목록을 덮지 않게 자른다. */
function bodyClip(r) {
  const b = el.body.getBoundingClientRect();
  const top = Math.min(r.height, Math.max(0, b.top - r.top));
  const bottom = Math.min(r.height, Math.max(0, r.bottom - b.bottom));
  return top || bottom ? `inset(${top}px 0 ${bottom}px 0)` : "none";
}
let slotCss = "";   // 마지막으로 slot 위에 준 스타일 — 같으면 다시 쓰지 않는다(dockSync 가 매 프레임 부른다)
function layoutFrame() {
  if (!built) return;
  const f = el.frame;
  // slot 위에 겹치는 때: 모달 팝업이 열려 있거나, PC 하단 도크의 재생부가 화면에 보일 때. 도크가 화면 밖이면 재생 중인 프레임은 플로팅으로 남는다.
  const inSlot = st.dock ? st.slotVisible : (st.popOpen || st.closing);
  const show = inSlot || st.started;
  f.hidden = !show;
  if (!show) return;
  if (inSlot) {
    hideGripTip();   // (마이크로 인터랙션) 프레임이 재생부로 들어가면 손잡이 안내는 닫는다
    // 재생부 자리(slot) 위에 겹친다. 손잡이 줄은 숨김. 도크는 페이지와 같이 스크롤되도록 문서 좌표(absolute)로 둔다.
    const r = el.slot.getBoundingClientRect();
    f.classList.remove("is-float");
    f.classList.toggle("is-dock", !!st.dock);
    const css = st.dock
      ? `position:absolute;left:${r.left + scrollX}px;top:${r.top + scrollY}px;width:${r.width}px;height:${r.height}px;right:auto;bottom:auto`
      : `left:${r.left}px;top:${r.top}px;width:${r.width}px;height:${r.height}px;right:auto;bottom:auto;clip-path:${bodyClip(r)}`;
    if (css !== slotCss) { f.style.cssText = css; slotCss = css; }
  } else {
    slotCss = "";
    f.classList.remove("is-dock");
    f.classList.add("is-float");
    // 넣은 상태면 가장자리 밖 자리(tuckedLeft). cssText 는 transform 도 지운다 — 미는 중 transform 은 호출한 쪽이 다시 준다
    f.style.cssText = st.fpos ? `left:${st.tuck ? tuckedLeft(st.tuck) : st.fpos.x}px;top:${st.fpos.y}px;right:auto;bottom:auto` : "";
  }
  placeSkip();   // (v4.8.3) 재생 불가 안내도 프레임을 따라간다
}

// ── PC 하단 도크 ─────────────────────────────────────────────────────
// PC 에서는 팝업을 모달로 띄우지 않고 메인 화면 맨 아래(#player-dock)에 붙여 둔다. 모바일은 기존 모달 그대로.
let dockRaf = 0;
let slotIO = null;
function dockSync() {   // 도크의 재생부가 보이는 동안 레이아웃이 밀려도(보드 재렌더 등) 프레임이 자리를 따라가게 한다
  dockRaf = 0;
  if (!st.dock || !st.slotVisible) return;
  layoutFrame();
  dockRaf = requestAnimationFrame(dockSync);
}
async function prepareContent() {
  paintTools();
  paintList();
  if (!st.songs.length) {
    await loadSongs();
    paintTools();
  }
  // 처음 열면 가장 최근 곡의 첫 화면만 불러 둔다 — 재생은 사용자가 누를 때 시작
  if (!st.curId && st.songs.length) selectSong(viewSongs(st.songs, { sortBy: "date", dir: "desc" })[0].id, false);
  else paint();
}

/** PC: 팝업 본체를 container 안으로 옮겨 상시 표시한다. 여러 번 불러도 안전. */
export async function mountDock(container) {
  build();
  if (st.dock === container) return;
  if (st.popOpen) closePlayer();
  finishClose();
  clearTuck();   // PC 도크: 넣은 상태는 풀린다
  st.dock = container;
  container.append(el.pop);
  el.pop.classList.add("mp-pop--dock");
  el.pop.setAttribute("role", "region");
  el.pop.removeAttribute("aria-modal");
  if (typeof IntersectionObserver === "function") {
    slotIO = new IntersectionObserver(([e]) => {
      st.slotVisible = e.isIntersecting;
      layoutFrame();
      if (st.slotVisible && !dockRaf) dockRaf = requestAnimationFrame(dockSync);
    });
    slotIO.observe(el.slot);
  } else {
    st.slotVisible = true;
    dockRaf = requestAnimationFrame(dockSync);
  }
  layoutFrame();
  await prepareContent();
}

/** 모바일로 넘어가면 팝업 본체를 모달 배경으로 되돌린다. */
export function unmountDock() {
  if (!built || !st.dock) return;
  if (slotIO) { slotIO.disconnect(); slotIO = null; }
  st.dock = null;
  st.slotVisible = false;
  el.scrim.append(el.pop);
  el.pop.classList.remove("mp-pop--dock");
  el.pop.setAttribute("role", "dialog");
  el.pop.setAttribute("aria-modal", "true");
  layoutFrame();
}

function clampFloat() {
  if (!st.fpos || !built || st.popOpen) return;
  const w = floatW(), hh = el.frame.offsetHeight;
  if (st.tuck && !tuckable()) clearTuck();   // 넓어져서 가장자리 넣기가 없어졌다 — 넣은 상태만 풀고(애니메이션 없이)
  st.fpos = {
    x: st.tuck ? st.fpos.x : clamp(st.fpos.x, 0, Math.max(0, innerWidth - w)),   // 넣은 상태의 x 는 layoutFrame 이 innerWidth 로 다시 계산
    y: clamp(st.fpos.y, 0, Math.max(0, innerHeight - hh)),
  };
}

// ── 손잡이: 끌기 · 더블클릭 · (v4.7.6) 모바일 가장자리 넣기 ──────────
let animTimer = 0;   // 전환 클래스(is-tuck-anim · is-spring)를 떼는 타이머
let gulpTimer = 0;   // 빛 띠 gulp 클래스를 떼는 타이머
let pull = null;     // 넣은 상태에서 손잡이 탭 · 조각을 끄는 중 — {id, sx, sy, y0, kind, d}
const visibleTab = () => (st.tuck === "l" ? el.tabR : el.tabL);   // 넣었을 때 화면에 남는 탭

/** 전환 클래스를 붙이고 600ms 뒤 뗀다. null 이면 떼기만 — 다음 끌기 · 팝업 따라가기 때 지연이 생기지 않게. */
function animFrame(cls) {
  clearTimeout(animTimer);
  el.frame.classList.remove("is-tuck-anim", "is-spring");
  if (!cls) return;
  el.frame.classList.add(cls);
  void el.frame.offsetWidth;   // 클래스를 붙인 뒤 한 번 굽어야 이어지는 위치 변화가 전환된다
  animTimer = setTimeout(() => el.frame.classList.remove(cls), 600);
}

/** 넣은 상태 표시를 모두 지운다(✕ · 팝업 · PC 도크 · 폭 변경). 위치는 호출한 쪽이 정한다. */
function clearTuck() {
  st.tuck = null;
  el.frame.classList.remove("is-tucked-l", "is-tucked-r");
  for (const t of [el.tabL, el.tabR]) { t.tabIndex = -1; t.classList.remove("is-ready"); }
  el.gBtns.inert = false;
}

// 가장자리 빛 띠 — 위치 · 높이는 JS 가 (손잡이 줄 위 26px · 프레임 높이 + 52px), 색 · 모양은 CSS
function bumpEdge() {
  el.edge.classList.remove("is-bump"); void el.edge.offsetWidth; el.edge.classList.add("is-bump");
}
function showEdge(side, p, armed) {
  const e = el.edge;
  e.classList.toggle("is-l", side === "l");
  e.classList.toggle("is-r", side === "r");
  e.style.top = (st.fpos.y - 26) + "px";
  e.style.height = (el.frame.offsetHeight + 52) + "px";
  e.style.setProperty("--p", p.toFixed(3));
  e.classList.add("is-on");
  e.classList.toggle("is-armed", armed);
}
function hideEdge() { el.edge.classList.remove("is-on", "is-armed"); }
/** 넣는 순간 빛 띠가 한 번 쑥 들어간다(560ms). */
function gulpEdge(side) {
  const e = el.edge;
  e.classList.remove("is-on", "is-armed", "is-gulp");
  e.classList.toggle("is-l", side === "l");
  e.classList.toggle("is-r", side === "r");
  void e.offsetWidth;
  e.classList.add("is-gulp");
  clearTimeout(gulpTimer);
  gulpTimer = setTimeout(() => e.classList.remove("is-gulp"), 560);
}

/** 가장자리로 넣는다 — side 쪽 끝에 영상 TUCK_VIS 만큼 + 손잡이 탭이 화면에 남는다. */
function tuckFrame(side) {
  st.tuck = side;
  el.frame.classList.remove("is-tucked-l", "is-tucked-r");
  el.frame.classList.add("is-tucked-" + side);
  el.gBtns.inert = true;   // 넣은 동안 손잡이 줄 버튼(이전 · 다음 · 팝업 · 닫기)은 안 눌린다 — 그 자리를 누르면 꺼내기(CSS pointer-events 와 같이)
  animFrame("is-tuck-anim");
  layoutFrame();   // cssText 가 transform 도 지운다 — 넣는 자리로 전환
  gulpEdge(side);
  vibrate(10);
  (side === "l" ? el.tabR : el.tabL).tabIndex = 0;   // 남는 탭만 키보드 포커스 대상
}
/** 꺼낸다. x = 꺼낸 뒤 프레임 left(없으면 가장자리 안쪽 INSET). 높이(st.fpos.y)는 그대로. */
function untuckFrame(x) {
  const side = st.tuck;
  if (!side) return;
  clearTuck();
  const w = floatW();
  const lo = TUCK_INSET, hi = innerWidth - w - TUCK_INSET;
  st.fpos = { x: x == null ? (side === "l" ? lo : hi) : clamp(x, lo, hi), y: st.fpos.y };
  animFrame("is-spring");
  layoutFrame();
}

/** 넣은 상태의 손잡이(탭 또는 보이는 손잡이 조각)를 누름. */
function pullStart(e) {
  if (e.button > 0 || !st.tuck) return;
  pull = { id: e.pointerId, sx: e.clientX, sy: e.clientY, y0: st.fpos.y, kind: null, d: 0 };
  animFrame(null);
  e.currentTarget.setPointerCapture(e.pointerId);
  e.preventDefault();
}
function pullMove(e) {
  if (!pull || e.pointerId !== pull.id || !st.tuck) return;
  const side = st.tuck;
  const dx = e.clientX - pull.sx, dy = e.clientY - pull.sy;
  const out = side === "l" ? dx : -dx;   // 화면 바깥(넣은 쪽 반대)으로 끈 거리 — 양수
  if (!pull.kind && Math.hypot(dx, dy) > 6) pull.kind = Math.abs(dy) > Math.abs(out) * 1.2 ? "v" : "pull";
  if (!pull.kind) return;
  st.fpos.y = clamp(pull.y0 + dy, 0, Math.max(0, innerHeight - el.frame.offsetHeight));
  layoutFrame();   // 높이만 옮기는 중 · 꺼내는 중 모두 여기서 자리를 잡는다
  if (pull.kind === "v") return;
  pull.d = out > 0 ? out : Math.max(out * 0.25, -8);   // 안쪽으로 끌면 살짝만 따라온다
  el.frame.style.transform = `translateX(${side === "l" ? pull.d : -pull.d}px)`;
  visibleTab().classList.toggle("is-ready", pull.d > TUCK_PULL);
}
function pullEnd(commit) {
  const p = pull, side = st.tuck;
  pull = null;
  if (!p || !side) return;
  el.tabL.classList.remove("is-ready");
  el.tabR.classList.remove("is-ready");
  if (!p.kind) { if (commit) untuckFrame(); else layoutFrame(); return; }   // 그냥 누름 = 꺼냄, 취소 = 그대로
  if (p.kind === "pull" && commit && p.d > TUCK_PULL) { untuckFrame(tuckedLeft(side) + (side === "l" ? p.d : -p.d)); return; }
  animFrame("is-spring");   // 덜 끌었거나 세로로 끌었으면 제자리로 튕겨 돌아간다
  layoutFrame();
}

function initGripDrag() {
  let drag = null;   // 떠 있는 프레임을 끄는 중 — {id, dx, dy, over, side, armed, touched}
  el.grip.addEventListener("pointerdown", (e) => {
    hideGripTip();
    if (e.target.closest("button") || e.button > 0) return;
    if (st.tuck) { pullStart(e); return; }   // 넣은 상태의 보이는 손잡이 조각 — 탭과 같이 끈다
    const r = el.frame.getBoundingClientRect();
    drag = { id: e.pointerId, dx: e.clientX - r.left, dy: e.clientY - r.top, over: 0, side: null, armed: false, touched: false };
    animFrame(null);
    el.grip.setPointerCapture(e.pointerId);
    e.preventDefault();
  });
  el.grip.addEventListener("pointermove", (e) => {
    if (pull) { pullMove(e); return; }
    if (!drag || e.pointerId !== drag.id) return;
    const w = floatW(), hh = el.frame.offsetHeight;
    const rawX = e.clientX - drag.dx;
    st.fpos = { x: clamp(rawX, 0, Math.max(0, innerWidth - w)), y: clamp(e.clientY - drag.dy, 0, Math.max(0, innerHeight - hh)) };
    layoutFrame();   // 먼저 — 아래에서 밀린 자리가 있으면 덮어쓴다
    if (!tuckable()) return;
    const maxX = innerWidth - w;
    let side = null, over = 0;   // over = 화면 끝을 넘어 더 민 거리
    if (rawX < 0) { side = "l"; over = -rawX; } else if (rawX > maxX) { side = "r"; over = rawX - maxX; }
    if (over > 0) {
      if (!drag.touched || drag.side !== side) { drag.touched = true; bumpEdge(); vibrate(6); }
      drag.side = side;
      drag.over = over;
      const p = Math.min(over / TUCK_ARM, 1);
      if (!drag.armed && over >= TUCK_ARM) { drag.armed = true; vibrate(14); }
      else if (drag.armed && over < TUCK_ARM * 0.8) drag.armed = false;   // 조금 물러나도 바로 풀리지 않게
      const push = TUCK_PUSH * (1 - Math.exp(-over / 70));   // 밀수록 덜 따라오는 저항
      el.frame.style.transformOrigin = side === "l" ? "left center" : "right center";
      el.frame.style.transform = `translateX(${side === "l" ? -push : push}px) scale(${1 - 0.035 * p})`;
      el.frame.classList.toggle("is-armed", drag.armed);
      showEdge(side, p, drag.armed);
    } else if (drag.touched) {
      drag.touched = false; drag.armed = false; drag.side = null; drag.over = 0;
      el.frame.classList.remove("is-armed");
      hideEdge();
    }
  });
  const end = (commit) => (e) => {
    if (pull) { if (e.pointerId === pull.id) pullEnd(commit); return; }
    if (!drag || e.pointerId !== drag.id) return;
    const d = drag;
    drag = null;
    el.frame.classList.remove("is-armed");
    if (commit && d.armed) { tuckFrame(d.side); return; }   // 다 찼을 때 놓으면 들어간다
    hideEdge();
    if (d.over > 0) animFrame("is-spring");   // 다 차기 전에 놓으면 끝자리로 튕겨 나온다
    layoutFrame();
  };
  el.grip.addEventListener("pointerup", end(true));
  el.grip.addEventListener("pointercancel", end(false));
  el.grip.addEventListener("dblclick", (e) => { if (!e.target.closest("button")) { markGripTipSeen(); hideGripTip(); openPlayer(); } });
  el.grip.addEventListener("pointerenter", (e) => { if (e.pointerType === "mouse") showGripTip(); });   // (마이크로 인터랙션) 처음 한 번만 안내
  // 넣은 상태의 남은 탭 — 누르기 · 바깥으로 끌기 = 꺼냄, 위아래 끌기 = 높이만
  for (const t of [el.tabL, el.tabR]) {
    t.addEventListener("pointerdown", pullStart);
    t.addEventListener("pointermove", pullMove);
    t.addEventListener("pointerup", (e) => { if (pull && e.pointerId === pull.id) pullEnd(true); });
    t.addEventListener("pointercancel", (e) => { if (pull && e.pointerId === pull.id) pullEnd(false); });
    t.addEventListener("click", (e) => { if (e.detail === 0 && st.tuck) untuckFrame(); });   // 키보드(Enter · Space)
  }
}

// ── (마이크로 인터랙션) 반복 · 셔플 상태 말풍선 ─────────────────────────
const RPT_LABEL = { off: "반복 꺼짐", one: "한 곡 반복", all: "전체 반복" };
let ctlTipTimer = 0;
/** 누른 버튼 위에 바뀐 상태(main)와 다음 동작(sub)을 1.8초 띄운다. */
function sayCtl(btn, main, sub) {
  const box = el.ctlTip.parentElement;
  el.ctlTip.replaceChildren(main, h("small", { text: sub }));
  const br = box.getBoundingClientRect(), r = btn.getBoundingClientRect(), w = el.ctlTip.offsetWidth;
  const cx = r.left + r.width / 2 - br.left;
  const left = clamp(cx - w / 2, 0, Math.max(0, br.width - w));
  el.ctlTip.style.left = `${left}px`;
  el.ctlTip.style.setProperty("--tail-x", `${clamp(cx - left, 10, w - 10)}px`);
  restartCls(el.ctlTip, "is-on");
  clearTimeout(ctlTipTimer);
  ctlTipTimer = setTimeout(() => el.ctlTip.classList.remove("is-on"), 1800);
}

// ── (마이크로 인터랙션) PC 플로팅 손잡이 더블클릭 안내 — 이 브라우저에서 처음 한 번만 ──────
// 손잡이에 처음 마우스를 올릴 때 띄우고, 띄운 순간 본 것으로 기록한다(localStorage). 안내를 보기 전에 더블클릭 · ▴ 로 이미 옮겨 봤어도 기록한다.
// 저장소를 못 쓰면(시크릿 창 · 차단) 이 페이지를 연 동안 한 번만. 4초 뒤 · 손잡이를 누르면 닫힌다.
let gripTipTimer = 0, gripTipShown = false;
function gripTipSeen() { try { return localStorage.getItem(GRIP_TIP_KEY) === "1"; } catch (e) { return false; } }
function markGripTipSeen() { gripTipShown = true; try { localStorage.setItem(GRIP_TIP_KEY, "1"); } catch (e) { /* 이 페이지를 연 동안만 */ } }
function showGripTip() {
  if (!st.dock || st.tuck || !el.frame.classList.contains("is-float") || gripTipShown || gripTipSeen()) return;
  markGripTipSeen();
  const r = el.grip.getBoundingClientRect();
  el.coach.hidden = false;
  const w = el.coach.offsetWidth, hh = el.coach.offsetHeight;
  const above = r.top - hh - 10 >= 8;
  el.coach.classList.toggle("is-below", !above);
  el.coach.style.left = `${clamp(r.left, 8, innerWidth - w - 8)}px`;
  el.coach.style.top = `${above ? r.top - hh - 10 : r.bottom + 10}px`;
  restartCls(el.coach, "is-on");
  clearTimeout(gripTipTimer);
  gripTipTimer = setTimeout(hideGripTip, 4000);
}
function hideGripTip() {
  clearTimeout(gripTipTimer);
  if (el.coach) { el.coach.classList.remove("is-on"); el.coach.hidden = true; }
}

// ── (마이크로 인터랙션) 모바일 재생목록 줄 밀어서 빼기 ──────────────────
// 줄을 왼쪽으로 밀면 밑판 「빼기」가 드러나고, 줄 폭의 35%를 넘으면 휴지통이 커지며 진동(10ms). 놓으면 빠지고, 덜 밀었으면 튕겨 돌아온다.
// 세로로 더 움직이면 목록 스크롤에 맡긴다(CSS touch-action: pan-y). 민 뒤의 click 은 곡 재생으로 치지 않는다. ✕ 버튼도 그대로 쓴다.
function trashIcon() {
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 16 16");
  svg.setAttribute("aria-hidden", "true");
  const p = document.createElementNS(NS, "path");
  p.setAttribute("d", "M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.6 8.5h5.8l.6-8.5");
  svg.appendChild(p);
  return svg;
}
function initQueueSwipe() {
  let d = null, suppress = false;
  el.qList.addEventListener("pointerdown", (e) => {
    const fg = e.target.closest(".mp-q__fg");
    if (!fg || !isPhone() || e.target.closest(".mp-q__x") || (e.pointerType === "mouse" && e.button !== 0)) return;
    d = { id: e.pointerId, x0: e.clientX, y0: e.clientY, fg, li: fg.parentElement, w: fg.offsetWidth || 1, drag: false, armed: false, dx: 0 };
  });
  el.qList.addEventListener("pointermove", (e) => {
    if (!d || e.pointerId !== d.id) return;
    const dx = e.clientX - d.x0, dy = e.clientY - d.y0;
    if (!d.drag) {
      if (Math.abs(dx) < 8 && Math.abs(dy) < 8) return;
      if (Math.abs(dy) >= Math.abs(dx)) { d = null; return; }
      d.drag = true;
      d.li.classList.add("is-swiping");
      try { d.fg.setPointerCapture(e.pointerId); } catch (_) { /* 무시 */ }
    }
    d.dx = dx;
    const lim = d.w * 0.6;
    const shown = dx >= 0 ? Math.min(14, dx * 0.2) : (-dx < lim ? dx : -(lim + (-dx - lim) * 0.3));
    d.fg.style.transform = `translateX(${shown.toFixed(1)}px)`;
    d.li.style.setProperty("--p", String(clamp(-dx / (d.w * 0.35), 0, 1)));
    const armed = -dx > d.w * 0.35;
    if (armed !== d.armed) { d.armed = armed; d.li.classList.toggle("is-armed", armed); vibrate(armed ? 10 : 5); }
  });
  const end = (commit) => (e) => {
    if (!d || e.pointerId !== d.id) return;
    const g = d;
    d = null;
    if (!g.drag) return;
    suppress = true;
    setTimeout(() => { suppress = false; }, 0);
    g.li.classList.remove("is-swiping");
    const i = Number(g.li.dataset.i);
    if (commit && g.armed) {
      if (calm()) { removeAnimated(i, null); return; }
      g.fg.animate([{ transform: g.fg.style.transform }, { transform: `translateX(${-g.w - 20}px)` }], { duration: 170, easing: "ease-in", fill: "forwards" })
        .onfinish = () => removeAnimated(i, g.li);
      return;
    }
    g.li.classList.remove("is-armed");
    g.li.style.setProperty("--p", "0");
    g.fg.style.transform = "";
  };
  el.qList.addEventListener("pointerup", end(true));
  el.qList.addEventListener("pointercancel", end(false));
  el.qList.addEventListener("click", (e) => { if (suppress) { e.preventDefault(); e.stopPropagation(); } }, true);
}

// ── 진행 바 ──────────────────────────────────────────────────────────
function seekTo(ratio) {
  if (!yt || !ytReady || !(st.dur > 0)) return;
  yt.seekTo(Math.min(Math.max(0, ratio), 1) * st.dur, true);
  st.pos = Math.min(Math.max(0, ratio), 1) * st.dur;
  paintProgress();
}
/** 타임바 끌기 — 끄는 동안은 화면(바 · 현재 시간)만 따라가고, 놓을 때 한 번만 해당 시간으로 이동한다. 단순 클릭도 같은 경로. */
let trackDrag = null;   // 끄는 중이면 {id, ratio}
const trackRatio = (e) => {
  const r = el.track.getBoundingClientRect();
  return r.width > 0 ? Math.min(Math.max(0, (e.clientX - r.left) / r.width), 1) : 0;
};
function previewDrag(ratio) {
  trackDrag.ratio = ratio;
  st.pos = ratio * st.dur;
  paintProgress();
  if (!trackDrag.touch) return;
  // (마이크로 인터랙션) 손가락으로 끄는 동안 — 손잡이를 키우고 손가락 위에 시간 말풍선. 1분 단위를 지날 때마다 짧은 진동
  const w = el.track.clientWidth;
  el.thumb.style.left = `${ratio * 100}%`;
  el.trackTip.textContent = fmt(st.pos);
  const tw = el.trackTip.offsetWidth;
  el.trackTip.style.left = `${clamp(ratio * w - tw / 2, -24, w - tw + 24)}px`;
  const m = Math.floor(st.pos / 60);
  if (trackDrag.min != null && m !== trackDrag.min) { vibrate(4); if (!calm()) restartCls(el.trackTip, "is-tick"); }
  trackDrag.min = m;
}
function initTrackDrag() {
  el.track.addEventListener("pointerdown", (e) => {
    if (e.button > 0 || !(st.dur > 0)) return;
    trackDrag = { id: e.pointerId, ratio: 0, touch: e.pointerType !== "mouse", min: null };
    el.track.setPointerCapture(e.pointerId);
    el.track.classList.add("is-drag");
    el.track.classList.toggle("is-touch", trackDrag.touch);
    previewDrag(trackRatio(e));
    e.preventDefault();
  });
  el.track.addEventListener("pointermove", (e) => {
    if (trackDrag && e.pointerId === trackDrag.id) previewDrag(trackRatio(e));
  });
  const end = (commit) => (e) => {
    if (!trackDrag || e.pointerId !== trackDrag.id) return;
    const ratio = trackDrag.ratio;
    trackDrag = null;
    el.track.classList.remove("is-drag", "is-touch");
    if (commit) seekTo(ratio);
    else paintProgress();   // 취소 — 다음 tick 이 실제 위치로 되돌린다
  };
  el.track.addEventListener("pointerup", end(true));
  el.track.addEventListener("pointercancel", end(false));
}
function onTrackKey(e) {
  if (!(st.dur > 0)) return;
  if (e.key === "ArrowRight") { e.preventDefault(); seekTo((st.pos + 5) / st.dur); }
  else if (e.key === "ArrowLeft") { e.preventDefault(); seekTo((st.pos - 5) / st.dur); }
}

// ── 열기 · 닫기 ──────────────────────────────────────────────────────
function trapFocus(e) {
  if (e.key !== "Tab") return;
  const f = [...el.pop.querySelectorAll("button, input, a[href]")].filter((n) => !n.disabled && n.offsetParent !== null);
  if (!f.length) return;
  const first = f[0], last = f[f.length - 1];
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
}

async function retryLoad() {
  loadPromise = null;
  await loadSongs();
  paintTools();
  paintList();
}

const SHEET_MS = 320;   // 모바일 바텀 시트 슬라이드 시간 — playerpop.css 의 transition 과 맞춘다
let closeTimer = 0;
let followRaf = 0;
let followUntil = 0;
/** 시트가 미끄러지는 동안 프레임이 재생부 자리를 매 프레임 따라가게 한다. */
function followFrame(ms) {
  followUntil = performance.now() + ms;
  if (followRaf) return;
  const step = () => {
    followRaf = 0;
    layoutFrame();
    if (performance.now() < followUntil) followRaf = requestAnimationFrame(step);
  };
  followRaf = requestAnimationFrame(step);
}
/** 닫는 애니메이션이 끝났을 때(또는 곧바로 다시 열거나 도크로 바뀔 때) 시트를 실제로 치운다. */
function finishClose() {
  clearTimeout(closeTimer);
  closeTimer = 0;
  if (!st.closing) return;
  st.closing = false;
  el.scrim.hidden = true;
  layoutFrame();
}

export async function openPlayer() {
  build();
  if (st.dock) { st.dock.scrollIntoView({ behavior: "smooth", block: "end" }); return; }   // PC: 플로팅 프레임의 ▴ · 더블클릭 = 하단 도크로 이동
  if (st.popOpen) return;
  clearTimeout(closeTimer);
  st.closing = false;
  lastFocus = document.activeElement;
  st.popOpen = true;
  el.scrim.hidden = false;
  void el.scrim.offsetWidth;                 // 시작 상태(아래쪽)를 먼저 확정해야 transition 이 돈다
  el.scrim.classList.add("is-open");         // 아래에서 위로 슬라이드 (모바일, css)
  document.documentElement.classList.add("mp-lock");
  layoutFrame();
  followFrame(SHEET_MS + 80);
  await prepareContent();
  requestAnimationFrame(() => { layoutFrame(); el.closeBtn.focus({ preventScroll: true }); });
}

export function closePlayer() {
  if (!built || !st.popOpen) return;
  st.popOpen = false;
  st.closing = true;                         // 내려가는 동안은 프레임이 계속 재생부를 따라간다
  el.scrim.classList.remove("is-open");
  document.documentElement.classList.remove("mp-lock");
  followFrame(SHEET_MS + 80);
  clearTimeout(closeTimer);
  closeTimer = setTimeout(finishClose, SHEET_MS + 40);
  if (lastFocus && typeof lastFocus.focus === "function") lastFocus.focus();
}

/** 플로팅 프레임의 ✕ — 재생을 멈추고 프레임을 치운다. */
function dismissFrame() {
  clearTuck();   // 넣은 상태였으면 풀고 — 프레임은 곧 숨는다
  watchStop();
  hideSkip();
  if (yt && ytReady) { try { yt.stopVideo(); } catch (e) { /* 무시 */ } if (st.vid) { try { yt.cueVideoById(st.vid); } catch (e) { /* 무시 */ } } }
  st.started = false;
  st.playing = false;
  paint();
}
