# 배경 「UFO 돔」 인계 (2026-11-05 갱신)

다음 세션이 이어서 하는 작업이다. 여기부터 읽는다. 다른 PC 에서도 이 문서와 브랜치만으로 이어 갈 수 있게 썼다.

## 지금 상태 한눈에

- 브랜치 `feat/bg-dome`(원격 푸시됨), 워크트리 `mewtype-scheduler-worktrees/v4/feat-bg-dome`. `main` v4.11.7 위에서 갈라졌다(main 은 v4.11.11 까지 나감 — 병합 전에 main 을 받아 충돌을 봐야 한다).
- **운영에는 아직 없다.** 이 브랜치에서는 돔이 기본 배경. `?bg=normal` = 가속 없이 지금 시각, 옛 배경 = `?bg=classic`, 시안 = `?bg=a · b · c`. 병합 · 배포는 운영자 결정. 병합되면 **v4.12.0(마이너)**(운영자 확정 11-04).
- 운영자 폰 = **S23 · 삼성 인터넷**(11-04 운영자 확인. 옛 기록의 「안드로이드 10」은 틀렸던 것).
- **11-05 세션 끝 상태**: `브랜치 끝 `2b3e1f4`(망원 줌). 작업 폴더 깨끗(미커밋 없음). 폰 확인 서버 · Tailscale Serve 는 끄고 마쳤다 — 다시 쓰려면 아래 「확인 방법」.`

## 이어서 할 일 (우선순위)

1. **망원 줌 · 지평선 달 질감** — ``2b3e1f4` 로 들어감(×30 에서 참고 사진 같은 주황 보름달 · 무늬 · 어두운 하늘 확인). **남은 과제: 1배에서 낮은 달(고도 5°)이 다시 작은 점** — 광륜을 줄인 대가. 1배에서도 「물체」로 찾을 수 있는 최소 크기감(지평선 실루엣 단서 · 원반 대비)을 풍경 작업과 같이 정할 것. 망원 중 돔 유리 격자선이 달 위를 지나는 것도 운영자에게 괜찮은지 확인.`
2. **수평선 아래 풍경 2단계** — 1단계(`84f8fab`)는 「중간」: 구형 지표 · 산 · 도시 · 바다 · 시드 저장 · 실내 분홍은 들어갔지만
   (a) **실사감 부족**(운영자 요구 = 실사에 가깝게, 만화 · 저다각형 금지) — Codex 가 필요한 퍼블릭 도메인 항공 · 위성 이미지 규격 · 출처 후보를 `codex_ground_impl_report.md` 에 정리해 둠. **출처 · 이용 조건 확인 → 운영자 승인 → 내려받기** 순서(운영자 지시). 받으면 `src/frontend/assets/bg/`, 출처는 README 「사용한 공개 자료」(앱 디스클레이머가 아니라 README — 운영자 11-05).
   (b) 도시 밤 불빛이 약하다 — 운영자 요구: 멀리서 약한 반짝임(가로등 거의 고정 + 옅은 흔들림, 차량은 도로 따라 천천히 흐름), 바다는 달(해) 광원에 따라 일렁이는 반사.
   (c) **GPU +52 ~ 55%**(SwiftShader 44 → 66 ~ 68ms), 30/60fps 미달 — 운영자: 「부드럽게 먼저, 최적화는 그다음」 + **「애니메이션 템플릿」(미리 만든 반복 패턴 재사용)** 방식 제안.
   (d) 달 착시(지평선 실루엣 단서)는 풍경과 같이 — 방법론 7단계, A/B 로 판단.
3. **폰 실측** — 아래 「검증해야 할 것」.

## 11-05 Claude 직접 구현 (Codex 이후)

| 커밋 | 내용 |
|---|---|
| `e3ea1af` | 산 조명 — Landsat 촬영 해(방위 143.82° · 고도 54.33°)로 사진 지형 음영 지우기(C-correction, Worker 1회), 환경광 = 하늘빛 × 하늘 보임 정도(horizon map 4방위) + 땅 반사, 직사 1.75배, 낮은 해 = 그림자 경계 넓게 · 볕 드는 경사 강조 · 해 쪽 원경 공기 빛, 평지 색 마른 풀빛. 조사 `terrain_lighting_research.md`. 캡처 비교 스크립트 = 워크트리 `_local/light-review/shoot.cjs` |
| (이 커밋) | 눈 고도 = 시드로 1 · 2 · 3km(`1 + floor(seed/3) % 3`) · 실내 보기에서 산 능선 안 그림(도시 띠는 유지) |

남은 것(Claude): 도시 입체(눈을 사진 위에 둔 채 — city3d 반려 이유 참고) · 건물 그림자 · 벽 음영(`terrain_lighting_research.md` 3절) · 폰 실측.

## Codex 마지막 의뢰 — 도시 가상 건물(city3d) 검수 결과: 반려 (11-05)

운영자(11-05): Codex 는 한도 소진으로 이것이 마지막 — 검수만 하고 쓸 만하면 반영, 별로면 여기 기입. 이후 이미지가 아닌 작업은 Claude 가 직접.

- **판정 = 반려**(작업 트리 되돌림, 커밋 안 함). 원본 보존: `codex_city3d_rejected.patch`(d59bfaa 기준 diff) · `codex_city3d_report.md` · `codex_city3d_brief.md` · 캡처 `codex_city3d_night_overview.jpg` · `_day_overview.jpg`.
- 반려 이유(Claude 캡처 검수):
  1. **눈을 사진 동쪽 28km 밖으로 옮겼다** → 1배에서 도시가 지평선의 가는 띠가 되고 화면 아래 절반이 빈 어두운 땅. 3b 에서 운영자가 본 「내려다보는 야경 카펫」이 사라졌다(밤 1배 · 4배가 사실상 빈 화면).
  2. ×30 에서만 건물이 보이는데 안개 속 회색 상자 몇 개 — 「도시처럼」 기준 미달.
  3. 사진(8km)이 작아 눈을 멀리 둔 것이 근본 원인. 눈을 사진 위에 둬야 건물이 발밑에 펼쳐진다 — 그러면 돔 바닥이 사진을 가리는 문제를 따로 풀어야 함.
- 다시 쓸 만한 것(패치 안):
  - 사진 분류에서 건물 후보 추출(길쭉한 회색 = 도로 제외, 주택 1 ~ 3층 · 중층 4 ~ 12층 · 고층 18 ~ 54층, seed 42 에서 4,306개).
  - 산 · 도시 공용 좌표 표 **RGBA16UI → RGB16UI**(산 메모리 27.3 → 22.8MiB 추정, 산 캡처 픽셀 동일이라고 보고).
  - 공간 칸 건너뛰기로 건물 교차 굽기(기본 448 ~ 687ms) · ×30 비용 −44.5%(SwiftShader).
- 다음(Claude 직접): 도시 입체는 눈을 사진 위(지금 위치)에 두는 방식으로 다시 — 조명 작업(`terrain_lighting_research.md`) 뒤에.

## 나중에 넣을 기능 — 천문 이벤트 · 하늘 읽기 (운영자 계획 11-05, 아직 착수 금지)

**착수 조건**: 지금의 기본 구성(위 「이어서 할 일」 · 3단계 의뢰 `codex_stage3_brief.md`)이 끝난 뒤. 이번엔 계획서에만 적는다.

1. **실제 천문 이벤트를 하루 1번 받아 반영** — 대상: 일식 · 월식, 달 위상, 행성(확대하면 그 행성의 위성도 표시), 혜성, ISS 위치(절차가 번거로우면 뺄 수 있음 — 운영자), 유성우, 별자리.
2. **시선을 머무르면 표시** — 시선이 일정 범위를 벗어나지 않고 일정 시간 머무르면, 화면 중심에서 일정 거리 안의 별자리 · 천문 이벤트를 띄운다.
   - 별자리 = 유노 생일 이스터에그의 **YMMT 별자리와 같은 로직**(`bdayscene-yuno.js` `kind === 'constellation'` · `'ymmt-sync'`: 별이 차례로 반짝이며 뜨고(`skyStar` · `ymmtDotIn`) 선이 순서대로 그어진 뒤 네온이 번쩍임, 꼭짓점 · 경로 데이터는 `bdaylogic.js` `ymmtLetters`).
   - 유성우도 같은 장면의 유성 로직을 써서 「내리는 것」을 보여 준다(같은 파일의 유성 줄기 그리기).
   - 표시되면 **HUD 홀로그램 느낌의 이름표**로 무엇인지 알려 준다.
   - **시선에서 가장 가까운 것 하나는 오른쪽 팝업으로 상세 정보** — 사용자가 읽는 콘텐츠가 된다.
3. 정할 것(착수 때 운영자와 확인 — 지금 추측으로 정하지 않음):
   - 「하루 1번 폴링」을 어디서 하나 — 정적 사이트라 방문자 브라우저가 매번 외부 API 를 부르면 호출이 방문자 수만큼 생긴다. 백엔드 일일 잡(KST 06:00 `/daily`)이 받아 data 브랜치 JSON 으로 쓰는 안 · 정해진 날짜 이벤트(일 · 월식 · 유성우)는 표로 넣는 안 등을 비교.
   - 「일정 범위 · 일정 시간 · 일정 거리」 값, 팝업 내용(한국어 설명 출처), 별자리 선 데이터 출처.
   - 출처는 **무료 · 공개 자료만**(유료 서비스 반려 · 공개 자료 원칙). 후보(확인 전): KASI 공공데이터 API(출몰 · 월령), USNO Astronomical Applications API(일 · 월식 · 위상), NASA JPL Horizons(행성 · 위성 · 혜성 위치), NOAA SWPC(오로라), Open Notify · N2YO(ISS), IMO 유성우 연간 일정. 별자리 선 · 별 목록은 공개 데이터(예: Stellarium 계열 · Yale BSC) 이용 조건 확인 필요.
   - 해 · 달 위치 · 위상은 이미 `bgastro.js` 가 직접 계산한다 — API 와 중복되면 어느 쪽을 정본으로 할지.

## 들어간 것 (커밋 순, 11-04 이후)

| 커밋 | 내용 |
|---|---|
| `72f267a` | 방위 보정 — 원천 우선순위(AbsoluteOrientationSensor → `deviceorientationabsolute` → iOS → absolute 표시값), 진북 편각 자동(`js/bgmag.js` WMM2025, 서울 −9.0°), 수동 「방향 맞추기」는 장소 · 시각과 저장, 다른 장소 · 3시간 뒤 자동 폐기. 근거 `stardroid_sensor_study.md` |
| `654fb87` | 눈 = 돔 수평 중심 `[0, 0.24, 0]`(전엔 남쪽 0.42 — 머리 위 돔 꼭대기가 북쪽 29° 에, 동 · 서 경도선 23° 쏠림). 방위 글자 N · E · S · W(바깥 보기, N 빨강) |
| `27aa1a4` | 배경 보기 두 손가락 줌 — 오므리면 뒤로 r(0 ~ 0.6) 물러남, 벌리면 중심. 배경 보기를 닫으면 r 0 |
| `8554ede` | 바닥 원판 가장자리 계단 현상 — 경계 픽셀 면적 섞기 |
| `935acc6` | UFO 기울임 — 세운 폰을 옆으로 기울이면 하늘은 그대로, 무늬만 낮은 쪽으로(`bggyro.gyroTilt`). 방위 글자 두께 · 달 위상 시험 `bgmoon` |
| `5912b52` | 방위 글자 — 더 두껍게, 테두리처럼 보이던 어두운 테 제거, 글자 색 글로우 |
| `c5d16e8` | 달 = NASA LRO 실제 사진(`assets/bg/moon-near.webp`, 출처 README) · 부드러운 명암 경계 · 하늘색에 맞춘 어두운 면 · 크기 시안 `bgsize` |
| `d96f3a0` | 해 큰 블룸(Codex 3차) |
| `cac3bdf` | `bgspeed=0` — 시각 멈춤 |
| `036179d` | **실내 · 바깥 시선 통일** — 둘 다 폰이 실제로 향한 방향(AR). 옛 실내의 35% 따라 돌기 · 흔들면 정면 이동 없앰 |
| `4ad8cc4` | 해 · 달 원반 기본 = **실제 각지름 약 0.53°**(운영자 확정) |
| `b4ce6a2` | 해 · 달 광원 — 공유 소광(Kasten–Young) · 큰 블룸 · 8방향 빛줄기 · 시선 고스트 3개 · 낮은 달 노르스름 + 광륜 2층. 해 고도에도 굴절(달과 통일). 디버그 `bgsunalt/az` · `bgmoonalt/az` · `bgcloud`. 방법론 `codex_luminary_method.md` |
| `84f8fab` | 수평선 아래 풍경 1단계(중간) — `js/bgground.js`, 디버그 `bgground` · `bgseed` · `bgalt`. 방법론 `codex_ground_method.md` |
| ``2b3e1f4`` | `지평선 달 색 · 질감(진한 호박색 · 또렷한 원반 · 광륜 축소) + **망원 줌**(배경 보기 핀치 r 0 에서 더 벌리면 최대 ×30, 광원 노출 · 배율 비례 평활 · 배율 HUD). 의뢰 `codex_moon_tele_brief.md`` |

(11-04 이전 커밋은 `git log --oneline origin/main..origin/feat/bg-dome`)

## 동작 요약 (코드 = 정본, 여기는 지도)

- **시선**: 실내 · 바깥 모두 폰의 실제 방향(나침반 절대 방위 + 실제 기울기), 기준점 화면 정가운데. 센서가 없으면(PC) 옛 실내 구도(위로 28°). 보기를 바꿔도 화면이 돌지 않는다.
- **눈**: 돔 중심 위 0.24. 배경 보기에서 핀치로 r 만큼 뒤로(보는 방향 반대쪽). `r 0 에서 더 벌리면 망원(시야각 축소, 최대 ×30), 오므리면 ×1 → r 증가. 배경 보기를 닫으면 ×1 · r 0.`
- **바깥 보기**(테마 버튼 0.5초 길게 → 팝업, 위치 권한 필수): 시각 · 위치별 하늘(낮 · 노을 · 박명 · 밤 이미지 벌), 해 · 달(실제 크기 + 광원 효과) · 별(항성시) · 방위 글자 · 수평선 아래 풍경.
- **실내 보기**: 분홍 하늘 + 같은 풍경(분홍 팔레트). 천체는 그리지 않는다.
- **흔들기**: 무늬가 섞인다(운영자가 좋아함 — 유지). **기울이기**: 무늬가 낮은 쪽으로 쓸린다.
- **방위 보정**: WMM2025 편각 자동. 「방향 맞추기」(팝업) = 실제 해(밤엔 달)를 겨누고 누르면 남은 오차 저장, 3시간 · 다른 장소면 자동 폐기.
- **성능 장치**: 카메라 정지 시 구름만 초당 6번(풍경 애니메이션 때문에 바뀌었을 수 있음 — 코드 확인), 해상도 배율 1.5 까지, 탭 숨김 · 생일 장면 · 움직임 줄이기에서 정지, WebGL2 실패 시 SVG 장면.

## 지켜야 할 결정 (운영자)

- 경도선은 천정까지(11-04, 「62°에서 멈춤」 · 「천정 아래 작은 원」 반려 — 욱일기 우려).
- 바깥 보기 낮 = 실제 낮 하늘, 분홍 하늘 = 실내 전용. 여명은 맑고 차갑게, 노을은 짙고 따뜻하게.
- 바깥 보기는 위치 권한이 있어야만.
- **디자인은 Codex 에, Claude 는 지시서 · 실제 화면 검증 · 통합**(11-04). Codex 의 「확인했다」는 믿지 말고 직접 캡처(11-05 에도 1차 해가 작은 별 · 낮은 해 · 달이 점이 된 걸 Claude 캡처로 찾아 되돌림).
- 단계마다 검증하고 다음으로. 폰 흔들기 유지. 공식 로고 · 캐릭터 · 그림 금지. 무료 · 빌드 없음 · 외부 라이브러리 금지.
- **눈 위치 = 돔 수평 중심, 높이 0.24**(11-05). **실내 · 바깥 시선 통일**(11-05).
- **해 · 달 원반 = 실제 크기**, 지평선 확대 옵션 없음(11-05). 크기감은 번짐 · 빛줄기 · 지평선 단서로. 지평선 달은 **색 · 질감 + 망원 줌**(11-05, 참고 사진 = 망원 촬영이라는 설명에 동의).
- 해: 「아주 크고 밝은 글로우」, 참고 사진(빛줄기 · 고스트) 느낌, 시선 따라 번짐(11-05).
- 방위 글자: N 빨강 · 나머지 시안, 굵게, 글로우는 글자 색 · 테두리처럼 보이지 않게(11-05).
- 풍경: 2km 상공, 기기별 시드 유지, 실내에도 분홍 톤, **실사에 가깝게**, 부드럽게 먼저(11-05).
- 공개 자료 출처는 **README 「사용한 공개 자료」**(앱 디스클레이머 아님, 11-05).

## 검증해야 할 것 (아직 안 됨)

**11-05 운영자 폰 실측(S23 · 삼성 인터넷, desktop-68v1g6c 서버 `2b3e1f4` 사본)**: 방위 = 카카오맵과 대조해 진북 맞음(기기 한계 안) — **장시간 이동 누적 오차는 미확인**. 부드러움 · 발열 문제없음. 핀치 · 기울기 · 흔들기 조작감 좋음. 해 괜찮음.
달은 너무 작다 → 「사람 눈의 실제 시야각」으로 기기와 무관하게 보정(왜곡 허용), 확대는 육안 × 배율 시야각(망원 시 어두워지며 크레이터 보이는 것은 좋음). 테마 전환 효과(격자 천정부터 반시계 · 사이버펑크 · 빠르게) 요청. iPhone 미확인. → 의뢰 `codex_stage3_brief.md`(달 크기 · 실사 사진 연결 · 테마 효과).

- [ ] **폰(S23 · 삼성 인터넷) 실측 전부** — 11-05 기능들은 PC 흉내(iframe + 가짜 센서 이벤트)로만 확인했다. 특히 방위가 돌릴수록 틀어지던 문제(11-04 운영자 실측)가 `72f267a` 로 사라졌는지: `?bgdebug` 콘솔 `ev.src`(sensor · event · ios · flag) · `ev.sensorErr` · `ev.decl` · `ev.offset`.
- [ ] 폰 GPU 비용 · 발열 · 배터리(광원 +13% 내외, 풍경 +52 ~ 55% 는 SwiftShader 값). 30/60fps 체감.
- [ ] 핀치 줌 · 기울기 · 흔들기가 실제 손가락 · 센서에서 자연스러운지.
- [ ] iPhone Safari(권한 창 · `webkitCompassHeading` 이 자북 기준인지 · WebGL2).
- [ ] 생일 스킨 날 · 테마 전환 · 가로 화면.
- [x] `node src/frontend/js/bgastro.selfcheck.mjs` · `bggyro.selfcheck.mjs` · `bgmag.selfcheck.mjs` 통과(11-05).

## 병합 전 정리 (운영자가 병합을 정하면)

1. `?bgdebug` 진단 코드 정리(`DEBUG` 경고 · `window.__bgdome` · `bgtime/bgspeed/bgmoon/bgsize/bgsunalt…/bgground/bgseed/bgalt` — 남길지 운영자에게).
2. 시안 a · b · c · `bgvirtual.js` · `?bg=classic` 정리 여부를 운영자에게.
3. `docs/SPEC.md` 「배경 장식」 · `docs/VERSION.md` · README 현재 버전 · CLAUDE.md(현재 버전 · 모듈 목록에 bgdomegl · bggyro · bgpeek · bgview · bgsite · bgastro · bgmag · bgground) · `config.js` APP_VERSION — CLAUDE.md 「버전 올릴 때 할 일」.
4. main 을 받아 충돌 확인.
5. 이미지 용량: 바깥 보기 이미지 10장(약 1.4MB) + 달 3.2KB 는 바깥 보기를 고를 때만 받는다.
6. (11-04 기록의 `config.js` 유노 생일 끄기 로컬 수정은 11-05 에 되돌렸다 — 이 PC(`node`)에는 없다. desktop-68v1g6c 에 남아 있는지는 그 PC 에서 `git status` 로 확인.)

## 확인 방법

```bash
cd mewtype-scheduler-worktrees/v4/feat-bg-dome
python scripts/serve_local.py 8102                  # http://localhost:8102/src/frontend/
```

- **폰 센서는 HTTPS 에서만.** Tailscale Serve: `tailscale serve --bg --https=443 http://127.0.0.1:<포트>`(끄기 `tailscale serve reset`). Funnel(인터넷 공개)은 켜지 않는다.
  11-05 에 이 PC(테일넷 이름 `node`)는 `https://node.taila8a0a6.ts.net/` 로 열었다(옛 PC 는 `desktop-68v1g6c`). `serve_local.py` 대기열 128 은 Serve 의 HTTP/2 동시 요청 때문(11-04 사고).
- **폰에 보여 줄 땐 커밋 사본을 따로 띄운다**(11-05 방식): Codex 가 워크트리를 고치는 동안 폰 화면이 깨지지 않게
  `git archive <커밋> src scripts | tar -x -C <세션 임시 폴더>/snap` → 그 폴더에서 `python scripts/serve_local.py 8103` → Serve 를 8103 으로.
  그 사본의 `src/frontend/scenes.html` 에 **장면 고정 목록**(아래)을 넣었다 — 원본은 이 폴더의 `scenes.html`. 쓰려면 사본 `src/frontend/` 에 복사.
- **장면 고정 옵션**(`?bgdebug` 와 함께): `bgtime=ISO`(시각) · `bgspeed=0`(멈춤, 그 밖 = 배속) · `bgsunalt` · `bgsunaz` · `bgmoon=0~1`(위상, 있어야 `bgmoonalt` · `bgmoonaz` 가 듣는다) · `bgsize=now|real|double|window` · `bgcloud=0~1` · `bgground=city|mountain|sea` · `bgseed` · `bgalt=1|2|3`. `scenes.html` = 모든 장면에서 해 · 달을 보이는 자리에 고정한 링크 목록(11-05 운영자 요청 — 오늘 기준으로 그리면 삭이라 달이 안 보였다).
- **PC 에서 폰 흉내**: 390×760 iframe(같은 출처)에 `navigator.geolocation` · `permissions.query` 를 덮어쓰고 `bgview.setBgView("outdoor")`, `deviceorientationabsolute` + `deviceorientation` 이벤트(진북 방위 az 를 보려면 alpha = 360 − (az − 편각), 서울 편각 −9.03° → alpha ≈ 351 − az · beta = 90 + 고도). 세운 채 오른쪽 30° 기울임 = beta 60 · gamma 90. 핀치 = `new Touch` · `TouchEvent` 를 `#bg-peek-catch` 에. 오늘이 생일 스킨 날이면 `data-bday` 가 돔을 멈춘다.
  자동 조작 브라우저는 rAF 가 느려 부드러움은 판단 불가 — 최종 상태만. 캔버스 확대 비교는 `image-rendering: pixelated` + iframe `transform: scale(6)`.

## Codex 협업

- 호출: `codex exec -s workspace-write --skip-git-repo-check -o 결과.md -i 이미지1,이미지2 - < 지시서.md`(상의만 할 땐 `-s read-only`). 전체 경로 `C:\Users\User\AppData\Local\Programs\OpenAI\Codex\bin\codex.exe`.
- 같은 파일(`bgdomegl.js`)을 고치는 Codex 작업은 **한 번에 하나만**. 읽기 전용 상의는 동시에 돌려도 된다.
- Git Bash 의 `/c/...` 경로를 Windows 프로그램에 넘기면 못 찾는다 → `C:/...`.
- Codex 는 파일을 CRLF 로 저장한다(11-05 에도) → 커밋 전 `sed -i 's/\r$//'` 후 `grep -c $'\r'` 로 0 확인.
- 캡처는 워크트리 `_local/`(gitignore). 보고서는 이 폴더로 복사해 둔다(`codex_*_report.md`).

## 이 폴더의 자료

- 11-04 이전: `research.md` · `codex_advice_*` · `codex_d_*` · `dome-*-prompt.txt` · `codex_floor_*` · `codex_sky2~4_*` · `sky-prompts-*` · `codex_grade_*` · `codex_flat_*` · `codex_sun_*` · `codex_sun2_*` · `PRODUCT.md`
- 방위: `stardroid_sensor_study.md`(Stardroid 소스 + 배포판 APK rea 디컴파일 대조)
- 방위 글자: `codex_nsew_*`
- 해 · 달 광원: `codex_sun3_*` · `codex_luminary_consult.md` → `codex_luminary_method.md`(방법론) → `codex_luminary_impl_brief.md` · `_fix1.md` · `_result.md` · `_report.md`
- 풍경: `codex_ground_consult.md` → `codex_ground_method.md`(방법론) → `codex_ground_impl_brief.md` · `_result.md` · `_report.md`(필요 이미지 목록 포함)
- 지평선 달 · 망원: `codex_moon_tele_brief.md` · `_result.md`
- `scenes.html` — 폰 장면 고정 목록(서버 사본에 복사해서 쓴다)
