"""수집 오케스트레이션.

사용법:
    python -m src.collector.main [light|deep]

환경변수:
    YOUTUBE_API_KEY  (필수)  YouTube Data API v3 키
    DATA_DIR         (선택)  schedule.json / archive.json 출력 위치. 기본 ./_data
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone

from .config import get_api_key, load_channels
from .reconcile import build_schedule
from .rss import fetch_all_rss_video_ids
from .youtube import YouTubeClient
from . import store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("collector")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _tracked_unresolved_ids(schedule: dict) -> list[str]:
    return [
        b["video_id"]
        for b in schedule.get("broadcasts", [])
        if b.get("status") in ("upcoming", "live")
    ]


def run(mode: str) -> int:
    mode = mode if mode in ("light", "deep") else "light"
    log.info("collector start mode=%s", mode)

    cfg = load_channels()
    id_by_key = {k: v["channel_id"] for k, v in cfg["channels"].items()}

    prev = store.load_schedule(cfg)

    rss_map = fetch_all_rss_video_ids(id_by_key)
    candidates: set[str] = set()
    for ids in rss_map.values():
        candidates.update(ids)
    tracked = _tracked_unresolved_ids(prev)
    candidates.update(tracked)
    log.info("candidates: rss=%d tracked=%d", sum(len(v) for v in rss_map.values()), len(tracked))

    yt = YouTubeClient(get_api_key())

    if mode == "deep":
        for cid in id_by_key.values():
            candidates.update(yt.search_upcoming(cid))
        log.info("after deep scan: %d candidates (quota_used=%d)", len(candidates), yt.quota_used)

    if not candidates:
        log.warning("no candidate video ids; previous schedule left untouched")
        return 0

    videos = yt.videos_list(sorted(candidates))
    log.info("videos.list: %d/%d resolved, quota_used=%d", len(videos), len(candidates), yt.quota_used)

    now_iso = _now_iso()
    new_schedule, newly_ended = build_schedule(cfg, videos, prev, now_iso)

    changed_sched = store.save_schedule(new_schedule)
    changed_arch = store.append_archive(newly_ended) if newly_ended else False

    log.info(
        "done: schedule changed=%s (%d live/upcoming), archive changed=%s (+%d ended), quota_used=%d",
        changed_sched,
        len(new_schedule.get("broadcasts", [])),
        changed_arch,
        len(newly_ended),
        yt.quota_used,
    )
    return 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1] if len(sys.argv) > 1 else "light"))
