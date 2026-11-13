"""(실험 브랜치 bg-dome-claude-test 전용 · main 병합 금지) 시선 튐 기록용 확인 서버 — scripts/serve_local.py 와 같은 동작 + POST /__gazelog 로 받은 줄을 CSV 에 이어 쓴다.

사용: python scripts/serve_gazelog.py [포트]  →  기록은 _local/gazelog/<세션>.csv
"""
import functools
import http.server
import pathlib
import re
import socketserver
import sys
import threading
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "_local" / "gazelog"   # git 제외 폴더
OUT.mkdir(parents=True, exist_ok=True)
RAW = "https://raw.githubusercontent.com/sbb2002/mewtype-scheduler-data/data/"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8102
LOCK = threading.Lock()
CACHE = {}   # 데이터는 한 번만 받아 둔다(raw 429 방지)


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            self.send_response(302)
            self.send_header("Location", "/src/frontend/")
            self.end_headers()
            return
        if not path.startswith(("/data/", "/src/frontend/", "/fixtures/")):
            self.send_error(404)
            return
        if path.startswith("/data/") and path.endswith(".json"):
            try:
                if path not in CACHE:
                    with urllib.request.urlopen(RAW + path[len("/data/"):], timeout=8) as r:
                        CACHE[path] = r.read()
                body = CACHE[path]
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                self.send_error(502)
            return
        super().do_GET()

    def do_POST(self):
        u = urllib.parse.urlsplit(self.path)
        if u.path != "/__gazelog":
            self.send_error(404)
            return
        sid = re.sub(r"[^0-9A-Za-z_-]", "", urllib.parse.parse_qs(u.query).get("sid", [""])[0])[:40]
        n = int(self.headers.get("Content-Length") or 0)
        if not sid or n <= 0 or n > 4_000_000:
            self.send_error(400)
            return
        body = self.rfile.read(n)
        with LOCK, open(OUT / f"{sid}.csv", "ab") as f:
            f.write(body)
        self.send_response(204)
        self.end_headers()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *args):
        pass


socketserver.ThreadingTCPServer.allow_reuse_address = True
socketserver.ThreadingTCPServer.request_queue_size = 128
with socketserver.ThreadingTCPServer(("127.0.0.1", PORT), functools.partial(Handler, directory=str(ROOT))) as server:
    print(f"http://127.0.0.1:{PORT}/", flush=True)
    server.serve_forever()
