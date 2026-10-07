// player.js — (v4.2.0) 유메미타 플레이어: 팝업(재생부 + 검색·정렬·목록) · 팝업을 내린 뒤의 플로팅 프레임.
// 열기는 playerbtn.js 가 발행하는 `mew:player-open` 이벤트 → main.js 가 이 모듈을 지연 import 해 openPlayer() 를 부른다.
//
// 설계 원칙 (YouTube API 정책 — 개발자 정책 III.I.5 · III.I.7 · III.I.9, 필수 최소 기능):
//  - 재생은 YouTube IFrame Player API 의 임베드 프레임만 쓴다. 광고는 프레임 안에서 YouTube 가 처리 — 건너뛰기를 대신하지 않는다.
//  - 프레임은 숨기지 않는다(백그라운드 재생 금지). 팝업을 내리면 같은 프레임이 플로팅으로 남는다. 크기는 항상 200×200 이상.
//  - 프레임 위에는 아무것도 덮지 않는다. 끌기 · 더블클릭용 손잡이 줄은 프레임 바깥(위)에 따로 붙는다.
//  - 프레임 요소는 한 번 만들면 옮기지 않는다(옮기면 iframe 이 다시 로드돼 재생이 끊긴다). 팝업 ↔ 플로팅은 CSS 위치만 바꾼다.
// 재생목록: 목록의 곡을 누르면 재생목록에 순서대로 쌓이고(같은 곡도 여러 번 쌓인다), 재생은 1번부터 순서대로 이어진다.
// 곡이 끝나면 재생목록의 다음 곡으로 넘어가고, 마지막이면 멈춘다. 재생목록 밖의 곡은 끝나면 멈춘다(추천 영상으로 넘어가지 않게 처음 화면으로 되돌림).
// 반복(BPM 과 같은 3단계): 꺼짐 → 한 곡(같은 곡 처음부터) → 전체(마지막 곡 뒤에 1번으로).
// 데이터는 textContent / createElement 로만 주입한다(XSS 방어, innerHTML 금지).

import { fetchPreview } from "./api.js";
import { SONGS_URL, SONGS_FALLBACK_URL, FALLBACK_CHANNELS } from "./config.js";
import { KIND_LABEL, displayKo, isNewSong, prepareSong, viewSongs, matchRange } from "./songs.js";

const FLOAT_W = 356;                      // 플로팅 프레임 너비(16:9 에서 높이 200 이 되는 값)
const FLOAT_H = 200;                      // 플로팅 프레임 높이 — YouTube 임베드 최소 200×200 을 채운다
const MIN_SLOT_H = 200;                   // 팝업 안 프레임 최소 높이 (좁은 화면에서도 200 이상)
const NS = "http://www.w3.org/2000/svg";

const st = {
  raw: [],
  songs: [],          // prepareSong 결과
  loadError: false,
  query: "",
  kind: "all",
  sortBy: "date",
  dir: "desc",
  curId: null,
  playing: false,
  started: false,     // 한 번이라도 재생을 시작했는가 — 팝업을 내린 뒤 플로팅 프레임을 남길지 결정
  popOpen: false,
  shuffle: false,
  repeat: "off",      // "off" | "one" | "all" — 버튼을 누를 때마다 순환 (BPM 과 같다)
  queue: [],          // 재생목록 — 곡 id 를 쌓은 순서대로(같은 곡을 여러 번 쌓을 수 있다)
  qi: -1,             // 지금 곡의 재생목록 위치(0부터). -1 = 지금 곡이 재생목록에서 고른 것이 아님 — 같은 곡이 여럿일 수 있어 id 가 아니라 위치로 센다
  fpos: null,         // 플로팅 프레임을 끌어 옮긴 위치 {x,y}. null 이면 CSS 기본(오른쪽 아래)
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
  search: null,
};

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
  if (key === "group") return { name: "그룹", color: "var(--color-collab)" };
  const ch = FALLBACK_CHANNELS[key];
  if (!ch) return null;
  const lane = document.querySelector(`.lane[data-channel="${CSS.escape(key)}"]`);
  const c = lane ? getComputedStyle(lane).getPropertyValue("--lane-color").trim() : "";
  return { name: ch.name_ko.split(" ").pop(), color: c || "var(--color-text-muted)" };
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
          // 로딩 중에 다른 곡이 골라졌으면 그 곡으로 바꾼다
          try {
            if (st.curId && st.curId !== videoId) wantPlay ? yt.loadVideoById(st.curId) : yt.cueVideoById(st.curId);
            else if (wantPlay) yt.playVideo();
          } catch (e) { /* 자동 재생 거부는 YouTube 쪽 컨트롤로 */ }
          startTick();
        },
        onStateChange: onYtState,
        onError: (e) => { st.error = { id: st.curId, code: e.data }; st.playing = false; paint(); },
      },
    });
  } catch (e) {
    st.error = { id: st.curId, code: "api" };
    paint();
  }
}

function onYtState(e) {
  const S = window.YT.PlayerState;
  if (e.data === S.PLAYING || e.data === S.BUFFERING) { st.playing = true; st.started = true; st.error = null; }
  else if (e.data === S.PAUSED || e.data === S.CUED) st.playing = false;
  else if (e.data === S.ENDED) {
    if (st.repeat === "one") { yt.seekTo(0, true); yt.playVideo(); return; }
    if (st.qi >= 0 && st.qi + 1 < st.queue.length) { playQueueAt(st.qi + 1); return; }   // 재생목록의 다음 곡
    if (st.qi >= 0 && st.repeat === "all") { playQueueAt(0); return; }                    // 마지막 뒤에 1번으로
    st.playing = false;
    st.pos = 0;
    yt.cueVideoById(st.curId);   // 처음 화면으로 되돌려 멈춘다 — 끝 화면의 추천 영상으로 넘어가지 않게
  }
  paint();
}

function startTick() {
  if (tickTimer) return;
  tickTimer = setInterval(() => {
    if (!yt || !ytReady || typeof yt.getCurrentTime !== "function") return;
    st.pos = yt.getCurrentTime() || 0;
    st.dur = yt.getDuration() || 0;
    paintProgress();
  }, 500);
}

/** 곡 선택. autoplay=true 면 바로 재생(사용자 조작 직후에만), false 면 첫 화면만 불러 둔다. */
/** qi = 이 곡의 재생목록 위치(재생목록에서 고른 경우). 아니면 -1. */
function selectSong(id, autoplay, qi = -1) {
  st.curId = id;
  st.qi = qi;
  st.pos = 0;
  st.dur = 0;
  st.error = null;
  if (autoplay) st.started = true;
  wantPlay = autoplay;
  if (!yt) ensurePlayer(id, autoplay);
  else if (ytReady) { try { autoplay ? yt.loadVideoById(id) : yt.cueVideoById(id); } catch (e) { /* 오류는 onError 로 */ } }
  paint();
}

function togglePlay() {
  if (!st.curId && !st.queue.length) return;
  // 재생목록이 있는데 지금 곡이 그 안에 없으면 1번부터 시작한다(멈춰 있을 때만 — 재생 중 일시정지는 그대로)
  if (st.queue.length && !st.playing && st.qi < 0) { playQueueAt(0); return; }
  st.started = true;
  if (yt && ytReady) {
    if (st.playing) yt.pauseVideo();
    else yt.playVideo();
  } else {
    selectSong(st.curId, true);
  }
  paint();
}

function go(dir) {
  if (st.queue.length) {   // 재생목록이 있으면 그 안에서 이동 (셔플이면 무작위)
    const q = st.queue;
    let next;
    if (st.shuffle && q.length > 1) {
      do { next = Math.floor(Math.random() * q.length); } while (next === st.qi);
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
  if (st.queue.length === 1) { selectSong(id, true, 0); return; }
  paint();
}
/** 재생목록의 i 번째 곡으로 이동 · 재생. */
function playQueueAt(i) {
  if (i < 0 || i >= st.queue.length) return;
  selectSong(st.queue[i], true, i);
}
/** i 번째 항목을 뺀다. 지금 곡이 빠지면 그 곡은 끝까지 재생되고 거기서 멈춘다(재생목록에서 고른 곡이 아니게 됨). */
function removeFromQueue(i) {
  if (i < 0 || i >= st.queue.length) return;
  st.queue.splice(i, 1);
  if (i < st.qi) st.qi -= 1;
  else if (i === st.qi) st.qi = -1;
  paint();
}
function clearQueue() {
  st.queue = [];
  st.qi = -1;
  paint();
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
  el.track = h("div", { class: "mp-track", role: "slider", "aria-label": "재생 위치", tabindex: "0", on: { click: onTrackClick, keydown: onTrackKey } }, el.fill);
  el.bPlay = h("button", { type: "button", class: "mp-main", on: { click: togglePlay } });
  el.bShuffle = h("button", { type: "button", class: "mp-tog", "aria-label": "셔플 (이전·다음 버튼이 무작위 곡으로)", title: "셔플", on: { click: () => { st.shuffle = !st.shuffle; paintControls(); } } }, icon("shuffle"));
  el.bRepeat = h("button", { type: "button", class: "mp-tog", on: { click: () => { st.repeat = st.repeat === "off" ? "one" : st.repeat === "one" ? "all" : "off"; paintControls(); } } }, icon("repeat"));
  el.err = h("div", { class: "mp-err", role: "status", hidden: true });
  el.qCount = h("span", { class: "mp-q__count" });
  el.qClear = h("button", { type: "button", class: "mp-link", text: "비우기", on: { click: clearQueue } });
  el.qList = h("ol", { class: "mp-q__list" });
  el.qBox = h("section", { class: "mp-q", "aria-label": "재생목록" },
    h("div", { class: "mp-q__head" }, h("strong", { text: "재생목록" }), el.qCount, el.qClear),
    el.qList,
  );
  const stage = h("section", { class: "mp-stage" },
    el.slot,
    h("div", { class: "mp-song" }, el.sTitle, el.sMeta, el.sKo),
    h("div", { class: "mp-bar" }, el.cur, el.track, el.dur),
    h("div", { class: "mp-ctl" }, el.bShuffle, iconBtn("prev", "이전 곡", "mp-btn", () => go(-1)), el.bPlay, iconBtn("next", "다음 곡", "mp-btn", () => go(1)), el.bRepeat),
    el.err,
    el.qBox,
  );

  // 목록부
  el.q = h("input", { id: "mp-q", type: "search", placeholder: "곡명 · 독음(가나·한글) 검색", autocomplete: "off", "aria-label": "곡 검색", on: { input: (e) => { st.query = e.target.value; paintList(); } } });
  el.kinds = h("div", { class: "mp-chips", role: "group", "aria-label": "종류" });
  el.sort = h("div", { class: "mp-sort", role: "group", "aria-label": "정렬" });
  el.list = h("ul", { class: "mp-list" });
  el.count = h("div", { class: "mp-count" });
  const lib = h("section", { class: "mp-lib" },
    h("div", { class: "mp-tools" },
      h("label", { class: "mp-search" }, icon("search", "mp-ico mp-ico--s"), el.q),
      h("div", { class: "mp-row2" }, el.kinds, el.sort),
    ),
    el.list,
    el.count,
  );

  el.pop = h("div", { class: "mp-pop", role: "dialog", "aria-modal": "true", "aria-labelledby": "mp-title" },
    h("div", { class: "mp-pop__head" }, el.titleEl, el.closeBtn),
    h("div", { class: "mp-pop__body" }, stage, lib),
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
    h("span", { class: "mp-grip__btns" },
      iconBtn("prev", "이전 곡", "mp-gbtn", () => go(-1)),
      iconBtn("next", "다음 곡", "mp-gbtn", () => go(1)),
      h("button", { type: "button", class: "mp-gbtn", "aria-label": "팝업 열기", title: "팝업 열기", text: "▴", on: { click: openPlayer } }),
      h("button", { type: "button", class: "mp-gbtn", "aria-label": "플레이어 닫기 (정지)", title: "닫기 (정지)", text: "✕", on: { click: dismissFrame } }),
    ),
  );
  el.ytBox = h("div", { class: "mp-yt" }, el.ytTarget);
  el.frame = h("div", { class: "mp-frame", id: "player-frame", hidden: true }, el.grip, el.ytBox);

  document.body.append(el.scrim, el.frame);

  initGripDrag();
  el.scrim.addEventListener("keydown", trapFocus);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && st.popOpen) closePlayer(); });
  window.addEventListener("resize", () => { clampFloat(); layoutFrame(); });
  if (typeof ResizeObserver === "function") new ResizeObserver(layoutFrame).observe(el.slot);
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
    const m = memberOf(s.who);
    if (m) el.sMeta.append(h("span", { class: "mp-dot", style: `--mc:${m.color}` }), `${m.name} · `);
    el.sMeta.append(`${KIND_LABEL[s.kind] || s.kind} · ${s.date}`);
  }
  el.err.hidden = !st.error;
  el.err.replaceChildren();
  if (st.error) {
    const url = `https://youtu.be/${st.error.id || st.curId}`;
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
  el.bPlay.replaceChildren(icon(st.playing ? "pause" : "play"));
  el.bPlay.setAttribute("aria-label", st.playing ? "일시정지" : "재생");
  el.bShuffle.setAttribute("aria-pressed", String(st.shuffle));
  const rp = st.repeat;
  el.bRepeat.setAttribute("aria-pressed", String(rp !== "off"));
  const lab = rp === "off" ? "반복 (꺼짐) — 누르면 한 곡 반복" : rp === "one" ? "한 곡 반복 (켜짐) — 누르면 전체 반복" : "전체 반복 (켜짐) — 누르면 끄기";
  el.bRepeat.setAttribute("aria-label", lab);
  el.bRepeat.title = lab;
  const t = el.bRepeat.querySelector(".mp-rpt");
  if (t) t.textContent = rp === "one" ? "1" : rp === "all" ? "A" : "";
}

function paintQueue() {
  if (!built) return;
  el.qCount.textContent = st.queue.length ? `${st.queue.length}곡` : "";
  el.qClear.hidden = !st.queue.length;
  if (!st.queue.length) {
    el.qList.replaceChildren(h("li", { class: "mp-q__empty", text: "오른쪽 목록에서 곡을 누르면 여기에 쌓입니다. 재생은 1번부터 순서대로 이어집니다." }));
    return;
  }
  el.qList.replaceChildren(...st.queue.map((id, i) => {
    const s = st.songs.find((x) => x.id === id);
    if (!s) return null;
    const cur = i === st.qi;   // 같은 곡이 여러 번 있어도 위치로 구분
    return h("li", { class: "mp-q__item" + (cur ? " is-cur" : "") },
      h("button", { type: "button", class: "mp-q__main", "aria-current": cur ? "true" : null, on: { click: () => playQueueAt(i) } },
        h("span", { class: "mp-mono mp-q__n", text: cur && st.playing ? "▶" : String(i + 1) }),
        h("span", { class: "mp-q__title", text: s.title })),
      h("button", { type: "button", class: "mp-q__x", "aria-label": `${s.title} 재생목록에서 빼기`, title: "빼기", text: "✕", on: { click: () => removeFromQueue(i) } }));
  }));
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

/** 최근 7일 안에 등록된 곡 표시 — 곡 줄 · 재생 중 곡 제목 옆. */
function newPill() {
  return h("span", { class: "mp-new", text: "NEW" });
}

function songRow(s, i, q) {
  const cur = s.id === st.curId;
  const m = memberOf(s.who);
  const sub = h("span", { class: "mp-item__sub" },
    m ? h("span", { class: "mp-dot", style: `--mc:${m.color}` }) : null,
    m ? h("span", { text: m.name }) : null,
    h("span", { text: KIND_LABEL[s.kind] || s.kind }),
    h("span", { class: "mp-mono", text: s.date }),
  );
  const qns = st.queue.flatMap((x, k) => (x === s.id ? [k + 1] : []));   // 재생목록에서의 번호들(같은 곡이 여러 번일 수 있다)
  if (qns.length) sub.append(h("span", { class: "mp-q-badge", text: `재생목록 ${qns.join("·")}번` }));
  const main = h("button", { type: "button", class: "mp-item__main", "aria-current": cur ? "true" : null, title: "재생목록에 추가", on: { click: () => addToQueue(s.id) } },
    h("span", { class: "mp-item__n mp-mono", text: cur && st.playing ? "▶" : String(i + 1) }),
    h("span", { class: "mp-item__body" }, h("span", { class: "mp-item__title" }, ...highlight(s.title, q), ...(isNewSong(s) ? [" ", newPill()] : [])), sub,
      displayKo(s) ? h("span", { class: "mp-item__ko" }, ...highlight(displayKo(s), q)) : null),
  );
  return h("li", { class: "mp-item" + (cur ? " is-cur" : "") }, main);
}

// ── 프레임 배치 ──────────────────────────────────────────────────────
function layoutFrame() {
  if (!built) return;
  const f = el.frame;
  const show = st.popOpen || st.started;
  f.hidden = !show;
  if (!show) return;
  if (st.popOpen) {
    // 팝업 안: 재생부 자리(slot) 위에 겹친다. 손잡이 줄은 숨김.
    const r = el.slot.getBoundingClientRect();
    f.classList.remove("is-float");
    f.style.cssText = `left:${r.left}px;top:${r.top}px;width:${r.width}px;height:${r.height}px;right:auto;bottom:auto`;
  } else {
    f.classList.add("is-float");
    f.style.cssText = st.fpos ? `left:${st.fpos.x}px;top:${st.fpos.y}px;right:auto;bottom:auto` : "";
  }
}

function clampFloat() {
  if (!st.fpos || !built || st.popOpen) return;
  const w = el.frame.offsetWidth, hh = el.frame.offsetHeight;
  st.fpos = { x: Math.min(Math.max(0, st.fpos.x), Math.max(0, innerWidth - w)), y: Math.min(Math.max(0, st.fpos.y), Math.max(0, innerHeight - hh)) };
}

// ── 손잡이: 끌기 · 더블클릭 ──────────────────────────────────────────
function initGripDrag() {
  let drag = null;
  el.grip.addEventListener("pointerdown", (e) => {
    if (e.target.closest("button") || e.button > 0) return;
    const r = el.frame.getBoundingClientRect();
    drag = { dx: e.clientX - r.left, dy: e.clientY - r.top };
    el.grip.setPointerCapture(e.pointerId);
    e.preventDefault();
  });
  el.grip.addEventListener("pointermove", (e) => {
    if (!drag) return;
    const w = el.frame.offsetWidth, hh = el.frame.offsetHeight;
    st.fpos = { x: Math.min(Math.max(0, e.clientX - drag.dx), Math.max(0, innerWidth - w)), y: Math.min(Math.max(0, e.clientY - drag.dy), Math.max(0, innerHeight - hh)) };
    layoutFrame();
  });
  const end = () => { drag = null; };
  el.grip.addEventListener("pointerup", end);
  el.grip.addEventListener("pointercancel", end);
  el.grip.addEventListener("dblclick", (e) => { if (!e.target.closest("button")) openPlayer(); });
}

// ── 진행 바 ──────────────────────────────────────────────────────────
function seekTo(ratio) {
  if (!yt || !ytReady || !(st.dur > 0)) return;
  yt.seekTo(Math.min(Math.max(0, ratio), 1) * st.dur, true);
  st.pos = Math.min(Math.max(0, ratio), 1) * st.dur;
  paintProgress();
}
function onTrackClick(e) {
  const r = el.track.getBoundingClientRect();
  seekTo((e.clientX - r.left) / r.width);
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

export async function openPlayer() {
  build();
  if (st.popOpen) return;
  lastFocus = document.activeElement;
  st.popOpen = true;
  el.scrim.hidden = false;
  document.documentElement.classList.add("mp-lock");
  paintTools();
  paintList();
  layoutFrame();
  if (!st.songs.length) {
    await loadSongs();
    paintTools();
  }
  // 처음 열면 가장 최근 곡의 첫 화면만 불러 둔다 — 재생은 사용자가 누를 때 시작
  if (!st.curId && st.songs.length) selectSong(viewSongs(st.songs, { sortBy: "date", dir: "desc" })[0].id, false);
  else paint();
  requestAnimationFrame(() => { layoutFrame(); el.closeBtn.focus(); });
}

export function closePlayer() {
  if (!built || !st.popOpen) return;
  st.popOpen = false;
  el.scrim.hidden = true;
  document.documentElement.classList.remove("mp-lock");
  layoutFrame();
  if (lastFocus && typeof lastFocus.focus === "function") lastFocus.focus();
}

/** 플로팅 프레임의 ✕ — 재생을 멈추고 프레임을 치운다. */
function dismissFrame() {
  if (yt && ytReady) { try { yt.stopVideo(); } catch (e) { /* 무시 */ } if (st.curId) { try { yt.cueVideoById(st.curId); } catch (e) { /* 무시 */ } } }
  st.started = false;
  st.playing = false;
  paint();
}
