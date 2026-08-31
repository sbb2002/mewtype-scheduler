"""OIDC bearer 토큰 검증 (방어적 심화).

verify_request: Flask request.headers 에서 Bearer 토큰 추출·검증.
"""

import logging
import os

try:
    from google.oauth2 import id_token
    from google.auth.transport import requests as ga_requests
except ImportError:
    # 라이브러리 미설치 환경에서 import 시도 — 스모크는 skip 처리
    id_token = None
    ga_requests = None

logger = logging.getLogger(__name__)


def verify_request(
    headers, *, expected_audience: str, expected_sa: str | None = None
) -> None:
    """Flask request.headers 에서 Bearer 토큰 추출·검증.

    환경변수 ALLOW_UNAUTH == '1' 이면 검증 스킵 (로컬 개발용).
    그 외에는 필수 Authorization 헤더 + Google OAuth2 토큰 검증.

    Args:
        headers: dict-like (Flask request.headers).
        expected_audience: OIDC 토큰의 audience 클레임 (Cloud Run 서비스 URL).
        expected_sa: 토큰 발급자 (서비스계정 email). 미지정 시 검증 스킵.

    Raises:
        PermissionError: 검증 실패 시. 이유는 메시지에 포함.
    """
    # ALLOW_UNAUTH 환경변수 확인 (로컬 개발)
    if os.getenv("ALLOW_UNAUTH") == "1":
        logger.debug("ALLOW_UNAUTH=1: Authorization skipped")
        return

    # Authorization 헤더 추출
    auth_header = headers.get("Authorization", "")
    if not auth_header:
        raise PermissionError("missing bearer token")

    # "Bearer <token>" 파싱
    parts = auth_header.split(" ")
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise PermissionError("invalid authorization header format")

    token = parts[1]

    # Google OAuth2 토큰 검증
    if id_token is None or ga_requests is None:
        raise RuntimeError(
            "google-auth not installed. "
            "Install with: pip install google-auth"
        )

    try:
        payload = id_token.verify_oauth2_token(
            token, ga_requests.Request(), audience=expected_audience
        )
    except Exception as e:
        raise PermissionError(f"token verification failed: {e}") from e

    # payload['iss'] 검증
    iss = payload.get("iss")
    if iss not in ("https://accounts.google.com", "accounts.google.com"):
        raise PermissionError(f"invalid issuer: {iss}")

    # expected_sa 검증 (옵션)
    if expected_sa:
        email = payload.get("email")
        if email != expected_sa:
            raise PermissionError(
                f"token email mismatch: expected {expected_sa}, got {email}"
            )

    logger.debug(f"Token verified for {payload.get('email')}")


# Self-test
if __name__ == "__main__":
    import sys

    print("Testing verify_request...")

    # Test 1: ALLOW_UNAUTH=1 이면 no-op
    os.environ["ALLOW_UNAUTH"] = "1"
    try:
        verify_request({}, expected_audience="https://example.com")
        print("[OK] ALLOW_UNAUTH=1 skips verification")
    except Exception as e:
        print(f"[FAIL] ALLOW_UNAUTH=1 test failed: {e}")
        sys.exit(1)
    finally:
        del os.environ["ALLOW_UNAUTH"]

    # Test 2: 토큰 없음 → PermissionError
    try:
        verify_request({}, expected_audience="https://example.com")
        print("[FAIL] Should raise PermissionError for missing token")
        sys.exit(1)
    except PermissionError as e:
        if "missing bearer token" in str(e):
            print("[OK] PermissionError raised for missing token")
        else:
            print(f"[FAIL] Unexpected error message: {e}")
            sys.exit(1)

    # Test 3: 잘못된 Authorization 헤더
    try:
        verify_request(
            {"Authorization": "Basic xyz"},
            expected_audience="https://example.com",
        )
        print("[FAIL] Should raise PermissionError for invalid header")
        sys.exit(1)
    except PermissionError as e:
        if "invalid authorization header format" in str(e):
            print("[OK] PermissionError raised for invalid header format")
        else:
            print(f"[FAIL] Unexpected error message: {e}")
            sys.exit(1)

    # Test 4: google-auth 라이브러리 미설치 시 테스트
    if id_token is None or ga_requests is None:
        print("-- google-auth not installed. Skipping token verification tests.")
        print("   Install with: pip install google-auth")
        print("\n[PASS] Baseline tests passed (token verification tests skipped)")
        sys.exit(0)

    # Test 5: 실제 토큰 검증은 네트워크 필요 (제약상 mock만 테스트)
    # 여기서는 import 성공만 확인
    print("[OK] google-auth library loaded")

    print("\n[PASS] All smoke tests passed!")
