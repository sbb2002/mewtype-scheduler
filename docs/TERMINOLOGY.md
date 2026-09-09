# 용어집 (TERMINOLOGY)

세션이 바뀌어도 같은 대상을 같은 단어로 부르기 위한 기준. 표현이 엇갈리면 여기에 추가한다.

| 정식 명칭 | 가리키는 것 | 쓰지 말 것 |
|---|---|---|
| **프론트엔드** | Vercel 정적 호스팅(`src/frontend/`). 빌드 없음, ES 모듈. `raw.githubusercontent.com` 의 JSON 을 폴링해 렌더링만 함. | 프론트서버, 웹앱 |
| **백엔드** | GCP Cloud Run 서비스(`src/backend/`). 메인 콘텐츠(preview·tweet·notice)를 **판정·상태전이·저장**. Cloud Scheduler/Tasks 트리거, GitHub `data` 브랜치에 커밋. 공개 webhook `mewtype-telegram` 도 이 범주. | 서버(단독), GCP(단독) |
| **업스트림 시스템** | 운영자 폰의 Automate 플로우. X·YouTube 푸시알림을 양식만 맞으면 `POST /ingest` 로 **중계**. 데이터 흐름상 백엔드 앞단의 1st-party 노드이며, 코드베이스 밖이라 런타임에서 관측·버전관리가 안 됨. | 외부 백엔드, 폰 릴레이, 서드파티(★ 진짜 서드파티는 X·YouTube 의 푸시알림 시스템이고, 이 폰 플로우는 그 신호의 중계기) |
| **외부 LLM** | Groq 이 서빙하는 LLM. v3 에서 도입 검토 중(미확정). notice 제목 추출 + notice/개인트윗 번역. 실패 시 폴백은 정규식(정규식이 기준선, LLM 은 보강). | 외부 백엔드2, LLM 서버 |
| **제어 채널** | 운영자가 백엔드를 제어·조회하는 경로. 명령(`/status` `/pause` `/resume` `/list` `/ingest` `/edit` `/del` `/undo` 등)으로 `control.json`·`admin_state.json` 을 바꾸거나 상태를 읽음. 데이터 경로(`/tick` `/wake`)와 분리된 out-of-band 경로. 현재 transport 는 텔레그램, 실체는 공개 webhook 서비스 `mewtype-telegram`. | 텔레그램 봇(개념 지칭 시), 관리 콘솔 |

## 관련 용어 (위 항목에 딸린 것)

- **`POST /ingest`** — 업스트림 시스템이 중계한 푸시알림 텍스트를 백엔드가 받는 공개 엔드포인트. transport 추상화 경계 — 입력 소스가 바뀌어도 이 이후 스키마는 불변.
- **`data` 브랜치** — 백엔드가 상태를 커밋하는 GitHub 브랜치. 코드 없음, JSON 만.
- **메인 콘텐츠** — preview(방송예고) · tweet(개인 트윗) · notice(공식 소식) 3종.
