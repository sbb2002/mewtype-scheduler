"""오토핫픽스 시험 S-O 트리거 — 트윗 보관함 1MB 초과 상황에서 개인 트윗 저장이 실패하는 ERROR 를 진짜 경로로 만든다.

**시험 대상 브랜치에 커밋하지 않는다** — 오토핫픽스 분석은 저장소 HEAD 스냅샷을 읽으므로, 이 파일(원인 설명 · GitHub 응답 흉내)이
브랜치에 있으면 분석 모델이 답을 미리 본다. 그래서 devpapers 에 두고 밖에서 실행한다.

동작: GitHub Contents API 응답만 흉내 낸 세션(네트워크 없음 — 운영 데이터 저장소에 닿지 않음)을 `GitHubStore` 에 넣고
**실제** `telegram_app._commit_personal_tweet` 을 부른다. 그 함수가 운영과 같은 줄에서 스스로 ERROR(`personal tweet 반영 실패` +
`RuntimeError: No content in response for tweet_archive.json` 트레이스백)를 남기고, 발신기가 버스로 보낸다.
GitHub 는 1MB 넘는 파일을 기본 형식으로 읽으면 content 를 비우고 encoding="none" 으로 준다 — 그 응답을 흉내 낸다.

사용 (시험 브랜치 `test/autofix-archive1mb` 워크트리 루트에서):
  python <이 파일 경로> [--bus <MEW_BUS_DIR>] [--env .env.local]
"""
from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.getcwd())          # 시험 브랜치 루트에서 실행 → src 패키지를 그 브랜치 것으로


class _R:
    def __init__(self, code, payload=None):
        self.status_code, self.reason, self.text, self._p = code, "", "", payload or {}

    def json(self):
        return self._p


class GitHub1MBSession:
    """tweets.json = 작은 정상 파일, tweet_archive.json = 1MB 넘은 파일(내용 비움), 그 밖 = 404, PUT = 성공."""

    def __init__(self, tweets: dict):
        self._tweets_b64 = base64.b64encode(json.dumps(tweets, ensure_ascii=False).encode()).decode()

    def get(self, url, params=None, headers=None, timeout=None):
        path = url.split("/contents/", 1)[-1]
        if path == "tweets.json":
            return _R(200, {"type": "file", "encoding": "base64", "content": self._tweets_b64, "sha": "t0", "size": 300, "path": path})
        if path == "tweet_archive.json":
            return _R(200, {"type": "file", "encoding": "none", "content": "", "sha": "a0", "size": 1_052_918, "path": path})
        return _R(404)

    def put(self, url, json=None, headers=None, timeout=None):
        return _R(201, {"content": {"sha": "w1"}})


def _load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        if "=" in raw and not raw.lstrip().startswith("#"):
            k, v = raw.split("=", 1)
            os.environ.setdefault(k.strip(), v.split(" #")[0].strip())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bus", default="")
    ap.add_argument("--env", default=".env.local")
    a = ap.parse_args(argv)
    _load_env(Path(a.env))
    if a.bus:
        os.environ["MEW_BUS_DIR"] = a.bus
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    from src.bus import install
    pub = install(service="runner")          # 러너와 같은 서비스 이름 — 시험 표시를 봉투에 남기지 않는다
    if pub is None:
        print("MEW_BUS_DIR 가 없어 발신기를 켤 수 없음 — --bus 또는 .env.local 확인", file=sys.stderr)
        return 2

    from src.backend import telegram_app as t
    from src.backend import xtweet
    from src.backend.gh_store import GitHubStore

    now = datetime.now(timezone.utc)
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    tid = str((int(now.timestamp() * 1000) - 1288834974657) << 22)
    gh = GitHubStore("offline", "offline/offline", "data", session=GitHub1MBSession({"generated_at": now_iso, "tweets": {}}))
    parsed = xtweet.parse("きょうも配信ありがとう！", title="仲町あられ", tag=f"p#https://x.com/#1tweet-{tid}",
                          channel_key="arale", now_iso=now_iso, handle="arale_yumemita")
    prepared = {"parsed": parsed, "text_src": parsed["text"], "text_ko": "오늘도 방송 고마워!", "quote_src": None, "quote_ko": None}
    res = t._commit_personal_tweet(gh, prepared, channel_key="arale", now_iso=now_iso)
    time.sleep(0.5)
    pub.flush_expired()
    print(f"_commit_personal_tweet → {res} · 발신 {pub.counters['sent']}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
