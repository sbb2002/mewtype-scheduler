# v3b 기능 지도 — 현행(v3.8.10) 기능 전체와 경로

- 작성: 2026-09-28 (기준 커밋 `origin/main` `6af6db7`)
- 목적: 현재 앱이 하는 일을 **기능 단위**로 전부 나열하고, 각 기능이 어떤 배선을 거쳐 어디에 쓰이는지 한 줄 경로로 기록.
  배선 단위 지도는 `v3b_wiring_map.md`, 이 문서는 그 배선들을 기능별로 다시 묶은 것.
- 근거: `src/backend/handlers.py`(`_run`), `src/backend/telegram_app.py`(`/ingest`·`/telegram` 분기, `call_write` 호출 지점),
  `deploy/deploy*.sh`, `v3b_wiring_map.md`를 직접 확인. 실동작 미검증 항목은 **(확인 필요)**로 표시.
- 표기: `→` = 흐름 방향. `/write` = 백엔드 쓰기 큐(`POST /write`, `concurrency=1`). 괄호 안은 `/write` 잡 kind.
  "제어 채널" = `mewtype-telegram`, "백엔드" = `mewtype-backend` (`docs/TERMINOLOGY.md`).
- 비고 표시 (흐름도 `v3b_feature_flow.html` "표시 참고"와 같음). 대부분 기능의 **한 단계**에 대한 표시이지 기능 전체가 안 된다는 뜻이 아니다.
  - **불발** — 코드에 있는데 실제로는 목적을 못 이루고 실패하는 경로 (코드·설정으로 확정). 현재 #12만.
  - **?** (확인 필요) — 실패를 의심할 근거는 있지만 실제 결과가 관측된 적 없는 경로. 현재 #14d.
  - **⚠** (구조 정리 후보) — 정상 동작하지만 쓰기 큐 직렬화 원칙 등에서 벗어나 v3b에서 정리할 배선.

---

## 1. 기능 목록

### A. 방송 자동 감지 (업스트림 없이 도는 핵심)

| # | 기능 | 트리거 | 경로 | 외부 서비스 | 쓰는 곳 | 비고 |
|---|---|---|---|---|---|---|
| 1 | 예정·라이브 정기 감지 | Cloud Scheduler 10분 | Scheduler → 백엔드 `/tick` → RSS + `videos.list` → preview 재구성 → data → raw CDN → 팬 브라우저 | YouTube RSS · Data API | `preview.json` | 트윗 없이 스트림을 먼저 찾는 본연의 역할 |
| 2 | 방송별 정밀 추적 (watching → live → end) | Cloud Tasks | 백엔드 `/tick`·`/wake` → Cloud Tasks 예약 → 백엔드 `/wake` → `videos.list` → data (→ 다음 확인 재예약) | YouTube Data API | `preview.json` | 시작 −3분, live 10분/5분, end 창 5분 |
| 3 | 그룹 공식 채널 5인 팬아웃 | (1번 안) | 1번 흐름 안 `build_preview` 규칙 | — | `preview.json` | `@BDP_yumemita` 영상 → 5인 레인 합동 |
| 4 | 종료 방송 보관 | (1·2번 안) | 1·2번 흐름 안에서 이관 | — | `preview_archive.json` | |
| 5 | 아바타 갱신 | Cloud Scheduler 06:00 JST | Scheduler → 백엔드 `/tick` baseline → `channels.list` → data | YouTube Data API | `preview.json` | baseline 때만 |
| 6 | 번역 재시도 | (1번 안, tick만) | 백엔드 `/tick` → `needs_tl` 행 탐색 → Groq 번역 → data | Groq | `notices`·`tweets`·`preview.json` | 감지와 무관한 일이 tick에 얹힘 |

### B. 업스트림 — X 알림 (트윗 기반)

| # | 기능 | 트리거 | 경로 | 외부 서비스 | 쓰는 곳 | 비고 |
|---|---|---|---|---|---|---|
| 7 | 공식 일일 스케줄 · 출연 공지 · 즉시 개시 릴레이 | 공식 계정 트윗 | X push → Automate → 제어 채널 `/ingest` → vxtwitter(원문 복원) → `xrelay.parse` (+ 합동 확인) → 백엔드 `/write`(`merge_rows`) → data | vxtwitter · Groq | `preview.json` (`announced`) | |
| 8 | 개인 트윗 배지 · 번역 | 5인 개인 트윗 | X push → Automate → 제어 채널 `/ingest` → 표시명으로 5인 판별 → vxtwitter → Groq 번역 → 백엔드 `/write`(`personal_tweet`) → data → raw CDN → 팬 브라우저 | vxtwitter · Groq · X embed | `tweets.json` | 24h 만료 |
| 9a | 개인 트윗 → 예고 (YouTube URL 있음) | 8번과 같은 입구 | … → `videos.list` 확정 (외부 채널이면 Groq 참여 판정) → 백엔드 `/write`(`url_confirmed_commit`) → data + Cloud Tasks 즉시 wake | YouTube Data API · Groq | `preview.json` | 예약이 백엔드 잡 안이라 정상 동작 |
| 9b | 개인 트윗 → 소식 (YouTube 외 URL) | 8번과 같은 입구 | … → 소식 이관 → 백엔드 `/write`(`apply_notice`) → data | Groq | `notices.json` | bilibili 등 — 라이브 추적 불가라 preview 밖 |
| 9c | 개인 트윗 → 예고 (URL 없음) | 8번과 같은 입구 | … → `parse_schedule` 후보 → Groq 본인 예고 최종 확인 → 백엔드 `/write`(`merge_rows`) → data | Groq | `preview.json` | LLM 실패 시 등록 안 함 |
| 10 | 소식 게시판 | 방송 외 이벤트 트윗 | X push → Automate → 제어 채널 `/ingest` → `xnotice.parse` → Groq 제목 추출 (+ 같은 날짜면 Groq 중복 판정, 크로스오버 공식 계정이면 Groq 비전 OCR) → 백엔드 `/write`(`apply_notice`) → data → raw CDN → 팬 브라우저 | Groq · Groq 비전 · Telegram `getFile` | `notices.json` | 자정 지나면 `notice_archive.json` |

### C. 업스트림 — YouTube 앱 알림

| # | 기능 | 트리거 | 경로 | 외부 서비스 | 쓰는 곳 | 비고 |
|---|---|---|---|---|---|---|
| 11 | 회원 전용 라이브 시작 | 회원 전용 시작 알림 | YouTube push → Automate → 제어 채널 `/ingest`(`source=yt`) → yt-dlp(video_id 조회) → 백엔드 `/write`(`yt_member_live_commit`) → data | yt-dlp | `preview.json` (live) | |
| 12 | 공개 방송 알림 즉시 확인 | 30분 전 · 리마인더 · 시작 알림 | YouTube push → Automate → 제어 채널 `/ingest`(`source=yt`) → Cloud Tasks wake 예약 → 백엔드 `/wake` → … | YouTube Data API | `preview.json` | ⚠️ **현재 불발**: 제어 채널에 `TASKS_QUEUE` 등 env 없음(`deploy_telegram.sh`) → 예약 실패가 `log.debug`로만 남고 다음 tick이 회수 |

### D. 운영자 명령 (텔레그램)

| # | 기능 | 명령 | 경로 | 외부 서비스 | 쓰는 곳 | 비고 |
|---|---|---|---|---|---|---|
| 13 | 조회 | `/status` `/list` `/notice-list` | 운영자 → Telegram → 제어 채널 `/telegram` → data 읽기 → DM | Telegram | (읽기만) | |
| 14a | `/ingest preview` — 예고 원문 수동 투입 | `/ingest` (preview 생략 가능) | 명령 → `admin_state` `pending_ingest` **직접 쓰기** → 원문 전송 → `xrelay.parse`(아니면 개인 예고로 재시도: URL → `videos.list`) + Groq 합동 확인 → `/write`(`ingest_queue_drain` → `merge_rows`) → data → DM | Groq (+ YouTube Data API) · Telegram | `preview.json` + undo, `admin_state.json` | ⚠ 대기 슬롯 직접 쓰기 |
| 14b | `/ingest notice` — 소식 원문 수동 투입 | `/ingest notice` (= `/notice`) | 명령 → `pending_notice` **직접 쓰기** → 원문 전송 → `xnotice.parse` + Groq 제목·중복 → `/write`(`notice_sweep` → `apply_notice`) → data → DM | Groq · Telegram | `notices.json` + undo, `admin_state.json` | ⚠ 대기 슬롯 직접 쓰기 |
| 14c | `/ingest tweet` — 개인 트윗 수동 투입 | `/ingest tweet <유닛>` | 명령 → `pending_op` **직접 쓰기** → 원문 전송 → `_maybe_personal_tweet`(via=ops) Groq 번역 → `/write`(`personal_tweet`) → data → DM | Groq · Telegram | `tweets.json`, `admin_state.json` | ⚠ 대기 슬롯 직접 쓰기 |
| 14d | `/edit preview` — 예고 편집 마법사 | `/edit` (preview 생략 가능) | 명령 → 목록 표시 → 단계마다 `pending_op` + 편집 락 **직접 쓰기** → 유닛·번호·필드·값·done → `/write`(`apply_preview_edit`) → data → (state 변경 + 영상 있음) 백엔드 자기 `/wake` → 결과 DM(백엔드가 직접) | Telegram | `preview.json` + undo, `admin_state.json` | ? 자기 `/wake` 호출(`telegram_app.py:4027 → 4088-4097`) — `concurrency=1`이라 429 가능성. 모니터 로그(09-09~09-28)에 상태 편집 0건이라 **미관측**. 실패 시 결과 DM에 실패 문구 + 다음 tick 회수. ⚠ 마법사 상태 직접 쓰기. 필드에 `ingest`를 보내면 원문 교체(`merge_rows`) |
| 14e | `/edit notice` — 소식 편집 마법사 | `/edit notice <id\|번호>` (= `/notice-edit`) | 명령 → `pending_notice_edit` **직접 쓰기** → 제목·날짜·URL 되묻기 → `/write`(`notice_edit_commit`) → data → DM | Telegram | `notices.json` + undo, `admin_state.json` | ⚠ 마법사 상태 직접 쓰기 |
| 14f | `/edit tweet` — 개인 트윗 교체 | `/edit tweet <유닛>` | 14c와 같은 경로 (새 원문으로 교체) | Groq · Telegram | `tweets.json`, `admin_state.json` | ⚠ 대기 슬롯 직접 쓰기 |
| 14g | `/del preview` — 예고 삭제 | `/del <유닛> <번호>` | 명령 → `pending_del` **직접 쓰기** + 경고 DM → `y`/`terminate` → `/write`(`remove_broadcast`) → data → (`terminate`) `suppress` 12h **직접 쓰기** → DM | Telegram | `preview.json` + undo, `admin_state.json` | ⚠ 확인 대기·재등록 차단 직접 쓰기. announced~live 항목은 감지 기능이 되살릴 수 있음 |
| 14h | `/del notice` — 소식 삭제 | `/del notice <id\|번호>` (= `/notice-del`) | 명령 → `/write`(`notice_del_commit`, 번호→id는 커밋 시점 해석) → data → DM | Telegram | `notices.json` + undo | 확인 단계 없음 |
| 14i | `/del tweet` — 트윗 배지 삭제 | `/del tweet <유닛>` | 명령 → `/write`(`tweet_del_commit`) → data → DM | Telegram | `tweets.json` + undo | 확인 단계 없음 |
| 14j | `/undo` — 직전 작업 되돌리기 | `/undo` | 명령 → undo 슬롯·현재 파일 읽기 → `pending_undo` **직접 쓰기** + 확인 DM → `y` → `/write`(`undo_restore`, 그 사이 바뀌었으면 거부) → data → 슬롯 정리 **직접 쓰기** → DM | Telegram | 대상 파일(`preview`·`notices`·`tweets`), `admin_state.json` | ⚠ 확인 대기·undo 슬롯 직접 쓰기. 스냅샷 저장은 각 `/write` 잡 안 |
| 15 | 수동 번역 | `/translate` | 운영자 → 제어 채널 → Groq → data **직접 쓰기** | Groq · Telegram | `notices`·`tweets`·`preview.json` | 쓰기 큐 우회 |
| 16 | 일시정지 · 재개 · 로그 레벨 | `/pause` `/resume` `/log` | 운영자 → 제어 채널 → data 직접 쓰기 (`/resume`은 + 백엔드 `/tick` 즉시 호출) | Telegram | `control.json` | `prev_sha=None` — 충돌 검사 없는 덮어쓰기 |
| 17 | 모니터 리포트 | `/monitor` (`--auto` `--off` `--monthly` `--yearly` 날짜) | 운영자 → 제어 채널 → monitoring 로그 + healthchecks + Vercel API → HTML 리포트 DM | healthchecks · Vercel API · Telegram | (`--auto`/`--off`는 `control.json`) | |
| 18 | 유실 원문 재투입 | `/ingest --retroactive` | 운영자 → 제어 채널 → `lost_queue.json` 읽기 → 한 건씩 7~10번 경로로 재처리 → 성공분만 큐에서 제거 | (재처리 경로에 따름) | `lost_queue.json` + 재처리 대상 | 순차 처리 |

### E. 알림 · 관측

| # | 기능 | 트리거 | 경로 | 외부 서비스 | 쓰는 곳 | 비고 |
|---|---|---|---|---|---|---|
| 19 | 상태 전이 알림 DM | 1·2번 결과 | 백엔드 `/tick`·`/wake` → Telegram DM | Telegram | — | 알림 레벨로 게이팅 |
| 20 | 유실 원문 보존 | 쓰기 실패 4지점 | 제어 채널 → Telegram DM(원문 전체) + monitoring 적재 | Telegram | `monitoring/lost_queue.json` | 최대 50건 |
| 21 | 모니터 이벤트 로그 | 각 처리마다 | 백엔드 · 제어 채널 → monitoring 브랜치 | — | `monitoring/events-YYYY-MM-DD.jsonl` | 06:00 KST 경계 |
| 22 | 일일 스냅샷 + 멤버 현황 DM | Cloud Scheduler 06:10 KST | Scheduler → 백엔드 `/monitor` → healthchecks + Vercel API → monitoring → Telegram DM | healthchecks · Vercel API · Telegram | `monitoring/days/`·`summary.json`·`latest.html` | DM은 `monitor_auto` 켜진 경우만 |
| 23 | 웹 모니터 (이스터에그) | 방문 | 팬 브라우저 `monitor.html` → 제어 채널 `/monitor-live` → monitoring 읽기 → 즉석 생성 (실패 시 raw `latest.html`) | — | (읽기만) | 프론트가 Cloud Run을 직접 부르는 유일한 배선 |
| 24 | 생존 신호 | 정기 tick | 백엔드 `/tick` → healthchecks.io 핑 | healthchecks | — | 일시정지 중에도 보냄. wake는 안 보냄 |

### F. 프론트 · 배포

| # | 기능 | 트리거 | 경로 | 외부 서비스 | 쓰는 곳 | 비고 |
|---|---|---|---|---|---|---|
| 25 | 팬 화면 (예고판 · 소식 티커 · 트윗 배지) | 75초 폴링 | 팬 브라우저 → raw CDN → data `preview`·`notices`·`tweets.json` | raw CDN · X embed | (읽기만) | CDN 캐시 최대 약 5분 |
| 26 | 배포 | `main` push | GitHub `main` → Vercel 자동 배포 | Vercel | — | `main`만 배포 허용 |

### 기능으로 세지 않은 잔재

| 항목 | 상태 |
|---|---|
| `ingest_queue.json` 적재·반영 | v2.3 ECHO/DRY-RUN 시절 잔재. 반영(`ingest_queue_drain`) 호출은 **지금도 `/ingest`마다 실행**됨 |
| `push_monitor.py` | v3.8.9부터 미사용 |
| v1 `collect.yml` (`src/collector/main.py`) | 실행해도 현행 사이트에 반영 안 됨 |

---

## 2. 외부 서비스 역할

"빠지면" 열 = 그 서비스만 없을 때 벌어지는 일. 계층: **핵심**(사이트가 멈춤) / **기능**(특정 기능만 사라지거나 약해짐) /
**운영**(운영자만 영향) / **관측**(보는 것만 영향).

| 외부 서비스 | 역할 | 호출하는 쪽 | 호출 시점 | 빠지면 | 계층 | 관련 기능 # |
|---|---|---|---|---|---|---|
| YouTube RSS | 채널별 최근 영상 id 발견 (쿼터 0) | 백엔드 | 정기 tick마다 6채널 (wake 제외) | 새 방송을 발견 못 함 | 핵심 | 1 |
| YouTube Data API | `videos.list` 상태·시각 확정 / `channels.list` 아바타 | 백엔드(tick·wake), 제어 채널(URL 확정) | 추적 후보 있으면 매번 / 아바타는 baseline만 | 예정·라이브·종료 판정 전체가 멈춤 | 핵심 | 1 2 5 9a 12 14a |
| raw CDN | data JSON을 브라우저에 전달 (캐시 약 5분) | 팬 브라우저 | 75초 폴링 | 화면 갱신 끊김 | 핵심 | 25 23(폴백) |
| Vercel | 프론트 정적 호스팅 · 자동 배포 | GitHub `main`, 팬 브라우저 | 배포 시 / 방문 시 | 사이트 접속 불가 | 핵심 | 26 |
| X · YouTube 푸시 알림 | 업스트림이 받아 `/ingest`로 중계하는 원본 신호 | (서드파티 → 운영자 폰) | 트윗 · 앱 알림 발생 시 | 예고 · 트윗 · 소식 · 회원 전용 라이브 입력이 사라짐 | 기능 | 7~12 |
| Groq LLM (`gpt-oss-120b`/`20b`) | 번역, 소식 제목 추출, 참여·합동·본인 예고 판정, 소식 중복 판정 | 제어 채널(준비 단계), 백엔드(재번역) | 번역·판정 필요 입력 시 / tick 때 `needs_tl` 있으면 | 번역 빠짐. LLM 확인이 필요한 예고는 등록 안 됨 | 기능 | 6 7 8 9a 9c 10 14a 14b 14c 14f 15 |
| Groq 비전 (qwen) | 공지 이미지 속 출연진 이름 판독 | 제어 채널 | 크로스오버 공식 계정 소식에 이미지가 있을 때 | 이미지로만 공지된 출연진 누락 | 기능 | 10 |
| vxtwitter → fxtwitter | 잘린 트윗 원문 · 미디어 · 인용 복원 | 제어 채널 | 트윗 id를 뽑을 수 있는 알림일 때 | 폰 원문으로 폴백 — 긴 트윗 잘림 위험 | 기능 | 7 8 |
| yt-dlp | 회원 전용 라이브 video_id · URL 조회 | 제어 채널 | 회원 전용 시작 알림 시 | 회원 전용 라이브 live 전환 불가 | 기능 | 11 |
| X embed (platform.twitter.com) | 말풍선 속 X 공식 트윗 카드 | 팬 브라우저(`tweets.js`) | `tweets.json`에 트윗 있을 때 | 원문 카드 사라짐 — 대체 수단 없음(v3.8.0 법률 자문으로 원문 직접 표시 제거) | 기능 | 8 25 |
| Telegram Bot API | 명령 수신(webhook), 알림 · 응답 DM, OCR용 `getFile` | 제어 채널, 백엔드 | 명령 시 / 상태 전이 시(레벨 게이팅) / 유실 시 | 운영자 제어·알림 끊김. 사이트는 정상 | 운영 | 13~20 22 |
| healthchecks.io | 생존 핑 / 상태 조회 API | 백엔드(tick마다, 일시정지 중에도), 모니터 | 정기 tick / 06:10 / 리포트 요청 시 | 생존 여부를 못 봄. 동작은 그대로 | 관측 | 17 22 24 |
| Vercel REST API | 배포 시도 수 (Hobby 한도 감시) | 모니터(양쪽) | 06:10 / 리포트 요청 시 | 한도 수치를 못 봄. 동작은 그대로 | 관측 | 17 22 |

GitHub Contents API(데이터 저장소 읽기·쓰기 통로)는 외부 서비스가 아니라 저장소 자체로 보고 표에서 뺐다.

---

## 3. 계층별 필수 요소 ("빼면 무엇이 멈추나")

| 계층 | 요소 | 빠지면 |
|---|---|---|
| 핵심 | Cloud Scheduler, 백엔드(Cloud Run), YouTube RSS · Data API, GitHub `data`, raw CDN, 프론트 · Vercel | 사이트가 멈추거나 갱신이 끊김 |
| 기능 | 업스트림 + 제어 채널 | 예고 · 트윗 · 소식 기능 전체 소실 (방송 감지는 tick이 계속 — 실측 38건 중 17건은 tick이 먼저 발견) |
| 기능 | Groq · Groq 비전 · vxtwitter · yt-dlp · X embed | 각 기능이 사라지거나 약해짐 (위 표) |
| 운영 | Telegram | 운영자 제어 · 알림만 끊김 |
| 정밀도 | Cloud Tasks | 라이브 감지가 최대 10분 늦어짐 (tick이 추적 중인 영상을 매번 재확인) |
| 관측 | healthchecks, Vercel API, `monitoring` 브랜치 | 상태를 못 볼 뿐 동작은 그대로 |
