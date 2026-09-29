"""(v4a H7) 운영자 관리 페이지 — Flask 블루프린트.

로그인(마법 링크) → 세션 쿠키 → API (읽기·쓰기 with CSRF).

의존성 주입으로 테스트 가능.
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import flask

logger = logging.getLogger(__name__)


def _sign(secret: str, purpose: str, payload_b64: str) -> str:
    """용도(login | session)를 서명 입력에 넣는다 — 로그인 토큰을 세션 쿠키로(또는 반대로) 재사용하는 것을 막는다."""
    return hmac.new(secret.encode(), f"{purpose}:{payload_b64}".encode(), hashlib.sha256).hexdigest()


def make_login_url(
    base_url: str,
    *,
    secret: str,
    ttl_sec: int = 300,
    clock: Callable[[], float] = time.time,
) -> str:
    """로그인 링크 생성. 토큰 = base64url({"n": nonce(hex16), "exp": epoch}) + "." + HMAC(secret, b64)."""
    nonce = secrets.token_hex(8)  # 16자 hex
    exp = int(clock()) + ttl_sec
    payload = json.dumps({"n": nonce, "exp": exp}, separators=(",", ":"), ensure_ascii=False)
    payload_b64 = base64.urlsafe_b64encode(payload.encode()).rstrip(b"=").decode()

    # HMAC-SHA256(secret, "login:" + payload_b64) — 용도 구분자로 세션 쿠키와 서로 바꿔 쓸 수 없게
    sig_hex = _sign(secret, "login", payload_b64)

    token = f"{payload_b64}.{sig_hex}"
    return f"{base_url}/admin/login?t={token}"


def create_blueprint(
    *,
    api,
    ops_store,
    secret: str,
    session_hours: float = 12,
    clock: Callable[[], float] = time.time,
) -> flask.Blueprint:
    """관리 페이지 Flask 블루프린트 생성.

    Args:
        api: admin_api 모듈 또는 호환 객체 (API_FUNCTIONS 함수들 노출).
        ops_store: LocalStore(ops 브랜치) 또는 호환 객체.
        secret: 서명 비밀키 (HMAC).
        session_hours: 세션 수명(시간).
        clock: 테스트 시간 mocking용 callable.

    Returns:
        Blueprint(url_prefix="/admin").
    """

    bp = flask.Blueprint("admin", __name__, url_prefix="/admin")

    # ─── 세션 · CSRF 헬퍼 ─────────────────────────────────────────────────────

    def _verify_signature(token_str: str, purpose: str = "login") -> Optional[dict]:
        """토큰 서명 검증(purpose = login | session). 유효하면 페이로드 dict, 아니면 None."""
        try:
            parts = token_str.split(".")
            if len(parts) != 2:
                return None
            payload_b64, sig_hex = parts

            # HMAC 검증 (constant-time compare)
            expected_sig = _sign(secret, purpose, payload_b64)
            if not hmac.compare_digest(sig_hex, expected_sig):
                return None

            # 페이로드 디코딩
            # base64url 복원 (padding 추가)
            padding = 4 - (len(payload_b64) % 4)
            if padding != 4:
                payload_b64 += "=" * padding
            payload_json = base64.urlsafe_b64decode(payload_b64).decode()
            return json.loads(payload_json)
        except Exception as e:
            logger.debug(f"토큰 검증 실패: {e}")
            return None

    def _verify_session() -> Optional[dict]:
        """세션 쿠키 검증. 유효하면 {"sid": session_id, "exp": epoch}, 아니면 None."""
        cookie = flask.request.cookies.get("mt_admin")
        if not cookie:
            return None

        payload = _verify_signature(cookie, "session")
        if not payload or not payload.get("sid"):
            return None

        # 만료 확인
        if payload.get("exp", 0) < int(clock()):
            return None

        return payload

    def _get_csrf_token(sid: str) -> str:
        """CSRF 토큰 생성. HMAC(secret, "csrf:" + sid)."""
        return hmac.new(
            secret.encode(), f"csrf:{sid}".encode(), hashlib.sha256
        ).hexdigest()

    def _make_session_cookie(sid: str) -> tuple[str, dict]:
        """세션 쿠키 값 · 속성 생성."""
        exp = int(clock()) + int(session_hours * 3600)
        payload = json.dumps({"sid": sid, "exp": exp}, separators=(",", ":"))
        payload_b64 = base64.urlsafe_b64encode(payload.encode()).rstrip(b"=").decode()
        cookie_value = f"{payload_b64}.{_sign(secret, 'session', payload_b64)}"

        # 쿠키 속성
        secure = flask.request.is_secure
        cookie_kwargs = {
            "max_age": int(session_hours * 3600),
            "httponly": True,
            "samesite": "Strict",
            "secure": secure,
            "path": "/admin",
        }
        return cookie_value, cookie_kwargs

    # ─── 로그인 · 세션 ────────────────────────────────────────────────────────

    @bp.route("/login", methods=["GET"])
    def login():
        """로그인 토큰 확인 → nonce 사용 처리 → 세션 쿠키 발급."""
        token = flask.request.args.get("t", "")

        # 서명 검증
        payload = _verify_signature(token, "login")
        if not payload or not payload.get("n"):
            return (
                flask.render_template_string(
                    """<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="color-scheme" content="dark">
<title>로그인 실패</title>
<style>body{background:#0f0f0f;color:#e8e8e8;font-family:system-ui;padding:2rem}
h1{color:#ff6b6b}</style></head>
<body><h1>로그인 실패</h1>
<p>링크가 만료됐거나 이미 사용됐습니다. 텔레그램에서 /admin 을 다시 보내세요.</p>
</body></html>"""
                ),
                403,
            )

        # 만료 확인
        if payload.get("exp", 0) < int(clock()):
            return (
                flask.render_template_string(
                    """<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="color-scheme" content="dark">
<title>로그인 실패</title>
<style>body{background:#0f0f0f;color:#e8e8e8;font-family:system-ui;padding:2rem}
h1{color:#ff6b6b}</style></head>
<body><h1>로그인 실패</h1>
<p>링크가 만료됐거나 이미 사용됐습니다. 텔레그램에서 /admin 을 다시 보내세요.</p>
</body></html>"""
                ),
                403,
            )

        nonce = payload.get("n")

        # nonce 사용 처리 (admin_nonces.json)
        max_retries = 3
        for attempt in range(max_retries):
            try:
                nonces_data, sha = ops_store.read_json("admin_nonces.json")
                if nonces_data is None:
                    nonces_data = {"used": {}}

                used = nonces_data.get("used", {})

                # 이미 사용됐는지 확인
                if nonce in used:
                    return (
                        flask.render_template_string(
                            """<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="color-scheme" content="dark">
<title>로그인 실패</title>
<style>body{background:#0f0f0f;color:#e8e8e8;font-family:system-ui;padding:2rem}
h1{color:#ff6b6b}</style></head>
<body><h1>로그인 실패</h1>
<p>링크가 만료됐거나 이미 사용됐습니다. 텔레그램에서 /admin 을 다시 보내세요.</p>
</body></html>"""
                        ),
                        403,
                    )

                # nonce 사용 처리
                now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
                used[nonce] = now_iso

                # 2일 이상 지난 항목 제거 (cleanup)
                cutoff = int(clock()) - 2 * 86400
                used = {
                    n: ts
                    for n, ts in used.items()
                    if (
                        isinstance(ts, str)
                        and datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() > cutoff
                    )
                }

                nonces_data["used"] = used
                ops_store.write_json(
                    "admin_nonces.json",
                    nonces_data,
                    prev_sha=sha,
                    message=f"admin: nonce 사용 처리 ({nonce[:8]}...)",
                )
                break  # 성공
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(f"nonce 사용 처리 실패: {e}")
                    return (
                        flask.render_template_string(
                            """<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="color-scheme" content="dark">
<title>서버 오류</title>
<style>body{background:#0f0f0f;color:#e8e8e8;font-family:system-ui;padding:2rem}
h1{color:#ff6b6b}</style></head>
<body><h1>서버 오류</h1><p>다시 시도해주세요.</p></body></html>"""
                        ),
                        500,
                    )

        # 세션 쿠키 발급
        sid = secrets.token_hex(8)
        cookie_value, cookie_kwargs = _make_session_cookie(sid)
        resp = flask.redirect("/admin/")
        resp.set_cookie("mt_admin", cookie_value, **cookie_kwargs)
        return resp

    @bp.route("/", methods=["GET"])
    def admin_page():
        """관리 페이지 (admin.html 서빙). 세션 필요."""
        if not _verify_session():
            return (
                flask.render_template_string(
                    """<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="color-scheme" content="dark">
<title>로그인 필요</title>
<style>body{background:#0f0f0f;color:#e8e8e8;font-family:system-ui;padding:2rem}</style></head>
<body><h1>로그인 필요</h1>
<p>텔레그램에서 /admin 을 보내 로그인 링크를 받으세요.</p></body></html>"""
                ),
                401,
            )

        # admin.html 서빙
        html_path = Path(__file__).parent / "admin_static" / "admin.html"
        if not html_path.exists():
            return "admin.html not found", 500

        with open(html_path, "r", encoding="utf-8") as f:
            html = f.read()

        response = flask.make_response(html)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Type"] = "text/html; charset=utf-8"
        return response

    # ─── CSRF 토큰 ────────────────────────────────────────────────────────────

    @bp.route("/api/csrf", methods=["GET"])
    def csrf_token():
        """CSRF 토큰 발급. 세션 필요."""
        session = _verify_session()
        if not session:
            return flask.jsonify({"error": "로그인 필요"}), 401

        token = _get_csrf_token(session["sid"])
        resp = flask.jsonify({"token": token})
        resp.headers["Cache-Control"] = "no-store"
        return resp

    # ─── 읽기 API ─────────────────────────────────────────────────────────────

    @bp.route("/api/<name>", methods=["GET"])
    def read_api(name: str):
        """읽기 API. 세션 필요."""
        session = _verify_session()
        if not session:
            return flask.jsonify({"error": "로그인 필요"}), 401

        # 읽기 함수 목록
        read_functions = {
            "list_preview",
            "list_notices",
            "list_tweets",
            "get_control",
            "list_history",
            "list_lost",
            "list_jobs",
            "channels",
        }

        if name not in read_functions:
            return flask.jsonify({"error": "함수 없음"}), 404

        try:
            func = getattr(api, name)

            # list_history 는 limit 파라미터 지원
            if name == "list_history":
                limit = flask.request.args.get("limit", default=50, type=int)
                result = func(limit=limit)
            else:
                result = func()

            resp = flask.jsonify(result)
            resp.headers["Cache-Control"] = "no-store"
            return resp
        except Exception as e:
            logger.error(f"{name} 실패: {e}")
            return flask.jsonify({"ok": False, "error": str(e)[:300]}), 500

    # ─── 쓰기 API ─────────────────────────────────────────────────────────────

    @bp.route("/api/<name>", methods=["POST"])
    def write_api(name: str):
        """쓰기 API. 세션 + CSRF 필요."""
        session = _verify_session()
        if not session:
            return flask.jsonify({"error": "로그인 필요"}), 401

        # CSRF 검증
        csrf_header = flask.request.headers.get("X-CSRF-Token", "")
        expected_csrf = _get_csrf_token(session["sid"])
        if not hmac.compare_digest(csrf_header, expected_csrf):
            return flask.jsonify({"error": "CSRF 검증 실패"}), 403

        # 쓰기 함수 목록
        write_functions = {
            "edit_preview",
            "delete_preview",
            "ingest_preview_raw",
            "ingest_notice_raw",
            "ingest_tweet_raw",
            "edit_notice",
            "delete_notice",
            "delete_tweet",
            "translate",
            "retry_lost",
            "set_paused",
            "set_log_level",
            "set_monitor_auto",
            "undo",
        }

        if name not in write_functions:
            return flask.jsonify({"error": "함수 없음"}), 404

        # JSON 바디 파싱
        try:
            body = flask.request.get_json() or {}
            if not isinstance(body, dict):
                return flask.jsonify({"error": "바디는 dict여야 함"}), 400
        except Exception as e:
            return flask.jsonify({"error": f"JSON 파싱 실패: {e}"}), 400

        try:
            func = getattr(api, name)
            result = func(**body)

            resp = flask.jsonify(result)
            resp.headers["Cache-Control"] = "no-store"
            return resp
        except TypeError as e:
            # 예상 밖의 키워드 인수
            logger.debug(f"{name} 호출 실패 (TypeError): {e}")
            return flask.jsonify({"error": str(e)[:300]}), 400
        except Exception as e:
            logger.error(f"{name} 실패: {e}")
            return flask.jsonify({"ok": False, "error": str(e)[:300]}), 500

    return bp


# ══════════════════════════════════════════════════════════════════════════════
# Self-test
# ══════════════════════════════════════════════════════════════════════════════


if __name__ == "__main__":
    import sys
    import tempfile

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    print("Admin Web Self-test\n")

    # 페이크 시간 제어
    class FakeClock:
        def __init__(self):
            self.now = int(time.time())

        def __call__(self):
            return self.now

        def advance(self, seconds):
            self.now += seconds

    clock = FakeClock()
    secret = "test_secret_key_12345"

    # 페이크 API
    class FakeAPI:
        def list_preview(self):
            return {"items": []}

        def list_notices(self):
            return {"notices": []}

        def list_history(self, limit=50):
            return [{"id": "1", "action": "edit_preview"}]

        def edit_preview(self, item_id, patch, seen):
            return {"ok": True, "job_id": "job_1", "result": {}}

    fake_api = FakeAPI()

    # LocalStore 임포트
    from .local_store import LocalStore

    with tempfile.TemporaryDirectory() as tmpdir:
        ops_store = LocalStore(tmpdir, "ops")

        bp = create_blueprint(
            api=fake_api,
            ops_store=ops_store,
            secret=secret,
            session_hours=12,
            clock=clock,
        )

        # Flask 앱 생성
        app = flask.Flask(__name__)
        app.register_blueprint(bp)

        # 테스트 클라이언트
        client = app.test_client()

        test_count = 0
        test_pass = 0

        def assert_test(condition: bool, name: str):
            global test_count, test_pass
            test_count += 1
            if condition:
                test_pass += 1
                print(f"  ✓ {name}")
            else:
                print(f"  ✗ {name}")
                raise AssertionError(name)

        # 1. 로그인 링크 생성 → 유효한 토큰
        print("1. 로그인 링크 검증")
        url = make_login_url("http://localhost", secret=secret, ttl_sec=300, clock=clock)
        assert_test("t=" in url, "로그인 URL에 t 파라미터 있음")

        # 2. 토큰 파싱 (비공개 함수이므로 직접 테스트 하지 않고 엔드포인트로 테스트)
        print("\n2. 로그인 엔드포인트")
        token = url.split("t=")[1]
        resp = client.get(f"/admin/login?t={token}")
        assert_test(resp.status_code == 302, "유효한 토큰 → 302 리다이렉트")
        # Set-Cookie 헤더에 mt_admin 쿠키가 있는지 확인
        set_cookie_headers = resp.headers.getlist("Set-Cookie")
        has_cookie = any("mt_admin" in c for c in set_cookie_headers)
        assert_test(has_cookie, "세션 쿠키 설정됨")

        # 3. 같은 토큰 재사용 → 403
        print("\n3. 토큰 재사용 차단")
        resp = client.get(f"/admin/login?t={token}")
        assert_test(resp.status_code == 403, "재사용된 토큰 → 403")

        # 4. 만료된 토큰 → 403
        print("\n4. 만료된 토큰 차단")
        # 먼저 지금 시점에서 토큰을 만든다
        past_url = make_login_url("http://localhost", secret=secret, ttl_sec=300, clock=clock)
        past_token = past_url.split("t=")[1]
        # 그 다음 시간을 5분 이상 진행시킨다
        clock.advance(400)  # 5분 초과
        resp = client.get(f"/admin/login?t={past_token}")
        assert_test(resp.status_code == 403, "만료된 토큰 → 403")

        # 5. 변조된 서명 → 403
        print("\n5. 변조된 서명 차단")
        tampered = url.split("t=")[1][:-4] + "xxxx"
        resp = client.get(f"/admin/login?t={tampered}")
        assert_test(resp.status_code == 403, "변조된 서명 → 403")

        # 6. 세션 쿠키로 /admin 접근 → 200
        print("\n6. /admin 엔드포인트")
        # 새 토큰으로 로그인
        new_url = make_login_url("http://localhost", secret=secret, ttl_sec=300, clock=clock)
        new_token = new_url.split("t=")[1]
        resp = client.get(f"/admin/login?t={new_token}")
        # Set-Cookie 헤더에서 mt_admin 쿠키 값 추출
        cookie = None
        for sc in resp.headers.getlist("Set-Cookie"):
            if sc.startswith("mt_admin="):
                cookie = sc.split(";")[0].replace("mt_admin=", "")
                break

        # 테스트용 admin.html 파일 생성 (임시 경로)
        # 주의: 실제 admin.html은 src/backend/admin_static/ 에 있어야 함
        admin_html_real = Path(__file__).parent / "admin_static" / "admin.html"
        if not admin_html_real.exists():
            # 테스트 실행 시 파일이 없으면 임시로 생성해야 함
            # 하지만 여기서는 파일이 이미 created되어 있으므로 패스
            pass

        resp = client.get("/admin/", headers={"Cookie": f"mt_admin={cookie}"})
        assert_test(resp.status_code == 200, "세션 쿠키로 /admin 접근 → 200")

        # 7. 세션 없이 /admin 접근 → 401
        print("\n7. 세션 없이 접근 차단")
        # 새로운 클라이언트를 사용하여 쿠키가 없는 상태 보장
        client_fresh = app.test_client()
        resp = client_fresh.get("/admin/")
        assert_test(resp.status_code == 401, "세션 없이 /admin → 401")

        # 8. GET /admin/api/list_preview (세션 필요)
        print("\n8. 읽기 API")
        # 새로운 클라이언트 사용 (쿠키 없음)
        client_fresh2 = app.test_client()
        resp = client_fresh2.get("/admin/api/list_preview")
        assert_test(resp.status_code == 401, "세션 없이 API 읽기 → 401")

        resp = client.get("/admin/api/list_preview", headers={"Cookie": f"mt_admin={cookie}"})
        assert_test(resp.status_code == 200, "세션으로 API 읽기 → 200")
        assert_test(resp.json == {"items": []}, "list_preview 결과 반환")

        # 9. POST without CSRF → 403
        print("\n9. CSRF 검증")
        resp = client.post(
            "/admin/api/edit_preview",
            json={"item_id": "1", "patch": {}, "seen": {}},
            headers={"Cookie": f"mt_admin={cookie}"},
        )
        assert_test(resp.status_code == 403, "CSRF 없이 POST → 403")

        # 10. POST with CSRF → 200
        csrf_resp = client.get("/admin/api/csrf", headers={"Cookie": f"mt_admin={cookie}"})
        csrf_token = csrf_resp.json["token"]
        resp = client.post(
            "/admin/api/edit_preview",
            json={"item_id": "1", "patch": {}, "seen": {}},
            headers={"Cookie": f"mt_admin={cookie}", "X-CSRF-Token": csrf_token},
        )
        assert_test(resp.status_code == 200, "CSRF 토큰으로 POST → 200")
        assert_test(resp.json["ok"] is True, "edit_preview 결과 반환")

        # 11. GET unknown name → 404
        print("\n10. 함수 미등록 처리")
        resp = client.get("/admin/api/unknown_func", headers={"Cookie": f"mt_admin={cookie}"})
        assert_test(resp.status_code == 404, "미등록 함수 → 404")

        resp = client.post(
            "/admin/api/unknown_func",
            json={},
            headers={"Cookie": f"mt_admin={cookie}", "X-CSRF-Token": csrf_token},
        )
        assert_test(resp.status_code == 404, "미등록 함수 POST → 404")

        # 12. POST to read-only function → 404
        print("\n11. 읽기 전용 함수에 POST")
        resp = client.post(
            "/admin/api/list_preview",
            json={},
            headers={"Cookie": f"mt_admin={cookie}", "X-CSRF-Token": csrf_token},
        )
        assert_test(resp.status_code == 404, "읽기 함수 POST → 404")

        # 13. Session expiry
        print("\n12. 세션 만료")
        clock.advance(int(12 * 3600) + 1)  # 12시간 초과
        resp = client.get("/admin/api/list_preview", headers={"Cookie": f"mt_admin={cookie}"})
        assert_test(resp.status_code == 401, "만료된 세션 → 401")

        # 14. admin_nonces.json 저장 확인
        print("\n13. admin_nonces.json 저장 확인")
        nonce_data, _ = ops_store.read_json("admin_nonces.json")
        assert_test(nonce_data is not None, "admin_nonces.json 생성됨")
        assert_test("used" in nonce_data, "used 필드 있음")

        # 15. (Claude 검증 추가) 용도 구분: 로그인 토큰을 세션 쿠키로 쓰면 거부 (nonce 소모 없이 접근 불가)
        print("\n14. 로그인 토큰 ↔ 세션 쿠키 재사용 차단")
        fresh_url = make_login_url("http://localhost", secret=secret, clock=clock)
        login_token = fresh_url.split("t=", 1)[1]
        client_x = app.test_client()
        resp = client_x.get("/admin/api/list_preview", headers={"Cookie": f"mt_admin={login_token}"})
        assert_test(resp.status_code == 401, "로그인 토큰을 쿠키로 → 401")
        resp = client_x.get(f"/admin/login?t={cookie}")
        assert_test(resp.status_code == 403, "세션 쿠키를 로그인 토큰으로 → 403")

        print(f"\n{'='*60}")
        print(f"Test Results: {test_pass}/{test_count} passed")
        if test_pass == test_count:
            print("✓ All tests passed!")
        else:
            print(f"✗ {test_count - test_pass} test(s) failed")
            sys.exit(1)
