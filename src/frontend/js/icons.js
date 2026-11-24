// 선 아이콘 — 이모지(🔒 📺) 대신 쓴다. 한 세트(lucide 모양) · 한 굵기(1.5) · 글자색을 따른다(currentColor).
// import 할 때 DOM 을 건드리지 않는다(node self-check 가 이 모듈을 불러도 깨지지 않게).
const NS = "http://www.w3.org/2000/svg";

const SHAPES = {
  // 자물쇠 = 회원 전용
  lock: [["rect", { x: 4, y: 11, width: 16, height: 10, rx: 2 }], ["path", { d: "M8 11V7a4 4 0 0 1 8 0v4" }]],
  // 화면 = 썸네일 없는 예고
  tv: [["rect", { x: 2, y: 7, width: 20, height: 14, rx: 2 }], ["path", { d: "m17 2-5 5-5-5" }]],
};

/** name 의 선 아이콘 <svg>. 크기는 CSS 가 정한다(기본 1em). */
export function lineIcon(name, cls = "ln-ico") {
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "1.5");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("class", cls);
  for (const [tag, attrs] of SHAPES[name] || []) {
    const n = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, String(v));
    svg.appendChild(n);
  }
  return svg;
}
