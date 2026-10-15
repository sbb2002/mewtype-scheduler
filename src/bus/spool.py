"""폴더 스풀 — 버스의 로컬 전송 수단. 파일 1개 = 메시지 1건.

쓰기는 항상 `.tmp/` 에 쓴 뒤 같은 볼륨 안에서 os.replace → 수신기가 반쯤 쓰인 파일을 읽을 일이 없다.
레이아웃은 docs/BUS_PROTOCOL.md §2.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

DIRS = ("err/inbox", "err/hold", "err/processing", "err/done", "err/dead", "ctl/inbox", "ctl/done", "report/inbox", "hb", ".tmp")
INBOX_CAP = 500  # 수신기가 안 가져가면 쌓이지 않게 — 넘으면 새 메시지를 버리고 dropped 로 센다


class Spool:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def ensure(self) -> None:
        for d in DIRS:
            (self.root / d).mkdir(parents=True, exist_ok=True)

    def _replace(self, src: Path, dst: Path) -> None:
        # Windows 에서 백신 · 인덱서가 잠깐 잡는 경우가 있어 짧게 재시도
        for i in range(6):
            try:
                os.replace(src, dst)
                return
            except PermissionError:
                if i == 5:
                    raise
                time.sleep(0.05 * (i + 1))

    def put(self, sub: str, name: str, obj: dict) -> Path:
        """sub 폴더(예: 'err/inbox')에 <name>.json 으로 원자적 기록."""
        tmp = self.root / ".tmp" / f"{name}.{os.getpid()}.tmp"
        tmp.write_text(json.dumps(obj, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        dst = self.root / sub / f"{name}.json"
        self._replace(tmp, dst)
        return dst

    def count(self, sub: str) -> int:
        try:
            return sum(1 for p in (self.root / sub).iterdir() if p.suffix == ".json")
        except FileNotFoundError:
            return 0

    def list(self, sub: str) -> list[Path]:
        try:
            return sorted(p for p in (self.root / sub).iterdir() if p.suffix == ".json")
        except FileNotFoundError:
            return []

    def move(self, path: Path, sub: str) -> Path:
        dst = self.root / sub / path.name
        self._replace(path, dst)
        return dst
