# 접수 서비스(mewtype-telegram) 인스턴스 상한 — 구현 명세 (2026-10-28 작성, 미구현)

> **검토 코멘트 (2026-10-28, Claude — 코드 · 운영 설정 대조) · 운영자 결정: 별도 패치 안 함(보류)**
>
> - **시급하지 않음.** 운영 서비스에는 이미 상한이 있다 — `gcloud run services describe mewtype-telegram` 결과
>   `autoscaling.knative.dev/maxScale=20`(배포 스크립트엔 플래그가 없지만 실제 설정엔 걸려 있음). 아래 「현황」의
>   "상한 사실상 높음"은 스크립트만 보고 쓴 서술이라 **틀렸다** — 이 명세를 적용하면 20 → 5 로 줄이는 것이다.
>   비싼 경로는 이미 인증 뒤에 있다: `/ingest`(비밀 헤더, 403) · `/telegram`(시크릿 + chat_id) · `/websub`(HMAC 서명, 상수 시간 비교) · `/gap-*`(OIDC) · `/admin`(HMAC 토큰 + 1회용 nonce).
> - **용량 계산 근거가 틀렸다.** 「5 × 4 스레드 = 동시 처리 20」이 아니라, concurrency 80 이면 인스턴스가 80개까지 받아 안에서 대기시키므로
>   429 는 처리 중 요청이 약 400(5 × 80)을 넘어야 난다. 오토스케일러는 CPU · 동시 요청 수로 늘리므로, 대기 시간 위주인 `/ingest` 는
>   인스턴스를 거의 늘리지 않는다. → 정상 부하에서 429 위험은 명세보다 더 낮지만 「3 은 빠듯」 근거는 성립하지 않는다.
> - **남은 위험(이 명세로는 못 막음 · 이번에도 손대지 않음):** 「인증 실패는 싸게 거절하므로 남은 위험은 인스턴스 수뿐」 전제가 맞지 않는다.
>   `GET /monitor-live/day.json?date=` (`telegram_app.py` `_monitor_live_day_json` → `_monitor_past_day`)는 인증 없이 공개이고, 오늘 이전이면 어떤 날짜든 받는다.
>   처음 보는 날짜마다 GitHub Contents API 를 여러 번(스냅샷 · 이벤트 로그 · 보관함) 부르고, 스냅샷이 없으면 Vercel · healthchecks 조회까지 한다.
>   캐시는 64칸에 꽉 차면 오래된 것부터 버린다(`_MONITOR_DAY_CACHE_MAX`). GitHub 토큰(PAT)은 두 서비스가 같이 쓰므로(`deploy.sh` · `deploy_telegram.sh` 의 `GITHUB_TOKEN`)
>   날짜를 바꿔 가며 계속 부르면 시간당 5000회 한도가 바닥나 쓰기 서비스(`/tick` · `/write`)도 멈춘다 — 인스턴스 1개로도 가능해서 `max-instances` 와 무관.
>   막는다면: 날짜 범위를 운영 시작일 ~ 어제로 제한 + 스냅샷 없는 날짜의 즉석 계산 금지(또는 결과를 길게 캐시). `/monitor-live` · `.json` 은 60초 캐시라 해당 없음.
> - 코드 밖 **예산 알림**(아래 「예산 알림」)은 패치와 별개로 걸어 둘 만하다.
> - 유지보수성 자체는 문제없음(한 줄 · env 로 덮어쓰기 · 롤백 · 문서 계획). 롤백 `--max-instances=default` 철자는 적용할 때 `--help` 로 확인.

## 목적
공개 서비스(`--allow-unauthenticated`)에 틀린 요청이 대량으로 쏟아져도 **Cloud Run 비용 · 자원이 무한히 늘지 않게** 상한을 둔다.
인증 실패(403)는 이미 싸게 거절하므로, 남은 위험은 "인스턴스 수 무제한 증가"뿐이다. 정상 동작은 조금도 느려지면 안 된다.

## 현황 (코드로 확인함)
- 쓰기 서비스 `mewtype-backend`: `deploy/deploy.sh` 에 `--concurrency=1 --max-instances=1` — **이미 있음, 손대지 않는다**.
- 접수 서비스 `mewtype-telegram`: `deploy/deploy_telegram.sh` 의 `gcloud run deploy` 에 `--max-instances` · `--concurrency` · `--min-instances` **모두 없음** (Cloud Run 기본값 = 상한 사실상 높음, concurrency 80).
- 컨테이너: `gunicorn --workers=1 --threads=4 --timeout=240` → 한 인스턴스가 동시에 처리하는 요청은 사실상 **4개**, 나머지는 인스턴스 안에서 대기한다.
- 이 서비스가 받는 것: 폰 `/ingest`(LLM · OCR · vxtwitter 호출로 수 초~수십 초), 텔레그램 webhook, WebSub 콜백(큐 경유), `/admin`, `/monitor-live`, `/gap-check`(매분), `/gap-fill`(Cloud Tasks 동시 1).
- 다중 인스턴스 안전성: 관리 로그인 nonce 는 ops 저장소(`admin_nonces.json`)에 있어 인스턴스가 여러 개여도 1회용이 지켜진다. 콘텐츠 쓰기는 백엔드 `/write` 한 곳이라 접수 서비스 인스턴스 수와 무관.

## 결정할 값: `--max-instances=5`
- 근거: 정상 부하는 대부분 인스턴스 1개(많아야 2). 상한 5 = 최대 동시 처리 약 20(5×4 스레드)으로 정상 폭주(멤버·공식 계정 글이 몇 분 안에 겹쳐 오는 경우)의 몇 배 여유가 있다.
  3 은 겹침 시 여유가 빠듯하고, 10 이상은 폭주 때 비용 상한 효과가 약하다.
- **확정 전 실측 1회**(구현 세션이 할 일): Cloud Monitoring `run.googleapis.com/container/instance_count`(서비스 `mewtype-telegram`, 최근 30일, 최대값)를 본다.
  - 최대 ≤ 2 → 5 확정.
  - 최대 3~4 → `max(5, 최대 × 2)` 로 올려 확정.
  - 확인이 어려우면 5 로 두고 아래 「배포 후 관찰」 항목으로 보완.
- `--concurrency` 는 **건드리지 않는다**(기본 80 유지). 낮추면 상한 도달 전에 429 가 나서 오히려 정상 요청이 거부된다. 4 스레드를 넘는 요청은 인스턴스 안에서 대기(기존과 같은 동작).
- `--min-instances` 도 건드리지 않는다(0 유지 — 비용 · 기존 콜드스타트 특성 그대로).

## 변경 내용
1. `deploy/deploy_telegram.sh` 의 `gcloud run deploy "$TELEGRAM_SERVICE"` 에 `--max-instances=${TELEGRAM_MAX_INSTANCES:-5} \` 한 줄 추가. 주석에 값의 근거(위 요약)와 「쓰기 서비스는 직렬화를 위해 1, 이쪽은 비용 상한용」 명시.
2. `deploy/README.md` 에 한 줄(접수 서비스는 상한 5, 이유).
3. 스테이징(`STAGE=1`) 은 같은 스크립트를 쓰므로 별도 처리 불필요(환경 변수로 덮어쓸 수 있음).
4. `docs/SPEC.md` §12(인프라) 에 접수 서비스 `max-instances` 한 줄. `docs/VERSION.md` 버전 항목 — 등급은 **일반 패치**(인프라 설정값 1개, 새 요소 없음).

## 적용 방법 (두 가지, 이미지 재빌드 불필요한 쪽 권장)
- 즉시 적용(코드 변경 없이): `gcloud run services update mewtype-telegram --region asia-northeast1 --max-instances=5` — 새 리비전만 만들고 이미지는 그대로.
- 스크립트 반영본은 다음 정식 배포 때 같이 나간다. 두 서비스 공통 코드를 바꾸는 게 아니므로 `deploy.sh`(쓰기 서비스)는 재배포하지 않는다.
- 배포 · 병합은 운영자 결정 — 구현 세션은 PR 까지만, 적용은 지시를 받고 한다. KST 05:50~06:30 는 daily 잡 시간대라 피한다.

## 느려지거나 깨질 수 있는 시나리오와 대비
| 시나리오 | 영향 | 대비 |
|---|---|---|
| 정상 부하가 5 인스턴스를 넘는다 | 초과 요청에 429 | 실측으로 거의 없음을 확인 후 적용. 발생 시 값 상향 |
| 폰 `/ingest` 가 429 를 받음 | 그 알림 1건 유실 가능(Automate 재시도 여부는 확인 필요) | 빠진 X 글은 `/gap-check` 가 1분마다 보충(계약 I). YouTube 알림은 10분 RSS 폴링이 안전망(`WEBSUB_REPLACE_RSS=0`) — 이 값이 1 로 바뀌었다면 이 대비가 약해지므로 먼저 확인 |
| Cloud Tasks(WebSub · gapfill) 요청이 429 | 큐가 자동 재시도(3~4회) | 추가 조치 없음 |
| `/gap-check` (Scheduler 매분) 429 | 다음 분에 재시도되는 구조 | 없음 |
| 콜드스타트 | 변화 없음(min-instances 불변) | — |
| 쓰기 서비스 영향 | 없음(접수 서비스 설정만 바뀜) | — |

## 예산 알림 (코드 밖, 운영자 콘솔 작업)
- GCP 결제 > 예산 및 알림에서 월 예산 하나 생성(금액은 운영자가 정함 — 무료 한도 안에서 운영 중이면 낮게), 50% · 90% · 100% 알림을 이메일로.
- 상한 5 가 있으면 폭주 시 최악 비용도 유한하다 — 이 둘은 함께 쓴다.

## 검증 절차 (적용 후)
1. `gcloud run services describe mewtype-telegram --region asia-northeast1 --format='value(spec.template.metadata.annotations)'` 에서 `autoscaling.knative.dev/maxScale: '5'` 확인.
2. 텔레그램 `/status` 응답, `/admin` 로그인, 관리 페이지 열기 — 정상.
3. 폰 알림 1건(또는 `INGEST_DRY_RUN`) 이 정상 접수되는지 모니터 로그로 확인.
4. 적용 후 24시간 Cloud Run 로그에서 429(요청 거부) 건수를 본다 — 0 이어야 한다. 있으면 상한을 올린다.

## 롤백
`gcloud run services update mewtype-telegram --region asia-northeast1 --max-instances=default`(기본값 복귀 — 옵션 철자는 구현 시 `gcloud run services update --help` 로 확인) 또는 직전 리비전으로 트래픽 이동.

## 하지 않는 것
- 쓰기 서비스 설정 변경, `--concurrency` 변경, `--min-instances` 도입, Cloud Armor · WAF 도입(과금 서비스 반려 원칙 — 메모리 「유료 서비스 반려」).
