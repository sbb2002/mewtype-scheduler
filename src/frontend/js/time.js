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
 * 남은 시간은 nowMs 를 넘겨주는 쪽(1분마다 갱신)이 계산 기준을 정한다.
 * @param {string} iso - ISO UTC string for scheduled_start
 * @param {number} nowMs - Current time in milliseconds (default: Date.now())
 * @returns {string}
 */
export function relativeLabel(iso, nowMs = Date.now()) {
  const deltaMs = new Date(iso).getTime() - nowMs;

  if (deltaMs < 60000) return "곧 시작";        // 지났거나 1분 미만

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
