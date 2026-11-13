// bgmusic.js — (bg-dome 시나리오, 11-13) 유메미타 플레이어 곡 ↔ UFO 돔 연결.
// 플레이어(player.js)가 쏘는 "mew:player-state" 를 듣고(플레이어 모듈은 첫 클릭 때 늦게 불리므로 import 하지 않고 이벤트 이름만 쓴다):
//   · 음악 테두리* — 배경 보기 중 곡이 재생되면 화면 위 가장자리에 부르는 멤버 색 띠가 천천히 숨 쉰다(그룹 곡 = 다섯 색).
//     * 음악 테두리 = 곡이 흐르는 동안 화면 위 가장자리에 깔리는 멤버 색 빛 띠. 바닥 조명(라이브 조명 · 별빛 조명)과 자리를 나눠 「라이브 중」 과 섞이지 않게 했다(운영자 11-13 Claude 추천안 채택).
//   · 솔로 곡이면 그 멤버의 탄생 별자리가 기본 우주 하늘에 멤버 색으로 옅게 떠오른다(아직 못 찾았을 때만 — 찾기 힌트, bghud.js 가 그린다).
// 배경 보기에서 플레이어 창이 걷혀도 재생은 계속된다(운영자 11-13 결정 — 바꾸지 않는다). 그래서 이 모듈은 「소리만 들리는 상태」 를 돔 쪽 빛으로 드러낸다.
// 박자 · 스펙트럼 연동은 하지 않는다 — iframe 안의 소리는 페이지가 못 읽고, 곡별 BPM 자료도 없다.
// DOM 은 createMusicRim 만 만진다. 위쪽 순수 함수는 bgmusic.selfcheck.mjs 가 확인한다.

export const PLAYER_STATE_EVENT = "mew:player-state";   // player.js 와 같은 이름

/** 이벤트 detail → { on(지금 소리가 나는 중), members(멤버 키 배열) }. 버퍼링은 바로 앞 상태를 이어 간다(잠깐 끊겨도 깜빡이지 않게) */
export function nextMusic(prev, detail) {
  const d = detail && typeof detail === "object" ? detail : {};
  const members = Array.isArray(d.members) ? d.members.filter((k) => typeof k === "string" && k) : [];
  if (d.state === "buffering") return prev && prev.on ? { on: true, members: members.length ? members : prev.members } : { on: false, members };
  return { on: d.state === "playing" && members.length > 0, members };
}

/** 솔로 곡이면 그 멤버 키, 아니면 null */
export const soloOf = (m) => (m && m.on && m.members.length === 1 ? m.members[0] : null);

/** 음악 테두리 그라데이션 — 멤버 색을 같은 폭으로 나란히(색 순환 점멸 없음). colors = { key: "#RRGGBB" }. 색을 모르는 멤버는 뺀다 */
export function rimGradient(members, colors) {
  const cs = (members || []).map((k) => colors && colors[k]).filter((c) => typeof c === "string" && /^#[0-9a-f]{6}$/i.test(c));
  if (!cs.length) return "";
  if (cs.length === 1) return `linear-gradient(90deg, transparent, ${cs[0]} 18%, ${cs[0]} 82%, transparent)`;
  const stops = cs.map((c, i) => `${c} ${Math.round(((i + 0.5) / cs.length) * 100)}%`);
  return `linear-gradient(90deg, transparent, ${stops.join(", ")}, transparent)`;
}

/** "#RRGGBB" → "r,g,b" (bghud.js 의 색 표기) */
export function rgbOf(hex) {
  const m = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex || "");
  return m ? `${parseInt(m[1], 16)},${parseInt(m[2], 16)},${parseInt(m[3], 16)}` : null;
}

/**
 * 돔 장면이 살아 있는 동안 음악 테두리를 둔다. colors = 멤버 색 표(config.js MEMBER_LIGHT_COLORS).
 * 돌려줌 = { get music() — 지금 상태 { on, members }, remove() }. signal(AbortSignal)이 끊기면 리스너도 뗀다.
 */
export function createMusicRim(colors, signal) {
  if (typeof document === "undefined") return { music: { on: false, members: [] }, remove() {} };
  const el = document.createElement("div");
  el.className = "bg-music-rim";
  el.setAttribute("aria-hidden", "true");
  document.body.appendChild(el);
  let music = { on: false, members: [] }, sig = "";
  const apply = () => {
    const s = music.on ? music.members.join(",") : "";
    if (s === sig) return;
    sig = s;
    if (s) el.style.setProperty("--rim", rimGradient(music.members, colors));
    el.classList.toggle("is-on", !!s);
  };
  document.addEventListener(PLAYER_STATE_EVENT, (e) => { music = nextMusic(music, e.detail); apply(); }, signal ? { signal } : undefined);
  return {
    get music() { return music; },
    remove() { el.remove(); },
  };
}
