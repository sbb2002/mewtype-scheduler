# v3 코드 구현 명세

`v3_draft.md`(결정 로그) · `v3_backend_surgery.md`(기능 상세) · `v3_telegram_controller.md`(제어 채널)
를 코드 작업 단위로 분해한 문서.

> **완료·배포됨 (v3.0, 2026-09-09)**. WP-0~19 전부 구현, `main` 머지·배포. 골라이브 후속
> 수정(LLM response_format·폴백모델, 트윗 이모지 VS16, 원문 링크 X, 읽음 유지)은 그 이후
> `main` 직커밋. 아래 WP 서술은 착수 당시 계획 기준(이력).

- 대상 브랜치: `main` (구현 당시 `v3`)
- 테스트 프레임워크 없음 — 각 모듈 `if __name__ == "__main__":` assert 스모크(현행 관례 유지).
- 코드 주석·커밋 메시지 한국어. 직렬화·시간 규칙은 v2 그대로 (`SPEC.md` §7).

---

## 0. 계약 동결 (구현 전 확정 필요한 값)

아래 값은 **이 문서에서 못 박는다.** 모든 WP 는 이 이름·시그니처를 전제로 병렬 작업한다.
구현 중 바꿔야 하면 이 절을 먼저 고치고 영향 WP 에 통지.

### 0.1 `preview.json` (계약 A' — `schedule.json` 대체)

`v3_backend_surgery.md` "v3 데이터 스키마" 의 JSON 그대로 채택. 확정 사항:

- 파일명 `preview.json` / 아카이브 `preview_archive.json`.
- `state` ∈ `announced | upcoming | watching | live | end` (none = 파일에서 삭제).
- `id` = `"pv_" + <8 hex>` — `first_seen` 시각 + `channel_key` 해시. 생애주기 내내 고정.
- 정렬: `state` 우선순위(`live` > `watching` > `upcoming` > `announced`) → `scheduled_start` asc(null 뒤) → `id`.
- **`source` 값 집합 확정**: `x-relay | personal | yt-notif | api | manual`.
- **`expires_at` 확정**: 공개 `scheduled_start + 3h` / `membership` `+5h` / `time_tbd` 그날 JST 자정.
- 번역 필드는 preview 에 **없음** (제목 번역은 notice/tweet 만 — `v3_draft.md` 미결항목 결정).
- `pending.json`(계약 E) **폐지** — 파일·모듈 삭제. FSM 은 저장 타이머 없이 파생(§1.1).
- `control.json`(계약 F) 유지. `archive.json`(계약 B) → `preview_archive.json` 으로 이름만
  바꿔 승계(스키마 동일 + `state` 표기). **미결: 아예 생략 가능** → 0.6 참조.

### 0.2 FSM 파생 규칙 (`statemachine.py` v3 — 순수)

입력 `(item, now_iso)` → 출력 `(next_state, next_check_at_iso | None, log: list[str])`.
`next_check_at` 은 **저장 안 함** — Cloud Tasks enqueue 시각 계산에만 씀.

| 규칙 | 조건 | 결과 |
|---|---|---|
| pre-live 진입 | `state in (announced,upcoming)` && `scheduled_start` 존재 && `now ≥ ss − 3분` | `watching`, check `ss − 3분`부터 3분 간격 |
| watching 체크 | `state==watching` && `now − ss < 120분` | check `now + 3분` |
| watching 지각 강등 | `state==watching` && `now − ss ≥ 120분` | `announced` (url·video_id 살림), check 없음 |
| assumed-live 폴백 | `assumed_live` && `video_id` 없음 && `now − ss ≥ 90분` | `none`(삭제 신호), check 없음 |
| live cadence (초기) | `state==live` && `now − actual_start < 60분` | check `now + 10분` |
| live cadence (후기) | `state==live` && `now − actual_start ≥ 60분` | check `now + 3분` |
| end 창 | `state==end` && `now − state_since < 30분` | check `now + 5분` |
| end → none | `state==end` && `now − state_since ≥ 30분` && 마지막 확인도 live 아님 | `none` |
| end → upcoming | `state==end` 마지막 확인에서 예고 스트림으로 재등장 | `upcoming` |
| membership 특례 | `membership==true` | `watching` 스킵 — 시작 알림(`yt-notif`) 오면 `announced/upcoming` → `live` 직행. API 확인 안 함 |

- 상수: `PRELIVE_LEAD_SEC=180`, `PRELIVE_TIGHT_SEC=180`, `WATCH_LATE_DEMOTE_SEC=7200`,
  `ASSUMED_LIVE_MAX_SEC=5400`, `LIVE_EARLY_SEC=600`, `LIVE_EARLY_WINDOW_SEC=3600`,
  `LIVE_TIGHT_SEC=180`, `END_WINDOW_SEC=1800`, `END_TICK_SEC=300`, `MAX_TASK_HORIZON_SEC=696*3600`.
- `announced → upcoming` 승격은 FSM 이 아니라 **정보 충족**(날짜+시간+제목+썸네일+url+video_id)
  으로 `preview_build` 가 판정. FSM 은 승격을 되돌리지 않음(지각 강등만).

### 0.3 `src/backend/llm.py` (외부 LLM — Groq)

```python
DEFAULT_MODEL = "openai/gpt-oss-120b"
FALLBACK_MODEL = "llama-3.3-70b-versatile"

class LLMClient:
    def __init__(self, api_key, *, model=DEFAULT_MODEL, fallback=FALLBACK_MODEL,
                 session=None, timeout=20.0)     # api_key 비면 disabled → 모든 호출 None 반환 + warning

    def notice_title(self, body_no_date_url: str, *, lang_hint="ja") -> dict | None
        # {"title_ja": str, "title_ko": str}  — JSON 1회 호출(response_format json_schema/json_object)
        #   reasoning_effort="low" 고정. 실패(429 백오프 소진·파싱실패·환각가드) → None

    def translate(self, text_ja: str) -> str | None
        # 개인 트윗 본문 JP→KO. 실패 → None
```

- 429/5xx → 지수 백오프 3회 → 폴백 모델 1회 → `None`.
- **환각 가드(기본선)**: 출력이 비었거나 입력과 무관하게 길이 3배 초과면 `None`(원문 노출).
  모델별 실패 특성은 배포 후 실측으로 규칙 보강 — 지금은 이 최소 가드만.
- **큐**: 별도 큐 파일 두지 않음(0.5 결정). 실패 시 대상 행에 `needs_tl: true` 플래그만 남기고
  다음 `/tick` 이 재시도 — "행 자체가 큐". (`v3_draft.md` "LLM 작업 큐" 의 의도를 스케일투제로에
  맞게 축소.)

### 0.4 `admin_state.json` v3 슬롯 (계약 G' — `admin.py` 재작성)

`/notice-*` 4개 + `pending_*` 5종을 **`{cmd} × {contents}}` 격자**로 접는다.

```jsonc
{
  "pending_op": null | {          // /ingest·/edit·/del·/translate 진행 중 1슬롯
    "cmd": "edit",                // ingest | edit | del | translate
    "contents": "preview",        // preview | notice | tweet
    "step": "await_idx",          // 명령별 상태머신 스텝 이름
    "ctx": { /* unit, target_id, patch 누적, snapshot 등 */ },
    "at": "2026-...Z"             // 마지막 문답 시각 — 단계별 TTL 60s
  },
  "edit_lock": null | { "id": "pv_ab12cd34", "until": "2026-...Z" },  // 아이템 단위 편집 락
  "suppress": [ { "url": "...", "until": "2026-...Z" } ],             // /del terminate — url 12h 재진입 차단
  "undo": null | {
    "cmd": "del", "contents": "preview",
    "path": "preview.json",       // preview.json | notices.json | tweets.json
    "prev_content": { /* 그 파일 전체(변경 직전) */ },
    "new_sha": "...",
    "at": "2026-...Z"
  },
  "pending_undo": null | { "at": "...", "target_sha": "...", "action": "..." }  // (y/N) 60s
}
```

- 순수 헬퍼: `default_admin_state()`, `get/set/clear_pending_op`, `pending_op_expired(s, now, ttl=60)`,
  `get/set/clear_edit_lock`, `edit_lock_active(s, id, now)`, `add/sweep_suppress`, `suppressed(s, url, now)`,
  `set/clear_undo`, `set/clear_pending_undo`. `set_*`/`clear_*` 는 다른 슬롯 보존.
- **취소 토큰** `aNoneTokyo` — 전 단계 공통(현행 상수 재사용).
- **단계별 60초 타임아웃** — `pending_op.at` 기준, 만료 시 자동취소 안내 후 통과.

### 0.5 결정 확정 (2026-09-09 운영자 승인)

D1·D2·D3·D6 모두 아래 권장안대로 확정.

| # | 항목 | 확정 | 영향 WP |
|---|---|---|---|
| D1 | `reconcile.build_schedule` 를 어디서 v3화? | **`src/backend/preview_build.py` 로 포크** (collector 는 v2 break-glass 로 동결, v3 는 콜드스타트라 v1 경로 무관) | WP-14 |
| D2 | LLM 작업 큐 파일 | **안 둠** — `needs_tl` 플래그 + 다음 tick 재시도 (0.3) | WP-2, WP-15 |
| D3 | `preview_archive.json` 를 실제로 둘지 | **둔다** — 회원전용 사후확정(RSS 지각 도착)·디버그용. 프론트 미사용 | WP-0, WP-14 |
| D4 | `src/collector/*` 수정 | **rss.py/youtube.py 는 그대로 import 재사용. reconcile.py 는 건드리지 않음**(포크) | 전반 |
| D5 | notice/tweet 번역 프론트 표기 | 토글 버튼(원문↔번역). notice 는 티커라 공간 제약 → **번역만 표시 + 길게눌러 원문** | WP-12 |
| D6 | 업스트림 YouTube 알림 중계 실착수 | `v3_draft.md` 트리거(회원전용 알림 관측) 미충족 — **`ytnotif.py` 파서는 구현하되(WP-3) `/ingest` 라우팅 연결은 플래그 `INGEST_YT_ENABLED` 뒤에** | WP-3, WP-15 |

---

## 진행 상황 (2026-09-09, v3 브랜치 커밋)

| 커밋 | 내용 |
|---|---|
| `e1de80e` | W0+W1 — preview·statemachine·llm·ytnotif·vxtwitter·admin·time.js |
| `5923e4d` | W2 — xnotice·notices·notify·xrelay·xtweet·render.js·tweets/notices.js·config.js |
| `84d8c3b` | W3 데이터 파이프라인 — preview_build·handlers·config.py |
| `0cd80ed` | WP-16(1차) — telegram_app v3 데이터 이관 + /translate·/del terminate + suppress/edit_lock 훅 |
| `dc7877f` | WP-18 일부 — pending.py 삭제 |
| `df49127` | WP-19 — SPEC 델타 노트 + deploy 스크립트 GROQ_API_KEY |
| (다음) | WP-16 마무리 — `{cmd}×{contents}` 격자 + `/edit` 마법사 |

**완료**: WP-0~19 전부. 세부:
- **격자**: `/list` `/ingest` `/edit` `/del` 가 첫 인자 `preview|notice|tweet` 분기(생략=preview,
  `/list arale` 등 v2 호출 하위호환). `/notice*`·`/add` 별칭 유지.
- **`/edit`**: `preview` = `pending_op` 슬롯 마법사(유닛→idx→필드/값 반복→done, `admin.set_edit_lock`
  세팅·해제, 적용 시 답한 필드만 patch + tick 충돌 필드 알림, `/undo` 스냅샷). `notice` = 기존
  `/notice-edit` 재사용. `tweet` = 유닛→원문→`merge_tweet` 교체.
- **`/del`/`/ingest`** 도 `tweet`/`notice` 분기 추가.
- **edit_lock 훅**: `handlers._run` 커밋 직전 `admin.suppressed(url)`(차단 아이템 제외)·
  `edit_lock_active(id)`(락 걸린 id 는 prev 값 유지).
- 전 백엔드 15모듈 self-test + 프론트 selfcheck 통과.

검수에서 수정한 것: time_tbd 만료(다음 JST 자정)·live_seen=None 오판정·D-n 캘린더 일수·
ytnotif 제목 【…】 보존·render buildLive end-only 소등·preview_build ytnotif/supersede 4건·
telegram_app `_merge_rows_into_schedule` v3 튜플 시그니처·`_remove_broadcast` id 매칭.

**배포 후 처리됨 / 남은 정리**:
- ✅ data 브랜치 — `.old/` 이관 + `preview.json` 시드 (2026-09-09, `docs/plan/v3_golive.md`).
- ✅ Groq secret 생성, 스케줄러 잡 URL 검증, LLM 실호출 검증.
- 미결(저위험): `deploy/scheduler.sh` gcloud 신버전 `--update-headers` (이번엔 무해),
  `docs/SPEC.md` 본문 전면 개정, 죽은 `.card--scheduled` CSS·`fixtures/schedule.sample.json`·
  `src/collector/*` — 그대로 둠. 데드맨 스위치(`/ingest` 침묵 경보)는 `v3_draft.md` 미결 항목.
- 텔레그램 현행→v3 명령어 대응표 문서화 — 다른 세션 예정.

---

## 1. 작업 패키지 (WP) 개요

담당: `haiku` = 병렬 에이전트 단독 + 최종 검수(사람/Sonnet). `me` = 통합 담당 직접.

| WP | 대상 | 의존 | 웨이브 | 담당 |
|---|---|---|---|---|
| **0** | `preview.py` + `fixtures/preview.sample.json` | 0.1 | W0 | haiku (검수 강함) |
| **1** | `statemachine.py` v3 재작성 (+`pending.py` 삭제는 W3) | 0.2 | W1 | haiku |
| **2** | `llm.py` 신규 | 0.3 | W1 | haiku |
| **3** | `ytnotif.py` 신규 (YT 푸시알림 파서) | `ref/flow-7*.log` | W1 | haiku |
| **4** | `vxtwitter.py` 신규 (unfurl) | — | W1 | haiku |
| **5** | 프론트 `time.js` v3 상대시간 규칙 | 계약 D 확장 | W1 | haiku |
| **6** | `admin.py` v3 슬롯 재작성 | 0.4 | W1 | haiku |
| **7** | `xnotice.py` + `notices.py` — 중복키(url∥title)·`title_ko`·LLM 훅 | WP-2 시그니처 | W2 | haiku |
| **8** | `xtweet.py` — 리트윗 필터·`text_ko`·개인예고→preview 머지 | WP-0, WP-2 | W2 | haiku |
| **9** | `xrelay.py` — `scheduled`→`announced` 리네임, collab 유지 | WP-0 | W2 | haiku |
| **10** | `notify.py` — `diff_events` 6상태 대응 + log_level 표 | WP-0 | W2 | haiku |
| **11** | 프론트 `render.js` + `css/card.css` — 6상태 카드 | WP-0 형태, WP-5 | W2 | haiku (검수 강함) |
| **12** | 프론트 `tweets.js`/`tweets.css` + `notices.js` — 원문↔번역 토글 | D5 | W2 | haiku |
| **13** | 프론트 `config.js` — `PREVIEW_URL` 등 상수 | WP-0 | W2 | haiku |
| **14** | `preview_build.py` 신규 (reconcile 포크 → 6상태) | WP-0, WP-1 | W3 | me |
| **15** | `handlers.py` 재작성 (tick/wake → preview.json, LLM 말단, edit_lock) | WP-14,1,2,8 | W3 | me |
| **16** | `telegram_app.py` 명령 통합 (`/list /ingest /edit /del /undo /translate × {contents}` + `/status` v3) | WP-0,6,2 | W3 | me (+haiku 서브) |
| **17** | `app.py` + `config.py` env 추가 | — | W3 | me |
| **18** | `pending.py` 삭제·import 스윕·`schedule.json`/`archive.json` 경로 제거 | 전부 | W4 | me |
| **19** | `deploy/*.sh` GROQ secret · `docs/SPEC.md` v3 개정 (**푸시만, 배포 안 함**) | 전부 | W4 | me |

### 병렬 실행 웨이브

```
W0  ─ WP-0                         (스키마 동결. 나머지는 0.1 이름만 있으면 병렬 시작 가능)
W1  ─ WP-1 WP-2 WP-3 WP-4 WP-5 WP-6   ← 6개 완전 병렬, 상호 무의존
W2  ─ WP-7 WP-8 WP-9 WP-10 WP-11 WP-12 WP-13   ← 7개 병렬
        (WP-7·8 은 WP-2 완료 후 / WP-8·9·10·11 은 WP-0 완료 후 / 프론트 3개는 상호 무의존)
W3  ─ WP-14 → WP-15 (순차) ‖ WP-16 ‖ WP-17     ← 14→15 는 직렬, 16·17 은 병렬
W4  ─ WP-18 → WP-19 (통합 정리, me)
```

- **W1 6개는 지금 즉시 병렬 배정 가능** (WP-0 산출물 없이도 0.1~0.4 계약만으로 작업).
- W2 는 WP-0 머지 후. 프론트(11·12·13)는 W1 과도 겹칠 수 있으나 WP-5(time.js) 먼저.
- W3 통합은 사람이. haiku 는 `/status` 문자열 포매팅(WP-16 서브) 정도만 분리 위임.

---

## 2. WP 상세

### WP-0 · `preview.py` + fixture   [haiku]

**만들 것**
- `src/backend/preview.py` (순수 — 네트워크·파일·시계 금지, `now_iso` 인자):
  - `default_preview() -> dict` — `{"generated_at": None, "channel_order": [...], "channels": {}, "items": []}`
  - `new_id(channel_key, first_seen_iso) -> str` — `"pv_" + sha1(f"{channel_key}|{first_seen}")[:8]`
  - `make_item(*, channel_key, state, source, now_iso, **fields) -> dict` — 0.1 스키마 전 필드 채움
    (미지정은 스키마 기본값: `collab_with=None`, `membership=False`, `time_tbd=False`, `assumed_live=False` …)
  - `match_item(items, inc, *, superscede_sec=4*3600) -> dict | None` — 같은 `channel_key` +
    (`video_id` 일치 ∥ `url` 일치 ∥ `scheduled_start` ±4h). `end→none` 으로 사라진 뒤는 매칭 안 함(호출부가 items 에서 이미 제거).
  - `sort_items(items) -> list` — 0.1 정렬 규칙.
  - `promote_state(item) -> str` — 정보 충족도로 `announced`/`upcoming` 판정
    (`upcoming` = `scheduled_start` && !`time_tbd` && `title` && `thumbnail` && `url` && `video_id`).
  - `set_state(item, new_state, now_iso) -> dict` — 원본 복사 + `state`/`state_since`/`last_updated` 갱신.
  - `to_archive_record(item, now_iso) -> dict` — `+archived_at`, `state` 유지.
- `fixtures/preview.sample.json` — 6상태 각 1건 이상 + collab 1건 + membership 1건. 프론트 WP-11 이 로컬에서 이걸로 렌더 확인.

**self-test**: `match_item` 3케이스(video_id/url/시각근접), `sort_items` 우선순위, `promote_state` 경계, `new_id` 안정성.

---

### WP-1 · `statemachine.py` v3   [haiku]

**바꿀 것**: 파일 전체 재작성. `pending.json`·`sync_pending`·`Decision`·`make_entry` 전부 제거.

```python
@dataclass
class Tick:
    next_state: str            # 인자 state 와 같으면 전이 없음
    next_check_at: str | None  # Cloud Tasks enqueue 시각(저장 안 함). None = 더 볼 것 없음
    log: list[str]

def derive(item: dict, now_iso: str, *, live_seen: bool | None = None,
           preview_stream_seen: bool = False) -> Tick
```

- `live_seen` = 이번 사이클 API/알림이 이 `video_id` 를 live 로 봤는지 (`None`=미확인).
  `handlers` 가 `videos_list` 결과로 채워 넘김.
- 0.2 표 그대로 구현. `MAX_TASK_HORIZON_SEC` 클램프는 `handlers` 가 아니라 여기서
  `next_check_at` 반환 직전에 적용.
- **self-test**: 0.2 표 각 행 1시나리오 + membership 직행 + horizon 클램프 = 최소 11 assert.

---

### WP-2 · `llm.py` 신규   [haiku]

- 0.3 시그니처 구현. Groq REST (`https://api.groq.com/openai/v1/chat/completions`), `requests`.
  형제 프로젝트 `bandori-playlist-maker` 프롬프트/클라이언트 코드가 있으면 참고(없으면 신규).
- 프롬프트: notice 는 "본문에서 이벤트 제목 1줄 추출 + 한국어 번역, JSON 만 출력".
  translate 는 "다음 일본어 트윗을 자연스러운 한국어로. 고유명사 보존. 번역문만".
- `reasoning_effort="low"`, `temperature=0`, `response_format` 은 모델별 분기(gpt-oss=json_schema,
  llama-3.3=json_object).
- **self-test**: `requests` 세션을 가짜 객체로 주입 — 200 정상 / 429→백오프→폴백 / 깨진 JSON→None /
  환각(과길이)→None. 네트워크 없이 4 assert. (실호출은 `GROQ_API_KEY` 있을 때만 `--live` 플래그.)

---

### WP-3 · `ytnotif.py` 신규   [haiku]

- 입력 = `/ingest` 가 넘기는 알림 payload dict (키: `chime.slot_key`, `pde_noti_tag`,
  `chime.thread_id`, `android.title`, `android.text`, `android.template`, `android.subText`).
- `parse_yt_notif(nx: dict, now_iso: str) -> dict | None`:
  - `pde_noti_pkg != com.google.android.youtube` → `None`. `SUMMARY` 태그 → `None`.
  - `thread_id` 접두어로 종류 분기 → 제목 필드 선택 (`v3_backend_surgery.md` §1 표):
    `TUNEIN`→`android.text` / `REMINDER`→`android.title` / `SUBSCRIPTION_LIVESTREAM_START`→`android.text`.
  - 제목 앞 `🔴 `·`【…】` 정리.
  - `video_id` = `chime.slot_key` (11자 검증). `url` = `watch?v=<id>`,
    `thumbnail` = `https://i.ytimg.com/vi/<id>/mqdefault.jpg`.
  - `kind` (`tunein`/`reminder`/`sub_start`), `scheduled_start`:
    TUNEIN → `now + 30분` + `time_approx=True`. REMINDER/START → `now` (=시작 신호).
  - 반환: `{video_id, url, thumbnail, title, kind, scheduled_start, time_approx, source:"yt-notif"}`.
- **self-test**: `ref/flow-7 (2).log` 에서 확정된 3건(ritsu `bgzve7Y7S50` / yuno `2eigVMdk3Pg` /
  arale `Pi7kwM-bS6w`) payload 를 인라인 dict 로 넣고 assert. 노이즈(InboxStyle 빈 알림·dcinside) → `None`.

---

### WP-4 · `vxtwitter.py` 신규   [haiku]

- `fetch_tweet(tweet_id: str, *, session=None, timeout=8.0, base="https://api.vxtwitter.com") -> dict | None`
  → `GET {base}/i/status/{id}` JSON.
- `extract(j: dict) -> dict` → `{text, media: [url...], urls: [expanded...], yt_video_id: str|None}`.
  `yt_video_id` = 본문/urls 에서 `youtube.com/(watch\?v=|live/)` · `youtu.be/` 11자 추출.
- 실패(비200·타임아웃·JSON 오류) → `None` + warning. 서드파티 다운 시 조용히 스킵.
- **self-test**: 캡처한 응답 JSON 1개를 `fixtures/vxtwitter.sample.json` 로 두고 `extract` assert
  (미디어 있는 트윗 + `youtube.com/live/` 포함 트윗). fetch 는 가짜 세션.

---

### WP-5 · 프론트 `time.js` v3   [haiku]

계약 D 확장. `relativeLabel(iso, nowMs)` 구간 재정의:

| 조건 (start − now) | 출력 | 비고 |
|---|---|---|
| 지각(< −5분) | `"{n}분 지각"` / `"{h}시간 {m}분 지각"` | 현행 유지 |
| < 60초 | `"곧 시작"` | 현행 유지 |
| 오늘(같은 KST 날짜) | `"{h}시간 {m}분 후"` (h·m 0 처리) | 현행 `<24h` 로직 유지 |
| 7일 이내(오늘 아님) | `"D-{n} {HH}:{mm}"` — KST 시각 | **신규 구간** |
| 그 외 | `"{YYYY}-{MM}-{DD} {HH}:{mm}"` — KST | **신규** (현행은 `formatKST` = MM/DD HH:mm) |

- `D-n` 의 `n` = KST 자정 기준 일수 차(올림, 최소 1).
- `formatKST` 시그니처 유지(`render.js` 가 `<time>` 표시에 계속 씀) — 반환만 `YYYY-MM-DD HH:mm`
  옵션 추가: `formatKST(iso, {full=false})`.
- live 라벨 `"방송 중"` → v3 는 `"방송 중 ({m}분)"` — `render.js` 가 `actual_start` 로 계산하므로
  time.js 에 `elapsedLabel(actualStartIso, nowMs) -> "방송 중 (12분)"` 추가.
- `end` 라벨 `"방송 종료"` 는 render 고정(time.js 무관).
- **self-test**: 파일 하단 주석에 케이스 표 + `node time.js` 로 돌릴 수 있는 `if (import.meta...)`
  대신, 간단히 `time.selfcheck.mjs` 하나 추가해 `assert` (프레임워크 없이).

---

### WP-6 · `admin.py` v3 슬롯   [haiku]

0.4 스키마로 파일 전체 재작성. v2 의 `pending_del`/`pending_ingest`/`pending_notice`/
`pending_notice_edit`/`pending_member`/`pending_undo` 개별 슬롯 → `pending_op` 1슬롯 + `cmd`/`contents`/`step`/`ctx`.
`undo.path` 는 3파일(`preview.json`/`notices.json`/`tweets.json`) 대응. `edit_lock`·`suppress` 신규.

- **self-test**: 슬롯 set/clear 시 타 슬롯 보존, `pending_op_expired` TTL 60s, `edit_lock_active`
  시각 경계, `suppressed`/`sweep_suppress` 12h, `undo` path 분기 = 최소 10 assert.

---

### WP-7 · `xnotice.py` + `notices.py`   [haiku]

- `xnotice.parse(...)` : **분류·날짜·URL 은 정규식 유지**. 제목 추출부(`_headline`)를
  `title_raw` 만 반환하도록 두고, 실제 제목 확정+번역은 호출부(`handlers`)가 `llm.notice_title`
  로 (본문에서 날짜/URL 제거한 텍스트 전달). `parse` 반환 dict 에 `body_for_llm` 필드 추가.
- LLM 미가동(`None`)이면 현행 `_headline` 정규식 결과를 `title` 로 폴백.
- `notices.merge_notice` : **중복키 = `url` 일치 ∥ `title` 일치** (v2 `date+anchor_a/b` 대체).
  `anchor_*`·`title_slug` 계산 코드는 제거 가능(남겨도 무해하나 정리 권장).
- 항목 스키마에 `title_ko` 추가. `edit_notice` 의 `_EDITABLE` 에 `title_ko` 포함.
- `notice_archive.json` 그대로.
- **self-test**: 기존 S1~S12 중 anchor 의존 케이스를 url/title 중복으로 재작성. `title_ko` 병렬저장.

---

### WP-8 · `xtweet.py`   [haiku]

- **리트윗/타인글 필터**: 본문이 `@핸들:` 패턴으로 시작(리트윗·인용 표기)하면 `parse` → `None`.
  정규식 `^\s*@[\w]+\s*[:：]`.
- 항목 스키마에 `text_ko` 추가 (`merge_tweet` 이 병렬 보존, 프론트 토글용).
- 실제 번역 호출은 `handlers._maybe_personal_tweet` 말단에서 `llm.translate` → `text_ko`.
  실패 시 `needs_tl=true`.
- **개인 예고 → preview 머지**: `parse_schedule` 유지하되 산출물을 v3 `preview.py` 아이템으로.
  `merge_personal_schedule(prev_items, inc, now_iso)` → `preview.match_item` 로 upsert,
  `state="announced"`, `source="personal"`, `info_source`/`info_at`/`time_tbd`/`api_start_seen` 세팅.
  `apply_overrides(new_items, prev_items, now_iso)` — 트윗이 정한 `scheduled_start` 를 API 재구성이
  안 덮게 (계약 §1-1 로직 그대로, 필드명만 preview 기준).
- `route_by_title` 무변경. `tweet_archive.json` 무변경(+`text_ko`).
- **self-test**: 리트윗 필터 3케이스, `merge_personal_schedule` upsert(같은 방송 재수신),
  `apply_overrides` API-override 억제.

---

### WP-9 · `xrelay.py`   [haiku]

- `parse` 산출 행의 `status:"scheduled"` → **`state:"announced"`** (preview 스키마).
  `sched_id` 제거(→ `preview.new_id`), `kind`/`collab_with`/`host`/`members_only`/`source:"x-relay"` 유지.
- `merge_scheduled` → `merge_announced(prev_items, inc, now_iso)` — `preview.match_item` 기반 upsert
  (replace-by-date 아님). collab 팬아웃 판정(`channel_key` ∪ `collab_with`)·`host=="group"` 특례 유지.
- `unparsed_lines`·`looks_relayable`·`summary_text` 시그니처 유지.
- **self-test**: 기존 S1~S9 를 preview 아이템 형태로 assert 재작성. collab `_carry_collab` 이관.

---

### WP-10 · `notify.py`   [haiku]

- `diff_events(prev_items, new_items, transitions, channels_cfg, now_iso)` — v2 는 `status`
  `upcoming`/`live` 만 봤음. v3 는 `state` 전이:
  | kind | 전이 |
  |---|---|
  | `announced` | new 에 `announced` 등장(첫실행 가드 유지) |
  | `upcoming` | `announced→upcoming` |
  | `live_start` | `*→live` (`lateness = actual_start − scheduled_start`) |
  | `live_end` | `live→end` |
  | `gone` | `end→none` (요약에만, 개별 전송 X) |
  | `demote` | `watching→announced` 지각 강등 (fallback 대체) |
- `allows(level, kind)` 표 (`SPEC.md` §6 갱신):
  `announced`=`scheduled` 자리(detail·normal), `upcoming`/`live_*`=전 레벨, `demote`=detail 만.
  `notice`/`tweet` 현행 유지.
- **self-test**: 전이별 이벤트 생성 + 첫실행 가드 + 레벨 게이팅 = 기존 10 시나리오 갱신.

---

### WP-11 · 프론트 `render.js` + `css/card.css`   [haiku · 검수 강함]

- `renderBoard` 가 `schedule.broadcasts`(`status`) → `preview.items`(`state`) 로.
  버킷 분류·레인 그룹핑·collab 팬아웃(`channel_key` ∪ `collab_with`) 골격은 유지.
- 카드 클래스 매핑:
  | state | 클래스 | 표기 |
  |---|---|---|
  | `announced` | `card--announced` (기존 `card--scheduled` 관례) | 점선·감광, 아이콘, "예고" |
  | `upcoming` | `card--upcoming` | 현행 |
  | `watching` | `card--watching` | 현행 upcoming + "대기 중" 배지(썸네일 있으면 표시) |
  | `live` | `card--live` | `LIVE` 배지, `card__rel` = `"방송 중 ({m}분)"` |
  | `end` | `card--end` | **OFF-AIR 소등**(빨강테두리 제거), `card__rel` = `"방송 종료"`, 영상 유지 |
  | membership | `+ card--membership` | 썸네일 자리 자물쇠, "회원 전용 방송" |
- `assumed_live` && `state in (announced,upcoming)` → 현행 `card--sched-live` "방송 중 (추정)".
- `lane__live` `data-state` : `live` 있으면 `on`, `end` 만 있으면 `off`(소등) + 카드는 버킷에.
- **XSS**: `textContent`/`createElement` 만. `innerHTML` 금지 유지.
- `updateCountdowns` : `live` 는 `elapsedLabel`, 나머지 `relativeLabel`. 구간 넘으면 재렌더.
- **self-test**: `fixtures/preview.sample.json` 로컬 렌더 — `python -m http.server` 로 눈 확인
  (자동 assert 는 DOM 없어 생략, 대신 `render.selfcheck` 로 순수 헬퍼(`bucketOf`, `laneKeys`)만).

---

### WP-12 · 프론트 `tweets.js`/`tweets.css` + `notices.js`   [haiku]

- `tweets.js` : 말풍선/토스트에 원문↔번역 토글 버튼. `text_ko` 있으면 기본 번역 표시,
  버튼으로 `text` 원문. `localStorage` 로 마지막 선택 기억(`mew:tllang`).
- `notices.js` : `title_ko` 있으면 티커에 번역 표시, **길게 눌러 원문**(D5). 공간상 버튼 안 넣음.
- `text_ko`/`title_ko` 없으면(미번역) 원문만 — 토글 숨김.
- **self-test**: `fixtures/tweets.sample.json`·`notices.sample.json` 에 `*_ko` 넣고 눈 확인.

---

### WP-13 · 프론트 `config.js`   [haiku]

- `DATA_URL` → `PREVIEW_URL` (`raw.githubusercontent.com/.../data/preview.json`). `NOTICES_URL`·
  `TWEETS_URL` 유지. `api.js`/`main.js` 의 참조명도 함께 정리(작은 변경, 같은 WP).
- 폴백 상수(`FALLBACK_CHANNEL_ORDER`/`FALLBACK_CHANNELS`) 유지.

---

### WP-14 · `preview_build.py` 신규 (reconcile 포크)   [me]

- `src/collector/reconcile.py` 를 `src/backend/preview_build.py` 로 복사 후 v3화:
  `build_preview(channels_cfg, videos, prev_preview, now_iso, *, avatars=None,
  ytnotif_items=None) -> (new_preview, transitions)`.
- 후보 집합·`live_state` 분기·`removed` 유예(6.5h)·collab supersede/`_carry_collab` 골격 유지.
- 차이:
  - 출력이 `items[]` + `state`. `status` 3값 → `state` 5값.
  - `none` 판정 시 archive append + items 에서 제거 (D3: `preview_archive.json`).
  - `announced` 행 보존/승격: `preview.promote_state` 로 `announced`↔`upcoming`.
  - FSM 전이 반영: `statemachine.derive` 를 각 `watching`/`live`/`end` 아이템에 적용해
    `state`·`state_since` 갱신 + `transitions` 로그. `next_check_at` 리스트는 `handlers` 에 반환.
  - `assumed_live` : `announced`/`upcoming` + `video_id` 없음 + `ss` 지남. 90분 폴백은 `derive` 가 `none`.
  - `ytnotif_items` 머지: video_id 로 `match_item` upsert(공개=정규 파이프라인 합류, membership=별도).
- **self-test**: v2 reconcile self-test 시나리오를 6상태로 재작성 + FSM 전이 3케이스 + ytnotif 머지.

---

### WP-15 · `handlers.py` 재작성   [me]

- `tick(mode)` / `wake(video_id)` 골격 유지. 변경점:
  - `build_schedule`+`sync_pending`+3파일 커밋 → `build_preview` + **`preview.json` 1파일 커밋**
    (+`preview_archive.json` 변경 시). `pending.json` 커밋 삭제.
  - 커밋 루프(최대 2회 `ConflictError` 재시도) 유지. `edit_lock` 걸린 `id` 는 이번 사이클
    `preview.json` 에서 그 아이템 필드 갱신 스킵(다른 아이템·다른 파일은 정상).
  - Cloud Tasks: `statemachine.derive` 가 준 `next_check_at` 들 → `enqueue_wake`.
    `newly_ended`(→`end`) 있으면 `enqueue_tick("light", now+20분)`. `announced` 예고 시각 wake
    (`_scheduled_wake_times`) 유지.
  - **LLM 말단**: 파이프라인 끝에서 자동 로직만 —
    · notice 신규/갱신분 → `llm.notice_title` → `title`/`title_ko`
    · 개인 트윗 신규분 → `llm.translate` → `text_ko`
    · 실패 → `needs_tl=true`, 다음 tick 재시도 (`needs_tl` 붙은 행 우선 처리).
    · preview 제목 번역 **안 함**.
  - Telegram diff = `notify.diff_events` (6상태). heartbeat(20분) 유지.
- 반환 dict 키에서 `pending_*` 제거, `preview_items`/`state_counts` 추가.

---

### WP-16 · `telegram_app.py` 명령 통합   [me + haiku 서브]

- 현행 개별 핸들러(`_handle_del_*`, `_handle_ingest_followup`, `_handle_notice_*`,
  `_handle_member_followup`, `_handle_notice_edit_*`, `_handle_undo_*`) → **`{cmd} × {contents}`
  디스패치 1계층**으로 재편:
  ```
  /list <contents>        /ingest <contents>     /edit <contents>
  /del <contents>         /undo                  /translate <contents>
  /status /pause /resume /log   (일반 — 현행 유지, /status 만 v3 재포맷)
  ```
  - `contents` ∈ `preview | notice | tweet`. `/notice`·`/notice-list`·`/notice-del`·`/notice-edit`
    및 `/add` 별칭 **삭제** (→ `/… notice`).
  - `pending_op` 슬롯 1개로 모든 되묻기 상태머신. 단계별 60s TTL. `aNoneTokyo` 취소.
  - `/edit <contents>` : `/list` 출력 → idx 되묻기 → `edit form` 제시 → 필드 선택 또는
    `ingest` 응답(= `/edit -i` 흡수). 답한 필드만 patch. `edit_lock` 세팅/해제 + 해제 시
    tick 충돌 필드 알림(`유지 / 재편집?` 60s, 무응답=운영자값).
  - `/del preview` : 유닛 → idx → 최종확인 `(terminate/y/N)`.
    · `y` = 아이템만 삭제 · `N`/60s = 취소 · `terminate` = 삭제 + `admin.add_suppress(url, 12h)`
    (url 없으면 `y` 와 동일 + 안내). `preview_build` 가 `suppress` 대조해 재생성 차단.
  - `/undo` : 직전 mutating 명령 1건 (계통 무관 단일 슬롯). 2단계 확인 + sha 2중 가드 유지.
    `undo.path` 로 3파일 복원.
  - `/translate <contents>` : `/list` → 유닛/idx(`all` 지원) → `llm` 호출 → 대상 행 `*_ko`
    갱신(원문 보존). **수동 명령이므로 자동 파이프라인의 번역과 별개** (`v3_draft.md` 결정).
- **`/status` v3** (`v3_telegram_controller.md` 양식) — haiku 서브 위임 가능:
  preview 상태 6종 카운트 · notice 건수+최이른 D-day · tweet 유닛목록(n/5) · 동기화 4줄 ·
  `LLM 큐` 대기(= `needs_tl` 행 수) · 업스트림 마지막 수신.
- `/ingest preview` : 유닛 되묻기(2명+ = 합동, 첫 번째 = 주 레인) → 원문 → 파싱 머지.
  `_ingest_queue_drain`(ECHO/DRY-RUN 버퍼) 유지.
- **self-test**: 현행 `__main__` 시나리오를 새 디스패치로 재작성 — `/edit` 락·충돌알림,
  `/del terminate` suppress, `/undo` 3파일, `/translate all`.

---

### WP-17 · `app.py` + `config.py`   [me]

- `config.py` : `GROQ_API_KEY`, `GROQ_MODEL`(기본 `openai/gpt-oss-120b`),
  `GROQ_MODEL_FALLBACK`(기본 `llama-3.3-70b-versatile`), `VXTWITTER_BASE`(기본
  `https://api.vxtwitter.com`), `INGEST_YT_ENABLED`(기본 `""`). `load_config` 누락 허용 유지.
- `app.py` : 라우트 무변경. `/wake` body 키 `video_id` 유지. 예외 처리 유지.
- `requirements.txt` : 추가 의존 없음(Groq·vxtwitter 는 `requests`).

---

### WP-18 · 정리   [me · W4]

- `src/backend/pending.py` 삭제. `statemachine` 구 export 참조 제거.
- `handlers`·`telegram_app`·`notify` 의 `schedule.json`/`archive.json`/`pending.json` 잔존 참조 제거.
- `from ..collector.store import default_schedule` → `preview.default_preview`.
- `fixtures/schedule.sample.json` → `preview.sample.json` 로 대체(구파일은 남겨도 무방).
- 전 모듈 `python -m src.backend.<mod>` 스모크 재확인.

### WP-19 · 문서·배포 스크립트 (푸시만)   [me · W4]

- `docs/SPEC.md` → v3 계약으로 개정 (계약 A'`preview.json`, E 폐지, G' `admin_state`,
  H `title_ko`, I `text_ko`, §8 모듈 표). 또는 `docs/SPEC.md` 를 통째로 v3 기준 재작성.
- `deploy/deploy_telegram.sh`·`deploy/setup.sh` : `GROQ_API_KEY` Secret 추가 (주석으로
  "배포 시 활성화" 표시 — **실행 안 함**).
- `CLAUDE.md` 저장소 구조 절 v3 반영.
- **배포·`data` 브랜치 작업은 이 WP 에 포함하지 않음** — golive 런북(별도)에서.

---

## 3. 착수 순서 요약

1. **지금**: WP-0 배정(haiku) + W1 6개 동시 배정(haiku ×6) — 상호 무의존.
2. WP-0 검수 완료 → W2 7개 배정. 프론트 3개(11·12·13)는 WP-5 먼저 끝나야 착수.
3. W2 검수 완료 → me 가 WP-14→15 직렬, WP-16·17 병렬.
4. WP-18 정리 → WP-19 문서. `v3` 브랜치 푸시. **머지·배포 없음.**

## 4. 검수 체크리스트 (각 WP 수령 시)

- [ ] `python -m src.backend.<mod>` self-test 통과 (프론트는 fixture 렌더 눈 확인).
- [ ] 직렬화 규칙(`sort_keys+indent=2+ensure_ascii=False+개행`) 준수.
- [ ] 시각 전부 UTC ISO `Z`. KST 변환은 `time.js` 만.
- [ ] `innerHTML` 없음(프론트). `textContent`/`createElement` 만.
- [ ] 0절 계약 이름·시그니처와 일치. 벗어나면 0절 먼저 수정했는지.
- [ ] 한국어 주석. `ponytail:` 주석으로 의도적 단순화 표시.
