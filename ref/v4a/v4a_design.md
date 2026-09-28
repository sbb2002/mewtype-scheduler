# v4a 설계안 — 서비스 2개 유지 + 적용 큐 일원화 + reconcile 통일

- 작성: 2026-09-28 · 기준 커밋 `origin/main` `6af6db7` (v3.8.10)
- 상태: **설계안 (미구현 · 미측정)**. 채택 여부는 §10 측정으로 결정.
- 함께 보는 자료: 흐름도 `ref/v4a/v4a_flow.html` · 현재 기능 지도 `ref/v3b/v3b_feature_map.md` ·
  현재 배선 지도 `ref/v3b/v3b_wiring_map.md` · v3b 목표안 `ref/v3b/v3b_target_flow.html`
- 표기: **(확인 필요)** = 코드 · 공식 문서로 아직 검증하지 않은 가정.
- **용어**: 이 문서는 §3의 v4a 용어를 쓴다. 현재(v3.8.10) 시스템을 가리킬 때만 현재 이름(제어 채널 · 백엔드 · `/tick` 등,
  `docs/TERMINOLOGY.md` 기준)을 쓰고 "현재"라고 밝힌다. v4a 용어는 채택 · 구현 시점에 `docs/TERMINOLOGY.md` 로 옮긴다.

---

## 1. 왜 — 엉킴의 뿌리 두 가지

**① Git 브랜치를 여러 곳이 동시에 쓰는 데이터베이스로 쓴다.**
GitHub Contents API는 브랜치 HEAD 단위로 충돌한다 — 파일이 달라도 먼저 커밋한 쪽 외에는 409.
그동안의 큰 패치(현재 백엔드 `max-instances=1`, v3.7 `/write` 쓰기 큐, v3.9 409 재시도 · `monitoring` 브랜치 분리 · 429 백오프)가
대부분 이 성질을 우회하려고 생겼다. 그런데도 현재 제어 채널이 data에 직접 쓰는 경로(`/translate` · `admin_state` · `control.json`)가 남아 있다.

**② "즉시" 처리하려는 지름길 배선이 기능마다 따로 붙었다.**
"알림 오면 바로 wake"(#12), "편집하면 바로 재확인"(#14d 자기 호출), "재개하면 바로 tick"(#16) —
이벤트가 생긴 자리에서 다음 동작을 직접 부른다. 이번 점검에서 나온 문제(#12 불발, #14d 확인 필요, `/tick` 호출자 셋)가 전부 여기서 나왔다.
반대로 **정기 tick은 매번 전체를 다시 계산하므로** 이벤트를 놓쳐도 다음 바퀴에 복구된다 — #12 · #14d가 실패해도 데이터가 안 틀어지는 이유.

## 2. 참고한 업계 방식

| 패턴 | 요지 | v4a에서 |
|---|---|---|
| Single writer + 내구성 있는 큐 (inbox 패턴) | 공유 상태는 한 주체만 쓰고, 나머지는 요청을 큐에 넣기만 | 쓰기 서비스만 data를 씀. 접수 서비스는 적용 큐에 적재 |
| Level-triggered reconcile (쿠버네티스 컨트롤러 방식) | 이벤트를 따라가지 않고 "지금 어때야 하나"를 매번 계산. 트리거는 "다시 맞춰 봐" 신호일 뿐 | 지름길 배선을 전부 `reconcile(범위)` 요청으로 통일 |
| Functional core, imperative shell | 판단은 순수 함수, 입출력은 바깥 껍데기 | `preview.py` · `statemachine.derive` · `merge_*` 는 그대로. 껍데기만 정리 |
| Modular monolith 우선 | 보안 · 확장 요구가 실제로 다를 때만 서비스를 나눔 | 공개 접수 / 비공개 쓰기 2개 유지 (v2.1 결정 1의 근거 그대로) |
| Strangler fig | 새 경로를 하나씩 붙이고 옛 경로를 걷어냄 | §11 단계마다 배포 가능 |

## 3. v4a 용어

이름 규칙: **서비스는 역할(동사)로, 큐는 전달하는 엔드포인트 이름으로, Scheduler 잡은 부르는 동작으로.**
이름만 보고 무엇이 무엇을 부르는지 알 수 있게 한다.

### 구성 요소

| v4a 용어 | GCP 리소스 이름 | 정의 | 현재(v3.8.10) 대응 |
|---|---|---|---|
| **접수 서비스** | Cloud Run `mewtype-intake` (공개) | 바깥에서 오는 모든 것을 받는 공개 서비스. 업스트림 알림 접수, 운영자 명령 대화, 외부 호출로 가공(LLM · vxtwitter · videos.list · yt-dlp · OCR), 적용 큐에 적재, 조회 응답, 웹 모니터. **data 브랜치에 쓰지 않는다** | 제어 채널 `mewtype-telegram` |
| **쓰기 서비스** | Cloud Run `mewtype-writer` (비공개, 동시 1 · 인스턴스 1) | data 브랜치를 쓰는 **유일한** 주체. reconcile · 작업 적용 · 다음 확인 예약 · 결과 DM · 모니터링 스냅샷 | 백엔드 `mewtype-backend` |
| **적용 큐** | Cloud Tasks `mewtype-apply` (동시 전달 1) | 쓰기 서비스 `/apply` 로 작업을 하나씩 전달하는 큐. 모든 쓰기 요청 · reconcile 요청이 여기로 | 현재 wake · tick 예약 큐(`TASKS_QUEUE`) |
| **가공 큐** | Cloud Tasks `mewtype-enrich` | 접수 서비스 `/enrich` 로 번역 재시도 요청을 전달하는 큐 (신규) | 없음 (tick 안 `_translate_sweep`) |
| **정기 reconcile 잡** | Cloud Scheduler `mewtype-reconcile-10m` · `mewtype-reconcile-daily` | 10분마다 · 매일 06:00 JST 쓰기 서비스 `/reconcile` 호출 (daily는 아바타 포함) | `mewtype-light` · `mewtype-baseline` |
| **스냅샷 잡** | Cloud Scheduler `mewtype-snapshot-daily` | 매일 06:10 KST 쓰기 서비스 `/snapshot` 호출 | `mewtype-monitor` |
| **`data` 브랜치** | 데이터 저장소 | 공개 콘텐츠(preview · notices · tweets + archive)만. 쓰기 서비스만 쓴다 | 같음 (admin_state · control 이 빠짐) |
| **`ops` 브랜치** | 데이터 저장소 (신규) | 운영 세션 상태 — admin_state(대화 · 확인 대기 · 편집 락 · suppress) · control · undo 슬롯. 접수 서비스와 쓰기 서비스가 쓴다 | 없음 (현재 data 브랜치에 섞여 있음) |
| **`monitoring` 브랜치** | 데이터 저장소 | 이벤트 로그 · 모니터링 스냅샷 · 유실 큐 | 같음 |

### 엔드포인트

| 엔드포인트 | 서비스 | 호출자 | 하는 일 | 현재 대응 |
|---|---|---|---|---|
| `POST /ingest` | 접수 | 업스트림 시스템 | X · YouTube 알림 접수 (경로 유지 — 폰 플로우의 경로 부분 불변) | 같음 |
| `POST /telegram` | 접수 | Telegram webhook | 운영자 명령 | 같음 |
| `POST /enrich` | 접수 | 가공 큐 (OIDC, 앱 안 검증) | 번역 재시도 → 결과를 적용 큐에 적재 | 없음 |
| `GET /monitor-live` | 접수 | 프론트 `monitor.html` | 웹 모니터 즉석 생성 (읽기 전용) | 같음 |
| `POST /reconcile` | 쓰기 | 정기 reconcile 잡 | `reconcile(전체)` | `/tick` |
| `POST /apply` | 쓰기 | 적용 큐 | 작업 하나 적용 (콘텐츠 반영 · 명령 적용 · `reconcile(범위)`) | `/write` + `/wake` + Tasks발 `/tick` |
| `POST /snapshot` | 쓰기 | 스냅샷 잡 | 모니터링 스냅샷 + 멤버 현황 DM | `/monitor` |

### 동작 용어

| 용어 | 정의 |
|---|---|
| **reconcile(범위)** | "지금 상태가 어때야 하나"를 다시 계산해 data에 맞추는 동작. 범위는 `전체`(RSS + 추적 중 전부) 또는 `영상 하나`. 누가 요청하든 같은 함수. 정기 reconcile 잡은 `/reconcile` 로, 나머지는 적용 큐 → `/apply` 로 요청한다 |
| **적재** | 적용 큐 · 가공 큐에 작업을 넣는 것. 넣으면 바로 돌아가고 결과를 기다리지 않는다 |
| **작업** | 적용 큐로 전달되는 요청 하나. 종류(kind)는 현재 `writers.py` 잡 종류를 재사용 + `reconcile`. 서로 독립 · 멱등이어야 한다(§9) |
| **결과 DM** | 작업을 적용한 뒤 쓰기 서비스가 보내는 DM. 조회 응답 · 대화 질문은 접수 서비스가 즉시 보낸다 |
| **마지막 시도** | 적용 큐가 작업을 재시도하다 한도에 이른 전달. 쓰기 서비스가 판별해 유실 큐에 적재한다(§9) |
| **리소스 이름 전환** | Cloud Run 서비스 이름을 `mewtype-intake` · `mewtype-writer` 로 실제 바꾸는 일. §9 "리소스 이름 전환" 참고 — 바꾸기 전까지 문서는 새 용어 뒤에 옛 리소스 이름을 병기할 수 있다 |

## 4. 원칙 (v4a의 모든 변경은 이 다섯 줄로 판단)

1. **data 브랜치를 쓰는 곳은 쓰기 서비스 하나.** (동시 1 · 인스턴스 1 — 정기 reconcile과 작업 적용이 같은 인스턴스에서 한 줄로 선다)
2. **접수 서비스는 적재하고 바로 돌아간다.** 현재의 동기 `/write`(60초 대기 · 429 백오프) 대신 적용 큐 적재. 쓰기 서비스가 바쁘면 적용 큐가 알아서 재시도.
3. **예약 · 재확인은 전부 `reconcile(범위)` 요청으로.** 누가 부르든 같은 큐에 같은 모양으로 들어간다. 자기 호출 · 동기 호출 없음.
4. **느린 외부 호출(LLM · vxtwitter · videos.list · yt-dlp · OCR)은 접수 서비스에서.** 쓰기 서비스는 머지 · 커밋 · 예약 · 결과 DM만.
   예외: reconcile의 YouTube 조회(RSS · `videos.list`)는 쓰기 서비스가 한다 — 판정 재료라서.
5. **운영 세션 상태는 `ops` 브랜치로.** 공개 데이터와 충돌하지 않는다.

## 5. 브랜치별 쓰는 주체

| 브랜치 | 내용 | 쓰는 곳 | 읽는 곳 |
|---|---|---|---|
| `data` | preview · notices · tweets (+ archive) | **쓰기 서비스만** | 양쪽 · 프론트(raw CDN) |
| `ops` | admin_state · control · undo 슬롯 | 접수 서비스(대화 · pause) + 쓰기 서비스(undo 슬롯 · suppress) | 양쪽 |
| `monitoring` | 이벤트 로그 · 모니터링 스냅샷 · 유실 큐 | 양쪽 (v3.9와 같음) | 양쪽 |

`ops` 를 두 곳이 쓰지만 운영자 한 명의 순차 조작이라 경합이 낮고, 경합해도 공개 데이터(`data`)에는 영향이 없다. 모두 sha 충돌 검사 + 재시도
(현재 `control.json` 의 `prev_sha=None` 덮어쓰기도 여기서 sha 검사로 바꾼다).
`/pause` 는 적용 큐 · 쓰기 서비스 상태와 무관하게 즉시 먹혀야 하므로 접수 서비스가 `ops` 에 직접 쓴다 — 비상 브레이크가 막힌 큐 뒤에 서면 안 된다.

## 6. 트리거 통일

| 트리거 | 현재 | v4a |
|---|---|---|
| 10분 · 06:00 정기 | Scheduler → 백엔드 `/tick` | 정기 reconcile 잡 → `/reconcile` = `reconcile(전체)`. 큐를 거치지 않지만 같은 인스턴스라 한 줄로 선다 (429 → Scheduler 재시도, 현행 `--max-retry-attempts=3`) |
| 방송별 정밀 확인 | 백엔드 → Tasks → `/wake` | 쓰기 서비스 → 적용 큐 → `/apply reconcile(영상)` |
| 종료 후 재확인 · 영상 없는 예고 시각 | 백엔드 → Tasks → `/tick` | 적용 큐 → `/apply reconcile(전체)` |
| URL 확정 · 등록 즉시 확인 | `/write` 잡 안에서 Tasks 예약 | 작업 안에서 `reconcile(영상)` 적재 |
| YouTube 공개 알림 즉시 확인 (#12) | 제어 채널이 Tasks 예약 시도 → **env 없음, 불발** | 접수 서비스가 `reconcile(영상)` 적재 — 모든 쓰기가 큐를 거치므로 큐 설정이 반드시 있다 |
| `/edit` 상태 변경 후 재확인 (#14d) | 백엔드 → 자기 `/wake` 동기 호출 | 작업 안에서 `reconcile(영상)` 적재 |
| `/resume` | 제어 채널 → `/tick` 동기 호출 | `ops` 에 control 쓰기 + `reconcile(전체)` 적재 |
| 번역 재시도 | tick 안 `_translate_sweep` (백엔드가 Groq 호출) | reconcile이 `needs_tl` 행을 보면 가공 큐 → 접수 서비스 `/enrich` 가 번역 → 적용 큐 |

## 7. 기능 커버리지 — 26가지(세부 37행) 전부

"변경" = v3.8.10 대비 경로가 바뀜. 기능 자체(사용자가 보는 동작)는 전부 유지된다.

| # | 기능 | v4a 경로 | v3.8.10 대비 |
|---|---|---|---|
| 1 | 예정 · 라이브 정기 감지 | 정기 reconcile 잡 → `/reconcile` → RSS + `videos.list` → preview 재구성 → data → CDN → 팬 | 유지 (이름만) |
| 2 | 방송별 정밀 추적 | 쓰기 서비스 → 적용 큐 `reconcile(영상)` → `/apply` → `videos.list` → data → 다음 확인 재적재 | 변경 (`/wake` → `/apply`) |
| 3 | 그룹 공식 채널 5인 팬아웃 | 1번 안 `build_preview` 규칙 | 유지 |
| 4 | 종료 방송 보관 | 1 · 2번 안 | 유지 |
| 5 | 아바타 갱신 | `mewtype-reconcile-daily` → `/reconcile` → `channels.list` → data | 유지 (이름만) |
| 6 | 번역 재시도 | reconcile → 가공 큐 → `/enrich` → Groq → 적용 큐 → `/apply` → data | 변경 (쓰기 서비스의 Groq 호출 제거) |
| 7 | 공식 스케줄 · 출연 공지 · 즉시 개시 릴레이 | 업스트림 → `/ingest` → vxtwitter · 파싱 · Groq → 적용 큐(`merge_rows`) → `/apply` → data → 결과 DM | 변경 (동기 `/write` → 적재) |
| 8 | 개인 트윗 배지 · 번역 | `/ingest` → vxtwitter · Groq → 적용 큐(`personal_tweet`) → `/apply` → data → CDN · X embed | 변경 |
| 9a | 개인 트윗 → 예고 (YouTube URL) | `/ingest` → `videos.list` (+ Groq) → 적용 큐(`url_confirmed_commit`) → `/apply` → data + `reconcile(영상)` 적재 | 변경 |
| 9b | 개인 트윗 → 소식 (비YouTube URL) | `/ingest` → Groq → 적용 큐(`apply_notice`) → `/apply` → data | 변경 |
| 9c | 개인 트윗 → 예고 (URL 없음) | `/ingest` → 파싱 + Groq 최종 확인 → 적용 큐(`merge_rows`) → `/apply` → data | 변경 |
| 10 | 소식 게시판 | `/ingest` → vxtwitter · 파싱 · Groq(+ 비전 OCR) → 적용 큐(`apply_notice`) → `/apply` → data | 변경 |
| 11 | 회원 전용 라이브 시작 | `/ingest`(source=yt) → yt-dlp → 적용 큐(`yt_member_live_commit`) → `/apply` → data | 변경 |
| 12 | 공개 방송 알림 즉시 확인 | `/ingest`(source=yt) → 적용 큐 `reconcile(영상)` → `/apply` → `videos.list` → data | 변경 (**불발 해소**) |
| 13 | 조회 명령 | 운영자 → 접수 서비스 → data · ops 읽기 → DM | 유지 (읽는 브랜치에 ops 추가) |
| 14a | `/ingest preview` | 명령 → `ops` 대기 슬롯 → 원문 → 파싱 · Groq → 적용 큐(`merge_rows`) → `/apply` → data + ops(undo) → 결과 DM | 변경 |
| 14b | `/ingest notice` (= `/notice`) | 명령 → `ops` 대기 슬롯 → 원문 → Groq → 적용 큐(`apply_notice`) → `/apply` → data + ops(undo) → 결과 DM | 변경 |
| 14c | `/ingest tweet` | 명령 → `ops` 대기 슬롯 → 원문 → Groq → 적용 큐(`personal_tweet`) → `/apply` → data → 결과 DM | 변경 |
| 14d | `/edit preview` | 명령 → `ops` 대화 · 편집 락 → done → 적용 큐(`apply_preview_edit`) → `/apply` → data + ops(undo · 락 해제) → (state 변경 + 영상) `reconcile(영상)` 적재 → 결과 DM | 변경 (**자기 호출 제거**) |
| 14e | `/edit notice` (= `/notice-edit`) | 명령 → `ops` 대화 → 적용 큐(`notice_edit_commit`) → `/apply` → data + ops(undo) → 결과 DM | 변경 |
| 14f | `/edit tweet` | 14c와 같은 경로 | 변경 |
| 14g | `/del preview` | 명령 → `ops` 확인 대기 + 경고 DM → y/terminate → 적용 큐(`remove_broadcast`) → `/apply` → data + ops(undo · terminate면 suppress) → 결과 DM | 변경 (suppress를 같은 작업 안에서) |
| 14h | `/del notice` (= `/notice-del`) | 명령 → 적용 큐(`notice_del_commit`) → `/apply` → data + ops(undo) → 결과 DM | 변경 |
| 14i | `/del tweet` | 명령 → 적용 큐(`tweet_del_commit`) → `/apply` → data + ops(undo) → 결과 DM | 변경 |
| 14j | `/undo` | 명령 → ops · data 읽기 → `ops` 확인 대기 + 확인 DM → y → 적용 큐(`undo_restore`) → `/apply` → data 복원 + ops 슬롯 정리 → 결과 DM | 변경 |
| 15 | 수동 번역 `/translate` | 명령 → data 읽기 → Groq → 적용 큐(번역 반영) → `/apply` → data → 결과 DM | 변경 (**직접 쓰기 제거**) |
| 16 | 일시정지 · 재개 · 로그 레벨 | 명령 → `ops` control 쓰기(sha 검사) → (`/resume`) 적용 큐 `reconcile(전체)` → DM | 변경 (**동기 호출 제거**) |
| 17 | 모니터 리포트 `/monitor` 명령 | 명령 → monitoring 읽기 + healthchecks · Vercel API → HTML DM (`--auto/--off` 는 ops control) | 유지 |
| 18 | 유실 원문 재투입 `--retroactive` | 명령 → 유실 큐 읽기 → 한 건씩 가공 재실행 → 적용 큐 적재 → **적재 성공분** 유실 큐에서 제거 | 변경 (제거 기준: 커밋 성공 → 적재 성공. 최종 실패는 쓰기 서비스가 다시 적재) |
| 19 | 상태 전이 알림 DM | `/reconcile` · `/apply reconcile` → data → 레벨 게이팅 DM | 유지 |
| 20 | 유실 원문 보존 | ① 접수 서비스 적재 실패 → DM + 유실 큐 ② 작업이 마지막 시도까지 실패 → 쓰기 서비스가 DM + 유실 큐 | 변경 (실패 지점 4곳 → 2곳) |
| 21 | 모니터 이벤트 로그 | 양쪽 → monitoring | 유지 |
| 22 | 일일 스냅샷 + 멤버 현황 DM | 스냅샷 잡 06:10 → `/snapshot` → healthchecks · Vercel → monitoring → DM | 유지 (이름만) |
| 23 | 웹 모니터 | 브라우저 → 접수 서비스 `/monitor-live` → monitoring 읽기 (폴백 raw) | 유지 |
| 24 | 생존 신호 | `/reconcile` → healthchecks 핑 | 유지 |
| 25 | 팬 화면 | 브라우저 → raw CDN → data | 유지 |
| 26 | 배포 | `main` push → Vercel | 유지 |

## 8. 현재 배선(`v3b_wiring_map.md`) → v4a

| 현재 배선 | v4a | 비고 |
|---|---|---|
| E1 · E2 `/ingest` (X · YouTube) | 유지 | 경로 유지. 내부 핸들러만 분리 |
| E3 운영자 명령 | 유지 | |
| E4 · E5 정기 tick | 변경 | 정기 reconcile 잡 → `/reconcile`. 번역 대신 가공 큐 적재 |
| E6 모니터 스냅샷 | 변경 | 스냅샷 잡 → `/snapshot` |
| I1 `/wake` 예약 | 변경 | 적용 큐 `reconcile(영상)` |
| I2 `/tick` 예약 (자기 재호출) | 흡수 | 적용 큐 `reconcile(전체)` |
| I3 `/write` 동기 쓰기 큐 | 변경 | 적용 큐 적재 (비동기). `writers.py` 잡 종류는 `/apply` 가 재사용 |
| I4 등록 즉시 wake | 흡수 | 작업 안에서 `reconcile(영상)` 적재 |
| I5 `/resume` → `/tick` | 변경 | `reconcile(전체)` 적재 |
| I6 백엔드 자기 호출 | **삭제** | |
| T `/tick` 한 바퀴 | 변경 | 번역 sweep 제거 |
| S1 preview (쓰는 갈래 둘) | 변경 | 쓰기 서비스 인스턴스 하나 (`/reconcile` · `/apply` 모두) |
| S2 · S3 `/translate` 우회 | 변경 | 적용 큐 경유 |
| S4 admin_state (제어 채널 직접) | 변경 | `ops` 브랜치로 이동 |
| S5 control (충돌 검사 없음) | 변경 | `ops` 브랜치 + sha 검사 |
| S6 `ingest_queue.json` | **삭제** | |
| S7 이벤트 로그 · lost_queue | 유지 | 유실 적재 지점 변경 (§7 #20) |
| S8 `latest.html` (쓰는 쪽 둘) | 유지 | monitoring 브랜치라 data와 무관. 정리는 선택 |
| X4 Groq (양쪽) | 변경 | 접수 서비스만 |
| X1 · X2 · X3 · X5~X9 | 유지 | |
| F1~F6 | 유지 | F5 는 접수 서비스 URL을 가리킴 (리소스 이름 전환 시 갱신) |
| (신규) 가공 큐 → `/enrich` | 추가 | Tasks OIDC 호출 — 공개 서비스라 앱 안에서 OIDC 검증(`oidc.verify_request` 재사용) |
| (신규) `ops` 브랜치 | 추가 | |

엉킨 지점 7개(배선 지도 기준): 1 쓰기 세 갈래 → **해소** · 2 `/tick` 호출자 셋 → **해소**(정기 reconcile 잡 하나) ·
3 `/wake` 전체 재계산 → `reconcile(영상)` 범위를 영상 하나로 좁히면 해소(구현 시 결정) · 4 `/ingest` 혼합 → 내부 분리만(경로 유지) ·
5 자기 호출 → **해소** · 6 프론트가 접수 서비스 호출 → 유지(읽기 전용이라 원칙에 어긋나지 않음) · 7 잔재 → **해소**.

## 9. 대가 · 확인 필요

| 항목 | 내용 |
|---|---|
| 결과 DM이 비동기 | 명령 결과가 커밋 뒤 쓰기 서비스에서 온다. 결과 DM 문구 조립을 `/apply` 작업 안으로 옮겨야 한다 (현재 `apply_preview_edit` 는 이미 이 방식). 조회 · 대화 질문은 지금처럼 즉시 |
| 묶음 커밋 없음 | 1건 = 1커밋. v3.8.2 측정(1커밋 약 3.3초)을 대입하면 60건 버스트는 마지막까지 약 3분 + 정기 reconcile 실행 중이면 그만큼 추가. 팬 화면은 raw CDN 캐시가 원래 최대 약 5분 — **추정, 재측정 필요** |
| 순서 보장 없음 | Cloud Tasks는 전달 순서를 보장하지 않는다 **(공식 문서 재확인)**. 작업은 서로 독립이고 id 기준 upsert여야 한다. 현재 머지 함수 대부분이 그렇고 `undo_restore` 는 `expected_sha` 로 보호 — 전 작업 종류 점검 필요 |
| 중복 전달 | 드물게 같은 작업이 두 번 올 수 있다 **(확인 필요)** → 멱등이어야 함. 명명 태스크로 중복 적재 방지 |
| 데드레터 없음 | Cloud Tasks에는 DLQ가 없다 **(확인 필요)** → 적용 큐에 최대 시도 횟수를 두고, 쓰기 서비스가 `X-CloudTasks-TaskRetryCount` 헤더로 마지막 시도를 판별해 유실 큐에 적재 **(헤더 이름 · 동작 공식 문서 재확인)** |
| 작업 크기 | 원문 + 가공 결과를 작업 본문에 싣는다. Cloud Tasks 작업 크기 상한 안인지 **확인 필요** (트윗 원문 · 미디어 URL 수준이라 여유 있을 것으로 추정) |
| 번역이 커밋 두 번 | reconcile이 발견한 방송 제목은 원문으로 먼저 커밋되고, 번역은 가공 큐를 거쳐 나중에 커밋된다 |
| `ops` 이관 | admin_state · control 을 읽는 모든 곳(reconcile의 suppress · 편집 락, 명령들)을 새 브랜치로 바꿔야 한다. 이관 스크립트 또는 첫 실행 시 복사 |
| `/enrich` 인증 | 공개 서비스의 경로라 IAM이 아니라 앱 안 OIDC 검증에 의존 |
| **리소스 이름 전환** | Cloud Run 서비스는 이름을 바꿀 수 없어 새로 배포해야 하고, **URL이 바뀐다**. `mewtype-telegram` → `mewtype-intake` 전환 시: 업스트림 폰 Automate 플로우의 URL(경로 `/ingest` 는 그대로) · Telegram webhook 재등록 · 프론트 `monitor.html` 의 `/monitor-live` 주소 · OIDC audience · IAM 바인딩을 같이 바꿔야 한다. 큐 · Scheduler 잡은 v4a 전환 때 어차피 새로 만드는 것이라 추가 비용이 작다. 삭제한 큐 이름은 일정 기간 재사용 불가 **(확인 필요)** — 새 이름을 쓰므로 무관 |

## 10. 채택 조건 — 측정

60건 버스트를 v3.8.2 방식 그대로 현재 / v4a에 흘려 지연 중앙값 · 유실을 비교한다. 유실이 늘거나 팬 화면 기준 지연이 눈에 띄게 늘면 채택하지 않거나
§12의 묶음 커밋을 얹는다.

## 11. 진행 순서 (단계마다 배포 가능)

1. **잔재 제거** — `ingest_queue` drain(`/ingest` 마다 도는 것), `push_monitor.py`.
2. **`ops` 브랜치 신설** — admin_state · control 이관 + 읽기 경로 변경 + control sha 검사.
3. **`mewtype-apply` 큐 · `/apply` 신설 + 적재 전환** — `writers.py` 잡 종류 재사용, 결과 DM을 작업 안으로. 한동안 `/write` 와 병행 후 제거.
4. **지름길 → `reconcile` 적재 통일** — I1 · I2 · I4 · I5 · I6, #12, #14d. `/wake` 제거.
5. **번역 이동** — `mewtype-enrich` 큐 + `/enrich`, `_translate_sweep` 제거, `/translate` 적용 큐 경유.
6. **유실 처리 재배선** — 적재 실패 · 마지막 시도 2지점, `--retroactive` 제거 기준 변경.
7. **이름 전환** — Scheduler 잡 3개 교체(`/tick` → `/reconcile`, `/monitor` → `/snapshot`), 그리고 Cloud Run 리소스 이름 전환(§9, 폰 URL 변경 동반 — 시점은 운영자 판단).
8. **60건 버스트 측정** (§10).
9. **기능 정리** — 별칭(`/notice` = `/ingest notice` 등) · 같은 함수를 타는 명령(14c · 14f) · 사용 빈도(모니터 로그 `flow="cmd"`) 기준.

2~3단계까지 마치면 엉킨 지점 1 · 7이, 4단계까지 마치면 2 · 5와 #12 · #14d가 풀린다.

## 12. v3b 목표안과 비교

| | v3b 목표안 (관제탑 + 우편함) | v4a |
|---|---|---|
| Cloud Run 서비스 | 3개 (게이트 · 감시자 · 관제탑) | 2개 (접수 서비스 · 쓰기 서비스) |
| 우편함 | Pub/Sub (신규 제품) | Cloud Tasks 적용 큐 (현재 큐의 역할 확장) + 가공 큐 |
| 쓰기 방식 | Git Data API 전환 (여러 파일 1커밋) | Contents API 그대로 |
| 묶음 커밋 | 있음 (버스트에 유리) | 없음 |
| 데드레터 | Pub/Sub 기본 제공 | 마지막 시도 판별로 직접 구현 |
| 운영 세션 상태 | data 브랜치 (관제탑이 씀) | `ops` 브랜치로 분리 |
| 업스트림 폰 변경 | `/x` · `/yt` 분리 (경로 변경) | 경로 유지. URL은 리소스 이름 전환 때만 변경 |
| 핵심 차이 | 부품을 더해 역할을 나눔 | 이미 있는 부품으로 쓰는 경로 · 트리거를 한 줄로 모음 |

버스트 성능이 부족하다고 측정되면, v4a 위에 목표안의 "묶음 커밋"만 따로 얹을 수 있다(`/apply` 가 큐에 쌓인 같은 종류 작업을 모아 한 번에 커밋 — 설계 미정).

## 13. 더 근본적인 대안 (참고)

가변 상태를 트랜잭션이 되는 저장소(예: Firestore)로 옮기고 Git은 공개 JSON 출력만 맡기면, 동시 쓰기 문제 자체가 사라진다
(인스턴스 1 제한 · 적용 큐 직렬화 · 409 재시도 불필요). 대신 저장소가 하나 늘고 Git 이력 기반 undo · 감사 방식을 다시 설계해야 한다. v4a 범위 밖.
