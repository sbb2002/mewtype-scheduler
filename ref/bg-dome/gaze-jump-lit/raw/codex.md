# 시선 튐 참고문헌 조사 — Codex

조사일: 2026-11-13 (Asia/Seoul). 요청: `REQUEST.md`. 코드 수정·실험·브랜치 변경 없이 작성한 문헌 조사다.

## 1. 먼저 읽을 결론

**이 현상을 직접 설명하는 선행 자료가 있다.** Chrome은 기기를 움직이지 않아도 주변 자기장 때문에 방위 이벤트가 생기며 VR에 문제가 된다고 공식적으로 설명했다[S01]. Android는 센서의 교정 과정에서 데이터에 점프가 생길 수 있음을 명시한다[S03, S04]. 따라서 이번 관측은 알려진 센서 융합 문제와 부합한다. 다만 **이 폰의 개별 계단이 자기장 교란·자력계 교정·제조사 융합기 중 무엇 때문에 생겼는지는 확인 못 함**이다. 브라우저 고유 버그라고 확정할 자료도 찾지 못했다.

화면 설계에는 **빠른 회전 추종과 느린 방위 기준 보정을 분리**하는 근거가 가장 강하다. Oculus는 자이로 추종에 작은 이득의 yaw 보정을 더하며[S11], VQF는 6축 자세와 자력계 기반 heading 보정을 분리한다[S12]. 움직임 중에는 추가 장면 회전에 덜 민감해질 수 있다는 실험도 있다[S16]. 그러나 **폰 화면에서 보정 속도 1~2°/s가 안 보인다는 근거는 확인 못 함**이다. HMD 실험의 수치를 폰 화면에 그대로 가져오면 안 된다[S16–S18].

요구 조건에는 다음 절충이 있다(수학적 판단).

- 정지 중 화면을 **완전히 고정**하고 현재 절대 방위와 차이가 있다면, 계속 정지하는 동안 그 차이를 화면에서 없앨 수 없다.
- 요청의 실제 조건인 **“눈에 띄지 않음”**을 허용하면 미세한 정지 중 보정을 시도할 여지는 있다. 그 허용량은 이 화면에서 측정해야 한다.
- 움직임 중에만 보정하면 수렴은 이후 움직임이 충분히 있다는 조건에 의존한다. 자기 교란으로 잘못된 절대 방위가 들어오면 그것에 수렴하는 것이 오히려 오답일 수 있다.

따라서 비교할 후보는 **상대 자세로 즉시 추종 + 별도 방위 오프셋 + 신뢰도에 따른 보정 차단 + 보정 속도 제한 + 움직임에 따른 보정 예산**이다. 이는 아래 문헌을 종합한 설계 제안이며, 세 조건을 모든 환경에서 보장하는 검증된 완제품 알고리즘이라는 뜻은 아니다.

## 2. 조사 범위와 확인 수준

- 내부 근거는 `git show origin/devpapers:ref/bg-dome/gaze-jump/REPORT.md`로 읽었다. 읽은 원격 추적 참조의 커밋은 `0ad684cfed8083fab7e5b2ec6d35bea9f4b5d34c`다. 보고서 저자 Claude, 2026-11-12. CSV 재분석이나 폰 재실측은 하지 않았다.
- 내부 보고서상 AOS만 2.5~9.2° 계단으로 변하고 ROS·자이로는 거의 정지했다. 이는 **내부 보고서의 관측**으로 인용하며 이번 조사에서 독립 재현한 결과는 아니다.
- 각 출처에 **직접 열람 / 검색 요약만 / 확인 못 함**을 명시했다. “직접 열람”은 표시한 본문·절·소스 파일을 실제로 열어 관련 부분을 확인했다는 뜻이며, 전체 저장소 감사나 구현 실행을 의미하지 않는다.
- 다른 PC에서 수행했다는 Codex 작업에 관해 이 세션이 사용할 수 있는 개인적 기억·파일은 없다. **기억만으로 복원한 출처는 0개**다. 기존 보고서에 적힌 링크는 별도 출발점으로 사용했고, 아래에서 재확인 여부를 구분했다. 다른 PC의 구현·보고서와 동일하다고 주장하지 않는다.
- 웹 자료는 2026-11-13에 열람했다. 지속 갱신되는 문서·저장소의 최초 발행연도를 확인하지 못한 경우 그대로 적었다. 저작권 연도를 논문 발행연도로 대신하지 않았다.

## 3. 현상·플랫폼·브라우저의 직접 근거

### S01. Device Orientation Changes Are Coming to Chrome 50

- 저자·연도: Jeff Posnick, Google / 2016 (페이지 갱신일 2016-03-14).
- URL: <https://developer.chrome.com/blog/device-orientation-changes>
- 확인: **이번에 직접 열람**, 본문 “What’s changing?”와 앞의 문제 설명. 기존 내부 보고서의 링크도 재확인함.
- 내용: 자력계 기반 절대 방위는 주변 자기장 변동에 민감하여 기기가 움직이지 않아도 이벤트를 발생시킬 수 있고, VR에서 문제가 된다고 설명한다. Chrome 50부터 기본 `deviceorientation`을 상대 방위로 변경하고 절대 방위는 `deviceorientationabsolute`로 제공했다.
- 짧은 원문: “despite the device itself not actually moving.”
- 적용: **정지했는데 화면이 움직이는 문제에 가장 직접적인 브라우저 공식 근거**다. 단, Chrome 50의 정책 설명이며 Chrome 143·삼성 인터넷 30의 특정 결함이나 수정 완료를 입증하지 않는다.

### S02. Intent to implement and ship: 'deviceorientation' event relative by default

- 저자·연도: Boris Smus 외 Chromium blink-dev 참여자 / 2015–2016.
- URL: <https://groups.google.com/a/chromium.org/g/blink-dev/c/lT_-2CiHOf4/m/UEpwwtdvAgAJ>
- 확인: **이번에 직접 열람**, 최초 제안과 후속 논의. 기존 보고서 링크 재확인함.
- 내용: 2015-09-14 제안의 동기는 절대 방위만 노출하는 Chrome의 VR 머리 추적 문제였다. Android 대상 변경이라고 명시하고 추적 번호 `531610`을 제시한다. 후속 논의에는 자력계 의존 제거와 외부 자기장 영향 감소가 나온다.
- 짧은 원문: “VR head tracking using DeviceOrientationEvent is currently unusable”.
- 적용: 상대/절대 경로를 나누는 브라우저 설계의 역사적 근거다. 논의 초기에 제안한 이벤트 이름과 실제 출시 이름은 다를 수 있으므로 현재 API 이름은 S01·S06을 따른다. `crbug.com/531610` 자체는 이번 도구로 본문을 열지 못했으므로 **현재 버그 상태는 확인 못 함**.

### S03. Position sensors

- 저자·연도: Android Developers / 지속 갱신 문서, 최초 발행연도 확인 못 함.
- URL: <https://developer.android.com/develop/sensors-and-location/sensors/sensors_position>
- 확인: **이번에 직접 열람**, game rotation vector와 uncalibrated magnetometer 절.
- 내용: `TYPE_GAME_ROTATION_VECTOR`는 지자기를 사용하지 않으며 기준 방향이 자이로 드리프트 정도로 흐를 수 있다. 자기장 변화의 영향을 받지 않아 상대 회전 측정에 적합하다. 교정하지 않은 자력계 출력은 교정 때문에 생기는 점프가 더 적고, 자체 융합에서는 교정 도입이 결과를 왜곡할 수도 있다고 설명한다.
- 짧은 원문: “fewer jumps from corrections applied through calibration.”
- 적용: ROS의 장점과 한계를 동시에 뒷받침한다. **절대 방위라는 이름이 정확도 보증을 뜻하지 않으며**, 자기 교란 중에는 틀릴 수 있다. Android 네이티브의 uncalibrated 자력계와 웹의 `RelativeOrientationSensor`는 서로 다른 센서다.

### S04. Sensor — TYPE_MAGNETIC_FIELD_UNCALIBRATED / TYPE_GAME_ROTATION_VECTOR

- 저자·연도: Android Developers / 지속 갱신 API 문서. 두 센서 상수는 API 18에 추가됐으며 문서 최초 발행연도는 확인 못 함.
- URL: <https://developer.android.com/reference/android/hardware/Sensor#TYPE_MAGNETIC_FIELD_UNCALIBRATED>
- 확인: **이번에 직접 열람**, 해당 상수 설명.
- 내용: uncalibrated 자력계는 hard iron 보정을 분리해 제공하며, 주기적 교정에 따른 불연속이 없다고 설명한다. 공장 교정·온도 보상은 남는다. game rotation vector 설명은 북쪽 기준을 쓰지 않고 드리프트를 허용함을 명시한다.
- 짧은 원문: “no periodic calibration is performed”.
- 적용: 교정 갱신 자체가 불연속의 원인이 될 수 있다는 공식 설명이다. 이를 근거로 **이 기기의 AOS 계단 원인이 주기적 교정이라고까지 확정할 수는 없다**. 웹에서 이 네이티브 센서 종류를 직접 선택할 수 있다는 뜻도 아니다.

### S05. Orientation Sensor

- 저자·연도: W3C Devices and Sensors Working Group; 편집 Kenneth Rohde Christiansen, Anssi Kostiainen / 2026-05-14 Working Draft.
- URL: <https://www.w3.org/TR/2026/WD-orientation-sensor-20260514/>
- 열람한 최신판 URL: <https://www.w3.org/TR/orientation-sensor/>
- 확인: **이번에 직접 열람**, §5 모델·센서 조합 표·§5.1 좌표계·문서 상태.
- 내용: AOS는 가속도계·자이로·자력계 융합, ROS는 가속도계·자이로 융합이다. 융합은 플랫폼별로 소프트웨어나 센서 허브에서 수행될 수 있다. AOS의 지구 좌표계는 **자북** 기준이다. quaternion 배열은 `[x,y,z,w]` 순서다.
- 짧은 원문: “The sensor fusion is platform specific”.
- 적용: 웹 API가 융합기의 연속성·보정 속도를 통일한다고 볼 수 없다. 자북과 진북 차이는 별도 문제다. 이 2026 판은 기존 배포 유지용이며 신규 프로젝트에는 Device Orientation and Motion을 권한다. 이것이 현재 기능을 즉시 교체해야 한다는 결론은 아니다.

### S06. Device Orientation and Motion

- 저자·연도: W3C; 편집 Reilly Grant, Marcos Cáceres / 2026-10-26 Candidate Recommendation Draft.
- URL: <https://www.w3.org/TR/2026/CRD-orientation-event-20261026/>
- 열람한 최신판 URL: <https://www.w3.org/TR/orientation-event/>
- 확인: **이번에 직접 열람**, §3.1.1·§6.1·§6.2·권한/가시성 규정.
- 내용: 상대 방위는 임의 기준 좌표계다. `deviceorientation`은 상대 방위를 못 주거나 절대 방위가 더 정확하다고 판단하면 절대 값으로 대체할 수 있으므로 `absolute`를 확인해야 한다. 방위 각도 정밀도는 0.1°로 제한하며 이벤트 발생을 위한 유의 변화 판정은 구현별이다. 보이지 않는 문서에는 이벤트를 보내지 않는 절차가 있다. `deviceorientationabsolute`는 구현 경험 부족으로 at risk다.
- 적용: **이벤트 이름만으로 모든 브라우저에서 자력계 없는 신호라고 단정하면 안 된다.** 0.1° 정밀도·권장 1° 변화 문턱은 이벤트 관련 규정이며, AOS quaternion에 관측된 9° 계단의 설명이나 인간 지각 문턱이 아니다. 명세 날짜가 삼성 인터넷의 구현 일치를 보장하지 않는다.

### S07. Chromium PlatformSensor.java

- 저자·연도: The Chromium Authors / 파일 저작권 2016, 열람 커밋의 작성연도 확인 못 함.
- URL: <https://chromium.googlesource.com/chromium/src/+/f2db5409f4065feeb5525a59fea56cc48298d9db/services/device/generic_sensor/android/java/src/org/chromium/device/sensors/PlatformSensor.java>
- 확인: **이번에 직접 소스 열람**, 센서 생성 switch와 `onAccuracyChanged`·`onSensorChanged`.
- 내용: `ABSOLUTE_ORIENTATION_QUATERNION → Sensor.TYPE_ROTATION_VECTOR`, `RELATIVE_ORIENTATION_QUATERNION → Sensor.TYPE_GAME_ROTATION_VECTOR` 매핑을 확인했다. 읽기 개수는 각 4개다. `onAccuracyChanged`는 빈 함수이고 센서 이벤트에서는 timestamp와 앞의 값들을 전달한다.
- 적용: Android 네이티브 융합 출력이 웹으로 들어오는 직접 경로가 실제로 있다. 이 파일에서는 네이티브 정확도 콜백을 활용하지 않는다. **열람 커밋이 Chrome 143 또는 삼성 인터넷 30과 일치하는지는 확인 못 함**. `143.0.7499.0` 태그의 해당 파일 열람을 시도했지만 실패했으므로 버전 일치를 주장하지 않는다.

### S08. Chromium platform_sensor_provider_android.cc

- 저자·연도: The Chromium Authors / 파일 저작권 2016, 열람 커밋의 작성연도 확인 못 함.
- URL: <https://chromium.googlesource.com/chromium/src/+/00ddf49163098/services/device/generic_sensor/platform_sensor_provider_android.cc>
- 확인: **이번에 직접 소스 열람**, 절대/상대 orientation 생성과 fallback 주석·분기.
- 내용: 절대 quaternion은 `TYPE_ROTATION_VECTOR` 직접 사용을 우선하고, 안 되면 Euler 기반 융합 경로를 시도한다. 절대 Euler 경로에는 가속도계+자력계 기반 대체 경로가 있다. 상대 경로는 game rotation vector 기반 quaternion을 사용한다.
- 적용: W3C의 센서 조합 표만으로 실제 기기에서 언제나 같은 9축 융합기가 실행된다고 단정할 수 없다. **이 폰이 실제 어느 분기를 사용했는지·Chrome 143에서도 동일한지는 확인 못 함**이다.

### S09. Introducing the Fused Orientation Provider API: Consistent device orientation for all

- 저자·연도: Geoffrey Boullanger, Shandor Dektor, Martin Frassl, Benjamin Joseph / Google, 2024-03-07.
- URL: <https://android-developers.googleblog.com/2024/03/introducing-fused-orientation-provider-api.html>
- 확인: **이번에 직접 열람**, API 특성과 자기 교란 설명. 기존 보고서 링크 재확인함.
- 내용: Google Play services의 FOP는 제조사별 편차를 줄이고 자이로 바이어스·센서 타이밍에 대응하며, Google Maps도 사용한다. 자기 교란 대응 개선을 명시한다. 일부 경우에는 AOSP Rotation Vector를 편각 보정해 전달한다. 위치 등을 통해 편각을 알면 진북, 아니면 자북 기준이다. 요청 업데이트 주기는 보장 주기가 아니다.
- 적용: 제조사 융합 출력의 품질·타이밍 차이를 플랫폼도 문제로 인식한다는 근거다. **Chrome AOS가 FOP를 사용한다는 근거는 없으며**, 이 네이티브 API를 웹에서 바로 부를 수 있다고 해석하면 안 된다. 내부 알고리즘·화면 보정 정책은 이 글로 확인 못 함.

### S10. CMAttitudeReferenceFrame.xArbitraryCorrectedZVertical

- 저자·연도: Apple / 지속 갱신 Core Motion 문서, 최초 발행연도 확인 못 함; API 가용성 iOS 4.0 이상.
- URL: <https://developer.apple.com/documentation/coremotion/cmattitudereferenceframe/xarbitrarycorrectedzvertical>
- 직접 확인한 공식 Markdown: <https://developer.apple.com/documentation/coremotion/cmattitudereferenceframe/xarbitrarycorrectedzvertical.md>
- 확인: **이번에 직접 열람**, HTML의 공식 Markdown 링크로 본문 확인.
- 내용: 초기 X 방향은 임의지만 자력계를 사용하여 장기 yaw 정확도를 개선하는 reference frame이다. 센서 가용성과 교정이 필요하다.
- 짧은 원문: “uses the magnetometer to improve long-term accuracy”.
- 적용: **임의 초기 방위라는 속성만으로 자력계를 안 쓴다고 판단할 수 없다.** 이는 네이티브 iOS의 개념 비교이며 Safari가 이 frame을 사용한다는 확인은 아니다. 이번에 Safari 실측·WebKit의 실제 선택 경로는 확인 못 함.

## 4. 보정 알고리즘·공개 구현

### S11. Head Tracking for the Oculus Rift

- 저자·연도: Steven M. LaValle, Anna Yershova, Max Katsev, Michael Antonov / 2014, ICRA, pp.187–194, DOI `10.1109/ICRA.2014.6906608`.
- 저자 제공 PDF: <https://lavalle.pl/papers/LavYerKatAnt14.pdf>
- 확인: **이번에 직접 PDF 열람**, §V tilt correction, §VI yaw correction, 식 (10)·(12), PDF 4–5쪽.
- 내용: 자이로의 빠른 추종을 유지하면서 작은 이득으로 기준 오차를 줄이는 상보 필터를 쓴다. §V에서는 보정이 사용자에게 지각되지 않을 만큼 작아야 한다고 명시하고, §VI에서는 같은 방식으로 수직축만 보정한다. 자력계 교정이 완벽하다고 가정하지 않고 가까운 자세의 여러 reference point를 사용한다.
- 짧은 원문: “small enough so that the corrections are imperceptible to the user.”
- 적용: 화면 전체의 회전을 둔화시키는 대신 **보정 경로만 약하게 만드는** 직접적인 HMD 구현 근거다. 작은 고정 이득은 보정 속도의 하드 제한과 같지 않으며 큰 오차에서는 보정 속도가 커질 수 있다. 본 논문이 “정지 중 완전 차단” 또는 “1°/s면 불가시”를 입증한다고 해석하면 안 된다.

### S12. VQF: Highly Accurate IMU Orientation Estimation with Bias Estimation and Magnetic Disturbance Rejection

- 저자·연도: Daniel Laidig, Thomas Seel / Information Fusion 91 (2023), 187–204. arXiv 초고 2022, 최종 수정 2022-10-27. DOI `10.1016/j.inffus.2022.10.014`.
- 서지·초록: <https://arxiv.org/abs/2203.17024>
- PDF: <https://arxiv.org/pdf/2203.17024>
- 확인: **이번에 직접 PDF 열람**, §2.2–2.5, Fig.3–4, §3.6/Fig.14, Appendix F/Algorithm 3.
- 내용: 6축 자세와 자력계 heading offset을 분리하여 자기 교란이 기울기 추정으로 번지지 않게 한다. 자기장 크기·dip angle을 통해 교란을 판단하고 보정을 차단하거나 느리게 한다. 교란된 사무실 사례에서는 차단 사용으로 최대 오차 20.0°가 3.7°로 줄었다. 이는 특정 실험의 **자세 추정 오차**이며 불쾌감·지각 임계치 결과가 아니다.
- 적용: “상대 자세 + 별도 장기 방위 보정”과 “교란 감지 후 보정 중지·회복”의 강한 근거다. **VQF는 raw gyro/acc/mag를 입력받는 융합기**다. 이미 융합된 AOS·ROS만으로 동일 알고리즘을 재현할 수 있다는 뜻은 아니다.

### S13. VQF Parameters / 공개 C++ 구현

- 저자·연도: Daniel Laidig 및 VQF 프로젝트 / 2021년 저작권 표기부터, 논문 2023; 열람한 main의 개별 갱신연도 확인 못 함.
- 저장소: <https://github.com/dlaidig/vqf>
- 파라미터 문서: <https://vqf.readthedocs.io/en/latest/ref_cpp_params.html>
- 직접 읽은 코드: <https://raw.githubusercontent.com/dlaidig/vqf/main/vqf/cpp/vqf.cpp>
- 확인: **이번에 문서·`updateMag` 소스 직접 열람**. 실행 검증은 하지 않음. main/latest는 이동하는 참조다.
- 내용: heading 보정 시간상수 기본값 `tauMag=9s`, 자기장 크기 허용 차이 10%, dip 차이 10°, 정상 복귀 판정 0.5s, 완전 거부 최대 60s를 제공한다. 새로운 자기장 기준을 받아들이는 시간은 충분한 회전(기본 20°/s 이상)에서만 누적한다. `updateMag`에는 거부 시 이득 0, 장기 교란 시 이득 축소, 초기 빠른 수렴의 별도 분기가 있다. 저장소는 MIT 라이선스다.
- 적용: **움직일 때만 새 자기장 기준을 인정하는 것**과 **화면 보정을 움직일 때만 하는 것**은 다르다. VQF의 해당 문턱을 후자의 실증 근거로 오인하면 안 된다. 9s·60s 등은 알고리즘 기본값이지 폰 화면의 지각상 안전 수치가 아니다. 초기 빠른 수렴도 화면 공개 뒤에는 눈에 띌 수 있으므로 별도 검토 대상이다.

### S14. Fusion — AHRS algorithm / magnetic rejection

- 저자·연도: x-io Technologies, 소스 저자 Seb Madgwick / 저장소 최초 발행연도 확인 못 함 (2026-11-13 열람).
- README: <https://github.com/xioTechnologies/Fusion>
- 직접 읽은 코드: <https://raw.githubusercontent.com/xioTechnologies/Fusion/main/Fusion/FusionAhrs.c>
- 확인: **이번에 README와 C 소스 직접 열람**. 실행·벤치마크는 하지 않음.
- 내용: 측정된 heading과 추정 heading의 각도 차이가 문턱을 넘으면 자력계 피드백을 거부한다. 장기간 거부에는 recovery가 있고, 시작 때는 빠른 수렴을 위해 거부 기능이 비활성화되며 이득을 낮춰 간다. README는 magnetic rejection 10°와 timeout 5s 등을 예시로 제시한다.
- 적용: **이상값 차단만 넣으면 끝이 아니라 복귀 정책도 필요하다**는 공개 구현이다. AOS/ROS 차이로 잔차 게이트를 만드는 아이디어는 유사하지만 raw 자력계 검증과 동등하지 않다. 예시 10°는 우리 2.5° 계단에 맞춘 검출 문턱이 아니고, 시작·recovery 중 화면 안정성을 보장하지 않는다.

### S15. 1€ Filter: A Simple Speed-based Low-pass Filter for Noisy Input in Interactive Systems

- 저자·연도: Géry Casiez, Nicolas Roussel, Daniel Vogel / CHI 2012, pp.2527–2530.
- 저자 공식 페이지: <https://gery.casiez.net/1euro/>
- 논문 링크: <https://direction.bordeaux.inria.fr/~roussel/publications/2012-CHI-one-euro-filter.pdf>
- 확인: **공식 페이지의 설명·튜닝 절차·구현 링크를 이번에 직접 열람**. 위 논문 PDF는 요청이 시간 초과되어 전문 확인 못 함. 검색 요약에서 논문 제목·저자를 대조함.
- 내용: 낮은 속도에서는 jitter 억제를 강화하고 빠른 움직임에서는 lag를 줄이는 조정법이다. 공식 페이지가 `mincutoff`를 낮추면 jitter는 줄고 lag는 늘어난다고 설명한다.
- 적용에 대한 추론: AOS의 계단을 그대로 입력하면 차분 속도가 커져 실제 빠른 회전처럼 받아들일 수 있다. 따라서 **One Euro 단독으로 실제 회전과 방위 기준 보정을 구분한다고 볼 수 없다**. ROS 기반 실제 회전과 보정량을 먼저 분리한 뒤 보조적으로 쓰는 편이 문제 정의에 맞다. Sky Map의 실제 적용 코드는 이번에 확인하지 않았으므로 해당 앱 사용 사례를 독립 검증 결과로 싣지 않는다.

## 5. 지각 문턱 연구 — 어느 상황에서 덜 보이는가

### S16. Scene-Motion Thresholds Correlate with Angular Head Motions for Immersive Virtual Environments

- 저자·연도: Jason Jerald, Frank Steinicke, Mary Whitton / ACHI 2009, pp.69–74. DOI `10.1109/ACHI.2009.40`.
- 전문: <https://pmc.ncbi.nlm.nih.gov/articles/PMC4327851/>
- 실제 열람에 성공한 주소: <https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4327851/>
- 확인: **이번에 전문 직접 열람**, §3–5. 직접 PMC 주소는 처음 접근 확인 화면이 나왔지만 두 번째 공식 주소에서 본문을 확인했다.
- 내용: HMD에서 8명의 피험자가 머리를 yaw 회전할 때 장면 이동 감지를 측정했다. 회전 크기·최고 속도·최고 가속도가 커질수록 장면 속도의 감지 문턱이 높아졌다. 머리 회전의 특정 단계가 일관되게 최선이라는 결과는 얻지 못했다. 저자들은 시야각·대비·장면 크기·훈련 등 다른 조건에 수치를 일반화하지 말라고 명시한다.
- 짧은 원문: “sensitivity to scene motion decreases as head motion increases”.
- 적용: 움직임 중 보정량을 더 허용하는 **정성적 근거**다. 이 실험은 느려지면 장면을 끄기도 했으므로 **정지 중 허용속도를 직접 구한 연구가 아니다**. 손에 든 폰은 머리 회전과 다르고 실제 주변 기준도 보여 수치 이전이 어렵다.

### S17. Relating Scene-Motion Thresholds to Latency Thresholds for Head-Mounted Displays

- 저자·연도: Jason Jerald, Mary Whitton / IEEE VR 2009, pp.211–218. DOI `10.1109/VR.2009.4811025`.
- 전문: <https://pmc.ncbi.nlm.nih.gov/articles/PMC3095496/>
- 확인: **이번에 전문 직접 열람**, §3–5와 §4.6 결과.
- 내용: 장면 속도와 머리 가속도를 통해 latency 지각을 분석한다. 일정 속도·Gaussian 속도·실제 지연으로 생긴 장면 이동의 문턱은 다르다. 6명 분석의 latency JND 평균은 16.6ms, 최소는 3.2ms였다. 이 값들은 실험의 지연 **변별 문턱**이며 일반 화면 움직임의 각도 문턱이 아니다.
- 적용: “몇 도만 천천히 움직이면 안 보인다”보다 **속도 프로파일·노출 시간·실제 추종 지연·개인차**를 나눠 봐야 한다. AOS 전체를 더 세게 평활하면 실제 회전 지연을 늘리므로 보정 경로만 제어할 이유가 있다. 이 논문은 우리 폰에서 0.08s 감쇠의 적절성이나 1°/s 허용을 검증하지 않았다.

### S18. Estimation of Detection Thresholds for Redirected Walking Techniques

- 저자·연도: Frank Steinicke, Gerd Bruder, Jason Jerald, Harald Frenz, Markus Lappe / IEEE TVCG 16(1), 2010, pp.17–27; 온라인 공개 2009. DOI `10.1109/TVCG.2009.62`.
- 저자 소속기관 PDF: <https://www.uni-muenster.de/imperia/md/content/psyifp/ae_lappe/freie_dokumente/stein__bruder__jerald__frenz__lappe_2010.pdf>
- 확인: **이번에 PDF 직접 열람**, E1 회전 실험·§4.2.2–4.2.3, PDF 6쪽.
- 내용: HMD에서 실제 회전에 대한 가상 회전의 gain을 조절했다. 보고된 회전 gain 문턱은 약 0.67과 1.24다. 이는 75% 응답 수준의 심리측정 결과이며 모든 피험자에게 불가시라는 뜻은 아니다.
- 적용: 움직일 때 회전량을 조금 다르게 보여 보정을 흡수하는 발상의 근거다. **24%를 항상 보정해도 안 보인다는 보증이 아니다.** gain은 회전 비율이며 정지 중 °/s로 변환할 수 없다. 우리 앱에서 시작값으로 그대로 채택할 근거도 없다.

## 6. 특허·구체적인 유사 사례

### S19. US8788193B2 — Tracking activity, velocity, and heading using sensors in mobile devices or other systems

- 발명자·연도: Mark A. Fauci, Yinghao Ma, Craig Poppe, Thung-Han Hee, Rahul Agrawal; 원출원인 GEN-9 Inc / 등록 공고 2014-07-22, 우선일 2011-10-17.
- URL: <https://patents.google.com/patent/US8788193B2/en>
- 확인: **이번에 특허 공개 본문 직접 열람**, heading/drift correction 예시. 권리 상태·청구범위 분석은 하지 않음.
- 내용: 자력계 신호가 늦으면 실제로는 +5° 드리프트인데 −5°로 판단해 반대 방향으로 보정할 수 있다는 수치 예시가 있다. 최근 표본에서 heading이 크게 변하지 않았는지 확인하는 방어 절차를 제안한다.
- 짧은 원문: “because of the lag in the magnetometer signal”.
- 적용: **시간 정렬 없는 두 신호의 차이를 곧바로 보정량으로 삼으면 안 된다**는 관련 근거다. 이 특허는 위치/보행 heading 추정에 관한 것이며 움직임 중 화면 보정을 숨기는 실험이나 삼성 폰의 버그 증거는 아니다.

### S20. Nordic Thingy52 orientation tracking

- 작성자·연도: 질문 andrewbates11 (Andrew), 답변 Nguyen Hoan Hoang / 페이지는 “over 7 years ago”만 표시; 정확한 게시 연도 확인 못 함.
- URL: <https://devzone.nordicsemi.com/f/nordic-q-a/43769/nordic-thingy52-orientation-tracking>
- 확인: **이번에 질문·답변 직접 열람**, 기존 보고서 링크 재확인함. 재현 실험은 하지 않음.
- 내용: Android 앱에서 회전하는 큐브가 때때로 반대 방향으로 작게 튄다는 보고다. 질문자는 자력계 갱신 시점일 수 있다고 추정했다. 그러나 답변자는 DMP quaternion이 가속도계·자이로만 사용하는 것으로 이해한다고 썼고, 구현 문서가 거의 없다고 했다. 게시물 상태는 Not Answered다.
- 적용: 눈에 보이는 자세 튐의 **증상 유사 사례**로는 맞지만 **자력계 갱신이 원인이라고 검증된 사례가 아니다**. 내부 보고서의 해당 요약은 이 불확실성을 붙여 읽어야 한다. Chrome 센서 경로와도 별개다.

## 7. 방법별로 실제 가져올 수 있는 것

아래는 문헌을 종합한 **설계 후보 평가**다. 구현 지시나 검증된 수치 권고가 아니다.

| 방법 | 근거 | 기대 효과 | 남는 한계 |
|---|---|---|---|
| ROS로 즉시 추종하고 절대 기준 오프셋만 별도 갱신 | S03, S07, S11, S12 | 실제 회전을 보정용 저역통과 필터에서 분리 | 상대 방위 드리프트, 초기 정렬·재시작 처리 필요 |
| 보정량에 긴 시간상수 | S11–S13 | 절대 계단을 완만한 이동으로 바꿈 | 큰 오차의 초기 보정속도는 여전히 클 수 있음; 불가시 보장 없음 |
| 보정의 각속도·각가속도 제한 | S11의 작은 보정 원칙, S16–S17의 지각 결과를 바탕으로 한 제안 | 계단에 대한 화면 보정속도 상한을 명확히 함 | 구체적인 제한값은 이 폰에서 미검증; 실제 회전 경로에 걸면 추종 지연 |
| 움직임 중 보정 예산 확대, 정지 중 축소/중지 | S16·S18의 정성적 근거 | 사용자가 멈춘 직후의 혼자 움직임 감소 가능 | 충분한 움직임 없이는 수렴 안 됨; 폰 회전과 머리 회전은 다름 |
| 자기장 이상 판정 후 보정 거부·복귀 | S12–S14 | 틀린 절대 기준으로 당겨지는 것을 줄임 | raw mag가 없는 현재 웹 경로에서 같은 검사는 불가 |
| AOS−ROS 잔차의 급변을 대리 지표로 사용 | S19의 시간 정렬 문제를 고려한 추론 | OS 출력에서만 생긴 기준 변화를 격리할 가능성 | 교란·정상 재교정·두 경로의 시간차를 확정 분류하지 못함 |
| One Euro를 보조 사용 | S15 | 손떨림과 응답성 절충에 유용할 수 있음 | 센서 보정과 실제 회전의 원인 구분 기능은 아님 |

방위각만의 개념 표기로 상대 방위 `r`, 절대 방위 `a`, 화면 보정 오프셋 `b`를 두면 화면은 `r+b`, 보정 목표는 두 신호를 같은 시각·좌표계로 맞춘 뒤의 `wrap(a−r)`로 볼 수 있다. **필터링할 대상은 원래 움직임 전체가 아니라 이 기준 차이**다. 이 표현은 yaw만의 설명이며 실제 3차원 자세를 Euler 성분별로 빼도 된다는 뜻은 아니다[S05, S12].

추가로 구분해야 할 사항:

1. **원인 판정과 화면 정책은 별개다.** AOS의 계단이 틀린 보정인지, 앞서 틀려 있던 방위가 뒤늦게 바로잡힌 것인지 현재 기록만으로 판단하기 어렵다. 두 경우 모두 즉시 화면에 드러내지 않는 정책은 가능하다.
2. **정지 판정에 AOS 변화량을 쓰면 역효과가 날 수 있다.** 보정 계단 때문에 “움직이는 중”이라고 판단하면 바로 그 계단을 화면으로 통과시킨다. ROS 변화·gyro를 우선 쓰고 손떨림·느린 의도 회전을 구분해야 한다(추론).
3. **raw 자기장 크기·dip 검사와 AOS−ROS 잔차 검사는 동등하지 않다.** 큰 잔차만으로 자기 교란이라고 부르면 정상 장기 드리프트 보정도 막을 수 있다. 작은 잔차라고 절대 방위가 정확한 것도 아니다.
4. **자북·진북, quaternion 부호, 화면 회전, 각도 wrap, 표본 시간차를 별도로 확인해야 한다.** `q`와 `−q`는 같은 회전이고, 단순 성분 차분은 잘못된 점프를 만들 수 있다. 정규화·부호를 고려한 회전 차이와 기울기 특이점 부근을 검사할 필요가 있다(수학적 점검 제안). 이를 이번 버그 원인으로 확인한 것은 아니다.
5. **동시 수신은 같은 측정시각을 뜻하지 않는다.** AOS·ROS·devicemotion의 빈도와 지연이 다르면 회전 중 잔차가 생긴다. 센서 timestamp를 이용해 정렬하고, 긴 공백·탭 복귀·센서 재시작 때 기존 상대 원점을 계속 믿지 않는 검토가 필요하다[S07, S19; 설계 추론].

## 8. 알려진 문제와 미확인 항목의 경계

- **확인한 일반 문제:** 자기장 변화가 정지한 기기의 절대 방위를 움직이게 하는 문제[S01], 교정으로 인한 데이터 불연속[S03–S04], 제조사 센서 융합 편차[S09], 자기장 기반 장기 보정의 오류와 거부·복귀 필요성[S11–S14].
- **확인한 브라우저 대응 이력:** Chrome의 상대 `deviceorientation` 기본 전환[S01–S02]. 이것을 “AOS 계단 버그가 해결됐다”로 해석하면 안 된다. AOS·절대 이벤트는 계속 자기장 기준을 제공하는 다른 경로다.
- **확인 못 함:** 삼성 인터넷 30 / Chrome 143에서 “회전 후 정지 직후 AOS가 2.5~9.2° 튐”과 정확히 일치하며 원인까지 확인된 공개 Chromium 버그, 수정 버전, 해당 폰 제조사 융합 알고리즘. 검색에서 찾지 못했다는 것이 버그가 없다는 증거는 아니다.
- **raw Magnetometer의 부재:** Chrome의 공식 `Sensors for the web` 글은 `Magnetometer`가 extra classes 플래그 뒤에 있다고 설명한다. 저자 Alex Shalamov, Mikhail Pozdnyakov, Thomas Steiner; 페이지 갱신일 2017-09-18. <https://developer.chrome.com/docs/capabilities/web-apis/generic-sensor> — **이번에 직접 열람**. 오래된 설명이므로 삼성 인터넷 30의 정확한 설정 상태는 확인 못 함. 중요한 점은 **raw API를 웹에 노출하지 않는 것과 OS 융합기가 내부적으로 자력계를 사용하는 것은 별개**라는 것이다[S05, S07].
- **이전 보고서의 삼성 링크:** “Can S22 Ultra be a problem in using Android TYPE_ROTATION_VECTOR?” / Samsung Developer Forum, 작성자·연도 확인 못 함. <https://forum.developer.samsung.com/t/can-s22-ultra-be-a-problem-in-using-android-type-rotation-vector/26674> — 이번 열람은 **404, 본문 확인 못 함**. 따라서 이 문서에서는 S22/S23 또는 운영자 기기의 확정 버그 근거로 쓰지 않는다.
- **이전 보고서의 Oculus 블로그 링크:** `magnetometer` / Oculus·Meta, 작성자·정확한 연도 확인 못 함. <https://developers.meta.com/vr/blog/magnetometer/> — 검색 요약에서 hard/soft iron 보정·yaw correction 내용을 봤지만 본문 열람은 시간 초과했다. **이번에는 검색 요약만, 직접 재확인 못 함**. 같은 주제의 근거는 실제로 읽은 저자 논문 S11을 우선했다.
- **현재 얻지 못한 지각 수치:** 이 돔의 시야각·배율·대비·기기·사용자 조건에서 정지 중 허용 가능한 °/s, 총 누적 각도, 움직임 중 허용 gain. S16–S18은 이 값을 대신하지 않는다.

## 9. 후속 비교에서 확인할 항목 — 이번에는 미수행

연구 결과를 적용할 때는 기존 관측의 대표 계단 구간을 재생하여 다음을 함께 평가하는 편이 타당하다(조사자의 제안).

- **멈춘 뒤 화면 안정성:** 정지 후 0.3s·1s·수 초의 보정 이동량과 최대 속도, 그리고 운영자의 실제 감지 여부.
- **실제 회전 추종:** ROS에 대한 화면 응답 지연과 느린 의도 회전을 놓치는지. 손떨림을 가리는 것과 의도 회전을 막는 것을 구분한다.
- **수렴 조건:** 움직임이 있는 경우와 계속 정지한 경우를 나눠 절대 기준 잔차를 기록한다. 절대 값 자체가 신뢰 가능한 환경인지도 별도 확인한다.
- **회복:** 큰 계단·반복 교란·탭 복귀·센서 재시작·기준 방향 재설정 때 화면이 한 번에 돌아가지 않는지.
- **환경 비교:** 같은 폰의 실내/실외·자성 액세서리 유무·다른 기기/브라우저. 이는 원인 가설을 좁힐 실험이며 현재 결과는 없다.

가장 먼저 읽을 원문은 **S01(Chrome의 동일 문제 설명), S11(Oculus의 보정 설계), S12–S13(VQF의 분리·거부·회복), S16(움직임과 지각 문턱의 관계)**다. 본 조사는 이 문서 하나의 작성으로 종료하며, 후보 알고리즘 구현·기존 코드 변경·다른 PC 결과와의 병합은 수행하지 않았다.
