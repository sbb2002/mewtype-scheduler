# UFO 돔 디자인 시안 · 11월 20일

기준 `5599a2e` · 작업 브랜치 `test/bg-dome-design-1120` · 커밋 `57d36a4`. 시안 캡처는 이 문서와 같은 폴더에 있다. Chrome 모바일 390×844, 로컬 8143, 샘플 예고 데이터와 소프트웨어 WebGL로 검증했다. 시선에는 디버그 방위를 썼고, 후반 보상은 해당 해금 상태를 준비한 별도 세션에서 재현했다.

## 과제별 결정과 근거

| 과제 | 시안 | 근거 · 선택지 |
| --- | --- | --- |
| 1. WARP 대기 | 속도계 옆 한 칸에 **가속 중 → 워프 준비 → 출발 가능**. 출발 가능은 청록 테두리와 실제 버튼 활성화가 함께 바뀐다. 사진 요청 중에는 **목적지 준비**와 비활성 버튼을 표시한다. | 경보가 울리는 이유와 조종자가 기다려야 하는 이유를 구별할 최소 문구다. 지연한 이미지 응답에서 준비 상태를 캡처했다. `bggear.js`, `bgdomegl.js`. `design_codex_07_acceleration.png`, `design_codex_08_warp_preparing.png`, `design_codex_09_warp_ready.png`, `design_codex_10_warp_loading.png`. |
| 2. 도착과 하늘 전환 | 전환 후 시점을 콘솔에서 조금 물러난 위치로 돌려 하늘과 시선 HUD를 먼저 보인다. 다시 접근하면 기존 홀로그램 패널이 열린다. | 이전에는 워프마다 조작 패널이 떠 다음 표식에 응시해도 진행하지 않았다. 기본 우주 전환 및 실제 WARP 도착에서 패널이 숨은 상태와 줌 목표 0.4를 확인했다. 대안은 카메라 거리를 유지하고 작은 콘솔 버튼만 띄우는 방식이다. `bgdomegl.js`. `design_codex_05_clear_sky.png`, `design_codex_11_warp_arrival.png`. |
| 3. 접근과 망원 | 두 손가락 벌리기는 콘솔까지의 접근에 쓴다. 정보 카드의 기존 **＋ 확대**를 눌러 망원으로 들어가고, 버튼 또는 오므리기로 돌아온다. | 표식이 잡혔다는 우연한 상태 변화가 핀치의 의미를 바꾸는 문제를 없앴다. 토성에서 두 손가락과 카드 확대를 각각 실행했다. `bgdomegl.js`, `bghud.js`. `design_codex_03_pinch_panel.png`, `design_codex_04_tele.png`. |
| 4. 첫 방문과 다시 보기 | 레인 이동 시연 뒤 주소 복사 안내를 띄우고, 테마 길게 누르기와 손짓 안내는 보이는 안내와 겹치는 동안 기다린다. 손짓은 보이는 활성 레인의 안전한 빈 위치를 찾아 가리킨다. 배경 테마 메뉴에 **배경 보기**, **손짓 다시 보기**를 둔다. UFO 하늘을 눌러도 예고보드로 돌아가지 않으며 왼쪽 위 **‹ 예고보드**로 나온다. | 카드와 제스처 경쟁을 피하면서 좁은 빈 공간을 거치지 않고도 들어갈 수 있게 두 개의 조작을 추가했다. 자동 손짓은 15초 후 접고 실제 진입 시에만 확인을 기록한다. 대안은 별도 진입 버튼 없이 다시 보기만 두는 방식이다. `bgpeek.js`, `bgview.js`, `longcopy.js`. `design_codex_01_theme_actions.png`, `design_codex_02_cue.png`, `design_codex_11_warp_arrival.png`. |
| 5. 지구 위치 권한 | 지구 타일 아래에 현재 위치의 해·달을 맞추기 위해 권한을 쓴다고 한 줄로 설명한다. 실패 후 지구 타일을 다시 누를 수 있다. 이미 배경 보기 중에는 폰을 들어 해·달을 보라는 안내만 표시한다. | 브라우저의 초기 거절, 타일 유지, 권한 허용 후 같은 타일로 재시도를 헤드리스에서 재현했다. 실제 기기의 시스템 권한 팝업과 방향 센서는 별도 확인이 필요하다. `bgpanel.js`, `bgview.js`. `design_codex_14_location_and_nav.png`, `design_codex_18_location_retry.png`, `design_codex_19_location_success.png`. |
| 6. 해금과 보상 | 도형 착지 때 콘솔 화면이 반짝이고, 별빛 조명 해금에는 바닥색이 한 번 더 밝아진다. 달 궤도의 첫 WARP는 **새 신호**, 지구 보상 알림은 4.6초. 지구에서 첫 YMMT는 현재 시선에 배치하고 그림이 읽히는 프레임까지 표시 여부를 저장한다. 자유 항해에는 **기본 우주**를 넣었다. | 짧은 빛 반응으로 발견과 콘솔을 연결했다. 달 첫 선택, 달에서 지구 잡기, 지구의 첫 YMMT 저장, 달 재방문과 기본 우주 복귀를 실제 클릭으로 확인했다. 착지 광량과 실기기에서의 감상은 확인 필요. 움직임 줄이기 설정에서는 YMMT 애니메이션을 생략한다. `bgconsole.js`, `bgpanel.js`, `bgfx.js`, `bgdomegl.js`. `design_codex_12_moon_signal.png`, `design_codex_13_earth_unlock.png`, `design_codex_15_ymmt.png`, `design_codex_16_return_to_space.png`. |
| 7. 효과음 | 아래 후보와 배치안을 제안한다. | 새 소리는 승인 뒤 청음과 삽입을 진행한다. |
| 8. 플레이어 BGM | 하늘의 오른쪽 위에 **♪ 곡 제목**. 사용자가 누르면 `playRecommendedSong(id)`가 곡을 찾아 기존 재생 경로로 보낸다. 기존 재생이나 시작 요청이 있으면 건드리지 않고, 곡이 흐를 때 칩은 접힌다. | 초행성X·오리온·별자리 정보 카드·달 궤도·지구 보상에 각각 추천한다. 재생 상태 전환과 음악 테두리를 확인하고, 재생 중 다른 추천 호출이 곡을 바꾸지 않는 것을 확인했다. `bgdomegl.js`, `player.js`. `design_codex_06_recommendation.png`, `design_codex_17_music_playing.png`. |

## 효과음 선택안

| 후보와 라이선스 | 적용 자리 |
| --- | --- |
| Kenney **Interface Sounds**, CC0 | 레인 걷힘이 끝날 때 부드러운 짧은 클릭, 패널이 열릴 때 건조한 버튼 클릭, 기어 단이 실제로 바뀔 때 낮은 클릭. 길게 누르는 동안은 게이지를 중심으로 두고 시작과 완료에만 짧은 소리를 넣는 안. [Kenney Interface Sounds](https://kenney.nl/assets/interface-sounds) |
| Kenney **Sci-fi Sounds**, CC0 | 하늘 전환의 경계가 지나갈 때 짧은 스윕, 도착에 잔향이 적은 짧은 종결음, 시선 잡힘과 콘솔 착지에 같은 질감의 짧은 신호음. [Kenney Sci-fi Sounds](https://kenney.nl/assets/sci-fi-sounds) |
| Kenney **Music Jingles**, CC0 | 현재 팡파르를 교체한다면 지구 해금과 별빛 조명에만 짧은 종결음을 후보로 검토. 자주 울리는 발견음은 Sci-fi Sounds 계열로 묶어 질감을 맞춘다. [Kenney Music Jingles](https://kenney.nl/assets/music-jingles) |
| bbrocer **Digital Alarm Loop.wav**, CC0 · 기존 `alarm.wav` | 5단 첫 진입에서 짧게 알리고 계속 켜진 구간의 반복은 줄인 뒤, 워프 준비 상태 전환에만 한 번 더 알리는 안. [Freesound 원본](https://freesound.org/people/bbrocer/sounds/389511/) |
| DylanTheFish **Warp Speed.wav**, CC0 · 기존 `warp-jump.m4a` | B의 도착은 0초인데 120ms 페이드인이 첫 절정을 누른다. B에서만 짧은 페이드로 기존 소스의 충격을 살리는 안과, 도착 소리를 따로 얹는 안을 청음 비교할 수 있다. [Freesound 원본](https://freesound.org/people/DylanTheFish/sounds/454683/) |

Kenney 후보는 공식 배포 묶음 단위로 선정했다. 세부 파일 청음·최종 선택은 확인 필요. 추천은 **조작 확인 → 시선 잡힘 → 보상의 끝음** 세 층만 먼저 맞추고 반복 경보를 줄이는 조합이다.

## 추천 곡 배치

정적 `assets/songs.json`의 제목 및 대표 ID를 사용한다. 초행성X는 **超惑星Xへの旅**, 오리온은 **オリオンをなぞる**, 멤버 별자리는 **ホシアイ**, 달 궤도에서 바라보는 지구는 **地球最後の告白を**, 지구의 최종 보상은 **Dream Voyage**로 시안에 넣었다. 보상을 그룹 정체성에 더 연결하려면 **アイの夢限**이 대안이다. 첫 세션에서 추천 칩을 누른 동작이 재생을 시작했으며, 음악 재생에 따른 기존 효과음 감쇠와 음악 테두리도 기존 경로를 사용한다.

## 검증

관련 모듈 self-check 15개, 변경 JS 문법 검사, `git diff --check` 통과. 모바일 브라우저에서 메뉴와 배경 보기 진입·이탈, 토성·성운, 망원, 네 WARP 상태, 도착, 위치 재시도, 보상 경로와 YouTube 재생을 검증했다. 실기기 터치·센서와 움직임 줄이기 설정의 체감, 새 음원 청음은 확인 필요.

END
