"""DB 관제소 Flask 앱 (`mewtype-db-tower`) — `data` 저장소 접근의 유일한 문.

라우트:
  POST /fetch  {"path","as":"json"|"text","budget"?}            → {"found","data"|"text","sha"}
  POST /put    {"path","as":"json"|"text","data"|"text","prev_sha"?,"message","budget"?}
                                                                → {"changed","sha"}
  GET  /       — 헬스체크 + 대기열 상태 {"ok","depth","cooldown_sec"}

오류: sha 충돌 409 · 대기 상한 초과/속도 제한 지속 503(+`Retry-After`, {"busy",true,"retry_after"}) ·
잘못된 입력 400 · 인증 실패 403 · 그 외 GitHub 오류 502.

조정(환경변수): `TOWER_WRITE_GAP_SEC`(쓰기 간 최소 간격, 기본 0.3) · `TOWER_MAX_READERS`(동시 읽기 상한, 기본 6).

배포 (deploy/deploy_tower.sh): `--concurrency=64 --max-instances=1`(scale-to-zero, min 0), gunicorn
`--workers=1 --threads=64`. 백엔드의 `--concurrency=1` 과 다르다 — 관제소는 요청이 프로세스 안에서
FIFO 로 줄을 서야 대기 상한(503)을 통제할 수 있으므로 여러 요청이 동시에 들어와 있어야 한다. 순서·직렬화는
`tower.Tower` 가 보장하고, 인스턴스가 하나(`max-instances=1`)라 그 보장이 서비스 전체에 성립한다.
"""
from __future__ import annotations

import logging
import os
import threading

from flask import Flask, jsonify, request

from . import oidc
from .gh_store import ConflictError, GitHubStore
from .tower import DEFAULT_BUDGET_SEC, MAX_READERS, WRITE_GAP_SEC, Tower, TowerBusy, safe_data_path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("backend.tower_app")

app = Flask(__name__)

_tower: Tower | None = None
_tower_lock = threading.Lock()


def _get_tower() -> Tower:
    """지연 생성 — import 단계에서 env 가 없어도 죽지 않게. ETag 캐시는 프로세스 메모리."""
    global _tower
    with _tower_lock:
        if _tower is None:
            token = os.environ.get("GITHUB_TOKEN", "").strip()
            repo = os.environ.get("GITHUB_REPO", "").strip()
            branch = os.environ.get("DATA_BRANCH", "data").strip() or "data"
            gh = GitHubStore(token, repo, branch, etag_cache={})
            _tower = Tower(
                gh,
                write_gap=float(os.environ.get("TOWER_WRITE_GAP_SEC", WRITE_GAP_SEC)),
                max_readers=int(os.environ.get("TOWER_MAX_READERS", MAX_READERS)),
            )
        return _tower


def _authorize() -> None:
    oidc.verify_request(
        request.headers,
        expected_audience=os.environ.get("SERVICE_URL", "").strip().rstrip("/"),
        expected_sa=os.environ.get("CALLER_SAS", "").strip() or None,
    )


def _budget(body: dict) -> float:
    try:
        b = float(body.get("budget", DEFAULT_BUDGET_SEC))
    except (TypeError, ValueError):
        b = DEFAULT_BUDGET_SEC
    return min(max(b, 1.0), 85.0)   # 서비스 요청 타임아웃(90초) 안쪽으로 제한


def _busy(e: TowerBusy):
    resp = jsonify({"busy": True, "retry_after": e.retry_after, "error": str(e)})
    resp.status_code = 503
    resp.headers["Retry-After"] = str(int(e.retry_after + 0.999))
    return resp


@app.post("/fetch")
def _fetch():
    try:
        _authorize()
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    body = request.get_json(silent=True) or {}
    path, kind = body.get("path"), body.get("as", "json")
    if not safe_data_path(path) or kind not in ("json", "text"):
        return jsonify({"error": "path(str, data 저장소 상대경로) / as(json|text) 필요"}), 400
    tw = _get_tower()
    try:
        if kind == "json":
            data, sha = tw.read_json(path, budget=_budget(body))
            return jsonify({"found": data is not None, "data": data, "sha": sha})
        text, sha = tw.read_text(path, budget=_budget(body))
        return jsonify({"found": text is not None, "text": text, "sha": sha})
    except TowerBusy as e:
        return _busy(e)
    except Exception as e:  # noqa: BLE001
        log.exception("fetch 실패 path=%s", path)
        return jsonify({"error": str(e)}), 502


@app.post("/put")
def _put():
    try:
        _authorize()
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    body = request.get_json(silent=True) or {}
    path, kind = body.get("path"), body.get("as", "json")
    message, prev_sha = body.get("message"), body.get("prev_sha")
    if (not safe_data_path(path) or kind not in ("json", "text")
            or not isinstance(message, str) or not message
            or (prev_sha is not None and not isinstance(prev_sha, str))
            or (kind == "json" and not isinstance(body.get("data"), dict))
            or (kind == "text" and not isinstance(body.get("text"), str))):
        return jsonify({"error": "path·as·message 와 (json→data:dict | text→text:str) 필요"}), 400
    tw = _get_tower()
    try:
        if kind == "json":
            changed, sha = tw.write_json(path, body["data"], prev_sha=prev_sha, message=message,
                                         budget=_budget(body))
        else:
            changed, sha = tw.write_text(path, body["text"], prev_sha=prev_sha, message=message,
                                         budget=_budget(body))
        return jsonify({"changed": bool(changed), "sha": sha})
    except ConflictError as e:
        return jsonify({"error": str(e), "conflict": True}), 409
    except TowerBusy as e:
        return _busy(e)
    except Exception as e:  # noqa: BLE001
        log.exception("put 실패 path=%s", path)
        return jsonify({"error": str(e)}), 502


@app.get("/")
def _healthz():
    # "/healthz" 는 GFE 가 가로채므로 루트를 쓴다. 인증 불필요(서비스 자체는 비공개).
    st = _get_tower().status() if os.environ.get("GITHUB_TOKEN") else {"depth": 0, "cooldown_sec": 0.0}
    return jsonify({"ok": True, **st})


if __name__ == "__main__":
    # 로컬 개발: ALLOW_UNAUTH=1 GITHUB_TOKEN=... GITHUB_REPO=owner/repo python -m src.backend.tower_app
    app.run(host="127.0.0.1", port=8081, debug=True)
