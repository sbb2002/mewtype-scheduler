// 세 배경 시험안. 공식 자산 없이 일반 기하 도형으로만 구성한다.
// 고정된 가장자리 구조와 흔들어 흩어지는 조각을 분리해, 흔든 뒤에도 공간이 읽히게 한다.
import { rng } from "./bglogic.js";

const NS = "http://www.w3.org/2000/svg";
function sv(tag, attrs, parent) {
  const e = document.createElementNS(NS, tag);
  for (const [key, value] of Object.entries(attrs)) e.setAttribute(key, value);
  if (parent) parent.appendChild(e);
  return e;
}

function ufo(parent, u) {
  const g = sv("g", { class: "bgv-ufo" }, parent);
  sv("path", { d: `M${-u * .42},0 Q${-u * .4},${-u * .9} ${u * .3},${-u * .5} L${u * .5},0 Z`, class: "bgv-glass" }, g);
  sv("ellipse", { cx: 0, cy: 0, rx: u, ry: u * .27, class: "bgv-solid" }, g);
  for (let i = -1; i <= 1; i++) sv("circle", { cx: i * u * .43, cy: 0, r: u * .07, class: "bgv-port" }, g);
  return g;
}

export function buildVirtualScene(variant, W, H) {
  const phone = W <= 767, edge = phone ? 33 : 25, r = rng(411), items = [], els = [];
  const svg = sv("svg", { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "xMidYMid slice", focusable: "false" });
  const defs = sv("defs", {}, svg);
  const grad = sv("linearGradient", { id: "bgv-spectrum", x1: "0", y1: "0", x2: "1", y2: "1" }, defs);
  [[0,"bgv-pink"],[.36,"bgv-ice"],[.68,"bgv-lilac"],[1,"bgv-pink"]].forEach(([offset, cls]) => sv("stop", { offset, class: cls }, grad));
  sv("rect", { width: W, height: H, class: "bgv-ground" }, svg);
  const fixed = sv("g", { class: "bgv-fixed" }, svg);

  // 물리의 중심은 화면 좌표, 도형은 해당 중심 기준의 로컬 좌표다.
  function piece(x, y, u, draw, index) {
    const it = { x, y, u, ang: 0 };
    const phys = sv("g", { class: "bgv-body" }, svg);
    phys.style.transformOrigin = `${x}px ${y}px`;
    const origin = sv("g", { transform: `translate(${x} ${y})` }, phys);
    const fl = sv("g", { class: `bgv-piece bgv-piece--${index % 3}` }, origin);
    draw(fl, u, index);
    items.push(it); els.push({ phys });
  }

  if (variant === "a") {
    // 넓은 프리즘 면의 교차가 16px 상단과 세로 틈을 연속으로 잇는다.
    for (let side = 0; side < 2; side++) {
      const rail = sv("g", { transform: side ? `translate(${W} 0) scale(-1 1)` : "" }, fixed);
      for (let i = 0; i < 5; i++) {
        const y = i * H / 4 - 65, span = phone ? 115 : 215;
        sv("polygon", { points: `-30,${y} ${span},${y + 70} ${edge - 9},${y + H / 4 + 48} -30,${y + H / 4 + 90}`, class: `bgv-plane bgv-plane--${(i + side) % 3}` }, rail);
        sv("path", { d: `M-20 ${y + 4} L${span} ${y + 70} L${edge - 9} ${y + H / 4 + 48}`, class: "bgv-seam" }, rail);
      }
    }
    sv("polygon", { points: `0,0 ${W * .65},0 ${W * .38},18 0,9`, class: "bgv-crown" }, fixed);
    sv("path", { d: `M0 ${H - 45} L${W * .38} ${H - 74} L${W * .7} ${H - 43} L${W} ${H - 62}`, class: "bgv-seam" }, fixed);
    for (let i = 0; i < 12; i++) piece(i < 10 ? (i % 2 ? W - edge : edge) : W * (i === 10 ? .29 : .76), i < 10 ? 30 + Math.floor(i / 2) * (H - 95) / 5 : H - 59, phone ? 13 + r() * 7 : 22 + r() * 12, (g, u, n) => {
      sv("polygon", { points: `${-u * .7},${-u} ${u},${-u * .25} ${u * .4},${u} ${-u},${u * .45}`, class: "bgv-shard" }, g);
      sv("path", { d: `M${-u * .7} ${-u} L${u * .4} ${u} L${-u} ${u * .45}`, class: "bgv-shard-edge" }, g);
      g.setAttribute("transform", `rotate(${n * 37})`);
    }, i);
    const light = sv("g", { class: "bgv-rare bgv-refraction" }, svg);
    for (const x of [edge, W - edge]) sv("polygon", { points: `${x - 6},-120 ${x + 9},-80 ${x + 4},40 ${x - 8},0`, class: "bgv-flare" }, light);
  } else if (variant === "b") {
    // 제어 기능처럼 보이는 가짜 문구 대신 프레임·체커·데이터 눈금만 쓴다.
    for (const x of [edge, W - edge]) {
      sv("path", { d: `M${x - 9} 0 V${H * .17} l9 10 V${H * .49} l-9 10 V${H - 40}`, class: "bgv-circuit" }, fixed);
      for (let i = 0; i < 14; i++) sv("path", { d: `M${x - 5} ${20 + i * (H - 80) / 14} h${i % 3 ? 4 : 10}`, class: "bgv-tick" }, fixed);
    }
    for (const [x,y,w,h] of [[-8,8, W * .44,60],[W - 110,H * .34,130,170],[-30,H * .66,110,130],[W * .15,H - 76,W * .71,45]]) sv("path", { d: `M${x + 14} ${y} H${x + w} V${y + h - 14} l-14 14 H${x} V${y + 14} Z`, class: "bgv-frame" }, fixed);
    for (let i = 0; i < (phone ? 18 : 40); i++) {
      const x = i * 16 + 5;
      for (let j = 0; j < 2; j++) if ((i + j) % 2) sv("rect", { x, y: 2 + j * 6, width: 6, height: 6, class: "bgv-check" }, fixed);
    }
    for (let i = 0; i < 12; i++) piece(i < 10 ? (i % 2 ? W - edge : edge) : W * (i === 10 ? .31 : .73), i < 10 ? 85 + Math.floor(i / 2) * (H - 190) / 5 : H - 55, phone ? 10 : 17, (g,u,n) => {
      if (n % 3 === 0) sv("path", { d: `M${-u} ${-u} H${u} V${u * .4} L${u * .4} ${u} H${-u} Z`, class: "bgv-chip" }, g);
      else for (let row = 0; row < 3; row++) for (let col = 0; col < 3; col++) if ((row + col + n) % 3) sv("rect", { x: (col - 1) * u * .65, y: (row - 1) * u * .65, width: u * .5, height: u * .5, class: "bgv-pixel" }, g);
    }, i);
    const scan = sv("g", { class: "bgv-rare bgv-scan" }, svg);
    for (const x of [edge - 7,W - edge - 7]) {
      sv("rect", { x, y: -60, width: 14, height: 50, class: "bgv-scan-tail" }, scan);
      sv("path", { d: `M${x - 5} -9 h24 m-19 4 h14`, class: "bgv-scan-head" }, scan);
    }
  } else {
    // 방사형 광선 없이 타원의 일부와 작은 별로 넓은 우주를 암시한다.
    for (let i = 0; i < (phone ? 48 : 90); i++) {
      const x = r() * W, y = r() * H;
      sv("circle", { cx: x, cy: y, r: i % 7 ? .8 : 1.5, class: i % 4 ? "bgv-star" : "bgv-star bgv-star--accent" }, fixed);
    }
    sv("ellipse", { cx: W * .5, cy: H - 55, rx: W * .7, ry: phone ? 47 : 92, transform: `rotate(-8 ${W * .5} ${H - 55})`, class: "bgv-orbit" }, fixed);
    sv("ellipse", { cx: W + 23, cy: H * .36, rx: phone ? 65 : 115, ry: H * .33, transform: `rotate(12 ${W + 23} ${H * .36})`, class: "bgv-orbit bgv-orbit--far" }, fixed);
    for (let i = 0; i < 10; i++) piece(i < 8 ? (i % 2 ? W - edge : edge) : W * (i === 8 ? .27 : .8), i < 8 ? 52 + Math.floor(i / 2) * (H - 135) / 4 : H - 57, phone ? 11 : 19, (g,u,n) => {
      if (n === 0 || n === 7) ufo(g,u);
      else if (n % 3 === 0) sv("path", { d: `M0 ${-u * .6} L${u * .15} ${-u * .15} L${u * .6} 0 L${u * .15} ${u * .15} L0 ${u * .6} L${-u * .15} ${u * .15} L${-u * .6} 0 L${-u * .15} ${-u * .15} Z`, class: "bgv-spark" }, g);
      else {
        sv("circle", { r: u * .7, class: "bgv-planet" }, g);
        sv("path", { d: `M${-u * .8} ${u * .4} Q${u * .7} ${u * .8} ${u * .85} ${-u * .4} M${-u * .8} ${u * .4} Q${-u * .9} ${-u * .6} ${u * .85} ${-u * .4}`, class: "bgv-planet-ring" }, g);
      }
    }, i);
    const fly = sv("g", { class: "bgv-rare bgv-flyby" }, svg);
    const path = sv("g", { transform: `translate(-45 ${H - 55})` }, fly);
    sv("path", { d: "M-65 3 H-23 M-48 8 H-28", class: "bgv-trail" }, path);
    ufo(path, phone ? 17 : 24);
  }
  return { svg, items, els };
}

/** 페이지 재렌더에도 대응하되, 배경 자체의 속성 변경은 관찰하지 않는다. */
export function observeMemberAccent(host) {
  const colors = { arale: "#efcf58", yuno: "#ff6688", nonoka: "#ffaacc", ritsu: "#6296ec", miyako: "#a28add" };
  const phone = window.matchMedia("(max-width: 767px)");
  let previous = "";
  function update() {
    const active = document.querySelector("#pager-dots .dot--on[data-channel]") || document.querySelector(".lane--active[data-channel]");
    const key = phone.matches ? active?.dataset.channel : "";
    if (key === previous) return;
    previous = key;
    host.style.setProperty("--bgv-accent", colors[key] || "#ff7788");
  }
  for (const id of ["board", "pager-dots"]) {
    const target = document.getElementById(id);
    if (target) new MutationObserver(update).observe(target, { subtree: true, childList: true, attributes: true, attributeFilter: ["class", "data-channel"] });
  }
  phone.addEventListener("change", update);
  update();
}
