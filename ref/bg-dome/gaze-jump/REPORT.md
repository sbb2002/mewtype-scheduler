# 시선 튐 조사 보고서 (2026-11-12, Claude)

배경 「UFO 돔」에서 **폰을 방위 방향으로 돌리다가 한 방향을 보고 멈췄는데 시선이 혼자 움직이는 현상**을 폰 실측으로 조사했다.
이 문서는 기록 방법 · 결과 · 웹 조사 · 권하는 해결 방향을 담는다. **코드 수정(해결)은 아직 하지 않았다.**

> ⚠ **충돌 주의** — 같은 문제를 Codex 가 **다른 PC** 에서 따로 작업했고(기록 CSV · 플롯 · 보고서 · 구현 코드),
> 그 결과는 그 PC 의 bg-dome 작업 폴더에 **푸시되지 않은 채** 남아 있다(운영자 2026-11-12 확인. 이 PC 와 원격에서는 찾지 못했다).
> 자세한 주의 사항은 맨 아래 「Codex 작업과의 충돌 주의」.

## 1. 결론

- **튀는 것은 자이로가 아니다. 자력계가 섞인 절대 방위 센서(`AbsoluteOrientationSensor`, 아래 `aos`)의 값이 계단처럼 한 번에 바뀐다.**
  - 「계단」* = 이웃한 두 표본(약 17 ~ 34ms) 사이에 방위가 2° 넘게 바뀌는 것. 이 문서에서만 쓰는 말이다.
- 운영자가 「튐」 버튼을 누른 11번 중 **10번**에서, 누르기 0.3 ~ 0.85초 전에 `aos` 만 2.5 ~ 9.2° 계단으로 뛰었다. 1번 표시만 앞 4초 안에 계단이 없었다.
- 그 순간 자이로 회전 속도는 대부분 1 ~ 6°/초(손떨림 수준)였고, 자력계를 쓰지 않는 상대 방위 센서(`RelativeOrientationSensor`, 아래 `ros`)는 움직이지 않았다.
- 계단은 **폰을 돌리다 멈춘 직후**에 난다. 방향(+/−)은 섞여 있다.
- 지금 코드는 `aos` 값을 0.08초 감쇠만 걸어 화면 시선으로 쓰므로(`bgdomegl.js` `updateView`), 계단이 0.2 ~ 0.3초짜리 「혼자 움직임」으로 보인다.

## 2. 기록 방법

- 실험 브랜치 **`bg-dome-claude-test`**(`97454c2`, `feat/bg-dome` `f9eb7e4` 위 커밋 1개). **main · feat/bg-dome 에 병합하지 않는다**(기록 전용).
  - `src/frontend/js/bggazelog.js` — 기록기. 주소에 `?debug=True` 가 있을 때만 `bgdomegl.js` 가 불러온다.
  - `scripts/serve_gazelog.py` — `serve_local.py` 와 같은 동작 + `POST /__gazelog` 로 받은 줄을 `_local/gazelog/<세션>.csv` 에 이어 쓴다.
- 다시 기록하려면(이 PC `desktop-68v1g6c` 기준):
  1. `git worktree add ../mewtype-scheduler-worktrees/v4/bg-dome-claude-test bg-dome-claude-test` (또는 기존 워크트리에서 브랜치 전환)
  2. `python scripts/serve_gazelog.py 8102` — Tailscale Serve 가 443 → 8102 로 이미 잡혀 있다.
  3. 폰에서 `https://desktop-68v1g6c.taila8a0a6.ts.net/src/frontend/?debug=True`
  4. 화면이 혼자 움직였다고 느끼면 오른쪽 아래 빨간 **「튐」** 버튼. 상태 줄의 `REC` 숫자가 늘면 PC 로 넘어오는 것.
- 기기: 운영자 폰, 삼성 인터넷 30(User-Agent 의 Chrome 143). 방위 원천은 줄곧 `sensor`(= `aos`). 표본은 `aos` · `ros` 약 36Hz, 자이로 · 화면 약 44Hz.
- 자력계 원값(`Magnetometer`)은 브라우저가 제공하지 않았다(`mag,none`).

### CSV 형식

한 줄 = `t(ms, performance.now), kind, 값들`.

| kind | 값 |
|---|---|
| `aos` | 절대 방위 센서(자력계 포함): 방위°, 고도°, 쿼터니언 x, y, z, w |
| `ros` | 상대 방위 센서(자력계 없음): 방위°(기준 임의 — 변화량만 비교), 고도°, 쿼터니언 |
| `doa` | `deviceorientationabsolute`: alpha, beta, gamma |
| `do` | `deviceorientation`: alpha, beta, gamma, absolute(1/0) |
| `dm` | `devicemotion`: 회전 속도 alpha, beta, gamma(°/초), 중력 포함 가속도 x, y, z |
| `view` | 프레임마다: 앱이 쓰는 방위°(`gyroAbs`, 편각 포함), 고도°, 화면에 그린 방위°, 고도°, 원천, 배율 |
| `mark` | 「튐」 버튼을 누른 시각: 누른 횟수 |
| `info` | 시작 정보(시각 · User-Agent) · 센서 오류 |

## 3. 자료

| 파일 | 내용 |
|---|---|
| `data/20261112054143_g4wz.csv` | **표시 11개가 있는 기록**(약 159초, 중간에 40초 공백 — 탭 전환으로 추정, 확인 안 함) |
| `data/20261112054135_0s2d.csv` | 같은 시각에 열려 있던 다른 탭의 기록(표시 없음). 계단 수는 같다(17회) |
| `plot_marks_g4wz.png` | 표시 구간 그래프 — 위: `aos` · `ros` · 화면 방위 / 가운데: `aos − ros`(자력계 보정량) / 아래: 자이로 속도. 빨간 점선 = 표시 |
| `plot_0s2d.png` | 다른 탭 기록의 같은 그래프 |
| `result_steps_g4wz.txt` | 계단 목록 · 표시별 직전 4초 안의 계단 |
| `result_series_g4wz.txt` | 표시 3 · 5 · 9 앞뒤의 0.1초 간격 값 |
| `analyze_steps_plot.py <csv> <png>` | 계단 찾기 + 그래프(numpy · matplotlib) |
| `analyze_series.py <csv> <표시 번호…>` | 표시 앞 3.5초 ~ 뒤 0.5초 값 나열 |
| `analyze_marks.py <csv>` | 표시별 앞 5초 요약(첫 분석 — 창이 넓어 회전이 섞인다. 참고용) |

## 4. 결과

### 표시별

| 표시 | 누르기 전 계단 | 계단 크기 | 그 순간 자이로 속도 |
|---|---|---|---|
| 1 | 없음(4초 안, 2° 기준) | – | – |
| 2 | 0.57초 전 | −5.4° | 6.2°/초 |
| 3 | 0.85초 전 | −4.9°(두 표본에 걸침) | 약 3°/초 |
| 4 | 0.73초 전 | +9.2° | 11.0°/초 |
| 5 | 0.53초 전 | +8.6° | 2.1°/초 |
| 6 | 0.52초 전 | −6.0° | 1.8°/초 |
| 7 | 0.43초 전 | −2.6° | 1.2°/초 |
| 8 | 0.54초 전 | −5.4° | 4.5°/초 |
| 9 | 0.54 ~ 0.27초 전 | +2.6°, +4.1°, −2.0° | 약 2°/초 |
| 10 | 0.58초 전 | −3.4° | 6.1°/초 |
| 11 | 0.48초 전 | −7.6° | 1.1°/초 |

### 전체

- 기록 전체에서 2° 넘는 계단은 17회, 그중 12회가 폰이 멈춘 상태(자이로 10°/초 미만)였다.
- 가장 큰 계단은 20초 지점의 −27.9°(폰을 돌리던 중, 자이로 64.5°/초).
- 계단 사이에는 `aos` 와 `ros` 가 거의 같이 움직인다(표시 5 앞 회전 구간에서 차이 ±1.4° 이내).
- 예: 표시 5 — `ros` 는 −16.7° 에 그대로, `aos` 만 −16.3° → −7.6°. 화면 방위는 0.3초에 걸쳐 따라갔다.

### 확인하지 못한 것

- 계단의 원인이 **기기 안 융합 알고리즘의 자력계 보정**이라는 것은 「`ros` · 자이로는 멈춰 있고 `aos` 만 움직였다」에서 나온 추론이다. 자력계 원값을 못 받아 직접 확인하지는 못했다.
- 기록 장소는 한 곳(실내로 추정 — 운영자에게 확인 안 함). 야외 · 다른 장소에서 계단이 줄어드는지 모른다.
- 다른 기기 · iPhone 은 기록하지 않았다.
- 1번 표시의 원인은 못 찾았다(계단 기준 2° 아래의 움직임이거나 잘못 누른 것일 수 있다 — 미확인).

## 5. 웹 조사 — 다른 앱 · 플랫폼은 어떻게 하나

| 방법 | 쓰는 곳 | 내용 |
|---|---|---|
| 자력계를 뺀 센서로 움직임 처리 | VR · 게임(Android `GAME_ROTATION_VECTOR`), Chrome 의 `deviceorientation` 기본값 | 자기장 변화에 영향받지 않아 튐이 없다. 대신 방위가 천천히 흐른다 |
| 나침반은 느리게만 보정(상보 필터*) | Mahony · Madgwick 계열 | 방위는 자이로 적분으로 움직이고, 나침반과의 차이는 작은 비율(예: 자이로 0.98)로만 당긴다 |
| 자기 교란 중엔 나침반 무시 | Reckon(공개 저장소), 9축 IMU 사례 | 자기장 세기 · 방위가 갑자기 변하면 자이로만 믿고, 안정되면 시간 상수를 두고 다시 섞는다 |
| 운영체제 융합에 맡김 | Google 지도(Fused Orientation Provider) | 자력계 · 자이로 치우침 보정, 자기 교란 대응을 넣었다고만 밝힘. 알고리즘 비공개 · 웹에서는 못 씀 |
| 출력 쿼터니언에 One Euro 필터 | Sky Map(Stardroid) | 손떨림용. 느린 움직임은 세게, 빠른 움직임은 약하게 거른다(`../stardroid_sensor_study.md`) |
| 정확도 낮으면 8자 보정 안내 | Sky Map, 나침반 앱 | 필터로 못 고치는 왜곡은 사용자 재보정으로 넘긴다 |

\* 상보 필터 = 빠른 변화는 한 센서(자이로), 느린 기준은 다른 센서(나침반)에서 받아 합치는 방식.

근거로 확인한 것:
- W3C 명세: `AbsoluteOrientationSensor` = 가속도계 + 자이로 + 자력계, `RelativeOrientationSensor` = 가속도계 + 자이로.
- 다른 기기 사례: 회전 반대 방향의 작은 튐이 자력계 갱신 때 생긴다는 보고(Nordic Thingy52), 주변 금속이 절대 방위를 망친다는 Chrome 개발진 글.
- 삼성 기기: S22 · A73 방위 무작위 보고, S22 Ultra 회전 벡터 차이 보고. **S23 보고는 찾지 못했다.**

출처:
- https://www.w3.org/TR/2019/CR-orientation-sensor-20191212
- https://developer.chrome.com/blog/device-orientation-changes
- https://groups.google.com/a/chromium.org/g/blink-dev/c/lT_-2CiHOf4/m/UEpwwtdvAgAJ
- https://android-developers.googleblog.com/2024/03/introducing-fused-orientation-provider-api.html
- https://devzone.nordicsemi.com/f/nordic-q-a/43769/nordic-thingy52-orientation-tracking
- https://github.com/ri12oe/Reckon/pull/3
- https://nxttime.wordpress.com/2012/01/23/9dof-imu-my-first-results/
- https://www.steppeschool.com/blog/attitude-estimation-rotation-matrices-quaternions-sensor-fusion
- https://developers.meta.com/vr/blog/magnetometer/
- https://github.com/firofame/react-native-compass-heading/issues/66
- https://forum.developer.samsung.com/t/can-s22-ultra-be-a-problem-in-using-android-type-rotation-vector/26674
- https://github.com/sky-map-team/stardroid/issues/188
- https://github.com/dfpc-coe/CloudTAK/issues/1901

## 6. 권하는 해결 방향 (미구현 — 운영자 결정 대기)

1. 화면 방위는 **상대 센서(`ros`)** 로 움직인다.
2. 절대 센서와의 차이(보정량 = `aos − ros`)만 따로 **느리게** 따라간다(예: 초당 1 ~ 2° 제한 또는 시간 상수 수 초). 계단이 와도 화면은 천천히만 맞춰진다.
3. 변형: 폰이 멈춰 있을 때(자이로 속도가 낮을 때)는 보정을 멈추거나 더 늦추고, 돌리는 동안 몰아서 맞춘다. 멈춘 화면이 혼자 움직이는 일이 없어진다. 대신 오차가 다음 움직임까지 남는다.
4. 차이가 갑자기 크게 변하면(계단) 교란으로 보고 잠시 보정을 멈추는 문을 둘 수 있다.

적응형 필터(One Euro)만 쓰는 안은 이 증상에 한계가 있다 — 계단은 실제 회전과 구별되지 않는 값 변화라서, 필터는 늦출 뿐 결국 9° 를 다 따라가고, 세게 걸면 실제로 돌릴 때 화면이 늦는다.

구현할 때 볼 곳: `bggyro.js`(`startSensor` · `takeAbsolute` · `gyroAbs`) · `bgdomegl.js` `updateView`. `ros` 를 못 쓰는 기기(iOS 등)는 지금 방식 그대로 두는 대체 경로가 필요하다.
고친 뒤에는 같은 기록기로 다시 기록해 `view`(화면 방위) 계단이 사라졌는지 전후를 비교한다.

## 7. Codex 작업과의 충돌 주의

운영자 확인(2026-11-12): Codex 가 **다른 PC** 에서 같은 기능(시선 튐 기록 · 보정)을 구현했고, 그 **코드 · 데이터(CSV · 플롯) · 보고서가 그 PC 의 bg-dome 작업 폴더에 푸시되지 않은 채** 있다.
이 PC · 원격 저장소 · 이 PC 의 Codex 세션 기록에서는 그 결과물을 찾지 못했으므로, **파일 이름 · 구현 방식은 여기서 알 수 없다**.

충돌을 피하려고 이번 작업은 이렇게 떼어 두었다.
- 코드는 `feat/bg-dome` 에 넣지 않고 **별도 브랜치 `bg-dome-claude-test`** 에만 있다. `feat/bg-dome`(`f9eb7e4`)은 건드리지 않았다.
- 자료는 devpapers **`ref/bg-dome/gaze-jump/`** 한 폴더에만 넣었다. `ref/bg-dome/HANDOFF.md` 는 맨 위에 한 절만 더했다.

그 PC 에서 푸시할 때:
1. 먼저 `git fetch origin` 으로 `devpapers` 를 받아 `ref/bg-dome/HANDOFF.md` 의 「11-12」 절과 겹치는지 본다(같은 파일 맨 위를 양쪽에서 고쳤으면 충돌한다 — 두 절을 모두 남긴다).
2. Codex 자료는 이 폴더와 섞지 말고 **다른 폴더 이름**(예: `ref/bg-dome/gaze-jump-codex/`)에 넣는다. 같은 이름의 파일을 덮어쓰지 않는다.
3. Codex 구현 코드가 `feat/bg-dome` 작업 폴더에 있으면 `feat/bg-dome` 에 바로 푸시하지 말고 별도 브랜치로 올린다 — 이쪽 기록기와 같은 곳(`bgdomegl.js` 의 확인용 블록 · `bggyro.js`)을 고쳤을 가능성이 높다(추정, 확인 안 함).
4. 두 결과(Codex 의 기록 · 필터 안과 이 보고서의 원천 분리 안)는 **운영자가 비교해서 하나를 고른 뒤** `feat/bg-dome` 에 넣는다. 그 전에 어느 쪽도 `feat/bg-dome` 에 합치지 않는다.
