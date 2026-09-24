# 용어집 (TERMINOLOGY)

세션이 바뀌어도 같은 대상을 같은 단어로 부르기 위한 기준. 표현이 엇갈리면 여기에 추가한다.

| 정식 명칭 | 가리키는 것 | 쓰지 말 것 |
|---|---|---|
| **프론트엔드** | Vercel 정적 호스팅(`src/frontend/`). 빌드 없음, ES 모듈. `raw.githubusercontent.com` 의 JSON 을 폴링해 렌더링만 함. | 프론트서버, 웹앱 |
| **백엔드** | GCP Cloud Run 서비스(`src/backend/`). 메인 콘텐츠(preview·tweet·notice)를 **판정·상태전이·저장**. Cloud Scheduler/Tasks 트리거, GitHub `data` 브랜치에 커밋. 공개 webhook `mewtype-telegram` 도 이 범주. | 서버(단독), GCP(단독) |
| **업스트림 시스템** | 운영자 폰의 Automate 플로우. X·YouTube 푸시알림을 양식만 맞으면 `POST /ingest` 로 **중계**. 데이터 흐름상 백엔드 앞단의 1st-party 노드이며, 코드베이스 밖이라 런타임에서 관측·버전관리가 안 됨. | 외부 백엔드, 폰 릴레이, 서드파티(★ 진짜 서드파티는 X·YouTube 의 푸시알림 시스템이고, 이 폰 플로우는 그 신호의 중계기) |
| **외부 LLM** | Groq 이 서빙하는 LLM(`gpt-oss-120b`/폴백 `gpt-oss-20b`). v3 부터 상용 운영 중. notice 제목 추출·notice/개인트윗 번역 + (v3.6) 외부 채널 콜라보 참여판정·텍스트 예고 최종확인(`participation`/`announces_own_broadcast`) + (v3.2) 크로스오버 공지 비전 OCR. 실패(5xx·재시도 소진)는 정규식/보수적 미등록으로 폴백(정규식이 기준선, LLM 은 보강 — 단 v3.6 최종확인 게이트는 LLM 없이는 등록 자체를 안 함). | 외부 백엔드2, LLM 서버 |
| **제어 채널** | 운영자가 백엔드를 제어·조회하는 경로. 명령(`/status` `/pause` `/resume` `/list` `/ingest` `/edit` `/del` `/undo` 등)으로 `control.json`·`admin_state.json` 을 바꾸거나 상태를 읽음. 데이터 경로(`/tick` `/wake`)와 분리된 out-of-band 경로. 현재 transport 는 텔레그램, 실체는 공개 webhook 서비스 `mewtype-telegram`. | 텔레그램 봇(개념 지칭 시), 관리 콘솔 |

## 관련 용어 (위 항목에 딸린 것)

- **`POST /ingest`** — 업스트림 시스템이 중계한 푸시알림 텍스트를 백엔드가 받는 공개 엔드포인트. transport 추상화 경계 — 입력 소스가 바뀌어도 이 이후 스키마는 불변.
- **`data` 브랜치** — 백엔드가 상태를 커밋하는 GitHub 브랜치. 코드 없음, JSON 만.
- **`monitoring` 브랜치** (v3.9) — 데이터 저장소의 **로그 전용** 브랜치. 이벤트 로그
  (`monitoring/events-*.jsonl`)·모니터 스냅샷(`latest.html`)·유실 원문 큐(`lost_queue.json`)가
  여기 쌓인다. `data` 에서 분기해 만들어 과거 로그를 히스토리째 승계했다. **분리한 이유**는
  GitHub Contents API 의 PUT 이 파일이 아니라 **브랜치 HEAD 단위로 충돌**하기 때문 — 이 로그들은
  `/write` 직렬화 창구를 거치지 않고 제어 채널이 직접 커밋하는데, 제어 채널은 인스턴스가 최대
  20개라 버스트 때 `data` 브랜치 쓰기를 409 로 밀어냈다(2026-09-24 트윗 유실 사고).
  env `MONITOR_BRANCH` 로 지정(기본 `monitoring`). "로그 브랜치"라고 불러도 되지만 문서·코드
  표기는 `monitoring` 브랜치로 통일.
- **`devpapers` 브랜치** — 개발 중 상시 참조하지 않는 문서(배경자료·구버전 기록·운영자용
  설명자료 등)를 모아두는 GitHub 브랜치. `docs/`에서 개발 시 계속 쓰는 4개
  (`SPEC.md`·`TERMINOLOGY.md`·`VERSION.md`·`INGEST_FLOW.md`)만 `main`에 남기고 나머지가
  여기 있다. `PUSH_MONITOR.html`처럼 자동으로 시간마다 갱신·커밋되는 문서도 여기 둔다 —
  `data` 브랜치와 같은 이유로 Vercel 배포 트리거에서 제외돼 있다(`vercel.json`). **"docs
  브랜치"라고 부르지 말 것** — `docs/` 폴더명과 헷갈린다.
- **메인 콘텐츠** — preview(방송예고) · tweet(개인 트윗) · notice(공식 소식) 3종.
- **모니터링 스냅샷** — (v3.8.9) 매일 KST 06:10 백엔드 `/monitor` 가 방금 끝난 하루(06:00~익일
  06:00 KST)의 모니터 리포트 데이터를 계산해 굳혀 둔 것. `monitoring/days/YYYY-MM-DD.json`
  (하루치 상세) + `monitoring/summary.json`(전 기간 잔디용 요약), `monitor_snapshot.py`.
  웹 monitor 는 오늘치만 실시간으로 계산하고 지난 날짜는 이것을 읽는다. 외부 조회값
  (healthchecks.io·Vercel)은 찍은 시각(`snapshotAt`) 기준. **"스냅샷"만 단독으로 쓰지 말 것** —
  undo 스냅샷(`/undo` 되돌리기용), reconcile 의 "이전 스냅샷 대비 diff" 와 헷갈린다.
