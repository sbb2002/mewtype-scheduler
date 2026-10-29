// bgdeco.js — (v4.9.8) 배경 장식. 화면 뒤에 분홍 → 파랑 옅은 그라데이션 톤을 깔고, 로고 도형 장식 11개를 흩뿌려 느리게 띄운다.
// 폰을 흔들면(devicemotion) 장식마다 제각각 튀어 나가 부딪히며 회전한다. 순수 로직 · 물리는 bglogic.js, 색 · 투명도 · 떠다니는 모션은 css/bgdeco.css.
//
// 그라데이션 비율 = 로고(위 약 60% 분홍 → 아래로 파랑). 도형 하나하나에도 같은 비율을 걸고, 돌아도 화면 기준 위 분홍 · 아래 파랑이 유지되게
// gradientTransform 을 매 프레임 반대로 돌린다. 데이터는 전혀 받지 않는 장식이라 접근성 트리에서 숨긴다(aria-hidden).

import { layout, scribblePath, makeBody, impulse, step, shakePower, SHAKE_GAP_MS } from "./bglogic.js";

const NS = "http://www.w3.org/2000/svg";
const RAD2DEG = 180 / Math.PI;
const GRAD_SPLIT = 0.6;       // 로고 비율: 위 60% 까지 분홍, 그 아래로 파랑
const REBUILD_MS = 200;       // 크기 바뀐 뒤 다시 그리기까지 기다림(연속 resize 합치기)
const REBUILD_DH = 150;       // 높이만 이만큼 이상 바뀌면 다시 그림 — 모바일 주소창이 나타나고 사라지는 정도는 무시

let host = null, svg = null, items = [], bodies = [], els = [];
let W = 0, H = 0, raf = 0, tPrev = 0, lastShake = 0, rebuildT = 0, sensorOn = false;
const reduce = () => window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function sv(tag, attrs, parent) {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(e);
  return e;
}

function stops(grad, split) {
  sv("stop", { offset: "0", class: "bgd-pink" }, grad);
  sv("stop", { offset: String(split), class: "bgd-pink" }, grad);
  sv("stop", { offset: "1", class: "bgd-blue" }, grad);
}

/** 장식 하나의 도형 (장식 중심 = 0,0 이 아니라 화면 좌표 x,y) */
function shape(it, grad, parent) {
  const { x, y, u, kind, ang } = it;
  const common = { transform: `rotate(${ang} ${x} ${y})`, class: "bgd-shape" };
  const line = { ...common, fill: "none", stroke: `url(#${grad})`, "stroke-width": String(Math.max(3.5, u * 0.2)), "stroke-linecap": "round", "stroke-linejoin": "round" };
  if (kind === "ring") return sv("circle", { ...line, cx: x, cy: y, r: u }, parent);
  if (kind === "tri") return sv("polygon", { ...line, points: `${x},${y - u} ${x + u},${y + u * 0.8} ${x - u},${y + u * 0.8}` }, parent);
  if (kind === "wave") return sv("path", { ...line, d: `M${x - u * 1.8} ${y} q${u * 0.9} ${-u * 1.1} ${u * 1.8} 0 t${u * 1.8} 0` }, parent);
  if (kind === "dot") return sv("circle", { ...common, cx: x, cy: y, r: u * 0.45, fill: `url(#${grad})` }, parent);
  return sv("rect", { ...common, x: x - u * 0.75, y: y - u * 0.75, width: u * 1.5, height: u * 1.5, rx: 3, fill: `url(#${grad})` }, parent);   // gem(마름모)
}

function build() {
  W = window.innerWidth; H = window.innerHeight;
  if (svg) svg.remove();
  svg = sv("svg", { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "xMidYMid slice", focusable: "false" });
  const defs = sv("defs", {}, svg);
  const tone = sv("linearGradient", { id: "bgd-tone", x1: "0", y1: "0", x2: "0", y2: "1" }, defs);
  stops(tone, GRAD_SPLIT);
  sv("rect", { width: W, height: H, fill: "url(#bgd-tone)", class: "bgd-tone" }, svg);   // 바탕 톤(투명도는 css 가 테마별로)

  items = layout(W, H);
  bodies = items.map((it) => makeBody(it, W, H));
  els = items.map((it, i) => {
    const gid = `bgd-g${i}`, ext = it.u * 1.9;
    const g = sv("linearGradient", { id: gid, gradientUnits: "userSpaceOnUse", x1: it.x, y1: it.y - ext, x2: it.x, y2: it.y + ext, gradientTransform: `rotate(${-it.ang} ${it.x} ${it.y})` }, defs);
    stops(g, GRAD_SPLIT);
    const phys = sv("g", { class: "bgd-sh" }, svg);                       // 흔들기 물리가 움직이는 층
    phys.style.transformOrigin = `${it.x}px ${it.y}px`;
    const fl = sv("g", { class: "bgd-fl" }, phys);                        // 평소 떠다니는 층(css 애니메이션)
    fl.style.setProperty("--dx", it.dx.toFixed(1) + "px");
    fl.style.setProperty("--dy", it.dy.toFixed(1) + "px");
    fl.style.setProperty("--dur", it.dur.toFixed(1) + "s");
    fl.style.setProperty("--delay", it.delay.toFixed(1) + "s");
    shape(it, gid, fl);
    return { phys, g };
  });

  const lg = sv("linearGradient", { id: "bgd-line", gradientUnits: "userSpaceOnUse", x1: 0, y1: 0, x2: 0, y2: H }, defs);   // 아래 긴 낙서 선: 화면 높이 기준 같은 비율
  stops(lg, GRAD_SPLIT);
  sv("path", { d: scribblePath(W, H), fill: "none", stroke: "url(#bgd-line)", "stroke-width": "5", "stroke-linecap": "round", "stroke-linejoin": "round", class: "bgd-shape" }, svg);
  host.appendChild(svg);
}

function paint() {
  bodies.forEach((b, i) => {
    const e = els[i];
    e.phys.style.transform = `translate(${b.ox.toFixed(1)}px, ${b.oy.toFixed(1)}px) rotate(${(b.th * RAD2DEG).toFixed(1)}deg)`;
    e.g.setAttribute("gradientTransform", `rotate(${(-items[i].ang - b.th * RAD2DEG).toFixed(1)} ${items[i].x} ${items[i].y})`);   // 돌아도 그라데이션은 위 분홍 · 아래 파랑
  });
}

function frame(t) {
  const dt = Math.min(0.05, (t - tPrev) / 1000 || 0.016);
  tPrev = t;
  const moving = step(bodies, dt);
  paint();
  raf = moving ? requestAnimationFrame(frame) : 0;
}

/** 흔들기 — power 는 shakePower() 값(기본 1). 연속으로 불러도 속도가 쌓인다. */
export function shake(power = 1) {
  if (!svg || reduce()) return;
  const now = performance.now();
  if (now - lastShake < SHAKE_GAP_MS) return;
  lastShake = now;
  bodies.forEach((b) => impulse(b, power));
  if (!raf) { tPrev = now; raf = requestAnimationFrame(frame); }
}

function onMotion(ev) {
  const p = shakePower(ev);
  if (p > 0) shake(p);
}

/** 센서 켜기. iOS 는 사용자 동작 안에서 권한을 물어야 해서 첫 터치 때 한 번 요청한다. 안드로이드 · 데스크톱은 바로 듣는다(데스크톱은 이벤트가 안 온다). */
function enableSensor() {
  if (sensorOn || typeof DeviceMotionEvent === "undefined") return;
  const attach = () => { sensorOn = true; window.addEventListener("devicemotion", onMotion); };
  if (typeof DeviceMotionEvent.requestPermission !== "function") { attach(); return; }
  const ask = () => {
    document.removeEventListener("pointerup", ask, true);
    DeviceMotionEvent.requestPermission().then((r) => { if (r === "granted") attach(); }).catch(() => {});   // 거절 · 실패하면 흔들기만 없다
  };
  document.addEventListener("pointerup", ask, true);
}

export function initBgDeco() {
  if (host) return;
  host = document.createElement("div");
  host.id = "bgdeco";
  host.setAttribute("aria-hidden", "true");
  document.body.prepend(host);
  build();
  window.addEventListener("resize", () => {
    clearTimeout(rebuildT);
    rebuildT = setTimeout(() => {
      if (window.innerWidth === W && Math.abs(window.innerHeight - H) < REBUILD_DH) return;
      build();   // 크기가 크게 바뀌면(회전 · 창 크기 조절) 장식 자리를 새로 잡는다
    }, REBUILD_MS);
  });
  if (!reduce()) enableSensor();
}
