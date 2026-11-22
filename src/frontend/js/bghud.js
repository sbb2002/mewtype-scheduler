// bghud.js — (bg-dome 해금 2단계) 배경 보기 중 화면에 고정되는 「시선 HUD」.
// (cyan 재구성, 11-23 운영자 「모션그래픽 스타일 그대로」) 모양 = HUD 모션그래픽 시안(아티팩트 「HUD Motion Study」 Cyan)을 Canvas 하나로 그대로 옮겼다.
//   · 가운데 다이얼(화면 가운데 = 시선): 바깥 눈금 링은 실제 방위에 맞춰 돈다(N · E · S · W) · 끊어진 호 링 역회전 · 흐르는 점선 링 ·
//     게이지 호 = 대상을 2초 바라보는 진행(SCAN → LOCK) · 궤도 점 · 레이더 스윕(블립 = 시야 60° 안의 아직 못 찾은 대상, 스윕이 지나갈 때 켜짐) · 가운데 세모 셋
//   · 위 방위 테이프(가운데 주황 세모, 못 찾은 대상 = 주황 마름모 · 테이프 밖이면 끝 화살표)
//   · 패널: SIGNAL(못 찾은 가장 가까운 대상까지 각도로 막대 · 파형 · PROX) · TELEMETRY(ALT · ZOOM · HDG) · LOG(실제 사건 + 센서 값 흐름)
//   · 표적 꺾쇠: 바라보는 동안 회전하며 조여들고, 잡히면 주황 + 리더선 + 「LOCK 이름」 · 방위/고도
//   · 화면 네 모서리 꺾쇠 · T+(배경 보기를 연 뒤 흐른 시간) · KST 시각 · 어두운 막 · 점 격자 · 주사선(CSS) · 가끔 글리치 · 켤 때 부팅 연출
// 잡힘 정보 카드(이름 · 무엇이 열렸는지 · [＋ 확대])와 좌하단 맥박 신호는 DOM(css/bgpanel.css). 계산은 bghudlogic.js(순수), 해금 규칙은 bgunlock.js, 언제 켜고 무엇을 넘기는지는 bgdomegl.js.
// 고정 문구 · 숫자만 쓰고 DOM 은 createElement · textContent 로 만든다(innerHTML 금지). 웹 글꼴은 받지 않는다 — 글꼴 이름은 있으면 쓰고 없으면 시스템 글꼴.

import { pickHit, sepDeg, createDwell, stepDwell, resetDwell, beacons } from "./bghudlogic.js";

const REDUCE = window.matchMedia("(prefers-reduced-motion: reduce)");
const TAU = Math.PI * 2, DEG = Math.PI / 180;
const CYR = "94,242,255", HOTR = "255,138,61";   // 시안 팔레트 Cyan — CSS .bghud 의 --hud-cy · --hud-hot 과 같은 값
const A = (a) => `rgba(${CYR},${a})`, HOT = (a) => `rgba(${HOTR},${a})`, INK = (a) => `rgba(207,230,234,${a})`;
// 글꼴 = 시안과 같은 JetBrains Mono · Chakra Petch(라틴 부분만, assets/fonts — css/bgpanel.css @font-face 「HUD Mono」 · 「HUD Chakra」). 한글은 시스템 글꼴로 넘어간다
const MONO = '"HUD Mono", ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace';
const DISP = '"HUD Chakra", "Bahnschrift", "DIN Alternate", "Roboto Condensed", "Noto Sans KR", system-ui, sans-serif';
const KO = '"Noto Sans KR", system-ui, sans-serif';
const HUD_MAX_W = 440;   // 대상 그림 · 꺾쇠 크기 단위(unit)의 기준 폭 — 예전과 같다
const clamp01 = (v) => (v < 0 ? 0 : v > 1 ? 1 : v);
const easeOut = (p) => 1 - Math.pow(1 - p, 3);
const wob = (x) => Math.sin(x) * 0.5 + Math.sin(x * 2.31 + 1.7) * 0.3 + Math.sin(x * 5.13 + 0.3) * 0.2;
const pad = (n, k = 2) => String(n).padStart(k, "0");

function h(tag, cls, kids, attrs) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (attrs) for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (kids) for (const c of kids) e.append(c);
  return e;
}
/** 대상 id → 4자리 16진 부호(레이더 블립 · 로그 표기. 못 찾은 대상 이름을 미리 드러내지 않으려고) */
function code(t) { let x = 7; for (const c of String(t.id)) x = (x * 31 + c.charCodeAt(0)) | 0; return ((x >>> 0) & 0xffff).toString(16).toUpperCase().padStart(4, "0"); }
function azAlt(d) { return [((Math.atan2(d[0], d[2]) / DEG) % 360 + 360) % 360, Math.asin(Math.max(-1, Math.min(1, d[1]))) / DEG]; }

/**
 * HUD 를 만든다. onLock(t) = 대상이 잡힘 → { k, to, fresh } 를 돌려준다(해금 · 저장 · 알림은 부르는 쪽),
 * onZoom(x) = [＋ 확대] · [－ 원래대로](x = 망원 배율, 1 = 원래대로).
 */
export function createHud({ onLock, onZoom }) {
  const root = h("div", "bghud");
  // 캔버스 글자는 글꼴을 스스로 불러오지 않는다 — HUD 를 만들 때(= UFO 돔) 미리 받아 둔다. 못 받으면 시스템 글꼴
  try { document.fonts?.load('600 12px "HUD Chakra"').catch(() => {}); document.fonts?.load('12px "HUD Mono"').catch(() => {}); } catch { /* 글꼴 API 없음 */ }
  const cv = h("canvas", "bghud-sky");
  cv.setAttribute("aria-hidden", "true");
  const g = cv.getContext("2d");
  root.append(cv);

  // ── 정보 카드 ──
  const kStar = h("span", "bghud-star"), kText = h("span"), name = h("h3"), toLine = h("p", "bghud-to"), zoomBtn = h("button", "bghud-btn", ["+ ZOOM"], { type: "button" }), hintLine = h("p", "bghud-hn");
  const hd = h("div", "bghud-hd", [h("span", "bghud-cap", ["TARGET"]), h("div", "bghud-k", [kStar, kText])]);
  const bd = h("div", "bghud-bd", [name, toLine, h("div", "bghud-btns", [zoomBtn]), hintLine]);
  const card = h("div", "bghud-card", [hd, bd, h("span", "bghud-x bghud-x--tr"), h("span", "bghud-x bghud-x--bl")]);
  root.append(card);
  // (11-09 운영자) 좌하단 맥박 신호 표시기 — 못 찾은 대상에 가까울수록 맥박이 빨라지고, 색은 빨강 → 주황 → 노랑 → 초록 → 파랑으로
  const pulseDot = h("i"), pulseRing = h("b"), pulseRing2 = h("b"), pulseLbl = h("span", "bghud-sig__l", ["SIGNAL"]);
  const bars = Array.from({ length: 5 }, () => h("i")), barsEl = h("div", "bghud-sig__bars", bars);
  const pulse = h("div", "bghud-pulse", [h("div", "bghud-pulse__o", [pulseRing, pulseRing2, pulseDot]), pulseLbl, barsEl]);
  root.append(pulse);
  let pulsePh = 0, focusK = 0, burstT = 0, burstCol = "79,227,255", sparks = [];
  let curTele = 1;
  zoomBtn.addEventListener("click", () => onZoom(curTele > 1.5 ? 1 : 6));
  document.body.appendChild(root);

  const st = createDwell();
  let W = 0, H = 0, dpr = 1, safeTop = 0, unit = 1, L = null, cardFor = null, revealT = 0, tintT = 0, tintCol = "", hintT = 0, firstHint = true, last = {};
  const probe = h("div", "bghud-probe"); root.appendChild(probe);

  // 끊어진 호 링 조각 — 고정 시드로 한 번만(시안과 같은 식)
  const segs = [];
  { let seed = 7; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647; for (let a = 0; a < TAU;) { const len = 0.08 + rnd() * 0.5; segs.push([a, len, rnd() < 0.2]); a += len + 0.04 + rnd() * 0.12; } }

  // 배경 보기 한 번의 상태
  let onT = 0, nextBeat = 0, beatI = 0, lastSky = null, lastFocusId = null, lastLockId = null, nextGlitch = 0, glitchUntil = 0;
  const logs = [], pings = [], blipLit = new Map();
  let wasOn = false, calmT0 = 0, calmMs = 0;   // calm = 스토리 발견 장면 동안 눈금이 잦아드는 구간
  function pushLog(s, warn = false) {
    const hex = ((Date.now() / 7 + logs.length * 977) & 0xffffff).toString(16).toUpperCase().padStart(6, "0");
    logs.push({ s: `${hex} ${s}`, warn });
    if (logs.length > 40) logs.shift();
  }
  // 로그는 처음부터 차 있게(시안처럼) — 배경 보기를 다시 열어도 지우지 않고 이어 쓴다
  for (const s of ["BOOT SENSOR ARRAY", "CALIB GYRO OK", "CALIB OPTIC OK", "LINK DOME VIEW", "PARITY OK", "SYNC KST"]) pushLog(s);

  function layout(w, hh) {
    W = w; H = hh; dpr = Math.min(window.devicePixelRatio || 1, 2);
    cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr);
    safeTop = probe.offsetHeight || 0;
    unit = Math.min(W, HUD_MAX_W) / 200;
    const wide = W >= 760;
    if (wide) {
      // 시안 넓은 화면 배치 — 다이얼 가운데, 패널 좌우
      const pw = Math.min(250, W * 0.2);
      L = { wide, R: Math.min(W * 0.21, H * 0.36), left: { x: 28, y: H * 0.17, w: pw, h: H * 0.66 }, right: { x: W - 28 - pw, y: H * 0.17, w: pw, h: H * 0.66 }, log: null };
    } else {
      // 폰 — 다이얼 · 테이프 · 모서리 표기만(빈 공간을 남긴다). 패널 대신 테이프 아래 한 줄(ALT · ZOOM · HDG). 다이얼은 가운데(= 시선)
      L = { wide, R: Math.max(80, Math.min(W * 0.4, H * 0.27, (H / 2 - safeTop - 104) / 1.12)), left: null, right: null, log: null, strip: true };
    }
    last = {};
  }
  const set = (k, v, fn) => { if (last[k] !== v) { last[k] = v; fn(v); } };

  function showCard(t, info) {
    cardFor = t; revealT = performance.now();
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

  // ── 그리기 도우미(시안과 같은 꼴) ──
  function glow(x, y, r, c) { const q = g.createRadialGradient(x, y, 0, x, y, r); q.addColorStop(0, c); q.addColorStop(1, "rgba(0,0,0,0)"); g.fillStyle = q; g.beginPath(); g.arc(x, y, r, 0, 7); g.fill(); }
  function text(s, x, y, size, col, align = "left", font = MONO) { g.font = `${size}px ${font}`; g.fillStyle = col; g.textAlign = align; g.textBaseline = "middle"; g.fillText(s, x, y); }
  function brackets(x, y, w, hh, s, col, lw = 1.5) {
    g.strokeStyle = col; g.lineWidth = lw; g.beginPath();
    g.moveTo(x, y + s); g.lineTo(x, y); g.lineTo(x + s, y);
    g.moveTo(x + w - s, y); g.lineTo(x + w, y); g.lineTo(x + w, y + s);
    g.moveTo(x + w, y + hh - s); g.lineTo(x + w, y + hh); g.lineTo(x + w - s, y + hh);
    g.moveTo(x + s, y + hh); g.lineTo(x, y + hh); g.lineTo(x, y + hh - s);
    g.stroke();
  }
  function panelFrame(r, title, p) {
    g.fillStyle = `rgba(4,8,11,${0.5 * p})`; g.fillRect(r.x, r.y, r.w, r.h);
    g.fillStyle = A(0.03 * p); g.fillRect(r.x, r.y, r.w, r.h);
    brackets(r.x, r.y, r.w, r.h, 12 * p, A(0.6 * p));
    text(title, r.x + 10, r.y + 14, 10, A(0.85 * p), "left", DISP);
    g.fillStyle = A(0.25 * p); g.fillRect(r.x + 10, r.y + 24, (r.w - 20) * p, 1);
  }

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
      // (bg-dome 시나리오) 솔로 곡 힌트 — t.hint = 멤버 색("r,g,b"). 못 찾은 별자리의 선이 멤버 색으로 옅게 숨 쉬고 별빛도 그 색(bgmusic.js · bgdomegl.js hudTargets)
      if (t.hint && on === 0) {
        const br = REDUCE.matches ? 0.3 : 0.18 + 0.16 * (0.5 - 0.5 * Math.cos(now / 1100));
        g.strokeStyle = `rgba(${t.hint},${br.toFixed(3)})`; g.lineWidth = 0.7 * unit; g.lineCap = "round";
        t.lines.forEach(([a, b]) => { if (!P[a] || !P[b]) return; g.beginPath(); g.moveTo(P[a][0], P[a][1]); g.lineTo(P[b][0], P[b][1]); g.stroke(); });
      }
      const sk = Math.pow(k, 0.5), starGlow = t.hint && !t.found ? `rgba(${t.hint},.5)` : "rgba(190,215,255,.45)";
      for (const q of P) { if (!q) continue; glow(q[0], q[1], 4.5 * sk * unit, starGlow); g.fillStyle = "#fff"; g.beginPath(); g.arc(q[0], q[1], 0.7 * sk * unit, 0, 7); g.fill(); }
    }
    g.lineCap = "butt";
  }

  // ── 시안 부품 ──
  function drawBackdrop(pS) {
    // 어두운 막 · 가장자리 그늘 · 32px 점 격자 — 시안의 어두운 바탕을 하늘 위에 옅게만 깐다(하늘의 유메미타 색은 살린다 — 11-23 운영자: 하늘을 어둡게 덮는 안은 롤백)
    g.fillStyle = `rgba(4,8,11,${0.3 * pS})`; g.fillRect(0, 0, W, H);
    const vg = g.createRadialGradient(W / 2, H / 2, Math.min(W, H) * 0.35, W / 2, H / 2, Math.hypot(W, H) * 0.6);
    vg.addColorStop(0, "rgba(0,0,0,0)"); vg.addColorStop(1, `rgba(0,0,0,${0.5 * pS})`);
    g.fillStyle = vg; g.fillRect(0, 0, W, H);
    g.fillStyle = A(0.07 * pS);
    for (let y = 16; y < H; y += 32) for (let x = 16; x < W; x += 32) g.fillRect(x, y, 1, 1);
  }
  function drawFrame(p) { brackets(8, 8 + safeTop, W - 16, H - 16 - safeTop, 22 * p, A(0.5 * p)); }

  function drawTape(yaw, f, p) {
    if (p <= 0) return;
    const w = Math.min(W * 0.5, 520) * p, x0 = W / 2, y = safeTop + 30, ppd = 4, half = w / 2;
    const fa = (x) => { const u = Math.abs(x - x0) / half; return u > 1 ? 0 : u < 0.7 ? 1 : 1 - (u - 0.7) / 0.3; };
    const names = { 0: "N", 45: "NE", 90: "E", 135: "SE", 180: "S", 225: "SW", 270: "W", 315: "NW" };
    const start = Math.floor((yaw - half / ppd) / 5) * 5;
    for (let d = start; d < yaw + half / ppd + 5; d += 5) {
      const x = x0 + (d - yaw) * ppd, a = fa(x); if (a <= 0) continue;
      const dn = ((d % 360) + 360) % 360, major = dn % 15 === 0;
      g.fillStyle = A((major ? 0.7 : 0.3) * a); g.fillRect(x, y, 1, major ? 9 : 5);
      if (names[dn] !== undefined) text(names[dn], x, y + 18, 11, dn === 0 ? HOT(0.95 * a) : A(0.95 * a), "center", DISP);
      else if (major) text(pad(dn, 3), x, y + 18, 8, A(0.5 * a), "center");
    }
    // 못 찾은 대상 방향 — 테이프 안이면 주황 마름모, 밖이면 끝 화살표(지평선 아래는 흐린 빈 마름모)
    let lOut = false, rOut = false;
    for (const b of beacons(yaw, f.fwd, f.targets, half / ppd)) {
      if (b.out < 0 && !b.below) lOut = true; if (b.out > 0 && !b.below) rOut = true;
      if (b.out) continue;
      g.save(); g.translate(x0 + b.dx * ppd, y - 7); g.rotate(Math.PI / 4);
      if (b.below) { g.strokeStyle = `rgba(95,127,150,${b.alpha})`; g.lineWidth = 1; g.strokeRect(-2.5, -2.5, 5, 5); } else { g.fillStyle = HOT(b.alpha); g.fillRect(-2.5, -2.5, 5, 5); }
      g.restore();
    }
    g.strokeStyle = HOT(0.9); g.lineWidth = 1.2; g.beginPath();
    if (lOut) { g.moveTo(x0 - half - 4, y); g.lineTo(x0 - half - 9, y + 4); g.lineTo(x0 - half - 4, y + 8); }
    if (rOut) { g.moveTo(x0 + half + 4, y); g.lineTo(x0 + half + 9, y + 4); g.lineTo(x0 + half + 4, y + 8); }
    g.stroke();
    g.beginPath(); g.moveTo(x0, y - 2); g.lineTo(x0 - 5, y - 10); g.lineTo(x0 + 5, y - 10); g.closePath(); g.fillStyle = HOT(p); g.fill();
  }

  function drawDial(f, yaw, v, T, ts, boot, rd) {
    const cx = W / 2, cy = H / 2, R = L.R, da = 1;   // 시안처럼 늘 100% 밝기(대상과의 관계는 게이지 · 꺾쇠 · 주황으로만)
    g.save(); g.translate(cx, cy);
    // 바깥 눈금 링 — 실제 방위(위 = 보는 방향). 2° 마다 눈금, 30° 마다 숫자(N · E · S · W 는 글자)
    const pA = boot(0.15, 1.1);
    g.beginPath();
    for (let i = 0; i < 180 * pA; i++) {
      const d = i * 2, a = (d - yaw - 90) * DEG;
      const len = d % 30 === 0 ? R * 0.07 : d % 10 === 0 ? R * 0.04 : R * 0.02;
      g.moveTo(Math.cos(a) * R, Math.sin(a) * R); g.lineTo(Math.cos(a) * (R - len), Math.sin(a) * (R - len));
    }
    g.strokeStyle = A(0.55 * da); g.lineWidth = 1; g.stroke();
    const fs = Math.max(9, R * 0.045);
    for (let d = 0; d < 360 * pA; d += 30) {
      const a = (d - yaw - 90) * DEG, l = { 0: "N", 90: "E", 180: "S", 270: "W" }[d];
      text(l || pad(d, 3), Math.cos(a) * R * 1.08, Math.sin(a) * R * 1.08, l ? fs + 2 : fs, l === "N" ? HOT(0.9 * da) : l ? INK(0.85 * da) : A(0.6 * da), "center", l ? DISP : MONO);
    }
    // 끊어진 호 링(역회전)
    const pB = boot(0.35, 1.0);
    g.save(); g.rotate(-T * 0.13);
    for (const [a, len, hot] of segs) {
      if (a > TAU * pB) break;
      g.beginPath(); g.arc(0, 0, R * 0.88, a, a + len * pB);
      g.strokeStyle = hot ? HOT(0.85 * da) : A(0.7 * da); g.lineWidth = hot ? 4 : 2.5; g.stroke();
    }
    g.restore();
    // 점선 링(흐름)
    const pC = boot(0.5, 0.8);
    g.setLineDash([2, 7]); g.lineDashOffset = -T * 12;
    g.beginPath(); g.arc(0, 0, R * 0.8, -Math.PI / 2, -Math.PI / 2 + TAU * pC);
    g.strokeStyle = A(0.45 * da); g.lineWidth = 1; g.stroke(); g.setLineDash([]);
    // 게이지 호 = 바라보기 진행(2초에 가득 → LOCK)
    const pD = boot(0.7, 1.2), val = v * pD;
    g.beginPath(); g.arc(0, 0, R * 0.73, -Math.PI * 0.75, Math.PI * 0.75);
    g.strokeStyle = A(0.1 * da + 0.05); g.lineWidth = 6; g.stroke();
    if (val > 0.001) {
      g.beginPath(); g.arc(0, 0, R * 0.73, -Math.PI * 0.75, -Math.PI * 0.75 + Math.PI * 1.5 * val);
      g.strokeStyle = val > 0.78 ? HOT(0.9) : A(0.85); g.lineWidth = 6; g.stroke();
    }
    const ga = -Math.PI * 0.75 + Math.PI * 1.5 * val;
    g.beginPath(); g.arc(Math.cos(ga) * R * 0.73, Math.sin(ga) * R * 0.73, 4, 0, TAU); g.fillStyle = INK(0.95 * pD); g.fill();
    const gs = st.lock ? "LOCK 100%" : st.focus ? `SCAN ${(v * 100).toFixed(1)}%` : "SCAN IDLE";
    text(gs, 0, R * 0.665, Math.max(10, R * 0.055), st.lock ? HOT(0.95 * pD) : INK(0.85 * pD * da), "center", DISP);
    // 궤도 점
    const oa = T * 0.9;
    for (let k = 0; k < 14; k++) {
      const a = oa - k * 0.035;
      g.beginPath(); g.arc(Math.cos(a) * R * 0.94, Math.sin(a) * R * 0.94, k === 0 ? 3 : 2, 0, TAU);
      g.fillStyle = A((1 - k / 14) * 0.8 * pA * da); g.fill();
    }
    // 레이더
    const pE = boot(0.9, 0.9), rr = R * 0.6;
    g.save();
    g.beginPath(); g.arc(0, 0, rr * pE, 0, TAU); g.clip();
    g.fillStyle = A(0.035); g.fill();
    g.strokeStyle = A(0.14 * da); g.lineWidth = 1;
    for (const k of [0.33, 0.66]) { g.beginPath(); g.arc(0, 0, rr * k, 0, TAU); g.stroke(); }
    g.beginPath(); g.moveTo(-rr, 0); g.lineTo(rr, 0); g.moveTo(0, -rr); g.lineTo(0, rr); g.stroke();
    const sw = rd ? -Math.PI / 2 : T * 1.3;
    for (let k = 0; k < 36; k++) {
      g.beginPath(); g.moveTo(0, 0); g.arc(0, 0, rr, sw - (k + 1) * 0.03, sw - k * 0.03); g.closePath();
      g.fillStyle = A(0.28 * (1 - k / 36) ** 2 * da); g.fill();
    }
    g.beginPath(); g.moveTo(0, 0); g.lineTo(Math.cos(sw) * rr, Math.sin(sw) * rr); g.strokeStyle = A(0.9 * da); g.lineWidth = 1.5; g.stroke();
    g.restore();
    g.beginPath(); g.arc(0, 0, rr * pE, 0, TAU); g.strokeStyle = A(0.5 * da); g.lineWidth = 1; g.stroke();
    // 블립 = 시야 60° 안의 아직 못 찾은 대상(화면에서 그 방향 · 각도 거리). 스윕이 지나가면 켜졌다 3초에 걸쳐 꺼진다
    const swn = ((sw % TAU) + TAU) % TAU;
    if (f.interact) for (const t of f.targets) {
      if (t.found || t.noBeacon || t.below) continue;
      const p = f.project(t.dir); if (!p) continue;
      const sep = sepDeg(f.fwd, t.dir); if (sep > 60) continue;
      const ang = Math.atan2(p[1] - cy, p[0] - cx), r = rr * sep / 60;
      const d = ((swn - ang) % TAU + TAU) % TAU;
      if (d < 0.12) blipLit.set(t.id, ts);
      const age = rd ? 0.9 : ts - (blipLit.get(t.id) ?? -9);
      if (age > 3) continue;
      const al = (1 - age / 3) * pE, x = Math.cos(ang) * r, y = Math.sin(ang) * r;
      g.beginPath(); g.arc(x, y, 3, 0, TAU); g.fillStyle = A(al); g.fill();
      g.beginPath(); g.arc(x, y, 3 + age * 6, 0, TAU); g.strokeStyle = A(al * 0.5); g.lineWidth = 1; g.stroke();
      text(code(t), x + 7, y - 7, 9, A(al * 0.8));
    }
    // 가운데 세모 셋
    g.save(); g.rotate(-T * 0.6);
    g.strokeStyle = INK(0.8 * pE); g.lineWidth = 1.2;
    for (let k = 0; k < 3; k++) { g.rotate(TAU / 3); g.beginPath(); g.moveTo(10, 0); g.lineTo(18, -4); g.lineTo(18, 4); g.closePath(); g.stroke(); }
    g.restore();
    // 처음 한 번 뜨는 안내
    const hintA = hintT && ts * 1000 - hintT < 2200 ? Math.min(1, (2200 - (ts * 1000 - hintT)) / 400) : 0;
    if (hintA > 0) text("HOLD GAZE", 0, -R * 0.665, 11, INK(0.95 * hintA), "center", DISP);
    g.restore();
  }

  function drawReticle(f, ts, rd, hit) {
    const lt = st.lock || hit; if (!lt) return;
    const p = f.project(lt.dir); if (!p) return;
    const base = (lt.draw === "zod" ? 22 : lt.draw === "photo" ? 30 : lt.draw === "feat" ? 12 : 10) * Math.max(1, Math.pow(Math.min(f.tele, 10), 0.6)) * unit;
    const ease = 1 - Math.pow(1 - (st.lock ? 1 : st.v), 3), s = base * (1.45 - 0.45 * ease);
    const locked = !!st.lock, col = locked ? HOT(0.95) : A(0.85);
    // 바라보는 동안 회전하며 조여든다(시안 표적 꺾쇠) — 잡히면 0°
    g.save(); g.translate(p[0], p[1]); if (!locked && !rd) g.rotate((1 - ease) * Math.PI * 0.5);
    brackets(-s, -s, s * 2, s * 2, Math.max(7, 0.25 * s), col, 1.5);
    g.restore();
    if (locked) {
      const side = p[0] > W - 170 ? -1 : 1, lx = p[0] + side * (s + 14), ly = p[1] - s - 18;
      g.beginPath(); g.moveTo(p[0] + side * s * 0.75, p[1] - s * 0.75); g.lineTo(lx, ly); g.lineTo(lx + side * 96, ly);
      g.strokeStyle = HOT(0.7); g.lineWidth = 1; g.stroke();
      const blink = rd ? 1 : Math.floor(ts * 4) % 2 === 0 ? 1 : 0.35, al = side > 0 ? "left" : "right";
      const [az, alt] = azAlt(lt.dir);
      const l1 = `LOCK ${lt.n}`, l2 = `AZ ${az.toFixed(1).padStart(5, "0")} · ALT ${alt < 0 ? "-" : "+"}${Math.abs(alt).toFixed(1)}`;
      // 대상은 보통 다이얼 한가운데라 글자가 링과 겹친다 — 글자 뒤에 어두운 판(시안 패널 바탕)을 깐다
      g.font = `11px ${DISP}`; const w1 = g.measureText(l1).width; g.font = `9px ${MONO}`; const bw = Math.max(w1, g.measureText(l2).width) + 12;
      g.fillStyle = "rgba(4,8,11,.78)"; g.fillRect(side > 0 ? lx - 6 : lx - bw + 6, ly - 18, bw, 36);
      text(l1, lx, ly - 9, 11, HOT(blink), al, DISP);
      text(l2, lx, ly + 9, 9, HOT(0.75), al);
    } else {
      text("ACQUIRING", p[0], p[1] + s + 12, 9, A(0.7), "center");
    }
  }

  function drawPings(ts) {
    for (let i = pings.length - 1; i >= 0; i--) {
      const pg = pings[i], age = ts - pg.t;
      if (age > 1.2) { pings.splice(i, 1); continue; }
      for (const off of [0, 0.15]) {
        const a = age - off; if (a < 0) continue;
        g.beginPath(); g.arc(pg.x, pg.y, 6 + a * 110, 0, TAU); g.strokeStyle = HOT((1 - a / 1.2) * 0.7); g.lineWidth = 1; g.stroke();
      }
    }
  }

  function drawSignal(r, p, T, kk, near) {
    if (!r || p <= 0) return;
    panelFrame(r, "SIGNAL · 16 BAND", p);
    const x = r.x + 10, w = r.w - 20, wide = L.wide;
    const bh = wide ? Math.min(110, r.h * 0.36) : 40, cells = wide ? 12 : 8, y0 = r.y + 34;
    const n = 16, gap = wide ? 3 : 2, bw = (w - gap * (n - 1)) / n, chh = (bh - (cells - 1) * 2) / cells;
    for (let i = 0; i < n; i++) {
      // 막대 = 늘 출렁이고(시안) 못 찾은 대상에 가까울수록(kk) 높아진다
      const vv = clamp01(0.42 + 0.3 * kk + 0.45 * wob(T * 2.2 + i * 0.7) * Math.cos(i * 0.25)) * p;
      const on = Math.round(vv * cells);
      for (let c = 0; c < cells; c++) {
        g.fillStyle = c < on ? (c >= cells - 2 ? HOT(0.85) : A(0.35 + (c / cells) * 0.6)) : A(0.06);
        g.fillRect(x + i * (bw + gap), y0 + bh - (c + 1) * chh - c * 2, bw, chh);
      }
    }
    let y = y0 + bh + 18;
    if (wide) {
      const wh = Math.min(70, r.h * 0.22);
      text("OSC · PROX", x, y, 9, A(0.6 * p));
      const mid = y + 10 + wh / 2;
      g.fillStyle = A(0.12 * p); g.fillRect(x, mid, w, 1);
      g.beginPath();
      for (let k = 0; k <= w * p; k += 2) {
        const u = k / w, yy = mid + Math.sin(u * 18 - T * (3 + 6 * kk)) * Math.sin(u * Math.PI) * wh * (0.12 + 0.24 * kk) + wob(u * 40 + T * 9) * wh * 0.06;
        k === 0 ? g.moveTo(x + k, yy) : g.lineTo(x + k, yy);
      }
      g.strokeStyle = A(0.9 * p); g.lineWidth = 1.3; g.stroke(); g.lineWidth = 1;
      y = mid + wh / 2 + 22;
    }
    if (y + 16 > r.y + r.h) return;
    text(`PROX ${near < Infinity ? pad(Math.round(near), 3) + "°" : "---"}`, x, y, 9, A(0.6 * p));
    const sn = 20, sg = (w - (sn - 1) * 2) / sn;
    for (let i = 0; i < sn; i++) { g.fillStyle = i / sn < kk * p ? (i > 15 ? HOT(0.85) : A(0.7)) : A(0.08); g.fillRect(x + i * (sg + 2), y + 8, sg, 5); }
  }

  function drawTelemetry(r, p, rows, withLog) {
    if (!r || p <= 0) return;
    panelFrame(r, "TELEMETRY", p);
    const x = r.x + 10, w = r.w - 20, big = L.wide ? 22 : 15;
    let y = r.y + (L.wide ? 44 : 40);
    for (const [k, v, u] of rows) {
      text(k, x, y, 9, A(0.55 * p));
      text(v, x + w - (L.wide ? 34 : 26), y, big, INK(0.95 * p), "right", DISP);
      text(u, x + w, y, 8, A(0.55 * p), "right");
      y += big + (L.wide ? 12 : 9);
    }
    if (withLog) { g.fillStyle = A(0.2 * p); g.fillRect(x, y - 4, w, 1); drawLogLines(x, y + 4, w, r.y + r.h - y - 8, p); }
  }
  function drawLogLines(x, y, w, hh, p) {
    const fs = L.wide ? 10 : 9, lh = fs + 6, lines = Math.max(0, Math.floor(hh / lh)), maxC = Math.floor(w / (fs * 0.6));
    const shown = logs.slice(-lines);
    shown.forEach((e, i) => {
      const age = (shown.length - 1 - i) / Math.max(1, lines), al = (1 - age * 0.85) * p;
      const s = (i === shown.length - 1 && Math.floor(performance.now() / 333) % 2 ? e.s + " _" : e.s).slice(0, maxC);
      text(s, x, y + 6 + i * lh, fs, e.warn ? HOT(al) : A(al * 0.9));
    });
  }

  function drawCorners(ts, sky, p) {
    const tt = Math.max(0, ts - onT), fr = Math.floor((tt % 1) * 24);
    // T+ = 배경 보기를 연 뒤 흐른 시간(왼쪽 위 「‹ 예고보드」 버튼 아래)
    text(`T+ ${pad(Math.floor(tt / 3600))}:${pad(Math.floor(tt / 60) % 60)}:${pad(Math.floor(tt) % 60)}:${pad(fr)}`, 18, safeTop + 70, 10, A(0.75 * p));
    const n = new Date(Date.now() + 9 * 36e5), clk = `KST ${pad(n.getUTCHours())}:${pad(n.getUTCMinutes())}:${pad(n.getUTCSeconds())}`;
    g.font = `10px ${MONO}`; const tw = g.measureText(clk).width;
    const on = REDUCE.matches || Math.floor(ts * 1.5) % 2 === 0;
    g.beginPath(); g.arc(W - 22 - tw - 9, safeTop + 24, 3.5, 0, TAU); g.fillStyle = HOT(on ? p : 0.2 * p); g.fill();
    text(clk, W - 22, safeTop + 24, 10, A(0.75 * p), "right");
    if (L.wide) {
      text(`SECTOR · ${sky}`, 22, H - 22, 9, A(0.45 * p));
      text(`FRAME ${pad(Math.floor(tt * 24), 6)}`, W - 22, H - 22, 9, A(0.45 * p), "right");
    }
  }

  function glitch() {
    for (let i = 0; i < 4; i++) {
      const sy = Math.random() * H, sh = 3 + Math.random() * 18, off = (Math.random() - 0.5) * 24;
      g.drawImage(cv, 0, sy * dpr, cv.width, sh * dpr, off, sy, W, sh);
    }
    g.fillStyle = A(0.05); g.fillRect(0, Math.random() * H, W, 2);
  }

  return {
    remove() { root.remove(); document.documentElement.classList.remove("bghud-on"); },
    /** 정보 카드가 떠 있나(조작 패널의 「다가가 보세요」 안내를 그동안 숨긴다) */
    get cardOn() { return !!cardFor; },
    get zodiacCard() { return !!cardFor?.zod; },
    /** 확인용(?bgdebug) — 잡기 상태 */
    get debug() { return { focus: st.focus?.id || null, v: +st.v.toFixed(2), lock: st.lock?.id || null, left: +st.left.toFixed(2), card: cardFor?.id || null }; },
    resize: layout,
    /** (스토리 「다시, 이 하늘」) 지금부터 ms 동안 눈금 · 패널을 잦아들게 — 지구와 곡에 집중. 움직임 줄이기여도 투명도만 바뀐다 */
    calm(ms = 2600) { calmT0 = performance.now() / 1000; calmMs = ms; },
    /** 배경 보기를 닫거나 패널이 뜨면 — 링 · 카드를 비운다 */
    reset() { resetDwell(st); hideCard(); root.classList.remove("is-targeted"); },
    /**
     * 한 프레임. f = { active(보이기), interact(잡기 판정 — 성간 이동 중엔 false), dt, yawDeg, pitchDeg, tele, zoomR(뒤로 물러선 거리 0 ~ 0.6, 없으면 0), ppd(화면 px / 도),
     * fwd(시선 방향), project(dir → [x, y] | null, CSS px), targets([{ id, n, dir, tol, draw, col, found, below, stars?, lines? }]), sky(하늘 이름) }
     */
    update(f) {
      if (!W) layout(window.innerWidth, window.innerHeight);
      const ts = performance.now() / 1000;
      // 켜짐 · 꺼짐은 set 캐시와 따로 기억한다 — layout(크기 바뀜)이 캐시를 비워도 부팅 연출이 다시 돌지 않게
      if (f.active !== wasOn) {
        wasOn = f.active;
        root.classList.toggle("is-on", f.active);
        document.documentElement.classList.toggle("bghud-on", f.active);   // 시선 HUD 가 켜져 있음(CSS 훅)
        if (!f.active) { resetDwell(st); hideCard(); }
        else {
          // 켤 때마다 부팅 연출(로그는 이어 쓴다)
          onT = ts; pings.length = 0; blipLit.clear(); lastSky = null; lastFocusId = null; lastLockId = null;
          pushLog("BOOT SENSOR ARRAY"); nextGlitch = ts + 4;
        }
      }
      if (!f.active) { root.classList.remove("is-targeted"); return; }
      const now = ts * 1000, rd = REDUCE.matches, T = rd ? 0 : ts;
      const boot = (d, dur) => (rd ? 1 : easeOut(clamp01((ts - onT - d) / dur)));
      curTele = f.tele;
      g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, W, H);
      drawBackdrop(boot(0, 0.5));
      // ── 해금 물듦 · 시선 필터 · 해금 연출(예전과 같음)
      const tint = tintT ? Math.max(0, 1 - (now - tintT) / 1600) : 0;
      if (tint > 0) { const q = g.createRadialGradient(W / 2, H / 2, 0, W / 2, H / 2, Math.max(W, H) * 0.7); q.addColorStop(0, `rgba(${tintCol},${0.4 * tint})`); q.addColorStop(1, "rgba(0,0,0,0)"); g.fillStyle = q; g.fillRect(0, 0, W, H); }
      // (11-09 운영자) 대상에 시선이 잡히면 둘레가 살짝 어두워지고 대상 둘레가 은은히 물든다
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
      const bu = burstT ? (now - burstT) / 1800 : 2;
      if (bu < 1) {
        const bx = W / 2, by = H / 2, R = Math.hypot(W, H) * 0.55;
        const fl = rd ? 0 : Math.max(0, 1 - bu / 0.28); if (fl > 0) { g.fillStyle = `rgba(${burstCol},${0.42 * fl})`; g.fillRect(0, 0, W, H); }
        for (let r = 0; r < 3; r++) { const u = Math.min(1, Math.max(0, (bu - r * 0.12) / 0.7)); if (u <= 0 || u >= 1) continue; const e = 1 - (1 - u) * (1 - u); g.strokeStyle = `rgba(${r === 1 ? "255,255,255" : burstCol},${0.85 * (1 - u)})`; g.lineWidth = (3 - r) * unit; g.beginPath(); g.arc(bx, by, e * R, 0, 7); g.stroke(); }
        g.lineCap = "round"; g.lineWidth = 0.9 * unit;
        for (const sp of rd ? [] : sparks) { const u = Math.min(1, bu / 0.85), e = 1 - (1 - u) * (1 - u), r0 = e * R * 0.8 * sp.v, r1 = r0 + sp.l * unit * (1 - u); g.strokeStyle = `rgba(255,255,255,${0.9 * (1 - u)})`; g.beginPath(); g.moveTo(bx + Math.cos(sp.a) * r0, by + Math.sin(sp.a) * r0); g.lineTo(bx + Math.cos(sp.a) * r1, by + Math.sin(sp.a) * r1); g.stroke(); }
        g.lineCap = "butt";
      }
      // ── 대상 그림 · 못 찾은 대상 가까이(15° 안) 반짝임
      const k = Math.pow(Math.min(f.tele, 10), 0.75) * unit;
      const rv = (now - revealT) / 1000;
      for (const t of f.targets) {
        const p = f.project(t.dir);
        if (!p || t.below) continue;
        drawTarget(t, p, k, now, f.project);
        if (cardFor === t && rv < 1.2) { g.strokeStyle = `rgba(${t.col || "79,227,255"},${0.8 * (1 - rv / 1.2)})`; g.lineWidth = 1.2 * unit; g.beginPath(); g.arc(p[0], p[1], (4 + rv / 1.2 * 60) * unit, 0, 7); g.stroke(); }
        if (!t.found && f.interact && t.draw !== "photo") {
          const d = sepDeg(f.fwd, t.dir);
          if (d < 15) { const tw = (1 - d / 15) * (0.5 + 0.5 * Math.sin(now / 140 + t.dir[0] * 9)), s = (5 + 4 * tw) * unit; g.strokeStyle = HOT(0.85 * tw); g.lineWidth = 0.6 * unit; g.beginPath(); g.moveTo(p[0] - s, p[1]); g.lineTo(p[0] + s, p[1]); g.moveTo(p[0], p[1] - s); g.lineTo(p[0], p[1] + s); g.stroke(); }
        }
      }
      // ── 잡기(판정 규칙은 bghudlogic — 그대로)
      let hit = null;
      if (f.interact) {
        hit = pickHit(f.fwd, f.targets.filter((t) => !t.below));
        const sepLock = st.lock ? sepDeg(f.fwd, st.lock.dir) : 0;
        const hadFocus = !!st.focus;
        const got = stepDwell(st, hit, sepLock, f.dt);
        if (!hadFocus && st.focus && firstHint) { firstHint = false; hintT = now; }
        if (got) {
          const info = onLock(got) || {}; showCard(got, info);
          const gp = f.project(got.dir); if (gp) pings.push({ x: gp[0], y: gp[1], t: ts });
        }
        if (cardFor && (!st.lock || st.lock.id !== cardFor.id)) hideCard();
      } else { resetDwell(st); hideCard(); }
      root.classList.toggle("is-targeted", !!(st.focus || st.lock));
      // ── 로그 — 실제 사건(하늘 · 바라보기 · 잡힘 · 놓침) + 센서 값 흐름
      if (f.sky !== lastSky) { lastSky = f.sky; pushLog(`SKY ${f.sky}`); }
      const fid = !st.lock && st.focus ? st.focus.id : null;
      if (fid && fid !== lastFocusId) pushLog(`SCAN ${code(st.focus)}`);
      lastFocusId = fid;
      const lid = st.lock ? st.lock.id : null;
      if (lid && lid !== lastLockId) pushLog(`LOCK ${st.lock.n}`, true);
      else if (!lid && lastLockId) pushLog("LOST TARGET", true);
      lastLockId = lid;
      const yaw = ((f.yawDeg % 360) + 360) % 360;
      const zv = f.tele > 1.001 ? f.tele : 1 - Math.max(0, Math.min(0.6, f.zoomR || 0));   // 표시용 배율 — 물러선 구간은 1 − zoomR(예전과 같은 지표)
      const altS = `${f.pitchDeg < 0 ? "-" : "+"}${Math.abs(f.pitchDeg).toFixed(1)}`;
      if (ts > nextBeat) {
        nextBeat = ts + 0.25 + Math.random() * 0.4;   // 시안과 같은 빠르기
        const lines = [`GYRO HDG ${yaw.toFixed(1).padStart(5, "0")}`, `GYRO ALT ${altS}`, `OPTIC ZOOM x${zv.toFixed(2)}`, `TRK ${f.targets.filter((t) => !t.found && !t.noBeacon).length} OPEN`];
        pushLog(lines[beatI++ % lines.length]);
      }
      // 못 찾은 가장 가까운 대상까지 각도(맥박 신호 · SIGNAL 패널)
      let near = Infinity;
      if (f.interact && !cardFor) for (const t of f.targets) { if (t.found || t.noBeacon || t.below) continue; near = Math.min(near, Math.max(0, sepDeg(f.fwd, t.dir) - (t.tol || 0))); }
      const kk = near < Infinity ? 1 - Math.min(1, near / 90) : 0;
      // ── 시안 HUD 층
      const v = st.lock ? 1 : st.v;
      // (스토리 발견 장면) 눈금 · 패널이 calm(ms) 동안 잦아든다 — 0.15 까지 빠르게 내려갔다 끝에서 되돌아온다. 꺾쇠 · 대상 · 카드는 그대로
      const cu = calmMs ? (ts - calmT0) / (calmMs / 1000) : 1;
      const calmA = cu >= 1 || cu < 0 ? 1 : cu < 0.15 ? 1 - (cu / 0.15) * 0.85 : cu > 0.75 ? 0.15 + ((cu - 0.75) / 0.25) * 0.85 : 0.15;
      g.globalAlpha = calmA;
      drawFrame(boot(0, 0.5));
      drawTape(yaw, f, boot(0.4, 0.8));
      drawDial(f, yaw, v, T, ts, boot, rd);
      drawSignal(L.left, boot(0.8, 0.7), T, kk, near);
      drawTelemetry(L.right, boot(1.0, 0.7), [["ALT", altS, "DEG"], ["ZOOM", zv.toFixed(1), "X"], ["HDG", yaw.toFixed(1).padStart(5, "0"), "DEG"]], L.wide);
      if (L.strip) {
        // 폰: 패널 대신 테이프 아래 한 줄 — ALT · ZOOM · HDG
        const p = boot(0.8, 0.7);
        if (p > 0) text(`ALT ${altS}  ·  ZOOM ${zv.toFixed(1)}  ·  HDG ${yaw.toFixed(1).padStart(5, "0")}`, W / 2, safeTop + 90, 10, A(0.8 * p), "center");
      }
      g.globalAlpha = 1;
      drawReticle(f, ts, rd, hit);
      drawPings(ts);
      g.globalAlpha = calmA;
      drawCorners(ts, f.sky, boot(0.2, 0.5));
      g.globalAlpha = 1;
      const bt = ts - onT;
      if (bt < 2.4 && !rd) {
        const al = bt < 1.8 ? 1 : 1 - (bt - 1.8) / 0.6, msg = "INITIALIZING SENSOR ARRAY", n = Math.min(msg.length, Math.floor(bt * 30));
        text(msg.slice(0, n) + (Math.floor(bt * 8) % 2 ? "▌" : ""), W / 2, H / 2 + L.R * 1.24, 11, INK(al * 0.9), "center", DISP);
      }
      if (!rd && calmA === 1) {
        if (ts > nextGlitch) { glitchUntil = ts + 0.12; nextGlitch = ts + 4 + Math.random() * 5; }
        if (ts < glitchUntil) glitch();
      }
      // ── 맥박 신호(좌하단, 운영자 지정 색 규칙 — 그대로)
      const pOn = near < Infinity;
      set("pulseOn", pOn, (on) => pulse.classList.toggle("is-on", on));
      if (pOn) {
        const rate = 0.6 + 4.4 * kk * kk;   // 멀면 초당 0.6 번 · 코앞이면 5 번
        pulsePh += f.dt * rate;
        const ph = pulsePh % 1, beat = rd ? 0.5 : Math.exp(-ph * 7) + 0.55 * Math.exp(-Math.pow((ph - 0.22) * 9, 2));
        const hue = Math.round(215 * (1 - kk));   // 0 빨강 → 30 주황 → 55 노랑 → 120 초록 → 215 파랑(멀수록)
        set("pc", hue, (hh) => pulse.style.setProperty("--pc", `hsl(${hh} 95% 58%)`));
        pulseDot.style.transform = `scale(${(0.8 + 0.45 * beat).toFixed(2)})`;
        const ph2 = (ph + 0.5) % 1, near20 = near < 20 ? 1 : 0;
        pulseRing.style.transform = `scale(${(1 + 1.6 * ph).toFixed(2)})`; pulseRing.style.opacity = rd ? "0.5" : (0.7 * (1 - ph)).toFixed(2);
        pulseRing2.style.transform = `scale(${(1 + 1.6 * ph2).toFixed(2)})`; pulseRing2.style.opacity = rd ? "0" : (near20 * 0.5 * (1 - ph2)).toFixed(2);
        set("bars", 1 + Math.round(kk * 4), (nb) => bars.forEach((b, i) => b.classList.toggle("on", i < nb)));
      }
      // ── 카드 버튼
      set("zbtn", f.tele > 1.5, (zin) => {
        zoomBtn.textContent = zin ? "- RESET" : "+ ZOOM";
        zoomBtn.classList.toggle("is-fill", zin);
        hintLine.textContent = zin ? "OR PINCH TO ZOOM OUT" : "";
      });
    },
  };
}
