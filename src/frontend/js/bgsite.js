// bgsite.js — (bg-dome 시험) 「바깥 보기」에 쓰는 기기 위치. 위치 권한을 받아 위도 · 경도를 얻는다.
// 저정밀 요청(GPS 대신 와이파이 · 기지국 — 빠르고 배터리를 덜 쓴다)이고, 소수 1자리(약 10km)로 줄여 해 · 달 계산에만 쓴다.
// 좌표는 기기 밖으로 보내지 않고 저장하지도 않는다(다음 방문엔 브라우저가 기억한 권한으로 다시 받는다).

const GEO_OPTS = { enableHighAccuracy: false, timeout: 15000, maximumAge: 6 * 3600 * 1000 };
let site = null;   // { lat, lon } (도)

export const outdoorSite = () => site;

/** 위치 권한 상태 — "granted" | "denied" | "prompt" | "unknown"(물어볼 수 없는 브라우저) */
export async function geoPermission() {
  try {
    const st = await navigator.permissions.query({ name: "geolocation" });
    return st.state;
  } catch { return "unknown"; }
}

function getPosition() {
  return new Promise((resolve) => {
    if (!navigator.geolocation) { resolve({ error: "unsupported" }); return; }
    navigator.geolocation.getCurrentPosition(
      (p) => resolve({ lat: Math.round(p.coords.latitude * 10) / 10, lon: Math.round(p.coords.longitude * 10) / 10 }),
      (e) => resolve({ error: e && e.code === 1 ? "denied" : "failed" }),
      GEO_OPTS,
    );
  });
}

/** 위치를 받아 둔다. 결과 = "ok" | "denied"(거절 · 이미 거절됨 — before 로 구분) | "failed"(신호 없음 · 시간 초과) | "unsupported" */
export async function acquireSite() {
  const before = await geoPermission();
  const r = await getPosition();
  if (r.error) return { result: r.error, before };
  site = { lat: r.lat, lon: r.lon };
  return { result: "ok", before };
}
