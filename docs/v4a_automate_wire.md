# 배선
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
    - go to [40]
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
    - go to [40]
    - variable: body
    - values: 
        ```
        urlEncode(
            {
                "source": "x",
                "text": coalesce(nx["android.text"], nx["android.bigText"], nmsg, nticker, ""),
                "title": coalesce(nx["android.title"], ""),
                "template": coalesce(nx["template"], ""),
                "tag": coalesce(nx["pde_noti_tag"], ""))
            }
        )
        ```
[40] http requests
    - go to [47]
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
        - timeout: 10s
        <output>
        - response status code: httpcode
        - response content or filename: httppresp
[47] http requests
    - for v4a test
    - go to [41]
    - variables
        <input>
        - request url: "https://<tailscaleIP>/ingest"
        - request method: POST
        - request content type: WWW form
        - request content body: body
        - request headers: ```
            {
                "X-ingest-Secret": [INGEST_SECRET_LOCAL]
            }
            ```
        - timeout: 10s
        <output>
        - response status code: httpcode
        - response content or filename: httppresp
[41] log append
    -message: nx