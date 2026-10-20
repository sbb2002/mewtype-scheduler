// king.js — (v4.3.1) 노노카 지각 이스터에그 「국왕 납시오」.
// 노노카 본인 방송이 예정 시각을 넘기면 왕이 자리를 비운 궁이 차려지고, 대신(왕보다 낮고 신하보다 높은 신분)이
// 신하(시청자)들에게 사정을 대신 고한다. 방송이 시작되면(라이브 전환) 입장 연출을 재생하고, 끝나면 곧바로
// 1.2초에 걸쳐 서서히 평소의 라이브 모습으로 돌아간다(무대·장식이 옅어지고 대신의 말 칸이 접힘). 설계 시안: 「국왕 행차 연출」 아티팩트.
//
//  표시 위치 3곳 — timetable.js 가 호출한다 (노노카 본인 방송이고 노노카 행/레인일 때만):
//    decorateBlock(blockEl, entry, state)                  PC 타임테이블 블록: 썸네일 위 왕관 · 카펫 띠 · 상태 글자
//    decoratePopup(popEl, imgEl, bodyEl, entry, state)     PC 블록 팝업: 무대 전체 + 대신의 말
//    decorateCard(cardEl, thumbEl, mainEl, entry, state)   모바일 오늘 카드: 무대 전체 + 대신의 말
//
//  단계(예정 시각 + 지각 시간): 1 ~3분 · 2 3~5분 · 3 5~10분 · 4 10~20분 · 5 20분~
//  시계 기준: 지각 = 지금 − scheduled_start
//            입장 연출 대상 = actual_start − 약속 시각 ≥ 1분 (약속 시각 = scheduled_start 와 announced_start 중 이른 것 — (v4.5.8)
//              영상 없는 예고가 실물에 흡수되면 실물 scheduled_start 는 YouTube 값이라, 백엔드가 예고 시각을 announced_start 로 넘긴다)
//   (v4.5.8 운영자 결정) 지각한 방송이 라이브인 동안에는 **시각과 상관없이 무조건** — 이 페이지가 그 방송을 라이브로 처음 그릴 때
//   (접속 · 열어 둔 화면이 라이브를 받음) 입장 연출(ARRIVE_MS)을 한 번 재생하고, 끝나면 바로 leave() 로 .k-leave 를 붙여 LEAVE_MS 동안
//   서서히 걷어낸 뒤 finish() 로 장식 DOM 을 지운다(= 평소 라이브 카드). 같은 페이지에서 다시 그려져도 재생하지 않는다(played).
//   전(v4.3.1~v4.5.7)엔 actual_start + 1분(v4.5.1 전 3분) 안에서만 연출했는데, 화면이 라이브를 알게 되는 건 백엔드 감지(0.3~6분) +
//   raw CDN 캐시(최대 5분) + 폴링(75초) 뒤라 그 창이 거의 늘 지나 있어 입장 연출이 나오지 않았다(2026-10-20).
//   탭이 숨겨져 있는 동안엔 시작하지 않고(k.mode "await") 탭이 보일 때 시작한다.
// 데이터는 textContent/createElement 로만 주입(XSS 방어, innerHTML 금지) — timetable.js 와 같은 규칙.
// 장식은 보드를 다시 그릴 때마다(데이터 폴링 · 1분 틱 재렌더) 새로 만들어지므로, 상태는 DOM 이 아니라 시각(scheduled_start / actual_start)으로 계산한다.
//
//  순수 함수(DOM 없음): kingTarget · lateStage · phaseOf · speech · blockLabel · mmss  — king.selfcheck.mjs

export const KING_KEY = "nonoka";
const MIN = 60000;
export const ARRIVE_MS = 3800;              // 입장 연출 길이 — (v4.5.8) 끝나면 바로 서서히 평소 라이브 모습으로(전엔 「입장 후」 모습을 actual_start + 1분까지 유지)
export const LEAVE_MS = 1200;               // (v4.5.1) 복귀(퇴장) 연출 길이 — king.css 의 --k-leave(1.2s) 와 같아야 한다
export const MAX_LATE_MS = 3 * 3600000;     // 예고는 예정 시각 + 3h 안에 정리되므로 그 이상은 꾸미지 않음
export const ARRIVE_MIN_LATE_MS = MIN;      // 이만큼 이상 늦게 시작해야 「지각 후 입장」 연출을 한다
const STAGE_EDGES = [3 * MIN, 5 * MIN, 10 * MIN, 20 * MIN];   // 1단계 끝 · 2단계 끝 · 3단계 끝 · 4단계 끝
const KICK = "대신이 고하오";
export const KING_RING_LATE = ["행차", "준비 중"];   // (v4.5.8) 오늘 카드 예정 링이 시작 시각을 넘겼을 때 「지각」 대신 쓰는 2단 글자(timetable.updateRing)

/* ── 순수 로직 ─────────────────────────────────────────────────────── */
export function kingTarget(item) {
  return !!item && item.channel_key === KING_KEY && !item.time_tbd;
}

/** 지각 시간(ms) → 0(연출 없음) | 1~5 */
export function lateStage(lateMs) {
  if (!isFinite(lateMs) || lateMs <= 0 || lateMs > MAX_LATE_MS) return 0;
  let s = 1;
  for (const edge of STAGE_EDGES) if (lateMs >= edge) s++;
  return s;
}

export function mmss(ms) {
  const s = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(s / 60), r = s % 60;
  return `${m < 10 ? "0" : ""}${m}:${r < 10 ? "0" : ""}${r}`;
}

/** (v4.5.8) 약속 시각(ms) = scheduled_start 와 announced_start(흡수된 예고의 시각) 중 이른 것 */
export function promisedStart(item) {
  const sched = Date.parse(item.scheduled_start);
  const ann = Date.parse(item.announced_start);
  return isFinite(ann) && ann < sched ? ann : sched;
}

/**
 * 이 항목이 지금 어떤 국면인가. playedAt = 이 페이지가 이 항목의 입장 연출을 시작한 시각(아직이면 undefined)
 *  { phase: "wait", stage, late }                       예정 시각이 지난 예고(upcoming) — 지각은 화면에 보이는 scheduled_start 기준
 *  { phase: "live", waited, since }                     약속 시각보다 1분 이상 늦게 입장한 라이브 — 아직 재생 안 했거나 재생한 지 ARRIVE_MS 안
 *  null                                                  연출 대상 아님 / 끝남
 */
export function phaseOf(item, state, nowMs, playedAt) {
  if (!kingTarget(item)) return null;
  const sched = Date.parse(item.scheduled_start);
  if (!isFinite(sched)) return null;
  if (state === "upcoming") {
    const late = nowMs - sched;
    const stage = lateStage(late);
    return stage ? { phase: "wait", stage, late } : null;
  }
  if (state === "live") {
    const actual = Date.parse(item.actual_start);
    if (!isFinite(actual)) return null;
    const waited = actual - promisedStart(item);
    if (waited < ARRIVE_MIN_LATE_MS) return null;
    const since = Math.max(0, nowMs - actual);
    if (playedAt != null && nowMs - playedAt >= ARRIVE_MS) return null;   // (v4.5.8) 이 페이지에서 한 번 재생했으면 끝
    return { phase: "live", waited, since };
  }
  return null;
}

/** 대신의 말. 조각: ["k", 머리말] ["b", 굵은 글, "big"?] ["s", 작은 글] ["c"](대기 시간 카운터) */
export function speech(kind, stage, waitedMs) {
  if (kind === "arrive") return [["k", KICK], ["b", "전하 납시오!", "big"], ["s", `그대들이 +${mmss(waitedMs)} 기다린 끝에 납시었소!`]];
  if (stage === 1) return [["k", KICK], ["b", "전하께서 곧 납시오~"]];
  if (stage === 2) return [["k", KICK], ["b", "전하께서 곧 행차할 것이오!"], ["s", "잠시 대기들 하시오!"]];
  if (stage === 3) return [["k", KICK], ["b", "행차가 길어지는구려. 자리를 뜨지 마시오!"], ["s", "그대들이 기다린 시간"], ["c"]];
  if (stage === 4) return [["k", KICK], ["b", "전하께서는 아직이시오. 이 대신이 알아보는 중이오."], ["s", "그대들이 기다린 시간"], ["c"]];
  return [["k", KICK], ["b", "전하께서는 아직 납시지 않으셨소. 졸고 있는 자들은 정신들 차리시오!"], ["s", "그대들이 기다린 시간"], ["c"]];
}

/** PC 블록의 상태 글자(원래 「지각」 자리) */
export function blockLabel(stage, lateMs) {
  return stage <= 2 ? "행차 준비" : `대기 +${mmss(lateMs)}`;
}

/* ── DOM ──────────────────────────────────────────────────────────── */
const SVG_NS = "http://www.w3.org/2000/svg";
const played = new Map();                       // 항목 → 입장 연출을 시작한 시각 (이 페이지에서 한 번만 재생)
let uid = 0;

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}
function sv(tag, attrs, parent) {
  const e = document.createElementNS(SVG_NS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(e);
  return e;
}
const reduceMotion = () => typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
const keyOf = (item) => item.video_id || item.id || item.scheduled_start;

const CROWN_D = "M4 44 L9 14 L22 28 L34 6 L46 28 L59 14 L64 44 Z";

/* 왕관: 은빛(.kg-cs) 과 금빛(.kg-cg) 두 겹. 입장 순간 은빛이 금빛으로 바뀐다 */
function crownSvg() {
  const u = ++uid;
  const svg = sv("svg", { viewBox: "0 0 68 56", "aria-hidden": "true" });
  const defs = sv("defs", {}, svg);
  const grad = (id, stops) => {
    const g = sv("linearGradient", { id: `${id}${u}`, x1: 0, y1: 0, x2: id === "kgl" ? 1 : 0, y2: id === "kgl" ? 0 : 1 }, defs);
    for (const [o, c, op] of stops) sv("stop", { offset: o, "stop-color": c, ...(op != null ? { "stop-opacity": op } : {}) }, g);
  };
  grad("kgg", [[0, "#ffe49a"], [.55, "#e8b84a"], [1, "#9a6d1c"]]);
  grad("kgs", [[0, "#e3e8f1"], [.55, "#a9b1c1"], [1, "#6b7384"]]);
  grad("kgl", [[0, "#fff", 0], [.5, "#fff", .9], [1, "#fff", 0]]);
  const cp = sv("clipPath", { id: `kgc${u}` }, defs);
  sv("path", { d: CROWN_D }, cp);
  sv("rect", { x: 4, y: 46, width: 60, height: 8, rx: 2 }, cp);

  const part = (cls, fill, tip, jewels) => {
    const g = sv("g", { class: cls }, svg);
    sv("path", { d: CROWN_D, fill: `url(#${fill}${u})` }, g);
    sv("rect", { x: 4, y: 46, width: 60, height: 8, rx: 2, fill: `url(#${fill}${u})` }, g);
    [[9, 12, 3], [34, 4, 3.4], [59, 12, 3]].forEach(([x, y, r]) => sv("circle", { cx: x, cy: y, r, fill: tip }, g));
    [[34, 36, 4.2], [18, 38, 3], [50, 38, 3]].forEach(([x, y, r], i) => sv("circle", { cx: x, cy: y, r, fill: jewels[i] }, g));
    return g;
  };
  part("kg-cs", "kgs", "#dfe4ee", ["#8a93a6", "#7d879b", "#7d879b"]);
  const gold = part("kg-cg", "kgg", "#ffe49a", ["#d1304f", "#5aa7ff", "#5aa7ff"]);
  const clip = sv("g", { "clip-path": `url(#kgc${u})` }, gold);
  sv("rect", { class: "kg-sweep", x: 0, y: 0, width: 16, height: 56, fill: `url(#kgl${u})`, transform: "skewX(-18)" }, clip);
  return svg;
}
function crownEl(cls) {
  const wrap = el("span", cls);
  wrap.appendChild(el("span", "kg-halo"));
  const orbit = el("span", "kg-orbit");
  for (let k = 0; k < 6; k++) { const i = el("i"); i.style.setProperty("--a", String(k * 60)); orbit.appendChild(i); }
  wrap.appendChild(orbit);
  const inner = el("span", "kg-crown-in");
  inner.appendChild(crownSvg());
  wrap.appendChild(inner);
  return wrap;
}
function sparks(n, wrapCls, dist, ratio) {
  const w = el("span", wrapCls);
  for (let i = 0; i < n; i++) {
    const a = (i / n) * Math.PI * 2 + 0.3, d = dist + (i % 3) * (dist * 0.3);
    const s = el("i");
    s.style.setProperty("--j", String(i));
    s.style.setProperty("--dx", `${Math.round(Math.cos(a) * d)}px`);
    s.style.setProperty("--dy", `${Math.round(Math.sin(a) * d * ratio)}px`);
    w.appendChild(s);
  }
  return w;
}

const COURT = [[12, 6, 1], [27, 30, 0.78], [88, 6, 1], [73, 30, 0.78]];
const FIDGET = [2.4, 3.1, 2.7, 3.6], FIDGET_DELAY = [0, -0.8, -1.5, -0.4];
const MOTES = [[20, 14, 5.5, 0, 8], [36, 30, 7, 1.2, -10], [52, 22, 6, 2.4, 12], [66, 40, 8, 0.6, -8], [80, 18, 6.5, 1.8, 10]];

/* 무대(모바일 카드 · PC 팝업 썸네일 위). 16:9 영역을 가득 채운다 */
function sceneEl() {
  const sc = el("div", "kg-scene");
  sc.setAttribute("aria-hidden", "true");
  const add = (cls) => { const e = el("div", cls); sc.appendChild(e); return e; };
  add("kg-hall");
  add("kg-rays");
  add("kg-rays kg-gold");
  add("kg-carpet");
  add("kg-dais");
  add("kg-pelmet");
  add("kg-drape kg-l");
  add("kg-drape kg-r");
  COURT.forEach(([x, y, scale], i) => {
    const sub = el("i", "kg-sub");
    sub.style.cssText = `--x:${x}%;--y:${y}%;--sc:${scale};--i:${i};--fd:${FIDGET[i]}s;--fl:${FIDGET_DELAY[i]}s`;
    const inn = el("i", "kg-in");
    inn.append(el("b", "kg-head"), el("b", "kg-torso"));
    sub.appendChild(inn);
    sc.appendChild(sub);
  });
  [["z", "13px", "0"], ["z", "16px", "8px"], ["Z", "19px", "16px"]].forEach(([t, fs, ml], k) => {
    const z = el("span", "kg-zz", t);
    z.style.cssText = `--k:${k};font-size:${fs};margin-left:${ml}`;
    sc.appendChild(z);
  });
  const motes = add("kg-motes");
  MOTES.forEach(([x, y, d, dl, dx]) => {
    const m = el("i");
    m.style.cssText = `--mx0:${x}%;--my0:${y}%;--md:${d}s;--mdl:${dl}s;--mdx:${dx}px`;
    motes.appendChild(m);
  });
  add("kg-veil");
  sc.appendChild(crownEl("kg-crown"));
  add("kg-flare");
  sc.appendChild(sparks(10, "kg-sparks", 70, 0.8));
  return sc;
}

/* 대신의 말 상자 */
function writeMsg(root, spec, countMs) {
  const k = root.__king;
  const box = k.msg;
  box.textContent = "";
  k.count = null;
  for (const p of spec) {
    let n;
    if (p[0] === "k") n = el("span", "king-kick", p[1]);
    else if (p[0] === "b") n = el("b", p[2] === "big" ? "king-big" : "", p[1]);
    else if (p[0] === "s") n = el("small", "", p[1]);
    else { n = el("span", "king-count", `+${mmss(countMs)}`); k.count = n; }
    box.appendChild(n);
  }
}

/* ── 한 장식(root = 블록 / 팝업 / 카드)의 상태 ───────────────────────── */
function setStage(root, stage) {
  for (let s = 1; s <= 5; s++) root.classList.toggle(`k-s${s}`, s <= stage);
}

function begin(root, kind, entry, state) {
  const p = phaseOf(entry.item, state, Date.now(), played.get(keyOf(entry.item)));
  if (!p) return null;
  root.__king = { kind, item: entry.item, state, mode: null, stage: 0, nodes: [], msg: null, count: null, label: null, labelOrig: "" };
  root.dataset.king = kind;
  root.classList.add("k-on");
  return p;
}

/* 국면을 화면에 반영. 처음 만들 때와 틱에서 단계가 바뀔 때 부른다 */
function applyPhase(root, p) {
  const k = root.__king;
  if (p.phase === "wait") {
    if (k.stage === p.stage && k.mode === "wait") return;
    k.mode = "wait"; k.stage = p.stage;
    setStage(root, p.stage);
    if (k.msg) writeMsg(root, speech("wait", p.stage), p.late);
    if (k.label) k.label.textContent = blockLabel(p.stage, p.late);
    return;
  }
  // 라이브(지각 후 입장) — (v4.5.8) 이 페이지에서 처음 그릴 때 입장 연출을 한 번 재생하고 끝나면 바로 걷어낸다
  if (k.mode === "arrive" || k.mode === "live") return;
  const key = keyOf(k.item);
  const now = Date.now();
  k.stage = 3;
  setStage(root, 3);                         // 장막 · 신하 · 카펫이 갖춰진 상태에서 입장
  if (k.label) k.label.textContent = k.labelOrig;
  // (v4.5.8) 탭이 숨겨져 있으면 재생을 미룬다 — 백그라운드 탭에서 폴링으로 라이브를 받았을 때 아무도 안 보는 사이 끝나 버리지 않게.
  // 틱이 탭이 보이는 순간 다시 부른다
  if (!played.has(key) && typeof document !== "undefined" && document.hidden) { k.mode = "await"; return; }
  if (!played.has(key)) played.set(key, now);
  const arriving = !reduceMotion() && now - played.get(key) < ARRIVE_MS;
  if (arriving) {
    k.mode = "arrive";
    // 두 프레임 뒤에 arrive 를 붙여야 장막이 닫힌 상태에서 열리는 전환이 보인다. 걷어내기 타이머는 클래스가 실제로 붙은 순간부터 잰다
    requestAnimationFrame(() => requestAnimationFrame(() => {
      if (!root.isConnected || root.__king !== k || k.mode !== "arrive") return;
      root.classList.add("k-arrive");
      setTimeout(() => { if (root.isConnected && root.__king === k) leave(root); }, ARRIVE_MS);
    }));
  } else {
    // 모션 줄이기(또는 재생 도중 다시 그려짐 — 재생 시작 후 ARRIVE_MS 안) — 금빛 「입장 후」 모습을 남은 시간만 보이고 틱이 걷어낸다
    k.mode = "live";
    root.classList.add("k-live");
  }
  if (k.msg) writeMsg(root, speech("arrive", 0, p.waited), p.waited);
}

/* 팝업이 블록 위쪽에 놓였으면(timetable.js 가 data-anchor-bottom 에 문서 좌표의 아래 가장자리를 적어 둔다) 높이가 줄어도 블록에 붙어 있게 top 을 다시 맞춘다 */
function repin(root) {
  const a = parseFloat(root.dataset.anchorBottom);
  if (isFinite(a)) root.style.top = `${a - root.offsetHeight}px`;
}

/* 연출을 걷어내고 평소 모습으로 */
function finish(root) {
  const k = root.__king;
  if (!k) return;
  if (k.label) k.label.textContent = k.labelOrig;
  for (const n of k.nodes) n.remove();
  root.classList.remove("k-on", "k-arrive", "k-live", "k-leave", "k-s1", "k-s2", "k-s3", "k-s4", "k-s5", "k-blk", "k-card", "k-pop");
  delete root.dataset.king;
  delete root.__king;
  repin(root);
}

/* 연출을 서서히 걷어낸다: .k-leave 로 무대 · 장식이 옅어지고 대신의 말 칸이 접힌 뒤(king.css) 장식 DOM 을 지운다.
   모션 줄이기 설정이면 바로 지운다. 링크 · 도넛 등 장식이 아닌 요소는 건드리지 않으므로 클릭 · 카운트다운은 그대로다 */
function leave(root) {
  const k = root.__king;
  if (!k || k.leaving) return;
  k.leaving = true;
  if (reduceMotion()) { finish(root); return; }
  if (k.msg) { k.msg.style.maxHeight = `${k.msg.offsetHeight}px`; void k.msg.offsetHeight; }   // 접히기 시작 높이를 px 로 고정해야 max-height 전환이 된다
  root.classList.add("k-leave");
  const follow = () => { if (root.isConnected && root.__king === k) { repin(root); requestAnimationFrame(follow); } };
  follow();
  setTimeout(() => { if (root.__king === k) finish(root); }, LEAVE_MS + 150);
}

/* ── 1초 틱: 단계 전환 · 대기 시간 카운터 · 입장 연출 뒤 걷어내기(leave — 보통은 입장 타이머가 먼저 부른다). 꾸밀 대상이 화면에 없으면 스스로 멈춘다 ─── */
let timer = 0;
function ensureTicker() {
  if (timer) return;
  timer = setInterval(() => {
    const roots = document.querySelectorAll("[data-king]");
    if (!roots.length) { clearInterval(timer); timer = 0; return; }
    const now = Date.now();
    for (const root of roots) {
      const k = root.__king;
      if (!k) continue;
      const p = phaseOf(k.item, k.state, now, played.get(keyOf(k.item)));
      if (!p) { leave(root); continue; }
      if (p.phase === "live") {
        if (k.mode === "await") applyPhase(root, p);   // (v4.5.8) 숨겨진 탭에서 미뤄 둔 입장 연출 — 탭이 보이면 시작
      } else {
        applyPhase(root, p);
        if (k.count) k.count.textContent = `+${mmss(p.late)}`;
        if (k.label && k.stage >= 3) k.label.textContent = blockLabel(k.stage, p.late);
      }
    }
  }, 1000);
}

/* ── 모바일 오늘 카드 ──────────────────────────────────────────────── */
export function decorateCard(card, thumb, main, entry, state) {
  const p = begin(card, "card", entry, state);
  if (!p) return;
  const k = card.__king;
  card.classList.add("k-card");
  const scene = sceneEl();
  thumb.insertBefore(scene, thumb.firstChild);          // LIVE · 합동 아이콘보다 아래
  const msg = el("div", "king-msg");
  main.appendChild(msg);
  k.nodes.push(scene, msg);
  k.msg = msg;
  applyPhase(card, p);
  ensureTicker();
}

/* ── PC 블록 팝업 (무대 + 대신의 말) ──────────────────────────────────── */
export function decoratePopup(pop, img, body, entry, state) {
  const p = begin(pop, "popup", entry, state);
  if (!p) return;
  const k = pop.__king;
  pop.classList.add("k-pop");
  const scene = sceneEl();
  img.insertBefore(scene, img.firstChild);
  const msg = el("div", "king-msg");
  body.appendChild(msg);
  k.nodes.push(scene, msg);
  k.msg = msg;
  applyPhase(pop, p);
  ensureTicker();
}

/* ── PC 타임테이블 블록 (작은 신호만: 왕관 · 카펫 띠 · 상태 글자) ──────────── */
export function decorateBlock(blk, entry, state) {
  const p = begin(blk, "block", entry, state);
  if (!p) return;
  const k = blk.__king;
  blk.classList.add("k-blk");
  const th = blk.querySelector(".tt-blk__th");
  if (!th) { finish(blk); return; }
  const crown = crownEl("kb-crown");
  const zz = el("span", "kb-zz", "z");
  zz.style.setProperty("--k", "0");
  const flare = el("span", "kb-flare");
  const sp = sparks(6, "kb-sparks", 22, 0.8);
  th.append(crown, zz, flare, sp);
  const carpet = el("span", "kb-carpet");
  blk.appendChild(carpet);
  k.nodes.push(crown, zz, flare, sp, carpet);
  const label = blk.querySelector(".tt-blk__rel");     // 예고 블록의 「지각」 자리 (라이브 블록엔 없음)
  if (label) { k.label = label; k.labelOrig = label.textContent; }
  applyPhase(blk, p);
  ensureTicker();
}
