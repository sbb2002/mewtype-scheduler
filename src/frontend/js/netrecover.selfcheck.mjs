// (v4.11.7) netrecover.js 순수 로직 self-check — 가짜 타이머로 상태 전이를 검사한다.
import { createNetRecovery, RETRY_DELAYS_MS, ONLINE_DELAY_MS } from "./netrecover.js";

let failures = 0;
function check(name, cond) {
  if (cond) console.log("ok   " + name);
  else { failures += 1; console.log("FAIL " + name); }
}

/** 가짜 타이머 환경 — now 를 앞으로 돌리며 만기된 타이머를 실행한다. */
function makeEnv() {
  const env = {
    now: 0, timers: [], retries: 0, shows: [], hides: 0, visible: true,
  };
  env.setTimer = (fn, ms) => {
    const t = { fn, at: env.now + ms, id: env.timers.length + 1, live: true };
    env.timers.push(t);
    return t;
  };
  env.clearTimer = (t) => { if (t) t.live = false; };
  env.live = () => env.timers.filter((t) => t.live);
  env.advance = (ms) => {
    const end = env.now + ms;
    for (;;) {
      const next = env.live().filter((t) => t.at <= end).sort((a, b) => a.at - b.at)[0];
      if (!next) break;
      env.now = next.at;
      next.live = false;
      next.fn();
    }
    env.now = end;
  };
  const rec = createNetRecovery({
    retry: () => { env.retries += 1; },
    show: (kind) => { env.shows.push(kind); },
    hide: () => { env.hides += 1; },
    setTimer: env.setTimer,
    clearTimer: env.clearTimer,
    isVisible: () => env.visible,
  });
  env.rec = rec;
  return env;
}

// (1) 1회 실패 뒤 재시도 성공 → show 0회
{
  const e = makeEnv();
  e.rec.onFailure("network");
  e.advance(RETRY_DELAYS_MS[0]);
  check("(1) 재시도 1회 발생", e.retries === 1);
  e.rec.onSuccess();
  e.advance(100000);
  check("(1) 재시도 성공 → show 0회", e.shows.length === 0);
  check("(1) 성공 뒤 타이머 없음", e.live().length === 0);
}

// (2) 3회 연속 실패 → show 1회, 2회째까지는 안 뜸 (3) 간격 3000 · 8000
{
  const e = makeEnv();
  e.rec.onFailure("server");           // 1차 실패
  e.advance(RETRY_DELAYS_MS[0] - 1);
  check("(2) 3초 전에는 재시도 없음", e.retries === 0);
  e.advance(1);
  check("(3) 첫 재시도는 3000ms 뒤", e.retries === 1);
  e.rec.onFailure("server");           // 2차 실패
  check("(2) 2차 실패 뒤 show 없음", e.shows.length === 0);
  e.advance(RETRY_DELAYS_MS[1] - 1);
  check("(3) 8000ms 전에는 두 번째 재시도 없음", e.retries === 1);
  e.advance(1);
  check("(3) 두 번째 재시도는 8000ms 뒤", e.retries === 2);
  e.rec.onFailure("server");           // 3차 실패
  check("(2) 3회째 실패 → show 1회", e.shows.length === 1 && e.shows[0] === "server");
  e.advance(100000);
  check("(2) 안내 뒤 추가 재시도 없음", e.retries === 2);
}

// (4) alert 뒤 성공 → hide 1회
{
  const e = makeEnv();
  e.rec.onFailure("network");
  e.advance(3000); e.rec.onFailure("network");
  e.advance(8000); e.rec.onFailure("network");
  check("(4) 안내 떠 있음", e.shows.length === 1);
  e.rec.onSuccess();
  check("(4) 성공 → hide 1회", e.hides === 1);
  e.rec.onSuccess();
  check("(4) 평소 성공은 hide 추가 없음", e.hides === 1);
}

// (5) 숨김 상태 실패 → show · 재시도 0회
{
  const e = makeEnv();
  e.visible = false;
  e.rec.onFailure("network");
  e.advance(100000);
  check("(5) 숨김 실패 → show 0회", e.shows.length === 0);
  check("(5) 숨김 실패 → 재시도 0회", e.retries === 0);
  check("(5) 숨김 실패 → 타이머 없음", e.live().length === 0);
}

// (6) 대기 중 실패 겹침 → 타이머 1개
{
  const e = makeEnv();
  e.rec.onFailure("network");
  e.rec.onFailure("network");
  e.rec.onFailure("network");
  check("(6) 대기 중 겹친 실패는 타이머 1개", e.live().length === 1);
}

// (7) alert 에서 onOnline → 5000 뒤 retry
{
  const e = makeEnv();
  e.rec.onFailure("server");
  e.advance(3000); e.rec.onFailure("server");
  e.advance(8000); e.rec.onFailure("server");
  const before = e.retries;
  e.rec.onOnline();
  e.advance(ONLINE_DELAY_MS - 1);
  check("(7) 온라인 복귀 5000ms 전에는 재조회 없음", e.retries === before);
  e.advance(1);
  check("(7) 온라인 복귀 5000ms 뒤 재조회", e.retries === before + 1);
}

// (8) idle 의 onOnline 무시
{
  const e = makeEnv();
  e.rec.onOnline();
  e.advance(100000);
  check("(8) idle 에서 onOnline 무시", e.retries === 0 && e.live().length === 0);
}

// (9) alert 중 kind 변경 시 show 재호출
{
  const e = makeEnv();
  e.rec.onFailure("network");
  e.advance(3000); e.rec.onFailure("network");
  e.advance(8000); e.rec.onFailure("network");
  e.rec.onFailure("server");
  check("(9) alert 중 kind 변경 → show 재호출", e.shows.length === 2 && e.shows[1] === "server");
  check("(9) alert 중 실패는 재시도 예약 없음", e.live().length === 0);
}

if (failures > 0) {
  console.log(`\n${failures} 건 실패`);
  process.exit(1);
}
console.log("\nnetrecover selfcheck: 전부 통과");
