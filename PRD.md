# PRD — 夢限大みゅーたいぷ 방송 예고 스케줄러 (mewtype-schduler)

> 작성일: 2026-08-30
> 근거 인터뷰: `INTERVIEW.md`, `INTERVIEW_2nd.md`, `INTERVIEW_3rd.md`
> 레포: https://github.com/sbb2002/mewtype-schduler

---

## 1. 개요

**夢限大みゅーたいぷ**(무겐다이 뮤타입) 소속 유튜브 방송인 5명의 **예약 방송(예고)과 현재 라이브 상태**를
한곳에 취합해 보여주는 **반응형 정적 웹사이트**. 팬/시청자가 사이트에 방문하면 "누가 언제 방송하는지",
"지금 라이브 중인지", "어느 주소로 접속하면 되는지"를 한눈에 확인할 수 있다.

한 줄 정의: **5명의 유튜브 예약 방송을 시간순으로 정리해주는 방송 예고판.**

---

## 2. 목표 / 비목표

### 목표 (v1)
- 5개 채널의 **upcoming(예약) / live(방송중)** 방송을 자동 수집해 시간순으로 노출
- 방송 카드 클릭 시 해당 유튜브 영상/라이브로 이동
- 종료된 방송은 화면에서 자동 제거
- PC·모바일 모두에서 무리 없는 레이아웃
- 서버 상시 가동 없이 무료 인프라(GitHub Actions + Vercel)로 운영

### 비목표 (v1에서 하지 않음)
- 브라우저 푸시 / Discord 알림 / 이메일 알림 → 사용자가 방문해서 확인하는 방식
- 로그인 / 개인화 / 즐겨찾기
- 트위치·치지직 등 유튜브 외 플랫폼
- 커뮤니티 글 공지 파싱
- 아카이브/통계 열람 페이지 (단, 종료 데이터는 보관해 향후 가능성만 열어둠)
- 다국어 (한국어 단일)

---

## 3. 대상 사용자 & 시나리오

**대상:** 위 방송인들을 구독/시청하는 팬. 로그인 없이 URL 방문만으로 이용.

| # | 시나리오 |
|---|---|
| S1 | 사이트 접속 → 지금 라이브 중인 방송인이 있으면 상단에서 즉시 확인하고 클릭해 시청 |
| S2 | 각 방송인 레인에서 앞으로 예정된 방송을 가까운 시간순으로 확인 |
| S3 | 특정 방송 카드의 예정 시각(KST)과 남은 시간을 보고 일정을 계획 |
| S4 | 모바일에서 이동 중 빠르게 오늘/내일 방송 유무만 훑어봄 |

---

## 4. 모니터링 대상 채널

| key | 이름 | 표기(한글) | handle | channel_id |
|---|---|---|---|---|
| `arale` | 仲町あられ (Nakamachi Arale) | 나카마치 아라레 | `@arale_yumemita` | `UCWfF0DB6m_t2CE3KcOOOX7g` |
| `yuno` | 千石ユノ (Sengoku Yuno) | 센고쿠 유노 | `@yuno_yumemita` | `UC99kOG6_9RD0mR3OG4EOfxw` |
| `nonoka` | 宮永ののか (Miyanaga Nonoka) | 미야나가 노노카 | `@nonoka_yumemita` | `UCGeCnpimiSN5rgiKbJzHd3A` |
| `ritsu` | 峰月律 (Minetsuki Ritsu) | 미네츠키 리츠 | `@ritsu_yumemita` | `UCxc0MrPoACKTFlV24GqX2sg` |
| `miyako` | 藤都子 (Fuji Miyako) | 후지 미야코 | `@miyako_yumemita` | `UCZXxRYaP7mfuglPnptnBBCA` |

레인 표시 순서는 설정값으로 두되 기본은 위 표 순서. (UI.png 시안과 순서가 다르므로 구현 시 최종 확정)

---

## 5. 아키텍처

```
┌─────────────────────┐   1h cron    ┌──────────────────────────────┐
│  GitHub Actions      │ ───────────▶ │ collector (Python)           │
│  (schedule cron)     │              │  - RSS 5채널 신규 videoId 발견 │
└─────────────────────┘              │  - YouTube Data API v3 enrich │
                                     │  - 상태 판정 / diff           │
                                     └──────────────┬───────────────┘
                                                    │ git commit (변경 시에만)
                                                    ▼
                                     ┌──────────────────────────────┐
                                     │ GitHub  `data` 브랜치         │
                                     │  schedule.json  (upcoming/live)│
                                     │  archive.json   (ended 누적)   │
                                     └──────────────┬───────────────┘
                                                    │ raw.githubusercontent.com fetch
                                                    ▼
┌─────────────────────┐             ┌──────────────────────────────┐
│ Vercel (main 브랜치) │ ──静的配信─▶ │ 브라우저: 바닐라 HTML/CSS/JS   │
│  index.html + assets │             │  - 5레인 렌더 / KST 변환       │
└─────────────────────┘             │  - 60~90s 주기 폴링 & 재렌더   │
                                    └──────────────────────────────┘
```

### 구성요소 결정 (인터뷰 확정)
| 항목 | 결정 | 비고 |
|---|---|---|
| 수집기 실행 | **GitHub Actions cron** | Render 미사용. 지연 이슈는 주기 실행이라 무시 가능. 문제 시 Render cron 재검토 |
| 데이터 저장소 | **GitHub `data` 브랜치** | `schedule.json`(현재분) + 별도 파일로 종료분 보관 |
| 프론트 데이터 읽기 | **런타임 `raw.githubusercontent.com` fetch** | 빌드 훅 없음 |
| 프론트 스택 | **바닐라 HTML/CSS/JS** | 규모상 React/Next 이점 미미. 반응형은 bandori-song-sorter 수준으로 신경 |
| 프론트 호스팅 | **Vercel** (`main` 브랜치) | |
| 과거 데이터 | `archive.json`에 append 보관 | v1 UI에서는 미노출 |

---

## 6. 데이터 수집 명세

### 6.1 RSS로 가능/불가능한 것 (2026-08-30 실측)

| 항목 | RSS(`/feeds/videos.xml?channel_id=`) |
|---|---|
| videoId, 제목, 채널명, 썸네일 URL, 설명, `published`/`updated` | ✅ |
| 예약 라이브 시작 시각 (`scheduledStartTime`) | ❌ 없음 |
| 라이브 상태(upcoming/live/none) | ❌ 없음 |
| 예약된 미래 방송 노출 | ❌ 최근 15개 **공개 영상**만. 예약 스트림은 미노출/무표식 |

→ **RSS 단독 불가.** RSS는 "최근 신규 videoId 저비용 발견" 용도로만 쓰고, 상태·시각은 **YouTube Data API v3**로 확정한다.

### 6.2 수집 사이클 (2단계)

**(A) 라이트 싱크 — 매시간(cron `0 * * * *`)**
1. 5채널 RSS 피드에서 최근 videoId(최대 15개/채널) 수집
2. `data` 브랜치의 현재 `schedule.json`에서 **아직 미해결(upcoming/live)인 videoId** 전부 수집
3. `후보 = (RSS 발견분) ∪ (미해결 추적분)`
4. `GET videos.list?part=snippet,liveStreamingDetails&id=<=50` 로 후보를 50개씩 배치 조회
5. 각 결과 상태 판정:
   - `snippet.liveBroadcastContent == "upcoming"` → **upcoming**, `liveStreamingDetails.scheduledStartTime` 저장
   - `== "live"` → **live**, `actualStartTime`, `concurrentViewers` 저장
   - `== "none"`:
     - 이전에 upcoming/live로 추적 중이었고 `actualEndTime` 존재 → **ended** 로 전이 (→ archive)
     - 그 외 → 일반 VOD/쇼츠로 간주, 무시
6. `schedule.json` 재생성(upcoming + live 만), 신규 ended는 `archive.json`에 dedupe append
7. 내용이 바뀐 경우에만 `data` 브랜치에 커밋

**(B) 딥 스캔 — 6시간마다(cron `0 */6 * * *`)**
- 채널별 `GET search.list?channelId=&eventType=upcoming&type=video&part=id` 로 **먼 미래 예약분**까지 발견
- 발견된 videoId를 (A)의 후보 집합에 합류시켜 동일하게 enrich
- 라이트 싱크만으로는 RSS 15개 창 밖에 있는 장기 예약을 놓칠 수 있으므로 이를 보완

### 6.3 쿼터 예산 (한도 10,000 units/day)

| 작업 | 단가 | 횟수/일 | 소계 |
|---|---|---|---|
| 라이트 싱크 `videos.list` (배치 2회 가정) | 1 | 24 × 2 | 48 |
| 딥 스캔 `search.list` (5채널) | 100 | 4 × 5 | 2,000 |
| 딥 스캔 `videos.list` 추가 배치 | 1 | 4 × 2 | 8 |
| **합계** | | | **≈ 2,056 / day** |

여유 충분. 필요 시 라이트 싱크를 30분 주기로 올려도 안전.

### 6.4 실패 처리
- API 호출 실패/쿼터 초과: 이번 사이클 스킵, 기존 `schedule.json` 유지, Actions 로그에 경고. 커밋하지 않음
- RSS 일부 채널 실패: 성공한 채널만 갱신, 실패 채널의 기존 데이터 보존
- `videos.list` 응답에 특정 id 누락(삭제/비공개): 해당 방송을 `schedule.json`에서 제거하고 archive에 `removed` 사유로 기록
- 커밋 충돌: rebase 후 재시도 1회, 실패 시 다음 사이클로

---

## 7. 데이터 모델 (`data` 브랜치)

시각은 모두 **UTC ISO 8601**로 저장하고, 표시 변환은 프론트가 담당.

### 7.1 `schedule.json` (현재 유효분만, 매 사이클 덮어씀)

```json
{
  "generated_at": "2026-08-30T12:00:00Z",
  "channels": {
    "arale":  { "name": "仲町あられ -Nakamachi Arale-", "name_ko": "나카마치 아라레",
                "channel_id": "UCWfF0DB6m_t2CE3KcOOOX7g", "handle": "arale_yumemita",
                "channel_url": "https://www.youtube.com/@arale_yumemita" },
    "yuno":   { "...": "..." },
    "nonoka": { "...": "..." },
    "ritsu":  { "...": "..." },
    "miyako": { "...": "..." }
  },
  "broadcasts": [
    {
      "video_id": "h31Mi6AS7a0",
      "channel_key": "arale",
      "title": "【歌枠】まったりお歌〜",
      "url": "https://www.youtube.com/watch?v=h31Mi6AS7a0",
      "thumbnail": "https://i.ytimg.com/vi/h31Mi6AS7a0/hqdefault.jpg",
      "status": "upcoming",
      "scheduled_start": "2026-08-31T11:00:00Z",
      "actual_start": null,
      "concurrent_viewers": null,
      "first_seen": "2026-08-30T09:00:00Z",
      "last_updated": "2026-08-30T12:00:00Z"
    }
  ]
}
```

- `status`: `upcoming` | `live`
- `broadcasts` 정렬은 프론트 책임이지만, 생성 시 `live` 우선 → `scheduled_start` 오름차순으로 정렬해 두면 디버깅 편의

### 7.2 `archive.json` (종료분 누적, append-only)

```json
{
  "updated_at": "2026-08-30T12:00:00Z",
  "broadcasts": [
    {
      "video_id": "MGVRS_MYXSw",
      "channel_key": "arale",
      "title": "【夜間警備】後編",
      "url": "https://www.youtube.com/watch?v=MGVRS_MYXSw",
      "thumbnail": "https://i.ytimg.com/vi/MGVRS_MYXSw/hqdefault.jpg",
      "status": "ended",
      "scheduled_start": "2026-08-29T15:00:00Z",
      "actual_start": "2026-08-29T15:03:00Z",
      "actual_end": "2026-08-29T17:20:00Z",
      "archived_at": "2026-08-30T12:00:00Z",
      "reason": "ended"
    }
  ]
}
```

- `reason`: `ended` | `removed`(삭제/비공개) | `canceled`(예약 취소로 none 전이 & 종료시각 없음)
- v1 프론트는 이 파일을 읽지 않음. 파일 비대화 시 연도별 분할(`archive-2026.json`)은 향후 과제

---

## 8. 프론트엔드 명세

### 8.1 레이아웃 (UI.png 기준)

- 화면을 **방송인 5명의 세로 레인(column)** 으로 분할
- 각 레인 상단: **헤더** (방송인 한글명 / 원어명, 채널 링크)
- 헤더 아래 **라이브 영역**: 해당 방송인이 지금 `live`면 강조 카드 1개(빨강 계열 뱃지 "LIVE", 시청자수 옵션)
- 그 아래 **예정 목록**: `upcoming` 카드들을 **남은 시간 오름차순**으로 세로 나열
- 카드 구성: 썸네일 / 제목(2줄 말줄임) / 예정 시각(KST, 예 `08/31 20:00`) + 상대 시간(`3시간 후`, `내일`, `2일 후`)
- 카드/헤더 클릭 → 해당 유튜브 URL 새 탭

### 8.2 상태·정렬 규칙
- 표시 상태는 **`upcoming` / `live` 만**. `ended`·아카이브는 미표시
- 레인 내 순서: `live`(있으면 최상단) → `upcoming` `scheduled_start` 오름차순
- 시각 표시: JSON의 UTC → **KST(UTC+9)** 로 변환해 렌더 (일본 방송인이라 JST=KST로 숫자 동일)
- 빈 레인: "예정된 방송이 없어요" 플레이스홀더 표시

### 8.3 갱신
- 페이지 로드 시 `schedule.json` fetch
- 이후 **60~90초 주기**로 재fetch → 변경 시 재렌더 (라이브 전환/시청자수/카운트다운 갱신)
- 카운트다운 텍스트는 클라이언트 타이머로 1분마다 자체 갱신 (fetch 없이)
- fetch 실패 시 직전 데이터 유지 + 조용한 재시도 (사용자에게 에러 강조 X, 작은 "업데이트 지연" 표시 정도)

### 8.4 반응형
- 데스크톱(≥1100px): 5레인 균등 그리드
- 태블릿/좁은 화면: 레인 최소 너비 유지 + **가로 스크롤** (레인 구조 보존) — 기본안
  - 대안(디자인 단계 확정): 3→2→1 컬럼으로 접기 + 방송인 탭 전환
- 모바일: 카드 썸네일 축소, 터치 타깃 44px 이상
- 초경량: 외부 프레임워크 없음, 폰트/이미지 최소화, 썸네일은 `loading="lazy"`

### 8.5 접근성/기타
- 라이브 뱃지는 색 + 텍스트 병기(색맹 대응)
- `<time datetime>` 사용
- 다크/라이트: v1은 단일 테마로 시작(디자인에서 결정), 시스템 다크 대응은 선택

---

## 9. 비기능 요구사항

| 항목 | 요구 |
|---|---|
| 성능 | 첫 콘텐츠 표시 < 1.5s(3G Fast 기준), JS 번들 < 50KB gzip 목표 |
| 데이터 신선도 | 예정 방송 반영 지연 ≤ 1시간(라이트 싱크 주기), 라이브 시작 반영 지연 ≤ 1시간 (허용) |
| 가용성 | 정적 호스팅 + GitHub raw. 수집기 다운 시에도 마지막 스냅샷은 계속 서빙됨 |
| 비용 | $0 (GitHub Actions 무료분 + Vercel Hobby + YouTube 무료 쿼터) |
| 보안 | 프론트에 API 키 노출 금지. `YOUTUBE_API_KEY`는 GitHub Actions Secret |
| 라이선스/이용약관 | YouTube 썸네일 핫링크(`i.ytimg.com`), 데이터는 공개 메타데이터만 |

---

## 10. 저장소 구조 (예정)

```
main 브랜치
├── index.html
├── css/…                 # 레이아웃, 카드, 반응형
├── js/…                  # fetch, KST 변환, 렌더, 폴링
├── assets/               # 로고/아이콘(선택)
├── .github/workflows/
│   └── collect.yml       # cron: 라이트 싱크 + 딥 스캔
├── collector/
│   ├── main.py           # 엔트리
│   ├── rss.py            # RSS 파싱(신규 videoId 발견)
│   ├── youtube.py        # videos.list / search.list 래퍼
│   ├── reconcile.py      # 상태 판정 & diff & schedule/archive 갱신
│   └── requirements.txt
├── config/
│   └── channels.json     # 5채널 메타(단일 소스)
├── PRD.md
└── INTERVIEW*.md

data 브랜치 (Actions가 커밋, 코드 없음)
├── schedule.json
└── archive.json
```

Actions 워크플로는 `main`의 `collector/`를 체크아웃해 실행하고, 산출물만 `data` 브랜치에 push.

---

## 11. 엣지 케이스

| 상황 | 처리 |
|---|---|
| 장기(2주+) 예약이 RSS 15개 창 밖 | 딥 스캔(`search.list eventType=upcoming`)이 커버 |
| 예약 방송이 취소됨(`upcoming`→`none`, 종료시각 없음) | `schedule.json`에서 제거, archive에 `reason: canceled` |
| 예약 시각이 변경됨 | 매 사이클 `scheduledStartTime` 갱신 → `last_updated` 갱신 |
| 프리미어(Premiere) 영상 | `liveBroadcastContent`가 `upcoming`/`live`로 오므로 자연히 포함됨. v1에서 별도 구분 안 함(원하면 `is_premiere` 플래그 추후) |
| 라이브가 비정상 종료(크래시 후 재시작) | 같은 video_id면 상태만 갱신. 새 video_id면 새 카드 |
| 동시에 2개 라이브(예: 콜라보 + 개인) | 라이브 영역에 복수 카드 허용 |
| 썸네일 404 | 프론트에서 `onerror` 시 `hqdefault`→`mqdefault` 폴백, 그래도 없으면 회색 플레이스홀더 |
| 채널 핸들/ID 변경 | `config/channels.json` 수정으로 대응 |

---

## 12. 마일스톤

| 단계 | 산출물 |
|---|---|
| M1 — 수집기 코어 | `collector/` 로컬 실행으로 `schedule.json`/`archive.json` 생성 검증 (API 키 필요) |
| M2 — Actions 연동 | `collect.yml` cron 동작, `data` 브랜치 자동 커밋, Secret 설정 |
| M3 — 프론트 정적 | `index.html` + JS로 `schedule.json` 렌더, 5레인/라이브/정렬/KST/카운트다운 |
| M4 — 반응형 & 폴리시 | 모바일 레이아웃, 빈 상태, fetch 실패 처리, 썸네일 폴백 |
| M5 — 배포 | Vercel `main` 연결, 도메인(선택), 실데이터로 1일 관찰 |
| 이후 | 알림(Discord webhook), 아카이브 페이지, 다크모드, i18n |

---

## 13. 확정 필요/열린 질문

1. 레인 표시 순서 최종 확정 (INTERVIEW 순서 vs UI.png 순서)
2. 좁은 화면 전략: 가로 스크롤 유지 vs 컬럼 접기+탭 — 디자인 단계에서 결정
3. 라이트 싱크 주기: 60분 확정? (쿼터상 30분도 가능)
4. `YOUTUBE_API_KEY` 발급 주체/계정 (사용자 제공 예정)
5. Vercel/도메인 정보 (사용자: "필요해지면 제공")
6. 단일 테마 색상/로고 등 비주얼 방향
