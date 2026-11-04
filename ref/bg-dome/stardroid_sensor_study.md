# Stardroid(Sky Map) 센서 · 방위 보정 조사 — 바깥 보기 해 · 달 위치 어긋남 대응 (2026-11-04)

계기: 운영자가 S23 · 삼성 인터넷으로 바깥 보기를 약 40분 써 봄. 반응성 · 다른 기능과의 충돌은 문제없었음.
그러나 해 · 달 자리가 안 맞았고, **많이 돌릴수록 오차가 커져** 나중엔 해가 지지 않는 쪽에 해가 지는 것처럼 보였다.
운영자 요청: 별자리 앱이 쓰는 보정 방법을 먼저 조사하고, 수동 「방향 맞추기」 없이 **자동으로** 방향을 맞추기.

조사 대상: `github.com/sky-map-team/stardroid` master `0d957f1`(2026-11-04 커밋). 옛 Google Sky Map 을 공개한 것이고 GPL-3.0 이다.
v2(Kotlin 멀티플랫폼, 지금 개발 줄기)를 위주로 보고 v1 은 참고만 했다. **코드는 읽기만 했고 돌려 보지 않았다.**
GPL 이라 코드를 옮겨 오지 않고 방법만 참고한다.

## 1. Stardroid 가 실제로 하는 것 (코드 · 문서로 확인한 것만)

| # | 단계 | 내용 | 근거 파일(v2 기준) |
|---|---|---|---|
| 1 | 자세 원천 | `TYPE_ROTATION_VECTOR`(자이로 + 가속도계 + 자력계를 OS 가 융합) 하나를 우선 쓴다. 없으면 가속도계 + 자력계로 직접 계산(중력으로 「위」, 자력 벡터에서 위 성분을 빼 「북」). 자력계를 빼는 `GAME_ROTATION_VECTOR` 는 **쓰지 않는다**. | `app/.../sensors/SensorOrientationSource.kt` (`route()`) |
| 2 | 진북 보정(편각) | `GeomagneticField(위도, 경도, 고도 0, 지금)`.declination 으로 **자동** 계산. 설정으로 끌 수만 있다. | `app/.../sensors/GeomagneticDeclinationSource.kt` |
| 3 | 보정을 거는 자리 | 「편각 + 사용자 방위 보정」을 더해 **하늘 쪽 좌표계(local frame)를 천정 축으로 돌린다**. 폰 쪽 값을 고치지 않는다. 하늘 좌표계는 위치 · 시각이 바뀔 때만 다시 계산하면 되기 때문. | `shared/viewmodels/.../MapViewModel.kt` (`declinationFor`, `refreshLocalFrame`) · v1 `docs/design/sensors.md` 「Magnetic correction」 |
| 4 | 사용자 정렬 | AR 화면에서 손가락으로 끌어 「방위 보정 + 고도 보정」 한 쌍을 맞춘다. 기기에 영구 저장(`sensorAzimuthAdjustmentDeg` · `sensorAltitudeAdjustmentDeg`)하고, 되돌리기 · 초기화가 있다. 고도 보정은 화면 오른쪽 축으로 돈다. **해 · 달을 써서 자동으로 맞추는 기능은 없다.** | `MapViewModel.kt` (`resolveSensorCamera`, 드래그 처리) · `docs/design/camera-ar-mode.md` Part 2 |
| 5 | 문서에 적어 둔 한계 | 자력계 오차는 전부 「천정 축 방위 오차」로만 나타난다(기울기는 중력이 잡음). 그런데 폰 자체 자석(hard-iron)과 주변 철 때문에 생기는 왜곡(soft-iron)은 **보는 방향에 따라 사인 곡선처럼 달라진다**. 그래서 고정 보정값은 맞춘 방향 근처에서만 맞는다. 고치려면 8자 재보정이 필요하다. | `docs/design/sensor-correction-model.md` |
| 6 | 정확도 감시 | 자력계 정확도가 MEDIUM 아래(LOW · UNRELIABLE)로 떨어지면 8자 보정 화면을 띄운다. 최대 3분에 한 번이고, 마지막 안내 시각은 저장해 앱을 다시 켜도 다시 조르지 않는다. | `shared/model/.../sensors/SensorAccuracyMonitor.kt` |
| 7 | 흔들림 거르기 | 최종 자세 쿼터니언* 하나에 One Euro 필터**를 건다. 실제 경과 시간 기준이고, 화면 회전을 반영하기 전에 거른다. | `shared/model/.../sensors/OneEuroQuaternionSmoother.kt` |
| 8 | 사용자 안내 | 「보정과 정확도는 다르다」. 보정해도 철근 · 콘크리트는 5–30°, 자석 · RFID 차단 케이스는 늘 오차를 만든다. 순서: 넓은 곳 → 8자 → 케이스 빼기. | 저장소 루트 `troubleshooting.md` |

\* 쿼터니언 = 3D 회전을 각도 셋(α · β · γ) 대신 숫자 넷으로 나타내는 방식. 폰을 세울 때 생기는 각도 꼬임이 없다
\*\* One Euro 필터 = 천천히 움직일 땐 많이, 빨리 움직일 땐 적게 거르는 떨림 제거 필터(Casiez 외, CHI 2012)

요점: Stardroid 에서 **자동인 것은 ① 융합 센서의 자체 보정 ② WMM 편각 둘뿐**이다. 주변 환경 때문에 생기는 수십 도 오차는 자동으로 못 없애고, 사람이 맞추거나 8자로 다시 보정하게 한다.

## 2. 웹에서 쓸 수 있는 같은 재료

| Stardroid | 웹(안드로이드 크롬 계열) | 확인 상태 |
|---|---|---|
| `TYPE_ROTATION_VECTOR` | `deviceorientationabsolute` 이벤트 · `AbsoluteOrientationSensor`(쿼터니언) — Chromium 은 둘 다 ROTATION_VECTOR 를 먼저 쓴다 | Chromium `services/device/generic_sensor` 문서 |
| (안 씀) `GAME_ROTATION_VECTOR` | 보통 `deviceorientation`(Chrome 50 부터 상대값) — **자력계가 없어 돌수록 오차가 쌓인다** | 같음 |
| 정확도(SENSOR_STATUS) | 웹에 노출 안 됨 | — |
| `GeomagneticField` | 웹 API 없음. WMM 계수를 넣어 직접 계산해야 함 | — |
| 삼성 인터넷 | MDN 호환 표에서 `AbsoluteOrientationSensor` 는 「Chrome 과 같음(mirror)」으로 나옴. `deviceorientationabsolute` 지원은 **확인 못 함**. 아주 옛 버전(5.0 전)은 `deviceorientation` 이 절대값이었다 | 실기기 확인 필요 |

## 3. 우리 코드(`feat/bg-dome` `ea58f8d`)와 대조

- 같은 점: 바깥 보기는 절대 방위만 쓰고(`bggyro.gyroAbs`), 보정은 천정 축 회전 하나(`headingOffset`)로 건다. Stardroid 3 · 4번과 같은 구조다.
- 다른 점:
  1. 방위 원천: `deviceorientationabsolute` 의 오일러 각을 받거나, `deviceorientation` 이 `absolute === true` 면 그걸 쓴다. 쿼터니언(`AbsoluteOrientationSensor`)은 안 쓴다.
     삼성 인터넷에서 실제로 어느 쪽이 값을 주는지는 **모른다** — `?bgdebug` 의 `gyroDebug` 카운터(orient · absolute · absFlag)로 확인할 수 있다.
  2. 편각: 따로 계산하지 않는다. 사용자 보정값에 섞여 들어간다.
  3. 보정값 수명: `localStorage "bgheading"` 에 영구 저장된다. **새로고침으로는 지워지지 않는다**(시크릿 모드 · 저장소 차단 제외). 어디서 · 언제 맞췄는지는 같이 저장하지 않는다 → 실내에서 맞춘 40 ~ 50° 가 다른 장소에서도 그대로 걸릴 수 있다.
  4. 정확도 감시 · 8자 안내 없음. 고도 보정 없음.

## 4. 이번 증상(돌릴수록 오차 증가)의 원인 후보 — 아직 확인 안 됨

1. **자력계가 섞이지 않은 원천이 쓰이고 있다** — 오차가 시간 · 회전에 따라 쌓이는 건 자이로만 누적할 때의 전형 증상이다(척도 오차 1% × 10바퀴 ≈ 36°).
   삼성 인터넷이 `deviceorientationabsolute` 를 안 주고 `deviceorientation` 에 `absolute: true` 를 붙여 주는데 그 값이 실제로는 상대값이라면, 지금 코드가 그대로 받아 쓴다. 실측으로 가려야 한다.
2. **실내 자기장 왜곡 + 폰 자동 자력계 보정이 엉뚱하게 수렴** — 이 경우 오차는 쌓이기보다 방향에 따라 출렁인다(1 장 5번). 이전 실측에서 「해와 5° 이내」(HANDOFF) 와 「40 ~ 50°」 가 둘 다 나온 것은 장소 · 방향에 따라 오차가 다른 이 성질과 맞는다.
3. **이전 보정값이 남아 있었다** — 3 장 3번.

참고: HANDOFF 에는 운영자 폰이 「안드로이드 10 · 삼성 인터넷 30」 으로 적혀 있다. S23 은 안드로이드 13 이상으로 나온 기종이라 **기록이 맞는지 확인 필요**.

## 5. 「자동 방향 맞추기」로 할 수 있는 것 · 없는 것

| 안 | 자동? | 없애는 오차 | 비고 |
|---|---|---|---|
| A. 자력계가 섞인 원천 보장 — `AbsoluteOrientationSensor`(쿼터니언) 우선, `deviceorientationabsolute` 다음, `absolute` 플래그만 붙은 값은 의심 | 자동 | 누적 오차(후보 1) | Stardroid 1번과 같음. 실측으로 원인이 1번이면 핵심 |
| B. WMM 편각 자동 계산 | 자동 | 자북 ↔ 진북 차이(한국 수 도 — 값은 계산해 확인) | Stardroid 2번과 같음. 계수표를 프론트에 넣어야 함 |
| C. 수동 보정값에 장소 · 시각을 같이 저장하고, 멀리 가거나 오래되면 버림 | 자동(버리기) | 옛 보정이 남는 문제(후보 3) | Stardroid 와 다름(거긴 영구 저장) — 우리 쪽 판단 필요 |
| D. 흔들기 · 회전을 보고 8자 보정 안내 | 반자동 | hard/soft-iron 일부 | 웹은 정확도 신호가 없어 판단 근거를 따로 만들어야 함 |
| E. 카메라로 실제 해를 찾아 자동 정렬 | 자동 | 환경 오차 전부(맞춘 방향 근처) | **Stardroid 에 없음**. 카메라 권한 · 밤엔 달만 · 설계를 처음부터 해야 함 |

주변 철근 · 전자기기 때문에 생기는 수십 도 오차는 **외부 기준(실제 해 · 달) 없이는 자동으로 없앨 수 없다** — Stardroid 도 같은 결론이다.

## 6. 배포판 APK 대조 — rea 로 디컴파일 (2026-11-04)

공개 소스와 실제 배포된 앱이 같은 방식으로 도는지 확인했다.

- 대상: GitHub 릴리스 `v2.2.0` 의 `app-gms-release.apk`(Play 스토어용 gms 빌드, 2026-10-22, SHA-256 `93b79815…61772`).
  **Play 스토어가 실제로 내려 주는 APK 와 같은 바이트인지는 확인 못 했다** — Play 는 AAB 를 구글 키로 다시 서명해 쪼개 내려 주므로 폰에서 직접 뽑아야 대조된다.
- 도구: rea 6.5.0 + JADX 엔진 `jadx-headless-mcp 0.7.1`(SHA-256 이 rea 가 감사해 둔 값 `6e5eacf5…ff75` 와 일치). APK 는 실행하지 않았다(정적 분석).
- R8 난독화로 클래스 이름이 지워져 있어, 대상 클래스는 직접 만든 dex 스캐너로 찾았다(특정 문자열 · Android API 를 부르는 메서드 찾기 — rea 가 아님). 디컴파일은 rea `inspect-android-method` 로 했다.

| 배포판 클래스 | 대응하는 소스 | 확인한 것 |
|---|---|---|
| `t9.y` 생성자 | `SensorOrientationSource` | `getDefaultSensor(11)` = ROTATION_VECTOR · `(1)` 가속도계 · `(2)` 자력계. **GAME_ROTATION_VECTOR(15) 는 안 부른다** |
| `t9.x` · `t9.v` `onSensorChanged` | 같은 파일의 fused 경로(지도용 · 진단용) | 회전 벡터 → 필터 → `getRotationMatrixFromVector` → 화면 회전 반영 |
| `t9.d.b` | `OneEuroQuaternionSmoother.update` | 쿼터니언 One Euro. 속도 미분 차단 주파수 1Hz(`0.159 = 1/2π`), 차단 = 최소값 + β × (속도 − 문턱). 샘플 간격이 1초 넘으면 다시 시작 |
| `ga.r3.o` | `MapViewModel` 의 local frame 갱신 | 보정이 켜져 있으면 `GeomagneticField(위도, 경도, 0, 시각).getDeclination()` + 사용자 방위 보정. **편각은 같은 위치 · 하루 안이면 캐시** |
| `ba.y.v` | 진단 화면 값 | 편각 + 사용자 보정을 따로 보여 줌 |
| `u9.u` 정적 초기화 | `DataStoreSettings` 키 | `sensor_azimuth_adjustment` · `sensor_altitude_adjustment` · `dont_show_calibration_dialog` · `last_calibration_warning` |
| `t9.n.a` | `SensorManagerStatusSource` | 정확도 감시용 센서 1 · 2 · 4 · 11 · 5 |

- 결론: 배포판의 센서 경로는 공개 소스와 같다. **소스에 없는 자동 정렬 같은 숨은 기능은 이 경로에서 보이지 않았다.**
  단, 찾은 범위는 위 문자열 · API 를 쓰는 메서드뿐이다 — 다른 경로로 숨긴 코드까지 없다는 증명은 아니다.
- 소스(`master 0d957f1`)와 APK(`v2.2.0`) 사이 63 커밋에서 센서 쪽 바뀐 파일은 둘(`GeomagneticDeclinationSource.kt` · `SensorManagerStatusSource.kt`)이다. 둘 다 파일 안 선언을 옮긴 것뿐이라 동작은 같다.

## 출처

- Stardroid: `stardroid-v2/docs/design/sensor-correction-model.md` · `camera-ar-mode.md`, `stardroid-v1/docs/design/sensors.md`, `stardroid-v1/specs/sensors/orientation.md`, `troubleshooting.md`, 위 표의 Kotlin 파일들
- W3C Orientation Sensor: https://www.w3.org/TR/2024/WD-orientation-sensor-20240110
- Chromium generic_sensor: https://chromium.googlesource.com/chromium/src/+/8f4679d70f32a2f7d5c02349b7583e5199120f28/services/device/generic_sensor
- MDN browser-compat-data `AbsoluteOrientationSensor`: https://chromium.googlesource.com/external/github.com/mdn/browser-compat-data/+/73d346309ee9d8be7e32fda8ff574d4c79dd4c51/api/AbsoluteOrientationSensor.json
- DeviceOrientationEvent 호환 표(옛 삼성 인터넷 절대값): https://docs.w3cub.com/dom/deviceorientationevent
