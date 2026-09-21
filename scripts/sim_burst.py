"""(v3.8.2) 업스트림 `/ingest` 버스트 시뮬레이터 — 배포 없이 관제소 효과를 검증한다.

한 프로세스 안에 실제 HTTP 서버 4개를 띄운다:
  가짜 GitHub(Contents API 모형) · 관제소(tower_app) · 백엔드(app — concurrency=1 흉내) · 제어 채널(telegram_app)
그리고 업스트림처럼 `/ingest` 를 **동시에** N 개 쏜다. 같은 시나리오를 두 모드로 돌려 비교한다:
  direct — `TOWER_URL` 없음: 제어 채널이 GitHub 를 직접 부름 (관제소 도입 전 = 현재 main 과 같은 경로)
  tower  — `TOWER_URL` 있음: 모든 GitHub 접근이 관제소를 거침

주의 — 이건 **모형**이다. 가짜 GitHub 는 다음만 흉내낸다(실제 GitHub 와 다를 수 있음):
  · 같은 브랜치에 커밋이 겹치면(한 PUT 이 처리 중일 때 다른 PUT 도착) 409  ← 2026-09-16 실사고의 원인 모형
  · 파일 sha 가 어긋나면 409
  · 지연(GET/PUT) 과 ETag(304)
  · 속도 제한은 GitHub 문서의 공식 한도(동시 100 · 분당 900점[GET 1/쓰기 5] · 콘텐츠 생성 80/분)만 적용.
    `--strict-limit` 을 주면 버스트에서도 걸리도록 임계값을 낮춰(동시 6 · 3초 창 쓰기 5) 관제소의 대기 경로를 자극한다.
Cloud Run(cold start·OIDC·인스턴스 수)·Telegram 타임아웃·실제 GitHub 임계값은 검증 범위 밖이다.

사용:
  python scripts/sim_burst.py                       # 버스트 6, 두 모드 비교
  python scripts/sim_burst.py --burst 12 --strict-limit
  python scripts/sim_burst.py --mode tower --burst 8
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import logging
import os
import sys
import threading
import time
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

os.environ.update(GITHUB_TOKEN="t", GITHUB_REPO="o/r", DATA_BRANCH="data", ALLOW_UNAUTH="1",
                  INGEST_SECRET="s", TELEGRAM_CHAT_ID="1")
for k in ("GROQ_API_KEY", "TOWER_URL", "MAIN_SERVICE_URL"):
    os.environ.pop(k, None)

import requests  # noqa: E402
from flask import Flask, jsonify, request  # noqa: E402
from werkzeug.serving import make_server  # noqa: E402

# ─────────────────────────── 가짜 GitHub ───────────────────────────
GET_LAT, PUT_LAT = 0.23, 0.80    # 실제 GitHub Contents API 실측 중앙값 (2026-09-21, 도쿄 리전 밖 클라이언트 기준: GET≈230ms · PUT≈800ms)
UPSTREAM_TIMEOUT_SEC = 10.0      # 업스트림(Automate) HTTP 타임아웃 약 10초 (docs/VERSION.md v3.7.3)


class FakeGitHub:
    def __init__(self, strict: bool):
        self.files: dict[str, tuple[str, str]] = {}
        self.lock = threading.Lock()
        self.put_in_flight = 0
        self.get_in_flight = 0
        self.in_flight = 0
        self.max_in_flight = 0
        self.stats = Counter()
        self.write_times: list[float] = []
        self.minute: list[tuple[float, int]] = []     # (t, points) — 분당 900점
        self.strict = strict
        self.cooldown_until = 0.0
        self.app = Flask("fake_github")
        self.app.logger.disabled = True
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        self.app.add_url_rule("/repos/<o>/<r>/contents/<path:p>", "c", self.handle, methods=["GET", "PUT"])

    def _limited(self, is_write: bool):
        """속도 제한 모형. 걸리면 (retry_after) 반환."""
        now = time.monotonic()
        if now < self.cooldown_until:
            return max(1, int(self.cooldown_until - now + 0.999))
        conc_cap, win, win_cap = (6, 3.0, 5) if self.strict else (100, 60.0, 80)
        hit = False
        if self.in_flight > conc_cap:
            hit = True
        if is_write:
            self.write_times = [t for t in self.write_times if now - t < win]
            if len(self.write_times) >= win_cap:
                hit = True
        self.minute = [(t, p) for t, p in self.minute if now - t < 60]
        if sum(p for _, p in self.minute) >= 900:
            hit = True
        if hit:
            self.cooldown_until = now + 3.0
            return 3
        return None

    def handle(self, o, r, p):
        is_write = request.method == "PUT"
        with self.lock:
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
            self.stats["PUT" if is_write else "GET"] += 1
            limit = self._limited(is_write)
            if limit is not None:
                self.in_flight -= 1
                self.stats["rate_limited"] += 1
                resp = jsonify({"message": "You have exceeded a secondary rate limit."})
                resp.status_code = 403
                resp.headers["retry-after"] = str(limit)
                return resp
            if not is_write and self.put_in_flight > 0:
                self.stats["read_during_write"] += 1        # 읽기 도중/직전에 쓰기가 진행 중
            if is_write and self.get_in_flight > 0:
                self.stats["write_during_read"] += 1        # 쓰기가 진행 중인 읽기와 겹침
            if not is_write:
                self.get_in_flight += 1
            now = time.monotonic()
            self.minute.append((now, 5 if is_write else 1))
            if is_write:
                self.write_times.append(now)
                head_busy = self.put_in_flight > 0        # 다른 커밋이 처리 중 → 브랜치 HEAD 충돌 모형
                self.put_in_flight += 1
        try:
            if not is_write:
                time.sleep(GET_LAT)
                with self.lock:
                    cur = self.files.get(p)
                if cur is None:
                    return jsonify({"message": "Not Found"}), 404
                text, sha = cur
                if request.headers.get("If-None-Match") == f'"{sha}"':
                    with self.lock:
                        self.stats["304"] += 1
                    return "", 304
                resp = jsonify({"content": base64.b64encode(text.encode()).decode(), "sha": sha})
                resp.headers["ETag"] = f'"{sha}"'
                return resp
            time.sleep(PUT_LAT)
            body = request.get_json()
            with self.lock:
                cur = self.files.get(p)
                if head_busy:
                    self.stats["409_head"] += 1
                    return jsonify({"message": "is at X but expected Y"}), 409
                if cur and body.get("sha") != cur[1]:
                    self.stats["409_sha"] += 1
                    return jsonify({"message": "sha does not match"}), 409
                text = base64.b64decode(body["content"]).decode()
                sha = hashlib.sha1(text.encode()).hexdigest()
                self.files[p] = (text, sha)
                self.stats["commit_ok"] += 1
                return jsonify({"content": {"sha": sha}}), 201
        finally:
            with self.lock:
                self.in_flight -= 1
                if is_write:
                    self.put_in_flight -= 1
                else:
                    self.get_in_flight -= 1


class Serial:
    """WSGI 미들웨어: 한 번에 요청 하나 (Cloud Run --concurrency=1 흉내)."""

    def __init__(self, app):
        self.app, self.lock = app, threading.Lock()

    def __call__(self, environ, start_response):
        with self.lock:
            return list(self.app(environ, start_response))


class Srv(threading.Thread):
    def __init__(self, app):
        super().__init__(daemon=True)
        self.srv = make_server("127.0.0.1", 0, app, threaded=True)
        self.port = self.srv.server_port

    def run(self):
        self.srv.serve_forever()

    def stop(self):
        self.srv.shutdown()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.port}"


class WarnCounter(logging.Handler):
    def __init__(self):
        super().__init__(logging.WARNING)
        self.c = Counter()

    def emit(self, record):
        msg = record.getMessage()
        key = ("monitor_log 실패" if "monitor_log" in msg else
               "ConflictError" if "Conflict" in msg or "409" in msg else
               "GitHub 속도 제한" if "속도 제한" in msg else "기타 경고/오류")
        self.c[key] += 1


# ─────────────────────────── 시나리오 ───────────────────────────
MEMBERS = ["仲町あられ", "千石ユノ", "宮永ののか", "峰月律", "藤都子"]


def run(mode: str, burst: int, strict: bool, write_gap: float, max_readers: int) -> dict:
    from src.backend import gh_store, telegram_app as T, towerclient, writeclient
    from src.backend import app as backend_app, tower as tower_mod, tower_app

    gh = FakeGitHub(strict)
    gh_srv = Srv(gh.app)
    gh_srv.start()
    gh_store.GitHubStore.API = gh_srv.url                       # GitHub 대신 가짜 서버로

    # 서비스 간 OIDC 는 우회 (로컬)
    for mod in (towerclient, writeclient):
        mod.fetch_id_token = lambda req, aud: "tok"
        mod.Request = lambda: None

    # 외부 호출·DM 스텁 (네트워크 없음)
    T._send_telegram = lambda *a, **k: True
    T._recover_raw_via_vxtwitter = lambda raw, tag: (raw, None)
    T._enrich_personal_media = lambda tag, prefetched=None: ([], None)
    T._enqueue_wake_now = lambda *a, **k: None
    writeclient._send_wait_notice = lambda kind: None

    servers = [gh_srv]
    backend_srv = Srv(Serial(backend_app.app))                  # 백엔드: concurrency=1
    backend_srv.start(); servers.append(backend_srv)
    os.environ["MAIN_SERVICE_URL"] = backend_srv.url
    backend_app._cfg.cache_clear()

    if mode == "tower":
        tower_app._tower = tower_mod.Tower(gh_store.GitHubStore("t", "o/r", "data", etag_cache={}),
                                           write_gap=write_gap, max_readers=max_readers)
        tower_srv = Srv(tower_app.app)
        tower_srv.start(); servers.append(tower_srv)
        os.environ["TOWER_URL"] = tower_srv.url
    else:
        os.environ.pop("TOWER_URL", None)

    ctrl_srv = Srv(T.app)                                       # 제어 채널: 스레드 넉넉히(최악: 전부 동시)
    ctrl_srv.start(); servers.append(ctrl_srv)

    wc = WarnCounter()
    logging.getLogger().addHandler(wc)

    results: list[tuple[int, dict, float]] = []
    lock = threading.Lock()
    gate = threading.Barrier(burst)

    def fire(i: int):
        text = f"버스트 테스트 트윗 {i} — 오늘도 수고했어요"
        tag = f"p#https://x.com/#1tweet-{2096552878769152000 + i}"
        gate.wait()                                             # 동시 발사
        t0 = time.monotonic()
        try:
            r = requests.post(f"{ctrl_srv.url}/ingest", timeout=90,
                              data={"text": text, "title": MEMBERS[i % len(MEMBERS)], "tag": tag},
                              headers={"X-Ingest-Secret": "s"})
            try:
                body = r.json()
            except ValueError:
                body = {"raw": r.text[:80]}
            out = (r.status_code, body, time.monotonic() - t0)
        except Exception as e:  # noqa: BLE001
            out = (0, {"error": repr(e)[:80]}, time.monotonic() - t0)
        with lock:
            results.append(out)

    t_start = time.monotonic()
    ths = [threading.Thread(target=fire, args=(i,)) for i in range(burst)]
    [t.start() for t in ths]
    [t.join() for t in ths]
    elapsed = time.monotonic() - t_start
    time.sleep(0.3)

    tweets = 0
    if "tweets.json" in gh.files:
        tj = json.loads(gh.files["tweets.json"][0])
        for v in tj.get("tweets", {}).values():
            tweets += len(v) if isinstance(v, list) else 1
    events = sum(len(t.splitlines()) for p, (t, _) in gh.files.items() if p.startswith("monitoring/events-"))

    out = {
        "mode": mode,
        "http_ok": sum(1 for s, _, _ in results if s == 200),
        "http_fail": [s for s, _, _ in results if s != 200],
        "tweets_saved": tweets,
        "monitor_events": events,
        "elapsed": elapsed,
        "slowest": max(d for _, _, d in results),
        "over10": sum(1 for _, _, d in results if d > UPSTREAM_TIMEOUT_SEC),
        "median": sorted(d for _, _, d in results)[len(results) // 2],
        "gh": dict(gh.stats),
        "gh_max_concurrent": gh.max_in_flight,
        "warns": dict(wc.c),
    }
    logging.getLogger().removeHandler(wc)
    for s in servers:
        s.stop()
    return out


def report(res: dict, burst: int) -> None:
    g = res["gh"]
    print(f"\n── {res['mode'].upper():6} ─ 버스트 {burst} ─────────────────────────────")
    print(f"  /ingest 응답      200 × {res['http_ok']}/{burst}" + (f"   실패 {res['http_fail']}" if res["http_fail"] else ""))
    print(f"  저장된 트윗       {res['tweets_saved']}/{burst}")
    print(f"  모니터 로그 이벤트 {res['monitor_events']}")
    print(f"  GitHub 커밋 성공   {g.get('commit_ok', 0)}    PUT {g.get('PUT', 0)} · GET {g.get('GET', 0)} · 304 {g.get('304', 0)}")
    print(f"  GitHub 409        HEAD 충돌 {g.get('409_head', 0)} · sha 불일치 {g.get('409_sha', 0)}")
    print(f"  GitHub 속도 제한   {g.get('rate_limited', 0)}   (동시 호출 최대 {res['gh_max_concurrent']})")
    print(f"  읽기-쓰기 겹침     쓰기 중 읽기 {g.get('read_during_write', 0)} · 읽기 중 쓰기 {g.get('write_during_read', 0)}")
    print(f"  경고·오류 로그     {res['warns'] or '없음'}")
    print(f"  요청 지연         중앙 {res['median']:.1f}s · 최대 {res['slowest']:.1f}s · 10초 초과 {res['over10']}/{burst}  (업스트림 타임아웃 ≈10s)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--burst", type=int, default=6, help="동시에 쏘는 /ingest 개수")
    ap.add_argument("--mode", choices=["both", "direct", "tower"], default="both")
    ap.add_argument("--write-gap", type=float, default=0.3, help="관제소 쓰기 간 최소 간격(초, 기본 = 관제소 기본값 0.3)")
    ap.add_argument("--max-readers", type=int, default=6, help="관제소 동시 읽기 상한")
    ap.add_argument("--get-lat", type=float, default=None, help="가짜 GitHub GET 지연(초). 기본 0.23(실측)")
    ap.add_argument("--put-lat", type=float, default=None, help="가짜 GitHub PUT 지연(초). 기본 0.80(실측)")
    ap.add_argument("--strict-limit", action="store_true", help="속도 제한 임계값을 낮춰 버스트에서도 걸리게 함")
    a = ap.parse_args()
    global GET_LAT, PUT_LAT
    if a.get_lat is not None:
        GET_LAT = a.get_lat
    if a.put_lat is not None:
        PUT_LAT = a.put_lat
    logging.disable(logging.INFO)
    modes = ["direct", "tower"] if a.mode == "both" else [a.mode]
    all_res = {}
    for m in modes:
        all_res[m] = run(m, a.burst, a.strict_limit, a.write_gap, a.max_readers)
        report(all_res[m], a.burst)
    if len(all_res) == 2:
        d, t = all_res["direct"], all_res["tower"]
        print("\n══ 비교 (direct → tower) ═════════════════════════════════════")
        print(f"  저장된 트윗      {d['tweets_saved']} → {t['tweets_saved']}   (기대 {a.burst})")
        print(f"  409 (HEAD+sha)   {d['gh'].get('409_head', 0) + d['gh'].get('409_sha', 0)} → {t['gh'].get('409_head', 0) + t['gh'].get('409_sha', 0)}")
        print(f"  속도 제한 응답   {d['gh'].get('rate_limited', 0)} → {t['gh'].get('rate_limited', 0)}")
        print(f"  GitHub 동시 호출 {d['gh_max_concurrent']} → {t['gh_max_concurrent']}")
        print(f"  모니터 이벤트    {d['monitor_events']} → {t['monitor_events']}")
        print(f"  가장 느린 요청   {d['slowest']:.1f}s → {t['slowest']:.1f}s")
        print(f"  10초 초과 요청   {d['over10']} → {t['over10']}   (업스트림 타임아웃 ≈10s)")
    sys.stdout.flush(); sys.stderr.flush(); os._exit(0)


if __name__ == "__main__":
    main()
