# 용어집 (TERMINOLOGY)

세션이 바뀌어도 같은 대상을 같은 단어로 부르기 위한 기준. 표현이 엇갈리면 여기에 추가한다.

| 정식 명칭 | 가리키는 것 | 쓰지 말 것 |
|---|---|---|
| **프론트엔드** | Vercel 정적 호스팅(`src/frontend/`). 빌드 없음, ES 모듈. `raw.githubusercontent.com` 의 JSON 을 폴링해 렌더링만 함. | 프론트서버, 웹앱 |
| **백엔드** | GCP Cloud Run 서비스(`src/backend/`). 메인 콘텐츠(preview·tweet·notice)를 **판정·상태전이·저장**. Cloud Scheduler/Tasks 트리거, GitHub `data` 브랜치에 커밋. 공개 webhook `mewtype-telegram` 도 이 범주. | 서버(단독), GCP(단독) |
| **업스트림 시스템** | 운영자 폰의 Automate 플로우. X·YouTube 푸시알림을 양식만 맞으면 `POST /ingest` 로 **중계**. 데이터 흐름상 백엔드 앞단의 1st-party 노드이며, 코드베이스 밖이라 런타임에서 관측·버전관리가 안 됨. | 외부 백엔드, 폰 릴레이, 서드파티(★ 진짜 서드파티는 X·YouTube 의 푸시알림 시스템이고, 이 폰 플로우는 그 신호의 중계기) |
| **외부 LLM** | Groq 이 서빙하는 LLM(`gpt-oss-120b`/폴백 `gpt-oss-20b`). v3 부터 상용 운영 중. notice 제목 추출·notice/개인트윗 번역 + (v3.6) 외부 채널 콜라보 참여판정·텍스트 예고 최종확인(`participation`/`announces_own_broadcast`) + (v3.2) 크로스오버 공지 비전 OCR. 실패(5xx·재시도 소진)는 정규식/보수적 미등록으로 폴백(정규식이 기준선, LLM 은 보강 — 단 v3.6 최종확인 게이트는 LLM 없이는 등록 자체를 안 함). | 외부 백엔드2, LLM 서버 |
| **제어 채널** | 운영자가 백엔드를 제어·조회하는 경로. 명령(`/status` `/pause` `/resume` `/list` `/ingest` `/edit` `/del` `/undo` 등)으로 `control.json`·`admin_state.json` 을 바꾸거나 상태를 읽음. 데이터 경로(`/tick` `/wake`)와 분리된 out-of-band 경로. 현재 transport 는 텔레그램, 실체는 공개 webhook 서비스 `mewtype-telegram`. | 텔레그램 봇(개념 지칭 시), 관리 콘솔 |
| **DB 관제소** | (v3.8.2) `data` 저장소(GitHub) 접근이 지나가는 유일한 문. 제어 채널·백엔드의 읽기·쓰기를 한 서비스(`mewtype-db-tower`)의 FIFO 큐(읽기끼리 병렬, 쓰기는 방벽·단독)로 모아 처리하고, 속도 제한(403/429)이 걸리면 기다렸다 재시도하며, 대기 상한을 넘기면 503 으로 돌려준다. 개별 GitHub 호출의 순서·속도만 다루고 트랜잭션 직렬화(`/write` 잡)는 백엔드가 맡는다. | 큐 서버, 프록시, DB 서버 |

## 관련 용어 (위 항목에 딸린 것)

- **`POST /ingest`** — 업스트림 시스템이 중계한 푸시알림 텍스트를 백엔드가 받는 공개 엔드포인트. transport 추상화 경계 — 입력 소스가 바뀌어도 이 이후 스키마는 불변.
- **`data` 브랜치** — 백엔드가 상태를 커밋하는 GitHub 브랜치. 코드 없음, JSON 만.
- **`devpapers` 브랜치** — 개발 중 상시 참조하지 않는 문서(배경자료·구버전 기록·운영자용
  설명자료 등)를 모아두는 GitHub 브랜치. `docs/`에서 개발 시 계속 쓰는 4개
  (`SPEC.md`·`TERMINOLOGY.md`·`VERSION.md`·`INGEST_FLOW.md`)만 `main`에 남기고 나머지가
  여기 있다. `PUSH_MONITOR.html`처럼 자동으로 시간마다 갱신·커밋되는 문서도 여기 둔다 —
  `data` 브랜치와 같은 이유로 Vercel 배포 트리거에서 제외돼 있다(`vercel.json`). **"docs
  브랜치"라고 부르지 말 것** — `docs/` 폴더명과 헷갈린다.
- **메인 콘텐츠** — preview(방송예고) · tweet(개인 트윗) · notice(공식 소식) 3종.
