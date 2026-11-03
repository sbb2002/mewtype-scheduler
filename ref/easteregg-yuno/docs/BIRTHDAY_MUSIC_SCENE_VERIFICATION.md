# 생일 음악 장면 3차 검증 (2026-10-31)

브랜치 `feat/birthday-music-scene`의 구현과 로컬 검증 기록이다. 2026-11-01 운영자 승인으로 v4.11.0을 병합·프로덕션 배포했다(PR #127, `6969df5`). 아래 미확인 실기기 검증은 운영자가 후속 확인하며, 병합·배포 식별자는 `docs/VERSION.md`에 기록한다.

## 프레임 비용

실제 Windows Chromium의 1440×900, DPR 1 장면을 시각별 120회 측정했다. 프레임 사이에는 requestAnimationFrame으로 대기하고 기존 장면 RAF는 테스트 응답에만 주입한 취소 함수로 정지시키고 장면을 실제 화면에 표시했다. draw의 CPU 제출 비용이며 GPU 완료·화면 표시 시간은 포함하지 않는다. 별도 브라우저 검사는 성능 계측과 동시에 실행하지 않았다. Chromium 149.0.7827.55의 SystemInfo에서도 2D Canvas와 GPU 합성 enabled를 확인했다.

- GPU 헤디드 렌더러: `ANGLE (NVIDIA, NVIDIA GeForce RTX 4080 SUPER (0x00002702) Direct3D11 vs_5_0 ps_5_0, D3D11)`.
- 소프트웨어 헤드리스 렌더러: `ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero) (0x0000C0DE)), SwiftShader driver)`.

| 곡 시각(s) | GPU 평균(ms) | GPU p95(ms) | GPU 최대(ms) | 소프트웨어 평균(ms) | 소프트웨어 p95(ms) |
|---|---:|---:|---:|---:|---:|
| 7.5 | 0.83 | 1.20 | 1.60 | 17.48 | 21.00 |
| 14 | 0.95 | 1.30 | 1.40 | 17.57 | 20.70 |
| 17.3 | 1.97 | 2.50 | 3.40 | 32.81 | 38.40 |
| 25 | 1.61 | 2.00 | 2.80 | 17.38 | 19.70 |
| 110 | 3.24 | 4.00 | 4.80 | 18.60 | 21.30 |

**GPU 환경 통과**: 측정한 600프레임의 평균·p95·최대가 모두 8ms 이하다(전체 최대 4.8ms). 소프트웨어는 8ms를 넘으며 바닥 합성이 병목이다. 이 데스크톱 GPU 수치로 모바일이나 모든 기기의 상한을 보증하지 않는다. 초기 캐시 생성은 별도 첫 실행이며 표는 워밍업 후 값이다. 화면 밖 Canvas 측정에서는 소비되지 않은 GPU 명령의 일괄 처리 지연이 섞였으므로 해당 후보 수치를 최종 판정으로 쓰지 않았다.

## 동작 검증

- 전체 self-check 10개와 `git diff --check` 통과.
- 정본의 의도된 차이를 보정한 PC 7개 시각: RGB 차이가 2를 넘는 변경 픽셀 0%, 최대 채널 차이 1/255. 정본 수식·색·시간을 유지했다. 바닥 잘라내기/클리핑 후보는 픽셀 차이가 생겨 채택하지 않았다.
- 평일 장면·음악 요청 0. 자동재생 허용과 실제 정책 차단→터치 시작, 저장 볼륨·음소거, 이전/다음, 자정 재판정·정리를 Chromium에서 검증했다.
- PC 유노 조명의 실제 최종 픽셀도 검사해 중간 클리핑으로 회색이 되지 않는지 확인했다.
- 모바일 390×844·412×915·360×800 레이아웃과 컨트롤/안내 배치 확인. 실제 Safari 검증은 아니다.
- Web Audio 곡 경계 3회: 경계 앞뒤 80ms씩의 스테레오 출력 샘플을 원본 PCM과 비교해 차이 허용값 1e-5를 넘는 샘플 0. 마지막 경계는 메인 스레드를 1초 막은 상태로 검사했다. Gain의 float32 반올림 오차만 남았으며 앱이 추가하는 공백은 없다. 원본 음원에 포함된 침묵·페이드 자체를 제거한 검사는 아니다.
- 일시정지/탐색/곡 선택은 예약 소스와 타이머를 취소한다. 110.125초 정지 탐색 오차 0. destroy/자정 후 생일 Audio·AudioContext·blob·RAF·예약 소스·폴링 타이머 0을 확인했다.

## 곡선·리소스와 미확인 사항

인계 문서의 곡선 충돌 해결 지시에 따라 .03→.30(3초), 2.4→1.0(17.14~18.64초)의 양 끝 값을 유지하고 quadratic ease-out으로 통일했다. 기존 선형 표본과 달리 1.5초는 .2325, 17.2초는 2.29024다. 점등 전파 중 기본 장면 Canvas의 CSS brightness는 .30이고, 별도 전파 Canvas가 태양 중심 마스크와 최종 밝기를 합성한다. 유노도 별도 Canvas에서 최종 밝기를 적용해 중간 클리핑으로 회색이 되는 문제를 수정했다.

첫 곡은 스트리밍하면서 두 곡을 blob/PCM으로 준비하고 AudioContext 시각에 출력을 교체한다. 디코드 뒤에는 현재 곡과 다음 두 곡을 샘플 경계에 예약한다. 재생·탐색 재시작에는 80ms의 예약 여유를 둔다. 48kHz 스테레오 PCM 두 곡은 약 157MiB다. Web Audio 미지원·디코드 실패의 스트리밍 대체 경로는 무공백을 보장하지 않는다.

**실제 iPhone Safari 미확인**: 자동재생 차단→첫 탭, Gain 기본 .3·음소거, 백그라운드 복귀, 주소창 높이 변화·안전영역, 긴 누르기 메뉴, 메모리 사용과 프레임 비용. 스트리밍 대체 경로의 무공백과 OS 스피커 녹음도 미확인이다. 복사 억제는 우연한 가져가기를 어렵게 하는 장벽이며 완전한 차단이 아니다.

## 재실행

```powershell
Get-ChildItem src/frontend/js/*.selfcheck.mjs | ForEach-Object { node $_.FullName }
python scripts/verify_birthday_music.py
python scripts/verify_birthday_lifecycle.py
python scripts/compare_birthday_pixels.py
python scripts/verify_birthday_addendum.py
python scripts/verify_birthday_gapless.py
python scripts/verify_birthday_performance.py --headed
python scripts/verify_birthday_performance.py
```

브라우저 검사는 서로 다른 포트를 쓰지만 성능 검사는 단독으로 실행한다. Python Playwright/Chromium·Pillow·numpy가 필요하다. 기존 캡처 검사는 명세의 운영자 PC handoff 자료를 사용한다. 새 성능/음향 검사는 기본적으로 임시 폴더 `birthday-verify-third`에 JSON을 기록하며 `BIRTHDAY_VERIFY_OUT` 환경변수로 바꿀 수 있다. 제품 소스에는 전역 디버그 훅이 없다. 테스트에서만 응답을 계측한다. 상세 산출물과 커밋 목록은 지시된 handoff `REPORT.md`의 「3차 결과」에 기록한다.

## 모니터 진입 후속 요청 검증 (2026-11-01)

`monitor.html` 초기화 확인창에서 ↑↑↓↓←→←→를 창 밖으로 드래그/터치하면 각 방향 가장자리가 빛난다. 8방향을 마치면 초기화 버튼이 빛나고 창이 닫히며, 리포트의 EXT→APP으로 `./?bday=yuno`에 들어간다. 저장값을 지우지 않는다. 사용 순서는 `BIRTHDAY_SKIN.md` 「모니터에서 시험 화면 열기」를 따른다.

- 순수 검사 11개 전체 통과(기존 10개 + 새 모니터 명령 검사).
- `python scripts/verify_monitor_birthday.py` 통과. 1440×900 마우스와 390×844 Android 터치에서 네 가장자리 빛·버튼 빛·팝업 닫힘·실제 생일 페이지 이동을 확인했다. 터치는 CDP의 실제 touchStart/touchMove/touchEnd로 입력했다.
- 잘못된 방향/탭, 30초 무입력, 라이브 실패→스냅샷 교체 뒤 새 iframe의 탭 연결을 검사했다. 진입 전 생일 음원/장면 자원 요청 0, 진입 뒤 저장값 유지, 정상 되돌리기 버튼의 저장값 초기화도 확인했다. JS pageerror 0.
- 모니터 리포트는 제품의 `monitor_report.render_html`에 빈 테스트 이벤트를 넣어 생성했다. 운영 로그/실데이터를 쓴 캡처는 아니다. 백엔드 소스·배포는 변경하지 않았다.
- 실제 삼성 브라우저는 미확인이다. SamsungBrowser UA·Android 터치 에뮬레이션을 실기기 검증으로 간주하지 않는다. 실제 iPhone Safari 미확인도 유지한다.

산출물은 새 검사 출력 폴더의 `monitor/results.json`, `pc-mouse-edge-*.png`, `android-touch-edge-*.png`, `*-armed.png`에 있다. 가장자리 표시는 드래그 중 즉시 켜지고 손을 뗀 뒤 450ms 유지된다. 방향 입력은 확인창 안에서 시작해야 하며 버튼에서는 시작하지 않는다.

## 운영 반영 확인 (2026-11-01)

- 코드 병합: PR #127, `6969df5871398a2daf12c02e82ee4fb453199db1`. 주석 태그 `v4.11.0`도 같은 병합 커밋에 지정해 푸시했다.
- Vercel 프로덕션: `dpl_HPj2rF2fAeJ8XMN5L8ootsZUKqLm`, READY. 운영 주소 `https://mewtype-schduler.vercel.app/`에서 확인했다.
- `config.js` v4.11.0/2026-11-01, `monitor.html`, 방향 입력 두 모듈, 생일 장면·음악·플레이어·CSS를 포함한 8개 운영 파일이 배포 소스와 일치했다. 두 mp3 모두 첫 1024바이트가 원본과 일치하고 Range 206/전체 크기도 맞았다.
- 배포 후 상세 조작·실제 삼성 브라우저/iPhone 확인은 운영자가 모니터 페이지로 수행한다. 기존 실기기 미확인 표시는 유지한다. 롤백 기준은 `fc6f8ca`다.
