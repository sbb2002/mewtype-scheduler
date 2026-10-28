# 로컬 확인용 서버: / = 워크트리 src/frontend, /data/ = 내려받은 data 브랜치 사본(+ 시험 글)
import http.server, os, sys, functools
FRONT, DATA, PORT = sys.argv[1], sys.argv[2], int(sys.argv[3])

class H(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        path = path.split("?", 1)[0].split("#", 1)[0]
        if path.startswith("/data/"):
            return os.path.join(DATA, path[len("/data/"):])
        return os.path.join(FRONT, path.lstrip("/"))
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()
    def log_message(self, *a):
        pass

H.extensions_map[".js"] = "text/javascript; charset=utf-8"
H.extensions_map[".mjs"] = "text/javascript; charset=utf-8"
H.extensions_map[".html"] = "text/html; charset=utf-8"
H.extensions_map[".css"] = "text/css; charset=utf-8"
http.server.ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
