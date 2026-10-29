# 라이브 시작 알림 — 경과 · 인계 (2026-10-29)

다른 세션이 이어받기 위한 문서. 결정 · 조사 · 시험판 상태 · 남은 일을 한곳에 모았다.
**아직 기획 · 시험 단계** — 운영 반영(구현 착수 · 병합 · 배포) 지시는 없다.

용어(이 문서에서 처음 쓰는 것 — 본 구현 때 `docs/TERMINOLOGY.md` 에 올릴 것)
- **멤버 종*** — 네임플레이트 핸들 옆 종 아이콘. 누르면 그 멤버의 모든 라이브(upcoming 이상으로 등록되는 영상)가 live 로 들어갈 때 알림.
- **방송 종*** — 영상이 확정된 예고 카드(upcoming · watching)의 종 아이콘. 누르면 그 방송 하나가 live 로 들어갈 때 알림.
- **구독*** — 브라우저 하나의 Web Push 등록(푸시 주소 + 키). 로그인 없음 — 「이용자」 = 브라우저 단위.
- **실험실*** — 로컬 시험 서버 `lab/push/server.py`(팬 화면 + 서버 쪽 보기 `/lab`).

---

## 1. 요구 (운영자)

1. 팬이 **알림 단추를 1번 누르면 등록이 끝나야 한다** — 예상 밖 추가 동작(다른 사이트로 가서 또 누르기 등)은 무의식적 불쾌감 → 이탈 요인.
2. 목표 단계(높을수록 좋음): **#1** 브라우저 프로세스가 꺼져도 · **#2** 사이트를 나가도 · **#3** 사이트는 열려 있지만 다른 탭을 볼 때 · **#4** 사이트를 보고 있을 때만.
3. 화면은 어떤 경우에도 같게 동작해야 한다 — 이용자는 서버 오류(429 등)를 알 필요가 없고 「적용됐는지」만 중요. 서버는 눈속임을 하더라도 버스트를 막으며 의도대로 동작하게.
4. 무료 인프라만. 디스클레이머를 고쳐야 할 만큼 외부 수집이 생기는 안은 보류.

## 2. 결정 경과 (모두 2026-10-29)

| 안 | 결과 | 이유 |
|---|---|---|
| 구글 캘린더 공유 | **폐기**(알림과 별개 주제) | 운영자: 결국 GCP 프로덕트화 + 개인 도메인 필요 → 앱 정책 위반(BPM 프로젝트 경험) |
| 유튜브 「알림 설정」 · 채널 종으로 유도 | 반려 | 클릭 2번(요구 1 위반). 공식 API(YouTube Data API)에 종 단계 · 예정 방송 알림 설정 기능 없음(`subscriptions` 리소스 확인) |
| A. 프론트만(페이지 타이머 · 75초 폴링으로 감지) | 한계 확인 | PC Chrome 데모에서 동작, **탭을 닫으면 안 옴**(운영자 확인). 페이지 코드가 사라지고, 서비스 워커는 스스로 깨어나지 못함(약 30초 유휴 후 종료). 최대 #3 |
| B. Web Push(서버 발송) | 처음엔 반려 → **채택** | 데모에서 탭 닫아도 옴(운영자 확인). 처음엔 GCP 버스트 · 공격 부담으로 반려했으나 OneSignal 보류 뒤 「15~16명 규모면 GCP 직접이 낫다」로 선회 |
| C. 이용자 PC 에 로컬 서버 | 불가 | 웹 페이지는 프로그램을 설치 · 실행할 수 없음 → 설치형 앱이 됨, 모바일 불가 |
| OneSignal 위탁 | **보류** | 무료(웹 푸시 구독자 무제한 · 한 번에 1만 명 · 월 발송 무제한)지만 한국 방문자 IP · 식별자 저장, 유럽 보관 · 미국 접근(국외 이전) → 디스클레이머 수정 필요, 수집 조건이 마음에 안 듦 |
| 저장소 | **Firestore**(GCP) | 구독 1개 = 문서 1개라 동시 쓰기 문제 없음 → 「모아서 한 번에 커밋」 장치 불필요. 비공개 GitHub 저장소는 요청마다 커밋 충돌 · 묶음 장치 필요 |
| 연타 방어 | **프론트 몫** | 화면은 누를 때마다 즉시 바뀌고, 마지막 조작 뒤 2초 조용하면 최종 상태 1건만 전송. 「2초 동안 단추 무반응」식 쿨타임은 화면이 다르게 동작해 채택 안 함 |
| 서버 방어 | **최소** | 응답은 늘 202, 크기 · 형식 오류 조용히 버림, 내용 같으면 안 씀, 하루 쓰기 상한. 입장 대기열 · 반영 주기 등 대량 공격 전용 장치는 뺐다(공격 논의 때 재판단) |
| 서비스 배치 | 미결 | 운영자 구상 = 이용자 1000명 이상이면 텔레그램 서비스처럼 **알림 전용 Cloud Run 서비스** 분리. Claude 의견 = 공격 위험은 이용자 수와 무관하니 공개 등록 주소를 여는 시점부터 분리 권장 |
| 종 색 | 확정 | 켜진 종은 모두 아라레 레인 색 `rgb(225 187 139)`(아라레 아바타 평균색 — `render.js` `sampleLaneColor` 와 같은 계산) |

## 3. 조사 요약

### 방문자 (Vercel Analytics, 최근 30일 · 145명 — 2026-10-29 확인)
Samsung Browser 48% · Chrome(PC) 24% · Chrome Mobile 17% · Mobile Safari 6% · Safari 4% / Android 63% · Windows 26% · iOS 6% · Mac 4% / 모바일 68%. 일 방문 평균 15~16명(운영자). Hobby 요금제라 30일까지만 보이고 사용자 지정 이벤트(클릭 수) 없음.

### 브라우저별 도달 가능 단계 (웹 조사 — 업체 자료끼리 갈리는 곳은 「확인 필요」)

| 환경 | 프론트만 | Web Push | 비고 |
|---|---|---|---|
| Android Samsung Internet | 실질 #4 | #2 확실, #1 **확인 필요** | 화면 끄면 뒤 탭 정지. 꺼진 상태 수신은 자료가 갈림 |
| Android Chrome | 실질 #4 | #1 | OS 가 푸시로 브라우저를 깨움(web.dev). 강제 중지 · 제조사 절전은 예외 가능 |
| Windows Chrome · Edge | #3 | #2, #1 조건부 | 숨긴 탭 타이머 5분 뒤 1분 1회. 창 다 닫은 뒤 수신은 「백그라운드 앱 계속 실행」 필요(기본값 꺼짐으로 보임 — **확인 필요**) |
| Mac Chrome | #3 | #2 | ⌘Q 로 종료하면 못 받음 |
| Mac Safari 16+ | #3 | #1 | webpushd 가 Safari 없이 받음(WebKit 공식) |
| iOS Safari 탭 | 없음 | 없음 | 탭에선 권한 요청 불가 |
| iOS 홈 화면 설치판(16.4+) | #4 | #1 | manifest + 설치 안내 필요 |
| 인앱 브라우저(카톡 · 디시 등) | 없음 | 없음 | Android WebView 에 Push · Notification API 없음. 카톡 자체는 **확인 필요** |

받지 못한 푸시는 푸시 서버가 보관했다가 브라우저를 켤 때 전달 → **TTL 을 짧게(시험판 30분)** 해서 끝난 방송 알림이 늦게 뜨지 않게.

### Firestore 무료 한도 (Standard, 프로젝트당 DB 1개, 태평양 시간 자정 리셋)
읽기 5만 · 쓰기 2만 · 삭제 2만 / 일. 우리 프로젝트는 Cloud Run 때문에 결제 계정이 붙어 있어 **넘으면 차단이 아니라 과금**(결제 계정 없을 때만 차단으로 보임 — 확인 필요) → 서버 하루 쓰기 상한 + GCP 예산 알림 권장. 저장 1GiB 는 공식 문서 재확인 못 함.

### 디스클레이머 영향 (미해결)
자체 Web Push 도 구독(브라우저별 고유 푸시 주소)과 「어느 멤버 · 방송을 등록했는지」를 저장한다. Cloud Run 요청 로그는 접속 IP 를 기본으로 남긴다(로그 제외 설정으로 끌 수 있음). 지금 고지(`src/frontend/index.html` 「개인을 식별할 수 있는 정보는 저장하지 않습니다」)를 그대로 두기 어려울 수 있음 — **운영자 판단 필요**(OneSignal 보류 기준이 「디스클레이머 수정」이었으므로).

## 4. 시험판 상태

### 데모 (scratchpad, 저장소 밖)
1분 뒤 알림 A(페이지 타이머) · B(Web Push) — PC Chrome 에서 운영자가 둘 다 동작, A 는 탭 닫으면 안 옴 확인. 폐기해도 됨.

### `test/live-notify` 브랜치 (최신 커밋 `43d3f4b`, origin 푸시됨 · 워크트리 `mewtype-scheduler-worktrees/v4/test-live-notify`)
- 실행: `lab/push/README.md` — Firestore 에뮬레이터(`gcloud emulators firestore start --host-port=127.0.0.1:8085`) + `FIRESTORE_EMULATOR_HOST=127.0.0.1:8085 python lab/push/server.py`, 또는 에뮬레이터 없이 `python lab/push/server.py` → 팬 화면 `http://localhost:8770/` · 서버 보기 `/lab`.
  이 PC 엔 2026-10-29 Java(Temurin 21) · `cloud-firestore-emulator` 설치함. 에뮬레이터가 Java 21 지원 종료 예고 경고를 냄(지금은 동작) — 막히면 Java 25 이상.
- 프론트
  - `src/frontend/js/push.js` — 종 생성 · 켬/끔(localStorage `mew.push.v1`) · 2초 묶음 전송 · 오류 시 2→60초 재전송 · 페이지 열 때 1회 재전송 · upcoming/watching 아닌 영상 등록 정리.
  - `src/frontend/sw.js` — push 받으면 알림, 누르면 방송 주소 열기.
  - `src/frontend/css/push.css` — 종 모양 · 색(`--push-bell-on`).
  - 종 위치: 멤버 종 = 네임플레이트 핸들 옆(`render.js buildHeader`). 방송 종 = 오늘 카드 썸네일 왼쪽 아래(`timetable.js todayCard`) · 이후 예고 카드 썸네일 오른쪽 아래(`render.js createCard`) · PC 타임테이블 팝업 「YouTube에서 보기」 아래(`timetable.js showCardPop`).
  - 네임플레이트를 누르면 열리던 트윗 시트는 그대로, 종만 건너뛰게 `tweets.js` 캡처 핸들러에 한 줄.
- 실험실 서버 `lab/push/server.py`
  - 저장소 두 구현이 같은 연산(get · set · delete · `array-contains-any`)만 쓰고 연산 수(읽기 · 쓰기 · 삭제)를 센다: `FirestoreStore`(실제 클라이언트, `FIRESTORE_EMULATOR_HOST` 있을 때, 컬렉션 `push_subs`) · `DocStore`(로컬 파일 `.data/subs.json`). 문서 id = 푸시 주소 SHA-256 앞 16자. 에뮬레이터가 비어 있으면 로컬 파일 구독을 옮겨 심음.
  - `POST /push/state`: 늘 202. 크기(4KB) · 형식(푸시 주소 도메인 · 멤버 5명 · 영상 30개 · video_id 11자) 오류 버림 → 읽기 1 → 같으면 안 씀 → 하루 쓰기 상한(`LAB_WRITE_CAP`, 기본 1만) → 쓰기 또는 해지(삭제).
  - `/lab`: 방송 상태 바꾸기(→ live 면 감지 · 발송), 시험 방송 만들기, 등록 현황 · 연산 수, 서버 기록, 버스트 시험(curl 흉내 연타 · 가짜 1500개 · 10KB).
  - 발송: live 전이 순간 조회 2번(멤버 · 영상) → `pywebpush`(TTL 30분), 영상당 1번, 404/410 이면 문서 삭제.
- 확인한 것: 종 렌더(카드 보기 · 오늘 카드) 스크린샷, 프론트 self-check(render · time · timetable · tweetlogic) 통과, curl 로 늘 202 · 같은 내용 안 씀 · 형식 오류 · 4KB 초과 · 해지 삭제 동작. 운영자 브라우저 구독 1개(아라레 · 미야코 · 유노)가 저장소에 들어와 있음 = 종 → 등록 경로는 실제로 동작.
- Firestore 에뮬레이터로 확인: 쓰기 · 같은 내용 안 씀 · live 전이 때 `array-contains-any` 조회(가짜 구독은 조회되지만 발송 제외) · 운영자 구독 옮겨 심기.
- **확인 안 한 것**: 종으로 등록한 뒤 `/lab` 에서 live 로 바꿨을 때 실제 알림 수신(운영자 보고 없음), 모바일 실기기, 실제 GCP Firestore(에뮬레이터만).

## 5. 운영자 결정 대기

1. 방송을 새로 판 경우(예약 삭제 후 재생성 · 방송 불량 재개설 = 새 video_id) — 등록 승계 규칙 · 승계 창(±45분 재활용? end 창 30분?) · 다시 알릴지. **지금 end 로직은 같은 영상만 복구**(`statemachine.py` end 분기 D6) — 영상→영상 승계는 없음.
2. 회원 전용 방송도 알릴지(시험판은 알리고 기록에 표시).
3. 알림 전용 서비스를 처음부터 분리할지(위 2절).
4. 디스클레이머 문구(위 3절).
5. 공격 논의(운영자가 「공격 논의 전에 기능부터」로 미뤄 둠) — curl 대량 등록 · 가짜 구독 판별 등.

## 6. 운영 이행 시 할 일 (본 구현 착수 때)

- 버전 등급: 새 요소 → **마이너**(`main` 다음 마이너). 계약은 `docs/SPEC.md` 먼저(구독 문서 스키마 · 종 DOM class · `/push/*` API).
- 백엔드: 알림 서비스(Cloud Run) — `/push/vapid` · `/push/state`(Firestore 문서 쓰기, 하루 쓰기 상한) · 발송 작업. live 감지는 쓰기 서비스 tick/wake 의 상태 전이(`handlers._preview_log_events` 에서 `→ live`)에서 **Cloud Tasks 로 발송 작업만 넣고** 실제 발송은 알림 서비스가(쓰기 서비스는 concurrency=1 이라 그 안에서 등록자 수만큼 보내면 다른 쓰기가 막힘). 영상당 1번 보냄 기록도 Firestore 에.
- 비밀: VAPID 개인 키 → Secret Manager. 공개 키는 프론트에 넣거나 `/push/vapid`.
- 프론트: 운영에선 API 가 다른 출처(Cloud Run) → `push.js` `PUSH_API` 와 서버 CORS(Vercel 주소만). `sw.js` 는 `src/frontend/` 루트(스코프 `/`). iOS 용 manifest · 설치 안내.
- 로그: Cloud Run 요청 로그의 IP 를 남기지 않으려면 로그 제외 설정.
- 문서: SPEC · TERMINOLOGY(위 용어) · VERSION · README · CLAUDE.md 현재 버전 · `config.js APP_VERSION`.
- 실기기 확인: Samsung Internet 꺼진 상태 수신, Android 화면 끈 상태, Windows Chrome 백그라운드 설정, iOS 홈 화면판, 카톡 인앱.

## 7. 출처 (조사 때 본 것)
- YouTube 알림: support.google.com/youtube/answer/3382248 · /9080341 · /9879686, developers.google.com/youtube/v3/docs/subscriptions
- 브라우저 동작: web.dev/articles/push-notifications-faq, developer.chrome.com/docs/web-platform/page-lifecycle-api · /blog/freezing-on-energy-saver, webkit.org/blog/12945 (Meet Web Push) · /13878 (iOS), pushpad.xyz 블로그, OneSignal 브라우저 동작 FAQ
- OneSignal: onesignal.com/pricing · /blog/understanding-onesignals-pricing · /privacy_policy, documentation.onesignal.com (rate-limits · data-collected-by-the-onesignal-sdk · handling-personal-data)
- Firestore: firebase.google.com/docs/firestore/quotas, docs.cloud.google.com/firestore/quotas
