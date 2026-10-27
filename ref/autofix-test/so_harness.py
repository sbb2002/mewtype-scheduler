"""오토핫픽스 시험 S-O 장치 v2 (2026-10-27) — 가짜 GitHub(fakegh.py) 위에 1MB 넘는 트윗 보관함을 두고 **진짜 경로**로 오류를 낸다.

v1(`archive1mb_trigger.py`)은 GitHub 응답 하나를 고정으로 흉내 내서, 수정이 실제로 맞았는지(오류가 사라졌나 · 데이터를 잃지 않았나)를 볼 수 없었다.
v2 는 폴더를 저장소처럼 쓰는 가짜 Contents API 라 raw · blob 읽기, 파일 나누기, 이전 스크립트 결과까지 그대로 반영된다.
**시험 대상 브랜치에 넣지 않는다**(분석 모델이 답을 미리 보지 않게). 시험 브랜치 워크트리 루트에서 실행한다.

  python <이 폴더>/so_harness.py seed  --root <데이터 폴더>            # data/ · ops/ 를 새로 만듦(보관함 1MB 초과) + 기준 명단
  python <이 폴더>/so_harness.py fire  --root <데이터 폴더> [--env .env.local]   # 개인 트윗 1건 저장 시도 → (고장 상태면) ERROR 가 버스로
  python <이 폴더>/so_harness.py check --root <데이터 폴더>            # 판정: 트윗 반영 · 보관 항목 손실 · 1MB 넘는 파일

수신기의 `RX_DATA_DIR` 를 같은 <데이터 폴더>로 두면, 오토핫픽스가 만든 이전 스크립트가 이 폴더를 고치고 fire/check 가 그 결과를 읽는다.
기준 명단 = <데이터 폴더>.manifest.json(폴더 밖 — 이전 스크립트가 건드리지 않게).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.getcwd())                       # 시험 브랜치 루트의 src 를 쓴다
sys.path.insert(0, str(Path(__file__).resolve().parent))  # fakegh

from fakegh import LIMIT_DEFAULT, FakeGitHubSession  # noqa: E402

EPOCH_MS = 1288834974657


def _serialize(d) -> str:
    return json.dumps(d, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def _tid(dt: datetime) -> str:
    return str((int(dt.timestamp() * 1000) - EPOCH_MS) << 22 | random.randint(0, 4194303))


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _manifest(root: Path) -> Path:
    return root.with_name(root.name + ".manifest.json")


def seed(root: Path, target: int) -> None:
    import shutil
    random.seed(20261027)
    chans = json.loads(Path("config/channels.json").read_text(encoding="utf-8"))
    keys = chans["channel_order"]
    handles = {k: (chans["channels"][k].get("x_handle") or f"{k}_yumemita") for k in keys}
    shutil.rmtree(root, ignore_errors=True)
    for b in ("data", "ops", "monitoring"):
        (root / b).mkdir(parents=True)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    rows, start = [], now - timedelta(days=120)
    jp = ["きょうも配信ありがとう！", "明日の夜はゲーム配信するよ〜", "新しい衣装のお披露目、楽しみにしててね", "リハーサルおつかれさまでした！",
          "みんなのコメントいっぱい読んだよ、ありがとう", "今週の予定をまとめました", "ライブの感想ありがとう！また会おうね"]
    ko = ["오늘도 방송 고마워!", "내일 밤엔 게임 방송할게~", "새 의상 공개 기대해 줘", "리허설 수고하셨습니다!", "댓글 많이 읽었어, 고마워", "이번 주 일정을 정리했어요", "라이브 감상 고마워! 또 만나"]
    t, i = start, 0
    while True:
        k = keys[i % len(keys)]
        posted = t
        n = random.randrange(len(jp))
        tid = _tid(posted)
        rows.append({"channel_key": k, "id": tid, "text": jp[n] + " " + "✨" * random.randint(1, 3) + f" #{i}",
                     "text_ko": ko[n], "url": f"https://x.com/{handles[k]}/status/{tid}", "handle": handles[k],
                     "received_at": _iso(posted + timedelta(seconds=40)), "posted_at": _iso(posted), "expires_at": _iso(posted + timedelta(hours=48)),
                     "media": [], "quote": None, "archived_at": _iso(posted + timedelta(hours=48, minutes=3)),
                     "archived_reason": random.choice(["expired", "expired", "expired", "rolled"])})
        i += 1
        t += timedelta(minutes=random.randint(20, 300))
        if i % 200 == 0 and len(_serialize({"tweets": rows}).encode()) > target:
            break
    (root / "data" / "tweet_archive.json").write_text(_serialize({"tweets": rows}), encoding="utf-8", newline="\n")
    (root / "data" / "tweets.json").write_text(_serialize({"generated_at": _iso(now), "tweets": {}}), encoding="utf-8", newline="\n")
    size = (root / "data" / "tweet_archive.json").stat().st_size
    _manifest(root).write_text(json.dumps({"archive_ids": [r["id"] for r in rows], "fired": [], "seeded_at": _iso(now)}, indent=1), encoding="utf-8")
    print(f"seed: tweet_archive.json {size:,}B ({len(rows)}건, 1MB 기준 {LIMIT_DEFAULT:,}B 초과={size > LIMIT_DEFAULT}) · 명단 {_manifest(root).name}")


def fire(root: Path) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    from src.bus import install
    pub = install(service="runner")
    if pub is None:
        print("MEW_BUS_DIR 가 없어 발신기를 켤 수 없음 — .env.local 확인", file=sys.stderr)
        return 2
    from src.backend import telegram_app as t
    from src.backend import xtweet
    from src.backend.gh_store import GitHubStore

    now = datetime.now(timezone.utc)
    now_iso = _iso(now)
    tid = _tid(now)
    gh = GitHubStore("offline", "offline/offline", "data", session=FakeGitHubSession(root))
    parsed = xtweet.parse("きょうも配信ありがとう！", title="仲町あられ", tag=f"p#https://x.com/#1tweet-{tid}",
                          channel_key="arale", now_iso=now_iso, handle="arale_yumemita")
    prepared = {"parsed": parsed, "text_src": parsed["text"], "text_ko": "오늘도 방송 고마워!", "quote_src": None, "quote_ko": None}
    res = t._commit_personal_tweet(gh, prepared, channel_key="arale", now_iso=now_iso)
    time.sleep(0.5)
    pub.flush_expired()
    m = json.loads(_manifest(root).read_text(encoding="utf-8"))
    m["fired"].append({"id": tid, "at": now_iso, "mode": res.get("mode")})
    _manifest(root).write_text(json.dumps(m, indent=1), encoding="utf-8")
    print(f"fire: _commit_personal_tweet → {res} · 발신 {pub.counters['sent']}건 · tweet {tid}")
    return 0


def _ids_in(obj, out: set) -> None:
    """JSON 안의 트윗 행(id + channel_key 를 가진 dict) id 를 모두 모은다 — 파일 구조가 바뀌어도(나눔 · 색인) 찾게."""
    if isinstance(obj, dict):
        if isinstance(obj.get("id"), str) and "channel_key" in obj:
            out.add(obj["id"])
        for v in obj.values():
            _ids_in(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _ids_in(v, out)


def check(root: Path) -> int:
    m = json.loads(_manifest(root).read_text(encoding="utf-8"))
    found, big, bad = set(), [], []
    for f in sorted((root / "data").rglob("*.json")):
        try:
            obj = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            bad.append(f"{f.relative_to(root)}: {type(e).__name__}")
            continue
        _ids_in(obj, found)
    for f in sorted(root.rglob("*")):
        if f.is_file() and f.stat().st_size > LIMIT_DEFAULT:
            big.append(f"{f.relative_to(root)} {f.stat().st_size:,}B")
    lost = [i for i in m["archive_ids"] if i not in found]
    tw = json.loads((root / "data" / "tweets.json").read_text(encoding="utf-8"))
    cur = set()
    _ids_in(tw, cur)
    fired = m["fired"]
    print(f"check: 보관 항목 {len(m['archive_ids'])}건 중 잃음 {len(lost)}건" + (f" (예: {lost[:3]})" if lost else ""))
    print(f"check: 1MB 넘는 파일 {len(big)}개" + (" — " + ", ".join(big) if big else ""))
    for x in fired:
        where = "tweets.json" if x["id"] in cur else ("다른 파일" if x["id"] in found else "없음")
        print(f"check: fire {x['at']} id {x['id']} mode={x['mode']} → {where}")
    if bad:
        print("check: 읽기 실패 파일 " + "; ".join(bad))
    print("check: 파일 목록 — " + ", ".join(f"{p.relative_to(root)}" for p in sorted((root / "data").rglob("*")) if p.is_file())[:600])
    return 0 if not lost and not bad else 1


def _load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        if "=" in raw and not raw.lstrip().startswith("#"):
            k, v = raw.split("=", 1)
            os.environ.setdefault(k.strip(), v.split(" #")[0].strip())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("seed", "fire", "check"))
    ap.add_argument("--root", required=True)
    ap.add_argument("--env", default=".env.local")
    ap.add_argument("--target", type=int, default=LIMIT_DEFAULT)
    a = ap.parse_args(argv)
    root = Path(a.root).resolve()
    if a.cmd == "seed":
        seed(root, a.target)
        return 0
    if a.cmd == "check":
        return check(root)
    _load_env(Path(a.env))
    return fire(root)


if __name__ == "__main__":
    sys.exit(main())
