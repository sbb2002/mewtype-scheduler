// birthday.js — (v4.10.0) 생일 스킨 판정. 순수 로직(DOM 없음) — 어느 멤버의 생일 장면을 지금 보여 줄지 정한다.
// 생일 = KST 달력 날짜(MM-DD)가 생일과 같은 날 00:00 ~ 익일 00:00. KST 는 UTC+9(서머타임 없음)라 UTC 시각에 9시간을 더해 달력 날짜를 읽는다.

const KST_OFFSET_MS = 9 * 3600 * 1000;

/** nowMs → KST 달력 월일 "MM-DD" */
export function kstMonthDay(nowMs) {
  const d = new Date(nowMs + KST_OFFSET_MS);
  const m = String(d.getUTCMonth() + 1).padStart(2, "0");
  const day = String(d.getUTCDate()).padStart(2, "0");
  return `${m}-${day}`;
}

/** 지금(KST) 생일인 멤버 키. 없으면 null. 같은 날이 겹치면 birthdays 정의 순서 첫 멤버(5명은 모두 날짜가 달라 겹치지 않는다) */
export function birthdayMemberAt(nowMs, birthdays) {
  const md = kstMonthDay(nowMs);
  for (const key of Object.keys(birthdays || {})) {
    if (birthdays[key] === md) return key;
  }
  return null;
}

/** 시험용 강제 표시: 주소의 ?bday=<멤버키>. 장면이 켜진 멤버 키일 때만 인정(아니면 null) */
export function overrideMember(search, enabled) {
  const m = /(?:^|[?&])bday=([a-z]+)(?:&|$)/.exec(search || "");
  if (!m) return null;
  return enabled && enabled[m[1]] ? m[1] : null;
}

/** 지금 보여 줄 생일 장면의 멤버 키 — 강제 표시 → 오늘 생일(장면이 켜진 멤버만) → null */
export function pickBirthdayScene(nowMs, search, birthdays, enabled) {
  const forced = overrideMember(search, enabled);
  if (forced) return forced;
  const key = birthdayMemberAt(nowMs, birthdays);
  return key && enabled && enabled[key] ? key : null;
}

/** 다음 KST 자정까지 남은 ms (자정 넘김 때 다시 판정하려고 타이머를 맞추는 데 쓴다) */
export function msToNextKstMidnight(nowMs) {
  const shifted = nowMs + KST_OFFSET_MS;
  const dayMs = 24 * 3600 * 1000;
  return dayMs - (shifted % dayMs);
}
