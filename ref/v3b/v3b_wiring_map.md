# v3b 배선 정리 — 현행(v3.8.10) 배선 지도

- 작성: 2026-09-26 (브랜치 `refactor/v3b-wiring`, 기준 커밋 `origin/main` `6af6db7`)
- 목적: v3b(이전 버전과 호환되지 않는 배선 정리) 착수 전, **현재 실제로 연결된 배선**을 출발→도착 기준으로 전부 기록.
- 근거: 현재 코드를 직접 읽어 확인(`src/backend/*.py`, `src/frontend/*`), Cloud Scheduler 잡 목록은
  `gcloud scheduler jobs list`로 확인. 추정이 섞인 항목에는 **(확인 필요)**를 달았다.
- 용어는 `docs/TERMINOLOGY.md` 기준. "제어 채널" = `mewtype-telegram`, "백엔드" = `mewtype-backend`.

---

## ① 들어오는 입구 (외부 → 백엔드)

| # | 출발 | 도착 | 인증 | 페이로드 | 기능 |
|---|---|---|---|---|---|
| E1 | 운영자 폰 Automate (X 알림) | 제어 채널 `POST /ingest` | `X-Ingest-Secret` 헤더 | form/JSON `text`·`title`·`template`·`tag` | 공식/개인 트윗 → preview·notice·tweet 분기 |
| E2 | 운영자 폰 Automate (YouTube 앱 알림) | 같은 `POST /ingest` (`source=yt`) | 같음 | 같음 | 회원 전용 라이브 시작 → yt-dlp 조회 → preview live |
| E3 | 텔레그램 Bot API (운영자 DM) | 제어 채널 `POST /telegram` | `X-Telegram-Bot-Api-Secret-Token` + `chat_id` 검사 | 텔레그램 update | 명령 `/list /ingest /edit /del /undo /translate /notice… /pause /resume /monitor` |
| E4 | Cloud Scheduler `mewtype-light` (`*/10`, UTC) | 백엔드 `POST /tick` (light) | OIDC | `{mode}` | RSS + `videos.list` → preview 재구성 **외 다수** (④ 참고) |
| E5 | Cloud Scheduler `mewtype-baseline` (06:00 JST) | 백엔드 `POST /tick` (baseline) | OIDC | `{mode:"baseline"}` | light와 동일 + 아바타(`channels.list`)만 추가 |
| E6 | Cloud Scheduler `mewtype-monitor` (06:10 KST) | 백엔드 `POST /monitor` | OIDC | — | 모니터링 스냅샷 + `latest.html` + 멤버 현황 DM |

## ② 서비스 간 내부 배선

| # | 출발 | 도착 | 방식 | 기능 |
|---|---|---|---|---|
| I1 | 백엔드 `/tick`·`/wake` | Cloud Tasks → 백엔드 `POST /wake {video_id}` | Tasks + OIDC | 방송별 정밀 확인 (시작 −3분, watching·live·end 창) |
| I2 | 백엔드 `/tick`·`/wake` | Cloud Tasks → 백엔드 `POST /tick` light | Tasks + OIDC | ① 영상 없는 예고 시각에 맞춘 tick ② 방송 종료 후 재확인 tick. **Scheduler 말고도 tick을 부르는 두 번째 호출자** |
| I3 | 제어 채널 (`/ingest`·`/telegram`) | 백엔드 `POST /write {kind,args}` | 동기 HTTP + OIDC, 429/503 재시도 | data 콘텐츠 쓰기 직렬화 (`merge_rows`, `url_confirmed_commit`, `personal_tweet`, `apply_notice`, `remove_broadcast`, `undo_restore`, `apply_preview_edit`, `ingest_queue_*` 등) |
| I4 | 백엔드 `/write` 잡 (URL 확정·회원 라이브 등) | Cloud Tasks → 백엔드 `/wake` | Tasks | 등록 즉시 wake 예약 (`_enqueue_wake_now`) |
| I5 | 제어 채널 `/resume` | 백엔드 `POST /tick` light | 동기 HTTP + OIDC | 재개 직후 즉시 한 바퀴 |
| I6 | 백엔드 `/write` 잡 `apply_preview_edit` (`/edit` 상태 변경, 영상 있는 항목) | **백엔드 자기 자신** `POST /wake` | 동기 HTTP + OIDC | 즉시 재확인. **(확인 필요)** 백엔드는 `concurrency=1·max-instances=1`이라 `/write` 처리 중 자기 `/wake`를 부르면 429로 거절될 가능성이 높다 |

## ③ 저장소 배선 (GitHub Contents API, 데이터 저장소 `sbb2002/mewtype-scheduler-data`)

| # | 파일 (브랜치) | 쓰는 쪽 | 읽는 쪽 | 비고 |
|---|---|---|---|---|
| S1 | `preview.json`·`preview_archive.json` (data) | 백엔드 `/tick`·`/wake` 직접 + `/write` 잡 | 백엔드, 제어 채널, **프론트** | 쓰는 쪽이 두 갈래(tick 직접 쓰기 + 쓰기 큐) |
| S2 | `notices.json`·`notice_archive.json` (data) | `/write` 잡 + tick 번역 sweep + **제어 채널 `/translate` 직접** | 백엔드, 제어 채널, **프론트** | `/translate`는 직렬화 창구를 **우회** |
| S3 | `tweets.json`·`tweet_archive.json` (data) | 위와 같음 (`/write` + tick 번역 + `/translate` 직접) | 백엔드, 제어 채널, **프론트** | 같은 우회 |
| S4 | `admin_state.json` (data) | 제어 채널 **직접** (15곳) | 제어 채널, 백엔드 tick (suppress·편집 락) | 대화 마법사·undo 스냅샷·편집 락 |
| S5 | `control.json` (data) | 제어 채널 **직접**, `prev_sha=None` (충돌 검사 없는 덮어쓰기) | 양쪽 전부 | pause, 로그 레벨, monitor_auto |
| S6 | `ingest_queue.json` (data) | `/write` (`ingest_queue_push`·`drain`) | 제어 채널 | v2.3 ECHO/DRY-RUN 시절 잔재인데 `/ingest` 때마다 drain 경로가 살아 있음 |
| S7 | `monitoring/events-*.jsonl`·`lost_queue.json` (monitoring) | 양쪽 **직접** | 백엔드 `/monitor`, 제어 채널 `/monitor-live` | v3.9에서 브랜치 분리 |
| S8 | `monitoring/latest.html`·`days/`·`summary.json` (monitoring) | 백엔드 `/monitor` + **제어 채널도 `latest.html` 씀** | 프론트 `monitor.html` (폴백) | 같은 파일을 쓰는 쪽이 둘 |

## ④ `/tick`·`/wake`(공용 `handlers._run`) 안에서 한 번에 도는 일

| 단계 | 대상 | 원래 역할과의 관계 |
|---|---|---|
| RSS + `videos.list` → `build_preview` | preview | **본연** (tick만 RSS, wake는 추적 중인 미해결 항목 전부) |
| `apply_overrides` (트윗 시각 우선) | preview | 트윗 경로의 후처리가 tick에 얹힘 |
| suppress·편집 락 반영 | preview ← admin_state | 운영 명령의 후처리가 tick에 얹힘 |
| 아카이브 이관 | preview_archive | 본연 |
| Cloud Tasks 예약 (I1·I2) | Tasks | 본연 + tick 자기 재호출 |
| **LLM 번역 재시도 sweep** | notices·tweets·preview | **무관** (tick에서만 실행) |
| 텔레그램 알림 · 모니터 로그 · healthcheck 핑 | 외부 | 부수 |

## ⑤ 외부 조회 배선 (백엔드 → 외부)

| # | 출발 | 도착 | 기능 |
|---|---|---|---|
| X1 | 백엔드 tick | YouTube RSS (`feeds/videos.xml`, 6채널) | 새 영상 발견 (쿼터 0) |
| X2 | 백엔드 tick·wake, 제어 채널 (URL 확정) | YouTube Data API `videos.list` / `channels.list` | 영상 상태·시각 확정 / 아바타 |
| X3 | 제어 채널 | yt-dlp (채널 streams 탭) | 회원 전용 라이브 video_id 조회 |
| X4 | 제어 채널 (준비 단계), 백엔드 (번역 sweep) | Groq LLM (`gpt-oss-120b`/`20b`) | 번역·소식 제목·참여/합동/예고 판정·중복 판정 |
| X5 | 제어 채널 | Groq 비전 (qwen) + 텔레그램 `getFile` | 공지 이미지 OCR |
| X6 | 제어 채널 | vxtwitter → 실패 시 fxtwitter | 트윗 원문·미디어·인용 복원 |
| X7 | 양쪽 | Telegram `sendMessage`/`sendDocument` | 운영 DM |
| X8 | 백엔드 tick, 양쪽 모니터 | healthchecks.io (ping / API) | 생존 신호 / 상태 조회 |
| X9 | 양쪽 모니터 | Vercel REST API | 배포 시도 수 |

## ⑥ 프론트 배선 (Vercel 정적)

| # | 출발 | 도착 | 기능 |
|---|---|---|---|
| F1 | `index.html` (`main.js`, 75초 폴링) | raw CDN `data/preview.json` | 예고판 (CDN 캐시 최대 약 5분) |
| F2 | 같음 | raw CDN `data/notices.json` | 소식 티커 |
| F3 | 같음 | raw CDN `data/tweets.json` | 편지 배지·말풍선 |
| F4 | `tweets.js` | `platform.twitter.com` embed iframe | X 공식 트윗 카드 |
| F5 | `monitor.html` (이스터에그) | **제어 채널 `GET /monitor-live`** (CORS `*`) → 실패 시 raw `monitoring/latest.html` | 웹 모니터. 프론트가 Cloud Run을 **직접** 부르는 유일한 배선 |
| F6 | GitHub `main` push | Vercel 자동 배포 (`main`만 허용) | 배포 |

---

## 엉킨 지점 (v3b 정리 후보)

1. **data 쓰기 경로가 세 갈래**: 백엔드 tick 직접, `/write` 큐, 제어 채널 직접(`/translate`·`admin_state`·`control.json`). v3.7의 직렬화 원칙에 구멍이 남아 있다.
2. **`/tick`의 호출자가 셋**(Scheduler, Cloud Tasks, `/resume`)이고, 내용물도 감지 이외의 일이 절반이다.
3. **`/wake`가 영상 하나가 아니라 추적 중인 전체 항목**을 다시 계산한다. tick과의 경계가 흐리다.
4. **`/ingest` 하나에 X 알림과 YouTube 알림**이 `source`로만 구분돼 섞여 들어온다.
5. **백엔드가 자기 자신을 동기 호출**하는 배선이 있다(I6, 확인 필요).
6. **프론트가 제어 채널을 직접 호출**한다(F5). 나머지 프론트 배선은 전부 raw CDN.
7. 잔재 배선: `ingest_queue.json` drain(S6), `push_monitor.py`(미사용), v1 `collect.yml`.

## 참고: `/tick` 실적 점검 (2026-09-26)

v3b 착수의 계기가 된 점검 결과. 모니터 이벤트 로그(09-09~09-26)와 `preview_archive.json`·`preview.json` 기준.

- 실행: 최근 24시간 `/tick` 148건 전부 HTTP 200. 모니터 로그상 tick 오류 0건.
- **트윗 없이 예약 스트림 감지(본연의 역할)는 수행 중**: 실제 방송된 38건 중 17건을 tick이 최초 발견했다
  (`source=api`). 트윗보다 수 시간 앞선 사례도 있다(리츠 09-15 20.6h, 09-16 15h / 유노 09-24 4.9h).
  09-26 미야코 21:30 방송은 스트림 생성 2분 40초 뒤 발견.
- **watching→live 전환은 `/wake`가 담당**: watching/upcoming→live는 wake 19건 vs tick 1건, live→end는 wake 27건 vs tick 0건.
- **확인 필요**: 10/1 그룹 채널 동시시청 방송은 스트림 생성 후 약 5시간 동안 tick이 찾지 못하고 공식 릴레이가 먼저 들어왔다.
  원인(RSS 반영 지연 / 공개 전환 시점)은 미확인. 종료된 영상은 YouTube `publishedAt`이 종료 무렵으로 덮어써져
  발견 지연을 잴 수 없다.
- `announced↔watching` 왕복: 09-17~18에 276회, v3.7.3 이후로는 하루 1~3건으로 줄었지만 **지금도 발생 중**.
