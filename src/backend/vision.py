"""Groq 비전(OCR) 클라이언트 — 크로스오버 공지 이미지 속 출연진 이름 추출 (v3.2).

배경: 프랜차이즈 공식 계정(예: `@bang_dream_on`)의 공지 트윗은 출연진 명단을
텍스트가 아니라 **첨부 이미지 그래픽**으로만 제공하는 경우가 있다. 업스트림
Automate 는 텍스트 알림만 중계하므로, 이미지 속 이름은 텍스트 파이프라인
(`xnotice.py`)으로는 절대 못 읽는다 — vxtwitter(`vxtwitter.py`)로 이미지 URL
자체는 얻을 수 있지만, 그 안의 글자를 읽으려면 비전 모델이 필요하다.

실측(2026-09-13): Groq `qwen/qwen3.6-27b`/`qwen/qwen3.8-27b` 둘 다 열린 질문
("이미지를 설명해줘")에는 발음·번역을 지어내는 할루시네이션이 섞였지만, "보이는
글자만 그대로, 지어내지 말고 모르면 ?" 로 범위를 좁히자 정답과 완전히 일치했다.
그래서 이 모듈은 항상 좁은 프롬프트(`_CAST_PROMPT`)만 쓴다 — 호출부가 프롬프트를
바꿀 수 없게 일부러 파라미터화하지 않았다.

일반 텍스트 LLM(`llm.py`, gpt-oss 계열)보다 이 두 비전 모델은 무료 티어 TPM/OTPM
한도가 훨씬 낮다(실측: qwen3.6-27b 는 thinking 모드가 길면 출력 토큰 한도에
쉽게 걸림) — 그래서 항상 `reasoning_effort:"none"` + 짧은 `max_tokens` 로 호출하고,
메인 모델이 실패(429/5xx/타임아웃/파싱 실패)하면 즉시 폴백 모델로 1회만 재시도한다
(llm.py 처럼 같은 모델에 지수 백오프 3회를 하지 않음 — 한도가 낮아 오히려 폴백
모델로 빨리 넘어가는 게 유리).

명세: docs/VERSION.md v3.2.0
"""
from __future__ import annotations

import base64
import logging
import re

import requests

logger = logging.getLogger(__name__)

DEFAULT_VISION_MODEL = "qwen/qwen3.8-27b"
FALLBACK_VISION_MODEL = "qwen/qwen3.6-27b"

# "N. <이름>" 형식 한 줄씩 — 프롬프트가 강제하는 출력 포맷.
_NAME_LINE_RE = re.compile(r"^\s*\d+\.\s*(.+?)\s*$", re.MULTILINE)

_CAST_PROMPT = (
    "이미지 속 인물 사진 아래에 적힌 일본어 이름(한자/가나)만 옮겨 적어라.\n"
    "규칙:\n"
    "1. 실제로 보이는 글자만 그대로 옮겨 적는다. 요미가나(발음)나 한국어 번역을 절대 추가하지 않는다.\n"
    "2. 확실하지 않은 글자는 지어내지 말고 ? 로 표시한다.\n"
    "3. 왼쪽부터 순서대로, 인물당 한 줄씩만 출력한다. 다른 설명·서론·결론은 쓰지 않는다.\n"
    "4. 형식: `N. <이름 그대로>`"
)


def _parse_names(text: str) -> list[str]:
    """"N. <이름>" 라인들에서 이름만 뽑는다. "?" 단독(판독 실패)은 버린다."""
    out = []
    for m in _NAME_LINE_RE.findall(text or ""):
        name = m.strip()
        if name and name != "?":
            out.append(name)
    return out


class VisionClient:
    """Groq 비전 모델 클라이언트 — 이미지 속 텍스트를 좁은 프롬프트로만 판독."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = DEFAULT_VISION_MODEL,
        fallback: str = FALLBACK_VISION_MODEL,
        session: "requests.Session | None" = None,
        timeout: float = 30.0,
    ):
        self.api_key = (api_key or "").strip()
        self.model = model
        self.fallback = fallback
        self.session = session or requests.Session()
        self.timeout = timeout
        self.disabled = not self.api_key

    def cast_names(
        self, *, image_url: str | None = None, image_bytes: bytes | None = None
    ) -> list[str] | None:
        """이미지에서 인물 이름 목록을 추출.

        Args:
            image_url: 공개 이미지 URL (있으면 우선 — 다운로드 왕복이 없어 더 빠름)
            image_bytes: 로컬 이미지 바이트 (image_url 없을 때 data URI 로 변환)

        Returns:
            이름 문자열 리스트(판독 실패한 인물은 제외) 또는 완전 실패 시 None.
            빈 리스트(`[]`)는 "호출은 됐지만 아무도 인식 못 함"과 다르게, 프롬프트가
            최소 1명은 있는 이미지를 전제하므로 사실상 안 나옴 — None 과 동일 취급 권장.
        """
        if self.disabled:
            logger.warning("VisionClient disabled (api_key missing)")
            return None
        if not image_url and not image_bytes:
            return None

        if image_url:
            image_content = {"type": "image_url", "image_url": {"url": image_url}}
        else:
            b64 = base64.b64encode(image_bytes).decode("ascii")
            image_content = {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
            }

        for model in (self.model, self.fallback):
            text = self._call(model, image_content)
            if text is None:
                continue
            names = _parse_names(text)
            if names:
                return names
            logger.warning("vision: %s 응답에서 이름 파싱 실패 (%r)", model, text[:200])

        return None

    def _call(self, model: str, image_content: dict) -> str | None:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": _CAST_PROMPT}, image_content],
                }
            ],
            "temperature": 0,
            "max_tokens": 300,
            "reasoning_effort": "none",
        }
        try:
            resp = self.session.post(url, json=payload, headers=headers, timeout=self.timeout)
        except requests.RequestException as e:
            logger.warning("vision: %s 네트워크 오류 — %s", model, e)
            return None

        if resp.status_code != 200:
            logger.warning("vision: %s %s %s", model, resp.status_code, resp.text[:200])
            return None

        try:
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError) as e:
            logger.warning("vision: %s 응답 파싱 실패 — %s", model, e)
            return None

        logger.info("vision ok model=%s out=%r", model, (content or "")[:200])
        return content


if __name__ == "__main__":
    import os
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    print("=" * 70)
    print("vision.py 스모크 테스트")
    print("=" * 70)

    # ── 시나리오 1: disabled (api_key 없음) ──
    vc_disabled = VisionClient("")
    assert vc_disabled.disabled is True
    assert vc_disabled.cast_names(image_url="https://example.com/x.jpg") is None
    print("[OK] disabled 상태 → None")

    # ── 시나리오 2: 인자 없음 → None (네트워크 미시도) ──
    vc_noarg = VisionClient("test-key")
    assert vc_noarg.cast_names() is None
    print("[OK] image_url/image_bytes 둘 다 없음 → None")

    # ── 시나리오 3: _parse_names ──
    sample = "1. 羊宮 妃那\n2. 渡瀬 結月\n3. ?\n4. 結川 あさき"
    assert _parse_names(sample) == ["羊宮 妃那", "渡瀬 結月", "結川 あさき"], _parse_names(sample)
    print("[OK] _parse_names: 번호 라인 추출 + '?' 제외")

    # ── 시나리오 4: 메인 모델 200 성공 ──
    class FakeSession:
        def __init__(self, responses):
            self.responses = responses  # {model: (status, content)}
            self.calls = []

        def post(self, url, *, json, headers, timeout):
            model = json["model"]
            self.calls.append(model)
            status, content = self.responses.get(model, (500, ""))

            class R:
                status_code = status
                text = content if status != 200 else ""

                def json(self):
                    return {"choices": [{"message": {"content": content}}]}

            return R()

    sess = FakeSession({DEFAULT_VISION_MODEL: (200, "1. 宮永 ののか")})
    vc = VisionClient("test-key", session=sess)
    names = vc.cast_names(image_url="https://example.com/cast.jpg")
    assert names == ["宮永 ののか"], names
    assert sess.calls == [DEFAULT_VISION_MODEL], sess.calls
    print("[OK] 메인 모델 성공 → 폴백 호출 안 함")

    # ── 시나리오 5: 메인 429 → 폴백 성공 ──
    sess2 = FakeSession({
        DEFAULT_VISION_MODEL: (429, "rate limited"),
        FALLBACK_VISION_MODEL: (200, "1. 宮永 ののか\n2. 渡瀬 結月"),
    })
    vc2 = VisionClient("test-key", session=sess2)
    names2 = vc2.cast_names(image_url="https://example.com/cast.jpg")
    assert names2 == ["宮永 ののか", "渡瀬 結月"], names2
    assert sess2.calls == [DEFAULT_VISION_MODEL, FALLBACK_VISION_MODEL], sess2.calls
    print("[OK] 메인 429 → 즉시 폴백 1회 → 성공")

    # ── 시나리오 6: 둘 다 실패 → None ──
    sess3 = FakeSession({})  # 둘 다 500
    vc3 = VisionClient("test-key", session=sess3)
    assert vc3.cast_names(image_url="https://example.com/cast.jpg") is None
    assert sess3.calls == [DEFAULT_VISION_MODEL, FALLBACK_VISION_MODEL], sess3.calls
    print("[OK] 메인·폴백 둘 다 실패 → None")

    # ── 시나리오 7: image_bytes → data URI 인코딩 ──
    sess4 = FakeSession({DEFAULT_VISION_MODEL: (200, "1. 宮永 ののか")})
    vc4 = VisionClient("test-key", session=sess4)
    result = vc4.cast_names(image_bytes=b"\xff\xd8\xff")  # 가짜 JPEG 헤더
    assert result == ["宮永 ののか"], result
    print("[OK] image_bytes → data URI 인코딩 경로 정상")

    print("\nSUCCESS: vision.py self-test 통과 (mock)")

    # ── 실호출 (--live 플래그 + GROQ_API_KEY 있을 때만) ──
    if "--live" in sys.argv:
        key = os.environ.get("GROQ_API_KEY", "")
        if not key:
            print("\n[skip] --live 이지만 GROQ_API_KEY 없음")
        else:
            print("\n" + "=" * 70)
            print("실호출 테스트 (fixtures/awarnoutz_cast.jpg 필요)")
            print("=" * 70)
            fixture = os.path.join(
                os.path.dirname(__file__), "..", "..", "fixtures", "awarnoutz_cast.jpg"
            )
            if not os.path.exists(fixture):
                print(f"[skip] fixture 없음: {fixture}")
            else:
                vc_live = VisionClient(key)
                with open(fixture, "rb") as f:
                    names = vc_live.cast_names(image_bytes=f.read())
                print("실측 결과:", names)
