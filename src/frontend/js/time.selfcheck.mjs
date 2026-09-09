/**
 * Self-check for time.js v3 — run with: node src/frontend/js/time.selfcheck.mjs
 */
import assert from 'node:assert';
import { formatKST, relativeLabel, elapsedLabel, isLate } from './time.js';

// 기준 시각: 2026-09-09T06:00:00Z (KST: 2026-09-09 15:00:00)
const baseNowMs = new Date('2026-09-09T06:00:00Z').getTime();

console.log('Testing formatKST...');
{
  // 기본: MM/DD HH:mm
  const result = formatKST('2026-09-09T06:00:00Z');
  assert(result === '09/09 15:00', `Expected '09/09 15:00', got '${result}'`);

  // full 옵션: YYYY-MM-DD HH:mm
  const fullResult = formatKST('2026-09-09T06:00:00Z', { full: true });
  assert(fullResult === '2026-09-09 15:00', `Expected '2026-09-09 15:00', got '${fullResult}'`);

  console.log('✓ formatKST passed');
}

console.log('Testing relativeLabel - 지각(< -5분)...');
{
  // 10분 지난 시점: 2026-09-09T05:50:00Z
  const result = relativeLabel('2026-09-09T05:50:00Z', baseNowMs);
  assert(result === '10분 지각', `Expected '10분 지각', got '${result}'`);

  console.log('✓ 지각 case passed');
}

console.log('Testing relativeLabel - < 60초...');
{
  // 30초 남은 시점: 2026-09-09T06:00:30Z
  const result = relativeLabel('2026-09-09T06:00:30Z', baseNowMs);
  assert(result === '곧 시작', `Expected '곧 시작', got '${result}'`);

  console.log('✓ < 60초 case passed');
}

console.log('Testing relativeLabel - 오늘(같은 KST 날짜)...');
{
  // 2시간 30분 후: 2026-09-09T08:30:00Z (KST: 2026-09-09 17:30)
  const result = relativeLabel('2026-09-09T08:30:00Z', baseNowMs);
  assert(result === '2시간 30분 후', `Expected '2시간 30분 후', got '${result}'`);

  // 5분만 남은 경우 (같은 날, h=0)
  const result2 = relativeLabel('2026-09-09T06:05:00Z', baseNowMs);
  assert(result2 === '5분 후', `Expected '5분 후', got '${result2}'`);

  // 1시간만 남은 경우 (같은 날, m=0)
  const result3 = relativeLabel('2026-09-09T07:00:00Z', baseNowMs);
  assert(result3 === '1시간 후', `Expected '1시간 후', got '${result3}'`);

  console.log('✓ 오늘 case passed');
}

console.log('Testing relativeLabel - 7일 이내(오늘 아님)...');
{
  // 2일 후: 2026-09-11T15:00:00Z (KST 기준)
  // UTC 로는 2026-09-11T06:00:00Z
  const result = relativeLabel('2026-09-11T06:00:00Z', baseNowMs);
  // 2026-09-11 06:00 UTC - 2026-09-09 06:00 UTC = 2일
  // D-n 에서 n = ceil(2일) = 2, 시각은 KST 15:00
  assert(result === 'D-2 15:00', `Expected 'D-2 15:00', got '${result}'`);

  console.log('✓ 7일 이내 case passed');
}

console.log('Testing relativeLabel - 그 외(7일 이상)...');
{
  // 30일 후: 2026-10-09T06:00:00Z
  const result = relativeLabel('2026-10-09T06:00:00Z', baseNowMs);
  assert(result === '2026-10-09 15:00', `Expected '2026-10-09 15:00', got '${result}'`);

  console.log('✓ 7일 이상 case passed');
}

console.log('Testing elapsedLabel...');
{
  // actual_start 2026-09-09T05:45:00Z, now = baseNowMs (2026-09-09T06:00:00Z)
  // 경과: 15분
  const result = elapsedLabel('2026-09-09T05:45:00Z', baseNowMs);
  assert(result === '방송 중 (15분)', `Expected '방송 중 (15분)', got '${result}'`);

  console.log('✓ elapsedLabel passed');
}

console.log('Testing isLate...');
{
  // 10분 지남 → true
  const isLate1 = isLate('2026-09-09T05:50:00Z', baseNowMs);
  assert(isLate1 === true, `Expected true, got ${isLate1}`);

  // 2분 지남 (5분 이내) → false
  const isLate2 = isLate('2026-09-09T05:58:00Z', baseNowMs);
  assert(isLate2 === false, `Expected false, got ${isLate2}`);

  console.log('✓ isLate passed');
}

console.log('\n✅ All tests passed!');
