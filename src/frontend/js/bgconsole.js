// bgconsole.js — (bg-dome) UFO 무대 가운데 바닥에 놓인 「조작 콘솔」. 그리는 곳 = bgdomegl.js 의 공중 무늬 층(.bgdm-air).
// 셰이더가 아니라 SVG 두 장을 3D 투영해 얹는다(셰이더 비용 0, 운영자 11-06 「제안대로」):
//   ① 바닥 무늬(받침 고리 · 유도 호) = 바닥 평면(y = 0)의 정사각형 → 화면 사각형으로 원근 사상(CSS matrix3d)
//   ② 몸체 · 별 항로 화면 = 무대 중심에 세운 세로 판(카메라 오른쪽 방향 × 세계 위쪽)을 같은 방식으로 사상
// 크림색 비행접시 조종대: 무대 조명의 티타늄 테 · 크림색 렌즈와 연결한다. 대기 표시는 CSS opacity만 맥동.
// 모든 SVG 는 고정 그림이라 createElementNS 로 만든다(데이터 주입 없음).

const NS = "http://www.w3.org/2000/svg";

// 세계 크기(돔 반지름 = 1, 눈 높이 0.24). 폰에서 만져 보고 조정할 값.
const FLOOR_HALF = 0.105;           // 바닥 무늬 정사각형 반 변
const STAND_W = 0.16;               // 세로 판 폭(SVG 160 단위)
const STAND_VB = [0, 0, 160, 132];  // 발 끝 y=129, 아래 3단위는 기존 투영의 바닥 밑 여백
const STAND_U = STAND_W / STAND_VB[2];   // SVG 1 단위 = 세계 길이
const STAND_H = STAND_VB[3] * STAND_U;
const BOX = 200;                    // 두 SVG 의 CSS 크기(px, 사상 전) — 정사각 · 세로 판 모두 이 폭

function el(tag, attrs, kids) {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (kids) for (const c of kids) e.appendChild(c);
  return e;
}
function floorSvg() {
  // viewBox −100 … 100 = 세계 ±FLOOR_HALF. 위(−y) = 세계 +z 쪽이 아니라 「사각형 꼭짓점 순서」로 맞춘다(아래 place 참고)
  return el("svg", { viewBox: "-100 -100 200 200", width: BOX, height: BOX, class: "bgcs-floor", "aria-hidden": "true" }, [
    el("defs", {}, [
      el("radialGradient", { id: "bgcs-glow" }, [
        el("stop", { offset: "0", "stop-color": "var(--bgcs-lilac)", "stop-opacity": ".32" }),
        el("stop", { offset: ".5", "stop-color": "var(--bgcs-lilac)", "stop-opacity": ".14" }),
        el("stop", { offset: "1", "stop-color": "var(--bgcs-lilac)", "stop-opacity": "0" }),
      ]),
    ]),
    el("circle", { r: "98", fill: "url(#bgcs-glow)" }),
    el("circle", { r: "53", fill: "var(--bgcs-pad)", "fill-opacity": ".7", stroke: "var(--bgcs-metal)", "stroke-width": "1.8", "stroke-opacity": ".65" }),
    el("circle", { r: "47", fill: "none", stroke: "var(--bgcs-lilac)", "stroke-width": "2", "stroke-opacity": ".6" }),
    // 원 전체가 번쩍이거나 퍼지지 않고, 앞쪽 두 호가 천천히 숨을 쉰다.
    el("path", { class: "bgcs-await", d: "M-77 12 A78 78 0 0 0 -40 67 M40 67 A78 78 0 0 0 77 12", fill: "none", stroke: "var(--bgcs-rose)", "stroke-width": "2.4", "stroke-linecap": "round" }),
    el("path", { d: "M-18 84 Q0 89 18 84", fill: "none", stroke: "var(--bgcs-cream)", "stroke-width": "3", "stroke-linecap": "round", opacity: ".7" }),
    el("ellipse", { cy: "4", rx: "36", ry: "24", fill: "var(--bgcs-shadow)", opacity: ".45" }),
  ]);
}

const SCREEN_D = "M43 31 H117 Q129 31 132 42 L137 57 Q140 68 126 71 Q80 82 34 71 Q20 68 23 57 L28 42 Q31 31 43 31Z";   // 유리 화면 윤곽

function standSvg() {
  const [x, y, w, h] = STAND_VB;
  return el("svg", { viewBox: `${x} ${y} ${w} ${h}`, width: BOX, height: BOX * h / w, class: "bgcs-stand", "aria-hidden": "true" }, [
    el("defs", {}, [
      el("linearGradient", { id: "bgcs-shell", x2: "0%", y2: "100%" }, [
        el("stop", { offset: "0", "stop-color": "var(--bgcs-shell-top)" }),
        el("stop", { offset: "1", "stop-color": "var(--bgcs-shell-bottom)" }),
      ]),
      el("linearGradient", { id: "bgcs-trim", x2: "0%", y2: "100%" }, [
        el("stop", { offset: "0", "stop-color": "var(--bgcs-metal-light)" }),
        el("stop", { offset: ".45", "stop-color": "var(--bgcs-metal)" }),
        el("stop", { offset: "1", "stop-color": "var(--bgcs-metal-dark)" }),
      ]),
      el("linearGradient", { id: "bgcs-screen", x2: "0%", y2: "100%" }, [
        el("stop", { offset: "0", "stop-color": "var(--bgcs-screen-top)" }),
        el("stop", { offset: "1", "stop-color": "var(--bgcs-screen-bottom)" }),
      ]),
      // 가까이 가서 조작 패널이 뜨면 화면이 켜진 듯 빛난다(11-06 운영자) — 흐린 빛 판(.bgcs-glow)과 화면 위 시안 막(.bgcs-lit), css/bgpanel.css
      el("filter", { id: "bgcs-blur", x: "-40%", y: "-60%", width: "180%", height: "220%" }, [el("feGaussianBlur", { stdDeviation: "9" })]),
      el("linearGradient", { id: "bgcs-orbit" }, [
        el("stop", { offset: "0", "stop-color": "var(--bgcs-rose)" }),
        el("stop", { offset: "1", "stop-color": "var(--bgcs-cream)" }),
      ]),
    ]),
    // 발 끝은 기존 place()의 viewBox 아래 3단위에 맞춘다. 전체를 정면 윤곽으로 그린다.
    el("path", { d: "M51 119 Q80 112 109 119 Q119 122 116 126 Q80 132 44 126 Q41 122 51 119Z", fill: "url(#bgcs-trim)", stroke: "var(--bgcs-metal-dark)", "stroke-width": "1.2" }),
    el("path", { d: "M63 84 H97 L101 116 Q80 124 59 116Z", fill: "url(#bgcs-shell)", stroke: "var(--bgcs-metal)", "stroke-width": "1.5" }),
    el("path", { d: "M73 94 H87 L89 113 Q80 116 71 113Z", fill: "var(--bgcs-metal)", opacity: ".65" }),
    el("path", { d: "M57 124 Q80 127 103 124", fill: "none", stroke: "var(--bgcs-cream)", "stroke-width": "1.5", "stroke-linecap": "round" }),
    // 가로로 넓고 둥근 크림색 외피 + 아래 티타늄 띠. 원근 사다리꼴 대신 정면 윤곽.
    el("path", { d: "M22 40 Q27 24 49 24 H111 Q133 24 138 40 L149 61 Q155 78 132 86 Q80 102 28 86 Q5 78 11 61Z", fill: "url(#bgcs-trim)", stroke: "var(--bgcs-metal-dark)", "stroke-width": "1.8" }),
    el("path", { d: "M23 39 Q28 23 49 23 H111 Q132 23 137 39 L147 59 Q151 70 130 77 Q80 91 30 77 Q9 70 13 59Z", fill: "url(#bgcs-shell)", stroke: "var(--bgcs-metal-light)", "stroke-width": "1.5" }),
    el("path", { d: "M20 72 Q80 96 140 72", fill: "none", stroke: "var(--bgcs-metal-dark)", "stroke-width": "1.3", opacity: ".65" }),
    el("rect", { x: "69", y: "20", width: "22", height: "4", rx: "2", fill: "var(--bgcs-metal-light)" }),
    // 넓은 유리 화면: 별 항로와 작은 계기. 읽을 수 없는 글자 · 주사선 · 깜빡임은 두지 않는다.
    el("path", { class: "bgcs-glow", d: SCREEN_D, fill: "#5fe6ff", stroke: "#5fe6ff", "stroke-width": "14", "stroke-linejoin": "round", filter: "url(#bgcs-blur)" }),
    el("path", { d: SCREEN_D, fill: "url(#bgcs-screen)", stroke: "var(--bgcs-metal-dark)", "stroke-width": "2" }),
    el("path", { class: "bgcs-lit", d: SCREEN_D, fill: "#4fe3ff" }),
    el("path", { d: "M39 35 H119", fill: "none", stroke: "var(--bgcs-glass)", "stroke-width": "1.5", "stroke-linecap": "round", opacity: ".45" }),
    el("ellipse", { cx: "61", cy: "53", rx: "24", ry: "13", fill: "none", stroke: "url(#bgcs-orbit)", "stroke-width": "1.3", transform: "rotate(-18 61 53)", opacity: ".75" }),
    el("path", { d: "M61 40 L65 48 L74 49 L67 55 L69 64 L61 60 L53 64 L55 55 L48 49 L57 48Z", fill: "var(--bgcs-cream)", stroke: "var(--bgcs-rose)", "stroke-width": "1.3", "stroke-linejoin": "round" }),
    el("circle", { class: "bgcs-await", cx: "82", cy: "46", r: "3", fill: "var(--bgcs-rose)", stroke: "var(--bgcs-cream)", "stroke-width": "1" }),
    el("g", { fill: "none", stroke: "var(--bgcs-glass)", "stroke-width": "2", "stroke-linecap": "round" }, [
      el("path", { d: "M98 44 H118 M98 50 H110", opacity: ".65" }),
      el("path", { d: "M99 63 V59 M107 63 V56 M115 63 V53" }),
    ]),
    // 세 개의 촉각 버튼과 오른쪽 대기등. 멀리서는 큰 별, 가까이서는 조작부가 읽힌다.
    el("g", { stroke: "var(--bgcs-metal-dark)", "stroke-width": "1" }, [
      el("ellipse", { cx: "48", cy: "78", rx: "4.5", ry: "2.8", fill: "var(--bgcs-rose)" }),
      el("ellipse", { cx: "63", cy: "81", rx: "4.5", ry: "2.8", fill: "var(--bgcs-cream)" }),
      el("ellipse", { cx: "78", cy: "82", rx: "4.5", ry: "2.8", fill: "var(--bgcs-mint)" }),
    ]),
    el("rect", { x: "99", y: "77", width: "15", height: "4", rx: "2", fill: "var(--bgcs-metal-dark)" }),
    el("path", { class: "bgcs-await", d: "M102 79 H111", stroke: "var(--bgcs-cream)", "stroke-width": "2", "stroke-linecap": "round" }),
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

  let active = false;
  return {
    /** 조작 패널이 떠 있는 동안 화면에 불(글로우) */
    setActive(on) { if (on !== active) { active = on; root.classList.toggle("is-active", on); } },
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
