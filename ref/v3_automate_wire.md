# 배선
[1] flow beginning
    - go to [2]
[2] fork stop with
    - OK route: go to [3]
    - NEW route: go to [5]
[3] when notification
    - go to [4]
    - variables
        <input>
        - package: com.sec.android.app.sbrowser
        <output>
        - posted package: pkg
        - title: ntitle
        - message: nmsg
        - nticker: nticker
        - dictionary of extras: nx
[4] fork stop with
    - OK route : go to [3]
    - NEW route : [log1]
[5] when notification
    - go to [6]
    - variables
        <input>
        - package: com.google.android.youtube
        <output>
        - posted package: pkg
        - title: ntitle
        - message: nmsg
        - nticker: nticker
        - dictionary of extras: nx
[6] fork stop with
    - OK route : go to [5]
    - NEW route : [log1]
[log1] log append
    - go to [log2]
    - message: pkg
[log2] log append
    - go to [7]
    - message: nx
[7] expression true?
    - formula: `pkg = "com.google.android.youtube" && trim(coalesce(nx["chime.slot_key"], "")) != "" && contains(coalesce(nx["chime.thread_id"], ""), "LIVESTREAM") != 0`
    - YES route: go to [8]
    - NO route: go to [9]
[8] variable set
    - go to [11]
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

[9] expression true?
    - formula: `pkg = "com.sec.android.app.sbrowser" && contains(coalesce(nx["android.template"], ""), "BigTextStyle") != 0 && contains(coalesce(nx["pde_noti_tag"], ""), "#1tweet-") != 0 && trim(coalesce(nx["android.text"], nx["android.bigText"], "")) != ""`
    - YES route: go to [10]
    - NO route: end
[10] variable set
    - go to [11]
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
[11] http requests
    - go to [12]
    - variables
        <input>
        - request url: "https://mewtype-telegram-lk3cg7l7ka-an.a.run.app/ingest"
        - request method: POST
        - request content type: WWW form
        - request content body: body
        - request headers: ```
            {
                "X-ingest-Secret": [env 참고]
            }
            ```
        - timeout: 10s
        <output>
        - response status code: httpcode
        - response content or filename: httppresp
[12] log append
    -message: nx