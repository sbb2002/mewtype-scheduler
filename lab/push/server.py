"""(test/live-notify) 라이브 알림 실험실 — 로컬 전용 최소 구현(Firestore 방향).

    python lab/push/server.py        → http://localhost:8770/     팬 화면(실제 프론트)
                                      http://localhost:8770/lab  서버 쪽 보기(등록 · 저장소 · 발송)

팬 화면은 src/frontend 를 그대로 띄우고, /data/preview.json 만 이 실험실이 들고 있는 사본을 준다
(시작할 때 운영 data 브랜치 preview.json 을 한 번 받아 온다 — 실패하면 fixtures 샘플). 나머지 /data/*.json 은 운영 것을 그대로 중계.
/lab 에서 방송 상태를 바꾸면(→ live) 등록자에게 Web Push 를 보낸다.

저장소 = Firestore 를 흉내 낸 로컬 문서 저장소(DocStore). 구독 1개 = 문서 1개(문서 id = 푸시 주소 해시).
운영에선 같은 동작을 Firestore 컬렉션 하나로 한다 — get · set · delete · array_contains 조회만 쓴다.

서버 쪽 방어(최소):
  - 응답은 늘 202 — 무엇을 하든 팬 화면은 같다
  - 크기 초과 · 형식 오류 → 조용히 버림
  - 내용이 같으면 쓰지 않음(읽기 1건으로 끝 — Firestore 무료 한도는 읽기가 쓰기의 2.5배)
  - 하루 쓰기 상한(DAILY_WRITE_CAP, 쓰기 + 삭제) — 넘으면 그날은 더 쓰지 않음(무료 한도를 넘겨 과금되지 않게).
    하루 기준은 Firestore 무료 한도와 같은 태평양 시간 자정.
연타는 프론트가 막는다(마지막 조작 뒤 2초 조용하면 최종 상태 1건만 보냄).
"""
import base64
import collections
import hashlib
import json
import os
import queue
import random
import re
import string
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from py_vapid import Vapid
from pywebpush import WebPushException, webpush

PORT = 8770
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
FRONT = os.path.join(ROOT, "src", "frontend")
DATA_DIR = os.path.join(HERE, ".data")          # gitignore — 구독 저장소 · VAPID 키
RAW = "https://raw.githubusercontent.com/sbb2002/mewtype-scheduler-data/data/"

MAX_BODY = 4096
DAILY_WRITE_CAP = int(os.environ.get("LAB_WRITE_CAP", "10000"))   # Firestore 무료 쓰기 하루 2만의 절반
MAX_VIDEOS = 30
PUSH_TTL = 1800                                   # 브라우저가 꺼져 있으면 푸시 서버가 30분까지만 보관
MEMBER_KEYS = {"arale", "yuno", "nonoka", "ritsu", "miyako"}
PUSH_HOSTS = ("fcm.googleapis.com", "updates.push.services.mozilla.com", "web.push.apple.com",
              ".notify.windows.com", ".push.apple.com")
VID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
try:
    PACIFIC = ZoneInfo("America/Los_Angeles")
except Exception:  # noqa: BLE001 — Windows 에 tzdata 가 없으면 고정 UTC-8(서머타임 1시간 차이는 시험판이라 무시)
    PACIFIC = timezone(timedelta(hours=-8))

os.makedirs(DATA_DIR, exist_ok=True)
KEY_PEM = os.path.join(DATA_DIR, "vapid_private.pem")

# ── VAPID ────────────────────────────────────────────────────────────
if os.path.exists(KEY_PEM):
    _vapid = Vapid.from_file(KEY_PEM)
else:
    _vapid = Vapid()
    _vapid.generate_keys()
    _vapid.save_key(KEY_PEM)
VAPID_PUBLIC = base64.urlsafe_b64encode(
    _vapid.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)).rstrip(b"=").decode()

LOG = collections.deque(maxlen=300)
STATS = collections.Counter()
NOTIFIED: set = set()
SEND_Q: "queue.Queue" = queue.Queue()
PREVIEW: dict = {}
PREVIEW_LOCK = threading.Lock()
NAMES = {"arale": "아라레", "yuno": "유노", "nonoka": "노노카", "ritsu": "리츠", "miyako": "미야코"}


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def hhmmss() -> str:
    return time.strftime("%H:%M:%S")


def log(kind: str, msg: str) -> None:
    LOG.appendleft({"t": hhmmss(), "kind": kind, "msg": msg})
    print(f"[{hhmmss()}] {kind:6} {msg}", flush=True)


# ── 문서 저장소 ──────────────────────────────────────────────────────
# 구독 1개 = 문서 1개. 쓰는 연산은 get · set · delete · array-contains-any 조회뿐이고, 연산 수를 센다(Firestore 무료 한도 대조용).
# FIRESTORE_EMULATOR_HOST 가 있으면 실제 Firestore 클라이언트(에뮬레이터), 없으면 같은 동작의 로컬 파일 저장소.
class _OpCounter:
    def __init__(self):
        self.lock = threading.Lock()
        self.ops = collections.Counter()   # 오늘(태평양 시간) 연산 수 — read · write · delete
        self.day = self._today()

    @staticmethod
    def _today() -> str:
        return datetime.now(PACIFIC).strftime("%Y-%m-%d")

    def _roll(self) -> None:
        if self._today() != self.day:
            self.day, self.ops = self._today(), collections.Counter()

    def _count(self, kind: str, n: int = 1) -> None:
        with self.lock:
            self._roll()
            self.ops[kind] += n

    def writes_today(self) -> int:
        with self.lock:
            self._roll()
            return self.ops["write"] + self.ops["delete"]

    def ops_today(self) -> tuple:
        with self.lock:
            self._roll()
            return dict(self.ops), self.day


class DocStore(_OpCounter):
    """로컬 파일 저장소(Firestore 흉내)."""
    kind = "로컬 파일(Firestore 흉내)"

    def __init__(self, path: str):
        super().__init__()
        self.path = path
        self.docs: dict = {}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self.docs = json.load(f)

    def _persist(self) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.docs, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")

    def get(self, doc_id: str):
        self._count("read")
        with self.lock:
            d = self.docs.get(doc_id)
            return dict(d) if d else None

    def set(self, doc_id: str, doc: dict) -> None:
        self._count("write")
        with self.lock:
            self.docs[doc_id] = doc
            self._persist()

    def delete(self, doc_id: str) -> None:
        self._count("delete")
        with self.lock:
            self.docs.pop(doc_id, None)
            self._persist()

    def where_array_contains_any(self, field: str, values: list) -> dict:
        with self.lock:
            hit = {k: dict(v) for k, v in self.docs.items() if set(v.get(field) or []) & set(values)}
        self._count("read", max(1, len(hit)))   # Firestore 는 결과 0건이어도 읽기 1건
        return hit

    def all(self) -> dict:          # 실험실 보기용(연산 수에 안 넣음)
        with self.lock:
            return {k: dict(v) for k, v in self.docs.items()}

    def purge(self, ids: list) -> None:   # 실험실 청소용(연산 수에 안 넣음)
        with self.lock:
            for k in ids:
                self.docs.pop(k, None)
            self._persist()


class FirestoreStore(_OpCounter):
    """실제 Firestore 클라이언트 — 컬렉션 하나. 운영에서도 이 연산만 쓴다."""
    kind = "Firestore"

    def __init__(self, collection: str = "push_subs"):
        super().__init__()
        from google.cloud import firestore
        from google.cloud.firestore_v1.base_query import FieldFilter
        self._ff = FieldFilter
        self.client = firestore.Client(project=os.environ.get("GOOGLE_CLOUD_PROJECT", "mewtype-lab"))
        self.col = self.client.collection(collection)
        self.kind = f"Firestore 에뮬레이터 {os.environ['FIRESTORE_EMULATOR_HOST']}" \
            if os.environ.get("FIRESTORE_EMULATOR_HOST") else "Firestore"

    def get(self, doc_id: str):
        self._count("read")
        snap = self.col.document(doc_id).get()
        return snap.to_dict() if snap.exists else None

    def set(self, doc_id: str, doc: dict) -> None:
        self._count("write")
        self.col.document(doc_id).set(doc)

    def delete(self, doc_id: str) -> None:
        self._count("delete")
        self.col.document(doc_id).delete()

    def where_array_contains_any(self, field: str, values: list) -> dict:
        hit = {d.id: d.to_dict() for d in self.col.where(filter=self._ff(field, "array_contains_any", values)).stream()}
        self._count("read", max(1, len(hit)))
        return hit

    def all(self) -> dict:
        return {d.id: d.to_dict() for d in self.col.stream()}

    def purge(self, ids: list) -> None:
        batch = self.client.batch()
        for i, k in enumerate(ids, 1):
            batch.delete(self.col.document(k))
            if i % 400 == 0:
                batch.commit()
                batch = self.client.batch()
        batch.commit()


LOCAL_PATH = os.path.join(DATA_DIR, "subs.json")
STORE = FirestoreStore() if os.environ.get("FIRESTORE_EMULATOR_HOST") else DocStore(LOCAL_PATH)


def sid_of(endpoint: str) -> str:
    return hashlib.sha256(endpoint.encode()).hexdigest()[:16]


def validate(body) -> tuple:
    if not isinstance(body, dict):
        return None, "형식 오류"
    sub = body.get("sub") or {}
    ep = sub.get("endpoint") or ""
    keys = sub.get("keys") or {}
    host = urlparse(ep).hostname or ""
    if not ep.startswith("https://") or not any(host == h or (h.startswith(".") and host.endswith(h)) for h in PUSH_HOSTS):
        return None, "푸시 주소가 아님"
    if not (isinstance(keys.get("p256dh"), str) and isinstance(keys.get("auth"), str)
            and len(keys["p256dh"]) < 200 and len(keys["auth"]) < 64):
        return None, "키 형식 오류"
    members, videos = body.get("members"), body.get("videos")
    if not isinstance(members, list) or not set(members) <= MEMBER_KEYS:
        return None, "멤버 목록 오류"
    if (not isinstance(videos, list) or len(videos) > MAX_VIDEOS
            or not all(isinstance(v, str) and VID_RE.match(v) for v in videos)):
        return None, "영상 목록 오류"
    return {"endpoint": ep, "keys": {"p256dh": keys["p256dh"], "auth": keys["auth"]},
            "members": sorted(set(members)), "videos": sorted(set(videos)),
            "fake": "/lab-fake-" in ep}, None


def apply_state(rec: dict) -> str:
    """등록 상태 1건을 저장소에 반영하고 무엇을 했는지 돌려준다."""
    sid = sid_of(rec["endpoint"])
    empty = not rec["members"] and not rec["videos"]
    cur = STORE.get(sid)                                        # 읽기 1
    if empty and cur is None:
        return "없는 구독 해지 — 아무것도 안 함"
    if cur and not empty and cur["members"] == rec["members"] and cur["videos"] == rec["videos"] \
            and cur["keys"] == rec["keys"]:
        STATS["same"] += 1
        return "내용 같음 — 안 씀"
    if STORE.writes_today() >= DAILY_WRITE_CAP:
        STATS["capped"] += 1
        return f"오늘 쓰기 상한 {DAILY_WRITE_CAP} 도달 — 안 씀"
    if empty:
        STORE.delete(sid)                                       # 삭제 1
        STATS["deleted"] += 1
        return "해지 — 문서 삭제"
    STORE.set(sid, {**rec, "updated": now_iso()})               # 쓰기 1
    STATS["written"] += 1
    return "문서 갱신" if cur else "문서 새로 만듦"


# ── 미리보기 사본 ────────────────────────────────────────────────────
def load_preview() -> None:
    global PREVIEW
    try:
        with urllib.request.urlopen(RAW + "preview.json", timeout=10) as r:
            PREVIEW = json.load(r)
        log("시작", f"운영 preview.json 사본 {len(PREVIEW.get('items', []))}건")
    except Exception as e:  # noqa: BLE001
        with open(os.path.join(ROOT, "fixtures", "preview.sample.json"), encoding="utf-8") as f:
            PREVIEW = json.load(f)
        log("시작", f"운영 사본 실패({e}) → fixtures 샘플")


def item_key(it: dict) -> str:
    return it.get("id") or it.get("video_id") or ""


# ── 발송 ─────────────────────────────────────────────────────────────
def on_live(it: dict) -> None:
    vid = it.get("video_id")
    if not vid:
        return
    if vid in NOTIFIED:
        log("발송", f"{vid} 이미 보냄 — 건너뜀")
        return
    NOTIFIED.add(vid)
    chans = sorted(c for c in {it.get("channel_key"), *(it.get("collab_with") or [])} if c)
    # Firestore 조회 2번 — 멤버를 켠 문서 + 이 영상을 등록한 문서, 문서 id 로 합친다
    targets = {**STORE.where_array_contains_any("members", chans), **STORE.where_array_contains_any("videos", [vid])}
    targets = {sid: d for sid, d in targets.items() if not d.get("fake")}
    who = " · ".join(NAMES.get(c, c) for c in chans)
    extra = " · 회원 전용" if it.get("membership") else ""
    log("감지", f"{who} live — {vid}{extra} → 발송 대상 {len(targets)}명")
    if targets:
        SEND_Q.put((it, who, targets))


def send_loop() -> None:
    while True:
        it, who, targets = SEND_Q.get()
        payload = json.dumps({
            "title": f"{who} 라이브 시작",
            "body": it.get("title") or "",
            "url": it.get("url") or f"https://www.youtube.com/watch?v={it.get('video_id')}",
            "tag": it.get("video_id"),
        }, ensure_ascii=False)
        t0 = time.monotonic()
        ok = gone = fail = 0
        for sid, d in targets.items():
            try:
                webpush(subscription_info={"endpoint": d["endpoint"], "keys": d["keys"]}, data=payload,
                        vapid_private_key=KEY_PEM, vapid_claims={"sub": "mailto:lab@example.com"}, ttl=PUSH_TTL)
                ok += 1
            except WebPushException as e:
                code = getattr(e.response, "status_code", None)
                if code in (404, 410):
                    gone += 1
                    STORE.delete(sid)
                    log("정리", f"구독 {sid[:10]} 만료({code}) → 문서 삭제")
                else:
                    fail += 1
                    log("실패", f"구독 {sid[:10]}: {code} {str(e)[:120]}")
        STATS["sent"] += ok
        log("발송", f"{who} — 성공 {ok} · 만료 삭제 {gone} · 실패 {fail} ({time.monotonic() - t0:.2f}초)")


# ── HTTP ─────────────────────────────────────────────────────────────
CTYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8",
          ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8", ".svg": "image/svg+xml",
          ".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp", ".ico": "image/x-icon", ".woff2": "font/woff2"}
_raw_cache: dict = {}


def raw_proxy(name: str):
    hit = _raw_cache.get(name)
    if hit and time.time() - hit[0] < 60:
        return hit[1]
    try:
        with urllib.request.urlopen(RAW + name, timeout=10) as r:
            body = r.read()
    except Exception:  # noqa: BLE001
        body = None
    _raw_cache[name] = (time.time(), body)
    return body


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes = b"", ctype: str = "text/plain; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/lab":
            with open(os.path.join(HERE, "lab.html"), "rb") as f:
                return self._send(200, f.read(), CTYPES[".html"])
        if path == "/lab/api":
            return self._json(lab_snapshot())
        if path == "/push/vapid":
            return self._send(200, VAPID_PUBLIC.encode())
        if path == "/data/preview.json":
            with PREVIEW_LOCK:
                body = json.dumps(PREVIEW, ensure_ascii=False).encode()
            return self._send(200, body, CTYPES[".json"])
        if path.startswith("/data/") and path.endswith(".json"):
            body = raw_proxy(path[len("/data/"):])
            return self._send(200, body, CTYPES[".json"]) if body is not None else self._send(404, b"not found")
        rel = "index.html" if path == "/" else path.lstrip("/")
        full = os.path.realpath(os.path.join(FRONT, rel))
        if not full.startswith(os.path.realpath(FRONT)) or not os.path.isfile(full):
            return self._send(404, b"not found")
        with open(full, "rb") as f:
            self._send(200, f.read(), CTYPES.get(os.path.splitext(full)[1], "application/octet-stream"))

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/push/state":
            return self.push_state()
        if path == "/lab/item":
            return self._json(lab_set_state(**self._body()))
        if path == "/lab/new":
            return self._json(lab_new(**self._body()))
        if path == "/lab/reset":
            NOTIFIED.clear()
            log("시험", "보냄 기록 초기화")
            return self._json({"ok": True})
        if path == "/lab/clearfake":
            fakes = [k for k, v in STORE.all().items() if v.get("fake")]
            STORE.purge(fakes)
            log("시험", f"가짜 구독 {len(fakes)}개 지움(연산 수에 안 넣음)")
            return self._json({"ok": True})
        self._send(404, b"not found")

    def push_state(self):
        """응답은 늘 202 — 무엇을 하든 팬 화면은 같다. 실제 처리 결과는 서버 기록에만."""
        STATS["recv"] += 1
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            STATS["bad"] += 1
            return self._send(202, b"accepted")    # 본문은 읽지 않는다(HTTP/1.0 이라 연결이 닫힌다)
        try:
            rec, err = validate(json.loads(self.rfile.read(n) or b"{}"))
        except ValueError:
            rec, err = None, "JSON 아님"
        if err:
            STATS["bad"] += 1
            return self._send(202, b"accepted")
        result = apply_state(rec)
        if not rec["fake"]:
            what = ", ".join([NAMES[m] for m in rec["members"]] + rec["videos"]) or "전부 해지"
            log("요청", f"구독 {sid_of(rec['endpoint'])[:10]} → {what} · {result}")
        self._send(202, b"accepted")

    def log_message(self, *args):
        pass


# ── 실험실 조작 ──────────────────────────────────────────────────────
def lab_snapshot() -> dict:
    with PREVIEW_LOCK:
        items = [{"key": item_key(it), "channel_key": it.get("channel_key"), "state": it.get("state"),
                  "video_id": it.get("video_id"), "title": it.get("title"), "membership": bool(it.get("membership")),
                  "scheduled_start": it.get("scheduled_start")} for it in PREVIEW.get("items", [])]
    docs = STORE.all()
    subs = [{"sid": sid[:10], "members": d["members"], "videos": d["videos"], "updated": d.get("updated", "")[11:19],
             "fake": bool(d.get("fake"))} for sid, d in docs.items()]
    ops, day = STORE.ops_today()
    return {"items": items, "subs": subs, "stats": dict(STATS), "ops": ops, "day": day, "store": STORE.kind,
            "notified": sorted(NOTIFIED), "log": list(LOG),
            "conf": {"cap": DAILY_WRITE_CAP, "max_body": MAX_BODY}}


def lab_set_state(key: str, state: str) -> dict:
    with PREVIEW_LOCK:
        it = next((x for x in PREVIEW.get("items", []) if item_key(x) == key), None)
        if not it or state not in ("upcoming", "watching", "live", "end"):
            return {"ok": False}
        prev = it.get("state")
        it["state"] = state
        it["state_since"] = now_iso()
        it["last_updated"] = now_iso()
        if state == "live" and not it.get("actual_start"):
            it["actual_start"] = now_iso()
        if state in ("upcoming", "watching"):
            it.pop("actual_start", None)
            NOTIFIED.discard(it.get("video_id"))
        snap = dict(it)
    log("시험", f"{NAMES.get(snap.get('channel_key'), '')} {snap.get('video_id') or key}: {prev} → {state}")
    if state == "live" and prev != "live":
        on_live(snap)
    return {"ok": True}


def lab_new(channel_key: str, state: str = "upcoming") -> dict:
    if channel_key not in MEMBER_KEYS:
        return {"ok": False}
    vid = "".join(random.choices(string.ascii_letters + string.digits, k=11))
    start = datetime.now(timezone.utc) + (timedelta(minutes=30) if state == "upcoming" else timedelta())
    it = {"id": f"lab_{vid}", "video_id": vid, "channel_key": channel_key, "state": "upcoming",
          "title": f"[실험실] {NAMES[channel_key]} 시험 방송", "url": f"https://www.youtube.com/watch?v={vid}",
          "scheduled_start": start.strftime("%Y-%m-%dT%H:%M:%SZ"), "first_seen": now_iso(),
          "state_since": now_iso(), "last_updated": now_iso()}
    with PREVIEW_LOCK:
        PREVIEW.setdefault("items", []).insert(0, it)
    log("시험", f"{NAMES[channel_key]} 시험 방송 {vid} 만듦 ({state})")
    if state == "live":
        lab_set_state(it["id"], "live")
    return {"ok": True, "video_id": vid}


def _carry_over() -> None:
    """운영자가 이미 켜 둔 등록을 잇는다(연산 수에 안 넣음).
    로컬 파일: 앞 시험판(10자리 문서 id)을 16자리로. Firestore(에뮬레이터는 끄면 비워짐): 비어 있으면 로컬 파일 내용을 옮겨 심는다."""
    local = {}
    if os.path.exists(LOCAL_PATH):
        with open(LOCAL_PATH, encoding="utf-8") as f:
            local = {sid_of(d["endpoint"]): d for d in json.load(f).values() if not d.get("fake")}
    if isinstance(STORE, DocStore):
        if set(local) != set(STORE.docs):
            with STORE.lock:
                STORE.docs = local
                STORE._persist()
            log("시작", f"앞 시험판 구독 {len(local)}개를 새 문서 id 로 옮김")
    elif local and not STORE.all():
        for k, d in local.items():
            STORE.col.document(k).set(d)
        log("시작", f"로컬 파일 구독 {len(local)}개를 Firestore 에 옮겨 심음")


if __name__ == "__main__":
    _carry_over()
    load_preview()
    threading.Thread(target=send_loop, daemon=True).start()
    log("시작", f"팬 화면 http://localhost:{PORT}/ · 서버 보기 http://localhost:{PORT}/lab · 저장소 {STORE.kind} · 구독 {len(STORE.all())}개")
    ThreadingHTTPServer.request_queue_size = 512   # 기본 5 — 동시 수천 건 시험에서 실험실 서버가 먼저 연결을 거절하지 않게
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
