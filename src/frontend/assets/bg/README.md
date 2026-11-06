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
| `space-starmap.webp` | NASA Scientific Visualization Studio 「Deep Star Maps 2020」 — 별 데이터 ESA/Gaia/DPAC | NASA 영상 = 퍼블릭 도메인, **Gaia 데이터 = CC BY-NC 3.0 IGO**(출처 표기 · 비상업) | 4096 × 2048 그대로 WebP 품질 80 |
| `space-eso.webp` | ESO/S. Brunier 「은하수 파노라마」 | **CC BY 4.0**(출처 표기 — ESO 조건 「credit is clear and visible」) | 4096 × 2048 그대로 WebP 품질 70 |
| `space-deep.webp` | NASA, ESA, CSA, STScI — 웹 망원경 SMACS 0723 첫 딥필드 | 퍼블릭 도메인(NASA) | 1960 → 1280 픽셀로 줄여 WebP 품질 82 |
| `space-earthrise.webp` | 위키미디어 공용 File:NASA-Apollo8-Dec24-Earthrise.jpg — NASA / Bill Anders | 퍼블릭 도메인 | 공용 960px 판을 WebP 품질 84 |
| `space-crab.webp` | File:Crab_Nebula.jpg — NASA, ESA, J. Hester, A. Loll (ASU) | 퍼블릭 도메인 | 960px 판을 WebP 품질 78 |
| `space-orion.webp` | File:Orion_Nebula_-_Hubble_2006_mosaic.jpg — NASA, ESA, M. Robberto (STScI/ESA), HST Orion Treasury Project Team | 퍼블릭 도메인 | 960px 판을 WebP 품질 84 |
| `space-pillars.webp` | File:Pillars_of_creation_2014_HST_WFC3-UVIS_full-res_denoised.jpg — NASA, ESA, Hubble Heritage Team (STScI/AURA) | 퍼블릭 도메인 | 1280px 판을 WebP 품질 84 |
| `space-tarantula.webp` | File:A_New_View_of_the_Tarantula_Nebula.jpg — NASA | 퍼블릭 도메인 | 1280px 판을 WebP 품질 76 |

- **화면 출처 표시가 아직 없다**: `space-eso`(CC BY 4.0) · `space-starmap`(Gaia CC BY-NC) 는 조건상 출처를 보여야 한다. 운영자 계획(11-05) = 그 자료가 화면에 보일 때만 시선에 고정된 아주 작은 홀로그램 글씨로 — 아직 구현 전(devpapers `ref/bg-dome/SCENARIOS.md` 3절).
- 위키미디어 5장의 라이선스 확인 기록 = devpapers `ref/bg-dome/space_images_license.md`. 앞의 세 장(starmap · eso · deep)은 원본 페이지 주소가 기록에 없어 병합 전에 다시 찾아 적을 것.
