// bgsound.js — (bg-dome 4단계) 성간 이동 소리 — 음원 파일 없이 Web Audio 로 합성(외부 파일 · 라이브러리 없음).
//   · ding()        좌석벨트 표시등이 켜지고 꺼질 때 기내 차임 「띵」(시안 Gear.dc.html 그대로: 기음 + 약한 배음, 1.5초에 걸쳐 잦아듦)
//   (엔진 울림은 뺐다 — 운영자 11-06 「가속 시 엔진 소리 거슬림」)
//   · alarm(k)      5단 경보 사이렌(아래)
//   (워프 점프 합성음도 뺐다 — 운영자 11-06 「촌스러움」. 음원으로 바꿀 후보 조사 중)
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
  siren.g.gain.setTargetAtTime(k > 0.01 ? 0.035 * k : 0.0001, t, 0.12);   // 0.11 → 0.035(약 −10dB, 운영자 11-06 「사이렌 마음에 안 듦 — 일단 낮춰」. 음원으로 바꿀 후보 조사 중)
  if (k <= 0.01 && !siren.stopAt) { siren.stopAt = 1; const s = siren; setTimeout(() => { if (siren === s && s.stopAt) { siren = null; try { s.o1.stop(); s.o2.stop(); s.lfo.stop(); s.g.disconnect(); } catch { /* 이미 */ } } }, 1500); }
  if (k > 0.01) siren.stopAt = 0;
}
