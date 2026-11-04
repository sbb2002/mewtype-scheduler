# 여명 하늘 · 구름 생성 프롬프트 원문

도구: built-in image_gen. CLI/API 우회 사용 없음.
구름은 2차까지 생성·비교했다. 최종은 결이 더 자연스러운 1차 원본을 사용하고, 내보내기에서 보이지 않는 알파 잔여를 제거했다. 2차 원본은 비교용으로만 보존한다.
참조는 기존 노을 파일이며 읽기만 한다. 산출물은 out4에만 저장한다.

## sky-dawn

Reference: `out2/sky-twilight.webp` (cloud geometry and series identity)
`transparent_background=false`

```text
Use case: lighting-weather.
Asset type: opaque photorealistic DAWN sky texture for a UFO dome, landscape 8:5, target 1280 x 800.
Input image 1 is the existing SUNSET sky-twilight.webp, a series identity and cloud-geometry reference. Create its SUNRISE/DAWN companion. Preserve the reference's broad cloud distribution, apparent altitude, abundance, scale, slanted feather-fine cirrus and thin stratiform threads across the ENTIRE image, including the upper half. Preserve as much cloud placement and wispy detail as possible; change the atmosphere and illumination.
Time and color: fresh clear cool early morning air just before sunrise, distinctly less saturated, less red, and a little brighter than the reference sunset. Top: light cool slate-blue, blue-gray and pale periwinkle/lavender, emphatically NOT dusty rose or purple-pink overhead. Middle: airy pale lilac transitioning through a restrained clear blush pink. Very bottom near horizon: a narrow soft pale peach and champagne-gold atmospheric band. Cool blue-lilac must dominate the upper half; warmth is mostly confined to the lower quarter. The clouds are delicate photographic vapor with pale pink and very pale gold illuminated undersides and cooler gray-lilac body. Keep realistic nuanced fine filament detail; do not replace clouds with an empty gradient or cotton clumps.
Projection and composition: entire image is ONLY sky. Top edge represents approximately 70 degrees elevation, bottom edge approximately the horizon, no land or horizon line. Horizontally even exposure and equal color/brightness at left and right at each altitude. No localized bloom, no directional sunlight, no central bright patch, no vignette. The game shader adds sun direction.
Production requirement: horizontally seamless repeating texture. Left and right cloud fibers must meet smoothly with matching color, luminance, flow and first derivative. No vertical tiling needed. Uniform light across the full horizontal width.
Avoid: sun, moon, stars, celestial points, birds, aircraft, UFO, landscape, trees, sea, buildings, dome, glass, reflections, text, logos, watermark, brushstrokes, illustration, deep orange, crimson, fiery sunset. Output one complete opaque sky image, not a contact sheet, not a mockup.
```

## clouds-dawn

Reference: `out2/clouds-twilight.webp` (four-wisp geometry and quantity)
`transparent_background=true`

```text
Use case: lighting-weather.
Asset type: photorealistic DAWN near-cloud overlay for the same UFO dome series, landscape 8:5, target 1280 x 800, TRUE RGBA TRANSPARENT BACKGROUND.
Input image 1 is the existing clouds-twilight.webp, a cloud-geometry and quantity reference, NOT a background. Create its fresh cool SUNRISE/DAWN companion. Preserve its four separate long thin wisps at approximately the same positions, heights, lengths and feathered texture: one in the upper left around 15-30% image height; one middle right around 36-47%; one small left wisp around 51-56%; one long wavy lower wisp around 64-78%. Match apparent cloud altitude, scale and quantity as closely as possible so the series crossfades coherently. Do not add extra clouds. Fine airy wisps, no thick cumulus.
Lighting and colors: fresh clear cool morning air, lighter and less saturated than sunset. Wisps have pale cool lavender-gray body, subtle clear blush pink and very pale champagne gold on their undersides, delicate photographic vapor, no strong orange or crimson. Broad diffuse even lighting with no side brighter than the other. Partial transparency throughout wisps, natural irregular soft feathered edges, no solid cut-paper bands.
Alpha requirements: AT LEAST 88% of all pixels must be genuinely fully transparent zero alpha, not merely dark or low opacity. Four narrow long wisps occupy at most 12% of the canvas, with large empty spaces between. Keep left and right edges and at least 24 pixels inside both edges COMPLETELY transparent, so horizontal repetition has no join. Keep top and bottom edges transparent too. Return real RGBA alpha, never a painted checkerboard, never opaque black or colored sky.
Avoid: sky background, gradient background, checkerboard squares, black matte, sun, moon, stars, celestial points, birds, aircraft, UFO, terrain, horizon, dome/glass, text, watermark, logo, illustration, solid cloud masses. Output only isolated cloud wisps on genuine transparency.
```
## clouds-dawn 재생성 (2차, 미채택)

Reference: `out2/clouds-twilight.webp`; `transparent_background=true`

```text
Use case: lighting-weather.
Create a DAWN color variant of input image 1, the existing transparent clouds-twilight.webp. It is already a production-ready RGBA texture: retain EXACTLY the same four wisps, positions, shapes, thin soft edges, scale, coverage, translucency and EMPTY SPACE. This is a very small color-only change. Do NOT grow the clouds, add halos, reconstruct their shape, increase density or add fog elsewhere.
Change only the lighting and color of the cloud pixels: reduce the warm sunset coral/pink saturation, use subtle pale cool lavender-gray and delicate very pale blush-pink and champagne-gold undersides. Clean cool sunrise rather than vivid sunset. Keep the same opacity as the reference: thin airy wisps that let the sky show through. Their maximum opacity should be roughly 50%, never white solid opaque bands.
Background: GENUINE RGBA transparency. Preserve or improve the reference's 86.66% exact-zero-alpha empty canvas. At least 86% empty pixels must have alpha EXACTLY ZERO. NO low-opacity residue outside the four reference wisps, NO fringes of random white speckles, no extra clouds, no painted checkerboard. Leftmost and rightmost 24 pixels are fully empty alpha zero, likewise top and bottom margins. Avoid all background colors and sky gradients.
Landscape 8:5 for final 1280x800 WebP, photographic cloud cutouts for horizontally repeating sky-dome overlay. No sun, moon, stars, objects, terrain, text, logo, watermark. Only four isolated, thin, softly feathered dawn cloud wisps.
```
