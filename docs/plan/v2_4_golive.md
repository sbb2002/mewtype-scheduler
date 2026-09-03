# X 릴레이 실배포 전환 런북 (v2.4)

다른 세션이 "이제 실제로 반영되게 켜자" 를 할 때 이 문서대로.
현행 전체 흐름 그림: `docs/plan/v2_4_flow.png` (생성기 `gen_v2_4.py`).

---

## 0. 지금 상태 (2026-09-03 기준)

- `mewtype-telegram` = **테스트 모드**. env `INGEST_ECHO=1`, `INGEST_DRY_RUN=1`.
  - `/ingest` 는 파싱·저장을 안 한다. 받은 텍스트를 DM 으로 돌려주고(`말미문구 ✅/❌`),
    `ingest ECHO: len=.. clen=.. tail_ok=..` 로그를 남기고, 스케줄 트윗이면
    `data` 브랜치 `ingest_queue.json` 에 원문을 적재한다.
- `mewtype-backend` = `-00013` (v2.3+v2.4 `reconcile`). 정기 `/tick` 은 이미 v2.4 로직.
- 프론트(Vercel) = `main` 자동배포됨. `.card--scheduled` / `.card--collab` 코드 있음.
  단 `schedule.json` 에 그런 행이 없어 화면 변화는 아직 없음.
- **아직 프로덕션 `schedule.json` 엔 X 릴레이 유래 행이 하나도 없다.**

## 1. 전환 전 확인 — 웹푸시 잘림 (#1)

폰(Automate)이 삼성 브라우저 웹푸시 알림을 relay 할 때 본문이 "Show more" 로
잘리는지 미확인. 실물 `@BDP_yumemita` 「配信スケジュール」 트윗이 한 번 와서
ECHO 를 타면 판정:

```bash
gcloud logging read \
  'resource.labels.service_name="mewtype-telegram" AND textPayload:"ingest ECHO"' \
  --limit 5 --format='value(timestamp,textPayload)'
```

- `tail_ok=True` → 말미 고정문구(`※時刻は予告なく変更…`)까지 도착 = **안 잘림**. 전환 진행.
- `tail_ok=False` → 잘림. 전환 전에 `xrelay.merge_scheduled` 에 부분 upsert 가드
  추가 (그 함수 상단 `# ponytail:` 주석 위치). 안 그러면 잘린 트윗이 그 날짜의
  온전한 기존 행을 덮어써서 엔트리가 사라진다.
- 트윗이 안 와서 판정 못 해도 전환은 가능하다 — 큐/merge 가 replace-by-date 라
  다음 온전한 트윗이 오면 자동 교체되고, 최악의 경우 하루치가 부분 노출될 뿐이다.

## 2. 전환

```bash
gcloud run services update mewtype-telegram --region asia-northeast1 \
  --update-env-vars INGEST_ECHO=0,INGEST_DRY_RUN=0
```

env 만 바꾸므로 재빌드 없음(새 리비전 1개). 코드 배포가 필요하면
`INGEST_ECHO=0 INGEST_DRY_RUN=0 bash deploy/deploy_telegram.sh` (env.sh 에
두 값이 없으므로 export 로 넘겨야 함 — `deploy_telegram.sh` 는 `${...:-0}`).

## 3. 전환 직후 동작

전환 후 **첫 `/ingest`** (폰 트윗이든, 아래 수동 트리거든) 에서:

1. `control.json` `paused` 확인 (paused 면 스킵).
2. `_ingest_queue_drain` — `ingest_queue.json` 의 원문을 `received_at` 순서대로
   `xrelay.parse_bdp_schedule` → `merge_scheduled`. 큐를 비운다.
3. 이번 요청 본문도 파싱·머지.
4. 요약 DM 에 `📥 대기열 N건(M행) 반영` 표기.

→ 테스트 기간에 폰에서 온 트윗이 유실 없이 반영된다.
빈 큐면 drain 은 즉시 no-op (읽기 1회).

수동으로 큐만 먼저 흘리고 싶으면 아무 스케줄 트윗이나 재전송:

```bash
SECRET=$(gcloud secrets versions access latest --secret=INGEST_SECRET)
curl -sS -X POST https://mewtype-telegram-376735243718.asia-northeast1.run.app/ingest \
  -H "X-Ingest-Secret: $SECRET" --data-urlencode "text@<트윗원문파일>"
```

## 4. 검증

```bash
# schedule.json 에 scheduled / collab 행이 들어갔나
curl -s "https://raw.githubusercontent.com/sbb2002/mewtype-scheduler/data/schedule.json" \
  | python -c "import sys,json; b=json.load(sys.stdin)['broadcasts']; \
      print([(x['channel_key'], x.get('status'), x.get('kind'), x.get('host')) \
             for x in b if x.get('status')=='scheduled'])"
```

- 프론트: 예고 카드(`.card--scheduled`) / 합동 카드(`.card--collab`, 참여 멤버
  전원 레인)가 뜨는지. raw CDN 캐시로 최대 ~5분 지연.
- 정기 `/tick` 후 `reconcile` 이 실물 `upcoming` supersede / `expires_at` 정리
  하는지 (`host="group"` 행은 멤버 실물로 supersede 안 됨 — TTL 로만).

## 5. 롤백

```bash
gcloud run services update mewtype-telegram --region asia-northeast1 \
  --update-env-vars INGEST_ECHO=1,INGEST_DRY_RUN=1
```

이미 `schedule.json` 에 쓰인 행은 그대로 남는다. 지우려면:
- 잠깐 기다리면 `expires_at`(start+3~5h) 지나며 다음 `/tick` 이 제거, 또는
- `data` 브랜치 `schedule.json` 에서 해당 `broadcasts[]` 항목 직접 삭제 커밋.

## 6. 관련 파일

| | |
|---|---|
| 파서·머지 | `src/backend/xrelay.py` (`parse_bdp_schedule`, `merge_scheduled`) |
| `/ingest`·큐 | `src/backend/telegram_app.py` (`_ingest_queue_push/_drain`, `_merge_rows_into_schedule`) |
| 보존·정리 | `src/collector/reconcile.py` (`build_schedule` scheduled 블록) |
| 프론트 | `src/frontend/js/render.js` (`createCard` scheduled/collab, `renderBoard` 팬아웃), `css/card.css` |
| 계약 | `docs/IMPLEMENTATION.md` §1-1 (scheduled 행 스키마, `host` 필드) |
| 설계 | `docs/plan/v2_3_x_relay.md` (X 릴레이), `docs/plan/v2_4_collab.md` (합동방송) |
| env | `deploy/deploy_telegram.sh` (`INGEST_ECHO` / `INGEST_DRY_RUN` = `${...:-0}`) |
