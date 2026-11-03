// 오르기 게임 물리 계산 — DOM 을 쓰지 않는 순수 함수 묶음(전역 ClimbLogic).
// proto.html(게임) · editor.html(레벨 편집기) · sim.cjs(Node 검증)가 같은 이 파일을 쓴다. 사이트 이식 때 모듈로 옮긴다.
const ClimbLogic = (() => {
  // 조정값 시작값 — 명세 §7
  const DEFAULTS = {
    R: 28, TIP_R: 6, L_MIN: 40, L_MAX: 150,
    GRAVITY: 1800, AIR_DRAG: 0.15,
    TOOL_SPEED: 1600, BODY_SHARE: 1.0, MAX_BODY_SPEED: 1400,
    TIP_FRICTION_ROCK: 4.0, TIP_FRICTION_SLICK: 0.3,
    BODY_FRICTION_ROCK: 0.8, BODY_FRICTION_SLICK: 0.05,
    ITER: 4,
  };
  const DT = 1 / 120;

  // 시험 코스 — 좌표 단위 u, y 는 아래가 +. 출발 바닥 윗면 = y 0. 벽은 전부 두께 60u 이상의 닫힌 다각형
  const rect = (x0, y0, x1, y1, mat = "rock") => ({ mat, pts: [[x0, y0], [x1, y0], [x1, y1], [x0, y1]] });
  const COURSE = {
    start: [-450, -28],
    polys: [
      rect(-1000, -2200, -700, 400),            // 왼쪽 경계 벽
      rect(700, -2200, 1000, 400),              // 오른쪽 경계 벽
      rect(-700, 0, 700, 400),                  // ① 출발 바닥
      rect(-150, -70, 700, 0),                  // ① 계단 1
      rect(150, -150, 700, -70),                // ① 계단 2
      rect(400, -290, 700, -230),               // ② 걸기용 턱(오른쪽 벽에서 튀어나옴, 아래가 비어 있음)
      // ③ 굴뚝 기둥 — 오른쪽 벽과의 틈 90u = 몸통 지름 × 1.6
      // ④ 되돌림 길 1: 기둥 윗면 = 미끄러운 비탈(왼쪽으로 오르막, 변 2 만 slick). 미끄러지면 굴뚝으로 빠져 ②의 턱까지 떨어진다
      { mat: "rock", edgeMat: { 2: "slick" }, pts: [[380, -400], [610, -400], [610, -1000], [380, -1100]] },
      rect(500, -1095, 560, -1015),             // ④ 비탈 중간의 바위 손잡이(도구를 걸 곳)
      // ⑤ 꼭대기 바닥 — 가운데 구멍(80u, 몸통보다 넓다) = 되돌림 길 2: 빠지면 출발 바닥까지 떨어진다
      rect(-20, -1100, 380, -1040),
      rect(-700, -1100, -100, -1040),
      rect(-360, -1340, -260, -1100),           // ⑤ 몸통보다 높은 벽(240u) — 튕기기로 넘는다
    ],
    goal: { x0: -700, y0: -1230, x1: -380, y1: -1100 },   // ⑥ 골인 영역
  };

  const add = (a, b) => [a[0] + b[0], a[1] + b[1]];
  const sub = (a, b) => [a[0] - b[0], a[1] - b[1]];
  const mul = (a, s) => [a[0] * s, a[1] * s];
  const dot = (a, b) => a[0] * b[0] + a[1] * b[1];
  const len = (a) => Math.hypot(a[0], a[1]);
  function clampLen(v, max) { const l = len(v); return l > max ? mul(v, max / l) : v; }
  function clampRange(v, lo, hi, fallback) {
    const l = len(v);
    if (l < 1e-6) return mul(fallback, lo / (len(fallback) || 1));
    if (l < lo) return mul(v, lo / l);
    if (l > hi) return mul(v, hi / l);
    return v;
  }

  function inside(pt, pts) {
    let c = false;
    for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
      const [xi, yi] = pts[i], [xj, yj] = pts[j];
      if ((yi > pt[1]) !== (yj > pt[1]) && pt[0] < (xj - xi) * (pt[1] - yi) / (yj - yi) + xi) c = !c;
    }
    return c;
  }
  function closestOnSeg(p, a, b) {
    const ab = sub(b, a), t = Math.max(0, Math.min(1, dot(sub(p, a), ab) / dot(ab, ab)));
    return add(a, mul(ab, t));
  }

  /** 원(중심 c, 반지름 r)이 파고든 다각형마다 접촉 하나 — n = 밀어낼 방향(바깥), depth = 파고든 깊이 */
  // 다각형마다 감싸는 사각형을 한 번만 계산해 두고, 원이 그 밖이면 변 검사를 건너뛴다(곡선을 잘게 쪼개 변이 많아져서)
  const boxes = new WeakMap();
  function boxOf(poly) {
    let b = boxes.get(poly);
    if (!b || b.n !== poly.pts.length) {
      b = { n: poly.pts.length, x0: Infinity, y0: Infinity, x1: -Infinity, y1: -Infinity };
      for (const [x, y] of poly.pts) { b.x0 = Math.min(b.x0, x); b.y0 = Math.min(b.y0, y); b.x1 = Math.max(b.x1, x); b.y1 = Math.max(b.y1, y); }
      boxes.set(poly, b);
    }
    return b;
  }
  function contacts(c, r, polys) {
    const out = [];
    for (const poly of polys) {
      const bb = boxOf(poly);
      if (c[0] < bb.x0 - r || c[0] > bb.x1 + r || c[1] < bb.y0 - r || c[1] > bb.y1 + r) continue;
      const pts = poly.pts;
      let best = Infinity, cp = null, edge = 0;
      for (let i = 0; i < pts.length; i++) {
        const q = closestOnSeg(c, pts[i], pts[(i + 1) % pts.length]);
        const d = len(sub(c, q));
        if (d < best) { best = d; cp = q; edge = i; }
      }
      const isIn = inside(c, pts);
      if (!isIn && best >= r) continue;
      let n;
      if (best < 1e-9) n = [0, -1];
      else n = isIn ? mul(sub(cp, c), 1 / best) : mul(sub(c, cp), 1 / best);
      // 재질은 다각형 단위(mat), 특정 변만 다르면 edgeMat[변 번호] — 얇은 쐐기 다각형을 따로 두지 않으려고
      out.push({ n, depth: isIn ? r + best : r - best, mat: poly.edgeMat?.[edge] ?? poly.mat });
    }
    return out;
  }

  /** 면 마찰 — 이번 단계에 면을 따라 미끄러진 거리(from → to)를 mu × 깊이 만큼 되돌린다. 되돌린 벡터를 돌려준다 */
  function friction(from, to, n, depth, mu) {
    const delta = sub(to, from);
    const t = sub(delta, mul(n, dot(delta, n)));
    const tl = len(t), lim = mu * depth;
    if (tl < 1e-9) return [0, 0];
    return tl <= lim ? mul(t, -1) : mul(t, -lim / tl);
  }

  function makeState(course = COURSE, P = DEFAULTS) {
    const p = [...course.start];
    const d = [90, 22];
    return { p, v: [0, 0], d, want: [...d], qPrev: add(p, d), tipHit: null, bodyHit: null, t: 0 };
  }

  const muTip = (P, mat) => mat === "slick" ? P.TIP_FRICTION_SLICK : P.TIP_FRICTION_ROCK;
  const muBody = (P, mat) => mat === "slick" ? P.BODY_FRICTION_SLICK : P.BODY_FRICTION_ROCK;

  /** 물리 한 단계(dt) — 명세 §5.3 순서 그대로 */
  function step(S, P, polys, dt = DT) {
    const p0 = S.p;
    // 1. 중력 · 공기 저항 → 몸통 예측 위치
    let v = [S.v[0], S.v[1] + P.GRAVITY * dt];
    v = mul(v, Math.exp(-P.AIR_DRAG * dt));
    let ph = add(p0, mul(v, dt));
    // 2. 도구 상대 위치를 목표 쪽으로, 한 단계 최대 TOOL_SPEED × dt 만큼만
    const want = clampRange(S.want, P.L_MIN, P.L_MAX, S.d);
    //    각도 · 길이로 나눠 옮긴다 — 직선으로 옮기면 목표가 몸통 반대편일 때 도구가 몸통을 못 넘어간다
    const l0 = len(S.d), a0 = Math.atan2(S.d[1], S.d[0]);
    const lw = len(want), aw = Math.atan2(want[1], want[0]);
    let da = aw - a0;
    da -= Math.PI * 2 * Math.round(da / (Math.PI * 2));
    let dl = lw - l0;
    const move = Math.hypot(l0 * da, dl), maxMove = P.TOOL_SPEED * dt;
    if (move > maxMove) { da *= maxMove / move; dl *= maxMove / move; }
    let d = [Math.cos(a0 + da) * (l0 + dl), Math.sin(a0 + da) * (l0 + dl)];
    d = clampRange(d, P.L_MIN, P.L_MAX, S.d);
    // 2-1. 몸통 자체의 움직임(중력 · 관성)만 면 마찰을 받는다.
    //      도구가 끌어 옮기는 몸통은 마찰로 막지 않는다 — 막으면 벽에 낀 몸통이 도구보다 세져 굴뚝을 못 오른다
    let tipHit = null, bodyHit = null;
    for (const c of contacts(ph, P.R, polys)) {
      ph = add(ph, mul(c.n, c.depth));
      ph = add(ph, friction(p0, ph, c.n, c.depth, muBody(P, c.mat)));
      bodyHit = c;
    }
    // 3. 도구 끝 충돌 → 반동을 몸통에 → 몸통 충돌(밀어내기만), ITER 회 반복
    for (let k = 0; k < P.ITER; k++) {
      let q = add(ph, d);
      let e = [0, 0];
      for (const c of contacts(q, P.TIP_R, polys)) {
        const push = mul(c.n, c.depth);
        q = add(q, push); e = add(e, push);
        const f = friction(S.qPrev, q, c.n, c.depth, muTip(P, c.mat));
        q = add(q, f); e = add(e, f);
        tipHit = c;
      }
      ph = add(ph, mul(e, P.BODY_SHARE));
      for (const c of contacts(ph, P.R, polys)) { ph = add(ph, mul(c.n, c.depth)); bodyHit = c; }
    }
    // 4. 몸통 이동 상한(튕기기 상한) → 한 번 더 몸통 충돌 → 고친 위치에서 속도
    ph = add(p0, clampLen(sub(ph, p0), P.MAX_BODY_SPEED * dt));
    for (const c of contacts(ph, P.R, polys)) { ph = add(ph, mul(c.n, c.depth)); bodyHit = c; }
    // 5. 도구 끝이 끝내 못 간 자리는 실제 위치로 맞춘다(몸통도 도구도 막혔을 때 떨림 방지).
    //    밀려난 끝이 팔 길이 한계를 넘으면 끝을 되돌리지 않고 몸통을 끌어온다 — 끝을 되돌리면 지형 안으로 다시 들어간다
    let q = add(ph, d);
    for (const c of contacts(q, P.TIP_R, polys)) q = add(q, mul(c.n, c.depth));
    const r = sub(q, ph), rl = len(r);
    if (rl > P.L_MAX || rl < P.L_MIN) {
      ph = sub(q, mul(r, (rl > P.L_MAX ? P.L_MAX : P.L_MIN) / (rl || 1)));
      for (const c of contacts(ph, P.R, polys)) { ph = add(ph, mul(c.n, c.depth)); bodyHit = c; }
    }
    S.v = mul(sub(ph, p0), 1 / dt);
    S.p = ph;
    S.d = sub(q, S.p);
    S.qPrev = q;
    S.tipHit = tipHit; S.bodyHit = bodyHit;
    S.t += dt;
    return S;
  }

  const inGoal = (S, g = COURSE.goal) => !!g && S.p[0] > g.x0 && S.p[0] < g.x1 && S.p[1] > g.y0 && S.p[1] < g.y1;

  // ── 레벨 데이터(편집기 · 파일) ─────────────────────────
  // 레벨 JSON = { version: 1, name, start: [x, y], goal: {x0,y0,x1,y1} | null, polys: [{ mat, edgeMat?, pts }] }
  // 그림(스킨)은 넣지 않는다 — 지형 모양 · 재질만. 스킨은 나중에 이 데이터 위에 씌운다
  const MIN_THICKNESS = 60;   // 이보다 얇은 지형은 도구 끝이 뚫을 수 있다(명세 §5.5)
  const MATS = ["rock", "slick"];
  const num = (v) => typeof v === "number" && Number.isFinite(v);

  /** 파일에서 읽은 값을 레벨로 다듬는다. 못 쓰는 다각형은 버리고 이유를 errors 에 적는다 */
  function normalizeLevel(raw) {
    const errors = [];
    if (!raw || typeof raw !== "object") return { level: null, errors: ["레벨 JSON 이 아니다"] };
    const level = { version: 1, name: typeof raw.name === "string" ? raw.name.slice(0, 80) : "", start: [0, -28], goal: null, polys: [] };
    if (Array.isArray(raw.start) && num(raw.start[0]) && num(raw.start[1])) level.start = [raw.start[0], raw.start[1]];
    else errors.push("출발점이 없어 (0, -28) 로 둔다");
    const g = raw.goal;
    if (g && num(g.x0) && num(g.y0) && num(g.x1) && num(g.y1)) level.goal = { x0: Math.min(g.x0, g.x1), y0: Math.min(g.y0, g.y1), x1: Math.max(g.x0, g.x1), y1: Math.max(g.y0, g.y1) };
    (Array.isArray(raw.polys) ? raw.polys : []).forEach((p, i) => {
      const pts = Array.isArray(p?.pts) ? p.pts.filter((q) => Array.isArray(q) && num(q[0]) && num(q[1])).map((q) => [q[0], q[1]]) : [];
      if (pts.length < 3) { errors.push(`지형 ${i + 1}: 꼭짓점이 3개 미만이라 버렸다`); return; }
      const poly = { mat: MATS.includes(p.mat) ? p.mat : "rock", pts };
      if (p.edgeMat && typeof p.edgeMat === "object") {
        const em = {};
        for (const [k, v] of Object.entries(p.edgeMat)) if (/^\d+$/.test(k) && +k < pts.length && MATS.includes(v) && v !== poly.mat) em[k] = v;
        if (Object.keys(em).length) poly.edgeMat = em;
      }
      if (p.curve && typeof p.curve === "object") {
        const cv = {};
        for (const [k, v] of Object.entries(p.curve)) if (/^\d+$/.test(k) && +k < pts.length && Array.isArray(v) && num(v[0]) && num(v[1])) cv[k] = [v[0], v[1]];
        if (Object.keys(cv).length) poly.curve = cv;
      }
      level.polys.push(poly);
    });
    return { level, errors };
  }

  const signedArea = (pts) => pts.reduce((s, a, i) => { const b = pts[(i + 1) % pts.length]; return s + a[0] * b[1] - b[0] * a[1]; }, 0) / 2;
  function segHit(p, dir, a, b) {   // 반직선 p + t·dir 과 선분 ab 의 교점까지 t (없으면 Infinity)
    const e = sub(b, a), den = dir[0] * e[1] - dir[1] * e[0];
    if (Math.abs(den) < 1e-12) return Infinity;
    const w = sub(a, p), t = (w[0] * e[1] - w[1] * e[0]) / den, u = (w[0] * dir[1] - w[1] * dir[0]) / den;
    return t > 1e-6 && u >= 0 && u <= 1 ? t : Infinity;
  }
  function segCross(a, b, c, d) {   // 두 선분이 끝점이 아닌 곳에서 교차하는가
    const o = (p, q, r) => Math.sign((q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0]));
    return o(a, b, c) * o(a, b, d) < 0 && o(c, d, a) * o(c, d, b) < 0;
  }

  /** 지형 안쪽으로 잰 두께 — 각 변의 1/4 · 1/2 · 3/4 지점에서 안쪽으로 쏜 반직선이 반대편 변에 닿는 거리 */
  function thinSpots(poly, min = MIN_THICKNESS) {
    const pts = poly.pts, n = pts.length, out = [];
    for (let i = 0; i < n; i++) {
      const a = pts[i], b = pts[(i + 1) % n], e = sub(b, a), el = len(e);
      if (el < 1e-6) continue;
      for (const t of [0.25, 0.5, 0.75]) {
        const m = add(a, mul(e, t));
        let nrm = [-e[1] / el, e[0] / el];
        if (!inside(add(m, mul(nrm, 0.5)), pts)) nrm = mul(nrm, -1);
        if (!inside(add(m, mul(nrm, 0.5)), pts)) continue;
        let best = Infinity;
        for (let j = 0; j < n; j++) if (j !== i) best = Math.min(best, segHit(m, nrm, pts[j], pts[(j + 1) % n]));
        if (best < min) out.push({ at: add(m, mul(nrm, best / 2)), thickness: best, edge: i });
      }
    }
    return out;
  }

  // ── 곡선 변 ─────────────────────────────────────────
  // 레벨의 변 i 에 curve[i] = [cx, cy] 가 있으면 꼭짓점 i → i+1 을 2차 베지어 곡선(조절점 c)으로 잇는다.
  // 물리는 다각형만 다루므로, 게임을 시작할 때 곡선을 CURVE_STEP 정도 길이의 짧은 변들로 쪼갠다(flattenPoly)
  const CURVE_STEP = 12;
  const bez = (a, c, b, t) => { const u = 1 - t; return [u * u * a[0] + 2 * u * t * c[0] + t * t * b[0], u * u * a[1] + 2 * u * t * c[1] + t * t * b[1]]; };
  const curveSteps = (a, c, b) => Math.max(2, Math.min(48, Math.ceil((len(sub(c, a)) + len(sub(b, c))) / CURVE_STEP)));
  /** 곡선 변을 쪼갠 다각형 — 변 재질도 쪼갠 변마다 이어 받는다. 곡선이 없으면 그대로 돌려준다 */
  function flattenPoly(poly) {
    if (!poly.curve) return poly;
    const n = poly.pts.length, pts = [], em = {};
    for (let i = 0; i < n; i++) {
      const a = poly.pts[i], b = poly.pts[(i + 1) % n], c = poly.curve[i], mat = poly.edgeMat?.[i] ?? poly.mat;
      const steps = c ? curveSteps(a, c, b) : 1;
      for (let k = 0; k < steps; k++) {
        if (mat !== poly.mat) em[pts.length] = mat;
        pts.push(k === 0 ? [a[0], a[1]] : bez(a, c, b, k / steps));
      }
    }
    const out = { mat: poly.mat, pts };
    if (Object.keys(em).length) out.edgeMat = em;
    return out;
  }
  const flattenLevel = (level) => ({ ...level, polys: level.polys.map(flattenPoly) });

  /** 편집기 경고 목록 — { level: "오류"|"주의", text, at: [x, y] }. 곡선은 쪼갠 모양으로 검사한다 */
  function checkLevel(level, P = DEFAULTS) {
    const out = [];
    const flat = level.polys.map(flattenPoly);
    flat.forEach((poly, k) => {
      const name = `지형 ${k + 1}`, pts = poly.pts, n = pts.length;
      if (Math.abs(signedArea(pts)) < 100) out.push({ level: "오류", text: `${name}: 넓이가 거의 0(선처럼 납작하다)`, at: pts[0] });
      for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) {
        if (j === i + 1 || (i === 0 && j === n - 1)) continue;
        if (segCross(pts[i], pts[(i + 1) % n], pts[j], pts[(j + 1) % n])) { out.push({ level: "오류", text: `${name}: 변이 서로 엇갈린다(꼬인 다각형) — 충돌이 틀어진다`, at: pts[i] }); i = n; break; }
      }
      const thin = thinSpots(poly);
      if (thin.length) { const w = thin.reduce((a, b) => (a.thickness < b.thickness ? a : b)); out.push({ level: "주의", text: `${name}: 두께 ${w.thickness.toFixed(0)}u — ${MIN_THICKNESS}u 보다 얇으면 도구 끝이 뚫을 수 있다`, at: w.at, thin }); }
    });
    if (contacts(level.start, P.R, flat).length) out.push({ level: "주의", text: "출발점의 몸통이 지형과 겹친다", at: level.start });
    if (!level.goal) out.push({ level: "주의", text: "골인 영역이 없다 — 깰 수 없는 레벨", at: level.start });
    else if (level.goal.x1 - level.goal.x0 < 2 * P.R || level.goal.y1 - level.goal.y0 < 2 * P.R) out.push({ level: "주의", text: `골인 영역이 몸통(지름 ${2 * P.R}u)보다 좁다`, at: [level.goal.x0, level.goal.y0] });
    return out;
  }

  /** 레벨의 가장 낮은 지형 y — 이보다 한참 아래로 떨어지면 출발점에서 다시 시작 */
  const lowestY = (level) => Math.max(level.start[1], ...level.polys.flatMap((p) => p.pts.map((q) => q[1])));

  return { DEFAULTS, DT, COURSE, MIN_THICKNESS, makeState, step, contacts, inGoal, inside, clampRange, add, sub, mul, len,
    normalizeLevel, checkLevel, thinSpots, signedArea, lowestY, bez, flattenPoly, flattenLevel, CURVE_STEP };
})();
if (typeof module !== "undefined") module.exports = ClimbLogic;
