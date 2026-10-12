# 에러 버스 규약 (BUS_PROTOCOL) — v4.3-fullauto

> 브랜치 `v4.3-fullauto` 전용 실험 문서 (2026-10-12). `main` 에는 아직 반영되지 않았다.
> **발신기**(로그를 내보내는 쪽)와 **수신기**(받아서 분석·대응하는 쪽)가 **서로의 코드를 몰라도** 이 문서와
> `docs/bus/schema/*.json` 만으로 통신할 수 있게 하는 계약이다. 두 쪽은 별도 세션에서 만들어도 된다.
> 용어는 `docs/TERMINOLOGY.md` 「에러 버스 용어」 기준.

## 0. 한눈에

```
[발신기: 러너]  ──mew.err/1──▶  err/inbox ─▶ processing ─▶ done | dead   [수신기]
      ▲                                                                       │
      └──────────────── mew.ctl/1 (ctl/inbox) ◀───────────────────────────────┤
                                       hb/publisher.json · hb/receiver.json   │
                                       report/inbox ◀──── mew.report/1 ───────┘
```

- 전송 수단: 지금은 **폴더 스풀**(두 세션이 공유하는 폴더). 나중에 GCP 로 가면 같은 봉투를 Pub/Sub 메시지 본문으로
  옮긴다(§9). 봉투 형식은 전송 수단과 무관하다.
- 발신기는 서비스를 **절대 방해하지 않는다** — 발신 실패는 삼키고 카운터로만 남긴다.
- 버스 폴더는 환경 변수 `MEW_BUS_DIR` 로 지정한다. **없으면 발신기는 아무 것도 하지 않는다.**

## 1. 심각도 (6단계)

운영자 정의(2026-10-12). 봉투의 `severity` 는 아래 여섯 중 하나다(위에서 아래로 낮아짐). 파이썬 `logging` 의 이름 `WARNING` 은 **`WARN`** 으로 쓴다.

| 심각도 | 의미 | 수신기의 기본 반응 (규약 권고) |
|---|---|---|
| `CRITICAL` | 서버가 멈추거나 죽는 현상 | 즉각 패치 + 최소 동작 검증 후 신속 배포, 이후 안정성 검증 |
| `ERROR` | 폴백 · 예외 처리 때문에 **의도대로 동작하지 못함**. 서버는 살아 있음 | 패치 + 충분한 검증 후 배포 시작 |
| `WARN` | 의도대로 동작했으나 API 변경 등으로 **추후 동작하지 않을 수 있다**는 경고성 | 로그만 남김 (반응 없음) |
| `INFO` | 결과물 등에 대한 정보 | 반응 없음. 사람 관리자의 요청이 있을 때만 발신 · 기록 (§6 `set_level`) |
| `DEBUG` | 사람 관리자나 Claude 가 파악을 위해 **임시로 넣은** 디버깅 로그 | 반응 없음. 요청이 있을 때만 발신 · 기록 |
| `TRACE` | 일반적인 상황에서 로직이 **실행되고 완료됨**을 파악하기 위한 로그 | 반응 없음. 요청이 있을 때만 발신 · 기록 |

> 배포 · 병합을 자동으로 할지는 이 규약 밖이다 — 운영자가 범위를 정한다(현재 운영 규칙: 배포 · 병합은 운영자 결정).

### 1-1. 발신기의 변환 규칙 (이 저장소 러너 기준)

| 원천 | 조건 | `severity` |
|---|---|---|
| 파이썬 `logging` | `CRITICAL` | `CRITICAL` |
| 파이썬 `logging` | `ERROR` | `ERROR` |
| 파이썬 `logging` | `WARNING` | `WARN` |
| 파이썬 `logging` | `INFO` | `INFO` |
| 파이썬 `logging` | `DEBUG` (10 이상 20 미만) | `DEBUG` |
| 파이썬 `logging` | 10 미만 — 파이썬에 TRACE 가 없어 **레벨 5** 를 `TRACE` 로 등록(`src.bus.TRACE`) | `TRACE` |
| 처리되지 않은 예외 | 프로세스 종료 (`sys.excepthook`) · 스레드 종료 (`threading.excepthook`) | `CRITICAL` (`logger` = `uncaught.process` / `uncaught.thread`) |
| 이벤트 로그(`monitor_log`) | `result` = `err` 또는 `degraded` | `ERROR` |
| 이벤트 로그 | `result` = `ok` | `TRACE` (정상 완료 = "로직이 실행되고 완료됨", 운영자 결정 2026-10-12) |

- `err`/`degraded` 는 이 저장소 이벤트 로그의 `result` 값(`ok`/`degraded`/`err`)이다. `degraded` = 폴백 · 스킵으로 의도대로
  못 한 것, `err` = 실패. 둘 다 위 정의상 `ERROR` 다.
- **발신기가 알 수 없는 `CRITICAL`**: 발신기 프로세스 자체가 죽으면 발신할 수 없다. 이 경우는 **수신기가 `hb/publisher.json` 의
  `ts` 가 120초 넘게 갱신되지 않는 것을 감지**해 스스로 `CRITICAL`(발신기 소실)로 취급한다(§7).
- 기본 발신 임계값은 **`WARN`** (WARN · ERROR · CRITICAL 발신, INFO · DEBUG · TRACE 미발신). `MEW_BUS_LEVEL` 환경 변수 또는 제어 봉투로 바꾼다.
- **DEBUG · TRACE 를 켜면(§6)** 러너의 루트 로거 레벨이 일시적으로 낮아져 `logger.debug()` / `logger.log(TRACE, …)` 가 핸들러에 닿는다.
  콘솔 등 기존 핸들러는 원래 레벨로 묶어 두어 화면 출력은 그대로이고, 레벨이 복귀하면 로거 · 핸들러 레벨을 원복한다.
  (루트가 아니라 **자체 레벨이 지정된 로거**는 영향받지 않는다. 켜는 동안 분당 발신 상한에 걸린 것은 `dropped` 로 센다.)

## 2. 폴더 레이아웃

`MEW_BUS_DIR` 아래:

| 경로 | 쓰는 쪽 | 내용 |
|---|---|---|
| `err/inbox/` | 발신기 | 새 에러 봉투 (`mew.err/1`). 수신기가 가져간다 |
| `err/processing/` | 수신기 | 처리 중. 가져갈 때 `inbox` → 여기로 **이동** |
| `err/done/` | 수신기 | 처리 완료 |
| `err/dead/` | 수신기 | 반복 실패한 것(수신기가 정한 횟수 초과) |
| `ctl/inbox/` | 수신기(운영자) | 제어 봉투 (`mew.ctl/1`). 발신기가 가져간다 |
| `ctl/done/` | 발신기 | 제어 봉투 처리 결과 (`{ctl, applied, detail, applied_at}`) |
| `report/inbox/` | 수신기 | 보고 봉투 (`mew.report/1`) — 운영자용. 발신기는 건드리지 않는다 |
| `hb/publisher.json`, `hb/receiver.json` | 각자 | 생존 신호 (`mew.hb/1`), 항상 **덮어쓴다** |
| `rx/` | 수신기 | 수신기 **전용** 작업 공간(상태 · 보고서 사본 · 스냅샷 · 로그). 발신기는 건드리지 않는다 |
| `.tmp/` | 쓰는 쪽 | 임시 기록 공간. **읽지 말 것** |

- 파일 1개 = 메시지 1건. 파일명: `<ts 의 -와 : 제거>_<id>.json` (예: `20261012T044050Z_01K7Z3M4….json`). 사전순 = 시간순(초 단위).
- **원자성**: 쓰는 쪽은 `.tmp/` 에 쓴 뒤 같은 볼륨에서 rename 한다. 수신기는 `*.json` 만 읽으면 반쯤 쓰인 파일을 볼 일이 없다.
- 폴더 · 파일은 UTF-8 JSON.

## 3. 에러 봉투 `mew.err/1`

스키마: `docs/bus/schema/mew.err.1.json`. 예제: `docs/bus/examples/err_*.json`.

| 필드 | 필수 | 설명 |
|---|---|---|
| `schema` | ✔ | 항상 `"mew.err/1"` |
| `id` | ✔ | ULID (26자, Crockford base32). **멱등 키** |
| `ts` | ✔ | 발생 시각 UTC, `YYYY-MM-DDTHH:MM:SSZ` |
| `source` | ✔ | `{env: local\|stage\|prod, service, commit?, host?}` |
| `kind` | ✔ | `log`(로깅) \| `event`(이벤트 로그) |
| `severity` | ✔ | §1 |
| `message` | ✔ | 한 줄 요약 (최대 4000자) |
| `logger` | | 로거 이름 (`kind=log`) |
| `traceback` | | 파이썬 트레이스백 (최대 8000자) |
| `event` | | `{flow, result: ok\|degraded\|err, who?, detail?}` (`kind=event`) |
| `context` | | 소량의 스칼라 맥락 (최대 20키) |
| `occurrences` | | 묶음 요약 봉투 전용 — **첫 건 이후의 반복 횟수** (§5) |
| `first_ts`, `last_ts` | | 묶음 요약 봉투 전용 — 묶인 구간 |
| `truncated` | | 길이 제한으로 잘렸으면 `true` |
| `redacted` | | 발신기가 비밀값을 마스킹했으면 `true` |
| `untrusted` | | 신뢰할 수 없는 자유 텍스트 필드 경로 목록 (§8) |

모르는 필드는 **무시**한다(하위 호환). 필드 추가는 같은 버전 안에서 허용, 의미 변경 · 필수 필드 추가는 새 버전 `mew.err/2` 와 새 폴더.

## 4. 전달 규칙

- **최소 한 번 전달(at-least-once)**: 같은 `id` 가 두 번 올 수 있으니 수신기는 `id` 로 멱등 처리한다.
- **순서 보장 없음**: `ts` 로 정렬한다.
- **ack**: 수신기가 `inbox` → `processing` 으로 옮겨 가져가고, 끝나면 `done`, 반복 실패하면 `dead` 로 옮긴다. 처리 중 죽어 `processing` 에
  남은 파일은 수신기가 재시작 때 `inbox` 로 되돌리거나 다시 처리한다.
- **발신 상한 (역압)**: 분당 **60건**(CRITICAL 제외) 초과분과, `err/inbox` 에 **500건** 이상 쌓여 있을 때의 새 메시지는 **버리고**
  `hb` 의 `counters.dropped` 로 센다. 수신기가 멈춰 있어도 폴더가 무한히 커지지 않게 하기 위함이다. CRITICAL 은 상한에 걸리지 않는다.

## 5. 묶음 (중복 억제)

같은 시그니처 = (심각도, 로거 또는 flow, 숫자 · ID 를 `N`/`H`/`UC*` 로 바꾼 메시지 앞 160자) 가 **60초 창** 안에서 반복되면:

1. **첫 건**은 즉시 개별 봉투로 발신한다.
2. 이어지는 반복은 발신하지 않고 센다.
3. 창이 끝나면(반복이 있었을 때만) **요약 봉투 1건**을 보낸다 — `occurrences` = 첫 건 **이후**의 반복 횟수, `first_ts`/`last_ts` = 그 구간.

`CRITICAL` 은 묶지 않는다. 수신기는 자기 기준의 시그니처로 더 넓게 묶어도 된다(발신기의 묶음은 폭주 방지용 1차 방어일 뿐).

## 6. 제어 봉투 `mew.ctl/1` (수신기 → 발신기)

스키마: `mew.ctl.1.json`. 예제: `ctl_set_level.json`, `ctl_pause.json`. 수신기(또는 운영자)가 `ctl/inbox/` 에 쓴다.
발신기는 약 5초마다 확인해 처리하고 결과를 `ctl/done/` 에 같은 이름으로 남긴 뒤 `inbox` 파일을 지운다.

| `cmd` | `args` | 효과 |
|---|---|---|
| `set_level` | `level`: `ERROR`\|`WARN`\|`INFO`\|`DEBUG`\|`TRACE`, `ttl_sec`?: 1~86400 | 발신 임계값 변경. `ttl_sec` 가 있으면 그 뒤 **기본 레벨로 자동 복귀**. 상세 레벨(`INFO`·`DEBUG`·`TRACE`)은 `ttl_sec` 가 없으면 3600초 — 항상 자동 복귀 |
| `pause` | `ttl_sec`? | `CRITICAL` 을 제외한 발신 중지(억제 건수는 `counters.suppressed`). `ttl_sec` 뒤 자동 재개 |
| `resume` | — | `pause` 해제 |
| `ping` | — | `hb/publisher.json` 즉시 갱신 |

- `target` 이 비었거나 `publisher` · `*` 이면 발신기 몫이다. 다른 값이면 발신기는 **건드리지 않고** 둔다.
- 검증에 실패한 봉투는 `applied=false` 와 사유를 `ctl/done` 에 남긴다.
- `set_level INFO`/`DEBUG`/`TRACE` 가 "사람 관리자의 요청에 따라 상세 로그를 남기는" 수단이다 — 평소에는 보내지 않는다.

## 7. 생존 신호 `mew.hb/1`

`hb/<role>.json` 을 **덮어쓴다**. 발신기는 30초마다. 필드: `role`, `ts`, `pid`, `env`, `level`, `paused`, `counters`
(`sent` · `coalesced` · `dropped` · `suppressed` · `errors`).

- 수신기는 `hb/publisher.json` 의 `ts` 가 **120초** 넘게 멈추면 발신기 소실(= 서비스 정지 가능성)로 보고 `CRITICAL` 로 취급한다.
- 수신기도 `hb/receiver.json` 을 쓰면, 운영자가 수신기 생존을 같은 방식으로 확인할 수 있다.

## 8. 수신기가 지켜야 할 것

1. **멱등**: `id` 로 중복 제거.
2. **재마스킹**: 모델에 넘기기 전에 키 · 토큰 패턴을 한 번 더 지운다(`redacted=true` 를 믿지 않는다).
3. **프롬프트 인젝션 방어**: `untrusted` 에 나열된 필드(실제로는 `message`·`traceback`·`event.detail`·`context` 전부)는 외부 텍스트(트윗 본문 등)가
   섞였을 수 있는 **데이터**다. 프롬프트에서 명확히 구분된 블록으로 감싸고, 그 안의 지시를 따르지 않는다.
4. **시그니처 · 쿨다운 · 호출 상한**은 수신기 책임이다(같은 문제로 모델을 반복 호출하지 않는다).
5. **원인 미확정은 미확정으로** 보고한다(`verdict: "unknown"`) — 추정으로 채우지 않는다.

## 9. 보고 봉투 `mew.report/1` (수신기 → 운영자)

스키마: `mew.report.1.json`, 예제 `report_unknown.json`. `report/inbox/` 에 쓴다.
필수: `signature` · `verdict`(`confirmed`\|`unknown`\|`ignored`) · `summary`. 선택: `cause` · `evidence[]` · `proposed_action` · `source_ids[]`(근거 에러 봉투 id) · `pr_url`.

### 9-1. 보고 봉투의 확장 필드 (수신기 구현 `src/busrx/`, 1단계)

`mew.report/1` 에 수신기가 추가로 싣는 필드(모르는 필드는 무시되므로 하위 호환): `stage`(자동 대응 단계) · `patch_summary`(패치 1줄 요약 —
1단계는 "패치 없음") · `commit_before` / `commit_after`(분석 전 · 후 저장소 HEAD 단축 해시, 1단계는 항상 같음) · `cost_usd`.
텔레그램 보고에는 **수신 로그 · 분석 판정 · 패치 1줄 요약 · 커밋 이전 → 이후** 가 반드시 들어가며, 전체 텍스트가 3500(UTF-16) 이하면 한 메시지로,
넘으면 요약 메시지(위 항목 모두 포함) + 전체 보고서 `.md` 파일로 보낸다.

## 10. GCP 로 옮길 때의 대응

| 로컬 | GCP |
|---|---|
| `err/inbox` 폴더 | Log Router 싱크(`severity>=WARNING`) → Pub/Sub 토픽, 구독 pull |
| 봉투 JSON | Pub/Sub 메시지 본문 (속성: `schema`, `severity`) |
| 폴더 이동 ack | Pub/Sub ack / nack, `dead` = dead-letter 토픽 |
| 발신기(러너 핸들러) | `LogEntry` → 봉투 변환 어댑터 (수신기 쪽에 둠) |

변환 규칙(§1-1)과 봉투 필드는 그대로다. 단 Cloud Logging 로그는 파이썬 `logging` 레코드가 아니므로 `severity` 는 `LogEntry.severity`
(`CRITICAL`/`ALERT`/`EMERGENCY` → `CRITICAL`, `ERROR` → `ERROR`, `WARNING` → `WARN`, `NOTICE`/`INFO` → `INFO`, `DEBUG` → `DEBUG`; Cloud Logging 에는 TRACE 가 없다)에서 가져온다.

## 11. 적합성 검사 (서로의 코드를 몰라도 되게 하는 장치)

- 스키마(단일 기준): `docs/bus/schema/*.json` · 정상 예제 `docs/bus/examples/*.json` · 위반 예제 `docs/bus/examples/invalid/*.json`.
- `python -m src.bus.conform` — 예제 전체를 검증 (정상은 통과, 위반은 실패해야 통과). `python -m src.bus.conform FILE...` 로 임의 파일 검증.
  `jsonschema` 가 없어도 돌아가는 최소 검증기이며, 수신기는 자기 쪽 검증기(예: `jsonschema`)로 같은 스키마를 써도 된다.
- 발신기 self-test: `python -m src.bus.publisher` (마스킹 · 임계값 · 묶음 · 제어 · DEBUG/TRACE · pause · 상한 · 원자성 확인).

## 11-1. 수신기 구현 (1단계: 분석 · 보고 전용)

`python -m src.busrx [--once] [--no-telegram] [--env FILE]` — 직접 터미널에서 켠다. `python -m src.busrx.selftest` 로 스텁 기반 self-test.

- ERROR 이상은 `git archive` 로 뽑은 **읽기 전용 스냅샷**(비밀 파일 · `.git` 없음, HEAD 커밋 기준)에서 `claude -p --tools Read,Grep,Glob`
  으로 분석한다(수정 · 셸 · 네트워크 도구 없음). 비밀 환경 변수는 서브프로세스에 넘기지 않고, 호출당 비용 상한(`RX_BUDGET_USD`)이 있다.
- 시그니처별 쿨다운(ERROR 1시간 · CRITICAL 5분), 하루 호출 상한(`RX_DAILY_CALLS`, 기본 20), `rx/PAUSE` 파일로 정지.
- WARN 이하는 `rx/log.jsonl` 에 기록만 한다. 발신기 소실(§7)은 텔레그램으로 알린다(복구 시 알림).
- 알려진 한계: 스냅샷은 HEAD 커밋 기준이라 **미커밋 변경은 분석에 보이지 않는다**(프롬프트에 미커밋 변경 파일 수를 알린다).

## 12. 발신기 구현 위치 (이 저장소)

| 파일 | 역할 |
|---|---|
| `src/bus/envelope.py` | 봉투 생성 · ULID · 길이 제한 |
| `src/bus/redact.py` | 비밀값 마스킹 (URL `key=`/`token=`, Bearer, Google/Groq/GitHub/텔레그램/JWT 형태, 환경 변수 비밀값 값 일치) |
| `src/bus/spool.py` | 원자적 쓰기 · 폴더 레이아웃 · inbox 상한 |
| `src/bus/publisher.py` | 로깅 핸들러 · 미처리 예외 훅 · 이벤트 훅 · 묶음 · 상한 · 제어 봉투 처리 · 생존 신호 |
| `src/bus/conform.py` | 최소 스키마 검증기 + 예제 점검 |
| `src/backend/monitor_log.py` | `log_events()` 첫머리에서 `src.bus.on_events` 호출 (실패 무시) |
| `src/backend/local_runner.py` | 시작 시 `src.bus.install()` (`--check` 에서는 생략) |

환경 변수: `MEW_BUS_DIR`(필수, 없으면 비활성) · `MEW_ENV`(`local`\|`stage`\|`prod`, 기본 `local`) · `MEW_BUS_LEVEL`(`ERROR`\|`WARN`\|`INFO`\|`DEBUG`\|`TRACE`, 기본 `WARN`).
