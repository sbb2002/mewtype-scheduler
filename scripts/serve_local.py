"""프론트 로컬 확인 서버 — 이 저장소를 그대로 열고 /data/*.json 만 운영 데이터 저장소에서 받아 넘긴다.

프론트는 *.vercel.app 이 아니면 /data/xxx.json 을 읽으므로 `python -m http.server` 만으로는 데이터가 404 다.
쓰기는 하지 않는다. 사용: python scripts/serve_local.py [포트]  →  http://localhost:8099/src/frontend/
"""
import functools
import http.server
import pathlib
import socketserver
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = "https://raw.githubusercontent.com/sbb2002/mewtype-scheduler-data/data/"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8099


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]
        if path.startswith("/data/") and path.endswith(".json"):
            try:
                with urllib.request.urlopen(RAW + path[len("/data/"):], timeout=8) as r:
                    body = r.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                self.send_error(502)
            return
        super().do_GET()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *args):
        pass


socketserver.ThreadingTCPServer.allow_reuse_address = True
with socketserver.ThreadingTCPServer(("127.0.0.1", PORT), functools.partial(Handler, directory=str(ROOT))) as server:
    print(f"http://localhost:{PORT}/src/frontend/", flush=True)
    server.serve_forever()
