# fix: gh_store 1MB 넘는 파일을 Git Blob API 로 읽어 개인 트윗 반영 실패 해결

## 변경 계획
- `src/backend/gh_store.py`: read_json 과 read_text 가 똑같이 들고 있는 Contents API GET·디코딩 부분(101-128행, 205-223행)을 private 헬퍼 `_get_contents(path) -> tuple[Optional[str], Optional[str]]`(본문 문자열, sha) 하나로 뽑는다. 404 는 (None, None), 200 이 아니면 지금과 같은 RuntimeError 를 낸다. 응답의 `content` 가 비었을 때 처리: (a) `encoding == 'none'` 이고 `sha` 가 있으면 1MB 초과 파일이므로 `_get_blob(sha)` 를 부른다. `_get_blob` 은 `GET {API}/repos/{repo}/git/blobs/{sha}` 를 같은 `_headers()` 와 timeout 으로 호출하고, 응답 `encoding` 이 'base64' 이면 `content` 를 base64 디코딩해 utf-8 문자열로 돌려준다. 200 이 아니거나 encoding 이 'base64' 가 아니거나 content 가 없으면 상태코드·encoding·size 를 담은 RuntimeError 를 낸다(삼키지 않는다). 반환 sha 는 Contents 응답의 sha 를 그대로 쓴다. blob 을 sha 로 지정해 받으므로 본문과 sha 가 같은 스냅샷이고, write_json 의 prev_sha 낙관적 동시성이 그대로 유지된다. (b) 그 밖의 빈 content 는 지금과 같은 'No content in response … (encoding=…, size=…)' RuntimeError 를 낸다. read_json 은 `_get_contents` 결과를 json.loads 하고, 지금처럼 (ValueError, KeyError) 를 'response parsing error' 로 바꾼다. read_text 는 결과를 그대로 돌려준다. requests.RequestException 은 지금처럼 'network error' RuntimeError 로 바꾼다. write_json 과 write_text 는 안에서 read_json/read_text 를 부르므로 따로 고치지 않아도 큰 파일 쓰기(아카이브 갱신 2191·4621·6315행)가 함께 풀린다. 모듈 docstring 과 read_json docstring 에 '1MB 초과(encoding=none) → Git Blob API(sha 지정, 최대 100MB)로 다시 읽음' 한 줄을 한국어로 적는다.
- `src/backend/gh_store.py (self-test)`: `if __name__ == "__main__":` 에 회귀 검사를 추가한다. URL 로 응답을 가르는 `_BigFakeSess` 를 만든다: `/contents/` GET 은 `{"content": "", "encoding": "none", "size": 1138183, "sha": "shaBig"}` 를, `/git/blobs/shaBig` GET 은 `{"content": base64(직렬화된 큰 dict, 76자마다 개행 포함), "encoding": "base64", "sha": "shaBig"}` 를 돌려주고 PUT 은 201 을 돌려준다. 검사 항목: (1) read_json 이 원본 dict 와 sha 'shaBig' 를 돌려준다. (2) blob GET 이 정확히 1번, sha 'shaBig' 로 호출된다. (3) write_json(prev_sha='shaBig') 는 PUT 한다. write_json(prev_sha='shaOld') 는 ConflictError 를 내고 PUT 하지 않는다. (4) read_text 도 같은 경로로 본문을 돌려준다. (5) blob 응답이 403 이면 RuntimeError 가 난다(조용히 None 을 돌려주지 않는다). (6) encoding 이 'none' 이 아니고 content 가 빈 응답이면 지금처럼 RuntimeError 가 난다. 기존 _FakeSess 검사 1~6 은 그대로 둔다.
- `docs/SPEC.md`: §8.7 `gh_store.py` 에 한 줄을 더한다: 'read_json · read_text — Contents API 가 1MB 초과 파일에 content 를 비워 주면(encoding=none) 응답 sha 로 `GET /repos/{repo}/git/blobs/{sha}` 를 다시 읽는다(최대 100MB). sha 는 Contents 응답 값을 그대로 써 낙관적 동시성이 유지된다. 실패는 RuntimeError.' 데이터 계약(계약 I `tweet_archive.json` 스키마·보존)은 바꾸지 않는다.

## 테스트 계획
1) `PYTHONIOENCODING=utf-8 python -m src.backend.gh_store` 실행. 기존 직렬화·낙관적 동시성·write_text 검사와 새 큰 파일(encoding=none → blob) 검사 6개가 모두 통과해야 한다. 2) `python -m src.backend.storage`, `python -m src.backend.telegram_app` 을 돌려 회귀가 없는지 본다. 둘 다 gh_store 를 감싸거나 가짜 gh 를 쓰므로 영향이 없어야 한다. 3) `python -m src.backend.local_store` 통과를 확인한다(로컬 시험판 저장 계층이며 이번에 바꾸지 않았다). 4) 운영 자원은 쓰지 않는다. 실제 블롭 경로는 로컬 실험용 저장소에 1MB를 넘는 JSON(예: tweets 1,500건짜리 tweet_archive.json)을 두고 GH_TOKEN_TEST 류의 시험 토큰으로 read_json → write_json 왕복을 해 확인한다. 이때 sha 일치와 PUT 성공을 본다. 이 확인은 수신기 쪽 시험 환경 몫이다.

## 위험
(1) Git Blob API 의 fine-grained PAT 권한은 GitHub 문서상 'Contents: read' 로 알고 있지만, 이 환경에서 실제 토큰으로 확인하지 않았다. 권한이 모자라면 403 RuntimeError 가 메시지를 그대로 담아 드러난다(지금과 같은 실패 지점이며 숨기지 않는다). (2) 1MB를 넘는 파일은 읽을 때마다 GET 이 2회가 되고, write_json 도 내부에서 read_json 을 부르므로 아카이브 쓰기 1회에 GET 2회 + PUT 1회가 된다. 시간당 5,000회 한도에 비하면 작다. (3) PUT 쪽 크기 한도는 소스로 증명하지 못했다. 다만 아카이브가 이미 1,138,183바이트로 저장돼 있고 모든 원격 쓰기는 _put_content(Contents PUT)를 거치므로, 이 크기의 PUT 은 성공한 적이 있다. (4) tweet_archive.json 은 보존 상한 없이 계속 커진다. 다만 Blob API 한도인 100MB 까지 여유가 크다. 보존 정책은 이번 수정 범위가 아니다(아래 auto_decisions).

## 자동 결정한 값
- 큰 파일 대체 경로 = Git Blob API(`/git/blobs/{sha}`). raw 미디어 타입 재GET 은 쓰지 않는다. 근거: 첫 GET 이 받은 sha 로 지정해 읽으므로 본문과 sha 가 같은 스냅샷이다. raw 재GET 은 두 GET 사이에 다른 커밋이 끼면 본문과 sha 가 어긋나 write_json 의 prev_sha 낙관적 동시성(gh_store.py:189-194)을 깰 수 있다. 호스트도 기존 api.github.com 이라 새 외부 호스트가 아니다.
- 대체 경로 발동 조건 = content 가 비고 encoding == 'none' 일 때만. 근거: 로그 응답이 정확히 그 형태다(encoding='none', size=1138183). 다른 빈 응답은 지금과 같은 에러를 유지해 동작 변화를 최소로 한다.
- tweet_archive.json 보존 상한·잘라내기는 넣지 않는다. 근거: SPEC 계약 I(docs/SPEC.md:617-618)에 보존 기간이 없다. 아카이브는 find_reused_ko 번역 재사용과 _fill_member_gaps 의 'deleted 되살리지 않기' 판정에 쓰인다. 지시의 '데이터를 버리거나 잘라내기 금지'에도 걸린다. 읽기 한도가 원인이므로 읽기 경로를 고치는 것이 근본 해결이다.
- telegram_app.py 의 호출부(2025·2160·2936·4614·6185·6309행)는 고치지 않는다. 근거: 모두 gh.read_json/write_json 을 통하고, storage.py:67-74 가 그대로 위임하므로 gh_store 수정으로 함께 풀린다. monitor_report.py:335 와 scripts/backfill_monitor_history_*.py:46 도 같은 이유로 고치지 않는다.

## ⚠️ 민감 경로 수정
- `src/backend/gh_store.py`
- `src/backend/gh_store.py (self-test)`
- `docs/SPEC.md`
