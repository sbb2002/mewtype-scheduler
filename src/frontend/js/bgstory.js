// bgstory.js — (bg-dome-mgcyan) UFO 돔 스토리 「다시, 이 하늘」(AGAIN, THIS SKY) 의 화면. 상태 · 규칙은 bgstorylogic.js(순수), 언제 부르는지는 bgdomegl.js.
//   · 출발 카드 — 화면 위쪽에 제목 + (곡이 흐르면) NOW PLAYING · 곡 제목. 3.6초 뒤 사라짐
//   · 방위선 레이더 — 좌하단(맥박 신호 바로 위, 라벨은 레이더 아래). 찾은 딥필드마다 방위선 하나, 다섯이면 한 점에서 겹치고 ORIGIN FIXED
//   · 발견 장면 — 달 궤도에서 지구를 잡으면 약 1초 동안 방위선이 지구 위로 모여 겹치고 SIGNAL ORIGIN · EARTH, 이어 NOW PLAYING 카드
// 모양 = 시안(HUD Motion Study · Cyan) 문법(css/bgpanel.css .ufo-story*). DOM 은 createElement · textContent 만(innerHTML 금지).
// 되살아남 방지: 예약한 setTimeout 은 모두 세대 번호(gen)를 확인한다 — cancel() · remove() 뒤엔 아무것도 다시 켜지지 않는다.

import { LINE_KEYS, lineAngle, STORY_TITLE } from "./bgstorylogic.js";

const REDUCE = window.matchMedia("(prefers-reduced-motion: reduce)");
const DEG = Math.PI / 180;
const CY = "94,242,255", HOT = "255,138,61";
const MONO = '"HUD Mono", ui-monospace, Menlo, Consolas, monospace';
const DISP = '"HUD Chakra", "Bahnschrift", "Roboto Condensed", system-ui, sans-serif';
const RADAR = 76;   // 레이더 한 변(px) — 맥박 신호 위 · 정보 카드(아래 136px) 밑 · 「ZOOM IN TO APPROACH」(가운데) 왼쪽에 들어가는 크기

function h(tag, cls, text) { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }

export function createStory() {
  const root = h("div", "ufo-story");
  root.setAttribute("aria-live", "polite");
  const cv = h("canvas", "ufo-story__cv"); cv.setAttribute("aria-hidden", "true");
  const g = cv.getContext("2d");
  const card = h("div", "ufo-story__card");
  const cTag = h("p", "ufo-story__tag"), cTitle = h("p", "ufo-story__title"), cNow = h("p", "ufo-story__now");
  card.append(cTag, cTitle, cNow);
  card.hidden = true;
  const radarLbl = h("p", "ufo-story__rl");
  radarLbl.hidden = true;
  const probe = h("div", "ufo-story__probe");   // 아래 안전 영역 높이(env) 재기
  root.append(cv, card, radarLbl, probe);
  document.body.appendChild(root);

  let gen = 0, W = 0, H = 0, dpr = 1, sb = 0;
  let radarOn = false, lines = [], fresh = null, conv = false, convAt = 0;   // fresh = { key, t } 방금 쌓인 선 · convAt = 지금 막 겹친 시각(애니메이션)
  let disc = null;   // { t0, dir } 발견 장면
  const timers = new Set();
  const later = (ms, fn) => { const my = gen; const id = setTimeout(() => { timers.delete(id); if (my === gen) fn(); }, ms); timers.add(id); };
  const now = () => performance.now() / 1000;

  function resize() { W = window.innerWidth; H = window.innerHeight; dpr = Math.min(window.devicePixelRatio || 1, 2); cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr); sb = probe.offsetHeight || 0; }
  window.addEventListener("resize", resize);

  function showCard(tag, title, nowTitle, ms) {
    cTag.textContent = tag; cTitle.textContent = title || ""; cTitle.hidden = !title;
    cNow.textContent = nowTitle ? `NOW PLAYING · ${nowTitle}` : ""; cNow.hidden = !nowTitle;
    card.hidden = false; card.classList.remove("is-on"); void card.offsetWidth; card.classList.add("is-on");
    later(ms, () => { card.classList.remove("is-on"); later(450, () => { card.hidden = true; }); });
  }

  // 레이더 중심 · 겹치는 점(신호 근원). 선 i = 테두리의 자기 각도에서 근원을 지나 조금 더
  const radarBox = () => ({ x: 14 + RADAR / 2, y: H - sb - 50 - RADAR / 2, r: RADAR / 2 - 6 });
  function drawRadar(t) {
    const { x, y, r } = radarBox(), ox = x + r * 0.22, oy = y - r * 0.18;
    g.fillStyle = "rgba(4,8,11,.62)"; g.fillRect(x - r - 6, y - r - 6, RADAR, RADAR);
    // 모서리 꺾쇠
    const b = 9, L = x - r - 6, T = y - r - 6, R2 = L + RADAR, B2 = T + RADAR;
    g.strokeStyle = `rgba(${CY},.6)`; g.lineWidth = 1.5; g.beginPath();
    g.moveTo(L, T + b); g.lineTo(L, T); g.lineTo(L + b, T); g.moveTo(R2 - b, T); g.lineTo(R2, T); g.lineTo(R2, T + b);
    g.moveTo(R2, B2 - b); g.lineTo(R2, B2); g.lineTo(R2 - b, B2); g.moveTo(L + b, B2); g.lineTo(L, B2); g.lineTo(L, B2 - b); g.stroke();
    g.lineWidth = 1; g.strokeStyle = `rgba(${CY},.25)`;
    g.beginPath(); g.arc(x, y, r, 0, 7); g.stroke();
    g.beginPath(); g.arc(x, y, r * 0.5, 0, 7); g.stroke();
    // 자리 표시(빈 칸 = 흐린 점)
    for (const k of LINE_KEYS) {
      const a = lineAngle(k) * DEG, px = x + Math.cos(a) * r, py = y + Math.sin(a) * r, has = lines.includes(k);
      g.fillStyle = has ? `rgba(${CY},.95)` : `rgba(${CY},.25)`; g.fillRect(px - 2, py - 2, 4, 4);
      if (!has) continue;
      let p = 1;
      if (fresh && fresh.key === k) p = REDUCE.matches ? 1 : Math.min(1, (t - fresh.t) / 0.9);
      const ex = px + (ox - px) * 1.25 * p, ey = py + (oy - py) * 1.25 * p;
      g.strokeStyle = conv ? `rgba(${HOT},.9)` : `rgba(${CY},.85)`; g.lineWidth = 1.2;
      g.beginPath(); g.moveTo(px, py); g.lineTo(ex, ey); g.stroke();
    }
    if (conv) {
      const u = convAt && !REDUCE.matches ? Math.min(1, (t - convAt) / 1.2) : 1;
      g.strokeStyle = `rgba(${HOT},${(1 - u) * 0.9})`; g.beginPath(); g.arc(ox, oy, 3 + u * 14, 0, 7); g.stroke();
      g.fillStyle = `rgba(${HOT},1)`; g.beginPath(); g.arc(ox, oy, 2.5, 0, 7); g.fill();
    }
    g.lineWidth = 1;
  }

  function drawDiscovery(t, project) {
    const p = disc && project(disc.dir);
    const age = t - disc.t0;
    if (age > 2.2) { disc = null; return; }
    if (!p) return;
    const R = Math.min(W, H) * 0.34;
    const draw = REDUCE.matches ? 1 : Math.min(1, age / 0.6);          // 0 ~ 0.6초: 다섯 방향에서 지구로 모인다
    const al = age < 1.4 ? 1 : Math.max(0, 1 - (age - 1.4) / 0.8);     // 1.4 ~ 2.2초: 사라짐 → 보이는 시간 약 1초 + 잔상
    g.lineWidth = 1.4;
    for (const k of LINE_KEYS) {
      const a = lineAngle(k) * DEG, sx = p[0] + Math.cos(a) * R, sy = p[1] + Math.sin(a) * R;
      g.strokeStyle = `rgba(${draw >= 1 ? HOT : CY},${0.85 * al})`;
      g.beginPath(); g.moveTo(sx, sy); g.lineTo(sx + (p[0] - sx) * draw, sy + (p[1] - sy) * draw); g.stroke();
    }
    if (draw >= 1) {
      const u = REDUCE.matches ? 1 : Math.min(1, (age - 0.6) / 0.6);
      g.strokeStyle = `rgba(${HOT},${(1 - u) * al})`; g.beginPath(); g.arc(p[0], p[1], 8 + u * 46, 0, 7); g.stroke();
      g.font = `600 13px ${DISP}`; g.textAlign = "center"; g.textBaseline = "middle";
      const lbl = "SIGNAL ORIGIN · EARTH", tw = g.measureText(lbl).width + 16;
      g.fillStyle = `rgba(4,8,11,${0.78 * al})`; g.fillRect(p[0] - tw / 2, p[1] + 58, tw, 24);
      g.fillStyle = `rgba(${HOT},${al})`; g.fillText(lbl, p[0], p[1] + 70);
    }
    g.lineWidth = 1;
  }

  return {
    /** 출발 장면 — title = 지금 곡 제목(무음이면 null) */
    intro(title) { showCard("TRANSMISSION · 01", STORY_TITLE, title, 3600); },
    /** 레이더 — on(보일지) · keys(쌓인 장소) · added(방금 쌓인 장소, 없으면 null) */
    setRadar(on, keys, added = null) {
      radarOn = !!on; lines = keys.slice(); radarLbl.hidden = !radarOn;
      const t = now();
      if (added) fresh = { key: added, t };
      const c = LINE_KEYS.every((k) => lines.includes(k));
      if (c && !conv) convAt = added ? t : 0;   // 지금 막 겹침이면 고리 애니메이션, 불러온 상태면 정지 그림
      conv = c;
      radarLbl.textContent = conv ? "ORIGIN FIXED" : `BEARINGS ${lines.length}/${LINE_KEYS.length}`;
      radarLbl.classList.toggle("is-hot", conv);
    },
    /** 발견 장면 — dir = 지구 방향(돔 좌표), title = 지금 곡 제목(무음이면 null) */
    discover(dir, title) {
      disc = { t0: now(), dir };
      later(1500, () => showCard("SIGNAL ORIGIN · EARTH", null, title, 3200));
    },
    /** 발견 장면이 끝난 뒤(약 5.2초) fn — 같은 자리의 해금 알림이 카드와 겹치지 않게. cancel() 뒤엔 부르지 않는다 */
    afterDiscovery(fn) { later(5200, fn); },
    /** 한 프레임. f = { active(배경 보기 중), project(dir → [x, y] | null) } */
    update(f) {
      if (!W) resize();
      g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, W, H);
      root.classList.toggle("is-on", !!f.active);
      if (!f.active) return;
      const t = now();
      if (radarOn) drawRadar(t);
      if (disc) drawDiscovery(t, f.project);
    },
    get busy() { return !!disc || !card.hidden; },
    /** 배경 보기를 나감 · 스토리 끝 — 예약한 것 · 진행 중 장면을 모두 거둔다 */
    cancel() {
      gen++; for (const id of timers) clearTimeout(id); timers.clear();
      disc = null; card.classList.remove("is-on"); card.hidden = true;
    },
    remove() { this.cancel(); window.removeEventListener("resize", resize); root.remove(); },
  };
}
