# v3 개선 구현 명세 (v3_improvisation)

> **상태: WP-1~8 구현·검증 완료 → v3.7.1** (2026-09-17). 명세와 다르게 구현된 점:
> `_maybe_nonyt_url_notice` 도 `_maybe_auto_notice` 와 같이 `apply_notice` 전에 `notice_sweep` 잡을 한 번
> 부른다(만료 소식 정리, 기능 영향 없음). 나머지는 본문대로.

> 작성 2026-09-17. 원본 제안서 `ref/v3_improvisation.md`(같은 날, `main` HEAD `b07d7b5` 기준)의
> 11개 항목을 **현재 코드와 다시 대조**하고, 사용자 결정을 받아 구현 단위(WP)로 옮긴 문서.
> 완료되면 다른 `docs/plan/*` 런북과 같은 규칙으로 `devpapers` 브랜치로 이전한다.
> 용어는 `docs/TERMINOLOGY.md` 기준(프론트엔드 / 백엔드 / 제어 채널 / 업스트림 시스템 / 외부 LLM).
> "write-queue" 는 `b07d7b5` 커밋·`writers.py`/`writeclient.py` docstring 이 이미 쓰는 이름을 그대로
> 따른다(TERMINOLOGY.md 에는 아직 없음 — 추가 여부 **확인 필요**).

---

## 0. 결정 기록 (2026-09-17, 사용자 확정)

| 원본 § | 주제 | 결정 |
|---|---|---|
| §3 | write-queue(`/write`) | **A-1** — 큐 유지. 외부 호출(외부 LLM·`videos.list`·vxtwitter·비전 OCR)은 제어 채널에서 먼저 끝내고 `/write` 에는 커밋만 보낸다. A-2(모든 쓰기를 큐로)·A-3(`content_ops.py` 분리)은 이번 범위 밖 |
| §2 | 모니터링 이벤트 로그 | **GitHub 유지 + 배치/스킵** — 백엔드 실행 1회 = 커밋 최대 1개, 변화 없는 tick/wake 는 기록 안 함. `/monitor` 리포트의 quota·호출 수 문구를 "기록된 실행 기준"으로 조정 |
| §5 | 라이브 wake 간격 | **후기 3분 → 5분** (`LIVE_TIGHT_SEC` 180 → 300) |
| §6 | `xtweet.apply_overrides` | **`handlers._run` 에 연결** (v3 계약에 맞게 고친 뒤 — §WP-6) |

### 0-1. B안(큐 폐기)을 기각한 근거

원본 §3 은 "사고의 근본 원인은 백엔드 모니터 커밋 밀도일 가능성이 높다"고 보고 B안을 추천했다.
실제 기록으로 확인한 결과는 달랐다.

- `data` 커밋 이력(2026-09-16 11:00~11:13 UTC): 백엔드 마지막 커밋은 `11:00:12 monitor tick`,
  이후 11:12:50 까지 백엔드 커밋 **없음**.
- 11:12:50 UTC 에 `/ingest` 요청 여러 건이 같은 초에 도착(이벤트 로그: relay 2 · notice 1 · nonoka tweet 1).
  11:12:52~59 사이 `monitor relay` → `notice added` → `undo snapshot` → `monitor notice` → `monitor tweet`
  → `monitor relay` 6커밋.
- 제어 채널 로그 11:12:55.8: `_maybe_personal_tweet` 의 `tweets.json` PUT →
  `ConflictError: PUT 409 Conflict ... "is at 3fde310… but expected 64b6e38…"` → tweet 이벤트 `err`.

즉 충돌 상대는 **제어 채널 안에서 동시에 처리되던 다른 요청들의 커밋**이었다. 모니터 커밋을
줄여도 요청마다 콘텐츠 + undo 커밋은 남으므로, 재시도만 늘리는 B안은 이 사고를 막는다고 보장할 수 없다.

### 0-2. 원본 제안서 대비 정정

| 원본 서술 | 확인 결과 |
|---|---|
| §3-2 외부 LLM 최악 지연 "~67초/모델, ~670초" | `_call_groq` 는 20초 타임아웃 × 3회 시도 + 사이 대기 1초·2초(마지막 뒤엔 대기 없음) = **모델당 약 63초**, 메인→폴백 약 126초, 5회 반복 판정(`participation`·`announces_own_broadcast`·`duplicate_notice`) 약 630초. 결론은 동일 |
| §6 "문서대로 연결하면 된다" | 그대로 연결하면 **오작동**. `apply_overrides` 는 v2 reconcile 형태(`new` 아이템의 `scheduled_start`=API 값)를 가정하는데, v3 `preview_build` 는 personal/x-relay 아이템의 `scheduled_start` 를 트윗 값으로 두고 API 값은 `api_start_seen` 에만 적는다. 또 `info_source` 비교 대상이 v2 이름(`bdp_schedule`·`appearance`)이라 v3 값 `x-relay` 를 못 잡는다 → WP-6 에서 v3 계약으로 수정 후 연결 |
| §3 A안 "LLM·videos.list·vxtwitter 는 telegram 에서" | Cloud Tasks wake 즉시 등록(`_enqueue_wake_now`)은 **백엔드에 남겨야 한다**. `deploy/deploy_telegram.sh` 는 `GCP_PROJECT`·`TASKS_QUEUE`·`SERVICE_URL`·`INVOKER_SA` 를 주입하지 않는다(백엔드는 주입) |
| §2 "배치만이라도" | 백엔드 실행 1회당 이벤트는 대부분 tick/wake 1줄이라 **배치만으로는 커밋이 거의 안 줄어든다**. 감소분은 거의 전부 "변화 없는 실행 스킵"에서 나온다 |

---

## 1. 이번 구현 범위 한눈에

| WP | 원본 § | 내용 | 주 파일 | 실행 트랙 |
|---|---|---|---|---|
| WP-1 | §1 P0 | `/ingest` 의 `gh` UnboundLocalError 수정 + `/ingest` 라우트 self-test | `telegram_app.py` | A (1순위) |
| WP-2 | §4 | 외부 LLM 폴백 기본값 404 모델 제거(한 곳으로) | `telegram_app.py`, `llm.py` | A (WP-1 과 함께) |
| WP-3a | §3 A-1 | 소식 경로: 준비(외부 호출)·커밋 분리 | `telegram_app.py`, `writers.py` | A (WP-1/2 뒤) |
| WP-3b | §3 A-1 | 개인 트윗·개인 예고 경로: 준비·커밋 분리 | `telegram_app.py`, `writers.py` | A (WP-3a 뒤) |
| WP-4 | §2 | 백엔드 모니터 로그 배치 + 변화 없는 실행 스킵 + 리포트 문구 | `monitor_log.py`, `handlers.py`, `monitor_report.py` | B (1순위) |
| WP-5 | §5-1 | `LIVE_TIGHT_SEC` 180 → 300 | `statemachine.py` | 독립 |
| WP-6 | §6, §5-3 | `apply_overrides` v3 계약 수정 + `handlers._run` 연결 + 3h 시절 주석 정정 | `xtweet.py`, `handlers.py`, `preview_build.py` | B (WP-4 뒤) |
| WP-7 | §7 | 배포 재현성: healthchecks Secret 조건부 마운트·생성, `env.example.sh` 갱신 | `deploy/*.sh` | 독립 |
| WP-8 | §8 | 문서 동기화(SPEC·CLAUDE.md·VERSION·INGEST_FLOW) — 구현·검증 후 | `docs/`, `CLAUDE.md` | 마지막 |

트랙 A·B 안에서는 같은 파일을 건드리므로 **순차**, 트랙끼리·독립 WP 는 병렬 가능.

### 1-1. 이번 범위 밖 (후속 — 사용자 결정 필요)

| 원본 § | 항목 | 비고 |
|---|---|---|
| §2-3 | 모니터 로그 Cloud Logging 이관 | 이번엔 GitHub 유지로 결정 |
| §3 | A-2 모든 `data` 쓰기를 큐로 / A-3 `content_ops.py` 분리 | A-1 뒤 잔여 위험(§WP-3 "남는 한계") 보고 판단 |
| §5-2~6 | live wake 폐지, 3h 시절 보정 장치 제거, RSS 병렬 fetch, OIDC 인증서 세션 캐시, `GitHubStore` 기본 세션 | 이번엔 주석 정정만(WP-6) |
| §7 | `requirements.txt` 버전 고정, Cloud Run 결정적 URL 로 1회 배포, healthchecks.io period 조정, `READONLEY` 오타 이름 변경 | |
| §8 | `README.md` 전면 교체 | v2.7.1 시대 서술 — 교체 방식 결정 필요 |
| §9 | `monitoring/latest.html` 공개 노출 | 공개 허용 / DM 만 / 프록시 중 결정 필요. `/ingest` 시크릿 `hmac.compare_digest` |
| §10 | v1 collector 죽은 경로 삭제, ruff 도입, `telegram_app.py` 분할, 멤버 키 하드코딩 3곳, `/translate` 배치 상한, `handlers._run` preview 중복 읽기, 잡파일 정리 | `collect.yml` 은 실행해도 코드 저장소 `data` 브랜치에 v1 `schedule.json` 을 push 할 뿐 프론트엔드(데이터 저장소 `preview.json`)에 영향 없음 — 확인됨 |
| §11 | 프론트엔드 ETag 조건부 요청 / 푸터 "확인 시각" 표시 | |

---

## WP-1. `/ingest` 개인 트윗 500 수정 (P0)

### 현상 (재현 확인)
`telegram_app._ingest` 안에서 지역변수 `gh` 가 대입(`gh = None`, `gh = _make_gh()`)보다 **앞**에서
사용된다 — 개인 5인 분기의 `writeclient.call_write("personal_tweet", gh=gh, ...)` 와 ECHO 블록의
`call_write("ingest_queue_push", gh=gh, ...)`. 파이썬은 함수 안에서 대입되는 이름을 통째로 지역변수로
보므로 `UnboundLocalError` → 500. 로컬 재현(원본 §12 스크립트): `STATUS 500`, 트레이스
`telegram_app.py line 3489 ... UnboundLocalError: cannot access local variable 'gh'`.

### 수정
1. `_ingest` 에서 `now_iso = ...` 직후, `route_by_title` 분기 **전**에 `gh = _make_gh()` 를 한 번 둔다.
2. 아래쪽의 `gh = None`(try 직전)과 `gh = _make_gh()`(DRY-RUN 블록 뒤) 대입은 삭제하고,
   `if gh is None: _send_telegram("⚠️ ingest: GitHub 설정 누락") ...` 검사는 그 자리에 그대로 둔다.
   `except` 블록의 `if gh is not None:` 는 유지.
3. WP-3b 적용 후에는 개인 5인 분기가 `call_write` 가 아니라 `_maybe_personal_tweet(...)` 직접 호출이 되지만,
   `gh` 선정의는 ECHO 블록에서도 필요하므로 그대로 유효.

### self-test 추가 (`python -m src.backend.telegram_app`)
`app.test_client()` 로 `/ingest` 를 실제로 친다. `MAIN_SERVICE_URL` 제거(로컬 디스패치),
`GitHubStore`/`_make_gh` 는 메모리 가짜, `_send_telegram` 무력화, `_recover_raw_via_vxtwitter` 는
`(raw, None)` 반환으로 스텁. 외부 LLM 은 `GROQ_API_KEY` 제거로 비활성. 4케이스:

| 케이스 | 입력 | 기대 |
|---|---|---|
| 개인 5인 | `title=仲町あられ`, `text=ねむい` | 200, 응답 JSON `personal == "arale"` |
| 테스트 부계정 | `title=jehy`, `text=hello` | 200, `echo == True` |
| 공식·스케줄 아님 | `title=""`, `text=ただの雑談` | 200 |
| 빈 text | `text=""` | 400 |
| 시크릿 틀림 | 헤더 `X-Ingest-Secret: wrong` | 403 |

(`app.testing` 은 기본값 그대로 — 예외가 500 으로 변환되는지를 봐야 한다.)

---

## WP-2. 외부 LLM 폴백 기본값 통일

### 현상
- `llm.py`: `DEFAULT_MODEL = "openai/gpt-oss-120b"`, `FALLBACK_MODEL = "openai/gpt-oss-20b"`
  (주석: `llama-3.3-70b-versatile` 은 이 계정에서 404). 백엔드 `config.py` 기본값도 20b.
- `telegram_app._make_llm_client()` 는 환경변수가 없으면 폴백을 **`llama-3.3-70b-versatile`** 로 만든다.
  `deploy.sh`·`deploy_telegram.sh` 는 `GROQ_MODEL_FALLBACK` 을 주입하지 않으므로 운영에서 이 값이 쓰인다.
  이 함수는 인라인 번역(`_inline_translate`)·소식 제목추출(`_inline_notice_title`)·소식 중복판정·
  `/translate` 가 쓴다. write-queue 이후엔 `/write` 잡 안(백엔드 프로세스)에서도 같은 함수가 불린다.
- `llm.LLMClient.__init__` docstring 에 "fallback 기본 llama-3.3-70b-versatile" 이라고 남아 있음(실제 기본값은 20b).

### 수정
1. `_make_llm_client()` 의 하드코딩 기본값을 `llm.DEFAULT_MODEL` / `llm.FALLBACK_MODEL` 로 교체
   (환경변수 `GROQ_MODEL`/`GROQ_MODEL_FALLBACK` 이 있으면 그 값 우선 — 동작 유지).
2. `llm.py` docstring 의 폴백 기본값 표기를 `openai/gpt-oss-20b` 로 정정.
3. (정정만, 동작 변경 없음) 400 응답 재시도 여부는 원본 §4 에서 "확인 필요"로 남김 — 이번 범위 밖.

### self-test
`GROQ_API_KEY=dummy` 로 `_make_llm_client()` 를 만들고 `.fallback == llm.FALLBACK_MODEL`,
`.model == llm.DEFAULT_MODEL` 확인(환경변수 `GROQ_MODEL*` 제거 상태).

---

## WP-3. write-queue A-1 — "외부 호출은 제어 채널, 커밋만 `/write`"

### 목표 상태
- `/write` 잡(`writers.dispatch` 로 실행되는 함수)은 **GitHub 읽기·쓰기 + (필요 시) Cloud Tasks enqueue·
  텔레그램 DM 만** 한다. 외부 LLM·`videos.list`·vxtwitter·비전 OCR 호출은 **0회**.
- 외부 호출은 제어 채널(동시 처리 80)에서 요청마다 병렬로 끝내고, 결과를 JSON 인자로 잡에 넘긴다.
  GitHub **읽기**는 충돌을 만들지 않으므로 준비 단계에서 스냅샷을 읽어 판단에 써도 된다.
- 잡 인자는 HTTP JSON 으로 전송되므로 **`json.dumps` 가능해야 한다**(self-test 로 확인).
- 어떤 잡 함수도 내부에서 `writeclient.call_write` 를 다시 부르지 않는다.

### 현재 잡 중 외부 호출이 있는 것 (코드 확인)

| `/write` kind | 실행 함수 | 잡 안의 외부 호출 |
|---|---|---|
| `apply_notice` | `_apply_notice` | 비전 OCR(`_maybe_tag_cast_participants`: vxtwitter + Groq 비전), 제목추출 LLM, 중복판정 LLM(5회 반복) |
| `personal_tweet` | `_maybe_personal_tweet` → `_maybe_personal_schedule` | vxtwitter(미디어·인용), 번역 LLM(본문·인용), `_expand_truncated_yt`(vxtwitter), `_maybe_url_confirmed_schedule`(`videos.list`, 참여판정 LLM 5회), `_maybe_nonyt_url_notice`→`_apply_notice`(위 3종), `announces_own_broadcast` LLM 5회 |
| `url_confirmed_schedule` | `_maybe_url_confirmed_schedule` | `videos.list`, 참여판정 LLM (※ 현재 이 kind 를 `call_write` 로 부르는 곳은 없음 — 위 `personal_tweet` 잡 안에서 직접 호출됨) |

나머지 kind(`merge_rows` `remove_broadcast` `notice_sweep` `notice_del_commit` `notice_edit_commit`
`tweet_sweep` `tweet_del_commit` `undo_restore` `apply_preview_edit` `ingest_queue_push`
`ingest_queue_drain`)는 GitHub I/O + 텔레그램 DM 만 — 변경 없음.

### WP-3a. 소식 경로

**새 함수 `_prepare_notice(raw, now_iso, *, tag=None, title=None, gh=None) -> dict | None`** (제어 채널에서 실행)
1. `parsed = xnotice.parse(raw, now_iso, tag=tag, title=title)` — `None` 이면 `None` 반환.
2. `_maybe_tag_cast_participants(parsed, tag)` (비전 OCR, 제자리 수정).
3. `tl = _inline_notice_title(...)` — 기존 `_apply_notice` 와 같은 조건(`not parsed.get("title_ko")`)·같은 입력.
4. 중복판정 사전 계산: `gh` 가 있으면 `notices.json`·`notice_archive.json` 을 **읽기만** 하고,
   `copy.deepcopy` 한 사본으로 `notices.merge_notice(prev, parsed, now_iso, archive=arch)` 를 돌려
   `changed and mode == "added"` 일 때만 `dup_id = _inline_notice_dup_check(parsed, prev)`.
   그 외 `dup_id = None`. (`merge_notice` 가 인자를 변형하는지와 무관하게 사본으로 호출.)
5. 반환 `{"parsed": parsed, "tl": tl, "dup_id": dup_id}`.

**`_apply_notice` → `_commit_notice(gh, prepared, now_iso) -> tuple[str, dict | None]`** (잡, 백엔드에서 실행)
- `prepared is None` → `("none", None)`.
- 기존 `_apply_notice` 의 read→merge→write 루프(2회 충돌 재시도)·`_save_undo` 를 그대로 두되,
  `_maybe_tag_cast_participants`/`_inline_notice_title`/`_inline_notice_dup_check` 호출을 제거하고
  `prepared["tl"]`, `prepared["dup_id"]` 를 쓴다. `mode == "added"` 이고 `dup_id` 가 있으면
  `notices.merge_into(prev, dup_id, parsed, now_iso)` — `found` 가 False(그 사이 그 소식이 사라짐)면 added 유지.
- 반환값·DM 없음·undo 스냅샷은 기존과 동일.

**호출부**
- `_maybe_auto_notice`: `gh = _make_gh()` 뒤 `prepared = _prepare_notice(raw, now_iso, tag=tag, title=title, gh=gh)`;
  `None` 이면 `"none"` 반환. `call_write("apply_notice", gh=gh, prepared=prepared, now_iso=now_iso)`.
  기존 앞단의 `xnotice.parse(...) is None` 조기 반환은 유지해도 된다(파싱 2회는 순수 함수라 무해).
- `_handle_notice_followup`(`/notice` 원문 수신): 같은 방식.
- `_maybe_nonyt_url_notice`: `_apply_notice(gh, ...)` 직접 호출 → `_prepare_notice` + `call_write("apply_notice", ...)`.
  (WP-3b 이후 이 함수는 제어 채널에서 실행된다.)
- `writers._registry()["apply_notice"]`: `t._commit_notice(gh, a.get("prepared"), a["now_iso"])` 결과를
  `{"mode", "parsed"}` 로.

**경쟁 조건 메모**: 중복 후보는 준비 시점 스냅샷 기준이다. 준비~커밋 사이에 같은 날짜 소식이 새로
커밋되면 그건 비교 대상에 없어 새 소식으로 등록된다 — LLM 실패 시와 같은 "안전한 기본값(중복이
잠깐 남음)"이며 `/notice-del` 로 정리 가능.

### WP-3b. 개인 트윗 · 개인 예고 경로

**새 함수 `_prepare_personal_tweet(raw, *, title, tag, channel_key, now_iso, vx_extract=None, gh=None) -> dict | None`** (제어 채널)
1. `handle` 계산, `media, quote = _enrich_personal_media(tag, prefetched=vx_extract)`,
   `parsed = xtweet.parse(...)` — 기존 `_maybe_personal_tweet` 앞부분과 동일. `None` 이면 `None`.
2. `gh` 로 `tweets.json`·`tweet_archive.json` 을 읽고, 사본으로 `xtweet.merge_thread(...)` 를 돌려
   `changed` 가 False 면 번역을 건너뛴다(`text_ko=None`, `quote_ko=None`).
3. `changed` 면:
   - `text_src = parsed.get("text") or ""`, `text_ko = _inline_translate(text_src)` (parsed 에 이미 `text_ko` 가 있으면 생략).
   - 인용: `quote_src = (parsed.get("quote") or {}).get("text")` 가 있으면
     `xtweet.find_reused_ko(quote_src, tweets_data=스냅샷, archive_data=스냅샷)` →
     없으면 `notices.json` 읽어 `find_reused_ko(quote_src, notices_data=...)` → 없으면 `_inline_translate(quote_src)`.
4. 반환 `{"parsed": parsed, "text_src": text_src, "text_ko": text_ko, "quote_src": quote_src, "quote_ko": quote_ko}`.

**새 잡 함수 `_commit_personal_tweet(gh, prepared, *, channel_key, now_iso, via="ingest") -> dict`** (백엔드)
- 기존 `_maybe_personal_tweet` 의 read→`merge_thread`→write 루프(2회 충돌 재시도)·`_tweet_sweep`·
  `log_event("tweet", ...)`(성공/`needs_tl`/예외) 를 옮긴다. LLM 호출은 없다:
  - 본문: `row` 에 `text_ko` 가 없고 `prepared["text_ko"]` 가 있으며 `row["text"] == prepared["text_src"]` 이면
    채우고 `needs_tl` 제거, 아니면 `needs_tl = True`.
  - 인용: 커밋 시점 `new_t`/`new_a` 로 `find_reused_ko` (순수 함수, 네트워크 없음) → 없으면
    `quote_ko`(원문이 `quote_src` 와 같을 때만) → 없으면 `needs_tl = True`. `notices.json` 재조회는 하지 않는다.
- 반환 `{"mode": mode, "n_thread": <해당 채널 스레드 길이>, "needs_tl": bool}`. 예외 시 기존처럼
  `log_event(... RESULT_ERR ...)` 후 `{"mode": "error", ...}`.

**`_maybe_personal_tweet(raw, *, title, tag, channel_key, now_iso, vx_extract=None, via="ingest") -> str`** — 제어 채널 오케스트레이터로 재구성
1. `gh = _make_gh()` (`None` 이면 `"no-gh"`), `prepared = _prepare_personal_tweet(...)` — `None` 이면 `"none"`.
2. `res = writeclient.call_write("personal_tweet", gh=gh, prepared=prepared, channel_key=channel_key, now_iso=now_iso, via=via)`.
   `WriteError`/예외 → `log.exception` + `_log_event_safe(gh, now_iso, "tweet", RESULT_ERR, who=channel_key, detail="mode: error (/write 호출 실패)", via=via)` → `"error"`.
3. `mode in ("added", "rolled")` 면 기존 문구 그대로 `_auto_dm(gh, "tweet", ...)` (스레드 수는 `res["n_thread"]`).
4. `_maybe_personal_schedule(...)` 호출(기존과 동일 인자). 반환 `mode`.

**호출부**
- `_ingest` 개인 5인 분기: `call_write("personal_tweet", ...)` → `mode = _maybe_personal_tweet(raw, title=title, tag=x_tag, channel_key=_route, now_iso=now_iso, vx_extract=_vx_ex)`.
- `/edit tweet` 마법사(`step == "await_raw" and contents == "tweet"`): 같은 방식(`title="", tag=None, via="ops"`).

**`_maybe_personal_schedule`** — 제어 채널에서 실행되는 것으로 바뀌며, 커밋 지점만 잡으로:
- `_maybe_url_confirmed_schedule` 을 둘로 나눈다.
  - 제어 채널 부분(같은 함수 이름 유지): URL 추출 → `videos.list` → `resolve_url_host` → (외부 채널이면) 참여판정 LLM →
    `new_item, next_check_at = xtweet.build_item_from_video(...)` 까지. 기존 degraded 로그(`_log_event_safe`)·반환값 규칙 유지.
    이어서 `res = call_write("url_confirmed_commit", gh=gh, video_id=..., new_item=new_item, next_check_at=next_check_at, host_key=host_key, now_iso=now_iso, via=via)`.
    `res["changed"]` 면 기존 DM(`📅 ... URL 확정 예고 반영`) 발송. `WriteError` 면 기존 "url-schedule write 실패" err 로그와 같은 문구로 `_log_event_safe` 후 `True` 반환.
  - **새 잡 `_url_confirmed_commit(gh, video_id, new_item, next_check_at, host_key, now_iso, via) -> dict`** (백엔드):
    기존 preview.json read→`merge_video_confirmed`→write 루프(2회 재시도) + `changed` 면 `_save_undo` +
    `next_check_at` 있으면 `_enqueue_wake_now(video_id, next_check_at)`. 쓰기 실패 시 기존 err 로그 후
    `{"changed": False, "error": True}`. 반환 `{"changed": bool, "error": bool}`.
    **`_enqueue_wake_now` 는 반드시 이 잡 안(백엔드)에 둔다** — 제어 채널 서비스엔 Cloud Tasks 환경변수가 없다.
- `_maybe_nonyt_url_notice`: WP-3a 대로.
- 텍스트 예고 경로 끝의 `_merge_rows_into_schedule(...)` 직접 호출 →
  `call_write("merge_rows", gh=gh, rows=[row], now_iso=now_iso, message=..., action=..., merge_fn="personal_schedule").get("changed")`.
- `writers._registry()`: `personal_tweet` → `_commit_personal_tweet`, `url_confirmed_schedule` 삭제 →
  `url_confirmed_commit` 추가. `writers` self-test 의 기대 kind 집합 갱신.

### WP-3 self-test
- `python -m src.backend.writers`: kind 집합 갱신 확인.
- `python -m src.backend.telegram_app` 에 추가:
  1. `_prepare_notice`/`_prepare_personal_tweet` 결과가 `json.dumps` 가능.
  2. **잡 함수는 외부 호출을 안 한다**: `_make_llm_client`·`_make_vision_client`·`vxtwitter.fetch_tweet`·`YouTubeClient`
     를 "호출되면 AssertionError" 스텁으로 바꾼 뒤 `_commit_notice`·`_commit_personal_tweet`·`_url_confirmed_commit`
     를 메모리 GH 로 실행해 통과.
  3. `_commit_notice` 에 `dup_id` 를 주면 `updated` 로 병합, 없는 id 면 `added`.
  4. `_commit_personal_tweet` 에 `text_ko` 를 주면 `text_ko` 채움, `None` 이면 `needs_tl`.
  5. WP-1 의 `/ingest` 개인 5인 케이스가 여전히 200.
- 기존 self-test 전부 통과(수정으로 깨진 기존 기대값은 **의미가 같을 때만** 새 구조에 맞게 고친다).

### 남는 한계 (A-1 범위에서 의도적으로 남김)
- 제어 채널이 **직접** 커밋하는 경로는 그대로다: `log_event`(notice/relay/ops 및 준비 단계의 degraded 기록),
  `admin_state.json` 마법사 단계(`_op_set` 등), `control.json`(`/pause` `/resume` `/log` `/monitor --auto`),
  `/translate`, `/monitor` 의 `latest.html`. 이것들과 큐 잡의 커밋이 부딪히면 잡은 최신 상태 재조회 후
  1회 재시도(기존 2회 루프)하고, 그래도 실패하면 그 콘텐츠는 반영되지 않는다. 없애려면 A-2.
- 준비~커밋 사이 경쟁(WP-3a 경쟁 조건 메모)은 안전한 기본값으로 수렴.

---

## WP-4. 백엔드 모니터 로그 — 배치 + 변화 없는 실행 스킵

### 현상 (코드·이력 확인)
- `handlers._run` 끝에서 tick/wake 이벤트 1건을 **무조건** `log_event`, 이어서 preview 전이마다 `log_event` —
  `monitor_log.log_event` 는 호출마다 `read_text` + `write_text` = 커밋 1개.
- 데이터 저장소 최근 100커밋 중 96건이 `data: monitor`(2026-09-17 조회).

### 수정
1. `monitor_log.py` 에 `log_events(gh, now_iso, events: list[dict]) -> None` 추가.
   - 각 원소는 `{"flow", "result", "who"?, "detail"?, ...추가필드}`. `result` 검증은 기존과 동일(`ValueError`).
   - 빈 리스트면 GitHub 을 건드리지 않고 반환.
   - 한 번 읽고 모든 줄을 이어 붙여 **한 번** `write_text`. 충돌 시 기존과 같은 2회 재시도.
   - 줄 형식은 기존 `log_event` 와 동일(`ts=now_iso`, `sort_keys=True`, `ensure_ascii=False`).
   - 커밋 메시지 `data: monitor {첫 이벤트 flow}(+{n-1}) {now_iso}` (n==1 이면 기존 형식 `data: monitor {flow} {now_iso}`).
   - `log_event` 는 `log_events(gh, now_iso, [한 건])` 로 위임(외부 동작 동일).
2. `handlers._run` 의 모니터 로그 블록:
   - `events = []`. preview 전이 이벤트(`_preview_log_events`)를 기존과 같은 필드로 `events` 에 담는다.
   - tick/wake 이벤트는 **다음 중 하나라도 참일 때만** 담는다:
     `pv_changed` · `arch_changed` · `enqueue_errors` 가 비어 있지 않음 · preview 전이 이벤트가 1건 이상 ·
     `sum(tl.values()) > 0`(번역 sweep 이 실제로 반영함).
   - `log_events(gh, now_iso, events)` 한 번. 예외는 기존처럼 경고 로그만.
   - 일시정지(`paused`) 조기 반환 경로는 원래 기록하지 않음 — 변경 없음.
3. `monitor_report.py` 문구(HTML 템플릿) — 수치 계산 로직은 그대로, 표기만:
   - quota 패널 설명 `정기수집·라이브감지 트리거(🕒/📡)가 소모한 quota 누적.` →
     `정기수집·라이브감지 트리거(🕒/📡) 중 변화가 있어 기록된 실행의 quota 누적 — 변화 없는 실행은 기록하지 않으므로 실제 사용량은 GCP 콘솔 기준.`
   - 요약 타일 `YouTube quota 사용(누적)` → `YouTube quota(기록된 실행)`.
   - `extYtCalls` 로 표시되는 호출 수 라벨이 있으면 같은 취지로 "기록된 실행" 표기.

### self-test
- `python -m src.backend.monitor_log`: `log_events` 3건 → PUT 1회, 3줄 누적 / 빈 리스트 → PUT 0회 /
  잘못된 result 포함 시 `ValueError` / 기존 검증 전부 통과.
- `python -m src.backend.handlers`: 이벤트 포함 조건을 순수 헬퍼(예: `_should_log_run(...) -> bool`)로 뽑아
  무변화 → False, `pv_changed` → True, `enqueue_errors` → True, 번역 1건 → True 확인.
- `python -m src.backend.monitor_report` 통과.

### 기대 효과 / 부작용
- 커밋: 변화 없는 tick/wake(하루 수백 건, 대부분)가 사라진다. 정확한 감소율은 배포 후 커밋 수로 측정 — 원본 추정 "약 1/10".
- `/monitor`: 🎯 트리거 점·백엔드 busy 구간·quota·호출 수가 "기록된 실행"만 반영(사용자 승인).

---

## WP-5. 라이브 후기 wake 간격 3분 → 5분

- `statemachine.py`: `LIVE_TIGHT_SEC = 5 * 60` — 주석 `# 300초 — live 후기 체크 간격 (5분, +60분 이상). 프론트엔드가 읽는 raw CDN 캐시가 max-age=300 이라 3분은 화면에 반영되지 않음 (v3 개선 WP-5)`.
- `PRELIVE_TIGHT_SEC`(watching 3분)·`END_TICK_SEC`(5분)·`LIVE_EARLY_SEC`(10분)는 **변경하지 않는다**.
- self-test(`python -m src.backend.statemachine`): live 후기 시나리오의 기대 간격이 180 으로 고정돼 있으면 300 으로.
  범위 검사(`180 <= delta <= ...`)는 그대로 통과하면 두고, 새로 `delta == LIVE_TIGHT_SEC` 확인을 추가.

---

## WP-6. `apply_overrides` v3 계약 수정 + `handlers._run` 연결

### v3 입력 형태 (코드 확인)
`preview_build.build_preview` 는 기존 아이템을 API 로 갱신할 때 `api_start_seen = video.scheduled_start`
를 **매번** 기록하고, `info_source ∈ ("personal", "x-relay")` 면 `scheduled_start` 를 덮지 않는다.
따라서 `build_preview` 직후의 새 아이템 `b` 에서 "이번 tick 의 API 시각" = `b["api_start_seen"]`,
직전 tick 의 API 시각 = 이전 아이템 `pb["api_start_seen"]`.

### 의도 (SPEC §2 계약 A′ 주석 · xtweet 주석)
"`api_start_seen` 은 마지막 API scheduled_start. **이 값이 바뀌면(스트림 실수정)** 트윗값 대신 API 승" /
"더 나중 트윗 또는 API 값 자체의 변화 전까지 트윗 시각 유지".

### `xtweet.apply_overrides(new_items, prev_items, now_iso)` 재작성 규칙
각 `b` 에 대해 `pb = preview.match_item(prev_items, b)`:
1. `pb` 없음 → 그대로.
2. `b.get("info_source") not in ("personal", "x-relay")` → 그대로.
3. `b.get("time_tbd")` 또는 `not b.get("scheduled_start")` → 그대로.
4. `api_now = b.get("api_start_seen")`, `api_prev = pb.get("api_start_seen")`.
   둘 중 하나라도 없으면 → 그대로(처음 API 가 관측된 tick 은 "변화"가 아니라 기준값 확보).
5. `abs(epoch(api_now) − epoch(api_prev)) <= 60` → 그대로(트윗 시각 유지).
6. 60초 초과(스트림 예약 실제 수정) → `b["scheduled_start"] = api_now`, `b["info_source"] = "api"`,
   `b["info_at"] = now_iso` (`api_start_seen` 은 `api_now` 유지).
- 입력 리스트를 변형하지 않고 사본 반환(기존과 동일). docstring 을 위 규칙으로 교체.
- 이후 tick 에서 `info_source == "api"` 이므로 `preview_build` 가 API 값으로 계속 갱신한다(추가 처리 불필요).

### `handlers._run` 연결
커밋 루프 안, `build_preview(...)` 호출 **직후**(suppress/edit_lock 반영 전):
`new_preview["items"] = xtweet.apply_overrides(new_preview.get("items", []), prev_preview.get("items", []), now_iso)`.
예외 시 경고 로그 후 원래 items 유지(주 로직 무영향).

**알려진 지연**: `build_preview` 가 반환한 `wakes`(Cloud Tasks 예약 시각)는 override 적용 전 시각 기준이다.
API 승으로 시각이 바뀐 경우 다음 light tick(최대 10분)에서 재계산된다.

### 3h 시절 주석 정정 (동작 변경 없음)
- `handlers.py` `_POST_END_RECHECK_SEC` 위 주석 "정기 light tick(3h)" · `_SCHED_WAKE_LOOKAHEAD_SEC` 위 주석
  "3h 안 기다리고" → light tick 이 v3.6 부터 10분임을 반영하고 "3h 시절 도입한 보정 — 현재는 10분 tick 과
  겹치지만 무해해 유지(제거 여부는 후속 결정)" 로.
- `preview_build.py` `STALE_REMOVE_SEC` 주변에 3h tick 전제 서술이 있으면 같은 취지로 정정(값 6.5h 유지).

### self-test
- `python -m src.backend.xtweet`: 기존 S-G/S-H 를 v3 형태로 교체 —
  (G) prev `api_start_seen=13:00`, new `scheduled_start=13:30(트윗)`·`api_start_seen=13:00`·`info_source=personal` → 13:30 유지.
  (H) new `api_start_seen=14:00` → `scheduled_start=14:00`, `info_source=api`.
  (I) prev `api_start_seen=None` → 트윗값 유지. (J) `info_source=x-relay` 도 (H)와 같이 동작.
  (K) `info_source=api` 아이템은 손대지 않음.
- `python -m src.backend.handlers` 통과.

---

## WP-7. 배포 재현성

- `deploy/deploy.sh`·`deploy/deploy_telegram.sh`: `HEALTHCHECKS_IO_READONLEY_TOKEN` Secret 마운트를
  `GROQ_API_KEY` 와 같은 **"Secret 이 있을 때만 붙이는"** 패턴으로 변경(`gcloud secrets describe` 성공 시에만
  `--set-secrets` 문자열에 추가). 이름은 오타 그대로 유지하고 주석에 "오타지만 운영 Secret 이름 — 바꾸려면 Secret 재생성 + 두 서비스 재배포" 명시.
- `deploy/setup.sh`: `create_secret HEALTHCHECKS_IO_READONLEY_TOKEN "healthchecks.io read-only API 키 (/monitor 백엔드 상태 조회용, 없으면 빈 값 Enter)" "${HEALTHCHECKS_IO_READONLEY_TOKEN:-}"` 추가 (`GROQ_API_KEY` 줄 뒤).
- `deploy/env.example.sh`: 주석 Secret 목록에 `INGEST_SECRET`·`GROQ_API_KEY`·`HEALTHCHECKS_IO_READONLEY_TOKEN` 추가,
  `INGEST_DRY_RUN`/`INGEST_ECHO`/`INGEST_YT_ENABLED` 예시(기본 0) 추가, `GITHUB_REPO` 예시를 데이터 저장소
  `sbb2002/mewtype-scheduler-data` 로(2026-09-14 저장소 분리 반영 — `docs/plan/data_repo_migration.md`).
- 검증: `bash -n` 으로 세 스크립트 구문 검사. `config.py`·`monitor_report` 가 이 값이 비어 있을 때 죽지 않는지
  코드로 확인(`os.environ.get(..., "")` 기본값).

---

## WP-8. 문서 동기화 (구현·검증 후)

| 문서 | 고칠 내용 |
|---|---|
| `docs/SPEC.md` | §0 표·§12 light tick 3h → 10분(`*/10 * * * *`), §8.4 폴백 모델 20b, §6-3 `apply_overrides` 새 규칙, FSM 상수 `LIVE_TIGHT_SEC=300`·cadence 표, `/write` 라우트·`writers.py`·`writeclient.py`(A-1 구조), `monitoring/` 파일, 모니터 로그 기록 조건 |
| `CLAUDE.md` | 저장소 구조에 `writers.py`·`writeclient.py`·`monitor.html`, 데이터 흐름 wake cadence(+60분 이후 5분), v2.8.1 단락의 `apply_overrides` 서술, 프론트 로컬 실행 안내(`PREVIEW_URL`·`preview.sample.json`), `collect.yml` "비상 경로" 서술 정정 |
| `docs/VERSION.md` | `b07d7b5`(write-queue·소식 LLM 중복판정·모니터 페이지)와 이번 개선분 기록 — **버전 번호 확인 필요** |
| `docs/INGEST_FLOW.md` | 개인 트윗·소식 경로에 "준비(제어 채널) → `/write` 커밋(백엔드)" 구분 반영 |

---

## 부록 A. 검증 체크리스트 (오케스트레이터가 완료 시 수행)

1. `git diff --stat` 이 각 WP 선언 파일 밖을 건드리지 않았는지.
2. 전 모듈 self-test: CLAUDE.md "명령" 절의 `python -m src.backend.*` 전부 + `writers`·`writeclient`·`handlers`.
3. WP-1 재현 스크립트 → 200.
4. WP-3 잡 함수 외부 호출 0회(스텁 검사) · 잡 인자 JSON 직렬화.
5. `grep` 확인: `llama-3.3-70b-versatile` 이 코드 기본값에서 사라짐 / `writeclient.call_write` 가 잡 함수 안에 없음 /
   `_enqueue_wake_now` 호출이 백엔드 잡 안에만 있음 / `apply_overrides` 호출이 `handlers._run` 에 있음.
6. `bash -n deploy/*.sh`.
7. 배포는 사용자 확인 후(`deploy.sh` + `deploy_telegram.sh` 둘 다 — `writers.py` 가 두 서비스 공통 이미지).
