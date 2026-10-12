# 자동 수정 (AUTOFIX) — 수신기 2단계, v4.3-fullauto

> 브랜치 `v4.3-fullauto` 전용 실험 (2026-10-12 운영자 결정). `main` · 운영에는 반영되지 않았다.
> 1단계(분석 · 보고)는 `docs/BUS_PROTOCOL.md` §11-1, 이 문서는 **2단계(수정안 작성 → 검증 → 로컬 브랜치 커밋 → 러너 적용 · 재시작)**.

## 1. 운영자 결정 (그대로 기록)

| 항목 | 결정 |
|---|---|
| 모델 배정 | **코드 수정 · 구현 = Haiku 5.5** (`claude-haiku-5-5`). **분석 · 명세서 작성 · 검증 · 이중 검토 = Sonnet 5.5** (`claude-sonnet-5-5`) |
| 변경 크기 | **제한 없음** (수백~수천 줄 가능). 대신 텔레그램에 **파일별 +/− 와 합계**를 항상 표시 |
| 이중 검토 | 넣는다 — 검증자와 별개의 독립 검토자(새 맥락) |
| 필수 확인 | 원격 main · data 브랜치, Vercel 주소, GCP 배포 서버 URL, 배포판이 쓰는 텔레그램 번호를 **건드리지 않는지 매번 확인** |
| 버저닝 | 프로젝트 규칙대로(핫픽스는 패치 번호만 — 본 브랜치에서는 `v4.3.<n>`, 순번은 수신기가 부여) |
| 커밋 · 푸시 | **로컬 브랜치에만** 커밋. **원격 푸시는 운영자가 요청할 때만** |
| 자동 병합 | 불필요 (main 병합 없음) |
| 러너 재시작 | 패치 적용 후 **자동으로** 진행 |

## 2. 파이프라인 (확정된 원인에 대해서만)

```
분석(Sonnet) ─ confirmed ─▶ 명세서(Sonnet) ─ fixable ─▶ 워크트리 생성(auto/<시그니처>-<n>)
   ─▶ 구현(Haiku) ─▶ 기계 검사(가드 · 문법 · self-test 전후 비교)
   ─▶ 검증(Sonnet) ─▶ 이중 검토(Sonnet, 새 맥락)  ──(문제 있으면 Haiku 수정 라운드 1회)──▶
   로컬 브랜치 커밋(수신기가 직접) ─▶ 보호 대상 불변 확인 ─▶ 러너 작업 브랜치에 ff-only 적용
   ─▶ 러너 재시작 ─▶ 건강 확인 ─ 실패 시 ─▶ 자동 git revert + 재시작
```

- 분석이 `unknown`/`ignored` 이거나 명세서가 `fixable=false`(외부 서비스 일시 오류 등)이면 **코드를 고치지 않고** 그 사유를 보고한다.
- 하루 수정 시도 상한 `RX_FIX_DAILY`(기본 3). 수정 호출은 Pro 사용 한도를 소모한다.
- 구현(Haiku)은 **셸 도구가 없다**(`Read,Grep,Glob,Edit,Write` + `acceptEdits`). git · 테스트 실행은 수신기가 한다. Haiku 는 git 을 쓰지 못한다.
- 검증 · 검토는 읽기 전용(`Read,Grep,Glob`). 검토자는 명세서 · 검증 결과를 보지 않고 원인 분석과 diff 만 본다.
- 수정 라운드는 1회: 문법 오류 · self-test 회귀 · 검증/검토 반려는 지적 사항을 Haiku 에 되돌려 다시 시도하고, 그래도 안 되면 폐기한다.
  **금지 자원 위반 · 검토자의 운영 자원 접촉 지적은 수정 라운드 없이 즉시 폐기**한다.

## 3. 가드 (프롬프트 규약이 아니라 사후 기계 검사 — `src/busrx/guard.py`)

1. **수정 허용 경로**: `src/backend/` · `src/collector/` 만. 그 밖(프론트엔드 · `config/` · `deploy/` · `docs/` · `.github/` …)은 위반.
2. **허용 경로 안의 금지 파일**: `src/bus/` · `src/busrx/`(자기 자신), 운영 자원 접근을 정하는
   `storage.py` · `gh_store.py` · `tasks.py` · `oidc.py` · `config.py` · `writeclient.py` · `local_runner.py` · `tg_poll.py` · `notify.py`.
3. **금지 자원이 추가되는 줄**(추가된 줄만 검사) — 위반이면 즉시 폐기:
   Vercel 주소(`vercel.app` · `mewtype-schduler`) · GCP(`*.run.app` · `asia-northeast1` · `mewtype-backend/telegram` · Cloud Tasks · Secret Manager) ·
   운영 데이터 저장소(`mewtype-scheduler-data` · GitHub API · raw.githubusercontent) · 원격 git/CLI 조작(`git push|remote|fetch|pull`, `gh`, `gcloud`, `vercel deploy` —
   `['git', 'push']` 같은 인자 리스트 형태 포함) · 텔레그램 봇 토큰 형태 · chat id 리터럴 · 운영 헬스체크 · main/data 브랜치 직접 지정 ·
   현재 환경의 비밀값/chat id 값이 코드에 들어간 경우.
4. **디스클레이머**: 디스클레이머 · 면책 · 법률 문구가 든 줄의 **삭제**는 위반.
5. **보호 대상 불변**(수정 전 · 후 스냅샷 비교): 로컬 `main` · `data` 브랜치 ref, **모든 원격 추적 ref**(푸시했다면 바뀐다), `origin` URL 등 remote 설정,
   `.env` · `.env.local` 내용. 하나라도 달라지면 위반.
6. **자체 검증**: 변경된 `.py` 문법 검사(`.pyc` 를 만들지 않음) + 변경 모듈과 핵심 모듈(`preview` · `statemachine` · `preview_build` · `xtweet` · `xrelay` · `notices`)의
   self-test 를 **변경 전 스냅샷과 변경 후 워크트리에서 각각** 돌려 비교. 변경 전엔 통과했는데 후에 실패하면 회귀(수정 라운드 대상). 변경 무관 기존 실패는 건수로만 표시.
   테스트 실행 환경에는 비밀 환경 변수를 넘기지 않는다.
7. 텔레그램 보고에 **"금지 자원 확인: 통과/실패 (확인 항목 목록)"** 이 항상 들어간다.

> 한계: 가드는 *추가되는 줄* 의 패턴을 검사하므로, 패턴에 없는 방식으로 운영 자원에 접근하는 코드는 막지 못할 수 있다. 그래서 이중 검토(독립 검토자의
> 운영 자원 접촉 판단)와 비밀 환경 변수 미전달(테스트 · claude 모두)을 겹쳐 둔다. 새 우회 패턴을 발견하면 `guard.FORBIDDEN_ADDED` 에 추가한다.

## 4. 적용과 재시작

- 적용 = 러너가 쓰는 작업 폴더(`RX_RUNNER_DIR`, 기본 이 저장소)의 **작업 브랜치(`RX_APPLY_BRANCH`, 기본 `v4.3-fullauto`)에 `git merge --ff-only auto/…`**.
  main · data 에는 절대 하지 않는다. 원격 푸시도 하지 않는다.
- 다음이면 **적용을 보류**하고 브랜치만 남긴다(보고서에 사유): 현재 브랜치가 작업 브랜치가 아님 · HEAD 가 수정 base 와 다름 · **미커밋 변경이 수정 파일과 겹침** · ff 불가.
  `RX_APPLY_LOCAL=0` 이면 항상 로컬 브랜치 커밋까지만.
- 재시작(`src/busrx/restart.py`): `_local/ops/runner.json` 의 pid 가 실제로 `local_runner` 를 실행 중일 때만 종료(`taskkill /T /F`) 후 같은 명령을 분리된 프로세스로 재기동.
  러너가 안 떠 있었으면 재시작하지 않고 "적용만"으로 보고. 재시작 뒤 출력은 `<러너 폴더>/_runner.log`.
  **원래 터미널 창에서 보던 러너 출력은 재시작 후 그 창에서 더 이상 안 나온다**(로그 파일로 이동).
- 건강 확인: `/healthz-local` ok + 발신기 hb 가 재시작 이후로 갱신. 실패하면 **자동 `git revert --no-edit HEAD` 후 재시작** — 결과를 보고한다.
- 재시작 중에는 "발신기 소실" 알림을 4분간 억제한다. 큐 작업은 디스크에 있어 재시작해도 이어진다.

## 5. 텔레그램 보고 (2단계)

항상 포함: ① 수신 로그(발신기) ② 분석 판정 · 한 줄 요약 ③ **패치 한 줄 요약 + 버전** ④ **변경 합계(파일 N개 · +A −D · 총 줄수)와 파일별 +/−**
⑤ 브랜치(로컬) · 모델 배정 ⑥ 테스트 결과 · 검증자/검토자 판정 · 수정 라운드 수 ⑦ **금지 자원 확인 결과** ⑧ **커밋 이전 → 이후**(base → 수정 커밋) ⑨ 적용 · 재시작 · revert 결과 ⑩ **구독 사용량**(세션 5시간 사용·남음·초기화 시각·이번 처리 +%p, 주간 7일 사용·남음·초기화 시각).
전체가 3500(UTF-16) 이하면 한 메시지, 넘으면 요약(위 항목 포함, 파일은 10개까지) + 전체 보고서 `.md`(파일 전부). report 봉투에는 `files_changed[]` ·
`lines_added/deleted` · `usage`(세션·주간 사용률) · `guard_ok` · `applied` · `restarted` · `fix_status` · `fix_branch` 가 추가로 실린다.

## 6. 설정 (환경 변수 · `src/busrx/receiver.py` `Config`)

`RX_STAGE`(기본 2, 1 이면 분석 · 보고만) · `RX_MODEL_ANALYSIS`(기본 `claude-sonnet-5-5`) · `RX_MODEL_CODE`(기본 `claude-haiku-5-5`) · `RX_FIX_DAILY`(3) ·
`RX_APPLY_LOCAL`(1) · `RX_APPLY_BRANCH`(`v4.3-fullauto`) · `RX_RUNNER_DIR`(이 저장소) · `RX_BUDGET_USD` 등 호출별 비용 상한. 정지: `mewtype-bus/rx/PAUSE` 파일.

## 7. 점검

`python -m src.busrx.selftest`(1단계) · `python -m src.busrx.selftest_fix`(2단계: 임시 git 저장소 + 가짜 claude · 가짜 재시작으로 S1~S12 · 가드 단위) · `python -m src.bus.conform`.
실제 `claude -p` 로 확인한 것: 두 모델 ID 호출 가능, Haiku 의 `--permission-mode acceptEdits` 파일 수정 동작. **실제 러너 종료 · 재기동은 아직 실물로 시험하지 않았다**(가짜 재시작으로만).

## 8. 구독 사용량 표시 (2026-10-12 운영자 요청)

텔레그램 보고마다 `── 사용량(구독) ──` 구간을 붙인다: **세션(5시간)** 사용률 · 남음 · 초기화 시각(KST) · **이번 처리에서 늘어난 %p**, **주간(7일)** 사용률 · 남음 · 초기화 시각.
- 출처: `claude -p --output-format stream-json --verbose` 가 호출마다 내보내는 `rate_limit_event` 의 `unifiedWindows.five_hour / seven_day` (`utilization` 0~1, `resetsAt` epoch).
  구독(claude.ai 로그인) 인증일 때만 있고, 없으면 "사용량 정보 없음"으로 표시.
- 한계: 사용률은 **같은 계정의 다른 세션(사람이 쓰는 Claude Code 포함) 사용분을 포함한 값**이고 1%p 단위로 갱신되어, 작은 처리는 +0~1%p 로 보인다.
  "이번 처리" 증가분은 직전 보고 이후(15분 이내, 같은 5시간 창)의 값을 기준선으로 하고 없으면 이번 처리의 첫 이벤트를 기준으로 한다.
