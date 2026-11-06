// bggear.js — (bg-dome 3단계) 성간 이동 중 배경 보기 화면 아래에 뜨는 「워프 기어」 패널. 모양 = css/bgpanel.css(.ufo-gear), 정본 = devpapers ref/bg-dome/ufo-panel/Gear.dc.html.
// 속도 계산은 bgwarp.js(순수), 언제 뜨는지 · 기어를 누르면 무엇을 하는지는 bgdomegl.js. 여기는 모양과 그리기만.
// 고정 문구 · 그림만 쓰고 모두 createElement(NS) · textContent 로 만든다(innerHTML 금지).
// 시안과 달라진 것: 설명 문단은 화면이 좁아 뺐다 · 속도계를 조금 줄였다 · 맨 아래에 WARP 버튼(운영자 11-06 — 레드존 + 좌석벨트 표시등 꺼짐이면 켜짐).

import { GEAR_BETA, isRed, warpReady } from "./bgwarp.js";
import { holoParts } from "./bgpanel.js";

const NS = "http://www.w3.org/2000/svg";
function h(tag, cls, kids, attrs) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (attrs) for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (kids) for (const c of kids) e.append(c);
  return e;
}
function s(tag, attrs, kids) {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (kids) for (const c of kids) e.appendChild(c);
  return e;
}

// 좌석벨트 표시등 — 시안 그대로(여객기 천장 표시등: 알약 렌즈 · 호박색 「두 손이 버클을 채우는」 그림 · 초록 삽입 화살표). 꺼짐 그림 위에 켜짐 그림을 겹친다.
function beltSign() {
  const hand = () => s("g", {}, [
    s("path", { d: "M12 4 L25 1.5 Q29 1 31 4 L38 12 Q41 15 39.5 19 L38.5 31 Q37.5 35.5 33 34.5 L26 32.5 Q22 31.5 21 27 L19 18 Q15.5 11.5 12 4 Z" }),
    s("path", { d: "M35 11.5 L44 12.5 Q46.5 13.5 45 16.5 L38 17.5 Z" }),
  ]);
  const fing = () => s("path", { d: "M30 33.5 L31 27.5 M34 34.5 L35 28 M37.5 33 L38 27", fill: "none", "stroke-linecap": "round" });
  const pic = () => s("svg", { viewBox: "0 0 120 40", "aria-hidden": "true" }, [
    s("g", { fill: "currentColor" }, [
      ...[18, 21, 24, 27].map((y) => s("rect", { x: 3, y, width: 32, height: 1.8 })),
      s("rect", { x: 37, y: 15, width: 17, height: 15, rx: 2 }),
      s("path", { "fill-rule": "evenodd", d: "M70 15h14v14H70z M72.6 17.6v8.8h8.8v-8.8z M75 20h4v4h-4z" }),
      ...[14, 17, 20, 23].map((y) => s("rect", { x: 96, y, width: 22, height: 1.8 })),
    ]),
    s("g", { fill: "currentColor", stroke: "#1d1e24", "stroke-width": "1.6", "stroke-linejoin": "round" }, [hand()]),
    s("g", { stroke: "#1d1e24", "stroke-width": "1.2" }, [fing()]),
    s("g", { transform: "translate(126 0) scale(-1 1)" }, [
      s("g", { fill: "currentColor", stroke: "#1d1e24", "stroke-width": "1.6", "stroke-linejoin": "round" }, [hand()]),
      s("g", { stroke: "#1d1e24", "stroke-width": "1.2" }, [fing()]),
    ]),
    s("path", { d: "M66 15.5 L66 28.5 L58.5 22 Z", fill: "var(--g)" }),
  ]);
  return h("div", "ugr-belt", [h("span", "ugr-belt__lens", [h("span", "ugr-belt__pic is-off", [pic()]), h("span", "ugr-belt__pic is-lit", [pic()])])], { role: "status", "aria-label": "좌석벨트 표시등 꺼짐" });
}

/** 기어 패널을 만든다. onGear(i) = 기어 누름(0 = N), onWarp() = WARP 누름 */
export function createGearPanel({ onGear, onWarp }) {
  const chip = h("span", "ufo-mono ugr-chip", ["IDLE"]);
  const head = h("div", "ugr-head", [
    h("div", "ugr-head__l", [h("span", "ufo-mono ugr-tag", ["WARP DRIVE"]), h("span", "ugr-title", ["성간 이동 기어"])]),
    chip,
  ]);
  const arc = s("path", { d: "M18 112 A100 100 0 0 1 218 112", fill: "none", "stroke-width": "10", pathLength: "100", "stroke-dasharray": "0 100", class: "ugr-arc" });
  const meterSvg = s("svg", { width: 236, height: 122, viewBox: "0 0 236 122", "aria-hidden": "true", class: "ugr-dial" }, [
    s("path", { d: "M18 112 A100 100 0 0 1 218 112", fill: "none", stroke: "rgba(255,255,255,.12)", "stroke-width": "10" }),
    s("path", { d: "M207.1 66.6 A100 100 0 0 1 218 112", fill: "none", stroke: "rgba(255,61,90,.35)", "stroke-width": "10" }),
    arc,
    s("g", { stroke: "#a9bad0", "stroke-width": "1.5" }, ["M18 112h10", "M47 41l7 7", "M118 12v10", "M189 41l-7 7", "M218 112h-10"].map((d) => s("path", { d }))),
    s("text", { x: 206, y: 48, fill: "#ff6d86", "font-size": "9", "letter-spacing": "1", class: "ufo-mono" }, [document.createTextNode("RED")]),
  ]);
  const needle = h("div", "ugr-needle");
  const read = h("span", "ufo-mono ugr-read", ["0.00c"]);
  const belt = beltSign();
  const meter = h("div", "ugr-meter", [belt, meterSvg, needle, h("div", "ugr-hub"), h("div", "ugr-readout", [read, h("span", "ugr-unit", ["광속 비율"])])]);

  const gears = GEAR_BETA.map((v, i) => {
    const b = h("button", "ugr-gbtn" + (i >= 4 ? " is-red" : ""), [h("span", "ufo-mono ugr-g", [i ? String(i) : "N"]), h("span", "ufo-mono ugr-v", [i ? "." + String(Math.round(v * 100)).padStart(2, "0") : "0"])],
      { type: "button", "aria-pressed": "false", "aria-label": i === 0 ? "중립 — 멈춤" : `${i}단 — 광속의 ${Math.round(v * 100)}%` + (i >= 4 ? " (레드존)" : "") });
    b.addEventListener("click", () => onGear(i));
    return b;
  });
  const grid = h("div", "ugr-grid", [h("span", "ufo-mono ugr-redzone", ["REDZONE"]), ...gears]);
  const warp = h("button", "ufo-mono ugr-warp", ["WARP"], { type: "button", disabled: "" });
  warp.addEventListener("click", () => { if (!warp.disabled) onWarp(); });
  const card = h("div", "ugr-card", [h("div", "ufo-scan"), head, meter, grid, warp]);
  // 테두리 · 주사선 · 스캔라인 · 등장 연출은 조작 패널과 같은 홀로그램 카드 틀(bgpanel.js holoParts)
  const root = h("div", "ufo-gear ufo-holo", holoParts(card), { role: "group", "aria-label": "성간 이동 기어", "aria-hidden": "true" });
  root.hidden = true; root.inert = true;
  document.body.appendChild(root);

  let shown = false, last = {};
  const set = (k, v, fn) => { if (last[k] !== v) { last[k] = v; fn(v); } };
  return {
    get shown() { return shown; },
    /** 카드 겹치기(bgdeck.js)용 — 패널 바깥 틀 */
    get el() { return root; },
    /** 뒤 카드로(작고 어둡게, 누를 수 없음) */
    setBack(v) {
      if (root.classList.contains("is-back") === v) return;
      root.classList.toggle("is-back", v);
      root.inert = !shown || v;
    },
    remove() { root.remove(); },
    show(on) {
      if (on === shown) return;
      shown = on;
      root.hidden = !on; root.inert = !on || root.classList.contains("is-back"); root.setAttribute("aria-hidden", on ? "false" : "true");
      root.classList.toggle("is-on", on);
      if (!on && root.contains(document.activeElement)) document.activeElement.blur();
    },
    /** 모형 상태를 그린다(바뀐 것만 DOM 을 건드린다). jumping = 워프 점프 연출 중(버튼 모두 잠금, 표시 「JUMP」) */
    update(st, jumping, jumpBeta) {
      const beta = jumping ? jumpBeta : st.beta, red = jumping ? beta >= 0.85 : isRed(st), moving = st.mode !== "idle";
      set("red", red, (v) => root.classList.toggle("is-red", v));
      set("beta", beta.toFixed(2), (v) => { read.textContent = v + "c"; });
      set("needle", (-90 + beta * 180).toFixed(1), (v) => { needle.style.transform = `rotate(${v}deg)`; });
      set("arc", (beta * 100).toFixed(1), (v) => arc.setAttribute("stroke-dasharray", v + " 100"));
      const gl = (k) => (k === 0 ? "N" : String(k));
      const ST = { go: "ACCEL", accel: "ACCEL", decel: "DECEL", redAccel: "REDLINE", redDecel: "BRAKE!", idle: st.gear === 0 ? "IDLE" : red ? "CRUISE · RED" : "CRUISE" };
      const text = jumping ? "JUMP" : moving && st.stage !== st.gear ? `${ST[st.mode]} ${gl(st.stage)}›${gl(st.gear)}` : ST[st.mode];
      set("chip", text, (v) => { chip.textContent = v; });
      set("chipTone", jumping || red || st.mode.startsWith("red") ? "red" : st.mode === "idle" ? "idle" : "go", (v) => { chip.dataset.tone = v; });
      gears.forEach((b, i) => {
        const on = moving ? i === st.stage : i === st.gear, tgt = moving && i === st.gear && i !== st.stage;
        set("g" + i, `${on}|${tgt}|${jumping}`, () => { b.classList.toggle("is-on", on); b.classList.toggle("is-tgt", tgt); b.disabled = jumping; b.setAttribute("aria-pressed", i === st.gear ? "true" : "false"); });
      });
      set("belt", st.belt, (v) => { belt.dataset.state = v; belt.setAttribute("aria-label", v === "off" ? "좌석벨트 표시등 꺼짐" : "좌석벨트를 매 주세요"); });
      set("warp", !jumping && warpReady(st), (v) => { warp.disabled = !v; });
    },
  };
}
