"""가짜 GitHub Contents API — 로컬 폴더(<root>/<브랜치>/…)를 GitHub 저장소처럼 흉내 낸다(네트워크 없음).

오토핫픽스 시험 S-O 용(2026-10-27). **시험 대상 브랜치에 넣지 않는다**(분석 모델이 읽는 스냅샷 밖에 둔다).
`GitHubStore(..., session=FakeGitHubSession(root))` 로 넣어 쓴다. 브랜치(ref) = <root> 아래 폴더 이름(data · ops · monitoring).
수신기 `RX_DATA_DIR` 도 같은 <root> 를 가리키게 하면 데이터 이전 스크립트가 고친 파일을 이 가짜 API 가 그대로 읽는다.

흉내 내는 GitHub 동작(v4.8.6 장애 기준 · GitHub 문서 「Get repository content」):
- 파일 GET(기본 `application/vnd.github+json`): 1MB(1,048,576B) 이하면 base64 content, 넘으면 content="" · encoding="none" · size 는 실제 크기.
- `Accept: application/vnd.github.raw`(또는 `.raw+json`): 본문 그대로(100MB 까지). `application/vnd.github.object`: 기본과 같은 메타.
- 디렉터리 GET: 항목 목록(name · path · type · sha · size). 없는 경로 = 404.
- `GET /git/blobs/<sha>`: base64 content(크기 제한 없음 — 100MB 까지).
- `download_url`: `https://fakegh.invalid/raw/<브랜치>/<경로>` — 이 세션으로 GET 하면 본문, requests 로 직접 부르면 실패(실제 GitHub 에도 닿지 않음).
- PUT: 기존 파일이면 body.sha 가 현재 sha 와 같아야 함(아니면 409), 새 파일이면 sha 없이. 쓰기 기록은 self.log.
- DELETE: body.sha 일치 시 삭제.
"""
from __future__ import annotations

import base64
import hashlib
import json as _json
from pathlib import Path
from urllib.parse import unquote, urlparse

LIMIT_DEFAULT = 1_048_576
LIMIT_RAW = 100 * 1_048_576


def blob_sha(b: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(b) + b).hexdigest()


class R:
    def __init__(self, code: int, payload=None, raw: bytes | None = None):
        self.status_code = code
        self.reason = {200: "OK", 201: "Created", 404: "Not Found", 409: "Conflict", 403: "Forbidden", 422: "Unprocessable"}.get(code, "")
        self._p = payload
        self.content = raw if raw is not None else (_json.dumps(payload, ensure_ascii=False).encode() if payload is not None else b"")
        self.text = self.content.decode("utf-8", "replace")
        self.headers = {"content-type": "application/vnd.github.raw" if raw is not None else "application/json"}
        self.ok = 200 <= code < 300

    def json(self):
        if self._p is None:
            return _json.loads(self.text)
        return self._p

    def raise_for_status(self):
        if not self.ok:
            import requests
            raise requests.HTTPError(f"{self.status_code} {self.reason}")


class FakeGitHubSession:
    def __init__(self, root: Path | str, default_ref: str = "data"):
        self.root = Path(root)
        self.default_ref = default_ref
        self.log: list[tuple] = []

    # ── 경로 ──
    def _split(self, url: str):
        u = urlparse(url)
        parts = unquote(u.path).strip("/").split("/")
        if u.netloc == "fakegh.invalid" and parts[:1] == ["raw"]:
            return "raw", parts[1], "/".join(parts[2:])
        # /repos/<owner>/<repo>/(contents|git/blobs)/...
        if len(parts) >= 4 and parts[0] == "repos":
            rest = parts[3:]
            if rest[:1] == ["contents"]:
                return "contents", None, "/".join(rest[1:])
            if rest[:2] == ["git", "blobs"] and len(rest) == 3:
                return "blob", None, rest[2]
        return "?", None, ""

    def _file(self, ref: str, path: str) -> Path:
        p = (self.root / ref / path).resolve()
        if self.root.resolve() not in p.parents and p != self.root.resolve():
            raise ValueError("경로 탈출")
        return p

    def _meta(self, ref: str, path: str, f: Path) -> dict:
        b = f.read_bytes()
        return {"type": "file", "name": f.name, "path": path, "sha": blob_sha(b), "size": len(b),
                "download_url": f"https://fakegh.invalid/raw/{ref}/{path}"}

    # ── 요청 ──
    def get(self, url, params=None, headers=None, timeout=None, **kw):
        kind, ref, path = self._split(url)
        accept = ((headers or {}).get("Accept") or "").lower()
        self.log.append(("GET", kind, path, accept))
        if kind == "raw":
            f = self._file(ref, path)
            return R(200, raw=f.read_bytes()) if f.is_file() else R(404, {"message": "Not Found"})
        if kind == "blob":
            for f in self.root.rglob("*"):
                if f.is_file() and blob_sha(f.read_bytes()) == path:
                    b = f.read_bytes()
                    if len(b) > LIMIT_RAW:
                        return R(403, {"message": "too_large"})
                    return R(200, {"sha": path, "size": len(b), "encoding": "base64", "content": base64.b64encode(b).decode()})
            return R(404, {"message": "Not Found"})
        if kind != "contents":
            return R(404, {"message": "Not Found"})
        ref = (params or {}).get("ref") or self.default_ref
        f = self._file(ref, path) if path else (self.root / ref)
        if f.is_dir():
            items = []
            for c in sorted(f.iterdir()):
                rel = f"{path}/{c.name}" if path else c.name
                items.append(self._meta(ref, rel, c) if c.is_file() else {"type": "dir", "name": c.name, "path": rel, "sha": "", "size": 0})
            return R(200, items)
        if not f.is_file():
            return R(404, {"message": "Not Found"})
        b = f.read_bytes()
        if "vnd.github.raw" in accept:
            return R(200, raw=b) if len(b) <= LIMIT_RAW else R(403, {"message": "too_large"})
        meta = self._meta(ref, path, f)
        if len(b) <= LIMIT_DEFAULT:
            meta.update(encoding="base64", content=base64.encodebytes(b).decode())
        else:
            meta.update(encoding="none", content="")
        return R(200, meta)

    def put(self, url, json=None, headers=None, timeout=None, **kw):
        kind, _, path = self._split(url)
        body = json or {}
        ref = body.get("branch") or self.default_ref
        self.log.append(("PUT", kind, path, ref))
        if kind != "contents" or not path:
            return R(404, {"message": "Not Found"})
        f = self._file(ref, path)
        if f.is_file():
            if body.get("sha") != blob_sha(f.read_bytes()):
                return R(409, {"message": "sha mismatch"})
        elif body.get("sha"):
            return R(422, {"message": "sha given for new file"})
        b = base64.b64decode(body.get("content") or "")
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b)
        return R(200, {"content": {"sha": blob_sha(b), "path": path, "size": len(b)}})

    def delete(self, url, json=None, headers=None, timeout=None, **kw):
        kind, _, path = self._split(url)
        body = json or {}
        ref = body.get("branch") or self.default_ref
        self.log.append(("DELETE", kind, path, ref))
        f = self._file(ref, path)
        if not f.is_file():
            return R(404, {"message": "Not Found"})
        if body.get("sha") != blob_sha(f.read_bytes()):
            return R(409, {"message": "sha mismatch"})
        f.unlink()
        return R(200, {"commit": {}})

    def request(self, method, url, **kw):
        return {"GET": self.get, "PUT": self.put, "DELETE": self.delete}[method.upper()](url, **kw)
