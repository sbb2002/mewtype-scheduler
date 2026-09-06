# v2.7 — 소식 게시판 (방송 외 이벤트)

작성 2026-09-07. v2.3(X 릴레이) 위에 얹는다. **아직 미구현 — 계획 + UI 시안만.**

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
- **펼치기(▾, 큰 화살표)**: 전체 소식 세로 목록, 아래 스케줄이 문서 흐름으로 밀려 내려감.
  **접으면 마지막 보던 소식부터** 순환 재개. 목록 하단에 `지난 소식 · 아카이브 →` 입구.
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

## 4. 데이터 계약 (초안)

### `notices.json` (data 브랜치 루트)

```jsonc
{
  "generated_at": "2026-09-07T...Z",
  "notices": [
    {
      "id": "2096552878769152326",       // 트윗 ID (Snowflake) = 고유키·중복제거·시간정렬
      "category": "live",                 // live | release | platform | etc
      "title": "「アワーノーツ」リリース日決定特番",
      "date": "2026-09-13",               // 기준 날짜 (JST). null 가능 → posted_at 로 대체
      "time": "21:00",                    // JST HH:MM. null 가능
      "deadline": false,                  // true 면 date 는 마감일("〜M/D")
      "site": "youtube",                  // youtube | bilibili | x | store | music | ...
      "url": "https://youtube.com/live/...",   // 이름 클릭 목적지. null 이면 tweet_url 사용
      "tweet_url": "https://x.com/i/status/2096552878769152326",
      "src_handle": "@BDP_yumemita",      // 출처 표시. 리포스트면 "RT @xxx"
      "posted_at": "2026-09-07T11:00:00Z",
      "expires_at": "2026-09-14T15:00:00Z"     // date/posted_at 의 JST 자정 → UTC
    }
  ]
}
```

### `notice_archive.json` — 위 항목 + `archived_at`, append-only, `id` dedupe.

## 5. 입력 경로 — `/notice` (수동 큐레이션 우선)

`/ingest` 2단계 흐름과 동일한 패턴. **자동 분류는 "후보 제안"까지만**, 게시는 운영자 확인.

- `/notice` (무인자) → `admin_state.json` `pending_notice` 슬롯 + 안내. 이어서 트윗 원문
  붙여넣기(또는 `/ingest` 릴레이 DM 을 그대로).
- 백엔드가 파싱 → 카테고리 추정(§6) + 날짜/시각/사이트/URL 추출 → **미리보기 DM**
  (`[카테고리] [D-DAY] 제목 / 사이트 / 링크`) + `y/N`.
- `y` → `notices.json` 머지. `n`/타임아웃 → 취소.
- `/notice-del <id|번호>` · `/notice-list` — `/del`·`/list` 재사용.
- (선택) 정기 `/ingest` 에서 스케줄 형식이 아니고 `looks_noticeable` 이면 "소식 후보?"
  DM 알림만 → 운영자가 `/notice` 로 승격.

## 6. 카테고리 추정 휴리스틱 (자동은 제안용)

`title`(=`android.title`, 게시자 표시 이름) + 본문 키워드:

- **출처 필터**: `title == "夢限大みゅーたいぷ"` 아니고 본문이 `@handle:`·`pic.x.com/` 로
  시작하면 리포스트 → `src_handle = "RT @..."`, 그래도 후보엔 올림.
- `platform`: 본문에 `bilibili`/`space.bilibili.com`/`ニコ生`/`ツイキャス`, 또는 `全員【…】`.
- `release`: `リリース`/`発売`/`配信開始`/`予約`/`受注`/`グッズ`/`CD`/`EP`.
- `live`: `配信決定`/`特番`/`生放送`/`○月○日` + YouTube URL (스케줄 트윗 아님).
- 그 외 → `etc`.

`全員【bilibili】` 등 v2.6 에서 `xrelay._SKIP_LINE_RE` 로 스킵하던 라인이 여기로 흡수됨.

## 7. 프론트

- `notices.json` 를 `schedule.json` 과 같은 주기로 fetch (`config.js` 에 URL 추가).
- `render.js` 에 티커 컴포넌트(목업의 접힘/펼침/순환/램프/marquee 로직). `#board` 위에 삽입.
- CSS: 목업의 `.board` 계열을 `css/` 에 추가. 예고판 토큰 재사용, 다크 단일.
- 만료(`expires_at` 지난 것)는 프론트에서도 숨김(백엔드 sweep 지연 대비).

## 8. 관련 파일 (구현 시)

- 백엔드: `src/backend/notices.py`(계약 헬퍼) · `xnotice.py`(파서/분류) ·
  `telegram_app.py`(`/notice` 흐름) · `admin.py`(`pending_notice` 슬롯) ·
  수명 sweep(정기 `/tick` 또는 telegram 서비스에서).
- 프론트: `src/frontend/js/render.js` · `js/config.js` · `css/`.
- data 브랜치: `notices.json` · `notice_archive.json`.
