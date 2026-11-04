# 시간대별 하늘·구름 2차 생성 프롬프트 원문

Built-in image_gen 사용. 각 호출은 첨부한 낮 기준 PNG 1장을 참조. 하늘: transparent_background=false. 구름: transparent_background=true. 프롬프트는 아래 원문 그대로 전달했다. 산출 경로는 요청의 최종 조건에 따라 out2만 사용하며 기존 out은 수정하지 않는다.

## sky-twilight

Reference: `ref-day-sky.png`

```text
Use case: lighting-weather.
Asset: horizontally repeating photorealistic sky texture for a transparent UFO dome, target 1280 x 800, landscape 8:5. Input image 1 (ref-day-sky.png) is our own daytime reference. Preserve its series identity and broadly similar detailed thin cirrus/stratiform cloud abundance, feathered filament scale and wide distribution across the ENTIRE frame, including the upper half. Do not turn it into empty gradient sky. Create only a distant opaque sky layer, no foreground separate cloud cutouts.
Time of day: twilight usable both for sunset and dawn. Lower edge must be the brightest and warmest, a broad gentle band of coral-peach and restrained honey gold. Transition upward through pink rose to mauve-violet at top. Pink identity from reference remains. Many delicate thin high clouds throughout, softly illuminated pink-gold filament edges, still photographic, no thick orange cumulus. Upper clouds visible and detailed, not blank. No one side brighter than the other.
Composition: sky only from elevated sky at top to near-horizon air at bottom; no horizon line or terrain. Horizontally EVEN atmospheric lighting with no sun direction or localized bright spot. Match left and right boundary color and cloud flow for seamless horizontal tiling, no vertical tiling needed. Natural photographic wisps with subtle fine detail, no brushstrokes, no illustration. No sun, moon, stars or any bright celestial points, no birds/bats, objects, buildings, landscape, dome, glass, reflections, grid, letters, watermark or logo. Clouds remain atmospheric and diffuse, never heavy blobs.
```

## sky-bluehour

Reference: `ref-day-sky.png`

```text
Use case: lighting-weather.
Asset: horizontally repeating photorealistic sky texture for a transparent UFO dome, target 1280 x 800, landscape 8:5. Input image 1 (ref-day-sky.png) is our own daytime reference. Preserve its series identity and broadly similar detailed thin cirrus/stratiform cloud abundance, feathered filament scale and wide distribution across the ENTIRE frame, including the upper half. Do not turn it into empty gradient sky. Create only a distant opaque sky layer, no foreground separate cloud cutouts.
Time of day: immediately after twilight, blue hour. Deep muted violet and indigo-violet overhead graduating to lavender with a narrow pale dusty pink atmospheric band along the whole bottom edge. A WIDE layer of delicate photographic cirrus and thin stratiform wisps covers much of the image, comparable spatial coverage and fine texture to reference, including upper and middle portions. Clouds have faint lavender illumination and translucent muted violet undersides; retain visible wispy texture, no black silhouette, no discrete dark clumps. Exposure is dimmer than twilight but still readable; restrained pink series identity. No localized celestial light.
Composition: sky only from elevated sky at top to near-horizon air at bottom; no horizon line or terrain. Horizontally EVEN atmospheric lighting with no sun direction or localized bright spot. Match left and right boundary color and cloud flow for seamless horizontal tiling, no vertical tiling needed. Natural photographic wisps with subtle fine detail, no brushstrokes, no illustration. No sun, moon, stars or any bright celestial points, no birds/bats, objects, buildings, landscape, dome, glass, reflections, grid, letters, watermark or logo. Clouds remain atmospheric and diffuse, never heavy blobs.
```

## sky-night

Reference: `ref-day-sky.png`

```text
Use case: lighting-weather.
Asset: horizontally repeating photorealistic sky texture for a transparent UFO dome, target 1280 x 800, landscape 8:5. Input image 1 (ref-day-sky.png) is our own daytime reference. Preserve its series identity and broadly similar detailed thin cirrus/stratiform cloud abundance, feathered filament scale and wide distribution across the ENTIRE frame, including the upper half. Do not turn it into empty gradient sky. Create only a distant opaque sky layer, no foreground separate cloud cutouts.
Time of day: night. Deep navy-indigo and midnight violet sky, visibly colored and not pitch black. Preserve a broad distribution of feather-fine high cirrus/stratiform veils similar to the reference; they are visible as very low-contrast silver-lavender and cool mauve atmospheric texture over much of the image, subtle enough to place shader stars over later. Lower edge only a little softer muted purple, NO orange band. These are diffuse photographic thin clouds, neither cosmic nebula nor dense glowing storm clouds. No directional spotlight. No stars or dots of any kind, NO moon.
Composition: sky only from elevated sky at top to near-horizon air at bottom; no horizon line or terrain. Horizontally EVEN atmospheric lighting with no sun direction or localized bright spot. Match left and right boundary color and cloud flow for seamless horizontal tiling, no vertical tiling needed. Natural photographic wisps with subtle fine detail, no brushstrokes, no illustration. No sun, moon, stars or any bright celestial points, no birds/bats, objects, buildings, landscape, dome, glass, reflections, grid, letters, watermark or logo. Clouds remain atmospheric and diffuse, never heavy blobs.
```

## clouds-twilight

Reference: `ref-day-clouds.png`

```text
Use case: photorealistic-natural.
Asset: standalone near-cloud overlay for a panoramic sky dome, landscape 8:5 target 1280x800. TRUE RGBA TRANSPARENT BACKGROUND. Input image 1 ref-day-clouds.png is our own daytime material reference ONLY: match its soft photographic pink mist and fine airy cirrus filaments, but greatly REDUCE its coverage. Do not reproduce any black/red/gray matte artifacts from preview.
Composition: at least 88-90 percent COMPLETELY EMPTY TRANSPARENT SPACE; just 3 or 4 extremely thin stretched-out wisps distributed across the canvas, with feathered partly transparent edges, no solid central masses. Each wisp is a tenuous irregular horizontal haze filament, not a compact object. A few fine long threads, not thick bands. Natural photographic high-altitude mist texture, not painterly. Clear open sky between wisps (actual zero alpha, no sky background). Keep top and bottom edges fully clear, left and right edges fully transparent for seamless horizontal repeating. Modest low opacity even inside clouds; all cloud detail is wispy, never a heavy silhouette.
Lighting: sunset/dawn soft coral-pink vapor with delicate pale peach-gold glints along fine filament edges. Broad diffuse illumination with no localized light direction. Very delicate airy mist overlay, photograph-like, complements the pink twilight reference series.
Never add opaque black or other background, checkerboard squares, sky gradient, sun, moon, stars, bright points, birds, bats, UFOs, objects, terrain, horizon line, dome/glass, grid, reflection, text, logo or watermark. No illustration, no linework, no black clumps. Output only the isolated cloud wisps on genuine transparency.
```

## clouds-bluehour

Reference: `ref-day-clouds.png`

```text
Use case: photorealistic-natural.
Asset: standalone near-cloud overlay for a panoramic sky dome, landscape 8:5 target 1280x800. TRUE RGBA TRANSPARENT BACKGROUND. Input image 1 ref-day-clouds.png is our own daytime material reference ONLY: match its soft photographic pink mist and fine airy cirrus filaments, but greatly REDUCE its coverage. Do not reproduce any black/red/gray matte artifacts from preview.
Composition: at least 88-90 percent COMPLETELY EMPTY TRANSPARENT SPACE; just 3 or 4 extremely thin stretched-out wisps distributed across the canvas, with feathered partly transparent edges, no solid central masses. Each wisp is a tenuous irregular horizontal haze filament, not a compact object. A few fine long threads, not thick bands. Natural photographic high-altitude mist texture, not painterly. Clear open sky between wisps (actual zero alpha, no sky background). Keep top and bottom edges fully clear, left and right edges fully transparent for seamless horizontal repeating. Modest low opacity even inside clouds; all cloud detail is wispy, never a heavy silhouette.
Lighting: blue hour just after twilight. Very muted dusty violet and desaturated lavender-gray haze. Cloud interiors are transparent violet vapor, gently darker than a blue-hour sky, with only the faintest lavender feathered edges. NO black silhouette, no solid body, no compact bird-like shapes. Long fine threads dispersed as translucent atmospheric streaks. No white bright thick cloud.
Never add opaque black or other background, checkerboard squares, sky gradient, sun, moon, stars, bright points, birds, bats, UFOs, objects, terrain, horizon line, dome/glass, grid, reflection, text, logo or watermark. No illustration, no linework, no black clumps. Output only the isolated cloud wisps on genuine transparency.
```

## clouds-night

Reference: `ref-day-clouds.png`

```text
Use case: photorealistic-natural.
Asset: standalone near-cloud overlay for a panoramic sky dome, landscape 8:5 target 1280x800. TRUE RGBA TRANSPARENT BACKGROUND. Input image 1 ref-day-clouds.png is our own daytime material reference ONLY: match its soft photographic pink mist and fine airy cirrus filaments, but greatly REDUCE its coverage. Do not reproduce any black/red/gray matte artifacts from preview.
Composition: at least 88-90 percent COMPLETELY EMPTY TRANSPARENT SPACE; just 3 or 4 extremely thin stretched-out wisps distributed across the canvas, with feathered partly transparent edges, no solid central masses. Each wisp is a tenuous irregular horizontal haze filament, not a compact object. A few fine long threads, not thick bands. Natural photographic high-altitude mist texture, not painterly. Clear open sky between wisps (actual zero alpha, no sky background). Keep top and bottom edges fully clear, left and right edges fully transparent for seamless horizontal repeating. Modest low opacity even inside clouds; all cloud detail is wispy, never a heavy silhouette.
Lighting: quiet night, faint soft silver-gray and pale muted lavender glints in feathered edges of extremely tenuous thin vapor. Not white bright cotton, no opaque cloud body. Clouds almost dissolve into empty space, very sparse and wispy. Subtle diffuse moonlit feel but NO moon or light source depicted. Gentle and natural photographic, not a cosmic nebula.
Never add opaque black or other background, checkerboard squares, sky gradient, sun, moon, stars, bright points, birds, bats, UFOs, objects, terrain, horizon line, dome/glass, grid, reflection, text, logo or watermark. No illustration, no linework, no black clumps. Output only the isolated cloud wisps on genuine transparency.
```


