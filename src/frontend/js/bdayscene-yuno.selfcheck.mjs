import assert from 'node:assert/strict';
import { readFile, readdir } from 'node:fs/promises';
import { BPM, yunoPose, spectrum } from './bdaybeat.js';

// Approved v16 samples captured before extracting/replacing its renderer.
const reference = JSON.parse(await readFile(new URL('../../../fixtures/bdayscene-yuno-v16-reference.json', import.meta.url), 'utf8'));
for (const sample of reference) {
  assert.deepEqual(JSON.parse(JSON.stringify(yunoPose(sample.t))), sample.pose, `v16 pose at ${sample.t}`);
  assert.deepEqual(Array.from({ length: 40 }, (_, i) => spectrum(sample.t, i, 40)), sample.spectrum, `v16 spectrum at ${sample.t}`);
}
assert.equal(BPM, 100);
assert.equal(yunoPose(.093).swingRatio, .62);
assert.ok(Math.abs(yunoPose(.093).left-5.5) < 1e-10);
assert.ok(Math.abs(yunoPose(.279).left+5.5) < 1e-10);
assert.ok(Math.abs(yunoPose(.108+.6).headY/yunoPose(.108).headY-2) < 1e-10);
let maxError = 0;
for (let n = 0; n < 3840; n++) {
  const t = n*.01, q = yunoPose(t);
  assert.ok(Object.values(q).every(v => typeof v !== 'number' || Number.isFinite(v)));
  for (const i of [0, 12, 24, 39]) {
    const v = spectrum(t, i, 40);
    assert.ok(v.height >= 18 && v.height <= 111 && v.cap >= v.height);
  }
  maxError = Math.max(maxError, Math.abs(q.leftRecord-q.leftCoast-26*q.left/5.5));
}
assert.ok(maxError < 1e-9);
const files = await readdir(new URL('../assets/birthday/yuno/', import.meta.url));
assert.equal(files.length, 9);
assert.ok(files.every(f => /^[a-z_]+\.webp$/.test(f)));
const css = await readFile(new URL('../css/bdayscene-yuno.css', import.meta.url), 'utf8');
assert.ok(!css.includes('.stage') && !css.includes('.rig-ritsu') && css.includes('prefers-reduced-motion'));
const module = await readFile(new URL('./bdayscene-yuno.js', import.meta.url), 'utf8');
assert.ok(!module.includes('innerHTML') && !module.includes('data:image') && module.includes('mountYunoScene'));
console.log(`Yuno legacy beat self-check passed: ${reference.length} exact v16 pose/spectrum comparisons, 3,840 safety samples, 9 assets. Canvas 검증은 bdaymusic.selfcheck.mjs 및 브라우저에서 별도 수행.`);
