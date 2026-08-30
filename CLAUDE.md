# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트

夢限大みゅーたいぷ(무겐다이 뮤타입) 소속 유튜브 방송인 5명의 **예약 방송·라이브 상태**를 취합해
보여주는 반응형 정적 웹사이트. 팬이 사이트에 방문하면 누가 언제 방송하는지, 지금 라이브 중인지,
어느 주소로 가면 되는지 한눈에 확인한다. 요구사항·설계 배경은 `PRD.md`, 모듈별 계약은
`docs/IMPLEMENTATION.md`, 인터뷰 원본은 `INTERVIEW*.md`.

서버 상시 가동 없음. 무료 인프라만 사용: **GitHub Actions**(수집) + **GitHub `data` 브랜치**(저장)
+ **Vercel**(정적 프론트).

## 저장소 구조

이 `mewtype-scheduler/` 폴더는 상위 `pyworks` 저장소 안에 **중첩된 별도 git 저장소**다
(`origin` = `github.com/sbb2002/mewtype-schduler` — 원격 레포명에 'e' 없음). 상위 `pyworks`와 무관하게 취급.

```
src/
  frontend/            # Vercel Root Directory = src/frontend, 빌드 없음
    index.html         # 빈 #board + #foot 스켈레톤, <script type="module">
    css/{reset,layout,card}.css
    js/                # ES 모듈, 상대 import
      config.js        # 상수 (DATA_URL, 폴링 주기, 폴백 채널 메타)
      time.js          # UTC→KST 포맷, 상대시간 라벨 — 순수 함수
      api.js           # fetchSchedule(): AbortController 타임아웃, {ok,data|error}
      render.js        # renderBoard / renderFooter / updateCountdowns
      main.js          # DOMContentLoaded → poll 루프 + 카운트다운 틱
  collector/           # python -m src.collector.main [light|deep]
    main.py            # 오케스트레이션
    config.py          # config/channels.json + YOUTUBE_API_KEY 로드
    rss.py             # 채널 RSS → videoId 발견 (쿼터 0)
    youtube.py         # YouTube Data API v3 (videos.list / search.list), VideoInfo
    reconcile.py       # 상태 판정 + 이전 스냅샷 대비 diff — 순수 함수
    store.py           # schedule.json / archive.json 로드·저장 (변경 시에만 기록)
config/channels.json   # 5채널 단일 소스 (channel_order, channel_id, handle, name, name_ko)
fixtures/              # schedule.sample.json(프론트/로직 공용), rss_arale.xml(파싱 테스트)
.github/workflows/collect.yml
data 브랜치             # schedule.json + archive.json 만. 코드 없음. Actions가 커밋
```

## 명령

```bash
# 수집기 로컬 실행 (API 키 필요)
pip install -r src/collector/requirements.txt          # requests 만
DATA_DIR=./_data YOUTUBE_API_KEY=xxxx python -m src.collector.main light   # 또는 deep
# PowerShell: $env:DATA_DIR="./_data"; $env:YOUTUBE_API_KEY="xxxx"; python -m src.collector.main light

# 모듈 self-test (네트워크 불필요)
python -m src.collector.rss          # fixtures/rss_arale.xml 파싱, 15개 assert
python -m src.collector.youtube      # _video_from_item 매핑 확인
python -m src.collector.reconcile    # build_schedule 시나리오 → count=2, ['ended','removed']

# 프론트 로컬 (저장소 루트에서 — fixture 상대경로 유지 위해)
python -m http.server 8099           # http://localhost:8099/src/frontend/
# 개발 중엔 src/frontend/js/config.js 의 DATA_URL 을 ../../fixtures/schedule.sample.json 으로 교체
```

테스트 프레임워크 없음. 각 collector 모듈의 `if __name__ == "__main__":` 블록이 스모크 테스트.

## 아키텍처 핵심

### 데이터 흐름
1. **GitHub Actions** (`collect.yml`, cron `0 * * * *`) 가 매시간 `python -m src.collector.main <mode>` 실행.
   `mode`는 JST 기준으로 결정 — 예고가 몰리는 JST 18:00~02:00 은 매시간 `deep`, 그 외는 대부분 `light`
   (JST 02·10·14시만 deep). 하루 deep 11회 ≈ 5,500 유닛 (한도 10,000).
2. 수집기가 `_data/`(= `data` 브랜치 체크아웃)에 `schedule.json`/`archive.json` 을 쓰고,
   **내용이 바뀐 경우에만** `data` 브랜치로 커밋·push (`GITHUB_TOKEN`, PAT 불필요).
3. **프론트**는 `raw.githubusercontent.com/.../data/schedule.json` 을 75초마다 fetch해 렌더.
   raw CDN 캐시로 최대 ~5분 지연 — 3시간 단위 방송 예고엔 문제 없음(의도된 트레이드오프, INTERVIEW #14).

### 수집 로직 (`main.py` → `reconcile.build_schedule`)
- **후보 집합** = RSS로 발견한 최근 videoId ∪ 이전 `schedule.json`의 미해결(upcoming/live) videoId
  ∪ (deep 모드면) `search.list?eventType=upcoming` 결과.
- `videos.list` 로 일괄 enrich → `snippet.liveBroadcastContent` 로 분기:
  `upcoming`/`live` 는 `schedule.json` 에 유지, `none` 은 이전에 추적 중이었으면 `archive.json` 으로
  이관(`ended`/`canceled`), 후보에서 아예 사라졌으면 `removed`.
- `schedule.json` 정렬: `live` 우선 → `scheduled_start` 오름차순.
- 시각은 전부 UTC ISO(`Z`)로 저장, KST 변환은 **프론트 `time.js` 담당**.

### 계약 (변경 시 `docs/IMPLEMENTATION.md` 먼저 수정)
- `schedule.json` / `archive.json` 스키마: IMPLEMENTATION §1, §2.
- 프론트 DOM 구조·class 이름: IMPLEMENTATION §3. `render.js` 가 생성하고 `css/` 가 스타일링.
  데이터는 `textContent`/`createElement` 로만 주입(XSS 방어), `innerHTML` 금지.
- 시간 표기 규칙(`formatKST`, `relativeLabel`): IMPLEMENTATION §4.

## 주의점

- **채널 추가/변경은 `config/channels.json` 한 곳만** 고치면 된다. `channel_url` 은 `@{handle}` 로 코드에서 파생.
- 준영구 "대기소/프리챗/굿즈안내" 프레임(예: `liveBroadcastContent=upcoming` 인데 `scheduled_start` 가
  1~2년 뒤)이 `schedule.json` 에 섞여 들어온다. 현재는 필터 없이 노출(보류 결정). 거를 거면 reconcile 단계에서.
- GitHub Actions 스케줄 cron 은 정각 보장 안 됨(3~15분, 드물게 1시간 지연/누락). 정밀 필요 시 Render cron.
- `date -u +%H` 는 `08`/`09` 를 8진수로 파싱하므로 산술 시 `$(( 10#$H ... ))` 필수 (`collect.yml` 참고).
- 코드 주석·문서·커밋 메시지는 한국어.
