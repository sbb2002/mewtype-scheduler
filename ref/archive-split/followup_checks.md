# v4.8.6 보관함 정리 — 다음 세션 확인 목록 (2026-10-26 작성)

v4.8.6(보관함 캐시 · 일자 분리)은 배포 · 첫 이전까지 끝났다. 아래는 **시간이 지나야 볼 수 있는 것**이다. 다른 세션이 이 문서만 보고 확인할 수 있게 적는다.
배경 = 같은 폴더 `impl_spec.md`(맨 위 「구현 결과」), 정본 = main `docs/SPEC.md` §8.18 · `docs/VERSION.md` v4.8.6.

- 배포: `mewtype-backend` 00186 · `mewtype-telegram` 00126 (롤백 = 00184 · 00125), 병합 `576ae34`, 태그 `v4.8.6`.
- 첫 이전: data `f33db54`(+ LF 되돌림 `fd46576`) · ops `9260c86`(+ `5a83fed`).
- 이전 직후 상태(기준값): `tweet_archive.json` 104,512B(91건) · `notice_archive.json` 147,910B(66건) · `llm_actions.json` 247,925B(207건),
  `tweet_archive/` 40개 · `notice_archive/` 15개 + `index.json` · ops `llm_actions/` 1개(`2026-10-05.json`).

## 1. 첫 보관함 정리 (2026-10-27 06:10 KST, 백엔드 `/monitor`) — 가장 중요

**예상**: 이전 때 이미 다 옮겨서 옮길 것이 적다. 06:10 기준 잘리는 선 = 트윗 게시 10-20 06:10 KST 이전 · 소식(보관/행사 날짜 중 늦은 것) 09-27 06:10 이전 ·
LLM 판단 10-06 06:10 이전. 대상마다 0 ~ 수 건, 쓴 일자 파일 0 ~ 2개. 실패 · 크기 초과면 운영자 텔레그램 DM 「⚠️ 보관함 정리 확인 필요」.

확인 방법(코드 저장소 루트에서, `gh` · `gcloud` 로그인 상태):
```bash
# 1-1. 모니터 이벤트 — 옮긴 게 있을 때만 flow="archive" 가 남는다(없으면 줄이 없는 게 정상)
gh api "repos/sbb2002/mewtype-scheduler-data/contents/monitoring/events-2026-10-27.jsonl?ref=monitoring" --jq .content | base64 -d | grep -i archive

# 1-2. data · ops 브랜치에 정리 커밋이 생겼나 (메시지 "data: archive tweet|notice|llm …")
for b in data ops; do gh api "repos/sbb2002/mewtype-scheduler-data/commits?sha=$b&since=2026-10-26T21:00:00Z&per_page=100" --jq '.[].commit.message' | grep "archive"; done

# 1-3. /monitor 실행 로그 — 오류 · 「보관함 정리 실패」가 없어야 한다
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="mewtype-backend" AND timestamp>="2026-10-26T21:05:00Z" AND timestamp<="2026-10-26T21:30:00Z" AND (textPayload:"보관함" OR severity>=WARNING)' --limit 20 --format='value(timestamp,severity,textPayload)'

# 1-4. 파일 크기 · 개수 — 캐시가 기준값과 비슷하거나 작아야 하고, 어느 파일도 1MB 근처가 아니어야 한다
for b in data ops; do echo "== $b"; gh api "repos/sbb2002/mewtype-scheduler-data/git/trees/$b?recursive=1" --jq '.tree[] | select(.type=="blob") | "\(.size)\t\(.path)"' | awk -F'\t' '$2 ~ /^(tweet_archive|notice_archive|llm_actions)/ {split($2,a,"/"); k=a[1]; n[k]++; if($1>m[k])m[k]=$1} END{for(k in n) printf "%s files=%d max=%d\n",k,n[k],m[k]}'; done
```
**같은 항목이 캐시와 일자 파일 양쪽에 남지 않았는지 · 잃은 게 없는지**(1-2 에서 커밋이 있었을 때만): 데이터 저장소를 clone 해(**`git config core.autocrlf false` 먼저** —
메모: 이 PC 는 autocrlf=true 라 안 하면 커밋 때 전체 파일이 CRLF 로 들어간다. 읽기만 할 땐 상관없음) `scripts/split_archives.py --dry-run` 을 돌리면
「잃은 항목 0 · 중복 0」과 「일자 파일 N개로 0건」(더 옮길 것 없음)이 나와야 한다.

**문제가 있으면**: 정리 작업은 일자 파일에 먼저 쓰고 캐시를 마지막에 줄이므로 실패해도 데이터를 잃지 않는다(양쪽에 남을 뿐 — 다음 날 정리가 정리).
코드를 되돌려야 하면 Cloud Run 트래픽을 00184 · 00125 로(옛 코드는 캐시만 읽으므로 그대로 동작. 단 옛 코드는 LLM 판단 기록을 다시 300건으로 자른다).

## 2. 관리 페이지 「LLM 판단」 기한 표시 (실화면 미확인)

운영자 로그인이 필요하다(텔레그램 `/admin` 일회용 링크 — 운영자에게 받거나 운영자가 직접 확인).
- 작업 탭 → 타임라인 → 칩 줄 아래 안내 문구 「LLM 판단은 판단 후 21일까지 반려 · 재판단 · 사용자 판단을 할 수 있습니다. 그 뒤에는 기록으로만 남습니다.」
- 「LLM 판단」 필터 → 판단 줄마다 「반려 · 재판단 가능: MM/DD HH:mm까지 (판단 후 21일)」. 10-06 이전 판단(있다면)은 「반려 · 재판단 기간 지남」 + 버튼 없음.
- 반려 확인 팝업 마지막 줄 「· 판단 후 21일이 지나면 반려 · 재판단할 수 없습니다.」
- 모바일 폭(≤640px)에서 줄이 겹치지 않는지.
- 서버 거절은 self-test 로만 확인했다(`admin_api._llm_review_expired`) — 실제로 기간 지난 판단에 API 를 부르면 안내 문구 오류가 와야 한다.

## 3. 웹 모니터 지난 날짜 팝업 (일자 파일 · 소식 색인에서 찾기)

이미 한 번 확인한 기준값(2026-10-26 23시 KST, 배포 직후):
```bash
U=https://mewtype-telegram-lk3cg7l7ka-an.a.run.app
for d in 2026-10-01 2026-09-20; do curl -s "$U/monitor-live/day.json?date=$d" | python -c "
import sys,json;d=json.load(sys.stdin);tw=d.get('tweet') or [];nt=d.get('notice') or []
print('$d','tweet',len(tw),'info',sum(1 for e in tw if e.get('info')),'| notice',len(nt),'info',sum(1 for e in nt if e.get('info')))"; done
```
- 기준값: 10-01 트윗 27건 중 26건 · 소식 12건 중 6건, 09-20 트윗 31건 중 31건 · 소식 6건 중 4건에 팝업 정보.
  트윗은 일자 파일에서 찾는 것이 확인됐다(이 날짜 트윗은 전부 캐시에서 빠졌다).
- **확인 필요**: 소식 정보가 빠진 건(10-01 6건 · 09-20 2건)이 **이전 전에도 빠져 있었는지**. 옛 코드 기준값이 없다 —
  이전 직전 data 커밋 `6ef699a` 의 `notice_archive.json` + `notices.json` 으로 `monitor_report.load_detail_lookup` 을 만들어 같은 날짜에
  `attach_details` 를 돌려 비교하면 알 수 있다(로컬 가짜 저장소로). 빠진 건이 이벤트 쪽 문제(nid 없음 · 소식으로 안 올라간 relay 등)면 이번 변경과 무관.
- 브라우저 확인: `https://mewtype-schduler.vercel.app/monitor.html?va=claude`(Claude 가 열 때는 `?va=claude` 필수) → 잔디에서 10-19 이전 날짜 → 트윗 · 소식 점 팝업에 원문 · 번역.

## 4. 그 밖에 남은 것 (급하지 않음)

- 모니터 `flow="archive"` 는 이벤트 로그에만 남고 웹 모니터 타임라인 레인이 없다 — 필요하면 레인 추가(`monitor_report._group`).
- `preview_archive.json`(151KB) · `banners_archive.json` 도 상한이 없다 — 커지면 같은 방식(`archive_rotate.Target` 추가).
- `notice_archive/index.json` 은 1년 약 180KB 로 자란다 — 몇 년 뒤 연도별로.
- 보류 중인 자기 답글 패치(`ref/self-reply/patch_spec.md`)를 다시 열 차례 — 그 명세의 「48h 지난 원글 되살리기」는 이제 트윗 일자 파일(게시일 = tweet id 로 계산)에서 찾는다.

## 5. 오토핫픽스 시험 S-O — 이 장애를 오토핫픽스가 혼자 고칠 수 있었나 (운영자 요청 2026-10-26)

**종료(2026-10-27, 1~6회차)** — 결론 = `ref/autofix-test/result_2026-10-27.md` 맨 위. 6회차(명세 Opus · high)가 사람 개입 없이 1MB 장애를 멈추는 수정
(Git Blob API 읽기)을 적용했고 운영자 기대 수준으로 평가 · 도입은 아직 이름. 근본 해결(캐시 + 일자 보관함)은 사람 아이디어 몫으로 남음.
부산물: main 핫픽스 v4.8.7 PR #99(빈 content 오류에 encoding · size) — 병합 · 배포 대기.
