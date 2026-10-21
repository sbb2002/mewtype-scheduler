"""(v4.5.9) Google Cloud Vision 글자 판독(TEXT_DETECTION) — Groq 비전(`vision.py`, qwen3.8-27b)이 이미지를 못 읽었을 때의 예비.

**운영자가 관리 페이지(작업 탭 「이미지 판독 대기」)에서 허가한 것만 부른다** — 자동 경로에서는 절대 부르지 않는다(2026-10-21 운영자 결정).
계기: 같은 날 실험이 Groq 비전 일일 토큰(200,000)을 거의 다 써서 운영 OCR 이 막힐 뻔했다.

- 요금(2026-10-21 공식 요금 페이지): 텍스트 감지 이미지 1장 = 1단위, **월 1,000단위 무료**, 넘으면 1,000단위당 $1.50.
  Cloud Vision 에는 월 단위 할당량이 없어(분당만 있음) 앱이 월 사용량을 세고 `MONTHLY_CAP`(900)에서 막는다
  (카운터 = ops `ocr_pending.json` 의 `usage`, `telegram_app._ocr_pending_commit` op=reserve).
- 인증: 실행 서비스 계정(Cloud Run) · 로컬은 gcloud 기본 자격 증명 — API 키가 없다. 서비스 계정에는 프로젝트 `serviceusage.services.use`
  (역할 Service Usage Consumer)가 필요하다.
- 글자만 돌려준다(「출연진 패널인가」 같은 판단 없음) — 이름 대조 · 행사 판정은 호출부가 한다.
- 이미지는 받아서 base64 로 보낸다(외부 URL 을 Google 이 직접 가져가게 하면 가끔 실패한다).
"""
from __future__ import annotations

import base64
import logging
import os

import requests

logger = logging.getLogger(__name__)

ENDPOINT = "https://vision.googleapis.com/v1/images:annotate"
MONTHLY_CAP = 900          # 월 무료 1,000단위 중 900에서 막는다(실험 · 수동 사용 여유)
MAX_PER_CALL = 16          # images:annotate 한 번에 보낼 수 있는 이미지 수


def _default_token() -> tuple[str, str | None]:
    """(액세스 토큰, 할당량 프로젝트) — Cloud Run 이면 서비스 계정, 로컬이면 gcloud 기본 자격 증명."""
    import google.auth
    import google.auth.transport.requests
    creds, project = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(google.auth.transport.requests.Request())
    quota = getattr(creds, "quota_project_id", None) or os.environ.get("GOOGLE_CLOUD_PROJECT") or project
    return creds.token, quota


def read_texts(urls: list[str], *, session: "requests.Session | None" = None, token_fn=None,
               timeout: float = 30.0) -> list[str | None]:
    """이미지 URL 마다 판독 글자(없거나 실패면 None). 호출 수 = 받기에 성공한 이미지 수(1장 = 1단위).

    예외를 던지지 않는다 — 인증 실패 · 네트워크 오류면 전부 None(호출부가 「실패」로 표시)."""
    urls = [u for u in (urls or []) if isinstance(u, str) and u]
    out: list[str | None] = [None] * len(urls)
    if not urls:
        return out
    s = session or requests.Session()
    try:
        token, quota = (token_fn or _default_token)()
    except Exception:  # noqa: BLE001
        logger.warning("cloudvision: 자격 증명 실패", exc_info=True)
        return out
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    if quota:
        headers["x-goog-user-project"] = quota
    imgs: list[tuple[int, str]] = []
    for i, u in enumerate(urls):
        try:
            r = s.get(u, timeout=20)
            if r.status_code == 200 and r.content:
                imgs.append((i, base64.b64encode(r.content).decode("ascii")))
            else:
                logger.warning("cloudvision: 이미지 받기 실패 %s %s", r.status_code, u)
        except requests.RequestException as e:
            logger.warning("cloudvision: 이미지 받기 오류 %s — %s", u, e)
    for k in range(0, len(imgs), MAX_PER_CALL):
        chunk = imgs[k:k + MAX_PER_CALL]
        body = {"requests": [{"image": {"content": b64}, "features": [{"type": "TEXT_DETECTION"}],
                              "imageContext": {"languageHints": ["ja"]}} for _, b64 in chunk]}
        try:
            r = s.post(ENDPOINT, headers=headers, json=body, timeout=timeout)
        except requests.RequestException as e:
            logger.warning("cloudvision: 호출 오류 — %s", e)
            continue
        if r.status_code != 200:
            logger.warning("cloudvision: %s %s", r.status_code, (r.text or "")[:300])
            continue
        for (i, _), resp in zip(chunk, (r.json() or {}).get("responses") or []):
            if resp.get("error"):
                logger.warning("cloudvision: 이미지 %d 오류 %s", i + 1, resp["error"])
                continue
            txt = ((resp.get("fullTextAnnotation") or {}).get("text") or "").strip()
            out[i] = txt[:1500] or None
    return out


if __name__ == "__main__":
    import json as _json
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

    class _R:
        def __init__(self, status, content=b"", data=None):
            self.status_code, self.content, self._data, self.text = status, content, data, _json.dumps(data or {})

        def json(self):
            return self._data

    class _S:
        def __init__(self):
            self.posts = []

        def get(self, url, timeout):
            return _R(404) if "missing" in url else _R(200, b"\xff\xd8img")

        def post(self, url, headers, json, timeout):
            self.posts.append((headers, json))
            return _R(200, data={"responses": [{"fullTextAnnotation": {"text": "開催期間 10月18日 15:00~10月26日 14:59\n"}},
                                               {"error": {"code": 3, "message": "bad image"}}]})

    s = _S()
    got = read_texts(["https://x/a.jpg", "https://x/missing.jpg", "https://x/c.jpg"], session=s, token_fn=lambda: ("tok", "proj"))
    assert got == ["開催期間 10月18日 15:00~10月26日 14:59", None, None], got
    assert len(s.posts) == 1 and len(s.posts[0][1]["requests"]) == 2, "받은 이미지 2장만 한 번에"
    assert s.posts[0][0]["x-goog-user-project"] == "proj" and s.posts[0][0]["Authorization"] == "Bearer tok"
    print("[OK] 받은 이미지만 한 요청으로 · 이미지별 글자 · 오류 이미지는 None · 할당량 프로젝트 헤더")
    assert read_texts(["https://x/a.jpg"], session=s, token_fn=lambda: (_ for _ in ()).throw(RuntimeError("no creds"))) == [None]
    assert read_texts([], session=s) == []
    print("[OK] 자격 증명 실패 · 빈 목록 → 예외 없이 None")
    print("\nSUCCESS: cloudvision self-test 통과 (mock)")
