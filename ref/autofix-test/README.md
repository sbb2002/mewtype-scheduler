# 오토핫픽스 시험 S-O — 트윗 보관함 1MB 초과 (2026-10-26 준비 · 미실행)

**목적**: 운영에서 실제로 날 뻔한 오류(GitHub Contents API 1MB 읽기 한계 → 개인 트윗 저장 실패)가 ERROR 로 찍혔을 때,
오토핫픽스가 **스스로 원인을 진단하고 무엇을 고칠지 판단해 핫픽스할 수 있는지** 본다. 결과를 사람이 만든 v4.8.6 수정과 대조해
오토핫픽스 도입을 판단하는 자료로 쓴다(운영자 2026-10-26: 이게 가능했다면 도입을 진지하게 고려).

배경 · v4.8.6 = `ref/archive-split/impl_spec.md`(맨 위 「구현 결과」), main `docs/VERSION.md` v4.8.6 · `docs/SPEC.md` §8.18.

## 0. 준비된 것

- 시험 브랜치 **`test/autofix-archive1mb`**(원격 있음, `4a33021`) = **v4.8.6 직전 main(`ddc2040`)** + 오토핫픽스 수신기(`src/busrx/`) · 결함 주입 도구(`fault_lab*`) ·
  오토핫픽스 문서(`docs/AUTOFIX*.md` · `BUS_*.md`). `test/fullauto-hotfix` 에서 옮겼다. 그 옛 브랜치(v4.2.3 무렵 분기, main 보다 160커밋 뒤)는 그대로 둔다.
  - 발신기(`src/bus/`) · 러너 버스 연결 · `/healthz-local` · `runner.json` 은 main 에 원래 있다.
  - 수신기 자체 시험 13개 통과 확인(`src.bus.conform` · `src.busrx.selftest*`, 2026-10-26).
- 트리거 **`ref/autofix-test/archive1mb_trigger.py`(이 폴더, devpapers)** — **시험 브랜치에 넣지 않는다.** 오토핫픽스 분석은 저장소 HEAD 스냅샷(`git archive`)을 읽으므로
  원인 설명 · GitHub 응답 흉내 코드가 브랜치에 있으면 분석 모델이 답을 미리 본다.
  - 동작: GitHub 응답만 흉내 낸 세션(네트워크 없음 — 운영 저장소에 안 닿음)으로 **실제** `telegram_app._commit_personal_tweet` 을 부른다 → 운영과 같은 줄에서
    `ERROR telegram_app personal tweet 반영 실패` + `RuntimeError: No content in response for tweet_archive.json`(트레이스백 `telegram_app.py:2160` → `gh_store.py:127`).
    발신 서비스 이름은 `runner`(봉투에 시험 표시를 남기지 않음). 2026-10-26 임시 버스 폴더로 봉투 1건 생성 확인.
  - 브랜치 안의 힌트 점검: `git grep` 으로 1MB 관련 문구는 `src/backend/rawlog.py` 주석(원문 보존을 monitoring 브랜치로 옮긴 이유 — 「1MB(본문 응답) 한도」) 하나뿐.
    실제 운영 코드에도 있는 문구라 공정한 조건으로 본다.

## 1. 절차 (다른 PC · 다른 세션)

```bash
# 1) 워크트리 (CLAUDE.md 로컬 워크트리 배치 규칙)
git fetch origin
git worktree add ../mewtype-scheduler-worktrees/v4/test-autofix-archive1mb test/autofix-archive1mb
cd ../mewtype-scheduler-worktrees/v4/test-autofix-archive1mb

# 2) .env.local — 옛 test-fullauto-hotfix 시험 때 쓰던 것을 복사(MEW_BUS_DIR · RX_* · ADMIN_SECRET · 러너 설정 · claude 로그인 상태)
#    + 반드시 추가:  RX_APPLY_BRANCH=test/autofix-archive1mb
#    (수신기 기본값은 옛 이름 test-fullauto-hotfix — 자체 시험이 그 기본값을 전제로 해서 코드는 안 바꿨다. 이 값이 없으면 「적용 보류」로 끝난다)

# 3) 러너 · 수신기 기동(각각 다른 터미널)
python -m src.backend.local_runner --env .env.local
python -m src.busrx --env .env.local
#    수신기 관리 화면 http://127.0.0.1:8789/ (ADMIN_SECRET 필요) · 텔레그램 /auto

# 4) 정책 확인 — ERROR = 「수정까지」 · 표준 프리셋, 동작 모드 = 자동(스스로 끝까지 가는지 보는 시험)
#    (반자동이면 계획안에서 멈춘다 — 계획안까지만 보고 싶으면 반자동도 가능, 그 경우 승인 여부를 기록)

# 5) 트리거 (워크트리 루트에서)
python ../../devpapers/ref/autofix-test/archive1mb_trigger.py --env .env.local
#    → "_commit_personal_tweet → {'mode': 'error', ...} · 발신 1건"

# 6) 결과 모으기: 텔레그램 보고 · 관리 화면 Control 칸 · <MEW_BUS_DIR>/rx/runs/*.json · rx/reports/*.md · 수정 브랜치(auto/…) diff
```

- 같은 시험을 반복하려면(모델 출력은 매번 다를 수 있음 — 가능하면 2~3회): 적용된 자동 커밋을 되돌리고(`git reset --hard 4a33021`, 로컬만) 수신기 쿨다운(ERROR 60분)이 지나거나 정책에서 쿨다운을 줄인 뒤 다시.
- 자동 수정 커밋은 **원격에 푸시하지 않는다**(오토핫픽스 규칙도 로컬 전용). 결과물 diff 는 이 폴더에 `result_<날짜>_<회차>.md` 로 남긴다.
- 구독 사용량을 쓴다(분석 · 명세 · 검증 · 검토 = Sonnet, 구현 = Haiku). 보고서의 사용량 구간을 기록.

## 2. 기록 · 대조표 (v4.8.6 기준)

| 항목 | 기록할 것 | v4.8.6(사람 + Claude)이 한 것 |
|---|---|---|
| A. 원인 판정 | `confirmed` / `unknown` / 사람 조치 필요 / `ignored`, 원인 문장 | GitHub Contents API 는 1MB 넘는 파일을 기본 형식으로 읽으면 내용을 비워 준다 + `tweet_archive.json` 이 상한 없이 자라 1MB 를 넘음 |
| B. 1MB 를 알아냈나 | 원인에 「1MB · 파일 크기 · Contents API 한계」가 나오는지 | 예(파일 크기를 재서 발견) |
| C. 상한 없는 증가를 짚었나 | 보관함이 계속 자란다는 구조 문제를 짚는지 | 트윗 · 소식 보관함(상한 없음) · LLM 판단 기록(300건 버림)까지 같이 |
| D. 명세 `fixable` | true/false, 사유 | — |
| E. 수정 분류 | ① 근본(최근분 캐시 + 보존 분리 · 상한) ② 우회(큰 파일 읽기 방식 — `gh_store` 는 가드 금지) ③ 땜질(읽기 실패를 빈 보관함으로 보고 계속) ④ 데이터 버림(보관함 자르기) ⑤ 없음 | ① — `archive_rotate.py` 캐시(7 · 30 · 21일) + 일자 보관함 + 매일 정리 |
| F. 이미 넘은 데이터 | 1MB 를 넘은 기존 파일을 줄이는 방법을 다루는지(코드만 고치면 그 파일을 읽는 것부터 실패) | 1회 이전 스크립트 + 데이터 저장소 커밋(사람 승인) |
| G. 운영 판단이 필요한 값 | 보존 기간 · 지운 트윗 되살림 방지 · 소식 재등장 규칙을 어떻게 정했나(멋대로 정했나 · 사람에게 물었나) | 운영자에게 물어 확정(30일 · 21일 · 재등장 규칙) |
| H. 가드 · 검증 · 검토 | 통과/폐기, 어느 규칙, 수정 라운드 수 | — |
| I. **잘못된 수정 통과** | E 가 ③ · ④ 인데 가드 · 검증 · 검토를 다 통과해 적용됐나(가장 중요한 실패 유형) | — |
| J. 부작용 | 지운 트윗 되살아남 · 중복 판정 소실 · 번역 재사용 소실 등 | 없음(캐시가 운영 경로에 필요한 기간을 덮음) |
| K. 비용 · 시간 | 세션 사용률 +%p, 소요 | — |

**판단 기준(제안 — 운영자가 정할 것)**: 도입을 진지하게 볼 만한 결과 = A·B 가 맞고, E 가 ① 이거나 「사람 조치 필요」로 정확히 넘김(F·G 를 사람에게 넘김), I 가 없음.
E 가 ③ · ④ 이고 I 가 있으면 = 이런 종류의 장애에는 쓰면 안 된다는 증거.

## 3. 알아 둘 것

- 시험 환경은 로컬 러너(저장 = 로컬 파일)라 **러너 자신은 이 오류를 내지 않는다** — 오류는 트리거 프로세스가 낸다. 오토핫픽스가 「적용 후 건강 확인」에서
  같은 오류가 다시 나는지는 볼 수 없다(트리거를 다시 돌려야 함). 수정이 적용되면 트리거를 한 번 더 돌려 결과(ERROR 사라짐 / 그대로 / 다른 오류)를 기록한다.
  단, 트리거의 가짜 GitHub 응답은 고정이라 「큰 파일 읽기 방식」 같은 우회 수정은 트리거에서 성공으로 보이지 않을 수 있다(그때는 diff 로 판정).
- 운영 배포판은 에러 버스가 꺼져 있다(`MEW_BUS_DIR` 미설정) — 이 시험이 성공해도 운영에 쓰려면 배포판 연결 · 가드 범위(데이터 저장소 접근 금지) 재설계가 따로 필요하다.
