"""YouTube PubSubHubbub(WebSub) 구독 시험기 — 앱과 별개. 채널별로 구독 → 허브 검증(GET) → 알림(POST) 수신을 기록한다.

    python pubsub_probe.py <공개 베이스 URL> <시간(분)>
공개 URL 은 ngrok 등으로 이 프로세스의 포트(8795)에 연결된 주소. 콜백 경로에 임의 비밀을 넣어 아무나 두드리지 못하게 한다.
"""
import json
import secrets
import sys
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT = 8795
HUB = "https://pubsubhubbub.appspot.com/subscribe"
OUT = Path(__file__).with_name("pubsub_probe.log")
CFG = json.loads(Path(r"C:/Users/user/Documents/myprojects/mewtype-scheduler-test-fullauto-hotfix/config/channels.json").read_text(encoding="utf-8"))
CHANNELS = {k: v["channel_id"] for k, v in CFG["channels"].items()}
CHANNELS.update({"topic:" + s["key"]: s["channel_id"] for s in CFG.get("song_feeds") or []})
SECRET = secrets.token_urlsafe(12)
BY_ID = {v: k for k, v in CHANNELS.items()}
lock = threading.Lock()


def log(kind, **kw):
    line = json.dumps({"t": time.strftime("%Y-%m-%d %H:%M:%S"), "kind": kind, **kw}, ensure_ascii=False)
    with lock:
        OUT.open("a", encoding="utf-8").write(line + "\n")
    print(line, flush=True)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _ok(self, code, body=b""):
        self.send_response(code)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # 허브의 구독 검증
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        parts = u.path.strip("/").split("/")
        if len(parts) != 3 or parts[0] != "cb" or parts[1] != SECRET or parts[2] not in CHANNELS:
            return self._ok(404)
        topic = (q.get("hub.topic") or [""])[0]
        cid = CHANNELS[parts[2]]
        if cid not in topic or (q.get("hub.mode") or [""])[0] not in ("subscribe", "unsubscribe"):
            return self._ok(404)
        log("verify", channel=parts[2], mode=q.get("hub.mode"), lease=q.get("hub.lease_seconds"))
        self._ok(200, (q.get("hub.challenge") or [""])[0].encode())

    def do_POST(self):  # 알림(Atom)
        u = urllib.parse.urlparse(self.path)
        parts = u.path.strip("/").split("/")
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(min(n, 200000)).decode("utf-8", "replace")
        if len(parts) != 3 or parts[0] != "cb" or parts[1] != SECRET or parts[2] not in CHANNELS:
            return self._ok(404)
        log("notify", channel=parts[2], bytes=n, body=body[:1500])
        self._ok(204)


def subscribe(base, name, cid, lease=432000):
    data = urllib.parse.urlencode({
        "hub.callback": f"{base}/cb/{SECRET}/{name}", "hub.mode": "subscribe", "hub.verify": "async",
        "hub.topic": f"https://www.youtube.com/xml/feeds/videos.xml?channel_id={cid}", "hub.lease_seconds": lease,
    }).encode()
    try:
        r = urllib.request.urlopen(urllib.request.Request(HUB, data=data), timeout=20)
        log("subscribe", channel=name, http=r.status)
    except Exception as e:  # noqa: BLE001
        log("subscribe", channel=name, error=f"{type(e).__name__}: {e}"[:200], body=(getattr(e, "read", lambda: b"")() or b"")[:200].decode("utf-8", "replace"))


def main():
    base, minutes = sys.argv[1].rstrip("/"), float(sys.argv[2])
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log("start", base=base, channels=list(CHANNELS))
    for name, cid in CHANNELS.items():
        subscribe(base, name, cid)
        time.sleep(1)
    end = time.time() + minutes * 60
    while time.time() < end:
        time.sleep(5)
    log("end")


if __name__ == "__main__":
    main()
