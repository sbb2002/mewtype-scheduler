# v3 개선 코멘트 — 구동·운영 효율 전방위 점검 (2026-09-17)

> 작성 기준: `main` HEAD `b07d7b5`(2026-09-17 11:27 KST) 코드 전체 + `docs/` 4종 + `deploy/` +
> 프론트엔드 전부를 직접 읽고, 실배포(Cloud Run 리비전·Cloud Logging·`data` 저장소 커밋 이력·
> Groq 사용 로그)를 조회해 수치를 붙였다. 추측으로 채운 항목은 **"확인 필요"** 로 표시했다.
> 용어는 `docs/TERMINOLOGY.md` 기준(프론트엔드 / 백엔드 / 업스트림 시스템 / 외부 LLM / 제어 채널).
>
> 이 문서는 "무엇을 고치면 좋은가"의 제안서다. 각 항목에 근거(파일:줄, 측정값, 재현 커맨드)를
> 달았으니 결정은 사용자가 내리면 된다. 우선순위는 **P0(지금 장애) > P1(운영 리스크·비용) >
> P2(설계 부채·문서 불일치) > P3(정리·최적화)**.

---

## 0. 한눈에 보기

| 우선순위 | 항목 | 한 줄 요약 | 근거 |
|---|---|---|---|
| **P0** | [1] `/ingest` 개인 트윗 전부 500 | 오늘 11:29 KST 배포된 write-queue 리비전에 변수 스코프 버그. 멤버 5인 트윗이 **전부 유실 중** | 재현 성공 + Cloud Logging 트레이스 + 48h 5xx 3건 |
| **P1** | [2] 모니터링 로그가 커밋의 95% | `data` 저장소 하루 463커밋 중 439건이 `data: monitor`. v3.2.2 가 없앤 "하트비트 커밋"을 다른 형태로 부활시킴 | GitHub API 커밋 집계 |
| **P1** | [3] write-queue 설계 재검토 | 직렬화 보장이 불완전(monitor/admin/control 은 우회) + 외부 LLM·YouTube API 호출이 직렬 구간 안에서 실행됨 | 코드 추적 + 충돌 재시도 로그 13건/24h |
| **P1** | [4] 외부 LLM 폴백 모델 불일치 | `telegram_app._make_llm_client` 기본값이 404 나는 `llama-3.3-70b-versatile` | Groq 로그 404 2건/일 |
| **P2** | [5] wake 빈도·Cloud Run 무료 티어 | 하루 wake 418건, 라이브 후기 3분 cadence 는 CDN 5분 캐시에 묻힘. 백엔드 CPU 무료 티어 ~45% 소진(추정) | 이벤트 로그 + 요청 지연 실측 |
| **P2** | [6] `apply_overrides` 미연결 | 문서(SPEC·CLAUDE.md)는 "tick 이 호출"이라 하지만 실제로 어디서도 안 부름 → 트윗/릴레이 시각이 API 변경을 영영 못 따라감 | grep 결과 |
| **P2** | [7] 배포 재현성 | `setup.sh` 가 `HEALTHCHECKS_IO_READONLEY_TOKEN` Secret 을 안 만드는데 `deploy.sh` 는 필수 마운트 → 새 프로젝트에서 배포 실패 | 스크립트 대조 |
| **P2** | [8] 문서 불일치 다수 | README 는 v2.7 시대, SPEC 은 light 3h·폴백 llama·`/write` 부재, CLAUDE.md 는 writers/writeclient 부재 등 | 문서 vs 코드 대조 |
| **P3** | [9] 공개 노출 | `monitoring/latest.html` 이 공개 저장소 raw URL 로 누구나 열람 가능 — 이스터에그 진입은 형식적 | 저장소 public 확인 |
| **P3** | [10] 코드·인프라 정리 | 죽은 v1 break-glass 경로, 세션 미재사용, RSS 순차 fetch, 오타 Secret 이름 등 | 코드 |
| **P3** | [11] 프론트엔드 | 75초 폴링 vs raw CDN 300초 캐시 — ETag 조건부 요청, "업데이트" 표시 UX | 헤더 실측 |

---

## 1. [P0] `/ingest` 개인 트윗 경로가 UnboundLocalError 로 500 — 지금 유실 중

### 무엇이 문제인가

`src/backend/telegram_app.py` 의 `/ingest` 라우트(`_ingest`, 3417행)에서 `gh` 지역변수가
**정의되기 전에 사용**된다.

- 3489행: 개인 5인 라우팅 분기 → `writeclient.call_write("personal_tweet", gh=gh, ...)`
- 3551행: ECHO 블록 → `writeclient.call_write("ingest_queue_push", gh=gh, ...)`
- 그런데 `gh = None` 은 3572행, `gh = _make_gh()` 는 3600행에서야 나온다.

파이썬은 함수 안에서 한 번이라도 대입되는 이름을 통째로 지역변수로 취급하므로, 3489행에
도달하는 순간 `UnboundLocalError: cannot access local variable 'gh'` 가 나고 Flask 가 500 을
돌려준다. 개인 5인 표시명(`x_names`)으로 라우팅되는 트윗은 **한 건도 처리되지 않는다** —
배지도, 예고 승격도, 번역도 전부 그 전에 죽는다.

### 확인한 증거

1. **로컬 재현**: `/ingest` 에 `title=仲町あられ` 로 POST → 500 + 위 트레이스 (재현 스크립트는
   §12 참고).
2. **정적 검사**: `ruff check --select F821` → `telegram_app.py:3489:42 F821 Undefined name 'gh'`,
   `:3551:64` 동일. (프로젝트에 린터가 없어서 못 잡았다 — §10 참고.)
3. **실배포 상태**: `mewtype-telegram-00069` 리비전이 2026-09-17 11:29:39 KST 에 배포됨
   (HEAD 커밋 11:27:02 KST 직후). Cloud Logging 에 같은 트레이스가 13:11:44 KST 에 찍혀
   있고, `/ingest` 5xx 가 48시간 내 3건(12:01, 13:11 ×2 KST). 오늘 `monitoring/events-2026-09-17.jsonl`
   에 `tweet` 이벤트가 0건(어제는 15건)인 것과 맞아떨어진다.
4. 업스트림 시스템(Automate)이 500 을 받았을 때 재전송하는지는 **확인 필요** — 재전송 안 하면
   그 3건은 그대로 유실이다. 당장은 `/ingest tweet <유닛>` 으로 수동 재등록이 가능하다.

### 어떻게 고치나 (제안)

`gh` 를 라우팅보다 **앞에서** 한 번 만든다. `_maybe_personal_tweet` 자체는 넘겨받은 `gh` 를 안
쓰고 내부에서 `_make_gh()` 를 새로 만들지만, `writeclient.call_write` 의 로컬 디스패치
경로(`MAIN_SERVICE_URL` 미설정)는 `gh` 가 필요하므로 아래처럼 두는 게 안전하다.

```python
# telegram_app.py _ingest — now_iso 계산 직후, route_by_title 분기 전으로 이동
now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
gh = _make_gh()            # ← 여기서 한 번. 아래 3572행 `gh = None` 은 삭제, 3600행은 `if gh is None:` 검사만 남김
```

그리고 **회귀 테스트**를 `telegram_app.py` self-test 에 추가할 것 — 현재 self-test 는 `/telegram`
웹훅은 test_client 로 치지만 `/ingest` 라우트는 한 번도 안 친다(§12 의 재현 스크립트를 그대로
넣으면 된다). 배포 전 `ruff check --select F821,F823` 한 줄이면 이 부류는 전부 걸린다.

### 왜 self-test 를 통과했나

self-test 는 `_maybe_url_confirmed_schedule` 등 **함수 단위**만 부르고, 라우트 함수 `_ingest` 는
안 부른다. 22개 모듈 self-test 전부 OK(§12) 인데도 프로덕션이 죽어 있는 이유가 이것이다.
"라우트 = 통합 경계" 를 테스트 사각지대로 두면 write-queue 처럼 라우트 안에서 배선을 바꾸는
변경이 조용히 깨진다.

---

## 2. [P1] 모니터링 이벤트 로그가 `data` 저장소 커밋의 95%

### 측정값

| 날짜(06:00 KST 경계) | 총 커밋 | `data: monitor` | 나머지 |
|---|---|---|---|
| 2026-09-16 | **463** | **439 (95%)** | preview 8 · tweet 7 · preview_archive 3 … |
| 2026-09-17 (~14:00 까지) | 37 | 35 | undo 1 · notice 1 |

`monitoring/events-2026-09-16.jsonl` 은 520줄: **wake 418** · tick 44 · relay 20 · preview 15 ·
tweet 15 · notice 8. (09-16 은 v3.6 배포 전 3h tick 이 섞여 tick 이 44 — 오늘은 8시간에 50건,
즉 10분 cadence 그대로.)

### 왜 이렇게 되나

`handlers._run` 끝에서 `log_event(gh, now_iso, "wake"/"tick", ...)` 를 **무조건** 부른다
(상태 변화가 없어도). `monitor_log.log_event` 는 이벤트 1건마다 `read_text` + `write_text`
= GitHub API 2회 + **커밋 1개**다. 여기에 `preview` 전이 이벤트가 있으면 이벤트마다 또 커밋.
telegram 쪽 `_maybe_auto_notice`/`_maybe_personal_tweet`/`/pause`/`/resume` 도 각각 커밋.

즉 v3.2.2 가 "`generated_at` 한 줄만 바뀐 하트비트 커밋 118건/일" 을 없앤 바로 그 자리에,
"`events-*.jsonl` 한 줄만 늘어난 커밋 440건/일" 이 들어왔다. `data` 저장소가 Vercel 과
분리돼 배포 한도는 안 먹지만, 다음 비용은 그대로다:

- **409 충돌의 주범**: 백엔드가 3분에 한 번꼴로 브랜치 HEAD 를 갱신하니 제어 채널(telegram)
  쪽 쓰기가 자꾸 부딪힌다. 최근 24h 로그에 "충돌 — 재시도" 가 telegram 11건 · backend 2건.
  write-queue(§3)를 만든 계기(노노카 트윗 유실)의 **근본 원인이 이 커밋 밀도**일 가능성이
  높다 — 큐로 우회하기 전에 원인을 줄이는 게 순서다.
- 커밋 이력이 무의미해진다: `/undo` 나 사람이 `git log` 로 "언제 무엇이 바뀌었나"를 보려면
  95% 노이즈를 걷어내야 한다.
- 파일 append 가 O(n²): jsonl 은 매번 전체 파일을 읽고 통째로 다시 PUT 한다(Contents API 는
  부분 쓰기가 없음). 하루 520줄이면 마지막 커밋은 100KB 를 다시 보낸다. 규모가 작아 당장 문제는
  아니지만 구조적으로 잘못된 자리다.
- GitHub API 호출: 백엔드 실행 1회당 ~8회(control·preview×2·archive·admin_state·write 확인·
  monitor read/write) × 500회/일 ≈ 4,000회/일. 시간당 5,000 한도 안이지만 여유가 크진 않다.

### 제안 (단기 → 장기)

1. **(단기, 코드 30줄)** 실행 1회 = 커밋 최대 1개. `_run` 안에서 이벤트를 리스트에 모았다가
   마지막에 **한 번만** append. `preview` 전이 N개 + tick/wake 1개 = 커밋 1개.
2. **(단기)** 상태 변화 없는 tick/wake 는 기록하지 않거나(`preview_changed=False and
   enqueue_errors==[]` 면 skip), 시간당 1줄로 roll-up. `/monitor` 타임라인의 🎯 트리거 점이
   듬성해지는 대신 커밋이 1/10 로 준다. 어느 쪽을 택할지는 사용자 결정 — "모든 tick 을 점으로
   보고 싶다"면 1번만이라도.
3. **(장기, 추천)** 모니터링 로그를 GitHub 에서 **Cloud Logging 으로 이관**. Cloud Run 은
   stdout JSON 한 줄을 구조화 로그로 자동 수집하고(무료 50GB/월, 30일 보존), `/monitor` 는
   Logging API(`gcloud logging read` 와 같은 API)로 그날 이벤트를 읽어 같은 HTML 을 만들면
   된다. 커밋 0개, 409 충돌 0개, 백엔드 실행당 GitHub 호출 2회 감소. 30일 넘는 보존이 필요하면
   Logging 싱크 → GCS(무료 5GB)로 빼면 된다. 이번 세션에서 본 `gcloud logging read` 조회가
   정확히 그 API 다.

---

## 3. [P1] write-queue(`/write`) 설계 재검토

오늘 커밋(b07d7b5)이 넣은 구조: telegram 의 콘텐츠 쓰기 14종을 `writeclient.call_write` →
OIDC → 백엔드 `POST /write` → `writers.dispatch` → (지연 import 한) `telegram_app` 의 원래 함수
실행. 백엔드가 `concurrency=1 · max-instances=1` 이라 자동 직렬화된다는 아이디어다. 발상은
맞지만 지금 구현은 세 가지가 어긋난다.

### 3-1. 직렬화 보장이 불완전하다

커밋 메시지가 정확히 지적했듯 Contents API 의 409 는 **파일이 아니라 브랜치 HEAD 단위**다.
그런데 아래는 여전히 telegram 서비스에서 **직접** `gh.write_*` 한다:

- `monitor_log.log_event` (notice/tweet/relay/ops 이벤트마다) — §2 의 커밋 폭주와 정면충돌
- `_save_undo` / `admin_state.json` 의 모든 마법사 단계(`_op_set`, `pending_*`)
- `control.json` (`/pause` `/resume` `/log` `/monitor --auto`)
- `_maybe_nonyt_url_notice` → `_apply_notice` 직접 호출 (write-queue 안 탐)
- `_translate` 명령, `_handle_log`

즉 "브랜치 HEAD 경쟁"은 그대로 남아 있고, 그 증거가 24h 동안 telegram 11건의 충돌 재시도다.
지금 상태는 "일부 경로만 큐를 타고 나머지는 옛 2회 재시도" 라서, **어떤 경로가 안전한지
코드를 안 보면 알 수 없는** 중간 상태다.

### 3-2. 느린 외부 호출이 직렬 구간 안에 있다

`/write` job 인 `personal_tweet` · `apply_notice` · `url_confirmed_schedule` 은 GitHub 읽기·
쓰기뿐 아니라 **vxtwitter 조회 → videos.list → 외부 LLM(번역·참여판정·예고확인·중복판정)** 을
전부 백엔드 위에서 실행한다. 백엔드는 한 번에 요청 1개만 처리하므로, 이 job 이 도는 동안
`/tick` `/wake` 는 Cloud Run 대기열에서 기다린다(대기 상한 초과 시 429 — 정확한 상한은
**확인 필요**, Scheduler/Tasks 재시도가 있어 유실은 안 되지만 정밀 wake 의 타이밍은 밀린다).

최악값을 계산하면: `llm._call_groq` 는 429/5xx 에 1+2+4초 백오프 3회 + 각 20초 타임아웃
≈ 67초, 메인→폴백 2모델 ≈ 134초, `participation`/`announces_own_broadcast` 는 이걸 **5회
반복** ≈ 670초. `writeclient._TIMEOUT_SEC` 는 60초, Cloud Run 요청 타임아웃은 300초, 백엔드
gunicorn `--timeout 120` 이다. Groq 가 장애를 겪는 날엔 (a) 클라이언트는 60초에 포기 → "ingest
오류" DM, (b) 백엔드 worker 는 120초에 gunicorn 이 kill → 그 사이 큐에 있던 tick/wake 까지
같이 죽는다(단일 worker). 실측은 아직 양호하다(`/write` 4건 median 0.5초, Groq median 0.43초
p90 2.7초) — 그러니까 "평소엔 괜찮고, 외부 장애 때 가장 중요한 tick 이 같이 죽는" 구조다.

### 3-3. 코드 구조

`writers._registry()` 가 백엔드 프로세스 안에서 `telegram_app` (4,307줄, Flask 앱 객체·
`logging.basicConfig` 포함)을 지연 import 한다. 동작은 하지만 "백엔드가 제어 채널 모듈을
통째로 실행 컨텍스트에 싣는" 구조라, 앞으로 telegram_app 쪽에서 모듈 수준 부작용(환경변수
검사·전역 초기화)을 하나만 추가해도 백엔드가 영향을 받는다. 커밋 메시지의 "4000줄 파일에서
기능을 뜯어 옮기는 리스크" 판단은 이해하지만, 그 리스크를 미루는 대가로 §1 의 버그가 왔다.

### 제안 — 둘 중 하나로 결정

**A안 (큐 유지, 정공법)** — "판단은 telegram, 커밋만 backend":

1. LLM·videos.list·vxtwitter 는 telegram 서비스(concurrency 80)에서 **먼저** 끝내고, 결과(번역문·
   판정·확정 아이템)를 job 인자로 넘긴다. `/write` job 은 순수 read-modify-write 만 하도록 —
   0.5초짜리 job 만 직렬 구간에 남는다.
2. `data` 저장소를 쓰는 **모든** 경로를 `/write` 로 보낸다(monitor/admin/control/undo 포함).
   §2-1 배치와 합치면 큐 통과 건수 자체가 준다.
3. 순수 커밋 함수들을 `content_ops.py`(가칭)로 뽑아 `writers.py` 가 그것만 import 하게 한다.
   telegram_app 은 "명령 파싱 + DM + content_ops 호출" 로 얇아진다.

**B안 (큐 폐기, 실용)** — §2 로 커밋 밀도를 1/10 로 줄이면 409 자체가 드물어진다. 그 위에
기존 2회 재시도를 5회 + 지터(0.3~1.5초)로 올리고, `/write` 홉을 없앤다. 단순하고 cold start
한 번(백엔드가 유휴일 때 write 마다 깨어남 — 24h 에 백엔드 cold start 15회)도 줄어든다.
대신 "절대 안 겹친다"는 보장은 없다 — 하루 15건 트윗 규모에서 5회 재시도가 다 실패할 확률은
사실상 0에 가깝다는 걸 받아들이는 안이다.

두 안 모두 §1 수정은 선행 조건이다. 내 추천은 **B → 필요해지면 A**: 지금 write-queue 는
문제(커밋 밀도)를 옆으로 옮겨 놓은 것이지 줄인 게 아니다.

부수: `writeclient._send_wait_notice`(2초 넘으면 "⏳ 처리 대기 중" DM)는 24h 로그에 0회 —
아직 안 울렸지만, A안으로 LLM 을 telegram 에 남기면 이 타이머는 job 이 아니라 LLM 을 기다리는
셈이 되므로 기준을 다시 정해야 한다.

---

## 4. [P1] 외부 LLM 폴백 모델이 두 갈래로 갈린다 (한쪽은 404)

| 위치 | 폴백 기본값 |
|---|---|
| `config.py` `Config.groq_model_fallback` / `llm.FALLBACK_MODEL` | `openai/gpt-oss-20b` (정상) |
| `telegram_app._make_llm_client()` | **`llama-3.3-70b-versatile`** — `llm.py` 주석 자체가 "이 계정에서 404" 라고 적어둔 모델 |
| `docs/SPEC.md` §8.4 | `llama-3.3-70b-versatile` (stale) |

`_make_llm_client` 는 인라인 번역·소식 제목추출·(v3.7) 중복판정·`/translate` 가 쓴다. Groq
사용 로그(`ref/groq-logs-…csv`, 09-16 하루)에 `llama-3.3-70b-versatile` 404 가 정확히 2건 찍혀
있고, 각각 직전에 `gpt-oss-120b` **400** 이 있다(09:59, 14:00 KST). 즉 "메인 400 → 폴백 404 →
실패 → `needs_tl`" 이 하루 2번 일어났다. 다음 tick 의 `_translate_sweep`(이쪽은 config 기본값이라
20b 로 성공)이 주워 담으니 결과는 "번역 지연" 이지만, 폴백이 죽어 있다는 사실 자체가 문제다.

- 수정: `_make_llm_client` 가 `config.load_config()` 의 값을 쓰게 하고(환경변수 직접 읽기
  제거), `deploy_telegram.sh`/`deploy.sh` 에서 `GROQ_MODEL_FALLBACK` 을 주입하든 기본값을 한
  곳으로 모으든 **한 군데**만 남긴다. SPEC §8.4 갱신.
- 400 의 원인은 **확인 필요**: `response_format: json_schema` 호출에서 모델 출력이 스키마 검증에
  실패하면 Groq 가 400(`json_validate_failed`)을 준다. `_call_groq` 는 429/5xx 만 재시도하고 400
  은 즉시 None 이라 폴백으로 넘어가는데, 폴백이 404 니 결국 실패. 400 도 1회 재시도 대상에
  넣을지 검토.
- 같은 맥락: `telegram_app.py` 전반이 `os.environ.get(...)` 을 40여 곳에서 직접 읽는다.
  `config.load_config()` 가 이미 있으니 통일하면 이런 이중 기본값이 구조적으로 안 생긴다.

---

## 5. [P2] wake 빈도 · Cloud Run 무료 티어 · 10분 tick 과의 중복

### 측정값

- 백엔드 요청(최근 24h, 로그 샘플 400건): `/wake` 309건 median **4.4초** p90 5.0초 max 11.2초 ·
  `/tick` 86건 median **6.0초** p90 7.2초 · `/write` 4건 median 0.5초.
- 하루 wake 418건(09-16). 라이브 cadence: 시작 60분까지 10분, 이후 **3분**(`LIVE_TIGHT_SEC=180`),
  end 창 5분, watching 3분.
- 백엔드 cold start(`Booting worker`) 24h 15회, telegram 23회.
- 추정 CPU(1 vCPU 기본값 가정 — 서비스 CPU 설정은 **확인 필요**): 418×4.4 + 144×6.0 ≈
  **2,700 CPU초/일 ≈ 81,000/월** → Cloud Run 무료 180,000 vCPU초/월의 **약 45%** (telegram
  서비스 몫 별도). "무료 인프라만" 이라는 전제 안에서 가장 큰 소비처다.

### 왜 3분 cadence 가 헛돈이 되나

프론트엔드는 `raw.githubusercontent.com` 을 75초마다 `cache:"no-store"` 로 부르지만, 실측 응답
헤더가 `Cache-Control: max-age=300` + `X-Cache: HIT`(Fastly) 다. 브라우저 캐시만 우회할 뿐 CDN
캐시는 못 뚫는다. 즉 **팬이 보는 신선도 상한은 5분**이고, 백엔드가 3분마다 종료를 확인해도
화면엔 5분 단위로만 반영된다(CLAUDE.md 에 "최대 ~5분 지연, 의도된 트레이드오프" 로 이미
적혀 있는 사실이 wake 설계엔 반영이 안 됐다).

### 제안

1. `LIVE_TIGHT_SEC` 180 → 300 (또는 600). 라이브 후기 wake 가 40% 줄고 체감은 동일.
2. light tick 이 10분이 된 지금, **live 상태의 wake 자체를 없애고 tick 에 맡기는** 선택지도
   있다(pre-live precheck `ss-3분` wake 만 유지 → 정시 시작 감지는 지금과 같고 종료 감지가
   최대 10분). wake 가 1/3 이하로 준다. 어느 쪽이든 사용자 결정.
3. 10분 tick 과 중복된 장치 정리: `_POST_END_RECHECK_SEC`(종료 후 20분 후속 tick)와
   `_scheduled_wake_times`(예고 시각에 tick 예약)는 3h tick 시절의 보정이다. 무해하지만 "왜
   있는지" 를 다음 사람이 또 추적해야 한다. `STALE_REMOVE_SEC=6.5h` 주석("light tick 3h
   간격 2회") 도 stale — 값을 1h 로 줄일지 결정.
4. tick 6초 중 RSS 6채널 **순차** fetch(`rss.fetch_all_rss_video_ids`)가 2~3초로 추정된다.
   `ThreadPoolExecutor(6)` 로 병렬화하면 tick 이 ~4초. 하루 144회 × 2초 = 288 CPU초 절약.
5. `oidc.verify_request` 가 호출마다 `ga_requests.Request()` 를 새로 만들어 Google 인증서를
   재다운로드한다(캐시 없음). 모듈 수준 세션 하나로 바꾸면 요청당 수백 ms 절약.
6. `gh_store.GitHubStore` 는 `session=None` 이면 **호출마다** `requests.Session()` 을 새로
   만든다(TLS 핸드셰이크 반복). 생성자에서 세션 하나를 기본으로 두면 실행당 8회 호출이
   같은 커넥션을 탄다.

---

## 6. [P2] `xtweet.apply_overrides` 가 어디서도 호출되지 않는다 (문서와 불일치)

- `grep apply_overrides src/` → 정의와 self-test 뿐. `handlers.py` 는 `xtweet.find_reused_ko` 만 쓴다.
- 그런데 `docs/SPEC.md` §6-3 ("`handlers.tick` 이 `build_preview` 직후 호출") 과 `CLAUDE.md`
  v2.8.1 단락("`handlers.tick()` 이 `reconcile` 직후 `xtweet.apply_overrides` 로 …") 은 호출된다고
  서술한다. CLAUDE.md 작업 원칙("이해용 문서에 실제 코드 동작과 다른 내용을 쓰면 안 된다")
  기준으로 **바로잡아야 할 불일치**다.
- 기능 영향: `preview_build.py:184` 는 `info_source ∈ (personal, x-relay)` 면 `scheduled_start`
  를 API 값으로 **절대 안 덮고** `api_start_seen` 만 기록한다. `apply_overrides` 가 하려던
  일("API 값이 `api_start_seen` 과 달라지면 = 스트림을 실제로 수정한 것 → API 승")은 지금
  아무도 안 한다. 멤버가 트윗으로 21:00 예고 → YouTube 예약을 22:00 으로 바꾸면, preview 는
  `expires_at`(21:00+3h) 까지 21:00 을 고집하다가 watching 지각 강등 → 카드가 "지각" 으로
  보인다. 실제로 이런 사례가 있었는지는 **확인 필요**(preview_archive 에서 `api_start_seen` ≠
  `scheduled_start` 인 행을 찾으면 된다).
- 제안: (a) 문서대로 `handlers._run` 에서 `build_preview` 직후 `apply_overrides(new, prev, now)`
  를 연결하고 self-test 에 시나리오 추가, 또는 (b) `preview_build` 섹션 1 에 그 판정을 직접
  넣고 `apply_overrides` 와 문서 서술을 삭제. 둘 중 하나로 **코드와 문서를 일치**시킨다.

---

## 7. [P2] 배포 재현성 — 새 프로젝트에서 `deploy.sh` 가 실패한다

- `deploy/deploy.sh` `--set-secrets` 에 `HEALTHCHECKS_IO_READONLEY_TOKEN=…:latest` 가 **무조건**
  들어가는데, `deploy/setup.sh` 의 `create_secret` 목록에 이 Secret 이 없다(`YOUTUBE_API_KEY
  GITHUB_TOKEN TELEGRAM_BOT_TOKEN TELEGRAM_WEBHOOK_SECRET INGEST_SECRET GROQ_API_KEY` 뿐).
  `deploy_telegram.sh` 도 마찬가지. 지금 프로젝트는 수동으로 만들어져 있어 돌아가지만,
  `docs/plan/v3_golive.md` 류 런북대로 새 프로젝트를 세우면 첫 배포에서 막힌다. `GROQ_API_KEY`
  처럼 "있을 때만 붙이는" 패턴을 쓰거나 `setup.sh` 에 추가.
- Secret/env 이름 오타 `READONLEY` — 이름을 바꾸려면 Secret 재생성 + 두 서비스 재배포라
  급하진 않지만, 문서(`config.py` 주석, SPEC §8.12)에 "오타지만 의도된 이름" 이라고 적어두지
  않으면 다음 사람이 "고쳐야 하나" 를 또 고민한다.
- `deploy/env.example.sh` 에 `INGEST_SECRET` `GROQ_API_KEY` `HEALTHCHECKS_IO_READONLEY_TOKEN`
  `INGEST_*` 플래그가 없다 — stale.
- `deploy.sh` 는 placeholder URL 로 1차 배포 → URL 조회 → env 갱신 2차 배포(리비전 2개).
  Cloud Run 의 결정적 URL(`https://<service>-<projectnumber>.<region>.run.app`) 을 미리 계산해
  넣으면 1회 배포로 끝난다 — 이 프로젝트에서 그 URL 형식이 활성화돼 있는지는 **확인 필요**
  (`gcloud run services describe … --format='value(status.url)'` 결과가 그 형식이면 가능).
- `src/backend/requirements.txt` 는 전부 `>=` 하한만 — 재배포 때마다 다른 버전이 깔릴 수
  있다. 소규모라 실해가 적지만, 오늘처럼 급히 롤백해야 할 때 "코드는 같은데 라이브러리가
  달라서" 라는 변수를 없애려면 `==` 고정(또는 `pip-compile`)이 낫다.
- healthchecks.io 체크는 README 기준 period 3h / grace 40m — tick 이 10분이 된 지금은
  period 10~15분 / grace 20분으로 조이면 다운 감지가 3시간 → 30분으로 빨라진다.

---

## 8. [P2] 문서 불일치 — "유일한 진실 소스" 가 여러 곳에서 코드와 다르다

CLAUDE.md 원칙상 이건 기능 버그와 같은 무게다. 확인된 것만 나열한다.

| 문서 | 서술 | 실제 |
|---|---|---|
| `README.md` 전체 | "현재 v2.7.1", "GitHub Actions 가 매시간 cron", `schedule.json` | v3.6+, Cloud Run, `preview.json`, 데이터 저장소 분리 — **문서 전체가 두 세대 전** |
| `docs/SPEC.md` §0 표·§12 | light **3h**, `mewtype-light "0 */3 * * *"` | `deploy/scheduler.sh` `*/10 * * * *` (실배포도 10분 확인) |
| `docs/SPEC.md` §8.4 | `FALLBACK_MODEL = "llama-3.3-70b-versatile"` | `openai/gpt-oss-20b`(그리고 §4 의 이중 기본값) |
| `docs/SPEC.md` §6-3, `CLAUDE.md` v2.8.1 단락 | `apply_overrides` 를 tick 이 호출 | 호출 안 함 (§6) |
| `docs/SPEC.md` §8, `CLAUDE.md` 저장소 구조 | `writers.py` `writeclient.py` `POST /write` `duplicate_notice` `monitor.html` 없음 | 전부 HEAD 에 존재·배포됨 |
| `docs/SPEC.md` §0 | "`ingest_queue.json` (ECHO/DRY-RUN 버퍼)" 만 | `monitoring/events-*.jsonl` `monitoring/latest.html` 도 `data` 저장소에 있음 |
| `CLAUDE.md` 명령 | `config.js` 의 `DATA_URL` 을 `../../fixtures/schedule.sample.json` 으로 | 상수명은 `PREVIEW_URL`, 픽스처는 `preview.sample.json` |
| `CLAUDE.md` 인프라 단락 | `collect.yml` = "비상 수동 경로" | 코드 저장소의 `data` 브랜치에 v1 `schedule.json` 을 쓰는데, 프론트엔드는 `mewtype-scheduler-data` 의 `preview.json` 을 읽는다 → **실행해도 아무 효과 없음** |
| `docs/VERSION.md` | 최신 v3.6 | write-queue · 소식 LLM 중복판정(v3.7) · 모니터 페이지 항목 없음. v3.7 흐름도 커밋(`9a6bb44`)은 `devpapers` 에만 있고 `main` 의 INGEST_FLOW.md 는 미갱신 |
| HEAD 커밋 메시지 | 제목 `fix(monitor): 자동 리포트가 …` | 본문에 write-queue · notice dedup · 프론트 이스터에그 3개 기능이 함께 들어 있음 — `git log --oneline` 만 보면 오늘 아무 기능 변경도 없었던 것처럼 보인다 |

제안: (1) README 는 CLAUDE.md 상단 요약으로 교체하거나 "개발 문서는 CLAUDE.md/SPEC.md 참고"
한 줄로 축소, (2) SPEC §0/§8/§12 갱신 + `/write` 계약(J?) 추가, (3) VERSION.md 에 오늘 변경분
3건 추가, (4) 기능 3개짜리 커밋은 앞으로 분리 — 최소한 제목이 내용을 가리키게.

---

## 9. [P3] 공개 노출 — `monitoring/latest.html`

- `mewtype-scheduler-data` 는 **public** 저장소다(raw CDN 익명 접근이 전제). `app.py /monitor`
  와 `/monitor` 명령이 커밋하는 `monitoring/latest.html` 은 `https://raw.githubusercontent.com/
  sbb2002/mewtype-scheduler-data/data/monitoring/latest.html` 로 누구나 열 수 있다.
  `monitor.html` 의 `noindex` 와 이스터에그 진입은 **이 URL 을 모르는 사람**에게만 유효하다 —
  저장소 URL 은 `config.js` 에 그대로 적혀 있으니 5초면 찾는다.
- 내용에 비밀값은 없다(확인: REPORT JSON 은 이벤트·상태·건수·에러 메시지 문자열). 다만
  `detail` 에 `str(e)[:150]` 같은 내부 예외 문구가 들어간다. 팬 커뮤니티 노출 수준으로
  괜찮다고 판단하면 그대로 두되, "비공개" 라는 전제는 문서에서 지우는 게 맞다. 진짜 비공개가
  필요하면: 텔레그램 DM 만 유지(커밋 삭제) 또는 Vercel 서버리스 함수가 private 저장소를
  토큰으로 읽어 프록시(무료 티어 안).
- `latest.html` 은 base64 아이콘 5개를 매번 포함해 하루 1회 이상 커밋된다 — 아이콘은 동일해서
  git 델타로 흡수되지만, `monitoring/` 이 `data` 저장소 크기(현재 920KB)를 키우는 주요 원천이
  될 것이다. §2-3 로 로그를 옮기면 이 파일도 같이 GCS 로 보내는 게 자연스럽다.
- 사소: `/ingest` 의 시크릿 비교 `got != secret` 은 상수시간 비교가 아니다(`hmac.compare_digest`).
  실질 위협은 낮다.

---

## 10. [P3] 코드·저장소 정리

- **죽은 경로 삭제**: `.github/workflows/collect.yml`, `src/collector/main.py` `reconcile.py`
  `store.py`, `fixtures/schedule.sample.json`. v3 가 쓰는 건 `rss.py` `youtube.py` `config.py`
  뿐(SPEC §8.0 도 그렇게 적음). 남겨두면 §8 표처럼 "비상 경로" 라는 잘못된 안심을 준다.
- **린터 도입**: `ruff check --select F821,F823,E9` 한 줄을 self-test 앞에. 오늘 P0 를 배포 전에
  잡았을 도구다(§1 에서 실증). `deploy.sh` 첫 줄에 넣으면 사람이 잊어도 막힌다.
- **`/ingest` 라우트 테스트**: 개인 5인 title · 공식 title · 테스트 부계정 · 빈 text 4케이스를
  `test_client` 로 치는 self-test. §12 스크립트가 출발점.
- `telegram_app.py` 4,307줄: 최소한 (a) `/ingest` 파이프라인, (b) 명령 핸들러·마법사, (c) 순수
  커밋 함수(§3 의 `content_ops`) 세 파일로. 지금은 Flask 라우트·비즈니스 로직·GitHub I/O·DM 이
  한 파일이라 §1 같은 배선 실수가 눈에 안 띈다.
- `handlers._run` 이 `preview.json` 을 두 번 읽는다(`_pv0` 와 커밋 루프 1회차). 첫 읽기의
  sha 를 1회차에 그대로 쓰면 GitHub 호출 1회/실행 절약(하루 500회).
- 잡파일: 루트의 `gcloud`(0바이트), `.secrets`(gcloud describe 출력 — gitignore 돼 있어 안전),
  `ref/*.png|jpg|csv` 9개가 untracked 상태로 남아 있다. `ref/` 를 gitignore 하든 devpapers 로
  보내든 정하기.
- `assets/member_icons/` 와 `src/frontend/assets/member_icons/` 중복 — 한쪽은 `monitor_report.py`
  base64 원본, 한쪽은 이스터에그 풍선용. 용도가 다르면 README 한 줄, 같으면 하나로.
- 명명: `KST`/`JST` 가 모듈마다 섞여 있다(둘 다 +9). 하나로 통일하면 `_kst_to_md`·`_jst_hm`
  같은 중복 헬퍼도 준다.
- `xrelay.ALL_KEYS`·`telegram_app._UNIT_KEYS`·`monitor_report.MEMBER_ORDER` 가 `config/
  channels.json` `channel_order` 를 하드코딩으로 복제한다 — "채널 추가는 이 파일 한 곳만"
  이라는 CLAUDE.md 약속이 깨져 있다(순수 모듈이라 파일을 못 읽는다면 호출부에서 주입).
- `/translate` 명령은 웹훅 안에서 미번역 행을 **순차** 번역한다. gunicorn `--timeout=60` 이라
  행이 30개를 넘으면(Groq p90 2.7초) worker 가 죽어 DM 없이 끝난다 — `_done()` 안전망도
  못 잡는다(프로세스가 죽으니). 배치 상한(예: 20건) + "나머지는 다음 tick" 안내.

---

## 11. [P3] 프론트엔드

- **폴링 vs CDN**: `POLL_MS=75000` 이지만 원본이 `max-age=300` 이라 5분 창 안의 4번은 같은
  응답을 받는다. `ETag` 가 제공되므로(실측 `ETag: "51e7…"`) `If-None-Match` 를 붙이면 304 로
  본문 전송을 아낀다 — 무료 자원이라 비용은 0 이지만 모바일 데이터엔 의미 있다. 또는
  `POLL_MS` 를 150초로 올려도 체감 차이는 없다.
- **"업데이트" 표시**: v3.2.2 이후 `generated_at` 은 실제 변화가 있을 때만 움직인다. 지금 라이브
  값이 `2026-09-16T16:00:01Z`(01:00 KST) — 14시간째 그대로인데 백엔드는 그 사이 50번 돌았다.
  팬 입장에선 "사이트가 죽었나" 로 읽힌다. 커밋 없이 해결하려면 푸터를 두 값으로: "데이터
  기준 01:00" + "확인 14:02"(클라이언트가 마지막으로 성공적으로 fetch 한 시각). 백엔드 손 안
  대고 `main.js` 5줄.
- `render.js` 는 `innerHTML` 금지 규칙을 지키고, `tweets.js` 의 `innerHTML` 4곳은 상수
  마크업(SVG·뼈대)만이고 사용자 텍스트는 `textContent` 로 넣는 걸 확인했다. `notices.js` 는
  `_esc/_attr` 이스케이프. XSS 면에서 문제 없음.
- CSS+JS 합계 128KB(비압축) — 정적 호스팅이라 Vercel 이 gzip 한다. 문제 없음.

---

## 12. 측정값 부록 · 재현 커맨드

### 배포 상태 (2026-09-17 14:00 KST 기준)

| 항목 | 값 |
|---|---|
| `main` HEAD | `b07d7b5` 2026-09-17 11:27:02 KST |
| `mewtype-telegram` 활성 리비전 | `00069-58j` 2026-09-17 11:29:39 KST · concurrency 80 · timeout 300s · maxScale 20 |
| `mewtype-backend` 활성 리비전 | `00090-clp` 2026-09-17 11:28:38 KST · concurrency 1 · timeout 300s · maxScale 1 |
| Cloud Scheduler | `mewtype-light */10 * * * *` UTC · `mewtype-baseline 0 6 * * *` JST · `mewtype-monitor 10 6 * * *` KST |
| Cloud Tasks `mewtype-wake` | maxConcurrentDispatches 1 · maxAttempts 100 · backoff 0.1s~3600s |
| `data` 저장소 | public · 920KB · `preview.json generated_at 2026-09-16T16:00:01Z` |
| raw CDN 헤더 | `Cache-Control: max-age=300` · `ETag` 있음 · `X-Cache: HIT` |

### 하루 활동량 (events-2026-09-16.jsonl · 커밋 이력 · Cloud Logging)

| 지표 | 값 |
|---|---|
| 백엔드 실행 | wake 418 · tick 44 (오늘은 8h 에 50 → 10분 cadence) |
| `data` 커밋 | 463 (monitor 439 · preview 8 · tweet 7 · archive 3 …) |
| 요청 지연(24h 샘플 400) | wake med 4.4s p90 5.0s · tick med 6.0s p90 7.2s · write med 0.5s |
| cold start | backend 15 · telegram 23 |
| 충돌 재시도 로그 | telegram 11 · backend 2 |
| `/ingest` 5xx (48h) | 3 (09-17 12:01 · 13:11 ·13:11 KST) |
| Groq 호출(09-16) | 42회: 120b 38 · 20b 2 · llama 2(404) · 400 2건 · med 0.43s p90 2.7s max 4.4s · 토큰 in 16k / out 7k |

### self-test 결과

22개 백엔드 모듈 + collector 3개 + `telegram_app` + `handlers` + `monitor_report` + node
selfcheck 2개 **전부 통과**. (그런데도 §1 이 프로덕션에서 죽어 있다 — 라우트 미커버.)

### P0 재현 스크립트 (저장소 루트에서)

```bash
PYTHONIOENCODING=utf-8 python - <<'EOF'
import os, sys
os.environ.update({"INGEST_SECRET":"s","GITHUB_TOKEN":"t","GITHUB_REPO":"o/r"})
os.environ.pop("MAIN_SERVICE_URL", None); sys.path.insert(0, ".")
import src.backend.telegram_app as t
t._recover_raw_via_vxtwitter = lambda raw, tag: (raw, None)
class FakeGH:
    def __init__(self,*a,**k): self.store={}
    def read_json(self,p): return (self.store.get(p), None)
    def write_json(self,p,d,*,prev_sha=None,message=""): self.store[p]=d; return (True,"s")
    def read_text(self,p): return (None,None)
    def write_text(self,p,x,*,prev_sha=None,message=""): return (True,"s")
t.GitHubStore = FakeGH; t._make_gh = lambda: FakeGH(); t._send_telegram = lambda *a, **k: True
r = t.app.test_client().post("/ingest", data={"text":"ねむい","title":"仲町あられ","tag":""},
                             headers={"X-Ingest-Secret":"s"})
print(r.status_code)   # 기대 200, 현재 500
EOF
```

### 정적 검사 · 로그 조회

```bash
ruff check --select F821,F823 src/backend/telegram_app.py      # → 3489, 3551 F821
gcloud logging read 'resource.labels.service_name="mewtype-telegram" AND textPayload:"UnboundLocalError"' --freshness=48h --limit 3
gcloud logging read 'resource.labels.service_name="mewtype-telegram" AND httpRequest.requestUrl:"/ingest" AND httpRequest.status>=500' --freshness=48h
curl -s "https://api.github.com/repos/sbb2002/mewtype-scheduler-data/commits?sha=data&per_page=100" | jq -r '.[].commit.message' | cut -d' ' -f1-2 | sort | uniq -c
```

### 이 문서가 확인하지 못한 것 (확인 필요 목록)

- 업스트림 시스템(Automate)이 `/ingest` 500 에 재전송하는가 — 유실 3건의 복구 여부.
- Cloud Run 이 concurrency=1 인스턴스가 바쁠 때 요청을 얼마나 오래 대기시키다 429 로 돌리는가.
- Groq 400 2건의 정확한 사유(`json_validate_failed` 추정).
- 백엔드 서비스의 CPU/메모리 설정값(무료 티어 추정은 1 vCPU · 512MiB 기본값 가정).
- `api_start_seen ≠ scheduled_start` 인 실사례가 archive 에 있는가(§6 의 실피해 여부).
- Cloud Run 결정적 URL 형식이 이 프로젝트에 활성화돼 있는가(§7 1회 배포 제안).
