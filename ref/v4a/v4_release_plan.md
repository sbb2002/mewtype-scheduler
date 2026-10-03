# v4 배포 · 머지 계획 — v4a → 정식 v4.0 (유메미타 플레이어는 v4.1)

- 작성: 2026-10-03 · 개정: 같은 날(운영자 결정 반영) · 상태: **계획 — 착수 가능(§8 선택에 이의가 없을 때)**
- 근거: `v4a_design.md`(§3 용어 · §10 대가 · §12 진행 순서) · `v4a_impl_plan.md`(§7 배포 단계 범위) · `v4a_pending_checks.md` · `v4a_decisions.md`
  · 코드 직접 확인(`app.py` · `apply.py` · `jobqueue.py` · `tasks.py` · `writeclient.py` · `storage.py` · `handlers.py` · `telegram_app.py` · `admin_web.py` · `deploy/*.sh`)
- 표기: **[확인]** 오늘 코드·기록으로 직접 확인 / **[확인 필요]** 아직 확인 못 함(추측으로 채우지 않음)

---

## 0. 확정된 결정 (운영자, 2026-10-03)

| # | 결정 |
|---|---|
| 1 | **배포 형태 = Cloud Run, 현재 main 의 배포와 동일한 방식** (Cloud Run 2서비스 + Cloud Scheduler + Cloud Tasks + `data` 브랜치 + Vercel 프론트) |
| 2 | **main 은 핫픽스하지 않는다.** 오늘 같은 문제를 해결하려고 v4a 를 만든 것 — v4 로 전환하는 것이 해결 |
| 3 | 정식 배포되면 **v4.0** 으로 버저닝. 유메미타 플레이어는 **v4.1**. (알파벳 접미사 `v4a` 는 시험판 이름일 뿐, 배포 때 쓰지 않는다) |
| 4 | **이벤트 배너 · LLM 판단 반려/재판단/사용자 판단은 v4.0 에 포함**한다. 배포하면서 써 보고 불편하면 핫픽스로 고친다(별도 사전 검증 기간 없음) |
| 5 | **60건 버스트 합격선은 두지 않는다**(§4-3 에서 이유와 대체 기준). 운영자가 계획에 없던 것으로 인식 — 아래 §4-3 참고 |

오늘 사고(2026-10-03)의 근거는 `v4a_pending_checks.md` 가 아니라 이 계획의 §1 에 요약한다.

---

## 1. 이 계획의 전제 — 오늘 사고와 v4a 실측

| 사실 | 근거 |
|---|---|
| 배포판(v3.8.10)에서 아라레 휴방 트윗(공식 스케줄 QRT)이 미야코 영상 URL 을 근거로 작성자를 게스트로 묶어 **가짜 합동 카드**를 만들었고, 끝난 미야코 방송이 `upcoming` 으로 되살아났다. 운영자가 `/del`(terminate)로 정리 | [확인] 데이터 저장소 커밋 `26113fee`·`ff5b9289`, 이벤트 로그 10-03 |
| v4a 는 같은 입력에서 합동으로 묶지 않았고(D28) 아라레 22:00 한 건만 취소했다. **운영자 개입 없음** | [확인] 러너 관리 페이지 흐름(11:34:39Z, `llm_f832566dfe`) |
| 따라서 main 핫픽스(D28 포팅) 대신 v4a 를 정식화한다 | 운영자 결정 §0-2 |

**이 계획이 풀어야 하는 한 문장**: v4a 의 *처리 로직*은 검증됐다. 하지만 v4a 는 *로컬 PC 에서만* 돌아가도록 연결돼 있다 — **로직은 그대로 두고 연결부만 Cloud Run 용으로 바꿔 운영 데이터 위에 올린다.**

---

## 2. 현황 — 로컬에만 있는 것의 목록 [확인]

v4a 코드는 `storage.is_local()`(= `V4A_RUNTIME=local`) 분기로 로컬과 클라우드를 가른다. 클라우드에서 안 도는 지점은 아래가 전부다.

| # | 위치 | 로컬에서 하는 일 | 클라우드(비로컬)에서 지금 일어나는 일 | 필요한 조치 |
|---|---|---|---|---|
| L1 | `app.py` | 라우트가 `/tick /wake /write /monitor /` 뿐 | v3 그대로. `/apply` 없음 | WP-2 |
| L2 | `apply.submit()` | 적용 큐(`q-apply`)에 적재 후 **결과 대기** | `_q is None` → **그 자리(접수 서비스 프로세스)에서 `handle()` 직접 실행** = 접수 서비스가 data 를 직접 씀(원칙 ① 위반, v3.9 의 409 문제 재발 지점) | WP-3 |
| L3 | `writeclient.call_write()` (`telegram_app.py` 약 40곳 호출) | 로컬이면 적용 큐 적재 | 비로컬이면 기존 **`/write` 동기 HTTP**(OIDC, 429/503 백오프) — v3 에서 검증된 경로. 단 `/write` 가 `writers.dispatch` 만 부르므로 v4a 전용 작업(`yt_notif` · `apply_translation` · `reconcile` · `snapshot` 등)은 처리 못 함 | WP-2 |
| L4 | `handlers._make_task_queue` | `apply.LocalTaskShim`(reconcile 적재) | 기존 `tasks.TaskQueue` → Cloud Tasks `/wake` · `/tick` 로 예약(v3 경로, 동작함) | 그대로 가능 (WP-2 에서 `/wake`·`/tick` 유지) |
| L5 | 접수 서비스의 즉시 예약(URL 확정·공식 스케줄 영상 확인·`yt_notif`) | `apply.enqueue_reconcile` 로 적재 | `tasks.TaskQueue` 를 부르려 하지만 **접수 서비스에는 `TASKS_QUEUE` env 가 없다**(`deploy_telegram.sh`) → 예약 안 됨. 이게 `v4a_feature_audit.md` §1 #12 「불발 24건」의 원인 | WP-3 (env · IAM 추가) |
| L6 | `apply.cancel_video_checks` | 적용 큐에서 그 영상의 예약 reconcile 삭제 | 비로컬이면 **0 반환(아무것도 안 지움)** — 지운 예고가 예약된 확인으로 되살아나는 문제(09-30 실측)가 클라우드에서 재발 | WP-3 |
| L7 | `enrich`(가공 큐) · `handlers` 번역 | `q-enrich` 에 적재 | 비로컬이면 v3 `_translate_sweep` 를 tick 안에서 직접 실행(v3 동작) | v4.0 은 유지 가능(§3 단계 B) |
| L8 | `admin_api` 의 작업 탭 | `apply.pending()` · `apply.recent()` · `enrich.pending()` · `flowtrace`(로컬 파일) | 접수 서비스 프로세스 메모리에는 **큐도 최근 결과도 없다** → 「예정된 확인」「최근 자동 처리」「지금 상태」「최근 흐름」이 비어 보임. `flowtrace` 는 코드 주석에 "배포판은 흐름마다 기록 커밋이 늘어 v3.9 식 브랜치 경합" 이라며 **의도적으로 비로컬 no-op** | WP-5 |
| L9 | `telegram_app._preserve_raw`(D19) | `_local/raw` 에 원문 보존 | `if not storage.is_local(): return` — **조용히 아무것도 안 함**(데이터 저장소가 공개라 원문 노출 위험 때문에 의도적) | WP-9 (운영자 결정 10-03: 데이터 저장소에 보존) |
| L10 | `storage.make_store("ops")` | `_local/ops` | `OPS_BRANCH` env 가 있을 때만 ops 라우팅. **env 없으면 control · admin_state 가 `data` 브랜치에 남는다** | WP-4 |
| L11 | `tg_poll`(텔레그램 getUpdates 폴링) | 로컬 봇 폴링 | 클라우드는 기존 **webhook**(`telegram_webhook.sh`) 사용 | 변경 없음 |
| L12 | `local_runner` 의 스케줄러 스레드(10분 · 06:00 JST · 06:10 KST) | in-process | **Cloud Scheduler 3잡**(기존) | 변경 없음 |
| L13 | 프론트 `config.js` | hostname 이 `*.vercel.app` 이면 GitHub raw URL, 아니면 `/data/*` | Vercel 에서는 raw URL — 동작함. 단 `banners.json` 은 신규 파일 | WP-6 |
| L14 | `deploy/*.sh` | — | **`ADMIN_SECRET` 시크릿 · `OPS_BRANCH` · `/admin` 서빙 설정 없음**(grep 으로 deploy 스크립트에 해당 키 없음 확인) | WP-4 |

### 2-1. 보안 관련 사실 [확인]

- **현재 운영 `mewtype-telegram` 은 `--allow-unauthenticated` + `ALLOW_UNAUTH=1` 로 배포된다**(`deploy_telegram.sh`). `oidc.verify_request` 가 이 값으로 **통째로 건너뛰어진다**. v3 에서는 그 서비스에 OIDC 가 필요한 경로가 거의 없어 무해했지만, v4 에서 `/admin` · `/enrich` 같은 새 경로가 이 서비스에 올라간다.
- `/admin` 은 `ALLOW_UNAUTH` 와 무관하게 **자체 인증**(HMAC 서명 링크 · 5분 만료 · nonce 1회 · 세션 쿠키 `HttpOnly`/`SameSite=Lax` · 쓰기 API CSRF)을 이미 갖췄다 [확인 `admin_web.py`]. 단 클라우드에서 확인할 것:
  1. 쿠키 `Secure` 플래그가 `request.is_secure` 로 정해진다 — Cloud Run 은 TLS 를 앞단에서 끝내므로 `X-Forwarded-Proto` 처리(예: ProxyFix) 없이는 `Secure` 가 **안 붙을 수 있다** [확인 필요].
  2. 로그인 nonce 사용 기록을 `ops` 브랜치에 읽고-쓰는데 접수 서비스는 인스턴스가 여러 개일 수 있어(현행 `max-instances` 미제한) **동시 사용 경합** 가능성 [확인 필요].
  3. `ADMIN_SECRET` 이 Secret Manager 에 없다(L14).
- 쓰기 서비스(`mewtype-backend`)는 `--no-allow-unauthenticated` + 앱 안 OIDC 라 안전하다 [확인].

---

## 3. 전략 — 운영과 같은 방식으로, 스테이징을 앞세워, 서비스 이름·URL 은 그대로

원칙 4개:

1. **로직은 안 건드린다.** 바꾸는 건 §2 표의 연결부(L1~L14)뿐. 판정 로직(D1~D34)은 v4a 그대로.
2. **서비스 이름·URL 을 바꾸지 않는다** — `mewtype-backend` · `mewtype-telegram` 에 새 리비전을 올린다. 설계 §12-9 의 `mewtype-intake/writer` 이름 전환은 **v4.0 범위에서 제외**(§8 에서 확인). 이유: 이름이 바뀌면 폰 Automate URL · Telegram webhook · OIDC audience · IAM · `monitor.html` 주소가 한꺼번에 바뀌어, 오늘 해결하려는 문제와 무관한 위험이 더해진다. 같은 서비스에 새 리비전이면 **코드 롤백이 몇 초**(`gcloud run services update-traffic --to-revisions=<이전 리비전>=100`)다.
3. **운영 컷오버 전에 스테이징에서 먼저 돌린다.** 폰 Automate 는 이미 한 알림을 두 곳(운영 · v4a)으로 보내는 구조(`docs/v4a_automate_wire.md`) — **v4a 쪽 목적지만 로컬 PC → 스테이징 Cloud Run 으로 바꾸면** 운영 영향 없이 실제 트래픽으로 검증된다.
4. **되돌릴 수 있게 컷오버한다**(§6).

### 3-1. v4.0 의 큐 전송 방식 — 가장 큰 설계 갈림길 (§8 확인 대상)

| | 안 1 (권장) **동기 전송 유지 + 연결부만 교체** | 안 2 (설계 §12-3 그대로) **Cloud Tasks 적용 큐 · 가공 큐 비동기화** |
|---|---|---|
| 접수 → 쓰기 | 기존 `/write` 동기 HTTP(v3 에서 검증, 429/503 백오프 있음). `/write` 가 `writers.dispatch` 대신 **`apply.handle`** 을 부르게만 바꾼다 | Cloud Tasks `mewtype-apply` 큐 → 쓰기 서비스 `/apply`. 접수는 적재만 하고 결과를 안 기다림 |
| 바뀌는 코드 | 작음 (`app.py` 1곳 + 접수 서비스 env/IAM) | **큼** — `call_write` 호출 약 40곳(`telegram_app.py`) 중 **반환값을 변수로 받아 쓰는 20곳**(`mode`/`changed` 로 DM 문구 · 분기)을 "적재 후 결과 모름" 으로 바꾸거나, 결과 DM 을 쓰기 서비스로 옮겨야 함. D33(결과 DM)과 충돌 |
| 429 | Cloud Run 이 초과 요청을 거절 → 백오프 재시도로 흡수(v3.9 가 이미 한 방식) | Cloud Tasks 가 재시도 — 429 문제 자체가 사라짐 |
| 오늘 문제와의 관계 | 오늘 문제는 **판정 로직**(D28)이 풀었고 큐 방식과 무관 | 큐 방식은 v3.9 사고 계열(버스트) 대응 |
| 위험 | 버스트 때 접수 서비스의 `/write` 대기가 길어질 수 있음(v3 와 동일 수준) | 비동기 전환의 DM·관리 페이지 동작 변경, Cloud Tasks 순서·중복·크기 가정(설계 §10 "확인 필요" 6건) 미검증 |

**권장은 안 1** — v4.0 은 "검증된 로직을 검증된 전송 위에 올린다". 안 2 는 v4.1 이후 별도 작업으로 분리(설계 §12-3 "한동안 `/write` 와 병행 후 제거"가 이미 병행 단계를 전제). 운영자가 안 2 를 원하면 §4 단계 B 의 WP-3 이 크게 늘어난다(§8).

---

## 4. 단계와 작업 항목

### 단계 A — 준비 (코드 변경 없음)

| # | 작업 | 산출물 |
|---|---|---|
| A1 | **스테이징 환경 정의** — 데이터 저장소에 `data-stage` · `ops-stage` · `monitoring-stage` 브랜치(운영 `data` · `monitoring` 의 사본에서 분기), Cloud Run `mewtype-backend-stage` · `mewtype-telegram-stage`(같은 이미지, env 만 `*-stage` 브랜치로), Cloud Tasks `-stage` 큐, 텔레그램은 **기존 로컬 시험용 봇 토큰**(운영 봇과 분리) 사용 | `deploy/` 스테이징 변수(`env.stage.sh` 가칭) |
| A2 | 시크릿 점검 — `ADMIN_SECRET` 생성(Secret Manager), `GROQ_API_KEY` 등 기존 시크릿 재사용 확인 | 체크리스트 |
| A3 | Cloud Scheduler 잡 비용·한도 확인 — 운영 3잡 + 스테이징 3잡 | [확인 필요] 과금 정책 |
| A4 | 운영 데이터 스냅샷 기준점 기록 — 컷오버 롤백용(§6) | `data`/`ops`/`monitoring` 브랜치 sha 목록 |

### 단계 B — 연결부 이식 (v4a 브랜치에서 코드 수정)

| # | 작업 (대응 §2) | 구체 변경 | 합격 기준 |
|---|---|---|---|
| WP-1 | 작업 이름(`name`) 규칙 점검 | `apply.enqueue_reconcile` 의 이름 `reconcile-video-{id}-{ISO[:16]}` 에 `:` 포함 — Cloud Tasks 태스크 이름은 영문·숫자·`-`·`_` 만 허용 [확인 필요] → 비로컬 경로는 기존 `tasks._build_task` 규칙(`wake-<vid>-<분버킷>`)을 그대로 씀. 로컬 이름은 건드리지 않음 | 기존 `tasks.py` self-test 통과 |
| WP-2 | **쓰기 서비스 라우트** (L1·L3) | `app.py`: `/write` 가 `apply.handle(kind, args, meta)` 를 부르도록(= v4a 전용 작업 처리), **`/tick` · `/wake` · `/monitor` 유지**(컷오버 시점에 Cloud Tasks 에 이미 쌓여 있는 v3 태스크가 이 경로로 도착 — 삭제하면 유실), `/apply` 는 안 만듦(안 1) | self-test + 기존 하네스(`harness.py`)에서 `/write` 경유 시나리오 통과 |
| WP-3 | **접수 서비스 비로컬 경로** (L2·L5·L6) | ① `apply.submit()` 의 `_q is None` 분기에서 **직접 실행 대신 `call_write` 로 위임**(원칙 ① 복구) ② 접수 서비스에 `TASKS_QUEUE` · `GCP_PROJECT` · `GCP_LOCATION` env + 기존 큐 enqueue 권한 → `apply.enqueue_reconcile` 의 비로컬 분기가 `tasks.TaskQueue` 사용(#12 불발 해소) ③ `cancel_video_checks` 비로컬: 태스크 이름 접두 `wake-<video_id>-` 로 목록 조회 후 삭제(`tasks.list/delete` 권한) | 스테이징에서: URL 확정 트윗 → `reconcile(영상)` 예약 확인 · 예고 삭제 → 예약 취소 확인 |
| WP-4 | **ops 브랜치 · 관리 페이지 배포 설정** (L10·L14) | `deploy_telegram.sh`: `OPS_BRANCH` · `ADMIN_SECRET` · `/admin` 이 올라간 같은 서비스 설정, `deploy.sh`: `OPS_BRANCH`. **ops 시딩**: 운영 `data` 의 `control.json`(`paused` · 알림 레벨 · `monitor_auto`)을 `ops` 로 복사(수동, 1회) — **빠지면 컷오버 직후 알림 레벨이 기본값으로 돌아간다** | 스테이징 관리 페이지에서 로그인 · 조회 · 수정 확인 |
| WP-5 | **관리 페이지 클라우드 동작** (L8) | 작업 탭은 큐·최근 결과·`flowtrace` 가 로컬 전용이라 비어 보인다. v4.0 에서는 **빈 화면이 오해를 만들지 않게** 비로컬이면 해당 패널을 「배포판에서는 이벤트 로그(리포트 탭)로 확인」으로 대체 표시. 다른 탭(예고·소식·트윗·원문 투입·유실 원문·운영·리포트)은 data/ops/monitoring 읽기라 동작 | 탭별 점검표 |
| WP-6 | 프론트 호환 (L13) | 새 `banners.js` 가 `banners.json` 404(데이터 저장소에 아직 없음)일 때 조용히 무시하는지, 새 `tweets.js` 가 `posted_at` 없는 옛 트윗 항목을 처리하는지 | 로컬 `python -m http.server` + fixture 로 확인 |
| WP-7 | 보안 (§2-1) | `Secure` 쿠키(`X-Forwarded-Proto`), nonce 경합, `ALLOW_UNAUTH=1` 이 새 경로에 미치는 영향을 `/security-review` 로 점검. `/admin` 은 자체 인증이라 별도지만, 새 경로 추가 시 OIDC 가정이 없는지 확인 | 리뷰 결과 문서 |
| WP-8 | **하네스 재검증** | `ref/v4a/verify/harness.py`(79) · `harness_b.py`(97) · `harness_c.py`(신규) 전부 통과 상태 유지 확인 | 전부 PASS |

| WP-9 | **원문 보존 켜기** (L9) | `_preserve_raw` 의 비로컬 즉시 반환 제거 + `deploy_telegram.sh` 에 `RAW_BRANCH=raw`. 저장 위치 = **데이터 저장소의 `raw` 브랜치**(`storage._ROLE_ENV` 의 기존 기본값, 코드가 이미 이 역할을 가짐). `data` 브랜치 자체가 아닌 이유: 호출부 10곳이 전부 접수 서비스(`telegram_app` · `admin_api`)라, `data` 에 쓰면 쓰기 서비스와 같은 브랜치 HEAD 를 두고 409 경합 — v3.9 에서 `monitoring` 을 분리한 것과 같은 이유. 공개 범위는 `data` 와 같다 | 스테이징에서 공식 스케줄 · 휴방 글 후 `raw/YYYY-MM.jsonl` 에 한 줄씩 |

(L7 가공 큐는 v4.0 에서 v3 `_translate_sweep` 경로 유지.)

### 단계 C — 스테이징 가동 (운영과 병행, 운영 영향 없음)

| # | 작업 |
|---|---|
| C1 | 스테이징 서비스 배포(`mewtype-*-stage`, `--no-allow-unauthenticated`는 쓰기 서비스만) · Scheduler 스테이징 잡 · 텔레그램 webhook 을 시험용 봇으로 |
| C2 | **폰 Automate 의 v4a 쪽 목적지를 로컬 PC → 스테이징 Cloud Run URL 로 변경**(운영자 작업 — `v4a_automate_wire.md` `[47]` 의 URL). 운영 쪽 `[40]` 은 그대로. 이제 모든 알림이 운영 + 스테이징 양쪽으로 들어온다 |
| C3 | **기간**: 최소 7일 + 아래 §5 시나리오가 모두 한 번 이상 실측됨. 하루 단위로 운영(v3.8.10)과 스테이징의 판정을 이벤트 로그로 대조 — 같은 입력에서 판정이 갈리면 어느 쪽이 맞는지 기록(오늘 같은 경우 스테이징이 맞아야 함) |
| C4 | 스테이징에서만 하는 시험: 같은 초 다건 몰림 시 유실 0(§4-3), Cloud Run 콜드 스타트 · 429 백오프, `cancel_video_checks`, ops 시딩 |

### 4-3. 버스트 시험을 합격선으로 두지 않는 이유와 대체 기준

운영자가 "계획에 없던 것"이라고 하신 60건 버스트 측정은 `v4a_design.md` §11 「채택 조건 — 측정」 / §12-10(2026-09-28 작성)에 있던 항목입니다 — 설계 당시 "채택 여부를 정하는 조건"으로 적어 둔 것이고, 운영자가 따로 승인한 결정 목록(설계 머리말의 「사용자 결정」 표)에는 없습니다. **합격선(숫자 기준)은 두지 않습니다.** 다만 이 시스템이 실제로 겪은 사고(09-16 · 09-24 버스트에서 트윗 유실)가 같은 초 몰림이었으므로, 스테이징 시나리오(C4)에 **"같은 초 N건 → 유실 0"** 만 확인 항목으로 남깁니다. 지연 시간 비교는 하지 않습니다.

### 단계 D — 운영 컷오버

| # | 작업 | 메모 |
|---|---|---|
| D1 | **사전 확인**: `git fetch` 후 로컬 트리가 `origin` 과 동기인지 확인 — `gcloud run deploy --source .` 는 **로컬 트리를 올려서**, 뒤처진 상태로 배포하면 프로덕션이 조용히 롤백된다(v3.9 사고, 메모리 `deploy_verify_origin_sync`) | 체크리스트 필수 |
| D2 | **운영 데이터 기준점 기록**(A4)과 `ops` 시딩(WP-4) 완료 확인 | 롤백 근거 |
| D3 | `v4a` → `main` 머지(충돌 없음 [확인], main 은 `6af6db7` 이후 무변경). PR #50 은 v4a 가 같은 수정을 포함하므로 머지 전에 **닫는다**. 머지 push 는 **1회** — Vercel Hobby 하루 100회 한도를 이미 초과한 적이 있어(메모리) 한도 여유가 있는 시각에 | 프론트(tweets/banners/monitor.html) 배포됨 |
| D4 | **쓰기 서비스(`mewtype-backend`) 먼저 배포** → 그 다음 접수 서비스(`mewtype-telegram`). 둘 다 `main` 최신에서. 쓰기가 먼저여야 접수가 `/write` 로 보낸 v4a 전용 작업을 받을 수 있다 | 같은 이름·URL 이라 폰·webhook 변경 없음 |
| D5 | Scheduler 잡: **기존 3잡 그대로**(이름·경로 `/tick` `/monitor` 유지 — WP-2 에서 유지했으므로 변경 불필요) | 이름 전환 안 함 |
| D6 | 폰 Automate v4a 쪽 목적지(C2 에서 바꾼 스테이징 URL)를 **끊거나 스테이징 유지**(운영자 선택). 운영 `[40]` 은 이미 운영 URL | |
| D7 | **버전 기록**: `docs/VERSION.md` 에 v4.0 항목, `CLAUDE.md` 갱신(§7) | |

### 단계 E — 관찰 · 사후

| # | 내용 |
|---|---|
| E1 | 컷오버 후 **48시간** 이벤트 로그 · 유실 큐 · 알림 DM · 팬 화면 · 관리 페이지 관찰. 이상은 핫픽스(§0-4) |
| E2 | 이벤트 배너 · LLM 판단 반려/재판단/사용자 판단은 실사용 중 불편을 모아 핫픽스 |
| E3 | 스테이징 환경 정리(서비스·큐·잡·`*-stage` 브랜치) — 관찰 종료 후 |
| E4 | v4.1(유메미타 플레이어) 설계 착수 — 재료는 `video_releases.json`(ops, 이미 누적) |

---

## 5. 스테이징 검증 시나리오 (실측 필요 항목)

`v4a_pending_checks.md` 의 미확인 항목을 **배포 환경 기준으로** 다시 정리한다. 로컬에서 확인된 것도 클라우드에서 한 번 더 본다.

| # | 시나리오 | 기대 | 로컬 확인 |
|---|---|---|---|
| S1 | **인용 QRT**: 멤버가 공식 일일 스케줄을 인용하며 휴방 트윗 | 합동 카드 안 생김(D28), 해당 멤버 예고만 취소 | ✔ 10-03 실측 |
| S2 | 개인 예고 트윗(URL 있음/없음) · 공식 일일 스케줄 · 합동(出演情報) | 예고 반영, 예고 DM(D29) | 부분(DM 3경로 중 2경로 미확인) |
| S3 | 방송 라이프사이클 upcoming → watching(20분 전) → live → end → out | 이벤트 로그 전이 순서, 종료 후 정리 | ✔ |
| S4 | **URL 확정 예고 → 즉시 reconcile(영상) 예약**(L5) | Cloud Tasks 에 태스크 생성 | ✘ 클라우드에서만 확인 가능 |
| S5 | **예고 삭제 → 예약된 확인 취소**(L6) | 삭제 후 예약 확인이 예고를 되살리지 않음 | ✘ |
| S6 | 같은 초 다건 몰림(트윗 5~10건) | 유실 0, 중복 0 | ✘ |
| S7 | 관리 페이지: 로그인 링크 · 세션 · CSRF · 예고/소식/트윗 수정·삭제 · 원문 투입 미리보기→확정 · 유실 원문 재투입 | 모든 탭 동작, `Secure` 쿠키 | ✘ (WP-7) |
| S8 | LLM 판단 반려 → 7종 재판단/사용자 판단 | 롤백 범위 정확 | ✔(하네스) · 실사용 미확인 |
| S9 | 이벤트 배너(`bang_dream_on` 글) | 배너 갱신/보류/재개/종료 | 부분 |
| S10 | 일시정지 · 재개 · 알림 레벨(ops 시딩 후) | 값 유지, 재개 시 reconcile | ✘ |
| S11 | 컷오버 당일 Cloud Tasks 에 남아 있던 v3 태스크(`/wake`) 도착 | 새 리비전이 정상 처리(WP-2 가 라우트 유지) | ✘ 컷오버 때만 |

---

## 6. 롤백

| 시점 | 방법 |
|---|---|
| 단계 B~C (스테이징) | 스테이징 서비스만 내리면 됨. 운영 영향 없음 |
| **단계 D 직후 코드 문제** | `gcloud run services update-traffic mewtype-backend --to-revisions=<v3.8.10 리비전>=100`, `mewtype-telegram` 도 동일 — **몇 초**. 서비스 이름·URL 이 같아서 폰 · webhook · Scheduler 변경 불필요. `main` 은 필요 시 머지 커밋 revert(Vercel 1회 추가 배포 소모 주의) |
| **데이터 호환 문제** | v4 가 쓴 항목(트윗 `posted_at` + 48h 수명, `ops` 로 옮긴 control, `banners.json`)을 v3.8.10 이 못 읽을 수 있다 — v3.8.10 코드가 모르는 필드는 무시되는지 [확인 필요]. 최악의 경우 D2 의 기준점 sha 로 `data`/`monitoring` 복구 |
| 롤백 불가 지점 | 없음 — 컷오버가 서비스 교체가 아니라 같은 서비스의 리비전 교체이기 때문 |

---

## 7. 문서 · 버전

- 버전: **v4.0**(정식 배포 시). 새 기능 묶음이므로 마이너 이상을 올리는 CLAUDE.md 기준에 부합. 후속 핫픽스는 `v4.0.Z`(Z 만 증가), 알파벳 접미사는 패치 분기가 있을 때만.
- 갱신 대상: `CLAUDE.md`(v4a 델타 상자를 정식 구조 서술로 재작성 — 코드와 어긋난 서술 금지 원칙, 직접 읽고 확인 후), `docs/SPEC.md` · `docs/ARCHITECTURE.md` · `docs/TERMINOLOGY.md`(§3 v4a 용어 중 실제 쓰는 것만 이전 — 새 용어는 운영자와 상의 후 추가) · `docs/VERSION.md`. 이해용 산출물(흐름도 등)은 직접 렌더링·확인한 것만 게시한다.
- `ref/v4a/` 문서는 devpapers 브랜치로 이동할지(배경자료) 컷오버 후 결정.

---

## 8. 계획에 반영한 선택 (이의가 없으면 이대로 진행)

1. **큐 전송 방식 = 안 1** (§3-1). v4a 로컬 시험에서 접수 쪽은 적용 큐에 적재한 뒤 **결과를 기다린다**(`apply.submit(wait=True)`) — 호출하는 쪽에서 본 동작은 안 1(`/write` 동기 호출)과 같고, DM 문구 · 분기도 그 전제로 검증됐다. 안 2(Cloud Tasks 비동기)는 `v4a_impl_plan.md` §1 이 "배포 단계에서 바꿔야 한다"고 적어 둔 방향이지만 **로컬에서 한 번도 안 돌아본 동작**이라 v4.0 범위에서 제외한다.
2. **서비스 이름은 그대로**(`mewtype-backend` · `mewtype-telegram`). 설계 §3 · §12-9 의 `mewtype-intake/writer` 는 이전 세션이 운영자와 논의 없이 정한 이름(운영자 확인 10-03). 운영자 지침 = "운영에 지장 없는 것은 그대로" → 문서 용어로는 남기되, 실제 서비스 이름 변경은 URL · webhook · 폰 설정을 바꾸므로(운영 영향) **하지 않는다**.
3. **원문 보존(D19) 켠다** — 운영자 결정(10-03): 데이터 저장소에 보존. 공개 범위는 이미 공개 중인 `tweet_archive.json`(원문 `text`)과 같은 수준(`v4a_decisions.md` §2-1). 브랜치는 `data` 가 아니라 같은 저장소의 `raw` 브랜치(WP-9 — 쓰기 경합 회피).

## 9. 알려진 위험

| 위험 | 대응 |
|---|---|
| 접수 서비스가 클라우드에서 data 를 직접 쓰는 경로(L2) | WP-3 ① 으로 `call_write` 위임 — 스테이징 S6 에서 동시 몰림으로 확인 |
| `ALLOW_UNAUTH=1` 이 공개 서비스에 켜진 채 새 경로 추가 | WP-7 보안 검토, 새 경로는 자체 인증만 신뢰 |
| ops 시딩 누락 → 알림 레벨·일시정지 상태 초기화 | D2 체크리스트 |
| 컷오버 시점 Cloud Tasks 의 v3 태스크 | WP-2 로 `/wake` `/tick` 유지(S11) |
| 배포 시 로컬 트리가 origin 보다 뒤처짐 | D1 필수 확인 |
| Vercel 하루 배포 한도 | D3 머지 push 1회, 여유 시각 |
| 스테이징 중 운영 데이터 사본이 어긋나 비교가 무의미해짐 | 스테이징은 `*-stage` 브랜치에서만 쓰고, 비교 기준은 "같은 입력에서의 판정"(데이터 상태 아님) |
| 관리 페이지 작업 탭이 배포판에서 비어 보임 | WP-5 로 안내 문구 대체, 이벤트 로그/리포트로 확인 |
