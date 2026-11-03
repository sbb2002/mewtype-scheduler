// 오르기 시험판 물리 검증 — climb-logic.js(게임 · 편집기와 같은 물리 코드)를 Node 에서 돌린다.
// 실행: node sim.cjs            → 합격 기준 0~10 검사(명세 §10 · §15)
//       node sim.cjs route 파일 → 완주 봇의 단계별 목표(want)를 JSON 으로 저장(브라우저 재생용)
// 봇 조작은 사람 손을 흉내 낸 것이다. 물리 계산은 proto.html 과 같은 코드를 쓴다.
const fs = require("fs"), path = require("path");
const src = fs.readFileSync(path.join(__dirname, "climb-logic.js"), "utf8");
const L = new Function("module", src + "\nreturn ClimbLogic;")({});
module.exports = L;

const P = { ...L.DEFAULTS }, polys = L.COURSE.polys;
let record = null;   // 완주 경로 기록용
const tick = (S) => { if (record) record.push([+S.want[0].toFixed(3), +S.want[1].toFixed(3)]); L.step(S, P, polys); S.minY = Math.min(S.minY ?? 1e9, S.p[1]); };

// ── 봇 동작 ──────────────────────────────────────────
/** 목표(몸통 기준 상대 위치)를 (x,y) 로 dur 초 동안 옮기고 hold 초 기다린다 */
// (v2) WAIT = true 면 옮긴 뒤 도구 끝이 목표에 닿거나(2u 이내) 막혀 멈출 때까지 최대 0.3초 더 기다린다 —
//      도구에 가속도가 생겨 목표를 늦게 따라가므로, 기본 물리로 도는 구간 검사(2 · 3)에서 쓴다. 사람도 도구가 닿은 걸 보고 다음 동작을 한다
let WAIT = true;
function mv(S, x, y, dur, hold = 0) {
  const w0 = [...S.want], n = Math.round(dur * 120);
  for (let i = 1; i <= n; i++) { const u = i / n; S.want = [w0[0] + (x - w0[0]) * u, w0[1] + (y - w0[1]) * u]; tick(S); }
  for (let i = 0; WAIT && i < 36; i++) {
    if (L.len(L.sub(S.d, L.clampRange(S.want, P.L_MIN, P.L_MAX, S.d))) < 2 || (i > 3 && L.len(S.tv) < 30)) break;
    tick(S);
  }
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

// (v2) 완주 봇은 도구 가속도 BOT_TOOL_ACCEL(사실상 즉시)로 돈다 — 봇 조작은 도구가 즉시 따라오던 v1 물리에 맞춰 짠 열린 순서라,
//      기본 가속도(DEFAULTS.TOOL_ACCEL)에서는 굴뚝 · 비탈 손잡이 구간 조작을 다시 짜야 한다(사람 손맛 확인은 운영자).
//      route.json · ?replay=1 도 같은 값으로 만들고 재생한다(proto.html)
const BOT_TOOL_ACCEL = 60000;
function fullRoute(log) {
  const accel0 = P.TOOL_ACCEL; P.TOOL_ACCEL = BOT_TOOL_ACCEL; WAIT = false;
  try { return fullRoute0(log); } finally { P.TOOL_ACCEL = accel0; WAIT = true; }
}
function fullRoute0(log) {
  const S = L.makeState(L.COURSE, P);
  for (const [name, fn] of Object.entries(stages)) {
    fn(S);
    if (log) console.log(`  ${name.padEnd(10)} 몸통 (${S.p[0].toFixed(0)}, ${S.p[1].toFixed(0)}) · 높이 ${(-(S.p[1] + P.R) / 100).toFixed(1)}m`);
  }
  return S;
}

L.bot = { stages, fullRoute, P, polys, BOT_TOOL_ACCEL };
if (require.main !== module) return;

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
  const drop = (p) => { const S = L.makeState(L.COURSE, P); S.p = p; S.v = [0, 0]; S.d = [0, -60]; S.want = [0, -60]; S.aim = [0, -60]; S.qPrev = L.add(S.p, S.d); mv(S, 0, -60, 0, 5); return S; };
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
  check(7, "골인", S.goalT >= 1, `골인 영역 체류 ${S.goalT.toFixed(2)}초 (기준 1초) · 봇 조작 시간 ${S.t.toFixed(0)}초 · 봇 도구 가속도 ${BOT_TOOL_ACCEL}(기본 ${P.TOOL_ACCEL})`);
}
{ // 8. 곡선 지형 — 아치 언덕 + 원 바위에서 버티기 · 뚫림 없음
  const k8 = 80 / Math.cos(Math.PI / 8);
  const { level } = L.normalizeLevel({ start: [0, -228], goal: null, polys: [
    { mat: "rock", pts: [[-700, 0], [700, 0], [700, 200], [-700, 200]] },
    { mat: "rock", curve: { 0: [0, -400] }, pts: [[-450, 0], [450, 0], [450, 60], [-450, 60]] },   // 윗변이 위로 휜 아치(꼭대기 y -200)
    { mat: "rock", edgeMat: { 2: "slick" },   // 원 바위(반지름 80, 꼭짓점 8 + 곡선 변 8)
      curve: Object.fromEntries([...Array(8)].map((_, i) => { const m = i * Math.PI / 4 + Math.PI / 8; return [i, [300 + k8 * Math.cos(m), -420 + k8 * Math.sin(m)]]; })),
      pts: [...Array(8)].map((_, i) => [300 + 80 * Math.cos(i * Math.PI / 4), -420 + 80 * Math.sin(i * Math.PI / 4)]) },
  ] });
  const fp = L.flattenLevel(level).polys;
  const inF = (pt) => fp.some((poly) => L.inside(pt, poly.pts));
  const S = L.makeState(level, P); S.d = [0, -80]; S.want = [0, -80]; S.aim = [0, -80]; S.qPrev = L.add(S.p, S.d);
  for (let i = 0; i < 120; i++) L.step(S, P, fp);
  const a = [...S.p]; let dev = 0; for (let i = 0; i < 360; i++) { L.step(S, P, fp); dev = Math.max(dev, L.len(L.sub(S.p, a))); }
  let bad = 0, seed = 11; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  for (let trial = 0; trial < 12; trial++) {
    const T = L.makeState(level, P); T.p = [[-300, -120], [0, -228], [250, -100], [300, -528], [180, -420], [420, -420]][trial % 6].slice(); T.qPrev = L.add(T.p, T.d);
    for (let k = 0; k < 60; k++) {
      const ang = rnd() * Math.PI * 2, n = 3 + Math.floor(rnd() * 10); T.want = [Math.cos(ang) * 225, Math.sin(ang) * 225];
      for (let i = 0; i < n; i++) { L.step(T, P, fp); if (inF(T.p) || inF(L.add(T.p, T.d))) bad++; }
    }
  }
  const errs = L.checkLevel(level, P).filter((w) => w.level === "오류");
  check(8, "곡선 지형", dev < 1 && bad === 0 && !errs.length,
    `아치 꼭대기에서 3초 움직임 ${dev.toFixed(3)}u (몸통 y ${a[1].toFixed(0)}, 꼭대기 -200) · 마구 휘두르기 12회 뚫림 ${bad}회 · 쪼갠 변 ${fp.reduce((s, p) => s + p.pts.length, 0)}개 · 검사 오류 ${errs.length}건`);
}
{ // 9. (v2) 고속 뚫림 없음 — 조정값 최대(도구 4000 · 몸통 3000 u/s, 가속도 최대)에서도 잘게 나눠 계산해 뚫리지 않는가
  const Q = { ...P, TOOL_SPEED: 4000, MAX_BODY_SPEED: 3000, TOOL_ACCEL: 60000, JUMP_DIST: 600 };
  let bad = 0, maxMove = 0, seed = 7; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  const spots = [[-450, -28], [-35, -98], [300, -178], [500, -318], [655, -600], [655, -900], [470, -1125], [200, -1128], [-200, -1128], [-500, -1128]];
  let subs = 0, over = 0;
  for (let trial = 0; trial < 20; trial++) {
    const S = L.makeState(L.COURSE, Q); S.p = [...spots[trial % spots.length]]; S.d = [0, -60]; S.want = [0, -60]; S.aim = [0, -60]; S.qPrev = L.add(S.p, S.d);
    for (let k = 0; k < 60; k++) {
      const a = rnd() * Math.PI * 2, n = 3 + Math.floor(rnd() * 10);
      S.want = [Math.cos(a) * Q.L_MAX * 1.5, Math.sin(a) * Q.L_MAX * 1.5];
      for (let i = 0; i < n; i++) {
        const q0 = L.add(S.p, S.d), x0 = S.p[0]; L.step(S, Q, polys); subs = S.substeps;
        maxMove = Math.max(maxMove, L.len(L.sub(L.add(S.p, S.d), q0)) / S.substeps);
        if (inside(S.p) || inside(L.add(S.p, S.d))) bad++;
        // 경계 벽(x ±700~±1000, 높이 22m)을 벽 높이 안에서 가로질렀으면 뚫림. 벽 위로 날아 넘어간 건 뚫림이 아니다(넘어간 뒤 바깥에 있는 것도)
        if (Math.abs(x0) <= 700 && Math.abs(S.p[0]) > 700) { if (S.p[1] > -2200) bad++; else over++; }
      }
    }
  }
  check(9, "고속 뚫림 없음", bad === 0, `도구 4000 · 몸통 3000 u/s 로 20회 × 약 6초, 지형 안에 들어간 단계 ${bad}회 · 한 단계를 ${subs}조각으로 계산 · 조각당 도구 끝 이동 최대 ${maxMove.toFixed(1)}u (경계 벽 위로 날아 넘어간 횟수 ${over}회 — 뚫림 아님)`);
}
{ // 10. (v2) 가속도 · 순간이동 제한
  // a. 가속: 멈춰 있던 도구가 반대편 목표로 갈 때 첫 단계 이동량과 최고 속도에 닿는 시간
  const S = L.makeState({ start: [0, -200], polys: [] }, P); S.d = [100, 0]; S.want = [100, 0]; S.aim = [100, 0];
  const Q = { ...P, GRAVITY: 0, JUMP_DIST: 600 };
  S.want = [-100, 0.1]; let first = 0, tReach = null;
  for (let i = 0; i < 60; i++) { const d0 = [...S.d]; L.step(S, Q, []); const mvd = L.len(L.sub(S.d, d0)) * 120; if (i === 0) first = mvd; if (tReach === null && mvd >= Q.TOOL_SPEED * 0.98) tReach = (i + 1) / 120; }
  const expect = P.TOOL_SPEED / P.TOOL_ACCEL;
  const okA = first <= P.TOOL_ACCEL / 120 + 1 && tReach !== null && Math.abs(tReach - expect) < 0.03;
  // b. 순간이동 제한: 도구로 땅을 짚고 선 몸통에서 목표를 반대편 아래로 한 번에 옮긴다(화면을 새로 누른 것) — 튀어 오른 높이 비교
  const fling = (jump) => {
    const Q2 = { ...P, JUMP_DIST: jump }, T = L.makeState(L.COURSE, Q2);
    T.d = [100, 20]; T.want = [100, 20]; T.aim = [100, 20];
    for (let i = 0; i < 120; i++) L.step(T, Q2, polys);
    const y0 = T.p[1]; let top = y0; T.want = [-100, 110];
    for (let i = 0; i < 180; i++) { L.step(T, Q2, polys); top = Math.min(top, T.p[1]); }
    return y0 - top;
  };
  // c. 일부러 빠르게 휘두르기(같은 이동을 0.12초 동안 이어서 입력)는 제한에 걸리지 않아야 한다
  const flick = (jump) => {
    const Q2 = { ...P, JUMP_DIST: jump }, T = L.makeState(L.COURSE, Q2);
    T.d = [100, 20]; T.want = [100, 20]; T.aim = [100, 20];
    for (let i = 0; i < 120; i++) L.step(T, Q2, polys);
    const y0 = T.p[1]; let top = y0;
    for (let i = 1; i <= 180; i++) { if (i <= 15) T.want = [100 - 200 * i / 15, 20 + 90 * i / 15]; L.step(T, Q2, polys); top = Math.min(top, T.p[1]); }
    return y0 - top;
  };
  const off = fling(600), on = fling(P.JUMP_DIST), fOff = flick(600), fOn = flick(P.JUMP_DIST);
  check(10, "가속도 · 순간이동 제한", okA && on < off * 0.6 && Math.abs(fOn - fOff) < 1,
    `첫 단계 도구 속도 ${first.toFixed(0)} u/s(상한 ${(P.TOOL_ACCEL / 120).toFixed(0)}) · 최고 속도 도달 ${tReach?.toFixed(3)}초(계산 ${expect.toFixed(3)}초) · 목표가 한 번에 옮겨졌을 때 튀어 오른 높이 제한 끔 ${off.toFixed(0)}u → 켬 ${on.toFixed(0)}u · 이어서 빠르게 휘두르기는 끔 ${fOff.toFixed(0)}u = 켬 ${fOn.toFixed(0)}u`);
}
{ // 11. (v2) 레벨 파일의 화면 확대 · 조정값 — 읽기 · 범위 자르기 · 기본값
  const { level } = L.normalizeLevel({ start: [0, -28], polys: [], view: { pc: 900, mobile: 99999 }, physics: { TOOL_ACCEL: 8000, TOOL_SPEED: -5, GRAVITY: 1 } });
  const { level: plain } = L.normalizeLevel({ start: [0, -28], polys: [] });
  const Pm = L.levelParams(level);
  const ok = level.view.pc === 900 && level.view.mobile === L.VIEW_RANGE[1] && Pm.TOOL_ACCEL === 8000 && Pm.TOOL_SPEED === L.LEVEL_PHYSICS.TOOL_SPEED[0]
    && Pm.GRAVITY === P.GRAVITY && !plain.physics && plain.view.pc === L.VIEW_DEFAULT.pc && L.viewSpan(plain, "mobile") === L.VIEW_DEFAULT.mobile;
  check(11, "레벨 화면 · 조정값", ok, `view ${JSON.stringify(level.view)} · physics ${JSON.stringify(level.physics)} (목록 밖 GRAVITY 는 버림) · 없을 때 view ${JSON.stringify(plain.view)}`);
}
{ // 물리 계산 비용(참고)
  const S = L.makeState(L.COURSE, P); const t0 = process.hrtime.bigint(); for (let i = 0; i < 12000; i++) { S.want = [Math.cos(i / 30) * 120, Math.sin(i / 30) * 120]; L.step(S, P, polys); }
  console.log(`참고  물리 한 단계 평균 ${(Number(process.hrtime.bigint() - t0) / 1e6 / 12000 * 1000).toFixed(1)}µs (Node) — 60fps 한 프레임 = 2단계`);
}
console.log(out.every(Boolean) ? "\n전부 통과" : "\n실패 있음");
process.exitCode = out.every(Boolean) ? 0 : 1;
