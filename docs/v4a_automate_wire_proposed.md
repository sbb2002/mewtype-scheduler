# 배선 (수정안 — 2026-10-01)

현행 `docs/v4a_automate_wire.md` 기준 수정안. 새 블록은 `idx1, idx2, …` 로 적었다(실제 번호는 운영자가 붙임).
근거: 폰 Automate 로그 `ref/flow-11_261001.log` 대조 — `ref/v4a/v4a_remaining_0930.md` §3-2.

## 바뀌는 것 요약

| # | 변경 | 막는 실패 |
|---|---|---|
| ① | `[40]` 응답을 파일로 저장하지 않음(「Save response」 비움 → 변수로만) | 동시 파이버끼리 `Download/Automate/ingest` 파일 충돌 (`FileSystemException: Failed to delete file`) |
| ② | body 를 만든 뒤 `[idx1]` Fork — 운영 `[40]` 과 v4a `[47]` 을 **서로 다른 파이버**로 | `[40]` 실패(`Software caused connection abort` · 파일 충돌)가 `[47]` 을 막음 · v4a 도착이 운영 응답(6~34초)만큼 늦어짐 |
| ③ | `[47]` 앞에 실패 처리 + 짧은 대기 후 재시도(최대 3회) | 폰 → PC 접속 실패(`failed to connect … after 10000ms`)가 한 번이면 그대로 유실 |
| ④ | `[40]` · `[47]` 결과(성공 코드 · 실패 메시지)를 각각 로그 | 다음 누락 때 어느 쪽에서 왜 멈췄는지 바로 보이게 |
| ⑤ | `[38]` 수식 정리 — 끝 괄호 1개 제거 · `template` 키를 `android.template` 로 | (문서상 오타 — 실제 폰 설정과 다르면 무시) |

`[1]` ~ `[36]` · `[37]` · `[42]` ~ `[46]` (알림 받기 · 판정) 은 그대로.

---

```
[1] flow beginning
    - go to [35]
[35] fork stop with
    - OK route: go to [2]
    - NEW route: go to [43]
[2] when notification
    - go to [42]
    - variables
        <input>
        - package: com.sec.android.app.sbrowser
        <output>
        - posted package: pkg
        - title: ntitle
        - message: nmsg
        - nticker: nticker
        - dictionary of extras: nx
[42] fork stop with
    - OK route : go to [2]
    - NEW route : [45]
[43] when notification
    - go to [44]
    - variables
        <input>
        - package: com.google.android.youtube
        <output>
        - posted package: pkg
        - title: ntitle
        - message: nmsg
        - nticker: nticker
        - dictionary of extras: nx
[44] fork stop with
    - OK route : go to [43]
    - NEW route : [45]
[45] log append
    - go to [46]
    - message: pkg
[46] log append
    - go to [20]
    - message: nx
[20] expression true?
    - formula: `pkg = "com.google.android.youtube" && trim(coalesce(nx["chime.slot_key"], "")) != "" && contains(coalesce(nx["chime.thread_id"], ""), "LIVESTREAM") != 0`
    - YES route: go to [37]
    - NO route: go to [36]
[37] variable set
    - go to [idx1]                                  ← 변경: [40] → [idx1]
    - variable: body
    - values:
        ```
        urlEncode(
            {
                "source": "yt",
                "video_id": nx["chime.slot_key"],
                "title": nx["android.text"],
                "kind": nx["chime.thread_id"],
                "tag": coalesce(nx["pde_noti_tag"], "")
            }
        )
        ```

[36] expression true?
    - formula: `pkg = "com.sec.android.app.sbrowser" && contains(coalesce(nx["android.template"], ""), "BigTextStyle") != 0 && contains(coalesce(nx["pde_noti_tag"], ""), "#1tweet-") != 0 && trim(coalesce(nx["android.text"], nx["android.bigText"], "")) != ""`
    - YES route: go to [38]
    - NO route: end
[38] variable set
    - go to [idx1]                                  ← 변경: [40] → [idx1]
    - variable: body
    - values:                                       ← 변경: template 키 · 끝 괄호
        ```
        urlEncode(
            {
                "source": "x",
                "text": coalesce(nx["android.text"], nx["android.bigText"], nmsg, nticker, ""),
                "title": coalesce(nx["android.title"], ""),
                "template": coalesce(nx["android.template"], ""),
                "tag": coalesce(nx["pde_noti_tag"], "")
            }
        )
        ```

# ── 여기부터 변경 ─────────────────────────────────────────────

[idx1] fork                                         ← 신규: 운영 · v4a 를 다른 파이버로
    - OK route : go to [idx2]      (이 파이버 = 운영)
    - NEW route : go to [idx5]     (새 파이버 = v4a — body 는 fork 시점 값이 복사돼 넘어간다)

# ── 운영 (Cloud Run) ──

[idx2] failure catch                                ← 신규
    - OK route : go to [40]
    - ERROR route : go to [idx4]
[40] http requests
    - go to [idx3]                                  ← 변경: [47] → [idx3]
    - variables
        <input>
        - request url: "https://mewtype-telegram-lk3cg7l7ka-an.a.run.app/ingest"
        - request method: POST
        - request content type: WWW form
        - request content body: body
        - request headers: ```
            {
                "X-ingest-Secret": [INGEST_SECRET]
            }
            ```
        - save response: (비움)                     ← 변경: 파일 `ingest` 저장 해제 — 동시 파이버 파일 충돌 원인
        - timeout: 10s                              (접속 제한 시간 — 응답 대기는 아님)
        <output>
        - response status code: httpcode_prod       ← 변경: 이름 구분(로그 읽기용)
        - response content: httpresp_prod
[idx3] log append                                   ← 신규
    - message: "prod http=" ++ httpcode_prod ++ " tag=" ++ coalesce(nx["pde_noti_tag"], nx["chime.slot_key"], "-")
    - go to end
[idx4] log append                                   ← 신규: 운영 전송 실패
    - message: "prod FAIL " ++ <failure catch 의 실패 메시지 출력 변수> ++ " tag=" ++ coalesce(nx["pde_noti_tag"], nx["chime.slot_key"], "-")
    - go to end

# ── v4a (로컬 PC, Tailscale) ──

[idx5] variable set                                 ← 신규: 재시도 횟수
    - variable: tries
    - value: 0
    - go to [idx6]
[idx6] failure catch                                ← 신규
    - OK route : go to [47]
    - ERROR route : go to [idx8]
[47] http requests
    - for v4a test
    - go to [idx7]                                  ← 변경: [41] → [idx7]
    - variables
        <input>
        - request url: "http://<tailscaleIP>:8787/ingest"   ← 확인: 러너는 TLS 없는 http, 포트 8787 (현행 문서 표기는 https · 포트 없음)
        - request method: POST
        - request content type: WWW form
        - request content body: body
        - request headers: ```
            {
                "X-ingest-Secret": [INGEST_SECRET_LOCAL]
            }
            ```
        - save response: (비움)
        - timeout: 10s
        <output>
        - response status code: httpcode_v4a
        - response content: httpresp_v4a
[idx7] log append                                   ← 신규 ([41] 대체 — nx 전체 대신 결과만)
    - message: "v4a http=" ++ httpcode_v4a ++ " try=" ++ tries ++ " tag=" ++ coalesce(nx["pde_noti_tag"], nx["chime.slot_key"], "-")
    - go to end
[idx8] log append                                   ← 신규: v4a 전송 실패
    - message: "v4a FAIL try=" ++ tries ++ " " ++ <failure catch 의 실패 메시지 출력 변수>
    - go to [idx9]
[idx9] variable set                                 ← 신규
    - variable: tries
    - value: tries + 1
    - go to [idx10]
[idx10] expression true?                            ← 신규: 최대 3회
    - formula: `tries < 3`
    - YES route: go to [idx11]
    - NO route: end                                 (3회 모두 실패 → 서버 쪽 유실. 로그 [idx8] 에 남음)
[idx11] delay                                       ← 신규
    - duration: 5s
    - go to [idx6]                                  (failure catch 를 다시 거쳐 재시도)

[41] log append                                     ← 삭제 후보: [idx3] · [idx7] 로 대체
                                                       (nx 전체 덤프가 필요하면 [46] 이 이미 남긴다)
```

---

## 확인이 필요한 것 (작성자가 추측으로 채우지 않은 부분)

- **failure catch 블록의 출력 변수 이름** — 실패 메시지를 받는 출력 칸 이름을 확인하고 `[idx4]` · `[idx8]` 의
  `<failure catch 의 실패 메시지 출력 변수>` 를 그 변수로 바꿀 것. 출력이 없으면 고정 문구만 남겨도 된다.
- **failure catch 가 걸리는 범위** — 같은 파이버에서 그 뒤에 실행되는 블록의 실패를 잡는다는 전제로 그렸다.
  `[idx11]` → `[idx6]` 으로 되돌아가 다시 catch 를 거는 구조가 Automate 에서 의도대로 도는지 1회 시험 권장
  (예: 러너를 끈 상태에서 알림 1건 → 로그에 `v4a FAIL try=0/1/2` 3줄이 남는지).
- **`[47]` 주소** — 현행 문서는 `https://<tailscaleIP>/ingest` 인데 러너는 `http://100.79.146.124:8787` 로 떠 있다
  (`_local/ops/runner.json`). 실제 폰 설정 값으로 맞출 것.
- **Fork 의 OK/NEW** — 현행 `[35]` · `[42]` 와 같은 뜻(OK = 이 파이버가 계속, NEW = 새 파이버)으로 썼다.
- **재시도 간격 · 횟수(5초 × 3회)** — 임의 기본값. 재시도는 접속 실패(요청이 서버에 닿기 전)를 겨냥한 것이다.
  v4a 가 요청을 이미 처리했는데 응답만 늦어 실패로 잡히면 같은 알림이 다시 들어간다 — 소식(이미 본 글) · 개인 트윗(같은 내용이면
  그대로) · 공식 스케줄(같은 행 다시 머지)은 **데이터가 중복되지는 않지만**, 공식 스케줄 요약 DM 은 바뀐 게 없어도 다시 나간다
  (`telegram_app._ingest_impl` 이 요약 DM 을 조건 없이 보냄). 현재 `[47]` 의 실패는 전부 접속 실패라 이 경우는 드물다.
