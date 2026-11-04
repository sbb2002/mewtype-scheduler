/**
 * (v4.11.7) 네트워크 실패 복구 상태 기계 — 순수 로직(DOM · window 접근 없음).
 *
 * 정기 조회가 실패하면 3초 · 8초 간격으로 두 번 더 재시도하고, 그래도 안 되면 안내를 띄운다.
 * 안내가 떠 있는 동안 브라우저가 온라인으로 바뀌면 5초 뒤 한 번 더 재조회한다.
 * 화면이 숨겨져 있으면 안내를 띄우지 않고 조용히 멈춘다(복귀 때 재조회가 돈다).
 *
 * 상태: idle(평소) · retrying(재시도 대기 중) · alert(안내 표시 중). 타이머는 하나만 둔다.
 */

export const RETRY_DELAYS_MS = [3000, 8000];   // 실패 뒤 재시도 간격 — 두 번까지
export const ONLINE_DELAY_MS = 5000;            // 온라인 복귀 뒤 재조회까지 대기

/**
 * @param {object} deps
 * @param {() => void} deps.retry - 재조회 (main.js 의 refetchAll)
 * @param {(kind: "network"|"server") => void} deps.show - 안내 표시 · 문구 갱신
 * @param {() => void} deps.hide - 안내 숨김
 * @param {(fn: () => void, ms: number) => any} deps.setTimer
 * @param {(id: any) => void} deps.clearTimer
 * @param {() => boolean} deps.isVisible - 화면이 보이는 중인지
 */
export function createNetRecovery({ retry, show, hide, setTimer, clearTimer, isVisible }) {
  let state = "idle";
  let attempt = 0;
  let timer = null;

  const cancel = () => {
    if (timer !== null) { clearTimer(timer); timer = null; }
  };
  const toIdle = () => {
    cancel();
    state = "idle";
    attempt = 0;
  };

  function onSuccess() {
    cancel();
    if (state === "alert") hide();
    state = "idle";
    attempt = 0;
  }

  function onFailure(kind) {
    // 숨김 상태에서 실패: 안내 없이 멈춘다. 복귀 때 재조회가 돈다.
    if (!isVisible() && state !== "alert") {
      toIdle();
      return;
    }
    // 이미 안내가 떠 있으면 문구만 갱신한다. 재시도는 예약하지 않는다.
    if (state === "alert") {
      show(kind);
      return;
    }
    // 재시도 대기 중이면 정기 조회가 겹친 것 — 아무것도 안 한다.
    if (timer !== null) return;

    if (attempt < RETRY_DELAYS_MS.length) {
      state = "retrying";
      timer = setTimer(() => {
        timer = null;
        attempt += 1;
        if (!isVisible()) { toIdle(); return; }
        retry();
      }, RETRY_DELAYS_MS[attempt]);
      return;
    }
    // 재시도가 다 떨어졌다 — 안내를 띄운다.
    cancel();
    state = "alert";
    show(kind);
  }

  function onOnline() {
    if (state === "idle") return;
    cancel();
    timer = setTimer(() => {
      timer = null;
      retry();
    }, ONLINE_DELAY_MS);
  }

  return { onSuccess, onFailure, onOnline };
}
