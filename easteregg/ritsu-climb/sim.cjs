// 오르기 시험판 물리 검증 — climb-logic.js(게임 · 편집기와 같은 물리 코드)를 Node 에서 돌린다.
// 실행: node sim.cjs            → 합격 기준 1~7 검사(명세 §10)
//       node sim.cjs route 파일 → 완주 봇의 단계별 목표(want)를 JSON 으로 저장(브라우저 재생용)
// 봇 조작은 사람 손을 흉내 낸 것이다. 물리 계산은 proto.html 과 같은 코드를 쓴다.
const fs = require("fs"), path = require("path");
const src = fs.readFileSync(path.join(__dirname, "climb-logic.js"), "utf8");
const L = new Function("module", src + "\nreturn ClimbLogic;")({});
module.exports = L;
if (require.main !== module) return;

const P = { ...L.DEFAULTS }, polys = L.COURSE.polys;
let record = null;   // 완주 경로 기록용
const tick = (S) => { if (record) record.push([+S.want[0].toFixed(3), +S.want[1].toFixed(3)]); L.step(S, P, polys); S.minY = Math.min(S.minY ?? 1e9, S.p[1]); };

// ── 봇 동작 ──────────────────────────────────────────
/** 목표(몸통 기준 상대 위치)를 (x,y) 로 dur 초 동안 옮기고 hold 초 기다린다 */
function mv(S, x, y, dur, hold = 0) {
  const w0 = [...S.want], n = Math.round(dur * 120);
  for (let i = 1; i <= n; i++) { const u = i / n; S.want = [w0[0] + (x - w0[0]) * u, w0[1] + (y - w0[1]) * u]; tick(S); }
  for (let i = 0; i < hold * 120; i++) tick(S);
}
/** 도구 끝을 세계 좌표 (x,y) 로 dur 초 동안 옮긴다(몸통이 움직여도 따라 고친다 — 공중에서만 쓴다) */
function tipTo(S, x, y, dur) {
  const n = Math.max(1, Math.round(dur * 120)), q0 = L.add(S.p, S.d);
  for (let i = 1; i <= n; i++) { const u = i / n; S.want = [q0[0] + (x - q0[0]) * u - S.p[0], q0[1] + (y - q0[1]) * u - S.p[1]]; tick(S); }
}
const crawlR = (S) => { mv(S, 40, -110, .25); mv(S, 130, -40, .25); mv(S, 130, 40, .2); mv(S, -40, 40, .5); };
const crawlLow = (S) => { mv(S, 30, -50, .2); mv(S, 110, -30, .2); mv(S, 110, 30, .2); mv(S, -40, 35, .5); };
const crawlL = (S, dx = 130) => { mv(S, -40, -110, .25); mv(S, -dx, -40, .25); mv(S, -dx, 30, .3, .2); mv(S, 40, 40, .6); };
const stepR = (S) => { mv(S, 40, -120, .3); mv(S, 140, -90, .3); mv(S, 140, 0, .3); mv(S, 0, 70, .5); mv(S, -60, 40, .4, .5); };

const stages = {
  "① 계단": (S) => { for (let c = 0; c < 3; c++) crawlR(S); stepR(S); for (let c = 0; c < 3; c++) crawlR(S); stepR(S); },
  "② 턱 걸기": (S) => {
    mv(S, 40, -110, .25); mv(S, 120, -40, .25); mv(S, 120, 40, .2); mv(S, -40, 40, .5);
    mv(S, -20, -130, .4); mv(S, 70, -135, .4); mv(S, 70, -100, .3);
    S.hangFrom = [...S.p]; mv(S, 70, -100, 0, 3); S.hangDrift = L.len(L.sub(S.p, S.hangFrom));   // 매달린 채 3초
    mv(S, 40, -10, .6); mv(S, -10, 50, .5); mv(S, -60, 40, .4, .6);
  },
  "③ 굴뚝": (S) => {
    for (let c = 0; c < 2; c++) crawlLow(S);
    mv(S, 30, -50, .2); mv(S, 60, -30, .2); mv(S, 60, 30, .2); mv(S, -30, 40, .5); mv(S, -40, 30, .3, .3);
    // 기둥 면에서 끝을 떼고 → 위로 → 면을 누르고 → 아래로 당기기
    for (let c = 0; c < 14 && S.p[1] > -1040; c++) {
      const free = 630 - S.p[0]; mv(S, free, S.d[1], .03); mv(S, free, -100, .08); mv(S, 606 - S.p[0], -100, .03); mv(S, 606 - S.p[0], 60, .35);
    }
  },
  "④ 비탈 손잡이": (S) => {
    mv(S, 0, -60, .08); tipTo(S, 600, -1150, .15); tipTo(S, 548, -1120, .15); mv(S, S.d[0], S.d[1] + 25, .15); mv(S, S.d[0], S.d[1], 0, .3);
    for (let i = 0; i < 8; i++) mv(S, S.d[0] + 12, S.d[1] + 20, .15);
    mv(S, -20, 45, .6, .5); mv(S, 45, 45, .5, .3); mv(S, 40, 0, .3, .5);
    mv(S, -40, -80, .3); tipTo(S, 368, -1130, .25); mv(S, S.d[0], S.d[1] + 28, .15);
    for (let i = 0; i < 8; i++) mv(S, S.d[0] + 18, S.d[1] + 18, .15);
  },
  "⑤ 구멍 건너기": (S) => {
    mv(S, 30, 45, .6, .5); for (let i = 0; i < 8 && S.p[0] >= 80; i++) crawlL(S, 130);
    mv(S, 18, 42, .5, .3); mv(S, 0, 40, .4, .4); mv(S, 30, -60, .3, .4); tipTo(S, -60, -1180, .3); tipTo(S, -108, -1135, .25); mv(S, S.d[0], S.d[1] + 35, .3, .2);
    for (let i = 0; i < 6; i++) mv(S, S.d[0] + 25, S.d[1] + 3, .12); mv(S, 40, 40, .4, .3);
  },
  "⑤ 벽 튕기기": (S) => {
    crawlL(S, 60); mv(S, 0, 40, .4, .5); mv(S, 15, 40, .3, .4);
    mv(S, 80, 140, .15); mv(S, 80, 140, 0, .04); mv(S, -40, -80, .1);   // 오른쪽 아래를 빠르게 눌러 왼쪽 위로 튀어 오르기
    for (let i = 0; i < 90; i++) { S.want = [-290 - S.p[0], -1325 - S.p[1]]; tick(S); if (S.tipHit && S.tipHit.n[1] < -0.7) break; }   // 공중에서 벽 꼭대기에 끝 걸기
    for (let i = 0; i < 6; i++) mv(S, S.d[0] - 12, S.d[1] + 25, .12); mv(S, -30, 40, .4, .6);
  },
  "⑥ 골인": (S) => { for (let i = 0; i < 3; i++) crawlL(S, 100); S.goalT = 0; for (let i = 0; i < 150; i++) { tick(S); if (L.inGoal(S)) S.goalT += L.DT; } },
};

function fullRoute(log) {
  const S = L.makeState(L.COURSE, P);
  for (const [name, fn] of Object.entries(stages)) {
    fn(S);
    if (log) console.log(`  ${name.padEnd(10)} 몸통 (${S.p[0].toFixed(0)}, ${S.p[1].toFixed(0)}) · 높이 ${(-(S.p[1] + P.R) / 100).toFixed(1)}m`);
  }
  return S;
}

if (process.argv[2] === "route") {
  record = [];
  const S = fullRoute(false);
  fs.writeFileSync(process.argv[3], JSON.stringify(record));
  console.log("기록", record.length, "단계 · 골인", S.goalT >= 1);
  return;
}

// ── 합격 기준 검사 ───────────────────────────────────
const out = [];
const check = (no, name, ok, detail) => { out.push(ok); console.log(`${ok ? "통과" : "실패"}  ${no}. ${name} — ${detail}`); };
const inside = (pt) => polys.some((poly) => { let c = false; const pts = poly.pts; for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) { const [xi, yi] = pts[i], [xj, yj] = pts[j]; if ((yi > pt[1]) !== (yj > pt[1]) && pt[0] < (xj - xi) * (pt[1] - yi) / (yj - yi) + xi) c = !c; } return c; });

{ // 0. 페이지 스크립트 문법 · 기본 코스 레벨 검사(편집기와 같은 검사)
  const bad = [];
  for (const f of ["proto.html", "editor.html"]) {
    const page = fs.readFileSync(path.join(__dirname, f), "utf8");
    for (const m of page.matchAll(/<script>([\s\S]*?)<\/script>/g)) { try { new Function(m[1]); } catch (e) { bad.push(`${f}: ${e.message}`); } }
  }
  const warns = L.checkLevel(L.normalizeLevel(JSON.parse(JSON.stringify(L.COURSE))).level, P);
  check(0, "문법 · 기본 코스 검사", !bad.length && !warns.length, bad.length ? bad.join(" / ") : `스크립트 문법 이상 없음 · 기본 코스 경고 ${warns.length}건`);
}
{ // 1. 버티기
  const S = L.makeState(L.COURSE, P); mv(S, 90, 22, 0, 1); mv(S, 0, 100, 1, 1);
  const a = [...S.p]; let dev = 0; for (let i = 0; i < 360; i++) { tick(S); dev = Math.max(dev, L.len(L.sub(S.p, a))); }
  check(1, "버티기", dev < 1, `도구로 받친 채 3초 최대 움직임 ${dev.toFixed(4)}u (기준 1u 미만)`);
}
{ // 2·3. 계단 · 걸기
  const S = L.makeState(L.COURSE, P); stages["① 계단"](S);
  check(2, "밀어 올리기", S.p[1] < -150 - P.R + 5 && S.p[0] > 150, `계단 2개를 올라 몸통 (${S.p[0].toFixed(0)}, ${S.p[1].toFixed(0)}) — 계단 2 윗면 -150`);
  stages["② 턱 걸기"](S);
  check(3, "걸기", S.hangDrift < 1 && S.p[1] < -290, `턱에 매달려 3초 움직임 ${S.hangDrift.toFixed(3)}u, 끌어올린 뒤 몸통 y ${S.p[1].toFixed(0)} (턱 윗면 -290)`);
}
{ // 4. 튕기기 — 같은 휘두름을 느리게(1초) · 빠르게(0.12초)
  const rise = (dur) => { const S = L.makeState(L.COURSE, P); mv(S, 110, 20, 0, 1); const y0 = S.p[1]; S.minY = 1e9; mv(S, 0, 110, dur, 1.5); return y0 - S.minY; };
  const slow = rise(1), fast = rise(0.12);
  check(4, "튕기기", fast - slow >= 2 * P.R * 2 && slow < 110, `느리게 ${slow.toFixed(0)}u(도구 길이만큼 올라선 것) · 빠르게 ${fast.toFixed(0)}u → 튕긴 높이 ${(fast - slow).toFixed(0)}u (기준 몸통 높이 2배 ${4 * P.R}u 이상)`);
}
{ // 5. 되돌림 길 — 비탈(바위 손잡이 오른쪽)에 내려놓고 손을 놓으면 굴뚝으로 빠지는가 · 구멍에 빠지면 출발 구간까지 가는가
  const drop = (p) => { const S = L.makeState(L.COURSE, P); S.p = p; S.v = [0, 0]; S.d = [0, -60]; S.want = [0, -60]; S.qPrev = L.add(S.p, S.d); mv(S, 0, -60, 0, 5); return S; };
  const S = drop([585, -1050]), T = drop([-60, -1140]);
  check(5, "되돌림 길", S.p[1] > -330 && S.p[1] < -290 && T.p[1] > -110,
    `비탈 → 몸통 (${S.p.map((v) => v.toFixed(0))}) = ②의 턱(윗면 -290) · 구멍 → 몸통 (${T.p.map((v) => v.toFixed(0))}) = 출발 옆 계단 1(윗면 -70)`);
}
{ // 6. 뚫림 없음 — 여러 자리에서 최대 속도로 마구 휘두르기 20회
  let bad = 0, worst = "";
  const spots = [[-450, -28], [-35, -98], [300, -178], [500, -318], [655, -600], [655, -900], [470, -1125], [200, -1128], [-200, -1128], [-500, -1128]];
  let seed = 7; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  for (let trial = 0; trial < 20; trial++) {
    const S = L.makeState(L.COURSE, P); S.p = [...spots[trial % spots.length]]; S.qPrev = L.add(S.p, S.d);
    for (let k = 0; k < 60; k++) {
      const a = rnd() * Math.PI * 2, n = 3 + Math.floor(rnd() * 10);
      S.want = [Math.cos(a) * P.L_MAX * 1.5, Math.sin(a) * P.L_MAX * 1.5];
      for (let i = 0; i < n; i++) {
        tick(S);
        const tip = L.add(S.p, S.d);
        if (inside(S.p) || inside(tip) || Math.abs(S.p[0]) > 700) { bad++; worst = `시도 ${trial} 몸통 (${S.p.map((v) => v.toFixed(0))}) 끝 (${tip.map((v) => v.toFixed(0))})`; }
      }
    }
  }
  check(6, "뚫림 없음", bad === 0, `20회 × 약 6초, 몸통 · 도구 끝 중심이 지형 안에 들어간 단계 ${bad}회 ${worst}`);
}
{ // 7. 골인
  console.log("   완주 봇:");
  const S = fullRoute(true);
  check(7, "골인", S.goalT >= 1, `골인 영역 체류 ${S.goalT.toFixed(2)}초 (기준 1초) · 봇 조작 시간 ${S.t.toFixed(0)}초`);
}
{ // 물리 계산 비용(참고)
  const S = L.makeState(L.COURSE, P); const t0 = process.hrtime.bigint(); for (let i = 0; i < 12000; i++) { S.want = [Math.cos(i / 30) * 120, Math.sin(i / 30) * 120]; L.step(S, P, polys); }
  console.log(`참고  물리 한 단계 평균 ${(Number(process.hrtime.bigint() - t0) / 1e6 / 12000 * 1000).toFixed(1)}µs (Node) — 60fps 한 프레임 = 2단계`);
}
console.log(out.every(Boolean) ? "\n전부 통과" : "\n실패 있음");
process.exitCode = out.every(Boolean) ? 0 : 1;
