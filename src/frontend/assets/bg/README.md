# assets/bg — 배경 돔 이미지

## 공개 자료로 만든 풍경 파일

아래 파일은 미국 정부 기관의 공개 자료(퍼블릭 도메인 · 이용 조건 없음)를 가공한 것이다.
USGS 3DEP 메타데이터는 데이터를 가공한 사용자에게 「가공 내용을 설명할 것」을 요구하므로 여기에 적는다.
이 가공은 원 기관이 승인 · 보증한 것이 아니다.

| 파일 | 원본 | 가공 내용 |
|---|---|---|
| `ground-city-albedo.webp` | USDA NAIP 2023-09-25 콜로라도 정사영상 4장(`m_3910417_nw/ne` · `m_3910409_sw/se`, Denver) | 경도 −104.977 ~ −104.883 · 위도 39.694 ~ 39.766 범위를 잘라 4장을 이어 붙이고 RGB 3밴드만 1024 × 1024 로 줄여 WebP(손실, 품질 75)로 저장 |
| `ground-mountain-albedo.webp` | USGS Landsat 9 Collection 2 Level-2 `LC09_L2SP_033033_20240831_02_T1`(Front Range) | 경도 −105.535 ~ −105.161 · 위도 39.530 ~ 39.818 범위를 잘라 빨강 · 초록 · 파랑 밴드를 감마 · 채도 · 대비 보정 후 1024 × 1024 WebP(손실, 품질 80)로 저장 |
| `ground-mountain-height.webp` | USGS 3DEP 1/3 arc-second DEM `USGS_13_n40w106`(2026-06-30 판) | 위 산 사진과 같은 범위를 잘라 512 × 512 로 줄이고(쌍선형), 높이(m)를 `(높이 − 1500) / 0.5` 정수로 바꿔 R = 상위 8비트 · G = 하위 8비트에 담아 WebP(무손실)로 저장. 되돌리기: `높이 = (R × 256 + G) × 0.5 + 1500`. 줄이면서 생긴 차이 외의 수정 없음 |

받는 방법 · 이용 조건 원문 기록: devpapers 브랜치 `ref/bg-dome/ground_sources.md` · `fetch_ground.py`.

## 우주 사진(UFO 돔 실내 「초행성X」 · 성간 이동)

`space/` 의 파일. 모두 원본 JPEG 을 WebP(손실)로 다시 저장한 것 — 크기 · 품질 외 수정 없음(2026-11-06). 이용 조건은 아래 「조건」 칸 기준(법률 해석 아님).
초행성X 를 고를 때만 받고(바탕 1장 + 큰 사진 1장), 워프 도착 사진은 성간 이동을 시작할 때 1장 더 받는다.

| 파일 | 원본 · 출처 표기 | 조건 | 가공 |
|---|---|---|---|
| `space-starmap.webp` | NASA Scientific Visualization Studio 「Deep Star Maps 2020」 — 별 데이터 ESA/Gaia/DPAC | 원본 페이지(https://svs.gsfc.nasa.gov/4851) 출처 문구 = 「NASA/Goddard Space Flight Center Scientific Visualization Studio. Gaia DR2: ESA/Gaia/DPAC」, 라이선스 표기 없음. Gaia 조건 원문 = 「The Gaia data are open and free to use, provided credit is given to 'ESA/Gaia/DPAC'」(표시 방식 지정 없음, 2026-11-11 확인 — 옛 기록의 「CC BY-NC 3.0 IGO」 는 근거 없음) | 4096 × 2048 그대로 WebP 품질 80 |
| `space-tycho.webp` | NASA Scientific Visualization Studio 「The Tycho Catalog Skymap - Version 2.0」(https://svs.gsfc.nasa.gov/3572, 2009) — `TychoSkymapII.t5_04096x02048.jpg`(은하수 가장 밝은 판) | 퍼블릭 도메인(SVS 「All of our content is in the public domain (unless otherwise noted)」, 이 항목에 예외 표시 없음) | 4096 × 2048 그대로 WebP 품질 60(2026-11-11, ESO 은하수 파노라마 대신)
| `space-edr3.webp` | 「Milky Way 360 equirectangular rendering with foreground stars removed」 — 저자 Kevinmloch(https://commons.wikimedia.org/wiki/File:Milky_Way_360_equirectangular_rendering_with_foreground_stars_removed.png), Gaia EDR3 별 데이터(ESA/Gaia/DPAC)로 bsrender 렌더링 | **CC BY-SA 4.0**(https://creativecommons.org/licenses/by-sa/4.0/) — 파일 페이지에 표준 조건 외 별도 요구 없음(2026-11-11 확인). 이 가공본도 CC BY-SA 4.0 | 8000 × 4000 PNG 를 4096 × 2048 로 줄여(Lanczos) WebP 품질 80(2026-11-11, ESO 은하수 대신) |
| `space-wise.webp` | 「Mapping the Infrared Universe: The Entire WISE Sky — Rectangular Format」(PIA15482, https://science.nasa.gov/photojournal/mapping-the-infrared-universe-the-entire-wise-sky-rectangular-format/) — Credits: NASA/JPL-Caltech/UCLA | JPL Image Use Policy(https://www.jpl.nasa.gov/jpl-image-use-policy) 「may be used for any purpose without prior permission」, 출처 문구는 캡션 것을 쓰라는 요청 · 표시 위치 지정 없음. 제3자 저작권 표시 없음(2026-11-11 확인). NASA · JPL · Caltech 보증을 암시하지 말 것 | 10000 × 5000 JPEG 을 4096 × 2048 로 줄여(Lanczos) WebP 품질 80(2026-11-11) |
| `space-deep.webp` | NASA, ESA, CSA, STScI — 웹 망원경 SMACS 0723 첫 딥필드 | 퍼블릭 도메인(NASA) | 1960 → 1280 픽셀로 줄여 WebP 품질 82 |
| `space-earthrise.webp` | 위키미디어 공용 File:NASA-Apollo8-Dec24-Earthrise.jpg — NASA / Bill Anders | 퍼블릭 도메인 | 공용 960px 판을 WebP 품질 84 |
| `space-crab.webp` | File:Crab_Nebula.jpg — NASA, ESA, J. Hester, A. Loll (ASU) | 퍼블릭 도메인 | 960px 판을 WebP 품질 78 |
| `space-orion.webp` | File:Orion_Nebula_-_Hubble_2006_mosaic.jpg — NASA, ESA, M. Robberto (STScI/ESA), HST Orion Treasury Project Team | 퍼블릭 도메인 | 960px 판을 WebP 품질 84 |
| `space-pillars.webp` | File:Pillars_of_creation_2014_HST_WFC3-UVIS_full-res_denoised.jpg — NASA, ESA, Hubble Heritage Team (STScI/AURA) | 퍼블릭 도메인 | 1280px 판을 WebP 품질 84 |
| `space-tarantula.webp` | File:A_New_View_of_the_Tarantula_Nebula.jpg — NASA | 퍼블릭 도메인 | 1280px 판을 WebP 품질 76 |

## 효과음(`sfx/`, 성간 이동)

Freesound 의 공개 미리듣기 파일(MP3)을 받아 잘라 다시 저장했다(2026-11-06). 둘 다 **CC0**(이용 조건 없음, 출처 표시 의무 없음 — 각 페이지의 라이선스 칸 확인).

| 파일 | 원본 | 조건 | 가공 |
|---|---|---|---|
| `alarm.wav` | 「Digital Alarm Loop.wav」 by bbrocer — https://freesound.org/people/bbrocer/sounds/389511/ | CC0 | 앞 0.242초(원본 길이)만 48kHz 16비트 모노 WAV 로 — 반복 재생 때 빈틈이 없게 |
| `warp-jump.m4a` | 「Warp Speed.wav」 by DylanTheFish — https://freesound.org/people/DylanTheFish/sounds/454683/ | CC0 | 12.8 ~ 17.3초(소리가 가장 큰 14.0초 앞뒤)를 잘라 앞 0.03초 · 끝 0.8초 페이드, AAC 96kbps |

- **출처**: `space-starmap` 의 출처(ESA/Gaia/DPAC 포함)는 이 표에 적는다 — Gaia · SVS 원문은 표시 방식을 정하지 않았다. ESO 은하수 `space-eso`(CC BY 4.0)는 ESO 조건(「clear and visible」, 사진과 떼어 두지 말 것)상 화면 표시가 필요해 2026-11-11 뺐다(운영자 결정 대기 — 다시 쓰려면 화면 출처 표시).
- 위키미디어 5장의 라이선스 확인 기록 = devpapers `ref/bg-dome/space_images_license.md`. 앞의 두 장(starmap · deep)은 원본 페이지 주소가 기록에 없어 병합 전에 다시 찾아 적을 것.
