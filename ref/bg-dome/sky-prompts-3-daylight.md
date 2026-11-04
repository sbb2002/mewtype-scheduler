# 3차 실제 낮 하늘 — 생성 프롬프트 원문

생성 도구: 기본 내장 image_gen. 두 기존 이미지를 각각 편집 대상으로 참조. 최종 파일은 out3에만 저장.

설정: sky는 transparent_background=false, clouds는 transparent_background=true. 원본 출력은 각각 1586×992 PNG였으며 sources에 보관했다. 아래 프롬프트는 도구에 보낸 원문이다. 리사이즈·경계 연결·알파 잔여 제거·WebP 인코딩은 finish_assets.py에서 재현할 수 있다.

## sky-daylight

```text
Use case: lighting-weather
Asset type: opaque photographic daylight sky texture for the outside view through a UFO dome, horizontally repeating three times around a cylinder.
Input image: the provided sky-twilight.webp is the EDIT TARGET and exact cloud-layout reference. Make a daytime counterpart of this existing sunset texture.
Primary request: change ONLY time of day, illumination and sky colors from pink sunset to a realistic clear daytime sky. Retain the same fine cirrus / high altocumulus cloud filament positions, sweeping directions, scale, density, altitude placement and texture as closely as possible, so a shader crossfade to the original sunset does not suddenly change the cloud structure.
Composition/framing: single wide flat texture, target 1280 x 800 (8:5). The upper edge corresponds to elevation approximately 70 degrees and lower edge to approximately -12 degrees near the horizon. No visible horizon line or ground. Rich natural medium-deep azure blue at the top, continuously and smoothly becoming much paler atmospheric blue and near-white haze at the bottom. Keep the uppermost region quiet enough to blend to its average color.
Style/medium: convincing photographic clear daytime atmosphere, wispy white cirrus and delicate high altocumulus filaments, natural fine detail, restrained contrast, no fluffy cumulus towers. Cloud amount and structure consistent with the reference, broad clear blue gaps.
Lighting: neutral white daylight, evenly illuminated horizontally at EVERY height, no sun direction, no lateral hotspot or light gradient, no pink/purple/warm sunset cast.
Constraints: exact seamless LEFT/RIGHT horizontal wrapping; cloud filaments crossing one side continue naturally on the other; no vertical tiling requirement. Keep geometry and cloud distribution. Opaque full-frame sky. No border or panel division.
Avoid: sun, solar disk, moon, stars, horizon landscape, ocean, trees, buildings, dome, grid, text, labels, people, logos, watermark, checkerboard, vignetting, directional glow, overcast sky, painted brushstrokes. Output the image only.
```

## clouds-daylight

```text
Use case: lighting-weather
Asset type: genuinely transparent separate photographic white daylight cloud overlay for an outside-view dome sky, target 1280 x 800, 8:5.
Input image: clouds-twilight.webp is the EDIT TARGET and exact silhouette/placement/alpha reference. Produce its daylight counterpart.
Primary request: recolor ONLY the existing sparse sunset cloud wisps into neutral daylight white, with very subtle cool gray-blue self shading. Preserve the exact existing cloud locations, shapes, fine fibrous cirrus / high altocumulus texture, relative size, soft edge falloff, and sparse distribution so shader crossfades remain registered. Do not replace them with a new arrangement.
Background: REAL fully transparent alpha, no painted background of any color and NO rendered checkerboard. At least 85 percent of the complete canvas must have alpha exactly zero. Preserve the sparse transparent spaces in the reference.
Composition: retain the four thin elongated sweeping wisps in the reference. Keep them airy, soft and delicate, not opaque ropes or fluffy cumulus blobs. Keep the broad completely empty sky gaps. Both left and right image edges must remain fully transparent with gradual soft cloud fading before the edge so horizontal repetition has no seam. No hard crop of a cloud. Quiet transparent top and bottom edges.
Lighting: neutral clear-day white, soft even illumination, no warm pink/yellow/peach and no colored matte halos.
Constraints: actual RGBA transparent output; soft partly transparent white edges; no sky pixels, no checkerboard pixels, no solid background. Same cloud elevation distribution as the reference; no new cloud masses.
Avoid: sun, moon, stars, horizon, ground, scenery, dome, grid, text, people, logos, watermark, shadow backdrop, vignette. Output only the transparent cloud image.
```
