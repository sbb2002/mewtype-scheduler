# v2.7 — 소식 게시판 (방송 외 이벤트)

작성 2026-09-07. v2.3(X 릴레이) 위에 얹는다.
**백엔드·프론트 구현 완료.** UI 목업: `docs/plan/v2_7_notice_board_mockup.html`

- UI 목업(확정): `docs/plan/v2_7_notice_board_mockup.html`
  (아티팩트: https://claude.ai/code/artifact/5ab98542-e5a2-4ec1-8a6e-dac81789a9d8)

---

## 0. 배경

폰 X 릴레이(`/ingest`, v2.3.x)로 이제 `@BDP_yumemita` 의 **모든** 알림이 백엔드에 온다.
일일 스케줄 트윗(→ `scheduled` 행) 외에도 **라이브 예고·음반/굿즈·타 플랫폼 방송·기타
공지**가 섞여 오는데, 지금은 스케줄 형식이 아니면 버린다. 이걸 예고판 상단의 얇은
"소식" 티커로 보여준다. 메인 콘텐츠(5인 유닛 스케줄)을 가리지 않는 게 최우선.

## 1. UI 확정 사양 (목업 참고)

- **접힘(기본)**: 딱 한 줄. 5초마다 다음 소식으로 세로 슬라이드 → 끝나면 무한 순환.
  진행바 없음. 마우스 올리면 정지(읽기·클릭), 벗어나면 재개. 탭 백그라운드면 정지.
- **펼치기(▾, 큰 화살표)**: 전체 소식 세로 목록이 아래 스케줄 **위에 오버레이**로 뜬다
  (스케줄 안 밀림). `max-height` 트랜지션으로 스르륵. `#notice` 밖을 단순 탭(드래그 아님)하면
  닫힘. **접으면 마지막 보던 소식부터** 순환 재개. 목록 하단에 `지난 소식 · 아카이브 →` 입구.
- **소식 0건**: 완전히 숨기지 않고 빈 막대("새 소식이 없습니다", 펼치기 비활성)만 유지.
- **한 줄 구성**
  - PC: `[날짜(우측정렬)] [D-DAY 배지] [사이트아이콘+시각] [이름·넘치면 marquee] [출처 아이콘+@ID]`
  - 모바일: `소식` 글자·날짜 컬럼 제거(램프만) → `[D-DAY] [아이콘+시각] [이름] [출처 아이콘]`.
    이름이 영역을 더 차지.
  - 모든 컬럼 고정 폭(이름만 가변). 시각은 JST 를 그대로(KST 와 동일).
- **좌측 램프**: `TODAY` 배지 소식이 하나라도 있으면 빨강 느린 점멸(2.4s), 없으면 소등.
- **D-DAY 배지**(카테고리 칩처럼 네모칸): `TODAY`=빨강 / D-1~D-7=주황 / 그 외=무채색 /
  날짜 없음=박스 없이 `—`.
- **링크**: 이름 클릭 → 트윗이 준 URL(YouTube/bilibili/스토어…). 없으면 출처. 출처 클릭 →
  원문 트윗 `x.com/i/status/<id>`. 시각 앞 아이콘 = 이름 클릭 시 도착 사이트.
- **정렬**: 임박순(시각 가까운 것 위, 시각 없는 소식은 아래).
- **아래 스케줄과 중복 제외**: `reconcile` 로 `scheduled`/`upcoming` 이 된 예고는 게시판에 안 띄움.

## 2. 카테고리 (4개 고정)

`라이브예고` / `음반·굿즈` / `타 플랫폼` / `기타`. **분류 안 되면 `기타`.**
(UI 티커엔 카테고리 칩 없음 — 펼친 목록의 좌측 3px 색선으로만 표시.)

## 3. 수명 · 아카이브

- 각 소식은 **그 기준 날짜의 자정(JST=KST)까지** 표시 → 날짜 넘어가면 게시판에서 사라짐.
- 날짜 없는 공지는 **게시 시각(posted_at) 기준** 같은 규칙(그 날 자정까지).
- `schedule.json`/`archive.json` 처럼, 사라진 소식도 **`notice_archive.json` 에 기록 보존**
  (되돌리기·집계·"지난 소식" 조회용).

## 4. 데이터 계약 (구현 — `src/backend/notices.py`)

### `notices.json` (data 브랜치 루트) — 정렬: date asc → time asc → id (undated 뒤)

```jsonc
{
  "generated_at": "2026-09-07T...Z",
  "notices": [
    {
      "id": "2096552878769152326",       // 첫 트윗 ID(Snowflake). tag 없으면 "n"+sha1(cat+date+slug)[:15]
      "category": "live",                 // live | release | platform | etc
      "title": "「アワーノーツ」リリース日決定特番",  // xnotice._headline (가장 눈에 띄는 줄)
      "date": "2026-09-13",               // 이벤트 날짜 (JST). 시각만 있으면 오늘로 보정
      "time": "21:00",                    // JST HH:MM (심야표기 24:xx 그대로). null 가능
      "deadline": false,                  // true 면 date 는 "〜M/D" 마감일
      "site": "youtube",                  // youtube | bilibili | store | music | web | x
      "url": "https://youtube.com/live/...",   // 이름 클릭 목적지. null → tweet_url
      "tweet_url": "https://x.com/i/status/2096552878769152326",  // 출처 클릭
      "src_handle": "@BDP_yumemita",      // 리포스트면 "RT @xxx"
      "anchor_a": "kx-nhmTj4Eg",          // 중복키 a — URL id (YT/bilibili/store tail)
      "anchor_b": "アワーノーツリリース日決定特番",  // 중복키 b — 「」/『』 인용구
      "title_slug": "アワーノーツリリース日決定特番",  // 합성 id 계산용
      "seen_ids": ["2096552878769152326"], // 이 소식을 만든·강화한 트윗들
      "first_seen": "...Z", "last_updated": "...Z",
      "expires_at": "2026-09-14T15:00:00Z"     // 이벤트 '그 날' JST 자정 다음 → UTC. 24:xx면 +1일
    }
  ]
}
```

### `notice_archive.json` — `{ "notices": [ <위 + archived_at> ] }`, append-only, `id` dedupe.

### 중복 판정 (`notices.merge_notice`) — mode ∈ added|updated|recap|dup|skip

1. `incoming.id` 가 어느 소식의 `id`/`seen_ids`(활성+아카이브)에 있음 → **dup** (no-op)
2. **같은 `date`** 이고 · 둘 다 `anchor_a` 있으면 `a` 일치 · `a` 없으면 둘 다 `anchor_b` 있고 `b` 일치
   → 같은 소식
   - `is_recap` + 이벤트 날짜 지남 → `seen_ids` 만 append → **recap**
   - 그 외 → 필드 갱신(title/time/url/site/anchor 은 나중 트윗 우선, date 유지) → **updated**
3. 활성에 없고 아카이브에서 같은 그룹 → 아카이브 `seen_ids` append, **부활 안 함** → **recap**
4. 아무 데도 없음: `is_recap` + 날짜 지남 → **skip** / 그 외 → **added**

날짜 다르면 별도 소식 (DAY1/DAY2 자동 분리). 불완전 그룹핑이어도 `sweep_expired` 가 자정에
아카이브로 치우므로 중복은 유한·자가치유.

## 5. 입력 경로 — 자동 + `/notice` 개입 (구현)

목표: **평소엔 무인. 문제 있을 때만 `/notice*`·`/undo` 로 손댐.**

- **자동**: 정기 `/ingest`(실배포, `INGEST_ECHO=0`) 에서 `xrelay.parse()` 가 행을 안 내면
  → `xnotice.parse(text, tag, title)` → `notices.merge_notice` → 커밋.
  - `added`/`updated` → 한 줄 DM (`🆕 소식 추가/갱신됨` + `↩️ /undo`).
  - `recap`/`dup`/`skip`/`none` → **조용히**(로그만).
  - 매 `/ingest` 진입 시 `_notice_sweep` 도 돌려 만료분을 아카이브로.
- **`/notice`** (무인자) → `pending_notice` 슬롯 + 안내 → 트윗 원문/파일 이어 보내기
  (`aNoneTokyo` 취소, `/`명령이면 대기 접고 통과, 180초 만료). `_apply_notice` 로 같은 경로.
- **`/notice-list`** (별칭 `/notices`) — id + 요약 나열. **`/notice-del <id|번호>`**(별칭 `/ndel`)
  — 1건 제거 + `/undo` 스냅샷.
- **`/notice-edit <id|번호>`** (별칭 `/nedit`, v2.7.x) — 편집 마법사. `pending_notice_edit` 슬롯
  (`{nid, step, new}`, TTL 300s)에 저장하고 **제목 → 날짜 → URL** 순으로 한 필드씩 되묻는다.
  각 단계 응답: 새 값 → `new` 누적 · `aNoneTokyo` → 그 필드 유지 · 다른 `/명령` → 취소하고 통과 ·
  5분 만료 → 취소. 마지막 단계 후 `_notice_edit_finalize` 가 바뀐 필드 + 파생값(`title_slug`·
  `expires_at`·`site`·`anchor_a`)만 patch 로 만들어 `notices.edit_notice(prev, nid, patch, now)`
  로 커밋(`id`/`seen_ids`/`first_seen` 보존) + `/undo` 스냅샷(`path=notices.json`).
  날짜 입력은 `YYYY-MM-DD` 또는 `xnotice._pick_event_date`(예: `11/21`, `11月21日`) 로 파싱.
  자동 감지가 잘린 폴백 알림 등으로 제목을 못 뽑았을 때의 유일한 교정 수단.
- **`/undo`** — `undo.path` 가 `notices.json` 이면 그 파일을 복원. y/N 2단계·SHA 가드 동일.
  `_undo_diff_text` 가 path 따라 `broadcasts`↔`notices` 를 `id` 로 비교.

## 6. 파서 · 분류 (`src/backend/xnotice.py`)

`parse(text, now_iso, *, tag=None, title=None) -> dict | None`

- **None 조건**: `配信スケジュール`/`出演情報` 포함 · 날짜·시각 **둘 다 없음**.
- **이벤트 날짜**: `M/D(曜)` · `○月○日` · `〜M/D`(deadline) · `2025年9月7日`/`2025/9/7`(명시 연도).
  본문에 `20xx年`/`20xx/` 가 있으면 그 연도 사용(회고글이 작년 날짜 적는 경우), 없으면 `_infer_year`
  (now 최근접). 여러 개면 `開催`/`発売`/`配信`/`リリース`/`より`/`から` 동사 근처(뒤 40자) 우선,
  아니면 미래 최근접. 시각만 있고 `本日`/`今夜` 등이면 오늘로 보정, 아니어도 시각만이면 오늘.
- **회고글 컷**: `_RE_RETRO`(`今日は何の日` · `N年前` · `去年の` · `懐かし` 등) → `is_recap`.
  `merge_notice` 는 **지난 날짜의 신규 소식은 `is_recap` 여부 무관하게 `skip`**(예고판에 안 올림).
- **카테고리** (먼저 맞는 것): `platform`(`bilibili`/`ニコ生`/`ツイキャス`/`全員【`) →
  `live`(`配信決定`/`特番`/`生配信`/`放送決定`/`プレミア公開`) →
  `release`(`リリース`/`発売`/`受注`/`予約`/`グッズ`/`CD`/`EP`/`フェア`) → `etc`.
- **사이트/URL/anchor_a**: 본문 온전 URL 하나 — `youtube.com/(watch?v=|live/)<11>` /
  `*.bilibili.com/<id>`·`b23.tv/*` / music(`lnk.to`·`spotify`·`music.apple`) / store
  (`bushiroad`·`booth.pm`·`/products/`) / 그 외 `web`. 없으면 `x`.
- **anchor_b**: 첫 `「…」`/`『…』` 정규화.
- **제목(`_headline`)** (v2.7.x 개선):
  - `_join_shout_titles` — 같은 장식 문자(`💪…💪` `🔥…🔥` `＼…／` · 역방향 `／…＼`)로 앞뒤를
    감싼, 최대 3줄에 걸친 외침형 제목을 한 줄로 합침.
  - `_LABEL_LINE_RE` — `日程：`/`会場：`/`料金：`/`チケット：` 등 부가정보 라벨 줄 −40점.
  - `_TITLE_NOUN_RE`(`最終回`·`第N話`·`放送開始`·`オンエア` 등) +25점 — 이 줄이 곧 제목.
  - `_STREAM_LIST_RE`(`ABEMA/Prime Video/dアニメ/Hulu/U-NEXT…` 슬래시 나열) −35점 — 배포 채널 안내.
  - 날짜로 시작하는 줄 −15점은 같은 줄에 이벤트 명사(`_TITLE_NOUN_RE`/`_EVENTISH_RE`)가 있으면 면제.
  - `_MID_DECO_RE` — 제목 중간에 박힌 순수 장식 이모지(`✨🌟💫🎊❗⏰` 등) 제거.
  - 그래도 틀리면 `/notice-edit` 로 수동 교정. (반복되면 그때 LLM 도입 검토 — 훅 지점만 확보)
- **src_handle**: 본문이 `@handle:` 로 시작하거나 `title`(android.title)이 공식 표시 이름이
  아니면 `RT …`.

`全員【bilibili】` 등 v2.6 에서 `xrelay._SKIP_LINE_RE` 로 스킵하던 라인이 여기로 흡수된다.

## 7. 프론트 (구현 — `src/frontend/js/notices.js` + `css/notices.css`)

- `main.js` 가 `NOTICES_URL`(`config.js`) 을 `POLL_MS` 주기로 fetch → `renderNotices(#notice, data)`.
  404/오류·소식 0건이면 **빈 막대**(램프 소등·"새 소식이 없습니다"·펼치기 비활성)만 둔다
  (완전 숨김 안 함 — 자리 유지).
- `notices.js` = 목업 로직 이식: 접힘 = 한 줄, 5초마다 세로 슬라이드 무한 순환(첫 항목 클론으로
  이음새 없음), hover/focus/탭숨김 정지.
  좌측 램프(TODAY 있으면 빨강 점멸), D-DAY 배지(TODAY 빨강/D-7 주황), 제목 넘치면 marquee.
- **펼침(`▾`)** = 오버레이. `.ntc__list` 가 `position:absolute` 로 예고판 **위에 떠서** 뜬다
  (예고판 안 밀림, PC·모바일 공통). `max-height` 0↔실측 px 트랜지션(0.3s)으로 스르륵.
  `#notice` **밖을 단순 탭**(이동 10px 이하 — 드래그·스크롤은 무시)하면 닫힘.
- 예고판 버킷은 모바일(`<768px`)에서 `한 달 이내`+`그 이후` → `7일 이후` 하나로 통합
  (`render.js` `BUCKET_DEFS_MOBILE`; 767px 경계 넘으면 `main.js` 가 보드 재렌더). 좁은 화면 세로 절약.
- 모바일 `.lane` 높이는 접힌 소식 막대 높이(`--m-notice`)를 빼서 하단 도트 띠를 안 침범.
- **만료(`expires_at` 지남)는 프론트에서도 필터**(백엔드 sweep 지연 대비). 정렬 date→time→id.
- 클래스는 `.ntc*` 네임스페이스(`#board` 와 충돌 방지). JP 제목은 시스템 JP 폰트 스택(웹폰트 안 씀).
- `poll` 마다 재호출되지만 `id+last_updated` 시그니처가 같으면 아무것도 안 하고 계속 돌린다.
- 로컬 개발: `fixtures/notices.sample.json` (만료일 2099 로 항상 표시). `config.js` URL 교체.

## 8. 관련 파일

- 백엔드: `src/backend/xnotice.py` · `notices.py` · `admin.py`(`pending_notice`, `set_undo(path=)`) ·
  `telegram_app.py`(`_apply_notice`/`_notice_sweep`/`_maybe_auto_notice`/`_handle_notice_*`,
  `_handle_undo_*` path 대응). self-test: `python -m src.backend.{xnotice,notices,admin,telegram_app}`.
- 프론트: `src/frontend/js/notices.js` · `css/notices.css` · `js/config.js`(`NOTICES_URL`) ·
  `js/main.js`(`pollNotices`) · `index.html`(`<section id="notice">`).
- data 브랜치: `notices.json` · `notice_archive.json`.

## 9. 남은 것

- 다이제스트 DM(하루 1회 요약)은 아직 — 지금은 건별 한 줄 DM(`added`/`updated`).
- 그룹 요약 알림은 필요해지면. (수동 수정 명령 `/notice-edit` 은 v2.7.x 에서 구현됨 — §5.)
