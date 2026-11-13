// bgyawfix.js — (실험 브랜치 bg-dome-claude-test · 시험 중) 「움직임 연동 방위 보정」 순수 로직. DOM · 센서 없음.
// 설계 = devpapers ref/bg-dome/gaze-jump-lit/METHOD.md. 재생 시험 = scripts/replay_yawfix.mjs.
//
//   움직임 연동 방위 보정* — 화면 방위 = 상대 방위 r(자력계 없음, 계단 없음) + 반영된 보정량 b.
//     보정량(절대 방위 a − r)의 목표 ê 는 폰이 멈춰 있을 때만 갱신하고,
//     b 는 폰이 돌아가는 동안에만 돌린 양에 비례해 ê 쪽으로 옮긴다. 멈춰 있으면 화면이 혼자 움직이지 않는다.
//   * 근거: Foxlin 특허 US5645077(멈췄을 때 재고 나눠서 반영) · AeroSense 98 PPF(보정량만 거르고, 느려질수록 억제)
//
// 각도 = 라디안, 시각 = ms. 방위만 다룬다(고도는 계단이 없어 그대로 — METHOD.md 4장).

const DEG = Math.PI / 180;
export const wrap = (x) => Math.atan2(Math.sin(x), Math.cos(x));

export const YAWFIX_DEFAULTS = {
  wStill: 8 * DEG,    // 정지 판정 문턱(라디안/초) — 상대 방위 회전 속도가 이보다 낮으면 정지
  wMove: 8 * DEG,     // 반영 문턱 — 이보다 빠를 때만 b 를 옮긴다
  tStill: 500,        // 목표 갱신 전 정지 지속(ms)
  k: 0.2,             // 돌린 양 대비 보정 비율(회전 이득 1 ± k)
  vMax: 15 * DEG,     // 초당 보정 상한(라디안/초)
  tauW: 120,          // 회전 속도 평활 시간 상수(ms)
  pairMs: 40,         // 보정량 측정에 쓸 두 센서 판독의 최대 시각 차(ms)
  gapMs: 1000,        // 상대 방위가 이만큼 끊기면 재시작으로 보고 b 를 바로 맞춘다
  bufMax: 64,         // 정지 구간 보정량 표본 최대 개수(중앙값용)
};

/** 보정기를 만든다. onRel · onAbs 로 판독을 넣고 yaw() 로 화면 방위를 읽는다 */
export function createYawFix(opts = {}) {
  const o = { ...YAWFIX_DEFAULTS, ...opts };
  let rT = null, r = 0;          // 마지막 상대 방위
  let aT = null, a = 0;          // 마지막 절대 방위
  let w = 0;                     // 평활한 회전 속도(라디안/초)
  let b = null, eHat = null;     // 반영된 보정량 · 목표
  let stillSince = null, buf = [];
  const st = { resets: 0, targetUpdates: 0 };

  function median(ref) {
    const d = buf.map((e) => wrap(e - ref)).sort((x, y) => x - y);
    const m = d.length >> 1;
    return wrap(ref + (d.length % 2 ? d[m] : (d[m - 1] + d[m]) / 2));
  }

  function measure(t) {
    if (rT == null || aT == null || Math.abs(t - (t === rT ? aT : rT)) > o.pairMs) return;
    const e = wrap(a - r);
    if (b == null) { b = e; eHat = e; st.resets++; return; }   // 처음 · 재시작 = 바로 맞춘다(상대 방위 기준이 임의라 이어 붙일 화면이 없다)
    if (stillSince == null) return;                          // 회전 중의 차이는 두 센서 시각 차로 틀어진다 — 버린다
    buf.push(e);
    if (buf.length > o.bufMax) buf.shift();
    if (t - stillSince >= o.tStill) { eHat = median(eHat); st.targetUpdates++; }
  }

  /** 상대 방위 판독(RelativeOrientationSensor). frozen = 고도가 너무 커 방위가 정의되지 않는 중 */
  function onRel(t, yaw, frozen = false) {
    if (rT != null && t - rT > o.gapMs) { b = null; eHat = null; w = 0; stillSince = null; buf = []; rT = null; }
    if (frozen) { rT = t; return; }
    if (rT == null) { rT = t; r = yaw; stillSince = t; measure(t); return; }
    const dt = Math.max(1, t - rT), dr = wrap(yaw - r);
    w += (Math.abs(dr) / (dt / 1000) - w) * (1 - Math.exp(-dt / o.tauW));
    rT = t; r = yaw;
    if (w < o.wStill) { if (stillSince == null) { stillSince = t; buf = []; } }
    else { stillSince = null; buf = []; }
    if (b != null && w >= o.wMove) {
      const lim = Math.min(o.k * Math.abs(dr), o.vMax * dt / 1000);
      b += Math.max(-lim, Math.min(lim, wrap(eHat - b)));
      b = wrap(b);
    }
    measure(t);
  }

  /** 절대 방위 판독(AbsoluteOrientationSensor, 자북 기준) */
  function onAbs(t, yaw, frozen = false) {
    if (frozen) return;
    aT = t; a = yaw;
    measure(t);
  }

  return {
    onRel, onAbs,
    /** 화면 방위(자북 기준, 편각은 부르는 쪽이 더한다) — 아직 못 맞췄으면 null */
    yaw: () => (b == null || rT == null ? null : wrap(r + b)),
    /** 확인용 상태 */
    debug: () => ({ r, a, w, b, eHat, still: stillSince != null, ...st }),
  };
}
