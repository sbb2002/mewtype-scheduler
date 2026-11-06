// bgdeck.js — (bg-dome 3단계) 성간 이동 중 「워프 기어 패널」과 「UFO 조작 패널」을 카드 두 장처럼 겹쳐 두고, 앞 카드를 좌우로 밀면 카드 섞듯 바꾼다(11-06 운영자).
// 앞 카드 = 손가락을 따라 옆으로 끌리고(--dx), 충분히 밀면 섞기(shuffleCards). 모양 = css/bgpanel.css.
// 어느 카드가 앞인지는 bgdomegl.js 가 정하고(.is-back 붙이기), 여기는 밀기 감지와 섞는 움직임만.

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
    if (Math.abs(dx) > Math.min(90, el.offsetWidth * 0.22)) onSwipe(Math.sign(dx), dx);
    else el.style.setProperty("--dx", "0px");   // 덜 밀었으면 제자리로
  };
  el.addEventListener("pointerup", end);
  el.addEventListener("pointercancel", end);
}

/**
 * 카드 섞기(11-06 운영자): front = 지금 앞 카드(손가락으로 dx 만큼 끌린 채) · back = 뒤 카드, dir = 민 방향(−1 왼쪽 · 1 오른쪽).
 *   앞 카드 = dir 쪽으로 빠져나갔다가 → 뒤 자리로 들어가며 어두워짐(비활성)
 *   뒤 카드 = 반대쪽으로 빠져나왔다가 → 앞 자리로 오며 원래 밝기로
 * 둘이 동시에 0.56초. 겹침 순서는 가운데쯤(45~55%)에서 바뀐다. 끝 모습은 부르는 쪽이 붙인 클래스(.is-back · --back-y)와 같게 맞춰 끝나면 그대로 이어진다.
 * backYFront = 앞 카드가 뒤로 갔을 때의 세로 위치(px), backYBack = 뒤 카드가 있던 세로 위치(px).
 */
export function shuffleCards(front, back, dir, dx, backYFront, backYBack) {
  const DIM = { opacity: 0.62, filter: "brightness(0.6)" }, LIT = { opacity: 1, filter: "brightness(1)" };
  const opt = { duration: 560, easing: "cubic-bezier(.3, .7, .2, 1)" };
  front.style.setProperty("--dx", "0px");
  if (typeof front.animate !== "function" || matchMedia("(prefers-reduced-motion: reduce)").matches) return;   // 움직임 줄이기 = 바로 바뀜
  front.animate([
    { transform: `translateX(${dx}px) rotate(${dx * 0.025}deg)`, zIndex: 977, ...LIT },
    { offset: 0.45, transform: `translateX(${dir * 62}%) rotate(${dir * 7}deg) scale(.96)`, zIndex: 977, ...LIT },
    { offset: 0.55, transform: `translateX(${dir * 58}%) rotate(${dir * 6}deg) scale(.95)`, zIndex: 974, opacity: 0.85, filter: "brightness(0.8)" },
    { transform: `translateY(${backYFront}px) scale(.92)`, zIndex: 974, ...DIM },
  ], opt);
  back.animate([
    { transform: `translateY(${backYBack}px) scale(.92)`, zIndex: 974, ...DIM },
    { offset: 0.45, transform: `translateX(${-dir * 62}%) rotate(${-dir * 7}deg) scale(.95)`, zIndex: 974, opacity: 0.85, filter: "brightness(0.8)" },
    { offset: 0.55, transform: `translateX(${-dir * 58}%) rotate(${-dir * 6}deg) scale(.96)`, zIndex: 976, ...LIT },
    { transform: "none", zIndex: 976, ...LIT },
  ], opt);
}
