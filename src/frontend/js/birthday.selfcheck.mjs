/**
 * Self-check for birthday.js — run with: node src/frontend/js/birthday.selfcheck.mjs
 */
import assert from 'node:assert';
import { kstMonthDay, birthdayMemberAt, overrideMember, pickBirthdayScene, msToNextKstMidnight } from './birthday.js';
import { BIRTHDAYS, BIRTHDAY_SCENES_ENABLED } from './config.js';

const t = (iso) => new Date(iso).getTime();

console.log('Testing kstMonthDay (UTC+9 경계)...');
assert.strictEqual(kstMonthDay(t('2026-11-03T14:59:59Z')), '11-03');   // KST 11/03 23:59:59
assert.strictEqual(kstMonthDay(t('2026-11-03T15:00:00Z')), '11-04');   // KST 11/04 00:00:00
assert.strictEqual(kstMonthDay(t('2026-11-04T14:59:59Z')), '11-04');   // KST 11/04 23:59:59
assert.strictEqual(kstMonthDay(t('2026-11-04T15:00:00Z')), '11-05');   // KST 11/05 00:00:00
assert.strictEqual(kstMonthDay(t('2026-12-31T15:00:00Z')), '01-01');   // 연말 넘김
assert.strictEqual(kstMonthDay(t('2028-02-28T15:00:00Z')), '02-29');   // 윤년
console.log('✓ kstMonthDay passed');

console.log('Testing birthdayMemberAt...');
assert.strictEqual(birthdayMemberAt(t('2026-11-03T15:00:00Z'), BIRTHDAYS), 'yuno');
assert.strictEqual(birthdayMemberAt(t('2026-11-04T14:59:59Z'), BIRTHDAYS), 'yuno');
assert.strictEqual(birthdayMemberAt(t('2026-11-04T15:00:00Z'), BIRTHDAYS), null);
assert.strictEqual(birthdayMemberAt(t('2026-11-03T14:59:59Z'), BIRTHDAYS), null);
assert.strictEqual(birthdayMemberAt(t('2027-02-06T15:00:00Z'), BIRTHDAYS), 'ritsu');
assert.strictEqual(birthdayMemberAt(t('2027-04-16T15:00:00Z'), BIRTHDAYS), 'nonoka');
assert.strictEqual(birthdayMemberAt(t('2026-08-15T15:00:00Z'), BIRTHDAYS), 'arale');
assert.strictEqual(birthdayMemberAt(t('2026-09-18T15:00:00Z'), BIRTHDAYS), 'miyako');
assert.strictEqual(birthdayMemberAt(t('2026-10-31T00:00:00Z'), BIRTHDAYS), null);
assert.strictEqual(birthdayMemberAt(t('2026-11-04T03:00:00Z'), null), null);
console.log('✓ birthdayMemberAt passed');

console.log('Testing overrideMember / pickBirthdayScene...');
const en = { yuno: true, ritsu: false };
assert.strictEqual(overrideMember('?bday=yuno', en), 'yuno');
assert.strictEqual(overrideMember('?va=claude&bday=yuno', en), 'yuno');
assert.strictEqual(overrideMember('?bday=ritsu', en), null);       // 장면이 꺼진 멤버는 강제 표시도 안 됨
assert.strictEqual(overrideMember('?bday=unknown', en), null);
assert.strictEqual(overrideMember('?xbday=yuno', en), null);
assert.strictEqual(overrideMember('', en), null);
// 오늘이 평일이어도 ?bday 로 강제 표시
assert.strictEqual(pickBirthdayScene(t('2026-10-31T00:00:00Z'), '?bday=yuno', BIRTHDAYS, en), 'yuno');
// 생일인데 장면이 꺼진 멤버(리츠 02-07)는 아무것도 안 바꾼다
assert.strictEqual(pickBirthdayScene(t('2027-02-06T15:00:00Z'), '', BIRTHDAYS, en), null);
// 실제 설정: 켜진 멤버는 유노만
assert.deepStrictEqual(Object.keys(BIRTHDAY_SCENES_ENABLED).filter((k) => BIRTHDAY_SCENES_ENABLED[k]), ['yuno']);
assert.strictEqual(pickBirthdayScene(t('2026-11-03T15:00:00Z'), '', BIRTHDAYS, BIRTHDAY_SCENES_ENABLED), 'yuno');
console.log('✓ override / pick passed');

console.log('Testing msToNextKstMidnight...');
assert.strictEqual(msToNextKstMidnight(t('2026-11-03T14:59:59Z')), 1000);
assert.strictEqual(msToNextKstMidnight(t('2026-11-03T15:00:00Z')), 24 * 3600 * 1000);
assert.strictEqual(msToNextKstMidnight(t('2026-11-04T03:00:00Z')), 12 * 3600 * 1000);
console.log('✓ msToNextKstMidnight passed');

console.log('\nAll birthday self-checks passed.');
