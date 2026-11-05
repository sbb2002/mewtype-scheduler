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
