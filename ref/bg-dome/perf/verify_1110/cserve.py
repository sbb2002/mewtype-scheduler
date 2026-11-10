# 확인용 서버 — 워크트리 프론트 + /data 는 한 번만 받아 캐시(운영 raw 429 방지)
import http.server, os, sys, urllib.request
ROOT = sys.argv[2]; CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
RAW = "https://raw.githubusercontent.com/sbb2002/mewtype-scheduler-data/data/"
class H(http.server.SimpleHTTPRequestHandler):
    def __init__(s, *a, **k): super().__init__(*a, directory=ROOT, **k)
    def log_message(s, *a): pass
    def do_GET(s):
        p = s.path.split("?")[0]
        if p.startswith("/data/") and p.endswith(".json"):
            f = os.path.join(CACHE, os.path.basename(p))
            if not os.path.exists(f):
                try:
                    with urllib.request.urlopen(RAW + p[6:], timeout=8) as r: open(f, "wb").write(r.read())
                except Exception as e: s.send_error(502, str(e)); return
            b = open(f, "rb").read(); s.send_response(200); s.send_header("Content-Type", "application/json"); s.send_header("Content-Length", str(len(b))); s.end_headers(); s.wfile.write(b); return
        return super().do_GET()
http.server.ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
