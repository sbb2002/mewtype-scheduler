# 수평선 아래 풍경 구현 결과 — 2026-11-05

기능의 첫 구현과 데스크톱 검증을 마쳤습니다. **실사 수준의 완성은 아닙니다.** 특히 산 표면과 도시 구역은 절차적 대체 질감입니다. GPU 비용은 기존보다 약 52~55% 증가했습니다. 30/60fps 갱신을 요청하는 코드는 넣었지만 이 환경의 SwiftShader에서는 실제 30fps를 달성하지 못했습니다.

제품 변경 파일은 `src/frontend/js/bgdomegl.js`, 새 데이터 생성·셰이더 모듈 `src/frontend/js/bgground.js` 두 개입니다. LF 저장, git commit 없음. 검증 코드·측정·이미지는 무시되는 `_local/ground-review/` 안에 있습니다. 기준 소스는 `baseline.js`입니다.

## 변경 및 단계별 상태

| 단계 | 상태와 한계 |
|---|---|
| 1 기준 측정 | 변경 전 소스를 보존하고 최종 장면에서 두 셰이더를 같은 uniform·텍스처·카메라로 교대 재생. 기준 정지 draw 약 6fps도 확인. 실제 휴대폰 GPU 기준값 없음 |
| 2 구형 지표·가림 | 지구 반지름 6371km, 외부 눈 고도 기본 2km. 구 교차의 가까운 해를 안정적인 식으로 계산. 수평선 1픽셀 면적 AA. 돔 E와 외부 세계를 분리해 줌에 외부 지형이 밀리지 않음 |
| 3 천체 가림 | 고도 0°에서 원반·별을 지우던 마스크 제거. 지표·산·건물 합성으로 가림. 태양·달의 기존 가시성 감쇠를 기준 지표 수평선보다 아래로 이동. 렌즈는 같은 `groundGeometry()`를 태양 원반 9점에서 평가해 가림 비율을 공유 |
| 4 대기색 | 하늘과 같은 A/B 텍스처·색 행렬·혼합률의 수평색, 야간 감광, 태양 방향 온기 사용. 거리 km의 exp 감쇠. 하늘의 모든 산란 항을 동일 함수로 완전히 공통화한 상태는 아니므로 정밀한 색 일치는 미완료 |
| 5 산 | 12/35/80km 거리층, 약 0.45~3.4km 높이의 시드 능선, 표면 결·음영·높은 곳의 옅은 눈. 폴리곤 메시나 레이마칭 없음. **실사 질감 및 실제 침식 지형의 완성도는 미달** |
| 6 바다 | 구형 수면 법선·시선·해/달 방향의 GGX 계열 반사 근사. 64초 반복 slope 텍스처 두 샘플. 태양 낮은 고도 반사, 달 위상 제곱·밤·고도 가시성에 연동. 구름에 의한 해 반사 감소. 달 위치 구름 차폐와 실제 파도 스펙트럼은 미구현 |
| 7 도시 | 8km 반복 타일의 구역·공원·도로·지붕, 8/22/65km의 건물 윤곽. 고정 가로등에 2.5%의 느린 주기 변화, 도로에 제한한 차량 패턴 이동. 차량 타일 512초 순환(약 15.6m/s). mipmap으로 작은 불빛을 평균 radiance로 전환. **도시 형태·도로망의 실사감은 미달**, 한 방향의 차량 흐름만 구현 |
| 8 저장·실내 | 첫 시드 `localStorage["bg-ground-seed-v1"]`, 세 종류 중 하나 유지. 강제 seed/kind는 저장값을 바꾸지 않음. 같은 지형을 실내에서 분홍·저대비로 합성. 저장소 차단 시 현재 모듈 수명 동안만 유지되며 재방문 영속성 불가 |

원래 돔 바닥·조명·떠다니는 장식은 유지했습니다. 풍경은 바닥에 가리지 않는 수평선 띠를 통해 보입니다. 바닥에 풍경을 반사시키지는 않았습니다. 광원의 넓은 대기광은 천체 원반처럼 소스 가림으로 전부 끄지 않습니다.

풍경이 화면 하단에 들어올 수 있는 시야에서는 정지 중에도 보통 30fps / `bg-peek` 60fps를 요청합니다. 위쪽 하늘만 보일 때는 기존 약 160ms 간격을 유지합니다. 산 최고 고도를 고려한 보수적인 시야 판정이라 실제 지형이 없는 일부 시야에서도 갱신할 수 있습니다. 기존 pause·페이지 중단 경로는 유지합니다.

## 확인 URL

`/src/frontend/?bgdebug&bgground=city&bgseed=42&bgalt=2&bgspeed=0&bgmoon=0.5`

- `bgground=city|mountain|sea`, `bgseed=정수`, `bgalt=1|2|3`은 `bgdebug`가 있어야 적용됩니다. 시드는 uint32로 정규화합니다.
- 기본 고도는 2km. 종류·시드만 바꿔도 시각에 따라 세계를 다시 추첨하지 않습니다.
- `bgspeed=0`은 천문 시각과 풍경 템플릿 시간을 고정합니다. 기존 `bgtime`, `bgmoon`, `bgsunalt/bgsunaz`, `bgmoonalt/bgmoonaz`도 유지합니다.
- 실제 천체·실외 조명을 보려면 기존대로 위치 확보와 바깥 보기 선택이 필요합니다.

## 캡처

390×760 CSS, DPR 1.5, WebGL 버퍼 585×1140. seed 42. 캡처는 `review.py`에서 카메라 uniform을 직접 고정합니다. 앱 자체의 센서 입력을 재현한 캡처는 아닙니다. 배경 canvas 영역의 캡처이므로 그 위의 기존 DOM 장식도 함께 보입니다.

- [종류 × 낮/노을/밤 요약](overview.jpg): 행 city/mountain/sea, 열 day/sunset/night. 시선 −10°, 줌 0.6.
- [실내 세 종류](indoor.jpg), [1/2/3km 비교](altitude.jpg).
- 핵심 요청 72장: `{city,mountain,sea}-{day,sunset,night}-{horizontal,down10,source}-z{0,0.6}.png` 54장, `*-indoor.png` 9장, `{kind}-alt{1,2,3}.png` 9장.
- source 시선은 낮 해 40°, 노을 해 1°, 밤 보름달 5° 방향(방위 180°). 실내는 −10°/줌 0.6. 고도 비교는 −5°/줌 0.6.
- [실내 변경 전](before-indoor.png), [실내 변경 후](after-indoor.png), [실외 변경 전](before-outdoor.png), [실외 변경 후](after-outdoor.png): 같은 장면의 이전/현재 셰이더 재생.
- `rotation-{kind}-{000..330}.png`: 각 종류 30° 간격 한 바퀴. `city-seam-*.png`: 북쪽 ±0.1° 보조 캡처.
- `city-micro-00..20.png`: 0.012°씩 미세 회전. [도시 야간 raw GL 미세 회전 GIF](city-raw-micro.gif)는 DOM 장식을 제외한 버퍼 영역입니다.
- `sea-loop-{0,63.99,64,64.01}.png`, `sea-reflection-power-*.png`: 반복 경계와 반사 기여 격리. power 캡처는 uniform을 직접 바꾸며 실제 달 원반 위상 변경 캡처는 아닙니다.

광원 위치를 바꾸는 카메라 캡처에서 CPU의 flare 투영 좌표까지 매번 재계산하지는 않았습니다. 렌즈 차폐는 `supplemental.py`가 별도로 `uFlare`를 강제해 검사합니다. 모든 캡처가 렌즈 효과의 구도까지 정확히 검증하는 것은 아닙니다.

## 수치 검증

`errors.json`의 JS/셰이더 오류 0. 두 JS의 `node --check`, `git diff --check` 통과.

- 세 종류 모두 고정 시각 0°/360° 재생의 다른 채널 수 **0** (`geometry-checks.json`). 북쪽 연결과 별개로 방위 전체가 닫힘을 확인했습니다. 임의 각도의 반복 패턴이 보이지 않는다는 보증은 아닙니다.
- 바다 기하 마스크에서 1/2/3km 강하 −1.01509°/−1.43546°/−1.75796°. 각각 중앙 세로선에 부분 덮임 픽셀 **1개**, coverage 약 0.043/0.675/0.557. 실제 색·장식이 아닌 마스크 전용 진단 셰이더의 결과입니다.
- 해 고도 −2°에서 도시·산·바다 모두 렌즈 on/off 출력의 다른 채널 **0**. 산 고도 −1°에서도 **0**, 같은 고도의 바다·도시는 효과가 남았습니다. seed 42의 거리층에 따른 차폐 차이가 소스 마스크에 반영됩니다 (`supplemental.json`).
- 야간 도시 21프레임, 0.012°/프레임, 시간 1/30초씩 증가. 345×84 device px 영역 휘도 합의 최대 인접 변화 **0.07836%**. 같은 영역의 산·바다는 2프레임 보조 측정만 했습니다. 이 합계는 바닥/빔·대기 기여도 포함해 개별 불빛의 떨림을 과소평가할 수 있습니다. 지글거림 완전 제거의 입증은 아닙니다.
- 시드 저장값 재사용, 강제값 후 저장 시드 보존, 저장소 차단 시 예외 없이 생성, 실제 reload 후 저장값 유지 확인 (`supplemental.json`, `frame-rates.json`).

GPU 타이머는 `EXT_disjoint_timer_query_webgl2`. **ANGLE Vulkan SwiftShader 소프트웨어 렌더러**입니다. 각 종류 밤 / −10° / 줌 0.6, 같은 버퍼·카메라·uniform·텍스처, 기존/현재 순서 교대 8라운드, 각 10회 draw. disjoint 샘플 0. 카메라를 직접 바꾼 장면으로 렌즈 gain은 0인 상태이며 렌즈가 강하게 보이는 최악 장면의 비용은 측정하지 않았습니다. p95는 라운드 8개에서 inclusive 보간한 값으로 표본이 작습니다.

| 종류 | 기존 중앙값 | 현재 중앙값 | 증가 | 기존 p95 | 현재 p95 |
|---|---:|---:|---:|---:|---:|
| 산 | 43.897ms | 66.665ms | +51.87% | 44.819ms | 69.927ms |
| 바다 | 43.842ms | 68.104ms | +55.34% | 47.603ms | 72.533ms |
| 도시 | 43.231ms | 65.626ms | +51.80% | 44.944ms | 70.745ms |

원자료 `costs.json`, 측정 코드 `bench.js`. **+15% 예산 미달**입니다. 이번 운영자 요구에 따라 표면 세부를 추가한 상태로 비용을 보고합니다. 바닥에 완전히 가려진 픽셀의 지표 계산 생략, 소스 가림의 CPU 또는 별도 소량 처리 등이 다음 최적화 후보입니다.

별도의 정지 장면 2.5초 draw 카운트: 기존 보통/배경 보기 약 5.96/5.99fps, 현재 약 **13.55/15.98fps**. 요청 주기는 30/60fps지만 SwiftShader 실행은 부족합니다. 실기기에서 움직임이 부드럽다는 판정은 하지 않았습니다. 소프트웨어 결과를 휴대폰 GPU 비용으로 환산할 수 없습니다.

추가 생성 텍스처: 512² RGBA8 + mipmap 약 1.33MiB, 2048×4 RGBA8 약 32KiB, 1픽셀 albedo 자리 4B, 합계 약 **1.36MiB**(드라이버 부대 메모리 제외). 정적 데이터 생성 CPU 단발 측정 도시 87.0ms / 산 82.1ms / 바다 72.0ms. 첫 생성이 메인 스레드에서 잠깐 멈출 수 있습니다. 추가 코드 순증 약 13.5KB, 새 모듈 단독 gzip 약 4.8KB. 새 이미지 다운로드 **0**. 추가 draw call·렌더 패스 없음.

## 승인 후 받을 실사 이미지 후보 — 이번에는 다운로드하지 않음

이미지 이용 조건과 개별 크레딧은 Claude가 최종 확인해야 합니다. NASA 자료에 제3자 저작물이 섞일 수 있으므로 기관명만으로 일괄 허용으로 취급하지 않습니다. NASA/Landsat 안내는 NASA 외 저작자 표기가 없는 Landsat 파생물을 공개 자료로 설명하고 USGS/NASA 출처 표시를 요구합니다: [NASA Landsat multimedia](https://science.nasa.gov/mission/landsat/multimedia/), [NASA media guidelines](https://www.nasa.gov/nasa-brand-center/images-and-media/).

| 용도 | 필요한 이미지와 권장 파일 | 후보 출처 |
|---|---|---|
| 도시 albedo, 우선 | 낮의 수직 정사사진, 도심·주택가·공원이 섞인 8×8km. 원본 1~4m급에서 2048² 또는 4096² RGB WebP로 축소. 표지·구름·짙은 그림자·밤 조명 없는 crop. 제안명 `ground-city-albedo.webp` | [USGS NAIP Plus ImageServer](https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPPlus/ImageServer), [USGS EarthExplorer 이용 안내](https://www.usgs.gov/centers/eros/science/earthexplorer-help-index). 서비스는 공공 정사영상 제공을 명시하나 해당 crop 메타데이터 확인 필요 |
| 도시 광역 대체 | Denver 도시와 Front Range 평지의 자연색 Landsat 이미지에서 글자·연도·비교 패널 없는 한 시점 crop. 2048²~4096². 8km 표면에는 고해상도 NAIP를 우선하고, Landsat은 더 큰 구역용으로 검토 | [NASA SVS: 50 years of Landsat — Denver](https://svs.gsfc.nasa.gov/31196/), [USGS Landsat Data Access](https://www.usgs.gov/landsat-missions/landsat-data-access) |
| 산 albedo, 우선 | Rocky Mountains/Front Range 계곡·수림·바위의 32×32km 자연색, 눈·구름·단단한 그림자 최소. 2048² RGB(약 16m/texel) 또는 4096². 제안명 `ground-mountain-albedo.webp` | [USGS Landsat Data Access](https://www.usgs.gov/landsat-missions/landsat-data-access), [NASA Landsat data overview](https://science.nasa.gov/mission/landsat/data-overview/). EarthExplorer에서 여름의 구름 적은 Landsat 8/9 surface reflectance를 선택하는 방안 |
| 바다 | 지금은 사진 불필요. 실사 파도 사진에는 이미 조명·반사가 들어 있어 albedo로 부적절. 필요하면 해안 없는 심해의 저주파 자연색만 1024² | [NASA Landsat multimedia](https://science.nasa.gov/mission/landsat/multimedia/)에서 광학 이미지 후보만 검토. 파도 법선은 별도 데이터가 필요 |

USGS는 Landsat 접근을 [공식 데이터 접근 안내](https://www.usgs.gov/landsat-missions/landsat-data-access)에서 제공하며, NAIP Plus는 공개 정사영상과 고해상도 도시 영상을 설명합니다. 현재 파일을 가져오거나 `src/frontend/assets/bg/`에 쓰지 않았습니다.

교체 자리: texture unit 7 / sampler `uGroundAlbedo`, 기본 `uGroundAlbedoOn=0`. 승인 이미지 업로드 후 mipmap + REPEAT 설정, `uGroundAlbedoOn=1`로 사용. base 지표는 `pos.xz / 8km`(도시), `/32km`(산), 산 거리층 표면은 방위·높이 좌표를 사용합니다. 경계를 seamless로 처리하고 한 타일 안의 스케일을 맞춰야 합니다. **이미지 로더·자동 탐색은 아직 없습니다.** 향후 로딩 코드를 두 JS 안에 추가해야 합니다. sRGB를 근사 gamma 2.2로 풀지만 기존 하늘/최종 합성 전체가 선형광인 것은 아닙니다. 촬영 그림자가 강한 이미지를 단순히 꽂는 것만으로 올바른 시각별 재조명을 얻을 수 없습니다. 특히 산 거리층 매핑은 사진과 실제 기하의 일치까지 보장하지 않습니다.

## 남은 것·확실하지 않은 것

- 실사 이미지 승인·도입 및 산/도시 형태의 실사감 개선. 현재 결과는 요청한 실사 수준의 최종 승인본으로 보기 어렵습니다.
- Android/iPhone GPU 시간·30/60fps·센서의 느린/빠른 팬·실제 화면에서 개별 불빛의 지글거림. 비용 개선은 별도 단계입니다.
- 달 각 위상/고도의 실제 URL별 반사 캡처 전체, 산·건물 뒤 해/달 원반이 연속 통과하는 영상, 고도 +10/−15/−30/−55° 전체 조합, 밝은 테마·가로·센서 거절·context 복구 등 표의 나머지 조합. 현재 전부 완료하지 않았습니다.
- 구름의 달 반사 차폐, 거리층 사이 물리적 지형 연결, 사진에서 제거하기 어려운 원래 그림자, 정확한 대기 광학/실제 지리와의 대응. 고도·지형·날씨는 가상입니다.
- 대기색은 같은 소스와 주요 보정을 사용한 근사입니다. 모든 천체·산란 계산을 단일 공통 함수로 재구성하지 않았습니다.
- 반복 타일과 정형 도시 도로망의 반복감, 산 거리층의 벽처럼 보이는 인상을 완전히 해소하지 못했습니다. 사진만으로 능선 기하의 실사감을 보증할 수 없습니다.
