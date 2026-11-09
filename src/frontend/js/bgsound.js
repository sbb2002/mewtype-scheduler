// bgsound.js — (bg-dome 4단계) 성간 이동 소리 — Web Audio.
//   · ding()        좌석벨트 표시등이 켜지고 꺼질 때 기내 차임 「띵」(합성, 시안 Gear.dc.html 그대로: 기음 + 약한 배음, 1.5초에 걸쳐 잦아듦)
//   · alarm(k)      5단 경보음 — 음원 assets/bg/sfx/alarm.wav 를 끊김 없이 반복(아래)
//   · jump(kind)    워프 점프 — 음원 assets/bg/sfx/warp-jump.m4a 의 절정이 도착 순간에 오게(아래)
//   (엔진 울림 · 합성 사이렌 · 합성 점프음은 뺐다 — 운영자 11-06 「거슬림」 · 「마음에 안 듦」 · 「촌스러움」. 음원 출처 = assets/bg/README.md)
// 브라우저는 사용자가 누른 뒤에만 소리를 낸다 — wake() 를 누르는 손길(기어 · WARP · 길게 누르기)에서 부른다. 탭이 숨으면 멈춘다.
// 음원은 wake() 때 한 번 받아 풀어 둔다(합쳐 약 80KB). 아직 못 받았으면 그 소리만 조용히 건너뛴다.
// 유메미타 플레이어와 겹쳐도 된다(운영자 11-06 계획서 0번 4). 소리 크기 전체 0.9 + 압축기(11-09 운영자 요청으로 키움 — 전엔 0.35).

let ac = null, master = null;
const AC = () => window.AudioContext || window.webkitAudioContext;
const SRC = { alarm: new URL("../assets/bg/sfx/alarm.wav", import.meta.url).href, jump: new URL("../assets/bg/sfx/warp-jump.m4a", import.meta.url).href };
const buf = {};   // 이름 → AudioBuffer(받는 중이면 Promise)

function load(name) {
  if (buf[name]) return;
  buf[name] = fetch(SRC[name]).then((r) => (r.ok ? r.arrayBuffer() : Promise.reject(r.status)))
    .then((a) => new Promise((ok, no) => ac.decodeAudioData(a, ok, no)))   // 옛 Safari 는 콜백 형태만
    .then((b) => { buf[name] = b; }, () => { setTimeout(() => { if (!(buf[name] instanceof AudioBuffer)) buf[name] = null; }, 10000); });   // 실패하면 10초 뒤 다시 받을 수 있게
}
const ready = () => ac && ac.state === "running";
const got = (name) => (buf[name] instanceof AudioBuffer ? buf[name] : null);

/** 누르는 손길 안에서 부른다 — 처음이면 만들고, 잠들어 있으면 깨운다 */
export function wake() {
  try {
    if (!ac) {
      const C = AC(); if (!C) return;
      ac = new C(); master = ac.createGain(); master.gain.value = 0.9;   // (11-09 운영자 「사이렌 · 워프 소리가 너무 작음」) 0.35 → 0.9. 커진 만큼 겹쳐 찢어지지 않게 압축기를 거친다
      const comp = ac.createDynamicsCompressor(); comp.threshold.value = -14; comp.knee.value = 12; comp.ratio.value = 6; comp.attack.value = 0.003; comp.release.value = 0.2;
      master.connect(comp); comp.connect(ac.destination);
      document.addEventListener("visibilitychange", () => { if (!ac) return; if (document.hidden) ac.suspend(); else ac.resume(); });
    }
    if (ac.state === "suspended" && !document.hidden) ac.resume();
    load("alarm"); load("jump");
  } catch { ac = null; }
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

/** (11-09 운영자 「해금 이펙트가 심심함」) 해금 · 탐험 완료 팡파르 — 위로 오르는 네 음(도 미 솔 도)과 반짝이는 배음 */
export function unlock() {
  if (!ready()) return;
  const t = ac.currentTime, out = ac.createGain(); out.gain.value = 0.55; out.connect(master);
  [523.25, 659.25, 783.99, 1046.5].forEach((f, k) => {
    const o = ac.createOscillator(), o2 = ac.createOscillator(), e = ac.createGain(), at = t + k * 0.09;
    o.type = "triangle"; o.frequency.value = f; o2.type = "sine"; o2.frequency.value = f * 2;
    env(e, at, k === 3 ? 1 : 0.7, 0.01, k === 3 ? 1.4 : 0.5);
    o.connect(e); o2.connect(e); e.connect(out); o.start(at); o2.start(at); o.stop(at + 1.5); o2.stop(at + 1.5);
  });
}

// 경보음(운영자 11-06 — Freesound 후보 중 「Digital Alarm Loop」 고름) — 5단 + 좌석벨트 표시등 켜짐 경보(bgdomegl.js alarmK)와 같이 커지고 작아진다.
// 0.24초짜리 한 음 삐삐음을 끊김 없이 반복(WAV 라 앞뒤 빈틈 없음). 음량은 낮게(운영자 「모두 볼륨 낮춰」) — 원음 평균 −31.5dB × 0.6 × 전체 0.35.
const ALARM_GAIN = 1.6;
let siren = null;
export function alarm(k) {
  if (!ready()) return;
  const t = ac.currentTime;
  if (!siren && k > 0.01) {
    const b = got("alarm"); if (!b) return;
    const g = ac.createGain(); g.gain.value = 0.0001; g.connect(master);
    const s = ac.createBufferSource(); s.buffer = b; s.loop = true; s.connect(g); s.start();
    siren = { g, s };
  }
  if (!siren) return;
  siren.g.gain.setTargetAtTime(k > 0.01 ? ALARM_GAIN * k : 0.0001, t, 0.12);
  if (k <= 0.01 && !siren.stopAt) { siren.stopAt = 1; const s = siren; setTimeout(() => { if (siren === s && s.stopAt) { siren = null; try { s.s.stop(); s.g.disconnect(); } catch { /* 이미 */ } } }, 1500); }
  if (k > 0.01) siren.stopAt = 0;
}

// 워프 점프(운영자 11-06 — 「Warp Speed」 고름, 절정만 잘라 빠르게 페이드 인). warp-jump.m4a = 원본 12.8 ~ 17.3초(4.5초): 소리가 차오르다 1.2초 지점(원본 14.0초)에서
// 가장 크고, 그 뒤 잦아든다(끝 0.8초 페이드 아웃은 파일에 넣어 둠). 절정을 점프 「도착」 순간(bgwarp.jumpFrame — A 0.62초 섬광 · B 바로 · C 0.7초 충격파)에 맞추려고
// 연출마다 파일의 다른 지점부터 틀고, 시작은 0.12초 페이드 인으로 부드럽게 든다.
const JUMP_PEAK = 1.2, JUMP_ARRIVE = { A: 0.62, B: 0, C: 0.7 }, JUMP_FADE = 0.12, JUMP_GAIN = 0.9;
export function jump(kind) {
  if (!ready()) return;
  const b = got("jump"); if (!b) return;
  const t = ac.currentTime, off = Math.max(0, JUMP_PEAK - (JUMP_ARRIVE[kind] ?? 0));
  const g = ac.createGain(); g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(JUMP_GAIN, t + JUMP_FADE); g.connect(master);
  const s = ac.createBufferSource(); s.buffer = b; s.connect(g); s.start(t, off);
  s.onended = () => { try { g.disconnect(); } catch { /* 이미 */ } };
}
