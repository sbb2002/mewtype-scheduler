// bgsound.js — (bg-dome 4단계) 성간 이동 소리 — 음원 파일 없이 Web Audio 로 합성(외부 파일 · 라이브러리 없음).
//   · ding()        좌석벨트 표시등이 켜지고 꺼질 때 기내 차임 「띵」(시안 Gear.dc.html 그대로: 기음 + 약한 배음, 1.5초에 걸쳐 잦아듦)
//   (엔진 울림은 뺐다 — 운영자 11-06 「가속 시 엔진 소리 거슬림」)
//   · alarm(k)      5단 경보 사이렌(아래)
//   · jump(kind)    워프 점프 소리 — A 섬광 돌파(빨려 드는 바람 → 쾅) · B 홀로그램 재투영(디지털 반짝임이 쓸려 내려감) · C 터널 급제동(쿵쿵 터널 → 끼익 제동)
// 브라우저는 사용자가 누른 뒤에만 소리를 낸다 — wake() 를 누르는 손길(기어 · WARP · 길게 누르기)에서 부른다. 탭이 숨으면 멈춘다.
// 유메미타 플레이어와 겹쳐도 된다(운영자 11-06 계획서 0번 4). 소리 크기는 전체 0.35 로 낮게.

let ac = null, master = null;
const AC = () => window.AudioContext || window.webkitAudioContext;

/** 누르는 손길 안에서 부른다 — 처음이면 만들고, 잠들어 있으면 깨운다 */
export function wake() {
  try {
    if (!ac) {
      const C = AC(); if (!C) return;
      ac = new C(); master = ac.createGain(); master.gain.value = 0.35; master.connect(ac.destination);
      document.addEventListener("visibilitychange", () => { if (!ac) return; if (document.hidden) ac.suspend(); else ac.resume(); });
    }
    if (ac.state === "suspended" && !document.hidden) ac.resume();
  } catch { ac = null; }
}
const ready = () => ac && ac.state === "running";

function noiseBuffer(sec) {
  const n = Math.floor(ac.sampleRate * sec), b = ac.createBuffer(1, n, ac.sampleRate), d = b.getChannelData(0);
  for (let i = 0; i < n; i++) d[i] = Math.random() * 2 - 1;
  return b;
}
function env(g, t, peak, a, dec) { g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(peak, t + a); g.gain.exponentialRampToValueAtTime(0.0001, t + a + dec); }

export function ding() {
  if (!ready()) return;
  const t = ac.currentTime, out = ac.createGain(); out.gain.value = 0.6; out.connect(master);
  [[1174.7, 1], [2349.3, 0.22], [3524, 0.07]].forEach(([f, g], k) => {
    const o = ac.createOscillator(), e = ac.createGain();
    o.type = "sine"; o.frequency.value = f; env(e, t, g, 0.006, k ? 0.7 : 1.5);
    o.connect(e); e.connect(out); o.start(t); o.stop(t + 1.6);
  });
}

/** 워프 점프 소리(점프 연출 bgwarp.js jumpFrame 시간표에 맞춤 — A 620ms 섬광 · C 700ms 충격파) */
export function jump(kind) {
  if (!ready()) return;
  const t = ac.currentTime, out = ac.createGain(); out.gain.value = 1; out.connect(master);
  const noise = (sec) => { const s = ac.createBufferSource(); s.buffer = noiseBuffer(sec); return s; };
  const boom = (at, f0, f1, peak, dec) => {
    const o = ac.createOscillator(), e = ac.createGain(); o.type = "sine";
    o.frequency.setValueAtTime(f0, at); o.frequency.exponentialRampToValueAtTime(f1, at + dec * 0.8);
    env(e, at, peak, 0.01, dec); o.connect(e); e.connect(out); o.start(at); o.stop(at + dec + 0.1);
  };
  if (kind === "A") {
    // 빨려 드는 바람(띠 거름이 위로 쓸려 올라감) → 섬광 순간 쾅(낮은 음 + 잡음 터짐) → 긴 꼬리
    const n = noise(0.7), bp = ac.createBiquadFilter(), e = ac.createGain(); bp.type = "bandpass"; bp.Q.value = 3;
    bp.frequency.setValueAtTime(300, t); bp.frequency.exponentialRampToValueAtTime(7000, t + 0.62);
    e.gain.setValueAtTime(0.0001, t); e.gain.exponentialRampToValueAtTime(0.9, t + 0.58); e.gain.exponentialRampToValueAtTime(0.0001, t + 0.7);
    n.connect(bp); bp.connect(e); e.connect(out); n.start(t);
    boom(t + 0.62, 110, 32, 1.0, 1.8);
    const n2 = noise(1.2), lp = ac.createBiquadFilter(), e2 = ac.createGain(); lp.type = "lowpass"; lp.frequency.value = 1200;
    env(e2, t + 0.62, 0.7, 0.005, 1.1); n2.connect(lp); lp.connect(e2); e2.connect(out); n2.start(t + 0.62);
  } else if (kind === "B") {
    // 디지털 반짝임: 높은 음 알갱이가 빠르게 내려오며 흩어지고(재투영 고리), 잡음이 위에서 아래로 쓸린다 · 바로 급제동의 낮은 쿵
    boom(t, 90, 40, 0.8, 0.9);
    for (let i = 0; i < 14; i++) {
      const at = t + 0.04 + i * 0.075, o = ac.createOscillator(), e = ac.createGain();
      o.type = "square"; o.frequency.value = 2600 * Math.pow(0.86, i) * (1 + (Math.random() - 0.5) * 0.08);
      env(e, at, 0.12 * (1 - i / 16), 0.003, 0.09); o.connect(e); e.connect(out); o.start(at); o.stop(at + 0.12);
    }
    const n = noise(1.5), bp = ac.createBiquadFilter(), e = ac.createGain(); bp.type = "bandpass"; bp.Q.value = 4;
    bp.frequency.setValueAtTime(6000, t); bp.frequency.exponentialRampToValueAtTime(400, t + 1.4);
    env(e, t, 0.45, 0.05, 1.35); n.connect(bp); bp.connect(e); e.connect(out); n.start(t);
  } else {
    // 터널: 초당 8 번 쿵쿵 울리는 바람(고리가 지나감) → 충격파 순간 쿵 + 금속성 끼익(공명 띠 거름 잡음)이 잦아듦
    const n = noise(0.75), bp = ac.createBiquadFilter(), e = ac.createGain(), am = ac.createGain(), lfo = ac.createOscillator(), lg = ac.createGain();
    bp.type = "bandpass"; bp.Q.value = 2; bp.frequency.setValueAtTime(500, t); bp.frequency.exponentialRampToValueAtTime(2500, t + 0.7);
    lfo.frequency.value = 8; lg.gain.value = 0.5; am.gain.value = 0.5; lfo.connect(lg); lg.connect(am.gain);
    e.gain.setValueAtTime(0.0001, t); e.gain.exponentialRampToValueAtTime(0.7, t + 0.6); e.gain.exponentialRampToValueAtTime(0.0001, t + 0.72);
    n.connect(bp); bp.connect(am); am.connect(e); e.connect(out); n.start(t); lfo.start(t); lfo.stop(t + 0.75);
    boom(t + 0.7, 70, 30, 1.0, 1.4);
    const n2 = noise(1.4), sq = ac.createBiquadFilter(), e2 = ac.createGain(); sq.type = "bandpass"; sq.Q.value = 18;
    sq.frequency.setValueAtTime(3200, t + 0.7); sq.frequency.exponentialRampToValueAtTime(1400, t + 1.9);
    env(e2, t + 0.7, 0.5, 0.02, 1.2); n2.connect(sq); sq.connect(e2); e2.connect(out); n2.start(t + 0.7);
  }
  setTimeout(() => { try { out.disconnect(); } catch { /* 이미 */ } }, 4000);
}

// 경보음(11-06 운영자 「경보음도」) — 5단 + 좌석벨트 표시등 켜짐 경보(bgdomegl.js alarmK)와 같이 커지고 작아진다.
// 오르내리는 사이렌: 톱니파 두 개(살짝 어긋나게)를 띠 거름에 통과, 음 높이가 600 ↔ 900Hz 를 1.25초 주기로 부드럽게 오르내린다(화면 붉은 가장자리 맥동과 같은 박자).
let siren = null;
export function alarm(k) {
  if (!ready()) return;
  const t = ac.currentTime;
  if (!siren && k > 0.01) {
    const g = ac.createGain(); g.gain.value = 0.0001;
    const bp = ac.createBiquadFilter(); bp.type = "bandpass"; bp.frequency.value = 900; bp.Q.value = 0.9;
    const o1 = ac.createOscillator(), o2 = ac.createOscillator(); o1.type = o2.type = "sawtooth"; o1.frequency.value = 750; o2.frequency.value = 750; o2.detune.value = 9;
    const lfo = ac.createOscillator(), depth = ac.createGain(); lfo.frequency.value = 0.8; depth.gain.value = 150;
    lfo.connect(depth); depth.connect(o1.frequency); depth.connect(o2.frequency);
    o1.connect(bp); o2.connect(bp); bp.connect(g); g.connect(master);
    o1.start(); o2.start(); lfo.start();
    siren = { g, o1, o2, lfo };
  }
  if (!siren) return;
  siren.g.gain.setTargetAtTime(k > 0.01 ? 0.11 * k : 0.0001, t, 0.12);
  if (k <= 0.01 && !siren.stopAt) { siren.stopAt = 1; const s = siren; setTimeout(() => { if (siren === s && s.stopAt) { siren = null; try { s.o1.stop(); s.o2.stop(); s.lfo.stop(); s.g.disconnect(); } catch { /* 이미 */ } } }, 1500); }
  if (k > 0.01) siren.stopAt = 0;
}
