/**
 * Format ISO UTC timestamp as KST (Asia/Seoul)
 * @param {string} iso - ISO UTC string (e.g., "2026-08-30T12:00:00Z")
 * @param {Object} opts - Options
 * @param {boolean} opts.full - If true, return "YYYY-MM-DD HH:mm"; else "MM/DD HH:mm" (default)
 * @returns {string} Formatted time in KST
 */
export function formatKST(iso, opts = {}) {
  const date = new Date(iso);
  const formatter = new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul",
    year: "numeric",
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

  if (opts.full) {
    return `${obj.year}-${obj.month}-${obj.day} ${obj.hour}:${obj.minute}`;
  }
  return `${obj.month}/${obj.day} ${obj.hour}:${obj.minute}`;
}

const DAY_MS = 86400000;

// (v4.11.16) 예정 시각 + 10분까지는 「준비중」(노란 글자, 느린 점멸) — 그 뒤부터 「n분 지각」. 전엔 5분 유예 + 「곧 시작」(옛 카드)
// · 유예 없음(오늘 보드)으로 둘이 달랐다. 오늘 보드(timetable.js)와 이후 예고 카드(render.js)가 이 값 하나를 쓴다.
export const PREP_MS = 10 * 60000;
const LATE_GRACE_MS = PREP_MS;

/**
 * (v4.11.16) 예정 시각 기준 지각 국면. "before" = 아직 전 · "prep" = 지났지만 10분 이내(준비중) · "late" = 10분 넘김(지각).
 * @param {number} startMs
 * @param {number} nowMs
 * @returns {{phase: "before"|"prep"|"late", lateMin: number}} lateMin = 지난 분(내림, late 때만 의미)
 */
export function latePhase(startMs, nowMs = Date.now()) {
  const over = nowMs - startMs;
  if (!(over > 0)) return { phase: "before", lateMin: 0 };
  return { phase: over > PREP_MS ? "late" : "prep", lateMin: Math.floor(over / 60000) };
}

/**
 * Generate relative time label for a scheduled start time (v3).
 * 지각(> +10분) → "{n}분 지각" / 0~10분 지남 → "준비중" / < 60초 → "곧 시작" / 오늘(같은 KST 날짜) → "{h}시간 {m}분 후" /
 * 7일 이내(오늘 아님) → "D-{n} {HH}:{mm}" / 그 외 → "{YYYY}-{MM}-{DD} {HH}:{mm}"
 * @param {string} iso - ISO UTC string for scheduled_start
 * @param {number} nowMs - Current time in milliseconds (default: Date.now())
 * @returns {string}
 */
export function relativeLabel(iso, nowMs = Date.now()) {
  const startTime = new Date(iso);
  const nowTime = new Date(nowMs);
  const deltaMs = startTime.getTime() - nowTime.getTime();

  // 지각(10분 넘김) → 「n분 지각」, (v4.11.16) 지났지만 10분 이내 → 「준비중」
  if (deltaMs < -LATE_GRACE_MS) return lateLabel(-deltaMs);
  if (deltaMs < 0) return "준비중";

  // < 60초 → "곧 시작"
  if (deltaMs < 60000) return "곧 시작";

  // KST 자정 계산하기 (오늘 vs 내일/그 이후 판정용)
  const kstFormatter = new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  });

  const nowParts = kstFormatter.formatToParts(nowTime);
  const startParts = kstFormatter.formatToParts(startTime);

  // 오늘 날짜 판정 (같은 KST 날짜면 오늘)
  const nowDateStr = `${nowParts.find(p => p.type === "year").value}-${nowParts.find(p => p.type === "month").value}-${nowParts.find(p => p.type === "day").value}`;
  const startDateStr = `${startParts.find(p => p.type === "year").value}-${startParts.find(p => p.type === "month").value}-${startParts.find(p => p.type === "day").value}`;

  const isToday = nowDateStr === startDateStr;
  const startHour = startParts.find(p => p.type === "hour").value;
  const startMinute = startParts.find(p => p.type === "minute").value;

  // 오늘(같은 KST 날짜) → "{h}시간 {m}분 후" (h·m 0 처리)
  if (isToday) {
    const totalMin = Math.floor(deltaMs / 60000);
    const h = Math.floor(totalMin / 60);
    const m = totalMin % 60;
    if (h === 0) return `${m}분 후`;
    if (m === 0) return `${h}시간 후`;
    return `${h}시간 ${m}분 후`;
  }

  // 7일 이내(오늘 아님) → "D-{n} {HH}:{mm}"
  // n = KST 자정 기준 캘린더 일수 차 (raw ms 가 아니라 날짜 경계로 계산 — 시각이 달라도 정확).
  const nowMidMs = Date.parse(`${nowDateStr}T00:00:00Z`);
  const startMidMs = Date.parse(`${startDateStr}T00:00:00Z`);
  const daysDiff = Math.max(1, Math.round((startMidMs - nowMidMs) / DAY_MS));
  if (daysDiff <= 7) {
    return `D-${daysDiff} ${startHour}:${startMinute}`;
  }

  // 그 외 → "{YYYY}-{MM}-{DD} {HH}:{mm}"
  const year = startParts.find(p => p.type === "year").value;
  const month = startParts.find(p => p.type === "month").value;
  const day = startParts.find(p => p.type === "day").value;
  return `${year}-${month}-${day} ${startHour}:${startMinute}`;
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
 * scheduled_start를 LATE_GRACE_MS(10분) 넘게 지났는지 여부 (지각 표시 스타일 토글용).
 * @param {string} iso
 * @param {number} nowMs
 */
export function isLate(iso, nowMs = Date.now()) {
  return new Date(iso).getTime() - nowMs < -LATE_GRACE_MS;
}

/**
 * 방송 경과 시간을 "방송 중 ({m}분)" 형식으로 반환 (v3).
 * @param {string} actualStartIso - ISO UTC string for actual_start
 * @param {number} nowMs - Current time in milliseconds (default: Date.now())
 * @returns {string} "방송 중 ({m}분)" format
 */
export function elapsedLabel(actualStartIso, nowMs = Date.now()) {
  const elapsedMs = nowMs - new Date(actualStartIso).getTime();
  const elapsedMin = Math.max(0, Math.floor(elapsedMs / 60000));
  return `방송 중 (${elapsedMin}분)`;
}
