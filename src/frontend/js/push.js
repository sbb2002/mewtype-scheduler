// (test/live-notify) 라이브 알림 시험판 — 네임플레이트의 멤버 종 · 예고 카드의 방송 종.
// 로컬 실험실(lab/push/server.py)에서만 동작한다. 배포판에는 넣지 않는다.
//
// 이 브라우저의 등록 상태(켠 멤버 · 등록한 영상)는 localStorage 에 두고, 서버에는 「최종 상태」를 통째로 보낸다.
// 연타 방어는 여기서 한다 — 화면은 누를 때마다 즉시 바뀌고, 마지막 조작 뒤 SYNC_DELAY_MS 동안 조용해야 최종 상태 1건만 보낸다.
// 서버 응답과 화면은 무관하다. 네트워크 · 서버 오류는 화면에 알리지 않고 늘어나는 간격으로 다시 보내고,
// 페이지를 열 때마다 한 번 다시 보낸다(서버는 내용이 같으면 쓰지 않으니 비용은 읽기 1건).

const KEY = "mew.push.v1";
const PUSH_API = "";            // 실험실은 프론트와 같은 출처
const SYNC_DELAY_MS = 2000;
const RETRY_MAX_MS = 60000;
const BELL_D = "M12 22a2.5 2.5 0 0 0 2.45-2h-4.9A2.5 2.5 0 0 0 12 22Zm7-6v-5a7 7 0 0 0-5.5-6.84V3a1.5 1.5 0 0 0-3 0v1.16A7 7 0 0 0 5 11v5l-2 2v1h18v-1l-2-2Z";

function load() {
  try {
    const s = JSON.parse(localStorage.getItem(KEY));
    if (s && Array.isArray(s.members) && Array.isArray(s.videos)) return s;
  } catch { /* 저장소 막힘 · 깨짐 → 빈 상태 */ }
  return { members: [], videos: [] };
}
function save() {
  try { localStorage.setItem(KEY, JSON.stringify(st)); } catch { /* 무시 */ }
}

const st = load();
let syncTimer = null;
let retryMs = 2000;
let regP = null;

function supported() {
  return typeof window !== "undefined" && "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

function listOf(kind) {
  return kind === "member" ? st.members : st.videos;
}

function paint(b) {
  const on = listOf(b.dataset.pushKind).includes(b.dataset.pushId);
  b.classList.toggle("is-on", on);
  b.setAttribute("aria-pressed", on ? "true" : "false");
  b.title = on ? `${b.dataset.pushLabel} 켜짐` : `${b.dataset.pushLabel} 꺼짐`;
}

function bell(kind, id, label) {
  if (!supported()) return null;
  const b = document.createElement("button");
  b.type = "button";
  b.className = `push-bell push-bell--${kind}`;
  b.dataset.pushKind = kind;
  b.dataset.pushId = id;
  b.dataset.pushLabel = label;
  b.setAttribute("aria-label", label);
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", BELL_D);
  svg.appendChild(path);
  b.appendChild(svg);
  paint(b);
  b.addEventListener("click", onClick);
  return b;
}

/** 네임플레이트 핸들 옆 멤버 종 */
export function memberBell(key, nameKo) {
  return bell("member", key, `${nameKo || key} 라이브 알림`);
}
/** upcoming · watching 카드의 방송 종 */
export function videoBell(videoId) {
  return bell("video", videoId, "이 방송 라이브 알림");
}

async function onClick(e) {
  // 카드(<a>)로의 이동 · 네임플레이트 트윗 시트 열림을 막는다(트윗 시트 쪽은 tweets.js 가 .push-bell 을 건너뛴다)
  e.preventDefault();
  e.stopPropagation();
  const b = e.currentTarget;
  if (Notification.permission !== "granted") {
    const p = await Notification.requestPermission();
    if (p !== "granted") {
      b.classList.add("is-blocked");
      b.title = "브라우저에서 이 사이트 알림이 차단돼 있어요";
      return;
    }
  }
  const list = listOf(b.dataset.pushKind);
  const i = list.indexOf(b.dataset.pushId);
  if (i >= 0) list.splice(i, 1); else list.push(b.dataset.pushId);
  save();
  document.querySelectorAll(".push-bell").forEach(paint);
  scheduleSync();
}

function scheduleSync(ms = SYNC_DELAY_MS) {
  clearTimeout(syncTimer);
  syncTimer = setTimeout(sync, ms);
}

function b64ToBytes(s) {
  const pad = "=".repeat((4 - (s.length % 4)) % 4);
  const raw = atob((s + pad).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

async function sync() {
  syncTimer = null;
  try {
    regP = regP || navigator.serviceWorker.register("/sw.js");
    const reg = await regP;
    let sub = await reg.pushManager.getSubscription();
    if (!sub) {
      if (!st.members.length && !st.videos.length) return;
      const key = await (await fetch(`${PUSH_API}/push/vapid`)).text();
      sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64ToBytes(key) });
    }
    const r = await fetch(`${PUSH_API}/push/state`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sub: sub.toJSON(), members: st.members, videos: st.videos }),
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    retryMs = 2000;
  } catch (err) {
    console.warn("[push] 다시 보냄 예정", err);
    scheduleSync(retryMs);
    retryMs = Math.min(retryMs * 2, RETRY_MAX_MS);
  }
}

// 페이지를 열 때 한 번 — 이전 방문에서 전송이 실패했거나 서버가 조용히 놓친 등록을 메운다(권한이 있고 켠 것이 있을 때만)
if (supported() && Notification.permission === "granted" && (st.members.length || st.videos.length)) {
  scheduleSync(3000);
}

/** 보드를 다시 그릴 때마다 — 더는 upcoming · watching 이 아닌 영상 등록은 지운다(live 가 됐거나 사라짐). */
export function pruneVideos(preview) {
  const alive = new Set(((preview && preview.items) || [])
    .filter((it) => it.video_id && (it.state === "upcoming" || it.state === "watching"))
    .map((it) => it.video_id));
  const next = st.videos.filter((v) => alive.has(v));
  if (next.length !== st.videos.length) {
    st.videos = next;
    save();
    scheduleSync();
  }
}
