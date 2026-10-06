// player.js — (v4.2.0) 유메미타 플레이어: 팝업(재생부 + 검색·정렬·목록) · 팝업을 내린 뒤의 플로팅 프레임.
// 열기는 playerbtn.js 가 발행하는 `mew:player-open` 이벤트 → main.js 가 이 모듈을 지연 import 해 openPlayer() 를 부른다.
//
// 설계 원칙 (YouTube API 정책 — 개발자 정책 III.I.5 · III.I.7 · III.I.9, 필수 최소 기능):
//  - 재생은 YouTube IFrame Player API 의 임베드 프레임만 쓴다. 광고는 프레임 안에서 YouTube 가 처리 — 건너뛰기를 대신하지 않는다.
//  - 프레임은 숨기지 않는다(백그라운드 재생 금지). 팝업을 내리면 같은 프레임이 플로팅으로 남는다. 크기는 항상 200×200 이상.
//  - 프레임 위에는 아무것도 덮지 않는다. 끌기 · 더블클릭용 손잡이 줄은 프레임 바깥(위)에 따로 붙는다.
//  - 프레임 요소는 한 번 만들면 옮기지 않는다(옮기면 iframe 이 다시 로드돼 재생이 끊긴다). 팝업 ↔ 플로팅은 CSS 위치만 바꾼다.
// 곡이 끝나면 다음 곡으로 넘어가지 않고 멈춘다. 반복이 켜져 있으면 같은 곡을 처음부터 다시 재생한다.
// 데이터는 textContent / createElement 로만 주입한다(XSS 방어, innerHTML 금지).

import { fetchPreview } from "./api.js";
import { SONGS_URL, FALLBACK_CHANNELS } from "./config.js";
import { KIND_LABEL, prepareSong, viewSongs, matchRange } from "./songs.js";

const ALIAS_KEY = "mew:player:aliases";   // localStorage — 사용자 별칭 { video_id: [별칭...] }. 이 브라우저에만 저장된다.
const FLOAT_W = 356;                      // 플로팅 프레임 너비(16:9 에서 높이 200 이 되는 값)
const FLOAT_H = 200;                      // 플로팅 프레임 높이 — YouTube 임베드 최소 200×200 을 채운다
const MIN_SLOT_H = 200;                   // 팝업 안 프레임 최소 높이 (좁은 화면에서도 200 이상)
const NS = "http://www.w3.org/2000/svg";

const st = {
  raw: [],
  songs: [],          // prepareSong 결과
  aliases: {},
  loadError: false,
  query: "",
  kind: "all",
  sortBy: "date",
  dir: "desc",
  editing: null,      // 별칭 편집 중인 곡 id
  curId: null,
  playing: false,
  started: false,     // 한 번이라도 재생을 시작했는가 — 팝업을 내린 뒤 플로팅 프레임을 남길지 결정
  popOpen: false,
  shuffle: false,
  repeat: false,
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
  if (name === "repeat") {   // 반복 화살표 안의 "1" — 한 곡 반복
    const t = document.createElementNS(NS, "text");
    t.setAttribute("x", "12"); t.setAttribute("y", "15"); t.setAttribute("font-size", "7"); t.setAttribute("font-weight", "700");
    t.setAttribute("text-anchor", "middle"); t.setAttribute("fill", "currentColor"); t.textContent = "1";
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
function readAliases() {
  try {
    const v = JSON.parse(localStorage.getItem(ALIAS_KEY) || "{}");
    return v && typeof v === "object" && !Array.isArray(v) ? v : {};
  } catch (e) {
    return {};
  }
}
function writeAliases() {
  try { localStorage.setItem(ALIAS_KEY, JSON.stringify(st.aliases)); } catch (e) { /* 저장 불가(사생활 보호 모드 등)면 이번 방문에만 유효 */ }
}

function loadSongs() {
  if (loadPromise) return loadPromise;
  loadPromise = fetchPreview(SONGS_URL).then((r) => {
    if (!r.ok || !r.data || !Array.isArray(r.data.songs)) { st.loadError = true; loadPromise = null; return; }
    st.loadError = false;
    st.aliases = readAliases();
    st.raw = r.data.songs;
    st.songs = st.raw.map((s) => prepareSong(s, st.aliases[s.id] || []));
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
    if (st.repeat) { yt.seekTo(0, true); yt.playVideo(); return; }
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
function selectSong(id, autoplay) {
  st.curId = id;
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
  if (!st.curId) return;
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
  el.cur = h("span", { class: "mp-mono", text: "0:00" });
  el.dur = h("span", { class: "mp-mono", text: "0:00" });
  el.fill = h("i");
  el.track = h("div", { class: "mp-track", role: "slider", "aria-label": "재생 위치", tabindex: "0", on: { click: onTrackClick, keydown: onTrackKey } }, el.fill);
  el.bPlay = h("button", { type: "button", class: "mp-main", on: { click: togglePlay } });
  el.bShuffle = h("button", { type: "button", class: "mp-tog", "aria-label": "셔플 (이전·다음 버튼이 무작위 곡으로)", title: "셔플", on: { click: () => { st.shuffle = !st.shuffle; paintControls(); } } }, icon("shuffle"));
  el.bRepeat = h("button", { type: "button", class: "mp-tog", "aria-label": "현재 곡 반복", title: "현재 곡 반복", on: { click: () => { st.repeat = !st.repeat; paintControls(); } } }, icon("repeat"));
  el.err = h("div", { class: "mp-err", role: "status", hidden: true });
  const stage = h("section", { class: "mp-stage" },
    el.slot,
    h("div", { class: "mp-song" }, el.sTitle, el.sMeta),
    h("div", { class: "mp-bar" }, el.cur, el.track, el.dur),
    h("div", { class: "mp-ctl" }, el.bShuffle, iconBtn("prev", "이전 곡", "mp-btn", () => go(-1)), el.bPlay, iconBtn("next", "다음 곡", "mp-btn", () => go(1)), el.bRepeat),
    el.err,
    h("p", { class: "mp-note", text: "선택한 곡만 재생하고 끝나면 멈춥니다. 반복을 켜면 처음부터 다시 재생합니다. 광고는 YouTube 가 프레임 안에서 직접 보여줍니다." }),
  );

  // 목록부
  el.q = h("input", { id: "mp-q", type: "search", placeholder: "곡명 · 독음(가나·한글) · 별칭 검색", autocomplete: "off", "aria-label": "곡 검색", on: { input: (e) => { st.query = e.target.value; paintList(); } } });
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
  el.gTitle = h("span", { class: "mp-grip__title" });
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
  paintList();
  paintGrip();
  layoutFrame();
}

function paintStage() {
  const s = curSong();
  el.sTitle.textContent = s ? s.title : "곡을 고르세요";
  el.sMeta.replaceChildren();
  if (s) {
    const m = memberOf(s.who);
    if (m) el.sMeta.append(h("span", { class: "mp-dot", style: `--mc:${m.color}` }), `${m.name} · `);
    el.sMeta.append(`${KIND_LABEL[s.kind] || s.kind} · ${s.date} · BPM ${s.bpm} · ${s.key}`);
    if (s.reading) el.sMeta.append(` · ${s.reading} · ${s.readingKo}`);
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
  el.bRepeat.setAttribute("aria-pressed", String(st.repeat));
}

function paintGrip() {
  const s = curSong();
  el.gTitle.textContent = s ? s.title : "";
}

function paintTools() {
  el.kinds.replaceChildren(...[["all", "전체"], ["solo", "솔로"], ["original", "오리지널"], ["cover", "커버"]].map(([k, l]) =>
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

function songRow(s, i, q) {
  const cur = s.id === st.curId;
  const m = memberOf(s.who);
  const sub = h("span", { class: "mp-item__sub" },
    m ? h("span", { class: "mp-dot", style: `--mc:${m.color}` }) : null,
    m ? h("span", { text: m.name }) : null,
    h("span", { text: KIND_LABEL[s.kind] || s.kind }),
    h("span", { class: "mp-mono", text: s.date }),
    s.reading ? h("em", {}, ...highlight(s.reading, q)) : null,
    s.readingKo ? h("em", {}, ...highlight(s.readingKo, q)) : null,
    ...s.aliases.map((a) => h("span", { class: "mp-alias" }, "#", ...highlight(a, q))),
  );
  const main = h("button", { type: "button", class: "mp-item__main", "aria-current": cur ? "true" : null, on: { click: () => selectSong(s.id, true) } },
    h("span", { class: "mp-item__n mp-mono", text: cur && st.playing ? "▶" : String(i + 1) }),
    h("span", { class: "mp-item__body" }, h("span", { class: "mp-item__title" }, ...highlight(s.title, q)), sub),
  );
  const li = h("li", { class: "mp-item" + (cur ? " is-cur" : "") }, main,
    h("button", { type: "button", class: "mp-edit", "aria-label": `${s.title} 별칭 편집`, text: "✎ 별칭", on: { click: () => { st.editing = st.editing === s.id ? null : s.id; paintList(); } } }));
  if (st.editing === s.id) li.append(aliasEditor(s));
  return li;
}

function aliasEditor(s) {
  const input = h("input", { class: "mp-alias-in", type: "text", value: s.aliases.join(", "), placeholder: "별칭 (쉼표로 구분)", "aria-label": `${s.title} 별칭` });
  const save = () => {
    const arr = input.value.split(",").map((x) => x.trim()).filter(Boolean);
    if (arr.length) st.aliases[s.id] = arr; else delete st.aliases[s.id];
    writeAliases();
    const idx = st.songs.findIndex((x) => x.id === s.id);
    st.songs[idx] = prepareSong(st.raw.find((r) => r.id === s.id), arr);
    st.editing = null;
    paintList();
  };
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); save(); }
    else if (e.key === "Escape") { e.stopPropagation(); st.editing = null; paintList(); }
  });
  setTimeout(() => input.focus(), 0);
  return h("div", { class: "mp-alias-edit" }, input, h("button", { type: "button", class: "mp-edit", text: "저장", on: { click: save } }));
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
  st.editing = null;
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
