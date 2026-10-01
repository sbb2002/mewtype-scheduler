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
    - go to [48]                                  ← 변경: [40] → [48]
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
    - go to [48]                                  ← 변경: [40] → [48]
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
# 변수 규칙: 새 이름은 그 블록의 <output> 칸에서 처음 선언한다. HTTP 결과는 현행 이름(httpcode · httppresp)을 그대로 쓴다 —
# [48] Fork 뒤 두 파이버는 변수를 각자 복사본으로 가지므로 운영 · v4a 가 같은 이름을 써도 서로 덮지 않는다.

[48] fork                                         ← 신규: 운영 · v4a 를 다른 파이버로
    - OK route : go to [49]      (이 파이버 = 운영)
    - NEW route : go to [51]     (새 파이버 = v4a — body · nx 는 fork 시점 값이 복사돼 넘어간다)

# ── 운영 (Cloud Run) ──

[49] failure catch                                ← 신규
    - OK route : go to [40]
    - ERROR route : go to [53]
    - variables
        <input>
        - retry limit: 0                            (운영은 재시도 안 함 — 아래 「확인이 필요한 것」 참고)
        <output>
        - retry count: prod_retry                   (신규 선언)
        - failure block id: prod_fail_block         (신규 선언)
        - failure type: prod_fail_type              (신규 선언)
        - failure message: prod_fail_msg            (신규 선언)
[40] http requests
    - go to [50]                                  ← 변경: [47] → [50]
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
        - response status code: httpcode            (현행 그대로)
        - response content or filename: httppresp   (현행 그대로 — 파일 저장을 끄면 내용이 들어온다)
[50] log append                                   ← 신규
    - message: "prod http=" ++ httpcode ++ " tag=" ++ coalesce(nx["pde_noti_tag"], nx["chime.slot_key"], "-")
    - go to end
[53] log append                                   ← 신규: 운영 전송 실패
    - message: "prod FAIL block=" ++ prod_fail_block ++ " " ++ prod_fail_type ++ ": " ++ prod_fail_msg ++ " tag=" ++ coalesce(nx["pde_noti_tag"], nx["chime.slot_key"], "-")
    - go to end

# ── v4a (로컬 PC, Tailscale) ──

[51] failure catch                                ← 신규 (재시도는 이 블록의 retry limit 으로 — 별도 반복 블록 없음)
    - OK route : go to [47]
    - ERROR route : go to [54]
    - variables
        <input>
        - retry limit: 2                            (실패한 블록을 2번 더 시도 = 최대 3회. 1회 접속 대기 10초)
        <output>
        - retry count: v4a_retry                    (신규 선언)
        - failure block id: v4a_fail_block          (신규 선언)
        - failure type: v4a_fail_type               (신규 선언)
        - failure message: v4a_fail_msg             (신규 선언)
[47] http requests
    - for v4a test
    - go to [52]                                  ← 변경: [41] → [52]
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
        - response status code: httpcode            (현행 그대로)
        - response content or filename: httppresp   (현행 그대로)
[52] log append                                   ← 신규 ([41] 대체 — nx 전체 대신 결과만)
    - message: "v4a http=" ++ httpcode ++ " retry=" ++ v4a_retry ++ " tag=" ++ coalesce(nx["pde_noti_tag"], nx["chime.slot_key"], "-")
    - go to end
[54] log append                                   ← 신규: v4a 전송 실패(재시도까지 모두 실패)
    - message: "v4a FAIL retry=" ++ v4a_retry ++ " block=" ++ v4a_fail_block ++ " " ++ v4a_fail_type ++ ": " ++ v4a_fail_msg ++ " tag=" ++ coalesce(nx["pde_noti_tag"], nx["chime.slot_key"], "-")
    - go to end


## disconnected(deprecated)
[41] log append                                     ← 삭제 후보: [50] · [52] 으로 대체
                                                       (nx 전체 덤프가 필요하면 [46] 이 이미 남긴다)