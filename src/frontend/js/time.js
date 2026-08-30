/**
 * Format ISO UTC timestamp as KST (Asia/Seoul) in MM/DD HH:mm format
 * @param {string} iso - ISO UTC string (e.g., "2026-08-30T12:00:00Z")
 * @returns {string} Formatted time as "MM/DD HH:mm" in KST
 */
export function formatKST(iso) {
  const date = new Date(iso);
  const formatter = new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  });

  const parts = formatter.formatToParts(date);
  const obj = {};
  for (const part of parts) {
    if (part.type !== "literal") {
      obj[part.type] = part.value;
    }
  }

  return `${obj.month}/${obj.day} ${obj.hour}:${obj.minute}`;
}

const DAY_MS = 86400000;

/**
 * Generate relative time label for a scheduled start time.
 * 24시간 이내면 "H시간 M분 남음"(분 단위), 그 밖은 "{n}일 후" / 날짜.
 * 예정 시각이 이미 지났는데 아직 upcoming 상태(=라이브 전환이 확인 안 됨)면
 * "{n}분/시간 지각"으로 표시 — 수집기가 다음 주기에 live 여부를 다시 확인할 때까지의 잠정 표시.
 * 남은 시간은 nowMs 를 넘겨주는 쪽(1분마다 갱신)이 계산 기준을 정한다.
 * @param {string} iso - ISO UTC string for scheduled_start
 * @param {number} nowMs - Current time in milliseconds (default: Date.now())
 * @returns {string}
 */
export function relativeLabel(iso, nowMs = Date.now()) {
  const deltaMs = new Date(iso).getTime() - nowMs;

  if (deltaMs < 0) return lateLabel(-deltaMs);  // 예정 시각을 이미 지남
  if (deltaMs < 60000) return "곧 시작";         // 1분 미만 남음

  const totalMin = Math.floor(deltaMs / 60000);
  const h = Math.floor(totalMin / 60);
  const m = totalMin % 60;

  // < 24시간 → 시·분 카운트다운
  if (deltaMs < DAY_MS) {
    if (h === 0) return `${m}분 남음`;
    if (m === 0) return `${h}시간 남음`;
    return `${h}시간 ${m}분 남음`;
  }

  // < 7일 → "{n}일 후" (올림, 최소 1)
  if (deltaMs < 7 * DAY_MS) {
    return `${Math.max(1, Math.ceil(deltaMs / DAY_MS))}일 후`;
  }

  // >= 7일 → 날짜
  return formatKST(iso);
}

/**
 * 예정 시각을 지난 정도를 "{n}분 지각" / "{h}시간 {m}분 지각"으로 표시.
 * @param {number} overMs - 지난 시간(ms), 항상 양수
 */
function lateLabel(overMs) {
  const totalMin = Math.max(1, Math.floor(overMs / 60000));
  const h = Math.floor(totalMin / 60);
  const m = totalMin % 60;
  if (h === 0) return `${m}분 지각`;
  if (m === 0) return `${h}시간 지각`;
  return `${h}시간 ${m}분 지각`;
}

/**
 * scheduled_start가 이미 지났는지 여부 (지각 표시 스타일 토글용).
 * @param {string} iso
 * @param {number} nowMs
 */
export function isLate(iso, nowMs = Date.now()) {
  return new Date(iso).getTime() - nowMs < 0;
}
