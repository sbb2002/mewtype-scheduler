// sheetdrag.js — 시트 끌어 닫기 (마이크로 인터랙션). 소식 시트 · 트윗 토스트 · 플레이어 시트(모바일)가 같이 쓴다.
// 손잡이를 닫는 방향으로 끌면 시트가 손을 따라오고 배경이 옅어진다. 「닫힘 선」(시트 높이의 30%, 최대 150px)을 넘으면
// 시트에 .is-armed(손잡이 막대가 길어지고 색이 바뀜) + 진동 14ms, 다시 물러나면 풀리며 진동 6ms. 놓았을 때 닫힘 선을 넘었거나
// 닫는 방향으로 빠르게 튕겼으면(0.55px/ms 이상 · 24px 이상) 닫고, 아니면 .is-spring 으로 튕겨 돌아간다. 반대 방향은 22px 까지만 버틴다.
// dir: "down" = 아래에서 올라온 시트(아래로 끌어 닫기) · "up" = 위에서 내려온 토스트(위로 밀어 닫기).
// 닫을 때는 인라인 transform 을 지운 뒤 close() 를 부른다 — 시트의 원래 닫힘 전환이 끌던 자리에서 이어서 돈다.
// 진동(navigator.vibrate)은 안드로이드에서만 울린다. 움직임 줄이기 설정이면 튕겨 돌아가기 애니메이션은 뺀다.

export const vibrate = (ms) => { try { if (navigator.vibrate) navigator.vibrate(ms); } catch (e) { /* 무시 */ } };
const reduce = () => !!(window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches);

const ARM_RATIO = 0.3, ARM_MAX = 150;   // 닫힘 선
const FLICK_V = 0.55, FLICK_MIN = 24;    // 튕겨 닫기
const BACK_MAX = 22;                     // 반대 방향 버팀
const SPRING_MS = 460;                   // .is-spring 유지 시간 (CSS 전환 길이와 맞춘다)

/**
 * @param {Object} o
 * @param {HTMLElement} o.sheet     움직일 시트 요소 (.is-dragging · .is-armed · .is-spring 이 붙는다)
 * @param {HTMLElement[]} o.handles 끌기를 시작하는 곳 (손잡이 줄 · 머리줄). 안의 버튼 · 링크 · 입력칸에서는 시작하지 않는다
 * @param {"down"|"up"} [o.dir]
 * @param {() => boolean} o.isOpen  지금 열려 있고 끌어 닫기가 가능한가
 * @param {() => void} o.close      닫기 (시트 쪽 원래 닫기 함수)
 * @param {(v: number|null) => void} [o.setScrim]  배경 진하기 0~1 (null = 원래대로)
 * @param {() => void} [o.onMove]   시트 위치가 바뀔 때마다 (플레이어 프레임이 따라오게)
 */
export function wireSheetDrag({ sheet, handles, dir = "down", isOpen, close, setScrim, onMove }) {
  const sgn = dir === "down" ? 1 : -1;
  let d = null, springT = 0;
  const scrim = (v) => { if (setScrim) setScrim(v); };
  const moved = () => { if (onMove) onMove(); };

  const down = (e) => {
    if (d || !isOpen() || (e.pointerType === "mouse" && e.button !== 0)) return;
    if (e.target instanceof Element && e.target.closest("button, a, input, select, textarea")) return;
    d = { id: e.pointerId, el: e.currentTarget, y0: e.clientY, h: sheet.offsetHeight || 1, dy: 0, armed: false, pts: [{ y: e.clientY, t: e.timeStamp }] };
    try { e.currentTarget.setPointerCapture(e.pointerId); } catch (_) { /* 이미 놓았으면 무시 */ }
    clearTimeout(springT);
    sheet.classList.remove("is-spring");
    sheet.classList.add("is-dragging");
  };
  const move = (e) => {
    if (!d || e.pointerId !== d.id) return;
    const dy = (e.clientY - d.y0) * sgn;   // 닫는 방향이 +
    d.dy = dy;
    const shown = dy >= 0 ? dy : -Math.min(BACK_MAX, Math.pow(-dy, 0.72));
    sheet.style.transform = `translateY(${(shown * sgn).toFixed(1)}px)`;
    scrim(1 - Math.min(1, Math.max(0, dy / d.h)) * 0.9);
    const armed = dy > Math.min(ARM_MAX, d.h * ARM_RATIO);
    if (armed !== d.armed) { d.armed = armed; sheet.classList.toggle("is-armed", armed); vibrate(armed ? 14 : 6); }
    d.pts.push({ y: e.clientY, t: e.timeStamp });
    if (d.pts.length > 5) d.pts.shift();
    moved();
  };
  const end = (commit) => (e) => {
    if (!d || e.pointerId !== d.id) return;
    const g = d;
    d = null;
    sheet.classList.remove("is-dragging", "is-armed");
    const p0 = g.pts[0], p1 = g.pts[g.pts.length - 1];
    const v = p1.t > p0.t ? ((p1.y - p0.y) * sgn) / (p1.t - p0.t) : 0;
    sheet.style.transform = "";
    scrim(null);
    if (commit && (g.armed || (v > FLICK_V && g.dy > FLICK_MIN))) { close(); return; }
    if (Math.abs(g.dy) > 1 && !reduce()) {
      sheet.classList.add("is-spring");
      springT = setTimeout(() => sheet.classList.remove("is-spring"), SPRING_MS);
    }
    moved();
  };
  for (const h of handles) {
    if (!h) continue;
    h.addEventListener("pointerdown", down);
    h.addEventListener("pointermove", move);
    h.addEventListener("pointerup", end(true));
    h.addEventListener("pointercancel", end(false));
  }
}
