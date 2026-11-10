// bghud.js — (bg-dome 해금 2단계) 배경 보기 중 화면에 고정되는 「시선 HUD」 — F5 시안(devpapers ref/bg-dome/hud/hud_f5.html) 디자인 그대로.
// 위 방위 테이프(HDG · 못 찾은 대상 방향 분홍 점) · 가운데 시선 링(대상을 2초 바라보면 잡힘) · 양옆 ALT · ZOOM 눈금(화면과 함께 움직임) · 아래 SKY · KST,
// 잡히면 아래 정보 카드(이름 · 무엇이 열렸는지 · [＋ 확대]). 대상 그림(토성 표식 · 성운 · 별자리)은 돔 위 2D 캔버스에 그린다 — 셰이더 하늘에는 없다.
// 계산은 bghudlogic.js(순수), 해금 규칙은 bgunlock.js, 언제 켜고 무엇을 넘기는지는 bgdomegl.js. 모양 = css/bgpanel.css(.bghud).
// 고정 문구 · 숫자만 쓰고 모두 createElement(NS) · textContent 로 만든다(innerHTML 금지).

import { pickHit, sepDeg, createDwell, stepDwell, resetDwell, beacons } from "./bghudlogic.js";

const NS = "http://www.w3.org/2000/svg";
const CY = "#4fe3ff", PK = "#ff6fb5", SUB = "#a9bad0", INK = "#eef6ff";
const U = 3.2;   // 방위 테이프 1° 당 단위(F5 와 같음, 화면 폭 200 단위)
const REDUCE = window.matchMedia("(prefers-reduced-motion: reduce)");
const HUD_MAX_W = 440;   // 계기 폭 상한(px) — 넓은 화면에서 눈금이 화면을 덮지 않게(제안 A-1)
function sv(tag, attrs, kids) {
  const e = document.createElementNS(NS, tag);
  if (attrs) for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (kids) for (const c of kids) e.appendChild(c);
  return e;
}
const txt = (x, y, s, o = {}) => { const t = sv("text", { x, y, "font-size": o.s || 7, fill: o.c || CY, "text-anchor": o.a || "start", "letter-spacing": ".6", ...(o.w ? { "font-weight": o.w } : {}) }); t.textContent = s; return t; };
function h(tag, cls, kids, attrs) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (attrs) for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (kids) for (const c of kids) e.append(c);
  return e;
}
const ZT = [1, 1.5, 2, 3, 4, 5, 7, 10, 15, 20, 30], ZM = [1.25, 1.75, 2.5, 3.5, 4.5, 6, 8.5, 12.5, 17.5, 25];

/**
 * HUD 를 만든다. onLock(t) = 대상이 잡힘 → { k, to, fresh } 를 돌려준다(해금 · 저장 · 알림은 부르는 쪽),
 * onZoom(x) = [＋ 확대] · [－ 원래대로](x = 망원 배율, 1 = 원래대로).
 */
export function createHud({ onLock, onZoom }) {
  // (제안 E-3) 루트는 보조기기에 열어 두고, 장식 캔버스 · 그림만 숨긴다 — 「＋ 확대」 버튼이 읽히게
  const root = h("div", "bghud");
  const cv = h("canvas", "bghud-sky");
  cv.setAttribute("aria-hidden", "true");
  const g = cv.getContext("2d");
  const svg = sv("svg", { class: "bghud-svg", preserveAspectRatio: "xMidYMin meet", "aria-hidden": "true" });
  root.append(cv, svg);

  // ── SVG 부품(한 번 만들고 매 프레임 속성만) ──
  const tape = sv("g");
  for (let d = -90; d <= 450; d += 5) {
    const x = d * U, big = d % 15 === 0, dm = ((d % 360) + 360) % 360;
    tape.appendChild(sv("line", { x1: x, x2: x, y1: big ? 0 : 3, y2: 6, stroke: CY, "stroke-width": ".6" }));
    if (big) { const l = { 0: "N", 90: "E", 180: "S", 270: "W" }[dm]; tape.appendChild(txt(x, 15, l || String(dm), { a: "middle", s: l ? 8 : 6, c: l ? PK : SUB })); }
  }
  const clipId = "bghud-cf" + Math.random().toString(36).slice(2, 7);
  const bcn = sv("g"), bedge = sv("g");
  // (제안 A-2) 테이프 양끝을 칼로 자르지 않고 마스크로 흐리게 — 가운데 80%만 선명
  const tapeWrap = sv("g", {}, [
    sv("defs", null, [
      sv("linearGradient", { id: clipId + "g", x1: -70, x2: 70, y1: 0, y2: 0, gradientUnits: "userSpaceOnUse" }, [
        sv("stop", { offset: 0, "stop-color": "#fff", "stop-opacity": 0 }), sv("stop", { offset: 0.2, "stop-color": "#fff" }),
        sv("stop", { offset: 0.8, "stop-color": "#fff" }), sv("stop", { offset: 1, "stop-color": "#fff", "stop-opacity": 0 }),
      ]),
      sv("mask", { id: clipId }, [sv("rect", { x: -70, y: -6, width: 140, height: 26, fill: `url(#${clipId}g)` })]),
    ]),
    sv("g", { mask: `url(#${clipId})` }, [tape, bcn]),
    bedge,
    sv("path", { d: "M0 -8 l-3 -5 h6z", fill: PK }),
  ]);
  // (제안 A-2 · B-1) 방위 숫자는 3자리 고정 — 칸을 둘러싼 챔퍼 베젤 안에
  const hdgBox = sv("path", { d: "M-30 -10 H30 L34 -6 V4 L30 8 H-30 L-34 4 V-6 Z", fill: "rgba(4,8,24,.55)", stroke: PK, "stroke-width": ".6" });
  const hdg = txt(0, 0, "방위 000°", { a: "middle", s: 8.5, w: 700, c: INK });
  const hdgG = sv("g", {}, [hdgBox, hdg]);
  // (제안 A-1 · 14) 중앙 링 — 방위(N) 제거: 링은 2초 관측 진행만, 방향은 위 테이프가 맡는다. 12개 짧은 기준 눈금 + 얇은 점선 링
  const ringTicks = sv("g");
  for (let i = 0; i < 12; i++) ringTicks.appendChild(sv("line", { x1: 0, x2: 0, y1: -42, y2: -37, stroke: CY, "stroke-width": ".8", transform: `rotate(${i * 30})` }));
  const dashRing = sv("circle", { cx: 0, cy: 0, r: 33, fill: "none", stroke: CY, "stroke-width": ".6", "stroke-dasharray": "4 8", opacity: ".55" });
  const C = 2 * Math.PI * 28;
  const arc = sv("circle", { cx: 0, cy: 0, r: 28, fill: "none", stroke: CY, "stroke-width": "2", "stroke-dasharray": C, "stroke-dashoffset": C, transform: "rotate(-90)" });
  const ringHint = txt(0, 42, "잠시 바라보기", { a: "middle", s: 7, c: INK });
  ringHint.setAttribute("class", "ko");
  const ringIn = sv("g", {}, [ringTicks, sv("circle", { cx: 0, cy: 0, r: 28, fill: "none", stroke: "rgba(79,227,255,.18)", "stroke-width": "2" }), dashRing, arc]);
  const ring = sv("g", { opacity: 0 }, [ringIn, ringHint]);
  const reticle = sv("g", {}, [sv("circle", { cx: 0, cy: 0, r: 1.6, fill: PK }), sv("path", { d: "M0 -8v5M0 3v5M-8 0h5M3 0h5", stroke: CY, "stroke-width": ".6", opacity: ".8" })]);
  const altClip = "bghud-al" + clipId, zmClip = "bghud-zm" + clipId;
  const altl = sv("g"), zml = sv("g");
  // (제안 A-4 · B-1) 고도 · 배율 눈금은 짧게(104 단위), 라벨은 한글, 현재값은 숫자 칸을 넓혀 굵게
  const altVal = txt(14, 0, "+0°", { s: 8.5, c: INK, w: 700 }), zmVal = txt(186, 0, "×1.0", { a: "end", s: 8.5, c: INK, w: 700 });
  const sides = sv("g", {}, [
    sv("clipPath", { id: altClip }, [sv("rect", { x: 0, y: -52, width: 44, height: 104 })]),
    sv("clipPath", { id: zmClip }, [sv("rect", { x: 156, y: -52, width: 44, height: 104 })]),
    sv("path", { d: "M14 -52v104", stroke: CY, "stroke-width": ".5", opacity: ".5" }), sv("g", { "clip-path": `url(#${altClip})` }, [altl]), sv("path", { d: "M12 0l-4 -2.6v5.2z", fill: PK }), txt(14, -58, "고도", { s: 6, c: SUB }), altVal,
    sv("path", { d: "M186 -52v104", stroke: CY, "stroke-width": ".5", opacity: ".5" }), sv("g", { "clip-path": `url(#${zmClip})` }, [zml]), sv("path", { d: "M188 0l4 -2.6v5.2z", fill: PK }), txt(186, -58, "배율", { a: "end", s: 6, c: SUB }), zmVal,
  ]);
  const skyName = txt(14, 0, "", { s: 8, c: INK, w: 600 }), clock = txt(186, 0, "--:--", { a: "end", s: 6.5, c: SUB });
  skyName.setAttribute("class", "ko");
  const foot = sv("g", {}, [txt(14, -12, "하늘", { s: 6, c: SUB }), skyName, txt(186, -12, "시각", { a: "end", s: 6, c: SUB }), clock]);
  svg.append(tapeWrap, hdgG, ring, reticle, sides, foot);

  // ── 정보 카드(F5 .pick) ──
  const kStar = h("span", "bghud-star"), kText = h("span"), name = h("h3"), toLine = h("p", "bghud-to"), zoomBtn = h("button", "bghud-btn", ["＋ 확대"], { type: "button" }), hintLine = h("p", "bghud-hn");
  const card = h("div", "bghud-card", [h("div", "bghud-k", [kStar, kText]), name, toLine, h("div", "bghud-btns", [zoomBtn]), hintLine]);
  root.append(card);
  // (11-09 운영자) 좌하단 맥박 신호 표시기 — 못 찾은 대상에 가까울수록 맥박이 빨라지고, 색은 빨강 → 주황 → 노랑 → 초록 → 파랑으로
  const pulseDot = h("i"), pulseRing = h("b"), pulseRing2 = h("b"), pulseLbl = h("span", null, ["신호"]);
  const pulse = h("div", "bghud-pulse", [h("div", "bghud-pulse__o", [pulseRing, pulseRing2, pulseDot]), pulseLbl]);
  root.append(pulse);
  let pulsePh = 0, focusK = 0, burstT = 0, burstCol = "79,227,255", sparks = [];
  let curTele = 1, ringInT = 0;
  zoomBtn.addEventListener("click", () => onZoom(curTele > 1.5 ? 1 : 6));
  document.body.appendChild(root);

  const st = createDwell();
  let W = 0, H = 0, dpr = 1, safeTop = 0, VH = 400, unit = 1, cardFor = null, cardInfo = null, revealT = 0, tintT = 0, tintCol = "", hintT = 0, firstHint = true, last = {};
  const probe = h("div", "bghud-probe"); root.appendChild(probe);
  function layout(w, hh) {
    W = w; H = hh; dpr = Math.min(window.devicePixelRatio || 1, 2);
    cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr);
    safeTop = probe.offsetHeight || 0;
    const sw = Math.min(W, HUD_MAX_W);   // 계기 폭 상한 — 가운데 정렬
    unit = sw / 200; VH = H / unit;
    svg.style.width = sw + "px"; svg.style.left = ((W - sw) / 2) + "px"; svg.style.right = "auto";
    svg.setAttribute("viewBox", `0 0 200 ${VH.toFixed(2)}`);
    foot.style.display = H < 500 ? "none" : "";   // (제안 3-6) 낮은 화면 — 하늘 · 시각 줄을 접는다
    const t0 = 34 + safeTop / unit;
    tapeWrap.setAttribute("transform", `translate(100,${t0.toFixed(2)})`);
    hdgG.setAttribute("transform", `translate(100,${(t0 + 28).toFixed(2)})`);
    last = {};
  }
  const set = (k, v, fn) => { if (last[k] !== v) { last[k] = v; fn(v); } };
  const clear = (el) => { while (el.firstChild) el.removeChild(el.firstChild); };

  function showCard(t, info) {
    cardFor = t; cardInfo = info; revealT = performance.now();
    kText.textContent = info.k || "";
    kStar.hidden = info.k !== "NEW";
    card.classList.toggle("is-new", info.k === "NEW");
    name.textContent = t.n;
    toLine.textContent = info.to || ""; toLine.hidden = !info.to;
    card.classList.add("is-on");
    if (info.fresh) { tintT = revealT; tintCol = t.col || "79,227,255"; }
    // (11-09 운영자 「해금 이펙트가 심심함」) 해금 · 탐험 완료는 즉시 터지는 연출 — 겹겹 고리 + 사방으로 튀는 불꽃 + 화면 섬광
    if (info.fresh && info.guide) {
      burstT = revealT; burstCol = t.col || "79,227,255";
      sparks = Array.from({ length: 44 }, (_, i) => ({ a: (i / 44) * Math.PI * 2 + Math.random() * 0.2, v: 0.5 + Math.random() * 0.9, l: 6 + Math.random() * 14 }));
    }
  }
  function hideCard() { if (!cardFor) return; cardFor = null; card.classList.remove("is-on"); }

  function glow(x, y, r, c) { const q = g.createRadialGradient(x, y, 0, x, y, r); q.addColorStop(0, c); q.addColorStop(1, "rgba(0,0,0,0)"); g.fillStyle = q; g.beginPath(); g.arc(x, y, r, 0, 7); g.fill(); }
  function drawTarget(t, p, k, now, project) {
    const [x, y] = p;
    if (t.draw === "saturn") {
      glow(x, y, 12 * k, "rgba(232,197,138,.35)");
      g.save(); g.translate(x, y); g.rotate(-0.35);
      g.strokeStyle = "rgba(232,197,138,.95)"; g.lineWidth = 1.2 * k; g.beginPath(); g.ellipse(0, 0, 9 * k, 3 * k, 0, Math.PI, 2 * Math.PI); g.stroke();
      g.fillStyle = "#d9a85e"; g.beginPath(); g.arc(0, 0, 4 * k, 0, 7); g.fill();
      g.beginPath(); g.ellipse(0, 0, 9 * k, 3 * k, 0, 0, Math.PI); g.stroke();
      g.restore();
    } else if (t.draw === "neb") {
      glow(x, y, 15 * k, "rgba(255,111,181,.55)"); glow(x + 3 * k, y - 2 * k, 10 * k, "rgba(79,227,255,.45)"); glow(x, y, 4 * k, "rgba(255,255,255,.9)");
    } else if (t.draw === "feat") {
      // 딥필드 · 달 궤도 사진 속 표식 — 찾기 전엔 사진 그대로(그림 없음), 찾은 뒤엔 옅은 고리
      if (t.found) { g.strokeStyle = `rgba(${t.col || "200,160,255"},.6)`; g.lineWidth = 0.8 * unit; g.beginPath(); g.arc(x, y, 6 * k, 0, 7); g.stroke(); g.beginPath(); g.arc(x, y, 9 * k, 0, 7); g.globalAlpha = 0.3; g.stroke(); g.globalAlpha = 1; }
    } else if (t.draw === "ymmt" && t.stars) {
      // (3단계 보상) YMMT 별자리 — 처음 한 번 anim 0 → 1 동안 선이 차례로 그어지고(유노 생일 장면과 같은 글자 모양), 그 뒤엔 옅게 늘 있다
      const P = t.stars.map((d) => project(d)), a = t.anim ?? 1, strong = a < 1;
      g.strokeStyle = `rgba(79,227,255,${strong ? 0.8 : 0.32})`; g.lineWidth = (strong ? 0.8 : 0.55) * unit; g.lineCap = "round";
      const n = t.lines.length * a;
      t.lines.forEach(([i, j], q) => { if (q >= n || !P[i] || !P[j]) return; const f = Math.min(1, n - q); g.beginPath(); g.moveTo(P[i][0], P[i][1]); g.lineTo(P[i][0] + (P[j][0] - P[i][0]) * f, P[i][1] + (P[j][1] - P[i][1]) * f); g.stroke(); });
      for (const q of P) { if (!q) continue; glow(q[0], q[1], (strong ? 5 : 3.5) * unit, `rgba(255,190,230,${strong ? 0.6 : 0.35})`); g.fillStyle = "#fff"; g.beginPath(); g.arc(q[0], q[1], 0.7 * unit, 0, 7); g.fill(); }
    } else if (t.draw === "zod" && t.stars) {
      const P = t.stars.map((d) => project(d));
      const on = cardFor === t ? Math.min(1, (now - revealT) / 800) : t.found ? 1 : 0;
      if (on > 0) {
        g.strokeStyle = `rgba(79,227,255,${cardFor === t ? 0.7 : 0.22})`; g.lineWidth = 0.6 * unit; g.lineCap = "round";
        const n = t.lines.length * on;
        t.lines.forEach(([a, b], i) => { if (i >= n || !P[a] || !P[b]) return; const f = Math.min(1, n - i); g.beginPath(); g.moveTo(P[a][0], P[a][1]); g.lineTo(P[a][0] + (P[b][0] - P[a][0]) * f, P[a][1] + (P[b][1] - P[a][1]) * f); g.stroke(); });
      }
      const sk = Math.pow(k, 0.5);
      for (const q of P) { if (!q) continue; glow(q[0], q[1], 4.5 * sk * unit, "rgba(190,215,255,.45)"); g.fillStyle = "#fff"; g.beginPath(); g.arc(q[0], q[1], 0.7 * sk * unit, 0, 7); g.fill(); }
    }
  }

  let clockS = -1;
  return {
    remove() { root.remove(); },
    /** 정보 카드가 떠 있나(조작 패널의 「다가가 보세요」 안내를 그동안 숨긴다) */
    get cardOn() { return !!cardFor; },
    /** 확인용(?bgdebug) — 잡기 상태 */
    get debug() { return { focus: st.focus?.id || null, v: +st.v.toFixed(2), lock: st.lock?.id || null, left: +st.left.toFixed(2), card: cardFor?.id || null }; },
    resize: layout,
    /** 배경 보기를 닫거나 패널이 뜨면 — 링 · 카드를 비운다 */
    reset() { resetDwell(st); hideCard(); },
    /**
     * 한 프레임. f = { active(보이기), interact(잡기 판정 — 성간 이동 중엔 false), dt, yawDeg, pitchDeg, tele, ppd(화면 px / 도),
     * fwd(시선 방향), project(dir → [x, y] | null, CSS px), targets([{ id, n, dir, tol, draw, col, found, below, stars?, lines? }]), sky(하늘 이름) }
     */
    update(f) {
      if (!W) layout(window.innerWidth, window.innerHeight);
      set("on", f.active, (v) => { root.classList.toggle("is-on", v); if (!v) { resetDwell(st); hideCard(); } });
      if (!f.active) return;
      const now = performance.now();
      curTele = f.tele;
      const cy = VH / 2;
      // ── 대상 · 잡기
      g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, W, H);
      const tint = tintT ? Math.max(0, 1 - (now - tintT) / 1600) : 0;
      if (tint > 0) { const q = g.createRadialGradient(W / 2, H / 2, 0, W / 2, H / 2, Math.max(W, H) * 0.7); q.addColorStop(0, `rgba(${tintCol},${0.4 * tint})`); q.addColorStop(1, "rgba(0,0,0,0)"); g.fillStyle = q; g.fillRect(0, 0, W, H); }
      // (11-09 운영자) 대상에 시선이 잡히면(링이 차는 동안 · 잡힌 뒤) 옅은 그라데이션 필터로 「이곳을 보고 있음」을 알린다 — 둘레가 살짝 어두워지고 대상 둘레가 은은히 물든다
      const fo = f.interact ? (st.lock || st.focus) : null, foP = fo ? f.project(fo.dir) : null;
      focusK += ((foP ? (st.lock ? 1 : 0.35 + 0.65 * st.v) : 0) - focusK) * (1 - Math.exp(-f.dt / 0.18));
      if (focusK > 0.01) {
        const cx0 = foP ? foP[0] : W / 2, cy0 = foP ? foP[1] : H / 2, col = (fo && fo.col) || "79,227,255";
        const vg = g.createRadialGradient(cx0, cy0, Math.min(W, H) * 0.12, cx0, cy0, Math.max(W, H) * 0.85);
        vg.addColorStop(0, "rgba(4,8,24,0)"); vg.addColorStop(1, `rgba(4,8,24,${0.34 * focusK})`);
        g.fillStyle = vg; g.fillRect(0, 0, W, H);
        const gl2 = g.createRadialGradient(cx0, cy0, 0, cx0, cy0, 120 * unit);
        gl2.addColorStop(0, `rgba(${col},${0.2 * focusK})`); gl2.addColorStop(1, `rgba(${col},0)`);
        g.fillStyle = gl2; g.fillRect(cx0 - 130 * unit, cy0 - 130 * unit, 260 * unit, 260 * unit);
      }
      // 해금 · 탐험 완료 연출(1.8초)
      const bu = burstT ? (now - burstT) / 1800 : 2;
      if (bu < 1) {
        const bx = W / 2, by = H / 2, R = Math.hypot(W, H) * 0.55;
        const fl = REDUCE.matches ? 0 : Math.max(0, 1 - bu / 0.28); if (fl > 0) { g.fillStyle = `rgba(${burstCol},${0.42 * fl})`; g.fillRect(0, 0, W, H); }
        for (let r = 0; r < 3; r++) { const u = Math.min(1, Math.max(0, (bu - r * 0.12) / 0.7)); if (u <= 0 || u >= 1) continue; const e = 1 - (1 - u) * (1 - u); g.strokeStyle = `rgba(${r === 1 ? "255,255,255" : burstCol},${0.85 * (1 - u)})`; g.lineWidth = (3 - r) * unit; g.beginPath(); g.arc(bx, by, e * R, 0, 7); g.stroke(); }
        g.lineCap = "round"; g.lineWidth = 0.9 * unit;
        for (const sp of REDUCE.matches ? [] : sparks) { const u = Math.min(1, bu / 0.85), e = 1 - (1 - u) * (1 - u), r0 = e * R * 0.8 * sp.v, r1 = r0 + sp.l * unit * (1 - u); g.strokeStyle = `rgba(255,255,255,${0.9 * (1 - u)})`; g.beginPath(); g.moveTo(bx + Math.cos(sp.a) * r0, by + Math.sin(sp.a) * r0); g.lineTo(bx + Math.cos(sp.a) * r1, by + Math.sin(sp.a) * r1); g.stroke(); }
      }
      const k = Math.pow(Math.min(f.tele, 10), 0.75) * unit;
      const rv = (now - revealT) / 1000;
      for (const t of f.targets) {
        const p = f.project(t.dir);
        if (!p || t.below) continue;
        drawTarget(t, p, k, now, f.project);
        if (cardFor === t && rv < 1.2) { g.strokeStyle = `rgba(${t.col || "79,227,255"},${0.8 * (1 - rv / 1.2)})`; g.lineWidth = 1.2 * unit; g.beginPath(); g.arc(p[0], p[1], (4 + rv / 1.2 * 60) * unit, 0, 7); g.stroke(); }
        // 못 찾은 대상 가까이(15° 안)에선 반짝임 — 힌트
        if (!t.found && f.interact && t.draw !== "photo") {
          const d = sepDeg(f.fwd, t.dir);
          if (d < 15) { const tw = (1 - d / 15) * (0.5 + 0.5 * Math.sin(now / 140 + t.dir[0] * 9)), s = (5 + 4 * tw) * unit; g.strokeStyle = `rgba(255,111,181,${0.85 * tw})`; g.lineWidth = 0.6 * unit; g.beginPath(); g.moveTo(p[0] - s, p[1]); g.lineTo(p[0] + s, p[1]); g.moveTo(p[0], p[1] - s); g.lineTo(p[0], p[1] + s); g.stroke(); }
        }
      }
      let hit = null;
      if (f.interact) {
        hit = pickHit(f.fwd, f.targets.filter((t) => !t.below));
        const sepLock = st.lock ? sepDeg(f.fwd, st.lock.dir) : 0;
        const hadFocus = !!st.focus;
        const got = stepDwell(st, hit, sepLock, f.dt);
        if (!hadFocus && st.focus && firstHint) { firstHint = false; hintT = now; }
        if (got) { const info = onLock(got) || {}; showCard(got, info); }
        if (cardFor && (!st.lock || st.lock.id !== cardFor.id)) hideCard();
      } else { resetDwell(st); hideCard(); }
      // 잡힘 꺾쇠
      const lt = st.lock || hit;
      if (lt) {
        const p = f.project(lt.dir);
        if (p) {
          // (제안 D-2) 바라보는 동안 꺾쇠가 바깥에서 조여들고(시안 시작 → 대상 둘레), 잡히면 핑크로 바뀐다
          const base = (lt.draw === "zod" ? 22 : lt.draw === "photo" ? 30 : lt.draw === "feat" ? 12 : 10) * Math.max(1, Math.pow(Math.min(f.tele, 10), 0.6)) * unit;
          const ease = 1 - Math.pow(1 - (st.lock ? 1 : st.v), 3), s = base * (1.45 - 0.45 * ease), a = 5 * unit;
          g.strokeStyle = st.lock ? PK : CY; g.lineWidth = 1 * unit * 0.8;
          for (const [sx, sy] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) { g.beginPath(); g.moveTo(p[0] + sx * s, p[1] + sy * (s - a)); g.lineTo(p[0] + sx * s, p[1] + sy * s); g.lineTo(p[0] + sx * (s - a), p[1] + sy * s); g.stroke(); }
        }
      }
      // ── 링
      const v = st.lock ? 1 : st.v;
      // (제안 D-1) 링이 켜질 때 0.35초 동안 1.18 → 1 로 수축하며 대상에 달라붙고, 점선 링은 천천히 돈다(움직임 줄이기면 정지)
      set("ringOn", !!(st.focus || st.lock) && f.interact, (on) => { ring.setAttribute("opacity", on ? 1 : 0); if (on) ringInT = now; });
      const sc = REDUCE.matches ? 1 : 1 + 0.18 * Math.max(0, 1 - (now - ringInT) / 350);
      ringIn.setAttribute("transform", `scale(${sc.toFixed(3)})`);
      if (!REDUCE.matches && (st.focus || st.lock)) dashRing.setAttribute("transform", `rotate(${((now * 0.02) % 360).toFixed(1)})`);
      set("ringT", cy.toFixed(1), (yy) => { ring.setAttribute("transform", `translate(100,${yy})`); reticle.setAttribute("transform", `translate(100,${yy})`); sides.setAttribute("transform", `translate(0,${yy})`); foot.setAttribute("transform", `translate(0,${(Number(yy) + 116).toFixed(1)})`); altVal.setAttribute("y", 60); zmVal.setAttribute("y", 60); });
      set("arc", (C * (1 - v)).toFixed(1), (o) => arc.setAttribute("stroke-dashoffset", o));
      set("hint", hintT && now - hintT < 2200 ? Math.min(1, (2200 - (now - hintT)) / 400).toFixed(2) : "0", (o) => ringHint.setAttribute("opacity", o));
      // ── 방위 테이프 · 힌트 점
      const yaw = ((f.yawDeg % 360) + 360) % 360;
      const yq = Math.round(yaw / 0.15) * 0.15;   // (제안 D · E) 0.15° 데드밴드 — 손떨림에 테이프 숫자가 떨지 않게
      set("tape", yq.toFixed(2), (y) => { tape.setAttribute("transform", `translate(${(-y * U).toFixed(2)},0)`); hdg.textContent = `방위 ${String(Math.round(y) % 360).padStart(3, "0")}°`; });
      const bs = beacons(yaw, f.fwd, f.targets, 21);
      const bKey = bs.map((b) => `${b.dx.toFixed(1)},${b.alpha.toFixed(2)},${b.below ? 1 : 0}`).join("|");
      set("bcn", bKey, () => {
        clear(bcn); clear(bedge);
        let L = false, R = false;
        for (const b of bs) {
          if (b.out < 0 && !b.below) L = true; if (b.out > 0 && !b.below) R = true;
          if (b.out) continue;
          bcn.appendChild(sv("rect", { x: -1.6, y: -1.6, width: 3.2, height: 3.2, transform: `translate(${(b.dx * U).toFixed(1)},9) rotate(45)`, opacity: b.alpha.toFixed(2), ...(b.below ? { fill: "none", stroke: SUB, "stroke-width": ".6" } : { fill: PK }) }));
        }
        if (L) bedge.appendChild(sv("path", { d: "M-76 6l-4 3 4 3", fill: "none", stroke: PK, "stroke-width": ".9" }));
        if (R) bedge.appendChild(sv("path", { d: "M76 6l4 3-4 3", fill: "none", stroke: PK, "stroke-width": ".9" }));
      });
      // ── 맥박 신호(좌하단): 못 찾은 가장 가까운 대상까지 각도 → 빠르기 · 색
      let near = Infinity;
      if (f.interact && !cardFor) for (const t of f.targets) { if (t.found || t.noBeacon || t.below) continue; near = Math.min(near, Math.max(0, sepDeg(f.fwd, t.dir) - (t.tol || 0))); }
      const pOn = near < Infinity;
      set("pulseOn", pOn, (v) => pulse.classList.toggle("is-on", v));
      if (pOn) {
        const kk = 1 - Math.min(1, near / 90), rate = 0.6 + 4.4 * kk * kk;   // 멀면 초당 0.6 번 · 코앞이면 5 번
        pulsePh += f.dt * rate;
        const ph = pulsePh % 1, beat = REDUCE.matches ? 0.5 : Math.exp(-ph * 7) + 0.55 * Math.exp(-Math.pow((ph - 0.22) * 9, 2));   // 쿵 · 딱 두 박(움직임 줄이기면 정지)
        const hue = Math.round(215 * (1 - kk));   // 0 빨강 → 30 주황 → 55 노랑 → 120 초록 → 215 파랑(멀수록). kk 는 가까울수록 1 이라 뒤집어 쓴다
        pulse.style.setProperty("--pc", `hsl(${hue} 95% 58%)`);
        pulseDot.style.transform = `scale(${(0.8 + 0.45 * beat).toFixed(2)})`;
        // (제안 D-3) 가까우면(20° 안) 두 번째 파동이 반 박자 늦게 겹쳐 퍼진다(소나 핑). 글자로도 거리를 준다
        const ph2 = (ph + 0.5) % 1, near20 = near < 20 ? 1 : 0;
        pulseRing.style.transform = `scale(${(1 + 1.6 * ph).toFixed(2)})`; pulseRing.style.opacity = REDUCE.matches ? "0.5" : (0.7 * (1 - ph)).toFixed(2);
        pulseRing2.style.transform = `scale(${(1 + 1.6 * ph2).toFixed(2)})`; pulseRing2.style.opacity = REDUCE.matches ? "0" : (near20 * 0.5 * (1 - ph2)).toFixed(2);
        set("pulseTxt", Math.round(near), (d) => { pulseLbl.textContent = `신호 · ${d}°`; });
      }
      // ── ALT · ZOOM 눈금(화면과 함께 움직임 — F5)
      const ppdU = f.ppd / unit, stp = [0.1, 0.2, 0.5, 1, 2, 5].find((s) => s * ppdU >= 10) || 5, m = stp === 5 ? 3 : 5;
      set("alt", `${f.pitchDeg.toFixed(2)}|${ppdU.toFixed(3)}`, () => {
        clear(altl);
        for (let i = Math.floor((f.pitchDeg - 90 / ppdU) / stp); i * stp <= f.pitchDeg + 90 / ppdU; i++) {
          const r = i * stp, yy = -(r - f.pitchDeg) * ppdU, big = ((i % m) + m) % m === 0, zero = i === 0;
          altl.appendChild(sv("line", { x1: 14, x2: big ? 21 : 17.5, y1: yy.toFixed(2), y2: yy.toFixed(2), stroke: zero ? PK : CY, "stroke-width": big ? ".7" : ".5", opacity: big ? ".9" : ".55" }));
          if (big) altl.appendChild(txt(23, (yy + 2).toFixed(2), (r > 0 ? "+" : "") + (stp < 1 ? r.toFixed(1) : Math.round(r)), { s: 5.5, c: zero ? PK : SUB }));
        }
        altVal.textContent = (f.pitchDeg >= 0 ? "+" : "") + Math.round(f.pitchDeg) + "°";
      });
      set("zm", f.tele.toFixed(3), () => {
        clear(zml);
        const lz = Math.log(f.tele), K = 60, zy = (z) => -(Math.log(z) - lz) * K;
        for (const z of ZM) { const yy = zy(z); if (yy > -90 && yy < 90) zml.appendChild(sv("line", { x1: 186, x2: 182.5, y1: yy.toFixed(2), y2: yy.toFixed(2), stroke: CY, "stroke-width": ".5", opacity: ".55" })); }
        for (const z of ZT) { const yy = zy(z); if (yy < -90 || yy > 90) continue; zml.appendChild(sv("line", { x1: 186, x2: 179, y1: yy.toFixed(2), y2: yy.toFixed(2), stroke: CY, "stroke-width": ".7", opacity: ".9" })); zml.appendChild(txt(177, (yy + 2).toFixed(2), "×" + z, { a: "end", s: 5.5, c: SUB })); }
        zmVal.textContent = "×" + f.tele.toFixed(f.tele < 10 ? 1 : 0);
        zoomBtn.textContent = f.tele > 1.5 ? "－ 원래대로" : "＋ 확대";
        hintLine.textContent = f.tele > 1.5 ? "두 손가락으로 오므려도 됩니다" : "두 손가락으로 벌려도 됩니다";
      });
      // ── 아래 SKY · 시각(카드가 뜨면 숨김)
      set("sky", f.sky, (s) => { skyName.textContent = s; });
      set("foot", !cardFor, (on) => { foot.setAttribute("opacity", on ? 1 : 0); });   // 카드가 떠도 고도 · 배율 숫자는 남긴다(제안 A-4 — 배율을 계속 보게). 하늘 · 시각 줄만 카드 때 접는다
      const sec = Math.floor(Date.now() / 1000);
      if (sec !== clockS) { clockS = sec; const n = new Date(Date.now() + 9 * 36e5), p = (x) => String(x).padStart(2, "0"); clock.textContent = `${p(n.getUTCHours())}:${p(n.getUTCMinutes())}`; }
    },
  };
}
