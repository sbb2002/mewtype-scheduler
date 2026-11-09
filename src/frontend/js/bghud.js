// bghud.js — (bg-dome 해금 2단계) 배경 보기 중 화면에 고정되는 「시선 HUD」 — F5 시안(devpapers ref/bg-dome/hud/hud_f5.html) 디자인 그대로.
// 위 방위 테이프(HDG · 못 찾은 대상 방향 분홍 점) · 가운데 시선 링(대상을 2초 바라보면 잡힘) · 양옆 ALT · ZOOM 눈금(화면과 함께 움직임) · 아래 SKY · KST,
// 잡히면 아래 정보 카드(이름 · 무엇이 열렸는지 · [＋ 확대]). 대상 그림(토성 표식 · 성운 · 별자리)은 돔 위 2D 캔버스에 그린다 — 셰이더 하늘에는 없다.
// 계산은 bghudlogic.js(순수), 해금 규칙은 bgunlock.js, 언제 켜고 무엇을 넘기는지는 bgdomegl.js. 모양 = css/bgpanel.css(.bghud).
// 고정 문구 · 숫자만 쓰고 모두 createElement(NS) · textContent 로 만든다(innerHTML 금지).

import { pickHit, sepDeg, createDwell, stepDwell, resetDwell, beacons } from "./bghudlogic.js";

const NS = "http://www.w3.org/2000/svg";
const CY = "#4fe3ff", PK = "#ff6fb5", SUB = "#a9bad0", INK = "#eef6ff";
const U = 3.2;   // 방위 테이프 1° 당 단위(F5 와 같음, 화면 폭 200 단위)
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
  const root = h("div", "bghud", [], { "aria-hidden": "true" });
  const cv = h("canvas", "bghud-sky");
  const g = cv.getContext("2d");
  const svg = sv("svg", { class: "bghud-svg", preserveAspectRatio: "xMidYMin meet" });
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
  const tapeWrap = sv("g", {}, [
    sv("clipPath", { id: clipId }, [sv("rect", { x: -70, y: -6, width: 140, height: 26 })]),
    sv("g", { "clip-path": `url(#${clipId})` }, [tape, bcn]),
    bedge,
    sv("path", { d: "M0 -8 l-3 -5 h6z", fill: PK }),
  ]);
  const hdg = txt(100, 0, "HDG 0°", { a: "middle", s: 9, w: 600, c: INK });
  const ringTicks = sv("g");
  for (let i = 0; i < 72; i++) { const big = i % 6 === 0; ringTicks.appendChild(sv("line", { x1: 0, x2: 0, y1: big ? -58 : -55, y2: -50, stroke: big ? CY : SUB, "stroke-width": big ? ".9" : ".5", transform: `rotate(${i * 5})`, opacity: big ? 1 : 0.6 })); }
  const C = 2 * Math.PI * 44;
  const arc = sv("circle", { cx: 0, cy: 0, r: 44, fill: "none", stroke: CY, "stroke-width": "2.4", "stroke-dasharray": C, "stroke-dashoffset": C, transform: "rotate(-90)" });
  const ringHint = txt(0, 62, "잠시 바라보기", { a: "middle", s: 7, c: INK });
  const ring = sv("g", { opacity: 0 }, [ringTicks, txt(0, -62, "N", { a: "middle", s: 8, c: PK, w: 600 }), sv("circle", { cx: 0, cy: 0, r: 44, fill: "none", stroke: "rgba(79,227,255,.18)", "stroke-width": "2.4" }), arc, ringHint]);
  const reticle = sv("g", {}, [sv("circle", { cx: 0, cy: 0, r: 1.6, fill: PK }), sv("path", { d: "M0 -8v5M0 3v5M-8 0h5M3 0h5", stroke: CY, "stroke-width": ".6", opacity: ".8" })]);
  const altClip = "bghud-al" + clipId, zmClip = "bghud-zm" + clipId;
  const altl = sv("g"), zml = sv("g");
  const altVal = txt(14, 0, "+0°", { s: 8, c: INK, w: 600 }), zmVal = txt(186, 0, "×1.0", { a: "end", s: 8, c: INK, w: 600 });
  const sides = sv("g", {}, [
    sv("clipPath", { id: altClip }, [sv("rect", { x: 0, y: -80, width: 44, height: 160 })]),
    sv("clipPath", { id: zmClip }, [sv("rect", { x: 156, y: -80, width: 44, height: 160 })]),
    sv("path", { d: "M14 -80v160", stroke: CY, "stroke-width": ".5", opacity: ".5" }), sv("g", { "clip-path": `url(#${altClip})` }, [altl]), sv("path", { d: "M12 0l-4 -2.6v5.2z", fill: PK }), txt(14, -86, "ALT", { s: 6, c: SUB }), altVal,
    sv("path", { d: "M186 -80v160", stroke: CY, "stroke-width": ".5", opacity: ".5" }), sv("g", { "clip-path": `url(#${zmClip})` }, [zml]), sv("path", { d: "M188 0l4 -2.6v5.2z", fill: PK }), txt(186, -86, "ZOOM", { a: "end", s: 6, c: SUB }), zmVal,
  ]);
  const skyName = txt(14, 0, "", { s: 8, c: INK, w: 600 }), clock = txt(186, 0, "KST --:--:--", { a: "end", s: 6.5, c: SUB });
  const foot = sv("g", {}, [txt(14, -12, "SKY", { s: 6, c: SUB }), skyName, txt(186, -12, "NOW", { a: "end", s: 6, c: SUB }), clock]);
  svg.append(tapeWrap, hdg, ring, reticle, sides, foot);

  // ── 정보 카드(F5 .pick) ──
  const kStar = h("span", "bghud-star"), kText = h("span"), name = h("h3"), toLine = h("p", "bghud-to"), zoomBtn = h("button", "bghud-btn", ["＋ 확대"], { type: "button" }), hintLine = h("p", "bghud-hn");
  const card = h("div", "bghud-card", [h("div", "bghud-k", [kStar, kText]), name, toLine, h("div", "bghud-btns", [zoomBtn]), hintLine]);
  root.append(card);
  // (11-09 운영자) 좌하단 맥박 신호 표시기 — 못 찾은 대상에 가까울수록 맥박이 빨라지고, 색은 빨강 → 주황 → 노랑 → 초록 → 파랑으로
  const pulseDot = h("i"), pulseRing = h("b"), pulseLbl = h("span", null, ["SIGNAL"]);
  const pulse = h("div", "bghud-pulse", [h("div", "bghud-pulse__o", [pulseRing, pulseDot]), pulseLbl]);
  root.append(pulse);
  let pulsePh = 0, focusK = 0, burstT = 0, burstCol = "79,227,255", sparks = [];
  let curTele = 1;
  zoomBtn.addEventListener("click", () => onZoom(curTele > 1.5 ? 1 : 6));
  document.body.appendChild(root);

  const st = createDwell();
  let W = 0, H = 0, dpr = 1, safeTop = 0, VH = 400, unit = 1, cardFor = null, cardInfo = null, revealT = 0, tintT = 0, tintCol = "", hintT = 0, firstHint = true, last = {};
  const probe = h("div", "bghud-probe"); root.appendChild(probe);
  function layout(w, hh) {
    W = w; H = hh; dpr = Math.min(window.devicePixelRatio || 1, 2);
    cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr);
    safeTop = probe.offsetHeight || 0;
    unit = W / 200; VH = H / unit;
    svg.setAttribute("viewBox", `0 0 200 ${VH.toFixed(2)}`);
    const t0 = 34 + safeTop / unit;
    tapeWrap.setAttribute("transform", `translate(100,${t0.toFixed(2)})`);
    hdg.setAttribute("y", (t0 + 28).toFixed(2));
    last = {};
  }
  const set = (k, v, fn) => { if (last[k] !== v) { last[k] = v; fn(v); } };
  const clear = (el) => { while (el.firstChild) el.removeChild(el.firstChild); };

  function showCard(t, info) {
    cardFor = t; cardInfo = info; revealT = performance.now();
    kText.textContent = info.k || "";
    kStar.hidden = info.k !== "NEW";
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
        const fl = Math.max(0, 1 - bu / 0.28); if (fl > 0) { g.fillStyle = `rgba(${burstCol},${0.42 * fl})`; g.fillRect(0, 0, W, H); }
        for (let r = 0; r < 3; r++) { const u = Math.min(1, Math.max(0, (bu - r * 0.12) / 0.7)); if (u <= 0 || u >= 1) continue; const e = 1 - (1 - u) * (1 - u); g.strokeStyle = `rgba(${r === 1 ? "255,255,255" : burstCol},${0.85 * (1 - u)})`; g.lineWidth = (3 - r) * unit; g.beginPath(); g.arc(bx, by, e * R, 0, 7); g.stroke(); }
        g.lineCap = "round"; g.lineWidth = 0.9 * unit;
        for (const sp of sparks) { const u = Math.min(1, bu / 0.85), e = 1 - (1 - u) * (1 - u), r0 = e * R * 0.8 * sp.v, r1 = r0 + sp.l * unit * (1 - u); g.strokeStyle = `rgba(255,255,255,${0.9 * (1 - u)})`; g.beginPath(); g.moveTo(bx + Math.cos(sp.a) * r0, by + Math.sin(sp.a) * r0); g.lineTo(bx + Math.cos(sp.a) * r1, by + Math.sin(sp.a) * r1); g.stroke(); }
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
          const s = (lt.draw === "zod" ? 22 : lt.draw === "photo" ? 30 : lt.draw === "feat" ? 12 : 10) * Math.max(1, Math.pow(Math.min(f.tele, 10), 0.6)) * unit, a = 5 * unit;
          g.strokeStyle = PK; g.lineWidth = 1 * unit * 0.8;
          for (const [sx, sy] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) { g.beginPath(); g.moveTo(p[0] + sx * s, p[1] + sy * (s - a)); g.lineTo(p[0] + sx * s, p[1] + sy * s); g.lineTo(p[0] + sx * (s - a), p[1] + sy * s); g.stroke(); }
        }
      }
      // ── 링
      const v = st.lock ? 1 : st.v;
      set("ringOn", !!(st.focus || st.lock) && f.interact, (on) => ring.setAttribute("opacity", on ? 1 : 0));
      set("ringT", cy.toFixed(1), (yy) => { ring.setAttribute("transform", `translate(100,${yy})`); reticle.setAttribute("transform", `translate(100,${yy})`); sides.setAttribute("transform", `translate(0,${yy})`); foot.setAttribute("transform", `translate(0,${(Number(yy) + 116).toFixed(1)})`); altVal.setAttribute("y", 92); zmVal.setAttribute("y", 92); });
      set("arc", (C * (1 - v)).toFixed(1), (o) => arc.setAttribute("stroke-dashoffset", o));
      set("hint", hintT && now - hintT < 2200 ? Math.min(1, (2200 - (now - hintT)) / 400).toFixed(2) : "0", (o) => ringHint.setAttribute("opacity", o));
      // ── 방위 테이프 · 힌트 점
      const yaw = ((f.yawDeg % 360) + 360) % 360;
      set("tape", yaw.toFixed(1), (y) => { tape.setAttribute("transform", `translate(${(-y * U).toFixed(1)},0)`); hdg.textContent = `HDG ${Math.round(y) % 360}°`; });
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
        const ph = pulsePh % 1, beat = Math.exp(-ph * 7) + 0.55 * Math.exp(-Math.pow((ph - 0.22) * 9, 2));   // 쿵 · 딱 두 박
        const hue = Math.round(215 * kk);   // 0 빨강 → 30 주황 → 55 노랑 → 120 초록 → 215 파랑(가까울수록)
        pulse.style.setProperty("--pc", `hsl(${hue} 95% 58%)`);
        pulseDot.style.transform = `scale(${(0.8 + 0.45 * beat).toFixed(2)})`;
        pulseRing.style.transform = `scale(${(1 + 1.6 * ph).toFixed(2)})`; pulseRing.style.opacity = (0.7 * (1 - ph)).toFixed(2);
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
      set("foot", !cardFor, (on) => { foot.setAttribute("opacity", on ? 1 : 0); altVal.setAttribute("opacity", on ? 1 : 0); zmVal.setAttribute("opacity", on ? 1 : 0); });   // 카드가 뜨면 아래 정보 · 배율 숫자를 숨긴다(F5)
      const sec = Math.floor(Date.now() / 1000);
      if (sec !== clockS) { clockS = sec; const n = new Date(Date.now() + 9 * 36e5), p = (x) => String(x).padStart(2, "0"); clock.textContent = `KST ${p(n.getUTCHours())}:${p(n.getUTCMinutes())}:${p(n.getUTCSeconds())}`; }
    },
  };
}
