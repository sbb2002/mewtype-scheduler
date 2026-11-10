// bglive.selfcheck.mjs — node src/frontend/js/bglive.selfcheck.mjs
// (bg-dome, 11-10) 돔 바닥 라이브 조명 — 라이브 판정 · 짝 순서 · 맥동값
import { liveLightKeys, pulse, LIVE_PERIOD_MS, forceLive, lastLive } from "./bglive.js";

let fail = 0;
const ok = (c, m) => { if (!c) { fail++; console.error("FAIL", m); } };
const ORDER = ["arale", "yuno", "nonoka", "ritsu", "miyako"];
const pv = (items, order = ORDER) => ({ channel_order: order, items });
const liveKeys = (r) => r.filter((s) => s.live).map((s) => s.key);

// 라이브 없음 → 5칸 전부 꺼짐, key 는 순서대로
{
  const r = liveLightKeys(pv([]));
  ok(r.length === 5, "길이 5");
  ok(liveKeys(r).length === 0, "라이브 없음 → 전부 꺼짐");
  ok(r.map((s) => s.key).join() === ORDER.join(), "조명 0~4 = channel_order 순서");
}

// 한 명 라이브 → 그 칸만 켜짐 (요네 = yuno 는 1번째 칸 = 조명 1)
{
  const r = liveLightKeys(pv([{ channel_key: "yuno", state: "live" }]));
  ok(liveKeys(r).join() === "yuno", "한 명 라이브 → yuno 만");
  ok(r[1].live === true && r[1].key === "yuno", "yuno = 조명 1번");
}

// 그룹(여러 멤버) 영상: 주 레인 + collab_with 전부 라이브
{
  const r = liveLightKeys(pv([{ channel_key: "ritsu", collab_with: ["miyako", "nonoka"], state: "live" }]));
  ok(liveKeys(r).sort().join() === "miyako,nonoka,ritsu", "그룹 → 참여 멤버 각각 라이브");
}

// assumed_live(지각 추정)는 라이브가 아니다
{
  const r = liveLightKeys(pv([{ channel_key: "nonoka", state: "upcoming", assumed_live: true }]));
  ok(liveKeys(r).length === 0, "assumed_live 제외");
  const r2 = liveLightKeys(pv([{ channel_key: "nonoka", state: "live", assumed_live: true }]));
  ok(liveKeys(r2).length === 0, "state live 여도 assumed_live 면 제외");
}

// 끝난 방송(end) · 예고(watching · upcoming · announced) 제외
{
  const r = liveLightKeys(pv([
    { channel_key: "yuno", state: "end" },
    { channel_key: "arale", state: "watching" },
    { channel_key: "miyako", state: "upcoming" },
    { channel_key: "ritsu", state: "announced" },
  ]));
  ok(liveKeys(r).length === 0, "end · 예고 상태 제외");
}

// channel_order 없음 → 대체 순서(config.js FALLBACK_CHANNEL_ORDER)
{
  const r = liveLightKeys({ items: [{ channel_key: "miyako", state: "live" }] });
  ok(r.map((s) => s.key).join() === ORDER.join(), "channel_order 없음 → 대체 순서");
  ok(r[4].live === true, "대체 순서에서 miyako = 조명 4번");
  const r2 = liveLightKeys({ channel_order: [], items: [] });
  ok(r2[0].key === "arale", "빈 channel_order → 대체 순서");
}

// 5명 미만 → 빈 칸은 key null, live false
{
  const r = liveLightKeys({ channel_order: ["yuno", "nonoka"], items: [{ channel_key: "nonoka", state: "live" }] });
  ok(r.length === 5, "5명 미만이어도 길이 5");
  ok(r[0].key === "yuno" && r[1].key === "nonoka" && r[1].live, "앞 두 칸 = yuno · nonoka(라이브)");
  ok(r[2].key === null && r[2].live === false && r[4].key === null, "빈 칸 key null · 꺼짐");
}

// 입력이 빈 값이어도 죽지 않는다
{
  ok(liveLightKeys(null).length === 5, "null preview 안전");
  ok(liveLightKeys({ items: null }).length === 5, "items null 안전");
}

// 맥동: 평소(0) ↔ 멤버 색(1), 주기 LIVE_PERIOD_MS, reduce 면 1
{
  ok(Math.abs(pulse(0, false)) < 1e-9, "t=0 → 0(평소 색)");
  ok(Math.abs(pulse(LIVE_PERIOD_MS / 2, false) - 1) < 1e-9, "반주기 → 1(멤버 색)");
  ok(Math.abs(pulse(LIVE_PERIOD_MS, false)) < 1e-9, "한 주기 뒤 → 0");
  let inRange = true;
  for (let t = 0; t < 10000; t += 37) { const v = pulse(t, false); if (v < -1e-9 || v > 1 + 1e-9) inRange = false; }
  ok(inRange, "맥동값은 0 ~ 1");
  ok(pulse(123, true) === 1 && pulse(0, true) === 1, "reduce → 항상 1(켜 둠)");
  ok(LIVE_PERIOD_MS >= 2500 && LIVE_PERIOD_MS <= 3000, "주기 2.5 ~ 3초");
}

// 강제 값(확인용): forceLive 는 같은 모양을 주고, null 이면 실제(없으면 null)로 돌아간다
{
  ok(lastLive() === null, "발행 전 lastLive = null");
  forceLive(["yuno"]);
  const f = lastLive();
  ok(f.length === 5 && f[1].live === true && f[0].live === false, "forceLive(['yuno']) → 조명 1만 켜짐");
  forceLive(null);
  ok(lastLive() === null, "forceLive(null) → 실제 값(발행 전 null)");
}

if (fail) { console.error(`bglive selfcheck: ${fail} 실패`); process.exit(1); }
console.log("bglive selfcheck: 전부 통과");
