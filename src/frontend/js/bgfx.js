// bgfx.js — (bg-dome 11-09 운영자 코멘트) 배경 보기 중 가끔 하늘에 나타났다 사라지는 것들.
//   · YMMT  = 지구 하늘에서 유노 생일 장면의 작은 YMMT 별자리 애니메이션(별이 뜨고 → 글자별로 선이 그어지고 → 번쩍 → 사라짐). 상설 별자리를 대신한다(어색하다는 코멘트).
//   · UFO   = 유노 생일 장면의 UFO(assets/birthday/ufo.png)가 화면을 가로질러 지나간다. 우주 · 딥필드 · 성간 이동 중에도 나온다.
//             성간 이동 중엔 특수 상대론 효과 — 도플러(다가오면 푸르고 밝게, 멀어지면 붉고 어둡게) · 길이 수축(1/γ) · 빠를수록 더 빨리 지나감.
// DOM 은 캔버스 하나(pointer-events 없음). 계산은 여기, 언제 켜고 무엇을 넘기는지는 bgdomegl.js. 움직임 줄이기면 나타나지 않는다.

import { ymmtLetters } from "./bdaylogic.js";
import { dirFromAzAlt } from "./bghudlogic.js";

const DEG = Math.PI / 180;
const rnd = (a, b) => a + Math.random() * (b - a);
const clamp01 = (x) => Math.max(0, Math.min(1, x));
const ss = (x) => { x = clamp01(x); return x * x * (3 - 2 * x); };

/** 특수 상대론 — beta(v/c), c = 이동 방향과 시선 사이 cos(1 = 다가옴). 돌려줌 = { D 도플러 인자, gamma, contract(길이 수축 배율) } */
export function relativistic(beta, c) {
  const b = Math.max(0, Math.min(0.999, beta)), gamma = 1 / Math.sqrt(1 - b * b);
  const D = Math.sqrt((1 + b * c) / (1 - b * c));
  return { D: Math.max(0.2, Math.min(5, D)), gamma, contract: 1 / gamma };
}
/** 도플러 인자 D → 색을 입힐 (r, g, b, 세기 0~1). D > 1 푸름 · < 1 붉음 */
export function dopplerTint(D) {
  const k = Math.min(1, Math.abs(Math.log(D)) / Math.log(3));
  return D >= 1 ? { rgb: [120, 190, 255], a: 0.75 * k } : { rgb: [255, 70, 40], a: 0.8 * k };
}

/** parent = 돔 공중 무늬 층(bgdm-air) — 바닥 콘솔보다 뒤에 놓여 UFO · 별자리가 바닥을 뚫지 않는다(bgdeco.css). 없으면 body 에 붙인다. */
export function createFx(parent = document.body) {
  const cv = document.createElement("canvas");
  cv.className = "bgfx"; cv.setAttribute("aria-hidden", "true");
  const g = cv.getContext("2d");
  parent.appendChild(cv);
  const ufoImg = new Image(); ufoImg.src = new URL("../assets/birthday/ufo.png", import.meta.url).href;
  const tint = document.createElement("canvas"); tint.width = tint.height = 96;   // 색을 입힌 UFO 한 장(매 프레임 다시 칠함)
  const tg = tint.getContext("2d");
  let W = 0, H = 0, dpr = 1, shown = false;
  let ymmt = null, ufo = null, nextY = 0, nextU = 0, lastPlace = null, shape = null;
  const t0 = () => performance.now() / 1000;

  function resize() {
    W = window.innerWidth; H = window.innerHeight; dpr = Math.min(window.devicePixelRatio || 1, 2);
    cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr);
  }

  // ── YMMT ──
  function drawYmmt(p, scalePx, age) {
    // age 0 ~ 9초: 0 ~ 1.4 별 · 1.4 ~ 5 글자별 선 · 5 ~ 5.4 번쩍 · 5.4 ~ 7 유지 · 7 ~ 9 사라짐
    const fade = 1 - ss((age - 7) / 2), rise = ss(age / 0.8);
    const a = rise * fade; if (a <= 0) return;
    const pen = clamp01((age - 1.4) / 3.6) * 4, flash = Math.sin(Math.PI * clamp01((age - 5) / 0.4));
    g.save(); g.translate(p[0], p[1]); g.scale(scalePx, scalePx); g.translate(-172, -40);
    g.lineCap = "round"; g.lineJoin = "round";
    shape.forEach(({ points, path }, i) => {
      const q = clamp01(pen - i) * (path.length - 1);
      if (q <= 0) return;
      const whole = Math.floor(q), part = q - whole;
      const trace = () => { g.beginPath(); g.moveTo(...points[path[0]]); for (let s = 1; s <= whole; s++) g.lineTo(...points[path[s]]); if (part > 0 && whole < path.length - 1) { const A = points[path[whole]], B = points[path[whole + 1]]; g.lineTo(A[0] + (B[0] - A[0]) * part, A[1] + (B[1] - A[1]) * part); } };
      g.globalAlpha = a * (0.55 + 0.45 * flash); g.shadowColor = "#329dff"; g.shadowBlur = 14; g.strokeStyle = "#329dff"; g.lineWidth = 4 + 3 * flash; trace(); g.stroke();
      g.shadowBlur = 0; g.globalAlpha = a * 0.75; g.strokeStyle = "#c3edff"; g.lineWidth = 1.6; trace(); g.stroke();
    });
    // 별 — 차례로 뜬다
    let n = 0; g.fillStyle = "#e6f5ff";
    for (const { points } of shape) for (const [x, y] of points) { const born = n++ * 0.065; g.globalAlpha = a * clamp01((age - born - 0.1) * 5); g.beginPath(); g.arc(x, y, 3.4 + 2 * flash, 0, 7); g.fill(); }
    g.restore();
  }

  // ── UFO ──
  // 경로 두 가지(유노 생일 장면 UFO 처럼): 부드러운 곡선 · 각진 직선 꺾임. 각진 경로는 꼭짓점마다 무작위 시간(0.35 ~ 1.6초) 멈췄다가 다음 꼭짓점으로 간다(운영자 11-09).
  function startUfo(rel) {
    const dir = Math.random() < 0.5 ? 1 : -1;   // 1 = 왼쪽에서 오른쪽
    const fast = 1 + 3 * rel.beta, angular = Math.random() < 0.5;
    let moves, dur;
    const u = { dir, size: rnd(30, 44), toward: Math.random() < 0.5 ? 1 : -1, rel, angular, ph: rnd(0, 6) };
    if (angular) {
      const n = 3 + Math.floor(Math.random() * 3);   // 안쪽 꼭짓점 3 ~ 5개
      const X = (f) => (dir > 0 ? -0.08 + 1.16 * f : 1.08 - 1.16 * f) * W;
      const pts = [[X(0), rnd(0.15, 0.5) * H]];
      for (let q = 1; q <= n; q++) pts.push([X(q / (n + 1) + rnd(-0.04, 0.04)), rnd(0.12, 0.55) * H]);
      pts.push([X(1), rnd(0.15, 0.5) * H]);
      const speed = (W * 0.42) * fast;   // px / 초
      const segs = []; let t = 0;
      for (let q = 1; q < pts.length; q++) {
        const L = Math.hypot(pts[q][0] - pts[q - 1][0], pts[q][1] - pts[q - 1][1]), d = Math.max(0.25, L / speed);
        segs.push({ t0: t, t1: t + d, a: pts[q - 1], b: pts[q] }); t += d;
        if (q < pts.length - 1) { const w = rnd(0.35, 1.6); segs.push({ t0: t, t1: t + w, a: pts[q], b: pts[q] }); t += w; }   // 꼭짓점에서 쉼
      }
      u.segs = segs; dur = t;
    } else {
      const y0 = rnd(0.14, 0.5) * H, amp = rnd(0.03, 0.09) * H;
      dur = rnd(4.2, 6.2) / fast;
      u.pos = (tt) => { const kk = tt / dur; return [(dir > 0 ? -0.08 + 1.16 * kk : 1.08 - 1.16 * kk) * W, y0 + Math.sin(kk * 7 + u.ph) * amp + (kk - 0.5) * H * 0.05]; };
    }
    if (angular) u.pos = (tt) => {
      const sg = u.segs, g0 = sg.find((e) => tt <= e.t1) || sg[sg.length - 1];
      const k = g0.t1 > g0.t0 ? ss((tt - g0.t0) / (g0.t1 - g0.t0)) : 1;
      return [g0.a[0] + (g0.b[0] - g0.a[0]) * k, g0.a[1] + (g0.b[1] - g0.a[1]) * k];
    };
    u.t0 = t0(); u.dur = dur;
    ufo = u;
  }
  function drawUfo(now) {
    const u = ufo, age = now - u.t0;
    if (age >= u.dur) { ufo = null; return; }
    const p = u.pos(age), edge = Math.min(1, age / 0.35, (u.dur - age) / 0.35);
    const r = u.rel.beta > 0.05 ? (() => { const q = relativistic(u.rel.beta, u.toward * 0.9); return { ...q, tint: dopplerTint(q.D) }; })() : null;
    const sx = r ? r.contract : 1;           // 이동 방향(가로)으로 납작
    const bright = r ? Math.max(0.25, Math.min(1.6, Math.pow(r.D, 1.5))) : 1;
    // 꼬리(지나온 길, 옅어짐) — 쉬는 동안엔 꼬리가 점점 모인다. 상대론 효과가 크면 색을 따라간다
    const tailCol = r ? (r.D >= 1 ? "150,205,255" : "255,110,80") : "160,225,255";
    g.lineCap = "round";
    for (let i = 14; i > 0; i--) {
      const ta = age - i * 0.07, tb = age - (i - 1) * 0.07; if (ta < 0) continue;
      const a = u.pos(ta), b = u.pos(tb);
      g.strokeStyle = `rgba(${tailCol},${0.42 * (1 - i / 14) * edge * Math.min(1, bright)})`; g.lineWidth = Math.max(1, u.size * 0.12 * (1 - i / 16));
      g.beginPath(); g.moveTo(a[0], a[1]); g.lineTo(b[0], b[1]); g.stroke();
    }
    if (!ufoImg.complete || !ufoImg.naturalWidth) return;
    const S = u.size;
    let src = ufoImg;
    if (r && r.tint.a > 0.02) {   // 색 입히기(도플러)
      tg.clearRect(0, 0, 96, 96); tg.globalCompositeOperation = "source-over"; tg.drawImage(ufoImg, 0, 0, 96, 96);
      tg.globalCompositeOperation = "source-atop"; tg.fillStyle = `rgba(${r.tint.rgb.join(",")},${r.tint.a})`; tg.fillRect(0, 0, 96, 96);
      tg.globalCompositeOperation = "source-over"; src = tint;
    }
    g.save(); g.translate(p[0], p[1]); g.rotate(Math.cos(age * 1.6 + u.ph) * 0.12 * u.dir); g.scale(sx, 1);
    g.globalAlpha = Math.min(1, edge * (0.35 + 0.65 * Math.min(1, bright)));
    g.shadowColor = r ? `rgba(${r.tint.rgb.join(",")},.9)` : "#8ae3e2"; g.shadowBlur = 7 + 8 * Math.min(2, bright);
    g.drawImage(src, -S / 2, -S / 2, S, S);
    g.restore();
  }

  return {
    remove() { cv.remove(); },
    /**
     * 한 프레임. f = { active(보이기), place("earth" · "space" · 딥필드 키 …), ymmtOn(YMMT 해금), project(dir → [x, y] | null), ppd(화면 px / 도), yawDeg, beta(성간 이동 속도, 없으면 0), reduced }
     */
    update(f) {
      if (!W) resize();
      const show = !!f.active && !f.reduced;
      if (show !== shown) { shown = show; cv.classList.toggle("is-on", show); if (!show) { ymmt = ufo = null; g.setTransform(1, 0, 0, 1, 0, 0); g.clearRect(0, 0, cv.width, cv.height); } }
      if (!show) return;
      const now = t0();
      if (f.place !== lastPlace) { lastPlace = f.place; ymmt = null; nextY = now + rnd(8, 16); if (!nextU || nextU < now) nextU = now + rnd(10, 22); }
      g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, W, H);
      // 스폰
      if (f.place === "earth" && f.ymmtOn && !ymmt && now >= nextY) {
        shape = shape || ymmtLetters(7);
        ymmt = { t0: now, dir: dirFromAzAlt(f.yawDeg + rnd(-28, 28), rnd(32, 52)) };
        nextY = now + 9 + rnd(35, 80);
      }
      if (!ufo && now >= nextU) { startUfo({ beta: f.beta || 0 }); nextU = now + (f.beta > 0.05 ? rnd(10, 22) : rnd(28, 70)); }
      if (ymmt) {
        const age = now - ymmt.t0;
        if (age > 9) ymmt = null;
        else {
          const p = f.project(ymmt.dir);
          if (p) drawYmmt(p, (18 * Math.max(4, f.ppd || 8)) / 345, age);   // 가로 약 18°(작게)
        }
      }
      if (ufo) drawUfo(now);
    },
  };
}
