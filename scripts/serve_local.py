"""프론트 로컬 확인 서버 — 이 저장소를 그대로 열고 /data/*.json 만 운영 데이터 저장소에서 받아 넘긴다.

프론트는 *.vercel.app 이 아니면 /data/xxx.json 을 읽으므로 `python -m http.server` 만으로는 데이터가 404 다.
쓰기는 하지 않는다. 사용: python scripts/serve_local.py [포트] [주소]  →  http://localhost:8099/ (주소 기본값 127.0.0.1, Tailscale 로 열려면 그 IP)
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
HOST = sys.argv[2] if len(sys.argv) > 2 else "127.0.0.1"


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":   # 메인 페이지로 — tailscale serve 로 열어도 주소가 짧다
            self.send_response(302)
            self.send_header("Location", "/src/frontend/")
            self.end_headers()
            return
        if not path.startswith(("/data/", "/src/frontend/", "/fixtures/")):   # 저장소의 다른 파일은 내주지 않는다
            self.send_error(404)
            return
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
# 대기열 기본값 5 는 tailscale serve(HTTP/2 로 파일을 한꺼번에 요청) 앞에서 넘쳐 연결이 거부된다 → 일부 CSS · main.js 를 못 받아 화면이 비었다(2026-11-04)
socketserver.ThreadingTCPServer.request_queue_size = 128
with socketserver.ThreadingTCPServer((HOST, PORT), functools.partial(Handler, directory=str(ROOT))) as server:
    print(f"http://{HOST}:{PORT}/", flush=True)
    server.serve_forever()
