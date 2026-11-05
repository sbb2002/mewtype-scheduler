# 풍경 표면 사진 — 출처 · 이용 조건 (2026-11-05)

**운영자 결정(11-05)**: 풍경 사진은 **공개 자료만** 쓴다. 출처 표기는 하지 않는다(가공한 이미지를 기관 것이라 표기하지 말라는 NASA 조항 취지 — 운영자 해석). 저장소 용량에 주의(머지하면 GitHub 에 올라감).

| 파일(`src/frontend/assets/bg/`) | 원본 | 이용 조건(원문 확인) | 크기 |
|---|---|---|---|
| `ground-city-albedo.webp` | USDA NAIP 2023-09-25 콜로라도, 아이템 `co_m_3910417_nw/ne` · `co_m_3910409_sw/se` `_13_030_20230925_20240104`(Denver 동쪽 · Cherry Creek · City Park). bbox −104.977, 39.694, −104.883, 39.766(약 8 × 8km) | 아이템 메타데이터 XML: 「Access Constraints: None Use Constraints: None」 + 면책 조항. 제작 USDA FPAC-BC-GEO, 촬영 위탁 Surdex | 1024², q75, 354KB(≈ 8m/px) |
| `ground-mountain-albedo.webp` | USGS Landsat 9 C2 L2 `LC09_L2SP_033033_20240831_02_T1`(구름 0.57%), Front Range 산지. bbox −105.535, 39.530, −105.161, 39.818(약 32 × 32km). 동쪽 끝 1/6 에 Golden · Morrison 시가지가 걸린다 | USGS 저작권 안내(웹 아카이브 2026 사본 — 원 페이지 11-05 HTTP 500): 「USGS-authored or produced data and information are considered to be in the U.S. Public Domain」 | 1024², q80, 91KB(≈ 31m/px = Landsat 원 해상도) |

- 받는 방법 = `fetch_ground.py`(Microsoft Planetary Computer STAC 검색 → 아이템별 bbox 잘라 받기 → 이어 붙이기). PC 는 원본을 그대로 보관만 하는 미러.
- 도시는 NAIP Plus(주 정부 영상이 섞임) 가 아니라 USDA NAIP 원본만 썼다.
- 도시 사진은 NAIP 타일 4장의 경계에서 밝기 차이가 조금 보인다. 8km 반복 타일로 쓸 땐 이음매 처리 필요.
- 2048² 원본(도시 2.2MB)은 용량 때문에 1024² 로 줄였다. 2km 상공 · 원경이라 8m/px 로 충분하다고 판단(폰 실측 확인 필요).

## 산 높이 — USGS 3DEP (11-05 추가)

| 파일 | 원본 | 이용 조건(원문 확인) | 크기 |
|---|---|---|---|
| `ground-mountain-height.webp` | USGS 3DEP 1/3″ DEM `USGS_13_n40w106`(2026-06-30 판), 산 사진과 같은 bbox. Planetary Computer `3dep-seamless` 아이템 `n40w106-13`(PC 라이선스 칸 = PDDL-1.0) | USGS 3DEP 소개(usgs.gov/3d-elevation-program, 11-05 웹 아카이브 사본 — 원 페이지 403): 「All 3DEP products are available free of charge and without use restrictions」(라이다 점군 포함). USGS FAQ: 「USGS-authored or produced data and information are considered to be in the U.S. public domain and can be freely used without permission」. 원본 메타데이터 useconst: 가공하면 **가공 내용을 설명할 의무**, 데이터를 왜곡하거나 USGS 승인 · 보증처럼 보이게 하지 말 것, 출처 표기는 권장(의무 아님) | 512², 무손실 WebP 196KB(`(R×256+G)×0.5+1500` m) |

- 가공 내용 설명 = `src/frontend/assets/bg/README.md`(운영자 11-05 — 파일 두는 곳에 README).
- 운영자 기준(11-05): 기관 요구는 들어주되, 메인 기능을 해치거나 개발자 · 사용자에게 불필요한 요구를 하면 그 자료는 쓰지 않는다. USGS 는 문제없음.
- 도시 건물 높이: PC `3dep-lidar-hag`(Microsoft · Landrush 가 USGS 라이다로 만든 파생물)는 라이선스 칸 「other」 · 조건 원문 없음 → 미확인, 쓰지 않음. USGS 원본 라이다 점군 자체는 위 「without use restrictions」 에 포함.
