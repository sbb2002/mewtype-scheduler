// bgpanel.js — (bg-dome) 배경 보기 중 UFO 가운데 콘솔에 다가가면 화면 가운데에 뜨는 「UFO CONTROL」 조작 패널. 모양 = css/bgpanel.css.
// 디자인 · 움직임 정본 = devpapers ref/bg-dome/ufo-panel/Main.dc.html(칸 · 문구 · 아이콘) + Approach.dc.html(등장 · 퇴장 연출).
// 언제 뜨는지는 bgdomegl.js 가 정한다(뒤로 물러선 거리 r 의 문턱 — 나타남 0.12 · 사라짐 0.18, 망원이면 숨김). 여기는 모양과 on/off 만.
// 2단계(11-06): 칸을 누르면 onPick 으로 알린다(배경 바꾸기는 bgdomegl.js). 3단계(11-06): 초행성X 칸 1초 길게 누르기 = onHold(성간 이동), 워프 기어 패널은 bggear.js.
// 고정 문구 · 아이콘만 쓰고 모두 createElement · textContent 로 만든다(innerHTML 금지).

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

// 아이콘(시안 그대로) — 분홍 구름 · 토성 · 지구
const ICONS = {
  pink: () => s("svg", { width: 26, height: 26, viewBox: "0 0 24 24", fill: "#ff8cc6", stroke: "#ff6fb5", "stroke-width": "1.4", "stroke-linejoin": "round", "aria-hidden": "true" }, [
    s("path", { d: "M6.5 17.5h11a3.5 3.5 0 0 0 .4-7A5 5 0 0 0 8.3 9.4 4 4 0 0 0 6.5 17.5Z" }),
  ]),
  space: () => s("svg", { width: 28, height: 28, viewBox: "0 0 24 24", fill: "none", "stroke-linecap": "round", "aria-hidden": "true" }, [
    s("ellipse", { cx: 12, cy: 12, rx: 10.5, ry: 3.4, transform: "rotate(-18 12 12)", stroke: "#e8c58a", "stroke-width": "1.5" }),
    s("circle", { cx: 12, cy: 12, r: 5.6, fill: "#d9a85e", stroke: "#f3d39b", "stroke-width": "1" }),
    s("path", { d: "M7 12.6c3 .9 7 .7 10-.8", stroke: "#b9843f", "stroke-width": "1" }),
    s("path", { d: "M2.3 15.1C5 15.6 10 14.6 15 12.9s7-3.4 6.7-4.6", stroke: "#e8c58a", "stroke-width": "1.5" }),
  ]),
  earth: () => s("svg", { width: 28, height: 28, viewBox: "0 0 24 24", "aria-hidden": "true" }, [
    s("circle", { cx: 12, cy: 12, r: 9, fill: "#2a6fd1" }),
    s("path", { d: "M7.2 5.6c1.6-.6 3.1-.3 3.6.8.4 1-.9 1.4-.7 2.5.2 1 1.6 1 1.5 2.3-.1 1.2-1.6 1.2-2.3 2.4-.6 1-.1 2.6-1 3-.9.3-1.6-1-2-2.4-.4-1.5-1.6-2-1.8-3.4-.2-1.6.9-4.4 2.7-5.2Z", fill: "#5fd08a" }),
    s("path", { d: "M14.4 4.4c1.5.2 3.4 1.4 4.4 3-.9.3-1.8-.3-2.6.3-.8.6-.2 1.8-1.2 2.1-1 .3-1.6-.8-1.4-2 .2-1.3-.6-2.5.8-3.4Z", fill: "#5fd08a" }),
    s("path", { d: "M15.6 13.4c1.2-.4 2.9.2 3.2 1.4-.5 1.6-1.6 3-3 3.9-.6-.9.5-1.8 0-2.8-.4-.9-1.2-1.8-.2-2.5Z", fill: "#5fd08a" }),
    s("circle", { cx: 12, cy: 12, r: 9, fill: "none", stroke: "#9fd6ff", "stroke-width": "1" }),
  ]),
};

const TILES = [
  { key: "pink", label: "버츄얼 스페이스", sub: "편안히 붕~ 떠있는 공간.", chips: [] },
  { key: "space", label: "초행성X로의 여행", sub: "외우주로 가출하고 오겠습니다!", chips: ["길게 누르면 워프"] },
  { key: "earth", label: "지구", sub: "당신이 있는 곳일지도?", chips: ["해", "달", "별", "실제 자리"] },
];

/**
 * 홀로그램 카드 틀(조작 패널 · 워프 기어 패널 공용, 11-06 운영자 「두 UI 테두리 · 주사선 · 스캔라인을 같게, 테두리는 푸른 글로우」).
 * card(모서리 잘린 카드 — 주사선 층 .ufo-scan 을 맨 앞 자식으로) 를 받아 바깥 틀 자식들을 돌려준다:
 *   .ufo-clip(등장 · 퇴장 연출) = card + 빛나는 테두리 SVG(.ufo-frame) + 색 갈라짐 두 겹, 모서리 꺾쇠 넷, 등장 광선.
 * 테두리를 SVG 로 따로 그리는 까닭: 카드는 clip-path 로 모서리를 자르는데 그러면 카드 자신의 box-shadow 글로우도 잘려 안 보인다.
 * SVG 는 카드 크기를 따라 모서리 잘린 윤곽을 다시 그리고(ResizeObserver), CSS drop-shadow 로 바깥에 번진다.
 */
export function holoParts(card) {
  const line = s("path", { class: "ufo-frame__line" });
  const frame = s("svg", { class: "ufo-frame", "aria-hidden": "true" }, [line]);
  const fit = () => {
    const w = card.offsetWidth, hh = card.offsetHeight;
    if (!w || !hh) return;
    frame.setAttribute("width", w); frame.setAttribute("height", hh); frame.setAttribute("viewBox", `0 0 ${w} ${hh}`);
    line.setAttribute("d", `M.6 .6 H${w - 18} L${w - .6} 18 V${hh - .6} H18 L.6 ${hh - 18} Z`);
  };
  if (typeof ResizeObserver === "function") new ResizeObserver(fit).observe(card); else requestAnimationFrame(fit);
  return [
    h("div", "ufo-clip", [card, frame, h("span", "ufo-chroma ufo-chroma--p"), h("span", "ufo-chroma ufo-chroma--c")]),
    h("span", "ufo-brk ufo-brk--tl"), h("span", "ufo-brk ufo-brk--tr"), h("span", "ufo-brk ufo-brk--bl"), h("span", "ufo-brk ufo-brk--br"),
    h("span", "ufo-line"),
  ];
}

/** 패널을 만든다. set(on) = 등장 · 퇴장, setCurrent(key) = 지금 배경 칸에 불. */
export function createUfoPanel() {
  const tiles = {}, firstChip = {}, chipBase = {}, subEl = {};
  let pick = null, hold = null, current = null;
  // 3단계: 초행성X 칸 1초 길게 누르기 = 성간 이동(시안 Main.dc.html chargeLoop — 1초에 차고, 떼면 0.25초에 빠짐, 다 차면 hold()).
  let charge = 0, holding = false, chargeRaf = 0, chargeLast = 0, eatClick = false, warping = false;
  const fill = h("span", "ufo-tile__fill");
  const showChip = (key) => { const c = firstChip[key]; if (!c) return; const text = key === "space" && charge > 0 && !warping ? `충전 ${Math.round(charge * 100)}%` : chipBase[key]; if (c.textContent !== text) c.textContent = text; };
  function chargeLoop(now) {
    chargeRaf = 0;
    const dt = Math.min(0.25, (now - chargeLast) / 1000); chargeLast = now;
    charge = holding ? charge + dt / 1.0 : charge - dt / 0.25;
    if (charge >= 1 && holding) {
      charge = 0; holding = false; eatClick = true;   // 다 찼다 — 뒤따르는 click(떼기)은 고르기로 치지 않는다
      fill.style.transform = "scaleX(0)"; showChip("space");
      if (hold) hold();
      return;
    }
    if (charge <= 0) charge = 0;
    fill.style.transform = `scaleX(${charge.toFixed(3)})`;
    showChip("space");
    if (holding || charge > 0) chargeRaf = requestAnimationFrame(chargeLoop);
  }
  const list = h("div", "ufo-list");
  TILES.forEach((t, i) => {
    const sub = h("span", "ufo-tile__sub", [t.sub]);
    subEl[t.key] = sub;
    const text = h("span", "ufo-tile__text", [h("span", "ufo-tile__lbl", [t.label]), sub]);
    if (t.chips.length) {
      const chips = t.chips.map((c) => h("span", "ufo-chip", [c]));
      firstChip[t.key] = chips[0]; chipBase[t.key] = t.chips[0];
      text.append(h("span", "ufo-chips", chips));
    }
    const b = h("button", "ufo-tile ufo-stg", [...(t.key === "space" ? [fill] : []), h("span", "ufo-tile__ico", [ICONS[t.key]()]), text, h("span", "ufo-tile__led")], { type: "button", "aria-pressed": "false" });
    b.style.setProperty("--i", String(i + 1));
    b.addEventListener("click", () => { if (eatClick) { eatClick = false; return; } if (on && pick) pick(t.key); });
    if (t.key === "space") {
      b.addEventListener("contextmenu", (e) => e.preventDefault());   // 길게 누를 때 폰 기본 메뉴 막기
      b.addEventListener("pointerdown", (e) => {
        if (!on || b.disabled || warping || !hold) return;
        eatClick = false; holding = true;
        try { b.setPointerCapture(e.pointerId); } catch { /* 캡처 못 함 */ }
        if (!chargeRaf) { chargeLast = performance.now(); chargeRaf = requestAnimationFrame(chargeLoop); }
      });
      const release = () => { if (!holding) return; holding = false; if (!chargeRaf) { chargeLast = performance.now(); chargeRaf = requestAnimationFrame(chargeLoop); } };
      b.addEventListener("pointerup", release);
      b.addEventListener("pointercancel", release);
      b.addEventListener("lostpointercapture", release);
    }
    tiles[t.key] = b;
    list.append(b);
  });
  // 지구를 고를 때 위치 권한을 묻는다는 안내(시안 Main.dc.html — 지구 칸 아래)
  const earthNote = h("p", "ufo-note", ["위치 권한을 물어요 — 거절하면 지금 배경에 남아요."]);
  list.append(earthNote);

  const head = h("div", "ufo-head", [
    h("div", "ufo-head__l", [h("span", "ufo-mono ufo-type ufo-head__tag", ["UFO CONTROL"]), h("span", "ufo-stg ufo-head__title", ["어디로 갈까요?"])]),
  ]);
  head.querySelector(".ufo-head__title").style.setProperty("--i", "0");
  const foot = h("div", "ufo-mono ufo-foot ufo-stg", [h("span", null, ["오므리면 닫힘"]), h("span", null, ["SYS · OK"])]);
  foot.style.setProperty("--i", "4");

  const card = h("div", "ufo-card", [h("div", "ufo-scan"), head, list, foot]);
  const root = h("div", "ufo-hud ufo-holo is-idle", holoParts(card), { role: "dialog", "aria-label": "UFO 조작 패널", "aria-hidden": "true" });
  root.inert = true;
  document.body.appendChild(root);

  // 멀리 있을 때 안내(Approach.dc.html) — 누르기는 통과
  const hint = h("div", "ufo-hint", [
    s("svg", { width: 18, height: 18, viewBox: "0 0 24 24", fill: "none", stroke: "#4fe3ff", "stroke-width": "1.6", "aria-hidden": "true" }, [s("path", { d: "M8 8 4 4M4 4v4M4 4h4M16 16l4 4M20 20v-4M20 20h-4" })]),
    h("span", null, ["두 손가락으로 벌려 가운데로 다가가 보세요"]),
  ], { "aria-hidden": "true" });
  document.body.appendChild(hint);

  let on = false, hintA = -1;
  return {
    get on() { return on; },
    remove() { root.remove(); hint.remove(); },
    set(v) {
      if (v === on) return;
      on = v;
      root.classList.remove("is-idle");
      root.classList.toggle("is-on", v);
      root.classList.toggle("is-off", !v);
      root.inert = !v || root.classList.contains("is-back");
      root.setAttribute("aria-hidden", v ? "false" : "true");
      if (!v && root.contains(document.activeElement)) document.activeElement.blur();
    },
    /** 칸을 누르면 부를 함수(key = "pink" | "space" | "earth") */
    onPick(fn) { pick = fn; },
    /** 칸의 첫 표시(칩) 글 바꾸기 — 같은 글이면 건드리지 않는다(초행성X 는 충전 중이면 「충전 N%」가 앞선다) */
    setChip(key, text) { chipBase[key] = text; showChip(key); },
    /** 초행성X 칸 1초 길게 누르기가 다 찼을 때 부를 함수 */
    onHold(fn) { hold = fn; },
    /** 성간 이동 중 표시 — 초행성X 칸이 꽉 찬 채 맥박 · 설명 「메롱이다, 그럼 바이바이!」(시안) · 칩 「성간 이동 중」 */
    setWarping(v) {
      if (v === warping) return;
      warping = v;
      if (v) { holding = false; charge = 0; }
      fill.classList.toggle("is-full", v);
      fill.style.transform = v ? "scaleX(1)" : "scaleX(0)";
      subEl.space.textContent = v ? "메롱이다, 그럼 바이바이!" : TILES[1].sub;
      chipBase.space = v ? "성간 이동 중" : TILES[1].chips[0];
      showChip("space");
    },
    /** 카드 겹치기(bgdeck.js)용 — 패널 바깥 틀 */
    get el() { return root; },
    /** 뒤 카드로(작고 어둡게, 누를 수 없음) · 길게 누르던 충전은 취소 */
    setBack(v) {
      if (root.classList.contains("is-back") === v) return;
      root.classList.toggle("is-back", v);
      root.inert = !on || v;
      if (v) this.cancelHold();
    },
    /** 길게 누르기 충전 취소(카드를 옆으로 밀기 시작하면) */
    cancelHold() { if (holding || charge > 0) { holding = false; charge = 0; fill.style.transform = "scaleX(0)"; showChip("space"); } },
    /** 성간 이동 레드존 — 시안 글로우를 빨갛게(css .is-red) */
    setRed(v) { if (root.classList.contains("is-red") !== v) root.classList.toggle("is-red", v); },
    setCurrent(key) {
      if (key === current) return;
      current = key;
      earthNote.hidden = key === "earth";   // 이미 지구면 권한 안내가 필요 없다
      for (const k in tiles) {
        const sel = k === key;
        tiles[k].classList.toggle("is-on", sel);
        tiles[k].setAttribute("aria-pressed", sel ? "true" : "false");
      }
    },
    /** 하늘 전환(돔 재투영) 중 — 패널을 빠르게 투명하게(css/bgpanel.css .is-tx). 끄고 켜기(set)는 bgdomegl.js 가 따로 한다 */
    transmit(v) { root.classList.toggle("is-tx", v); },
    /** 하늘을 고른 뒤 준비(우주 사진 · 위치) 중 — 칸을 비활성(누를 수 없고 흐리게) */
    setBusy(v) { for (const k in tiles) tiles[k].disabled = v; },
    /** 안내 불투명도 0 ~ 1(0.02 이상 바뀔 때만 DOM 을 건드린다) */
    setHint(a) {
      if (Math.abs(a - hintA) < 0.02 && !(a === 0 && hintA !== 0)) return;
      hintA = a;
      hint.style.opacity = a.toFixed(2);
      hint.style.visibility = a > 0 ? "visible" : "hidden";
    },
  };
}
