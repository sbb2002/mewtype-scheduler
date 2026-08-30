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

/**
 * Generate relative time label for a scheduled start time
 * @param {string} iso - ISO UTC string for scheduled_start
 * @param {number} nowMs - Current time in milliseconds (default: Date.now())
 * @returns {string} Relative time label
 */
export function relativeLabel(iso, nowMs = Date.now()) {
  const scheduledMs = new Date(iso).getTime();
  const deltaMs = scheduledMs - nowMs;

  // <= 0 or < 60 seconds: "곧 시작"
  if (deltaMs <= 0 || deltaMs < 60000) {
    return "곧 시작";
  }

  const deltaSec = Math.floor(deltaMs / 1000);
  const deltaMin = Math.floor(deltaSec / 60);
  const deltaHr = Math.floor(deltaMin / 60);

  // < 60 minutes: "{n}분 후"
  if (deltaMin < 60) {
    return `${deltaMin}분 후`;
  }

  // < 24 hours: "{n}시간 후" (floor)
  if (deltaHr < 24) {
    return `${deltaHr}시간 후`;
  }

  // < 7 days: "{n}일 후" (ceil, min 1)
  if (deltaHr < 7 * 24) {
    const dayCount = Math.ceil(deltaHr / 24);
    return `${Math.max(1, dayCount)}일 후`;
  }

  // >= 7 days: formatKST
  return formatKST(iso);
}
