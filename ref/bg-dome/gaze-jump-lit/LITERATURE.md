# 시선 튐 — 참고문헌 조사 종합 (2026-11-13, Claude)

같은 문제를 Claude · Codex · agy(Antigravity) 세 쪽이 따로 조사했고, 이 문서는 그 결과를 **원문 확인 수준으로 걸러** 합친 것이다.
현상 · 실측은 `../gaze-jump/REPORT.md`, 이 조사로 고른 해결 방법은 `METHOD.md`.

- 조사 요청서 = `raw/REQUEST.md`(운영자 지시로 Claude 가 herdr 로 보냄)
- Codex 원본 = `raw/codex.md`(출처 20개, 확인 수준을 출처마다 표시 — 대체로 정확)
- agy 원본 = `raw/agy.md` — **인용문 다수가 원문에 없음.** 아래 「agy 보고서 검증 결과」를 먼저 볼 것

## 0. 용어

- **계단*** = 이웃한 두 표본 사이에 방위가 2° 넘게 바뀌는 것(REPORT.md 와 같은 뜻)
- **보정량*** = 절대 방위 − 상대 방위(방위 성분만). 자력계가 상대 방위에 더해 주는 몫
- **상보 필터*** = 빠른 변화는 한 센서(자이로 · 상대 방위)에서, 느린 기준은 다른 센서(자력계 · 절대 방위)에서 받아 합치는 방식

## 1. 결론

1. **현상 자체는 알려진 문제다.** 브라우저(Chrome) · OS(Android) 문서가 자력계 기반 절대 방위가 기기가 안 움직여도 바뀌거나 교정 때 점프할 수 있다고 적는다(S01 · S03 · S04).
   계단은 브라우저가 아니라 **OS · 제조사 센서 융합 단계**에서 생긴다 — Chromium 은 Android 의 융합 결과를 그대로 넘긴다(S07).
2. **해법은 1990년대 VR 헤드 트래커에서 이미 정리됐다** — 「기준 센서와의 차이는 **멈췄을 때 재고**, 화면에는 **나눠서 · 천천히** 반영한다」(Foxlin 특허 S21 · AeroSense 98 S22).
   Oculus(S11)는 「사용자가 못 느낄 만큼 작은 이득」의 상보 필터로 같은 원칙을 쓴다.
3. **「움직일 때는 화면의 작은 어긋남을 덜 알아챈다」는 지각 연구가 있다**(S16 · S18). 단, 수치는 HMD · 머리 회전 실험값이라 손에 든 폰 화면에 그대로 옮길 수 없다(저자 명시).
4. **정지 중 몇 °/초까지 보정해도 안 보이는지는 확인된 수치가 없다.** agy 가 낸 「정지 시 1°/초」(Razzaque)는 원문을 열지 못했다(404). 우리 화면에서 직접 정해야 한다.
5. 자기 교란을 감지해 자력계를 끊는 최신 방법(VQF S12 · Fusion S14 · Fan 2017 S23)은 **자력계 원값이 필요**하다. 브라우저가 원값을 주지 않으므로 그대로는 못 쓰고, 「차단 · 복귀」 구조만 참고한다.

## 2. 신뢰 출처 (원문 확인)

확인 = 누가 어떻게 열었는지. 「Claude 원문」 = Claude 가 PDF 본문을 직접 추출해 검색, 「확인 에이전트」 = Claude 가 띄운 웹 읽기 에이전트가 페이지를 열어 문구를 대조, 「Codex 원문」 = Codex 가 직접 열었다고 표시한 것(Claude 재확인 안 함).

### 해법 — 보정을 화면에 반영하는 방식

| # | 출처 | 확인 | 우리 문제와 관련된 내용 |
|---|---|---|---|
| S21 | Eric M. Foxlin, 특허 **US5645077** 「Inertial orientation tracker apparatus having automatic drift compensation …」, MIT, 1997-07-08 등록 · https://patents.google.com/patent/US5645077A/en | 확인 에이전트(앞 4만 자 원문 · 다음 10만 자 요약 · 나머지 22만 자 안 읽음) | 원문: 「the compensating angular position sensors and compass are used periodically, at times when the user's head is not moving」, 「the drift is removed from the output gradually, rather then all at once」, 「a fractional error correction signal is used, rather than the entire error correction signal, to prevent a 'jump' or 'lurch' apparent to the user」. 보정 속도 「nδ °/sec 선형」은 요약에서만 봄 — 미확인 |
| S22 | Foxlin · Harrington · Altshuler (InterSense), 「Miniature 6-DOF inertial system for tracking HMDs」, SPIE 3362 AeroSense 98, 1998 · https://www.macs.hw.ac.uk/~ruth/year4VEs/Resources/AeroSense98.pdf | Claude 원문 | 원문: 「The inclinometer and compass were ignored during head motion, and consulted during natural head-motion pauses」. 지각 기준 후처리 필터(PPF): 「Since the human observer is more sensitive to jitter and drift when still or moving slowly, the PPF uses adaptive filtering to preferentially suppress these effects as the head slows down」, 「the PPF only filters the corrections to orientation made by the error estimator, and not the orientation signals themselves」 → 「no additional latency」 |
| S11 | LaValle · Yershova · Katsev · Antonov (Oculus VR), 「Head Tracking for the Oculus Rift」, ICRA 2014, DOI 10.1109/ICRA.2014.6906608 · https://msl.cs.illinois.edu/~lavalle/papers/LavYerKatAnt14.pdf | Claude 원문 · Codex 원문 | 기울기 보정 식 (10), 방위 보정 식 (12) = 작은 이득 α₂ 로 매 반복 조금씩. 원문: 「The parameter α should be large enough to correct all drift, but small enough so that the corrections are imperceptible to the user」. 움직임에 따라 보정을 막는 내용은 없음(계속 보정) |
| S11b | Steve LaValle, 「Help! My Cockpit Is Drifting Away」, Oculus 블로그, 2013-12-29 · https://developers.meta.com/vr/blog/magnetometer/ | 확인 에이전트 | 원문: 「A better idea is to gradually apply the corrective rotations」. 이득은 「tuned based on perceptual experiments」 — 숫자 없음 |
| US5991085 | Rallison 외 (i-O Display Systems), 특허 US5991085, 1999 · https://patents.google.com/patent/US5991085A/en | **요약만**(확인 에이전트가 모델 요약으로 읽음 — 문장 그대로인지 미확인) | 요약: 정지 상태에서 방위 보정값을 계산 · 저장하고, 움직이는 상태일 때 더한다. 보정 한도 약 5~25° |
| S12 · S13 | Laidig · Seel, 「VQF: Highly Accurate IMU Orientation Estimation with Bias Estimation and Magnetic Disturbance Rejection」, Information Fusion 91 (2023), DOI 10.1016/j.inffus.2022.10.014 · 구현 https://github.com/dlaidig/vqf (MIT) | Codex 원문 | 6축 자세와 자력계 방위 오프셋을 분리. 교란 시 보정 차단 · 장기 교란 뒤 복귀. 기본 시간 상수 `tauMag = 9 s`. 새 자기장 기준은 충분히 돌릴 때(기본 20°/초 이상)만 받아들임 — **화면 보정을 움직일 때만 하라는 근거는 아님**(Codex 주의) |
| S14 | x-io Technologies (Madgwick), Fusion AHRS · https://github.com/xioTechnologies/Fusion | Codex 원문 | 측정 방위와 추정 방위의 차이가 문턱(예시 10°)을 넘으면 자력계를 거부, 오래 거부되면 복귀 |
| US8531180 | Piemonte 외 (Apple), 특허 US8531180B2 「Determining heading using magnetometer data and angular rate data」, 2013-09-10 등록 · https://patents.google.com/patent/US8531180B2/en | 확인 에이전트(앞 4만 자 원문, 나머지 요약) | 자력계 값의 분산이 문턱을 넘으면 자이로로만 방위를 이어 가는 「coasting mode」로, 정확해지면 자력계로 복귀 |
| S23 | Fan · Li · Wang · Liu, 「An Adaptive Orientation Estimation Method for Magnetic and Inertial Sensors in the Presence of Magnetic Disturbances」, Sensors 17(5):1161, 2017 · https://pmc.ncbi.nlm.nih.gov/articles/PMC5470907 | 확인 에이전트 | 정지 판정 = 자이로 0.5°/초 · 가속도 0.04 g · 0.5 초. 자기장 세기 · 복각으로 교란 정도를 재 자력계 비중을 연속으로 낮춤 — 원값 필요 |
| S24 | Fan · Li · Liu, 「How Magnetic Disturbance Influences the Attitude and Heading …」, Sensors 18(1):76, 2017 · https://pmc.ncbi.nlm.nih.gov/articles/PMC5795611/ | 확인 에이전트(일부 요약) | 융합 4방식 비교. 작은 교란에 모두 10초 안에 약 5.7° 끌려감(요약). 문턱 방식은 짧고 작은 교란엔 효과가 약하다(요약) |
| S15 | Casiez · Roussel · Vogel, 「1€ Filter」, CHI 2012 · https://gery.casiez.net/1euro/ | Codex 원문(공식 페이지) | 속도가 낮으면 세게, 빠르면 약하게 거름. 계단은 「빠른 움직임」으로 보여 그대로 통과 — 단독으로는 이 문제를 못 푼다(Codex · agy · REPORT 6장 일치, 추론) |

### 현상 · 플랫폼 · 브라우저

| # | 출처 | 확인 | 내용 |
|---|---|---|---|
| S01 | Jeff Posnick, 「Device Orientation Changes Are Coming to Chrome 50」, 2016 · https://developer.chrome.com/blog/device-orientation-changes | Codex 원문 · 확인 에이전트 | 원문: 「a web app registering a bunch of `DeviceOrientationEvent`s due to a nearby magnet, despite the device itself not actually moving」. 그래서 기본 `deviceorientation` 을 상대 방위로 바꾸고 절대 방위는 `deviceorientationabsolute` 로 분리 |
| S02 | Chromium blink-dev 「'deviceorientation' event relative by default」, 2015~2016 · https://groups.google.com/a/chromium.org/g/blink-dev/c/lT_-2CiHOf4/m/UEpwwtdvAgAJ | Codex 원문 | 「VR head tracking using DeviceOrientationEvent is currently unusable」 |
| S03 · S04 | Android Developers, Position sensors · `Sensor` API 문서 | Codex 원문 | `TYPE_GAME_ROTATION_VECTOR` 는 지자기를 안 써 자기장 변화에 영향받지 않음. 교정 안 한 자력계는 「fewer jumps from corrections applied through calibration」 — 교정이 점프를 만들 수 있다는 공식 설명 |
| S05 · S06 | W3C Orientation Sensor(2026-05 WD) · Device Orientation and Motion(2026-10 CRD) | Codex 원문 | AOS = 가속도 + 자이로 + 자력계, ROS = 가속도 + 자이로. 「The sensor fusion is platform specific」 |
| S07 · S08 | Chromium `PlatformSensor.java` · `platform_sensor_provider_android.cc` | Codex 원문(열람 커밋이 Chrome 143 과 같은지는 미확인) | AOS → Android `TYPE_ROTATION_VECTOR`, ROS → `TYPE_GAME_ROTATION_VECTOR`. 값을 그대로 넘김 |
| S09 | Google, 「Introducing the Fused Orientation Provider API」, 2024-03 | Codex 원문 | 제조사별 융합 편차 · 자기 교란을 플랫폼도 문제로 봄. 웹에서는 못 씀 |
| S19 | 특허 US8788193B2 (GEN-9), 2014 | Codex 원문 | 자력계 신호가 늦으면 반대 방향으로 보정할 수 있다 — **시각이 안 맞는 두 신호의 차이를 바로 보정량으로 쓰면 안 된다** |
| S20 | Nordic DevZone 「Thingy52 orientation tracking」 | Codex 원문 · 확인 에이전트 | 「small jumps (often in the opposite direction of the rotation)」 — 증상 유사 사례. 원인 미확정(답변 없음) |

### 지각 문턱

| # | 출처 | 확인 | 내용 |
|---|---|---|---|
| S16 | Jerald · Steinicke · Whitton, 「Scene-Motion Thresholds Correlate with Angular Head Motions …」, ACHI 2009 · https://pmc.ncbi.nlm.nih.gov/articles/PMC4327851/ | Codex 원문(전문) | 「sensitivity to scene motion decreases as head motion increases」. 머리 회전의 어느 단계가 일관되게 최선이라는 결과는 없음. 저자가 다른 조건으로 수치 일반화 금지를 명시 |
| S17 | Jerald · Whitton, 「Relating Scene-Motion Thresholds to Latency Thresholds for HMDs」, IEEE VR 2009 · https://pmc.ncbi.nlm.nih.gov/articles/PMC3095496/ | Codex 원문(전문) | 지연 지각 문턱 연구. 우리 화면의 각도 문턱이 아님 |
| S18 | Steinicke · Bruder · Jerald · Frenz · Lappe, 「Estimation of Detection Thresholds for Redirected Walking Techniques」, IEEE TVCG 16(1), 2010 | Codex 원문(PDF) | 실제 회전 대비 가상 회전 비율(회전 이득) 문턱 약 0.67 · 1.24(75% 응답 수준). 「회전하는 동안엔 회전량을 조금 다르게 보여도 모른다」의 근거. 정지 중 °/초로 바꿀 수 없음 |

Claude 가 처음에 「Jerald 2008 — 머리가 거의 멈췄을 때 가장 잘 알아챈다」고 쓴 것은 **검색 요약만 본 것**이다. 전문을 읽은 S16 은 단계별 차이를 확인하지 못했다. 근거로 쓰지 않는다.

## 3. agy 보고서 검증 결과 (2026-11-13)

Claude 가 띄운 확인 에이전트와 Claude 의 PDF 원문 검색으로 대조했다.

| agy 가 든 출처 · 인용 | 결과 |
|---|---|
| LaValle ICRA 2014 「relying directly on magnetometer readings introduces unacceptable perceptual artifacts … Drift correction must be applied smoothly and gradually」 | **원문에 없음**(PDF 본문 검색) |
| Chrome 50 블로그 「compass readings fluctuated wildly … even when the phone was sitting on a desk」 | **원문에 없음** — 실제 문장은 S01 |
| Foxlin US5645077 「drift compensation is not applied as a step function」 · 「adjustable rate limiter so that the visual display never translates or rotates without corresponding user motion」 | **읽은 범위에 없음**(가까운 실제 문장은 S21. 특허 뒷부분 22만 자는 안 읽음) |
| Apple US8531180 「preventing sudden jumps or discontinuities in the heading display」 | **읽은 범위에 없음**. 서지(제목 · Apple · 2013)는 맞음 |
| Bosch 포럼 BNO055 「calibration status transitions … discrete step jump」 · 「software slew-rate limiter」 권고 | **주소 404** — 확인 못 함 |
| Razzaque 학위논문(2005) 「정지 시 1°/초 미만」 | **주소 404** — 확인 못 함 |
| Bolte · Lappe 2015 「saccade 중 ±5° 못 알아챔」 | 출판사 페이지가 빈 응답 — 확인 못 함 |
| krpano gyro2 플러그인 동작 | **주소 404** — 확인 못 함 |
| Steinicke 2010 「49% 더 · 20% 덜」 | 초록 수치는 맞음(검색 요약 · Codex S18). 「vestibular signals mask …」 인용은 미확인 |

따라서 agy 가 권한 **수치(정지 판정 3°/초 · 보정 비율 12% · 정지 시 0.5°/초 · 「100% 인지 못함」)는 근거 없음**으로 본다.
agy 의 구조 제안(상대 센서로 화면 구동 + 방위 차이만 움직일 때 속도 제한 반영)은 신뢰 출처 S21 · S22 와 같은 방향이라 `METHOD.md` 에서 신뢰 출처 쪽 근거로 채택했다.

## 4. 이 조사로도 모르는 것

- 이 폰의 계단 원인이 교정 갱신인지 · 자기 교란인지 · 제조사 융합기의 게인 전환인지(자력계 원값이 없어 구분 불가)
- 계단이 「틀린 값으로 튄 것」인지 「틀려 있던 값이 바로잡힌 것」인지 — 화면 정책은 둘 다 「바로 드러내지 않기」로 같다(Codex 지적)
- 폰 화면에서 정지 중 · 회전 중 허용되는 보정 속도(문헌 수치 없음)
- 다른 기기 · iPhone · 다른 장소
