# 夢限大みゅーたいぷ 방송 예고판

> **프로젝트:** 夢限大みゅーたいぷ(무겐다이 뮤타입) 소속 유튜브 방송인 5명의 **예약 방송 · 라이브 상태**를 한곳에서 보여주는 반응형 정적 웹사이트.
> 팬이 들어오면 누가 언제 방송하는지, 지금 라이브 중인지, 어느 주소로 가면 되는지 한눈에 확인한다.
> 비공식 팬 메이드 · 비영리 프로젝트이며 관련 권리는 각 권리사에 있다.

**현재 버전: v4.9.6 (일반 패치 · 2026-10-29)** — 버전별 내역은 [docs/VERSION.md](./docs/VERSION.md), 버전마다 git 태그 `vX.Y.Z`([Tags](https://github.com/sbb2002/mewtype-scheduler/tags))
🌐 운영 사이트: <https://mewtype-schduler.vercel.app/> (주소의 `schduler` 오타는 옛 이름이 그대로 남은 것 — 프로젝트 · 저장소 이름은 `mewtype-scheduler`)

📦 [구현 명세 (docs/SPEC.md)](./docs/SPEC.md) | 🗣 [용어 기준 (docs/TERMINOLOGY.md)](./docs/TERMINOLOGY.md) | 🔀 [ingest 흐름 (docs/INGEST_FLOW.md)](./docs/INGEST_FLOW.md) | 🧭 작업 지침 [CLAUDE.md](./CLAUDE.md)

---

## 화면 (프론트엔드)

| 기능 | 설명 |
|---|---|
| **오늘 타임테이블** | PC = 멤버별 가로 편성 레일(KST 06:00~익일 06:00) 위에 예고 · 라이브 · 종료 블록. 호버 = 카드 팝업, 예고 블록은 「방송시작까지 n시간/n분」. 보기 방식 탭 [테이블 \| 카드]. 모바일 = 멤버 1명씩 슬라이드하는 오늘 카드(카운트다운 링) |
| **이후 예고** | 오늘 구간 밖 · 시각 미정 예고를 펼쳐 보는 목록 |
| **소식 · 행사 배너** | 방송 외 이벤트 소식판(`#notice` — 분류 탭(LLM 판정 6분류, 한 소식에 여럿), 라이브공연 탭 공연별 묶음(공연일 + 7일까지, 지난 소식은 어둡게), 제목 한 줄, 가리키거나 누르면 번역 본문 · X 카드가 담긴 팝업 카드)과 게임 행사 · 가챠 배너 카드(D-n 진행 막대, 좌우로 끌어 넘김) |
| **멤버 트윗 말풍선** | 멤버 아바타의 편지 배지 → X 공식 트윗 카드 + 한국어 번역 말풍선 |
| **마이크로 인터랙션** | 조작을 돕는 작은 보조 동작 — 시트 · 토스트 끌어 닫기, 트윗 없는 멤버를 누르면 「새 트윗 없음」, 재생목록 비우기 되돌리기 · 밀어서 빼기, 반복 · 셔플 상태 말풍선, 처음 한 번만 뜨는 안내 등 |
| **유메미타 플레이어** | 곡 목록(검색 · 독음 · 신곡)과 YouTube 임베드 재생, 재생목록 · 셔플 · 반복, **랜덤플리 오마카세**(전체/오리지널/커버를 무작위로 재생목록에 넣어 재생) |
| **밝게 / 어둡게** | 소식 막대 마지막 칸의 해/달 버튼, 기기 설정을 따라감 |
| **하단 디스클레이머** | 비공식 · 번역 안내 · 방문 통계 고지. 마우스를 2초 올리면 전체 팝업(포커스는 바로) |
| 이스터에그 | 노노카 지각 연출(`king.js`), 운영 모니터 페이지 진입(`monitor.html`) |

데이터는 모두 `data` 저장소의 JSON(`preview.json` · `notices.json` · `tweets.json` · `banners.json` · `songs.json` 등)을 75초마다 fetch한다.
`raw.githubusercontent.com` 캐시 때문에 최대 약 5분 지연되는 것은 의도된 트레이드오프다.

---

## 동작 방식 (백엔드)

서버를 상시 가동하지 않는다. 무료 인프라만 쓴다.

```
 업스트림(운영자 폰 Automate)      YouTube PubSub 알림       Cloud Scheduler            Cloud Tasks
  X · YouTube 앱 알림 중계             (WebSub 푸시)       (baseline · light 10분 ·       (방송별 정밀 wake)
          │                                 │              monitor · websub-renew)            │
          ▼                                 ▼                         ▼                      ▼
   mewtype-telegram (제어 채널, 공개)  ──────────────►  mewtype-backend (수집 · 판정, concurrency=1)
   텔레그램 webhook · /ingest · /websub                  /tick · /wake · /write · /monitor
          │  쓰기는 /write 로 직렬화                              │
          └──────────────────────► GitHub Contents API ◄────────┘
                                   저장소 mewtype-scheduler-data (data · monitoring 브랜치)
                                            │ raw.githubusercontent.com
                                            ▼
                               프론트엔드 (Vercel, src/frontend)
```

- **수집/판정**: Cloud Run 두 서비스 — `mewtype-backend`(`/tick` `/wake` `/write` `/monitor`)와 `mewtype-telegram`(텔레그램 webhook · 업스트림 `/ingest` · PubSub 콜백). 리전 `asia-northeast1`.
  YouTube RSS · Data API로 발견한 방송을 6상태(`none` `announced` `upcoming` `watching` `live` `end`) FSM으로 `preview.json` 에 재구성한다(상태는 저장하지 않고 항목에서 파생).
- **번역/판정 LLM**: Groq(`gpt-oss-120b`, 폴백 `gpt-oss-20b`)가 트윗 · 소식 · 방송 제목 번역, 본인 예고 · 행사 판정 등을 맡는다. 번역에 일본어가 남으면 1회 재요청하고, 반각 가타카나는 전각으로 바꿔 보낸다(v4.5.7).
- **새 방송 발견**: 10분마다 RSS 폴링 + YouTube PubSub 알림(WebSub). 방송 시작/종료는 방송별 Cloud Tasks wake가 추적한다.
- **저장**: 별도 저장소 `sbb2002/mewtype-scheduler-data` 의 `data` 브랜치(서비스 데이터) · `monitoring` 브랜치(이벤트 로그). 변경분만 GitHub Contents API로 커밋한다.
- **운영 도구**: 텔레그램 봇(`/status` `/pause` `/resume` `/list` `/admin` 등)과 운영 모니터 리포트(`monitor_report` · `monitor_snapshot`).
- **프론트**: Vercel 정적 호스팅(빌드 없음). `main` 브랜치만 배포하고 `devpapers` 등 나머지 브랜치는 배포에서 제외한다(`src/frontend/vercel.json`).

> `src/collector/` 는 **v1 수집기의 잔재**다. `config` · `rss` · `youtube` 는 백엔드가 가져다 쓴다. v1 실행기(`main.py` · `reconcile` · `store` + GitHub Actions `collect.yml`)와 그 결과를 받던 이 저장소의 `data` 브랜치는 2026-10-20 에 지웠다(기록 = 태그 `archive/data-2026-09-15`).

---

## 저장소 구조

```
mewtype-scheduler/
├── src/
│   ├── frontend/          # Vercel 정적 호스팅 (Root Directory = src/frontend)
│   │   ├── index.html · monitor.html · vercel.json
│   │   ├── css/           # layout · timetable · card · notices · banners · tweets · player* · king · theme …
│   │   ├── js/            # main · render · timetable · notices · banners · tweets · player · songs · theme · king …
│   │   │                  #   + *.selfcheck.mjs (브라우저 없이 도는 단위 점검)
│   │   └── assets/songs.json   # 플레이어 곡 목록 시드
│   ├── backend/           # Cloud Run 서비스 (Flask + gunicorn): app · telegram_app · handlers · preview_build ·
│   │                      #   statemachine · llm · xtweet · xrelay · xnotice · banners · songs · websub · gh_store …
│   ├── collector/         # v1 순수 모듈 — config · rss · youtube 는 백엔드가 재사용
│   └── bus/               # 에러 버스 발신기 (MEW_BUS_DIR 없으면 no-op)
├── config/channels.json   # 5채널 메타 단일 소스 (핸들 · 채널 ID · 한글명 · X 표시명 · 호칭)
├── deploy/                # gcloud 배포 스크립트 (setup · deploy · deploy_telegram · scheduler · telegram_webhook) + README
├── docs/                  # SPEC · TERMINOLOGY · VERSION · INGEST_FLOW … (그 외 배경자료는 devpapers 브랜치)
├── fixtures/              # 프론트 · 파서 테스트용 샘플 데이터
├── scripts/               # 일회성 보조 스크립트
└── Dockerfile             # 두 Cloud Run 서비스가 공유 (엔트리포인트만 다름)
```

브랜치: `main`(배포 대상) · `data`(데이터 저장소 쪽) · `devpapers`(개발 배경 문서 · 자동 생성 모니터 HTML — Vercel 배포 트리거 밖).
작업 브랜치 이름에는 버전 번호를 쓰지 않는다(`hotfix/<이름>` · `test/<이름>`).
버전은 **태그**로 남긴다 — 버전이 `main` 에 들어온 병합 커밋에 `vX.Y.Z` 주석 태그를 붙이고, 이 README 맨 위 「현재 버전」 줄도 같이 고친다
(절차: [CLAUDE.md](./CLAUDE.md) 「주의점」 **버전 올릴 때 할 일**). 태그 → 커밋 · 브랜치 대조는 [docs/VERSION.md](./docs/VERSION.md) 맨 위 「버전 태그 대조표」,
어떤 커밋의 버전은 `git describe --tags <커밋>`.

로컬 워크트리는 메인 저장소 옆 `mewtype-scheduler-worktrees/<큰 버전>/<브랜치 이름의 / 를 - 로>` 에 둔다
(예: `hotfix/web-analytics` → `mewtype-scheduler-worktrees/v4/hotfix-web-analytics`, `main` 은 메인 저장소 폴더 `mewtype-scheduler/` 자체, `devpapers` 는 `mewtype-scheduler-worktrees/devpapers`).

---

## 로컬 실행

### 프론트엔드

정적 서버는 **저장소 루트**에서 실행한다(fixture 상대경로 `../../fixtures/...` 가 서버 루트 밖으로 나가지 않도록).

```bash
python -m http.server 8099
# http://localhost:8099/src/frontend/
```

로컬 호스트에서는 운영 `data` 저장소의 실데이터를 그대로 읽는다. 샘플 데이터로 보려면 `src/frontend/js/config.js` 의 `PREVIEW_URL` 을
`../../fixtures/preview.sample.json` 으로 임시 교체한다(주석 처리된 줄 있음). 브라우저가 이전 스크립트를 캐시할 수 있으니 확인 땐 강력 새로고침(Ctrl+Shift+R).

### 점검 (테스트 프레임워크 없음 — 모듈마다 self-test)

```bash
# 프론트 (Node)
node src/frontend/js/king.selfcheck.mjs && node src/frontend/js/songs.selfcheck.mjs
node src/frontend/js/timetable.selfcheck.mjs && node src/frontend/js/render.selfcheck.mjs && node src/frontend/js/time.selfcheck.mjs

# 백엔드 (네트워크 불필요, Windows 콘솔은 PYTHONIOENCODING=utf-8 권장)
python -m src.backend.llm            # 번역 · 판정 프롬프트 · 가나 잔존 재요청 등
python -m src.backend.preview_build  # 6상태 재구성
python -m src.backend.statemachine   # FSM
python -m src.backend.xtweet         # 개인 트윗 파서
python -m src.backend.websub         # PubSub 수신
```

전체 목록은 [CLAUDE.md](./CLAUDE.md) 「명령」 절 참고. 실제 LLM 호출 점검은 `GROQ_API_KEY` 가 있을 때만 가능하다.

### 백엔드 로컬 시험 러너

`python -m src.backend.local_runner` 는 클라우드 없이 PC 에서 백엔드를 돌려 보는 시험용 러너다(저장은 `_local/`). 방법과 검증 기록은
[ref/v4a/v4a_local_runbook.md](https://github.com/sbb2002/mewtype-scheduler/blob/devpapers/ref/v4a/v4a_local_runbook.md) (`devpapers` 브랜치).

---

## 배포

### 프론트엔드 — Vercel (자동)

- Vercel 프로젝트 Root Directory = `src/frontend`, Build Command 없음.
- **`main` 브랜치에 푸시하면 자동 배포**된다(다른 브랜치는 `vercel.json` 으로 제외). 하루 배포 횟수 한도가 있어 봇이 커밋하는 브랜치는 반드시 배포에서 빼야 한다.
- 방문 통계는 Vercel Web Analytics(쿠키 없음 · 익명 집계)이며 하단 디스클레이머에 고지한다.

### 백엔드 — Cloud Run (수동 스크립트)

gcloud 로그인과 `deploy/env.sh`(루트 `.env` 매핑, git 제외)가 필요하다. 상세 · 롤백은 [deploy/README.md](./deploy/README.md).

```bash
bash deploy/setup.sh                                   # API · SA · IAM · Cloud Tasks 큐 · Secret (멱등)
bash deploy/deploy.sh                                  # mewtype-backend
bash deploy/scheduler.sh                               # Scheduler 잡 (URL 불변이면 생략 가능)
bash deploy/deploy_telegram.sh && bash deploy/telegram_webhook.sh   # mewtype-telegram
```

`llm.py` · `telegram_app.py` 처럼 **두 서비스가 공유하는 코드를 바꾸면 `deploy.sh` 와 `deploy_telegram.sh` 를 둘 다** 실행한다.
`--source .` 배포는 로컬 작업 트리를 올리므로, 배포 전에 `origin/main` 과 동기화됐는지 먼저 확인한다.

### Secret / 환경 변수 (값은 저장소에 없음)

Secret Manager: `GROQ_API_KEY`(번역 · 판정 LLM) · `WEBSUB_SECRET`(PubSub 서명) · `VERCEL_TOKEN`(모니터 리포트의 배포 시도 수) · GitHub 데이터 저장소용 fine-grained PAT · 텔레그램 봇 토큰 · 업스트림 인증 비밀.
`YOUTUBE_API_KEY` 는 YouTube Data API 호출에 쓴다. 이름과 주입 방식은 `deploy/` 스크립트와 `deploy/README.md` 에 있다.

---

## 파일 설명

- `config/channels.json`: 5개 채널의 메타데이터 단일 소스(채널 추가 · 변경은 여기만). 그룹 공식 채널 · 뮤타입 음원 채널(`song_feeds`) · 게임 계정(`game_accounts`)도 여기서 관리한다.
- `docs/SPEC.md`: 데이터 계약(preview · notices · tweets · banners …)과 백엔드 · 프론트 모듈 명세.
- `docs/TERMINOLOGY.md`: 문서 · 코드 간 용어 기준. 새 용어는 뜻을 함께 적어 여기에 올린다.
- `docs/VERSION.md`: 버전별 추가 · 변경 · 제거 요약(내림차순).

---

## 라이센스 · 고지

공개 메타데이터를 활용한다. YouTube 썸네일은 `i.ytimg.com` 핫링크를 쓰고, 트윗은 X 공식 임베드로 표시한다. 번역은 비공식 팬 번역이며 AI(Groq)가 만든다.
삭제 · 문의 요청은 [GitHub Issues](https://github.com/sbb2002/mewtype-scheduler/issues) 로 받는다.
