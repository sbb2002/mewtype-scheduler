"""설정 로드: config/channels.json 및 환경변수."""
from __future__ import annotations

import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CHANNELS_PATH = REPO_ROOT / "config" / "channels.json"


def load_channels() -> dict:
    """config/channels.json 을 파싱해 {"channel_order": [...], "channels": {...}} 반환."""
    with open(CHANNELS_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    if "channel_order" not in cfg or "channels" not in cfg:
        raise ValueError(f"invalid channels config: {CHANNELS_PATH}")
    missing = set(cfg["channel_order"]) - set(cfg["channels"])
    if missing:
        raise ValueError(f"channel_order keys not in channels: {sorted(missing)}")
    return cfg


def get_api_key() -> str:
    """YouTube Data API 키. 없으면 종료."""
    key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if not key:
        raise SystemExit("환경변수 YOUTUBE_API_KEY 가 필요합니다.")
    return key


def channel_url(handle: str) -> str:
    return f"https://www.youtube.com/@{handle}"
