# 생일 이스터에그 감상 이야기·완주 보상 인계

작성: 2026-11-01 KST. **미완성 WIP이며 운영에는 배포하지 않았다.** 사용자가 세션 한도를 고려해 먼저 handoff 작성을 요청했다.

## 1. 작업 위치와 운영 기준

- 저장소: `C:/Users/User/Documents/pyworks/mewtype-scheduler` — 루트는 `main` 유지.
- 현재 작업 브랜치: `feat/birthday-story`.
- 작업 worktree: `C:/Users/User/Documents/pyworks/mewtype-scheduler-worktrees/v4/feat-birthday-story`.
- 시작 커밋/현재 main: `11ef3b57c8deb56cea42c054f616608f0852a19d`.
- 운영 버전: **v4.11.2**, 코드 병합 `ba2b65b10d83c0db319f288b64c1bdd5540b3496`, 태그 `v4.11.2`도 이 코드 병합에 있음.
- v4.11.2 코드 PR #131, 배포 기록 PR #132 완료. 마지막 docs 배포 `dpl_7QqLVtfJiKC2u6UYRDpLT55QirG5` READY.
- 운영 URL: `https://mewtype-schduler.vercel.app/`, 진입: `/monitor.html`. 도메인의 schduler 철자는 그대로 쓸 것.
- 이번 WIP에는 버전/README/CLAUDE/SPEC/VERSION 갱신을 **아직 하지 않았다**. 새 이야기·보상 UI는 저장소 규칙상 마이너 후보(v4.12.0). 이전 v4.11.2는 사용자가 명시적으로 핫픽스로 지정했음. 이번 최종 범위에 맞춰 등급을 정할 것.
- 이 인계는 WIP 커밋으로 해당 브랜치에 보존/푸시한다. 배포·머지 완료로 오해하지 말 것.
- 루트의 untracked `tools/`는 기존 작업 증거·개인 보조 스크립트이다. 통째로 add/삭제 금지.

## 2. 최신 사용자 요구 — 전부 유효

1. 노래를 끝까지 듣고 싶게 하는 예고 → 진행 이야기 → 피날레·감사 카드. 사용자가 제안에 동의했고 구간별 상세 설명을 원함.
2. UFO 스캔 때 밑으로 비추는 빛을 자연스럽게 조정.
3. PC에서 잘리는 유노 사인을 PC/모바일 모두 화면에 맞춰 온전히 표시.
4. 우하단 곡 제목의 `BGM` 글자는 삭제. `♪ 곡 제목` 형식.
5. 새 문구/카드도 PC/모바일에서 잘리지 않게 조절. 작은 화면·가로 화면까지 검증.
6. **가장 최근 추가, 아직 미구현**: 노래를 다 들은 보상으로 플레이바를 확장하고 구분선 뒤에 **폭죽·UFO·사인 등 직접 실행 버튼** 제공.
   - 사용자가 자유롭게 눌러볼 수 있도록 **수동 버튼 실행이 최우선**.
   - 수동 동작 중 기존 고정 이벤트가 겹쳐 발생하지 않도록 억제.
   - 마지막 추가 조작 후 **3초 동안 입력이 없으면** 현재 곡 시각의 고정 루틴으로 복귀.
   - 한 번이라도 해제/열었다면 **해당 브라우저에서 기억**해서 이후 방문에도 제공(localStorage 권장).
7. 최신 요청: 세션 한도 대비 handoff를 우선 작성.

## 3. 사용자에게 설명한 이야기 흐름과 구현 상태

실제 음원 길이: Noctural Run 214.814초, Midnight Groove 214.014초, 합계 약 7분 9초.

| 곡/시각 | 현재 문구/동작 |
|---|---|
| 첫 곡 0:00~0:27 | 기존 일출·17.14초 드럼·19초 인사말 공개, 기존 느린 퇴장 유지 |
| 첫 곡 30~39초 | “오늘 밤의 마지막 선물까지,\n함께 있어 줘.” |
| 첫 곡 134~142초 | “별빛 하나,\n마음을 담아서.” + 작은 별 1개 |
| 첫 곡 203.8~212.8초 | “아직 전하지 못한 선물이 있어.” |
| 둘째 곡 26~34초 | “별빛 둘,\n조금 더 가까이.” + 작은 별 2개 |
| 둘째 곡 175~184초 | “별빛 셋,\n이제 마음을 전할 시간이야.” + 작은 별 3개 |
| 둘째 곡 209초 | 전체 화면·재생 중이면 기존 scene.finale() 1회 |
| 둘째 곡 211초 이후 | 감사 카드: “함께해 줘서 고마워 / 유노의 생일 밤을\n끝까지 빛내 준 당신에게. / Happy Birthday, Yuno.” |

- 카드 버튼 “밤 풍경 더 보기”로 닫는다. 음악은 계속 재생한다.
- 현재 피날레/카드의 1회 상태는 **방문 내 메모리**이다. 최신 요구의 브라우저 영구 해제 상태는 별도로 구현해야 함.
- **중요한 미완성 조건**: 현재 카드 트리거는 단순히 둘째 곡 시각 >=211초이다. 최신 보상 요구에서 “노래를 다 들었다”는 판정으로 그대로 사용하면 선곡/탐색만으로 해제될 수 있다. 두 곡 실제 감상 또는 자연 재생 완료를 추적하도록 보완 필요. 건너뛰기/재진입/반복/정지/유메미타 우선 정지를 테스트할 것. 곡 재생 조작 자체를 금지하는 설계는 아님.

## 4. 현재 WIP 코드 변경

### 새 모듈

- `src/frontend/js/bdaystorylogic.js`: 위 5개 문구의 순수 타임라인과 `birthdayStoryCue(track,time)`.
- `src/frontend/js/bdaystory.js`: `mountBirthdayStory({audio,scene,shell,reduced})`.
  - 오디오 구독 + 재생 중 RAF로 시각을 읽고 문구를 갱신. 정지/숨김 시 RAF를 쉬고 재개.
  - 전체 화면에서만 문구/카드 노출. 일반 화면의 카드는 inert/aria-hidden.
  - 피날레와 카드 방문당 1회, 카드 닫기, 보류 카드의 전체 화면 재진입 표시.
  - destroy에서 RAF·구독·observer·리스너·DOM 제거.
  - 완주 보상 버튼/브라우저 저장은 아직 없음.

### 기존 파일

- `bdayplayer.js`: story 모듈 mount/destroy 연결. 곡 제목 `♪BGM ` → `♪ `.
- `css/bdayplayer.css`: 이야기 문구와 감사 카드 스타일 추가.
  - 줄바꿈·overflow-wrap·화면 안전 여백, 작은 높이(500px 이하)용 작은 글자·패딩.
  - 카드 최대 높이/폭 제한. 테스트 화면에서는 내부 스크롤 없이 전체 표시 통과.
- `bdaylogic.js`: `fitSkySign(view,portrait)` 추가.
  - 전체 사인/UFO/별/글로우 영역을 실제 하늘 viewport 안으로 축소·중앙 배치.
- `bdayscene-yuno.js`:
  - 사인에 PC/모바일 공통 fit 적용. UFO 외부 clip도 실제 skyViewport로 변경.
  - 스캔 광원은 UFO 밑면의 회전에 맞춰 `(sx,sy)` 배치.
  - 폭/이동량을 하늘 너비·광원 높이에 맞춰 제한, 좌우 이동을 느리게, 저채도 시안 투명 cone + 타원형 바닥 glow.
  - 바닥 y=386으로 cone/pool이 지평선 y=395에서 잘리지 않게 여유.
- `bdaysign.js`: 사전 렌더 core/glow 캐시를 550×390 → 614×454로 확장(32px padding), drawImage 위치를 반대로 보정해 획 위치 유지. 캐시 내부 글로우 잘림도 방지.

## 5. 테스트 — 이미 통과한 것과 아직 남은 것

### 통과

- 새 `python scripts/verify_birthday_story.py`.
  - HTTP 서버는 **포트 0(임의 포트)** 사용. 고정 포트 8141은 다른 기존 프로세스가 사용 중이라 처음 테스트에 404가 났음. 다른 프로세스를 종료하지 않고 임의 포트로 해결함.
  - 독립 fixture에서 실제 story 모듈을 가짜 오디오 시각으로 구동.
  - 1440×900, 1920×600, 900×800, 390×844, 360×800, 320×568, 740×360에서 5개 문구 전부 화면 안·수평 overflow 없음.
  - 같은 7개 화면에서 카드 전체 표시(내부 스크롤 없음), 정지 중 피날레 미실행, 재생 중 1회, 카드 닫은 뒤 반복 표시 없음, destroy DOM 정리.
  - 실제 전체 앱/Canvas에서 1440×900, 1920×600, 900×800, 390×844, 320×568, 740×360의 사인 transform 경계·스캔 광원/바닥 경계·곡 제목 BGM 제거 확인, JS pageerror 0.
  - `?bday=yuno&ufo=sign`으로 사인 경로 강제. 테스트 전용 라우트 계측으로 plan/transform을 읽음. 운영 코드에 테스트용 API 추가하지 않았음.
- `BIRTHDAY_VERIFY_OUT=%TEMP%/birthday-story/ui`로 `python scripts/verify_birthday_player_ui.py` 통과.
  - 1440×900, 390×844, 360×800, 320×740에서 기존 인사말·호버·손잡이·재생/볼륨·일반 화면 제어 차단·회전·정리 회귀 통과, JS pageerror 0.
- Node syntax check는 story 모듈에 대해 수행함. **전체 self-check·lifecycle·GPU 성능은 이번 브랜치에서 아직 미실행.**
- 캡처 육안 확인: `390x844-scan.png`, `1440x900-sign.png`, `740x360-card.png`. 사인 잘림 없음, 가로 카드 읽기/여백 양호, 스캔 cone이 UFO 아래에서 출발.

### 산출물

`C:/Users/User/AppData/Local/Temp/birthday-story/`

- `results.json`, `<화면>-card.png`, `<화면>-scan.png`, `<화면>-sign.png`.
- `ui/results.json` 및 기존 UI 검증 PNG.
- Canvas 캡처는 테스트에서 곡을 0초 정지시키므로 `filter:brightness(1)!important`를 **테스트 페이지에만** 주입했다. UI의 시작 안내/일반 화면 오류 표시가 일부 캡처에 남아 있는데 네트워크 fixture/정지 상태 때문이며 운영 UI 검증과 별도이다.

## 6. 다음에 바로 해야 할 일 — 완주 보상/수동 우선 모드

1. **진짜 완주 판정과 브라우저 기억**.
   - 새 전용 localStorage 키(예: `bday-yuno-controls-unlocked-v1`)를 try/catch로 읽기/쓰기.
   - 기존 bday-vol·일반 플레이어 저장값·모니터 초기화 데이터와 분리.
   - 두 곡 재생의 유효 시간/자연 종료를 추적. seek/수동 next만으로 완료되지 않도록. 반복해서 들을 때 중복 시간 누적만으로 건너뛴 구간을 감상한 것으로 세지 않게 할 것.
   - 한 번 해제되면 이후 방문에서 intro 종료 후 바로 확장 제어 제공. 저장 차단 시 이번 방문에는 동작하게.
2. **플레이바 확장 + 구분선 + 효과 버튼**.
   - 기존 왼쪽 손잡이와 재생 버튼은 유지하고 구분선 뒤 폭죽/UFO/사인/(유성 등) 버튼.
   - 모바일은 한 줄을 무리하게 늘리지 말고 두 번째 줄로 확장하는 것이 적절. 기존 CSS `.bday-music__bar` pill/nowrap 전제와 드래그 제한에 높이/폭 변화 반영.
   - `bdayplayerdrag.js`는 현재 타이틀/디스클레이머 위 12px 제한. 확장 상태/브라우저 회전/320px/가로 화면에서 다시 검증.
   - 해제 안내/감사 카드가 확장 바를 가리지 않게. 키보드 접근성, 버튼 클릭이 빈 화면 click/바 드래그로 전달되지 않게.
3. **장면 최우선 수동 모드 API**.
   - scene에 `triggerManual(kind)` 같은 단일 진입점. 오디오 시각·선곡은 바꾸지 말 것.
   - 마지막 클릭 시각을 갱신하고 3초 무입력 시 현재 곡 시각의 정상 루틴으로 복귀. 오래된 이벤트를 대기열로 재생하면 안 됨.
   - 수동 모드 동안 `skyProps`의 고정 유성/오로라/drop, `skyUfos` 고정 UFO/사인, ambient 별/폭죽/유성의 중첩을 억제. 태양/캐릭터/음악 반응 기본 장면은 유지하는 쪽이 자연스러움.
   - 선택한 수동 효과만 별도 재생 시각으로 실행. 반복 클릭 시 사용자 입력 우선으로 교체/재시작.
   - **주의: 사인 원래 그리기 시간이 3초보다 길 수 있음.** “3초 입력 없으면 루틴 복귀”와 충돌하지 않게 수동 사인 연출을 단축해서 3초 안에 완성/잠깐 유지하거나, 사용자 의도에 맞는 명확한 정책을 정할 것. 아무 말 없이 3초 규칙을 무시하지 말 것.
   - 음악이 정지되어 있어도 사용자가 해제된 버튼을 눌러 자유롭게 볼 수 있게 수동 효과 시계는 monotonic wall time 권장. 현재 scene `frame()`은 곡 시각이 안 바뀌면 draw를 생략하므로 manual active 조건 추가 필요.
   - 모션 줄이기, hidden page, destroy/자정 정리, RAF/타이머 누수 검증.
4. 실제 앱에서 완주→해제→새 context 같은 저장값→즉시 보상 제공, storage 차단, 3초 복귀, 연속 클릭, 고정 이벤트 구간 내 수동 실행 우선, 정지 중 실행 테스트.
5. 새 story RAF를 포함해 `verify_birthday_lifecycle.py`를 다시 돌려 destroy 후 생일 리스너/RAF가 0인지 확인.
6. 새 기능 명세·버전·README·CLAUDE 갱신. story/보상 타임라인과 수동 모드 우선순위를 `docs/BIRTHDAY_SKIN.md`, `docs/BIRTHDAY_MUSIC_SCENE_SPEC.md`, `docs/SPEC.md`에 반영. 현재 작업은 이 문서들에 아직 없음.

## 7. 기존 동작·주의점

- 유메미타 플레이어 PLAYING/BUFFERING이 생일 BGM보다 우선. `musicpriority.js` 공유 상태와 `bdayaudio.js` 구독/재생 차단을 유지.
- 일반 화면에 생일 재생 버튼을 다시 만들지 말 것. 생일 전체 화면 컨트롤만 사용.
- 모바일 방향 입력은 팝업 내부 36px 스와이프 허용. 코나미 UUDDLRLR 후 EXT=B → APP=A. 이번 작업과 무관하므로 유지.
- 기존 random sky 계획은 인트로·고정 유성·drop·오로라·UFO/잔상 구간을 피하고 빈 구간에 배치. manual 모드에서는 이 계획도 일시 억제해야 함.
- v4.11.2의 `verify_birthday_sky.py`는 사인 branch를 포함하지 않고 zig를 강제한다. 이번 새 story 검증이 sign도 커버한다.
- 실제 삼성 브라우저/iPhone은 운영자가 직접 확인하기로 한 상태. 에뮬레이션을 실기기로 표현하지 말 것.
- 관련 스킬은 이번 CSS/Canvas 작업에 맞는 항목이 없어 사용/설치하지 않았음. 외부 이미지 생성도 불필요.
- 사용자는 진행에 따라 상세 설명을 원한다. 새 보상 UI와 3초 우선권 정책도 이해할 수 있게 설명할 것.
- 새 sub-agent는 사용자가 요청하지 않았으므로 만들지 말 것.

## 8. 릴리스 절차(완성 후)

사용자는 이전부터 검증 후 머지·배포를 승인해 왔다. 이 WIP는 완성되지 않았으므로 현재 배포하지 않음. 완료 시 세션 내 승인 범위를 고려해 기존 절차를 이어갈 것.

- root main 유지, 별도 worktree에서 작업. 한국어 커밋/설명과 Co-Authored-By: Codex <noreply@openai.com>.
- PR merge commit, 정확한 head/체크 SUCCESS 확인. 버전 태그는 **코드 병합 커밋**에만 주석 태그로 올리고 이름을 지정해 push. `push --tags` 금지.
- 배포 완료 기록은 별도 docs PR에서 tag 표·배포/롤백 확인 기입.
- Vercel root `src/frontend`, main 자동 배포. 루트 `.env`의 VERCEL_TOKEN을 출력하지 말 것.
- 재사용 가능한 read-only helper: 루트 `tools/birthday-continuation/release_status.py`.
- 예전 `finish_*release.py`, `prepare_*release.py`는 특정 버전/해시/브랜치 하드코딩이므로 **그대로 실행 금지**.
- 운영 파일을 새 code merge SHA query로 요청해 로컬 파일과 UTF-8/개행 정규화 비교. READY만으로 끝내지 말 것.
- 미관련 docs PR #122/#124는 그대로 두었음. 병합할 필요 없음.
- 완성 후 자기 worktree만 clean+main에 merged 확인하고 절대 경로가 지정한 worktrees/v4 아래인지 확인한 뒤 제거. root tools/와 다른 worktree는 보존.

## 9. 다음 세션 시작 요약

**이 문서와 feat/birthday-story를 읽고, 최신 완주 보상 제어 버튼부터 구현하라. 이야기/사인/스캔/BGM 표기 보정은 WIP 구현 및 일부 브라우저 검증 완료. 보상 해제·영구 기억·수동 최우선 실행/3초 복귀는 전부 아직 없다. 버전/릴리스 문서도 아직 갱신 전이며 main/운영은 안전하게 v4.11.2 그대로다.**
