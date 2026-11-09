// bggear.js — (bg-dome 3단계) 성간 이동 중 배경 보기 화면 아래에 작게 뜨는 「워프 기어」 패널 — 스로틀 레버형(11-06 운영자 채택 = 컴팩트 시안 B,
// 아티팩트 「워프 기어 컴팩트 시안」). 조작 패널은 그대로 두고, 이 패널은 성간 이동 중 늘 떠 있다가 끝나면 하늘 전환처럼 사라진다(도트 + 흰 선).
// 속도 계산은 bgwarp.js(순수), 언제 뜨는지 · 기어를 누르면 무엇을 하는지는 bgdomegl.js. 여기는 모양 · 그리기 · 사라지기만. 모양 = css/bgpanel.css(.ufo-gear).
// 고정 문구 · 그림만 쓰고 모두 createElement(NS) · textContent 로 만든다(innerHTML 금지).
// 예전 큰 속도계 · 카드 겹치기 안 = 브랜치 test/bg-dome-deck-v52.

import { GEAR_BETA, isRed, warpReady, gearPos } from "./bgwarp.js";
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

// 사라지기 = 하늘 전환(돔 재투영)과 같은 말투 — 흰 띠가 위에서 아래로 지나가고, 그 앞 도트(6px 칸)가 칸마다 무작위로 서서히 사라진다.
// 캔버스로 만든 마스크를 매 프레임 바꾼다(패널이 작아 싸다). 흰 띠 = 「여기까지 사라짐」(도트 띠의 뒤 끝).
const CELL = 6;
const cellHash = (x, y) => { const v = Math.sin(x * 127.1 + y * 311.7) * 43758.5453; return v - Math.floor(v); };
function dissolve(root, line, done) {
  const PAD = 30, w = root.offsetWidth + PAD * 2, hh = root.offsetHeight + PAD * 2;
  const mc = document.createElement("canvas"); mc.width = w; mc.height = hh;
  const mx = mc.getContext("2d"), t0 = performance.now(), T = 1100, band = 0.45;
  line.style.left = "0px"; line.style.right = "0px";
  const step = (now) => {
    const u = Math.min(1, (now - t0) / T), e = u * u * (3 - 2 * u), edge = -band + e * (1 + 2 * band);
    mx.clearRect(0, 0, w, hh); mx.fillStyle = "#000";
    for (let y = 0; y < hh; y += CELL) for (let x = 0; x < w; x += CELL) {
      const sv = (edge - (y + CELL / 2) / hh) / band;
      if (sv <= 0) { mx.globalAlpha = 1; mx.fillRect(x, y, CELL, CELL); continue; }
      if (sv >= 1) continue;
      const th = 0.01 + 0.64 * cellHash(x / CELL, y / CELL), a = 1 - Math.max(0, Math.min(1, (sv - th) / 0.35));
      if (a > 0) { mx.globalAlpha = a; mx.fillRect(x, y, CELL, CELL); }
    }
    mx.globalAlpha = 1;
    const url = `url(${mc.toDataURL()})`;
    root.style.webkitMaskImage = url; root.style.maskImage = url;
    const ly = (edge - band) * hh - PAD;
    line.style.top = ly + "px"; line.style.opacity = u < 1 && ly > -12 && ly < hh - PAD * 2 + 12 ? "1" : "0";
    if (u < 1) requestAnimationFrame(step); else done();
  };
  root.style.webkitMaskSize = root.style.maskSize = `${w}px ${hh}px`;
  root.style.webkitMaskPosition = root.style.maskPosition = `-${PAD}px -${PAD}px`;
  root.style.webkitMaskRepeat = root.style.maskRepeat = "no-repeat";
  requestAnimationFrame(step);
}

/** 기어 패널을 만든다. onGear(i) = 기어 고름(0 = N), onWarp() = WARP 누름 */
export function createGearPanel({ onGear, onWarp }) {
  const belt = beltSign();
  const read = h("span", "ufo-mono ugr-read", ["0.00c"]);
  const chip = h("span", "ufo-mono ugr-chip", ["IDLE"]);
  const warp = h("button", "ufo-mono ugr-warp", ["WARP"], { type: "button", disabled: "" });
  warp.addEventListener("click", () => { if (!warp.disabled) onWarp(); });
  const top = h("div", "ugr-top", [belt, read, chip, h("span", "ugr-sp"), warp]);
  // 스로틀 레일: 손잡이를 끌거나 눈금을 눌러 단을 고른다(N · 1 ~ 5, 오른쪽 두 칸 = 레드존). 채움 = 지금 속도
  const fill = h("span", "ugr-fill"), thumb = h("span", "ufo-mono ugr-thumb", ["N"]);
  const track = h("div", "ugr-track", [h("span", "ugr-redrail"), fill, ...GEAR_BETA.map((v, i) => { const d = h("span", "ugr-det"); d.style.left = i * 20 + "%"; return d; }), thumb],
    { role: "slider", tabindex: "0", "aria-label": "성간 이동 기어(N, 1 ~ 5단 · 4 · 5단은 레드존)", "aria-valuemin": "0", "aria-valuemax": "5", "aria-valuenow": "0" });
  const labels = h("div", "ufo-mono ugr-labels", GEAR_BETA.map((v, i) => h("span", i >= 4 ? "is-red" : "", [i ? String(i) : "N"])));
  let locked = false, dragging = false;
  const gearAt = (e) => { const r = track.getBoundingClientRect(); return Math.round(Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)) * 5); };
  track.addEventListener("pointerdown", (e) => { if (locked) return; dragging = true; try { track.setPointerCapture(e.pointerId); } catch { /* 캡처 못 함 */ } onGear(gearAt(e)); });
  track.addEventListener("pointermove", (e) => { if (dragging && !locked) onGear(gearAt(e)); });
  const up = () => { dragging = false; };
  track.addEventListener("pointerup", up); track.addEventListener("pointercancel", up);
  track.addEventListener("keydown", (e) => {
    if (locked) return;
    const cur = Number(track.getAttribute("aria-valuenow"));
    if (e.key === "ArrowRight" || e.key === "ArrowUp") { onGear(Math.min(5, cur + 1)); e.preventDefault(); }
    if (e.key === "ArrowLeft" || e.key === "ArrowDown") { onGear(Math.max(0, cur - 1)); e.preventDefault(); }
  });
  const card = h("div", "ugr-card", [h("div", "ufo-scan"), top, track, labels]);
  // 테두리 · 주사선 · 스캔라인 · 등장 연출은 조작 패널과 같은 홀로그램 카드 틀(bgpanel.js holoParts)
  const root = h("div", "ufo-gear ufo-holo", holoParts(card), { role: "group", "aria-label": "성간 이동 기어", "aria-hidden": "true" });
  const wline = h("span", "ugr-wline");
  root.append(wline);
  root.hidden = true; root.inert = true;
  document.body.appendChild(root);

  // (11-09 해금) 워프 목적지 고르기 — WARP 를 누르면 기어 패널 위에 홀로그램 카드로 뜬다. 고르지 않거나 취소 · 바깥 누르기 = 아무 일도 없음.
  const chList = h("div", "ugc-list");
  const chCancel = h("button", "ufo-mono ugc-cancel", ["취소"], { type: "button" });
  const chCard = h("div", "ugc-card", [h("div", "ufo-scan"), h("div", "ufo-head", [h("div", "ufo-head__l", [h("span", "ufo-mono ufo-head__tag", ["WARP"]), h("span", "ufo-head__title", ["워프 목적지"])])]), chList, chCancel]);
  const chooser = h("div", "ufo-chooser ufo-holo", holoParts(chCard), { role: "dialog", "aria-label": "워프 목적지" });
  const chScrim = h("div", "ufo-chooser-scrim");
  chooser.hidden = chScrim.hidden = true;
  document.body.append(chScrim, chooser);
  let chPick = null;
  const closeChooser = () => { if (chooser.hidden) return; chooser.hidden = chScrim.hidden = true; chooser.classList.remove("is-on"); chPick = null; };
  chCancel.addEventListener("click", closeChooser);
  chScrim.addEventListener("click", closeChooser);

  let shown = false, leaving = false, last = {};
  const set = (k, v, fn) => { if (last[k] !== v) { last[k] = v; fn(v); } };
  function reset() { root.style.webkitMaskImage = root.style.maskImage = "none"; wline.style.opacity = "0"; root.style.transform = ""; }
  return {
    get shown() { return shown; },
    remove() { root.remove(); chooser.remove(); chScrim.remove(); },
    /** 워프 목적지 고르기 창 — items = bgunlock.chooserItems 결과, onPick(key) = 고름(창은 닫힌다). 지금 있는 곳(here)은 누를 수 없다 */
    openChooser(items, onPick) {
      chList.replaceChildren(...items.map((it) => {
        const b = h("button", "ugc-item" + (it.here ? " is-here" : ""), [h("span", "ugc-name", [it.name]), ...(it.here ? [h("span", "ufo-chip", ["지금 여기"])] : [])], { type: "button" });
        if (it.here) b.disabled = true;
        b.addEventListener("click", () => { const fn = chPick; closeChooser(); if (fn) fn(it.key); });
        return b;
      }));
      chPick = onPick;
      chooser.hidden = chScrim.hidden = false;
      chooser.classList.remove("is-on"); void chooser.offsetWidth; chooser.classList.add("is-on");
    },
    closeChooser,
    get choosing() { return !chooser.hidden; },
    /** 보이기 · 숨기기. 숨길 때 animate = true 면 도트 + 흰 선으로 사라지고(움직임 줄이기면 바로), "fade" 면 0.15초에 꺼진다(하늘을 바꿀 때) */
    show(on, animate = false) {
      if (on === shown) return;
      shown = on;
      if (on) {
        leaving = false; reset();
        root.hidden = false; root.inert = false; root.setAttribute("aria-hidden", "false");
        root.classList.remove("is-on"); void root.offsetWidth; root.classList.add("is-on");   // 등장 연출 다시
        return;
      }
      root.inert = true; root.setAttribute("aria-hidden", "true");
      closeChooser();   // 기어 패널이 사라지면 고르기 창도
      if (root.contains(document.activeElement)) document.activeElement.blur();
      const hide = () => { if (shown) return; leaving = false; root.hidden = true; root.classList.remove("is-on"); reset(); };
      if (animate === "fade" && !root.hidden) { leaving = true; root.classList.add("is-tx"); setTimeout(() => { root.classList.remove("is-tx"); hide(); }, 160); }   // 하늘을 바꿀 때 — 조작 패널과 함께 0.15초에 꺼짐
      else if (animate && !root.hidden && !leaving && !matchMedia("(prefers-reduced-motion: reduce)").matches) { leaving = true; root.style.transform = ""; dissolve(root, wline, hide); } else hide();
    },
    /** 흔들기(px) — 좌석벨트 표시등이 켜지면 빠르고 세게, 깜빡일 땐 약하게(bgdomegl.js 가 매 프레임) */
    shake(dx, dy) { if (!leaving) root.style.transform = dx || dy ? `translate(${dx.toFixed(1)}px, ${dy.toFixed(1)}px)` : ""; },
    /** 모형 상태를 그린다(바뀐 것만 DOM 을 건드린다). jumping = 워프 점프 연출 중(조작 잠금, 표시 「JUMP」) */
    update(st, jumping, jumpBeta) {
      locked = jumping;
      const beta = jumping ? jumpBeta : st.beta, red = jumping ? beta >= 0.85 : isRed(st), moving = st.mode !== "idle";
      set("red", red, (v) => root.classList.toggle("is-red", v));
      set("beta", beta.toFixed(2), (v) => { read.textContent = v + "c"; });
      set("fill", (gearPos(beta) * 20).toFixed(1), (v) => { fill.style.width = v + "%"; });   // 채움 끝 = 지금 속도의 단 위치(눈금과 같은 눈금자)
      set("gear", st.gear, (v) => { thumb.style.left = v * 20 + "%"; thumb.textContent = v ? String(v) : "N"; track.setAttribute("aria-valuenow", String(v)); });
      const gl = (k) => (k === 0 ? "N" : String(k));
      const ST = { go: "ACCEL", accel: "ACCEL", decel: "DECEL", redAccel: "REDLINE", redDecel: "BRAKE!", idle: st.gear === 0 ? "IDLE" : red ? "CRUISE·RED" : "CRUISE" };
      const text = jumping ? "JUMP" : moving && st.stage !== st.gear ? `${ST[st.mode]} ${gl(st.stage)}›${gl(st.gear)}` : ST[st.mode];
      set("chip", text, (v) => { chip.textContent = v; });
      set("chipTone", jumping || red || st.mode.startsWith("red") ? "red" : st.mode === "idle" ? "idle" : "go", (v) => { chip.dataset.tone = v; });
      set("tgt", moving && st.stage !== st.gear, (v) => thumb.classList.toggle("is-tgt", v));
      set("lock", jumping, (v) => track.classList.toggle("is-locked", v));
      set("belt", st.belt, (v) => { belt.dataset.state = v; belt.setAttribute("aria-label", v === "off" ? "좌석벨트 표시등 꺼짐" : "좌석벨트를 매 주세요"); });
      set("warp", !jumping && warpReady(st), (v) => { warp.disabled = !v; });
    },
  };
}
