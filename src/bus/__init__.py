"""에러 버스 발신기 (test-fullauto-hotfix) — 규약: docs/BUS_PROTOCOL.md.

MEW_BUS_DIR 이 없으면 아무 것도 하지 않는다(운영 코드 경로에 영향 없음).
"""
from .publisher import install, on_events, get  # noqa: F401
