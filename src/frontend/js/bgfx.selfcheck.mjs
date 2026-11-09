// bgfx.selfcheck.mjs — node src/frontend/js/bgfx.selfcheck.mjs (상대론 계산만 — 캔버스는 브라우저에서)
import assert from "node:assert/strict";
// bgfx.js 는 document 를 건드리는 createFx 가 있어 순수 함수만 떼어 검사한다
globalThis.window = {}; globalThis.document = { createElement: () => ({}), body: { appendChild() {} } };
const { relativistic, dopplerTint } = await import("./bgfx.js");
const a = relativistic(0.9, 1), b = relativistic(0.9, -1), z = relativistic(0, 1);
assert.ok(a.D > 1 && b.D < 1, "다가오면 푸른쪽 · 멀어지면 붉은쪽");
assert.ok(Math.abs(z.D - 1) < 1e-9 && z.contract === 1, "정지 = 효과 없음");
assert.ok(Math.abs(a.contract - Math.sqrt(1 - 0.81)) < 1e-9, "길이 수축 1/γ");
assert.ok(dopplerTint(2).rgb[2] > dopplerTint(2).rgb[0] && dopplerTint(0.5).rgb[0] > dopplerTint(0.5).rgb[2]);
assert.equal(dopplerTint(1).a, 0);
console.log("bgfx self-check ok");
