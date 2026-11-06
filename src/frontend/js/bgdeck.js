// bgdeck.js — (bg-dome 3단계) 성간 이동 중 「워프 기어 패널」과 「UFO 조작 패널」을 카드 두 장처럼 겹쳐 두고, 앞 카드를 좌우로 밀면 카드 섞듯 바꾼다(11-06 운영자).
// 앞 카드 = 손가락을 따라 옆으로 끌리고(--dx), 충분히 밀면 그 방향으로 빠져나갔다가(.is-out) 뒤로 들어가고, 뒤 카드(.is-back)는 앞으로 올라온다. 모양 = css/bgpanel.css.
// 어느 카드가 앞인지는 bgdomegl.js 가 정하고(.is-back 붙이기), 여기는 밀기 감지와 빠져나가는 움직임만.

/** el 을 좌우로 밀 수 있게 한다. canSwipe() 가 참일 때만, 충분히 밀면 onSwipe(방향 −1 | 1). 민 뒤 따라오는 click 은 삼킨다(버튼 · 칸이 눌리지 않게) */
export function attachSwipe(el, { canSwipe, onSwipe, onDragStart }) {
  let id = null, x0 = 0, y0 = 0, dx = 0, swiping = false;
  el.addEventListener("pointerdown", (e) => {
    if (!canSwipe()) return;
    id = e.pointerId; x0 = e.clientX; y0 = e.clientY; dx = 0; swiping = false;
  });
  el.addEventListener("pointermove", (e) => {
    if (e.pointerId !== id) return;
    const mx = e.clientX - x0, my = e.clientY - y0;
    if (!swiping && Math.abs(mx) > 12 && Math.abs(mx) > Math.abs(my) * 1.3) { swiping = true; el.classList.add("is-dragging"); if (onDragStart) onDragStart(); }
    if (swiping) { dx = mx; el.style.setProperty("--dx", dx.toFixed(1) + "px"); }
  });
  const end = (e) => {
    if (e.pointerId !== id) return;
    id = null;
    if (!swiping) return;
    swiping = false;
    el.classList.remove("is-dragging");
    const eat = (ev) => { ev.stopPropagation(); ev.preventDefault(); };
    el.addEventListener("click", eat, { capture: true, once: true });
    setTimeout(() => el.removeEventListener("click", eat, true), 400);
    if (Math.abs(dx) > Math.min(90, el.offsetWidth * 0.22)) onSwipe(Math.sign(dx));
    else el.style.setProperty("--dx", "0px");   // 덜 밀었으면 제자리로
  };
  el.addEventListener("pointerup", end);
  el.addEventListener("pointercancel", end);
}

/** 앞 카드 el 을 dir 쪽으로 빼냈다가(0.2초) 뒤로 보낸다 — 뒤로 가는 .is-back 은 부르는 쪽이 붙인다 */
export function flyOut(el, dir) {
  el.style.setProperty("--dir", String(dir));
  el.classList.add("is-out");
  setTimeout(() => { el.classList.remove("is-out"); el.style.setProperty("--dx", "0px"); }, 200);
}
