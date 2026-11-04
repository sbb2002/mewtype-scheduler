# Luminary review 2

Applied over the existing uncommitted implementation. Tracked modifications remain limited to bgdomegl.js and bgastro.js; both use UTF-8/LF. No commit. This revision changes bgdomegl.js and preserves the first revision in bgastro.js.

- Disc radii unchanged. Solar Gaussian sigmas: 1.4/3.6/7 degrees at altitude, 1.9/4.8/8.5 near the horizon. Bright white core and inner bloom, warm outer bloom. Low-altitude exposure compensation retains extinction hue without losing visibility. Rays, veil and ghosts retained.
- Lunar exposure preserves extinction hue with a small warm fill. Soft halo sigma 0.35 to 0.85 degrees, intensity depends on phase. At 1 degree, a thin crescent remains small because the actual disc and phase mask are preserved.
- Compass glyph and luminaries are projected onto the camera plane. The entire glyph, glow and shadow fade with CSS screen distance: sun 55 to 140 px; moon 45 to 100 px. Fully transparent at close range.

## Artifacts and validation

42 PNG captures, 390x760 CSS at DPR 1.5 (plus supplemental conditions), and a micro-motion GIF. Includes sun 60/20/5/1/0 degrees at center/edge/outside5; moon 60/20/5/1 degrees in full/half/crescent phases; isolated stages, clouds and occlusion. Reproduce with review.py and supplemental.py. baseline.js is the uncommitted first revision before this task.

Indoor comparison, identical uniforms/textures/frame: 0 different pixels and 0 maximum channel delta. Conditions: dark portrait DPR 1.5 and 1, light portrait DPR 1, light landscape DPR 1.5. See comparison.json and supplemental.json.

Cost: GPU timer median 46.752 -> 44.217 ms/draw (-5.42%), 585x1140 buffer, sun at 60 degrees centered, 8 alternating rounds of 10 draws. No disjoint samples. ANGLE SwiftShader SOFTWARE renderer; this is not evidence of a speedup or actual phone GPU performance.

JS syntax checks, all 19 astronomy selfchecks, and git diff --check passed. Browser/shader errors: none (errors.json). Lens effects remain fully occluded for opaque cloud, below-horizon and rear-facing test cases (0 different channels).
