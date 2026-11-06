// bgconsole.js — (bg-dome) UFO 무대 가운데 바닥에 놓인 「조작 콘솔」. 그리는 곳 = bgdomegl.js 의 공중 무늬 층(.bgdm-air).
// 셰이더가 아니라 SVG 두 장을 3D 투영해 얹는다(셰이더 비용 0, 운영자 11-06 「제안대로」):
//   ① 바닥 무늬(받침 고리 · 파동) = 바닥 평면(y = 0)의 정사각형 → 화면 사각형으로 원근 사상(CSS matrix3d)
//   ② 몸체 · 홀로그램 · 빛기둥 = 무대 중심에 세운 세로 판(카메라 오른쪽 방향 × 세계 위쪽)을 같은 방식으로 사상
// 모양 · 움직임 정본 = devpapers ref/bg-dome/ufo-panel/Approach.dc.html(홀로그램 깜빡임 · 주사선 · 빛기둥 맥동 · 받침 파동 · 상태등).
// 모든 SVG 는 고정 그림이라 createElementNS 로 만든다(데이터 주입 없음).

const NS = "http://www.w3.org/2000/svg";

// 세계 크기(돔 반지름 = 1, 눈 높이 0.24). 폰에서 만져 보고 조정할 값.
const FLOOR_HALF = 0.15;            // 바닥 무늬 정사각형 반 변
const STAND_W = 0.132;              // 세로 판 폭(SVG 110 단위)
const STAND_VB = [140, 455, 110, 160];   // 세로 판 SVG viewBox — 아래 끝(y 615)이 바닥
const STAND_U = STAND_W / STAND_VB[2];   // SVG 1 단위 = 세계 길이
const STAND_H = STAND_VB[3] * STAND_U;
const BOX = 200;                    // 두 SVG 의 CSS 크기(px, 사상 전) — 정사각 · 세로 판 모두 이 폭

function el(tag, attrs, kids) {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (kids) for (const c of kids) e.appendChild(c);
  return e;
}
const anim = (attr, values, dur) => el("animate", { attributeName: attr, values, dur, repeatCount: "indefinite" });

function floorSvg() {
  // viewBox −100 … 100 = 세계 ±FLOOR_HALF. 위(−y) = 세계 +z 쪽이 아니라 「사각형 꼭짓점 순서」로 맞춘다(아래 place 참고)
  return el("svg", { viewBox: "-100 -100 200 200", width: BOX, height: BOX, class: "bgcs-floor", "aria-hidden": "true" }, [
    el("defs", {}, [
      el("radialGradient", { id: "bgcs-glow" }, [
        el("stop", { offset: "0", "stop-color": "#4fe3ff", "stop-opacity": ".34" }),
        el("stop", { offset: ".55", "stop-color": "#ff6fb5", "stop-opacity": ".12" }),
        el("stop", { offset: "1", "stop-color": "#ff6fb5", "stop-opacity": "0" }),
      ]),
    ]),
    el("circle", { r: "98", fill: "url(#bgcs-glow)" }),
    el("circle", { r: "78", fill: "none", stroke: "#8a74d6", "stroke-opacity": ".45", "stroke-width": "1.2" }),
    el("circle", { r: "56", fill: "none", stroke: "#4fe3ff", "stroke-opacity": ".55", "stroke-width": "1.4", "stroke-dasharray": "6 5" }),
    el("circle", { r: "30", fill: "#120e26", stroke: "#4fe3ff", "stroke-opacity": ".75", "stroke-width": "1.6" }),
    // 받침 파동 — 고리가 퍼지며 옅어진다(Approach.dc.html 의 rx 34 → 44 를 원 반지름으로)
    el("circle", { r: "30", fill: "none", stroke: "#ff6fb5", "stroke-width": "1.6" }, [anim("r", "30;62;30", "2.4s"), anim("stroke-opacity", ".7;0;.7", "2.4s")]),
  ]);
}

function standSvg() {
  const [x, y, w, h] = STAND_VB;
  return el("svg", { viewBox: `${x} ${y} ${w} ${h}`, width: BOX, height: BOX * h / w, class: "bgcs-stand", "aria-hidden": "true" }, [
    el("path", { class: "bgcs-beam", d: "M168 548 L146 462 L244 462 L222 548 Z", fill: "#4fe3ff", "fill-opacity": ".09" }),
    el("path", { d: "M175 612 L180 580 L210 580 L215 612 Z", fill: "#1a1436", stroke: "#4fe3ff", "stroke-opacity": ".55" }),
    el("g", { class: "bgcs-holo" }, [
      el("path", { d: "M160 578 L230 578 L222 548 L168 548 Z", fill: "#4fe3ff", "fill-opacity": ".22", stroke: "#4fe3ff", "stroke-width": "1.5" }),
      el("g", { stroke: "#bff6ff", "stroke-opacity": ".8", "stroke-width": "1" }, [
        el("path", { d: "M174 570 H192" }), el("path", { d: "M172 562 H206" }), el("path", { d: "M176 555 H200" }),
      ]),
      el("rect", { x: "166", y: "549", width: "58", height: "1.6", fill: "#ffffff", "fill-opacity": ".7" }, [anim("y", "549;576;549", "2.2s")]),
    ]),
    el("circle", { cx: "214", cy: "566", r: "3", fill: "#ff6fb5" }, [anim("fill-opacity", "1;.2;1", "1.2s")]),
  ]);
}

/** 단위 정사각형 (0,0)(1,0)(1,1)(0,1) → 화면 네 점 사상(투영 변환) → w×h 상자용 CSS matrix3d. */
export function quadMatrix(p, w, h) {
  const [x0, y0] = p[0], [x1, y1] = p[1], [x2, y2] = p[2], [x3, y3] = p[3];
  const dx1 = x1 - x2, dx2 = x3 - x2, dx3 = x0 - x1 + x2 - x3;
  const dy1 = y1 - y2, dy2 = y3 - y2, dy3 = y0 - y1 + y2 - y3;
  const den = dx1 * dy2 - dx2 * dy1;
  if (Math.abs(den) < 1e-9) return null;
  const g = (dx3 * dy2 - dx2 * dy3) / den, hh = (dx1 * dy3 - dx3 * dy1) / den;
  const a = x1 - x0 + g * x1, b = x3 - x0 + hh * x3, d = y1 - y0 + g * y1, e = y3 - y0 + hh * y3;
  const m = [a / w, d / w, 0, g / w, b / h, e / h, 0, hh / h, 0, 0, 1, 0, x0, y0, 0, 1];
  return `matrix3d(${m.map((v) => +v.toPrecision(7)).join(",")})`;
}

/**
 * 콘솔을 만든다. place(project, B) 를 프레임마다 부른다 — project(world) = [화면 x, y, 깊이 z] (z ≤ 0 이면 뒤).
 * B.right = 카메라 오른쪽 방향(수평). 보이지 않을 때는 setVisible(false).
 */
export function createConsole(layer) {
  const root = document.createElement("div");
  root.className = "bgcs";
  root.hidden = true;
  const floor = floorSvg(), stand = standSvg();
  root.appendChild(floor);
  root.appendChild(stand);
  layer.appendChild(root);
  const standBoxH = BOX * STAND_VB[3] / STAND_VB[2];
  // bgdeco.css 의 `#bgdeco svg { width: 100%; height: 100% }` 를 이겨야 사상 기준 크기가 맞는다
  floor.style.width = floor.style.height = BOX + "px";
  stand.style.width = BOX + "px"; stand.style.height = standBoxH + "px";
  let visible = false;

  function put(node, world, w, h) {
    const p = [];
    for (const q of world) {
      const s = project(q);
      if (!s || s[2] < 0.03) { node.style.visibility = "hidden"; return; }
      p.push(s);
    }
    const m = quadMatrix(p, w, h);
    if (!m) { node.style.visibility = "hidden"; return; }
    node.style.visibility = "";
    node.style.transform = m;
  }
  let project = null;

  return {
    setVisible(on) {
      if (on === visible) return;
      visible = on;
      if (on) { root.hidden = false; requestAnimationFrame(() => root.classList.add("is-on")); }
      else { root.classList.remove("is-on"); root.hidden = true; }
    },
    place(projectFn, B) {
      if (!visible) return;
      project = projectFn;
      const f = FLOOR_HALF;
      // 바닥: SVG 왼쪽 위 = 화면 쪽에서 본 왼쪽 먼 모서리가 되게 카메라 오른쪽 · 앞 방향으로 잡는다(무늬가 원이라 회전은 상관없음)
      const r = [B.right[0], 0, B.right[2]], fw = [-B.right[2], 0, B.right[0]];
      const at = (u, v) => [r[0] * u + fw[0] * v, 0, r[2] * u + fw[2] * v];
      put(floor, [at(-f, f), at(f, f), at(f, -f), at(-f, -f)], BOX, BOX);
      // 세로 판: 아래 끝 = 바닥, 가운데 = 무대 중심
      const hw = STAND_W / 2, top = STAND_H - 3 * STAND_U;   // viewBox 아래 3 단위(612 → 615)는 바닥 밑 여백
      const sp = (u, y) => [r[0] * u, y, r[2] * u];
      put(stand, [sp(-hw, top), sp(hw, top), sp(hw, top - STAND_H), sp(-hw, top - STAND_H)], BOX, standBoxH);
    },
  };
}
