# v2.4 — 합동방송(공동명의 채널) → 참여 멤버 레인 중복 노출

작성 2026-09-03. v2.3(X 예고 릴레이) 위에 얹는다.

프론트 배치 시안(3안 비교) 아티팩트: https://claude.ai/code/artifact/66a173f4-513d-4eae-b9f4-54251b50a957

---

## 0. 문제

`@BDP_yumemita` 일일 스케줄 트윗에 5인이 **공동명의(公式) 채널**에서 하는 합동방송이 섞여 온다.
실측(2026-09-03):

```
📺24:00〜 仲町あられ×宮永ののか
https://youtube.com/live/kx-nhmTj4Eg
```

이 방송은 멤버 5명 개인 채널 어디에도 안 속한다 → 지금 프론트에 **아예 안 뜬다**.
보드는 PC 5열 고정 그리드, 모바일 1레인 캐러셀이라 "6번째 레인"은 비용이 크다(특히 PC).

## 1. 결정 = C안 (참여 멤버 레인에 중복 노출)

합동 카드를 `channel_key` 하나가 아니라 **참여 멤버 전원**(`channel_key` ∪ `collab_with`) 레인에
같은 카드로 삽입. 자리·존(버킷/라이브)은 기존 그대로 재사용 → **PC·모바일 레이아웃 변경 0**.

대안 A(맨 앞 "공식" 레인) / B(그리드 위 풀블리드 밴드)는 아티팩트 §노트 참고. 그룹 채널 방송이
정기화되면 A로 승격(모바일 캐러셀은 레인 수 무관이라 거의 무비용, PC만 폭 재계산).

## 2. 계약 델타 (`schedule.json` scheduled 행, IMPLEMENTATION §1-1)

- **`host`** 필드 추가. `"group"` = 공동명의 채널 방송. 아니면 `null`.
- `url` — 기존 스키마에 있었으나 v2.4부터 collab 행에 **실제로 채운다**(트윗의 온전한 영상 URL).
- `collab_with` — 렌더 팬아웃의 근거. 참여자 = `[channel_key] + collab_with`.

## 3. 파서 (`src/backend/xrelay.py`)

- `YT_VIDEO_RE` — `youtube.com/(live/|watch?v=|shorts/)<11자>` + 뒤에 word char 없음.
  트윗에서 `…` 로 잘린 URL 은 링크가 깨지므로 **매치 안 함**(url=None).
- `_video_url_near(lines, idx)` — 엔트리 줄 바로 다음의 URL 줄에서 영상 URL 캡처. 다음 시각 줄이나
  헤더를 만나면 중단. `@handle` 채널 URL 은 대상 아님(정규식이 안 잡음).
- `line_has_collab`(= `collab_with` 있음 or `×` 있음) 이면 → `host="group"`, `url=<캡처값 or None>`.
- 심야표기(`24:00〜29:59` → 익일)·`頃`·`明日朝`·아이콘→kind 는 v2.3 그대로.
- self-test S5(실측 24:00 collab), S6(`watch?v=` 온전 URL) 추가.

## 4. reconcile (`src/collector/reconcile.py`)

- scheduled 보존 루프의 supersede 조건에 `and not prev_entry.get("host")` 가드.
  `host="group"` 행은 멤버 개인 채널 실물 `upcoming`/`live` 로 supersede 하지 않는다 —
  그룹 채널은 추적 5채널이 아니라 애초에 `_real` 에 안 들어오고, 우연히 같은 시각 멤버 방송이
  있어도 별개다. `expires_at` TTL 로만 소멸.
- `assumed_live` / TTL / 정렬은 v2.3 그대로. `collab_with`·`host`·`url` 은 `dict(prev_entry)` 로 이관.

## 5. 프론트 (`src/frontend/`)

- `render.js` `renderBoard` — broadcast 를 `channel_key` ∪ `collab_with` 전 레인에 push(팬아웃).
- `createCard(b, nowMs, channelData, laneKey)` — `laneKey` 인자 추가(합동 상대 표기용).
  - `isCollab = kind=="collab" || host=="group"` → class `card--collab`, href `= url || channel_url`.
  - 배지 "합동"(`card__badge--collab`), 라벨 "합동 · {참여자 − laneKey}", `host=="group"` 이면
    `.card__host` "공식 채널 합동방송" 한 줄.
  - `updateCountdowns` 는 기존 `.card--scheduled` 셀렉터로 커버(collab 도 이 class 유지).
- `card.css` — `.card--collab`(실선·바이올렛 좌측 inset bar·감광 완화), `.card__badge--collab`,
  `.card__host`. `layout.css` — `--color-collab: #8b7cc9` (live/sched/late 와 안 겹침).
- `fixtures/schedule.sample.json` — collab(arale×nonoka, host=group) + 일반 scheduled 행 추가.

## 6. 열린 것

- **그룹 채널 자체 메타**(handle/avatar/channel_id) 는 아직 없음. `url` 이 잡히면 링크는 정상.
  `url` 이 None(트윗 URL 잘림)이면 카드 링크가 `channel_url`(첫 참여자 채널) 로 폴백 — 부정확.
  → 그룹 채널 정보 확보되면 `config/channels.json` 에 `group` 항목 추가하고 폴백을 그쪽으로.
- 외부 이벤트/합방 공지(예: `watch?v=PAfMVT3GTLg`)가 **일일 스케줄 트윗에** `×`+영상 URL 형태로
  실리면 자동으로 같은 경로를 탄다. 별도 자유문 트윗이면 파서 B(v2.3 §3-2, 후속).
- 전원(5명) 참여 방송이면 5개 레인에 같은 카드 5장. 그 케이스만 B안(풀블리드) 특례가 나을 수 있음 — 보류.
