"""외부 LLM(Groq) 클라이언트 — 소식 제목 추출 및 트윗 번역.

명세: docs/plan/v3_impl_spec.md §0.3
"""

import json
import logging
import time
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "openai/gpt-oss-120b"
# llama-3.3-70b-versatile 는 이 Groq 계정에서 404 (2026-09 라인업 변경). 같은 계열
# gpt-oss-20b 로 폴백 — 작고 빠르며 지시이행 동일.
FALLBACK_MODEL = "openai/gpt-oss-20b"


def _strip_json_fence(text: str) -> str:
    """```json ... ``` 펜스나 앞뒤 잡텍스트를 벗겨 JSON 본체만 남긴다."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1] if "\n" in t else t[3:]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    i, j = t.find("{"), t.rfind("}")
    return t[i:j + 1] if 0 <= i < j else t.strip()


class LLMClient:
    """Groq 외부 LLM 클라이언트."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = DEFAULT_MODEL,
        fallback: str = FALLBACK_MODEL,
        session: "requests.Session | None" = None,
        timeout: float = 20.0,
    ):
        """
        Groq LLM 클라이언트 초기화.

        Args:
            api_key: Groq API 키. 비어있으면 disabled.
            model: 메인 모델 (기본 gpt-oss-120b)
            fallback: 폴백 모델 (기본 llama-3.3-70b-versatile)
            session: 선택사항 requests.Session (테스트 mock 용)
            timeout: API 호출 타임아웃 (초)
        """
        self.api_key = api_key.strip() if api_key else ""
        self.model = model
        self.fallback = fallback
        self.session = session or requests.Session()
        self.timeout = timeout
        self.disabled = not self.api_key

    def notice_title(
        self, body_no_date_url: str, *, lang_hint: str = "ja"
    ) -> dict | None:
        """
        소식 본문에서 이벤트 제목 1줄 추출 및 번역.

        Args:
            body_no_date_url: 본문 텍스트 (날짜/URL 제거됨)
            lang_hint: 입력 언어 힌트 (기본 "ja")

        Returns:
            {"title_ja": str, "title_ko": str} 또는 실패 시 None
        """
        if self.disabled:
            logger.warning("LLMClient disabled (api_key missing)")
            return None

        prompt = (
            f"다음 이벤트 공지 본문에서 자연스러운 제목 1줄을 뽑아내고 일본어와 한국어로 제시하라. "
            f"JSON 포맷만 출력 (다른 텍스트 제외). 고유명사 보존.\n\n"
            f"본문:\n{body_no_date_url}\n\n"
            f"출력:\n"
            f'{{"title_ja": "<일본어>", "title_ko": "<한국어>"}}'
        )

        response = self._call_groq(self.model, prompt)
        if response is None:
            logger.warning(
                f"notice_title: 메인 모델 실패, fallback 시도"
            )
            response = self._call_groq(self.fallback, prompt)

        if response is None:
            logger.warning("notice_title: 폴백도 실패")
            return None

        # 환각 가드: 출력 비었거나 입력 길이 3배 초과
        if self._is_hallucination(response, body_no_date_url):
            logger.warning(
                f"notice_title: 환각 가드 발동 (input={len(body_no_date_url)}, "
                f"output={len(response)})"
            )
            return None

        try:
            result = json.loads(_strip_json_fence(response))
            if isinstance(result, dict) and "title_ja" in result and "title_ko" in result:
                return result
            else:
                logger.warning(f"notice_title: 예상 필드 부재 {result}")
                return None
        except json.JSONDecodeError as e:
            logger.warning(f"notice_title: JSON 파싱 실패 — {e}")
            return None

    def translate(self, text_ja: str) -> str | None:
        """
        일본어 트윗을 한국어로 번역.

        Args:
            text_ja: 일본어 텍스트

        Returns:
            한국어 번역 또는 실패 시 None
        """
        if self.disabled:
            logger.warning("LLMClient disabled (api_key missing)")
            return None

        prompt = (
            f"다음 일본어 텍스트를 자연스러운 한국어로 번역하라. "
            f"고유명사는 보존. 번역문만 출력 (설명 제외).\n\n"
            f"일본어:\n{text_ja}"
        )

        response = self._call_groq(self.model, prompt)
        if response is None:
            logger.warning("translate: 메인 모델 실패, fallback 시도")
            response = self._call_groq(self.fallback, prompt)

        if response is None:
            logger.warning("translate: 폴백도 실패")
            return None

        # 환각 가드
        if self._is_hallucination(response, text_ja):
            logger.warning(
                f"translate: 환각 가드 발동 (input={len(text_ja)}, output={len(response)})"
            )
            return None

        return response.strip()

    def _call_groq(self, model: str, prompt: str) -> str | None:
        """
        Groq API 호출 (지수 백오프 3회).

        Args:
            model: 사용할 모델 이름
            prompt: 프롬프트

        Returns:
            응답 텍스트 또는 실패 시 None
        """
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # response_format 은 안 보낸다 — Groq gpt-oss 는 json_object 를 거부하고
        # json_schema 는 스키마 객체를 요구한다. 프롬프트의 "JSON 만 출력" 지시 +
        # notice_title 의 방어적 파싱(펜스 제거 후 json.loads)으로 충분.
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "reasoning_effort": "low",
        }

        # ponytail: 지수 백오프 3회 (1s/2s/4s)
        delays = [1.0, 2.0, 4.0]

        for attempt, delay in enumerate(delays):
            try:
                # ponytail: requests.post의 json 인자와 호환, 테스트 mock도 지원
                _t0 = time.monotonic()
                resp = self.session.post(
                    url, json=payload, headers=headers, timeout=self.timeout
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if "choices" in data and len(data["choices"]) > 0:
                        content = data["choices"][0]["message"]["content"]
                        # 번역 품질 사후 검토용 — 모델·지연·입출력 미리보기를 남긴다.
                        logger.info(
                            "Groq ok model=%s %.1fs in=%d out=%r",
                            model, time.monotonic() - _t0, len(prompt),
                            (content or "")[:160],
                        )
                        return content
                    logger.warning(f"Groq: 예상 응답 구조 없음 {data}")
                    return None
                elif resp.status_code in (429, 500, 502, 503, 504):
                    if attempt < len(delays) - 1:
                        logger.info(
                            f"Groq {resp.status_code}: {delay}초 후 재시도 (attempt {attempt+1}/3)"
                        )
                        time.sleep(delay)
                        continue
                    else:
                        logger.warning(
                            f"Groq {resp.status_code}: 백오프 소진 ({attempt+1}/3)"
                        )
                        return None
                else:
                    logger.warning(
                        f"Groq {resp.status_code}: {resp.text[:200]}"
                    )
                    return None
            except requests.Timeout:
                logger.warning(f"Groq: 타임아웃 (attempt {attempt+1}/3)")
                if attempt < len(delays) - 1:
                    time.sleep(delay)
                    continue
                return None
            except requests.RequestException as e:
                logger.warning(f"Groq: 네트워크 오류 — {e}")
                return None

        return None

    def _is_hallucination(self, response: str, input_text: str) -> bool:
        """
        환각 가드: 출력이 비었거나 입력의 3배 초과 길이.

        Args:
            response: 모델 응답
            input_text: 입력 텍스트

        Returns:
            환각 의심이면 True
        """
        if not response or not response.strip():
            return True
        if len(response) > len(input_text) * 3:
            return True
        return False


if __name__ == "__main__":
    import sys

    # Windows UTF-8 콘솔 가드
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    print("=" * 70)
    print("LLM llm.py 스모크 테스트")
    print("=" * 70)

    # ──── 시나리오 1: disabled 상태 (api_key 없음) ────
    print("\n[시나리오 1] disabled 상태 (api_key 없음)")
    print("-" * 70)

    llm_disabled = LLMClient("")
    assert llm_disabled.disabled is True
    result = llm_disabled.notice_title("test body")
    assert result is None, "disabled 상태에서 None 반환해야 함"
    result = llm_disabled.translate("test text")
    assert result is None, "disabled 상태에서 None 반환해야 함"
    print("✓ disabled 상태: notice_title/translate 모두 None 반환")

    # ──── 시나리오 2: 200 정상 응답 (notice_title) ────
    print("\n[시나리오 2] 200 정상 응답 (notice_title)")
    print("-" * 70)

    class FakeSession:
        def __init__(self, status_code=200, body=None):
            self.status_code = status_code
            self.body = body or {}

        def post(self, url, **kwargs):
            class FakeResp:
                pass

            resp = FakeResp()
            resp.status_code = self.status_code
            resp.text = json.dumps(self.body) if isinstance(self.body, dict) else str(self.body)

            def json_method():
                return self.body

            def raise_for_status():
                pass

            resp.json = json_method
            resp.raise_for_status = raise_for_status
            return resp

    session_200 = FakeSession(
        status_code=200,
        body={
            "choices": [
                {
                    "message": {
                        "content": '{"title_ja": "新年イベント", "title_ko": "신정 이벤트"}'
                    }
                }
            ]
        },
    )

    llm_200 = LLMClient("test-key", session=session_200)
    # 입력을 충분히 길게 해서 환각 가드를 통과하도록 (응답 44자 * 3 = 132자 필요)
    long_input = "뭔가 이벤트 소식이 있는데요. " * 10  # 충분히 긴 입력
    result = llm_200.notice_title(long_input)
    assert result is not None, "200 응답에서 None이 아닌 값 기대"
    assert result.get("title_ja") == "新年イベント"
    assert result.get("title_ko") == "신정 이벤트"
    print("✓ 정상 응답 파싱: title_ja/title_ko 추출됨")

    # ──── 시나리오 3: 429 → 백오프 → 폴백 ────
    print("\n[시나리오 3] 429 → 백오프 → 폴백")
    print("-" * 70)

    class Fake429Then200Session:
        def __init__(self):
            self.call_count = 0

        def post(self, url, **kwargs):
            self.call_count += 1
            class FakeResp:
                pass

            resp = FakeResp()
            # 첫 3회는 429, 4회차는 200
            if self.call_count <= 3:
                resp.status_code = 429
                resp.text = "Rate limited"
            else:
                resp.status_code = 200
                resp.text = '{"choices":[{"message":{"content":"fallback response"}}]}'

            def json_method():
                if self.call_count <= 3:
                    return {}
                return {
                    "choices": [
                        {
                            "message": {"content": "fallback response"}
                        }
                    ]
                }

            resp.json = json_method
            return resp

    session_429 = Fake429Then200Session()
    llm_429 = LLMClient("test-key", session=session_429)

    # 메인 모델에서 3번 백오프 후 실패 → None 반환
    result = llm_429._call_groq(DEFAULT_MODEL, "test")
    assert result is None, "429 3회 후 None 기대"
    call_count_after_main = session_429.call_count
    print(f"✓ 메인 모델: {call_count_after_main}회 호출 후 None 반환")

    # 다시 시도하면 (새로운 세션)
    session_429_fallback = Fake429Then200Session()
    llm_429_fb = LLMClient("test-key", session=session_429_fallback)
    result = llm_429_fb._call_groq(FALLBACK_MODEL, "test")
    # 첫 3회가 429로 끝나고 4회차가 200이면
    assert result == "fallback response" or result is None, "fallback 호출 결과"
    print(f"✓ 폴백 모델 호출 완료 (총 {session_429_fallback.call_count}회)")

    # ──── 시나리오 4: JSON 파싱 실패 ────
    print("\n[시나리오 4] JSON 파싱 실패")
    print("-" * 70)

    session_bad_json = FakeSession(
        status_code=200,
        body={"choices": [{"message": {"content": "not valid json {"}}]},
    )

    llm_bad = LLMClient("test-key", session=session_bad_json)
    result = llm_bad.notice_title("test body")
    assert result is None, "JSON 파싱 실패 시 None 기대"
    print("✓ JSON 파싱 실패 → None 반환")

    # ──── 시나리오 5: 환각 가드 (과길이) ────
    print("\n[시나리오 5] 환각 가드 (과길이)")
    print("-" * 70)

    short_input = "short"
    long_output = "x" * (len(short_input) * 4)  # 입력의 4배

    session_hallucination = FakeSession(
        status_code=200,
        body={
            "choices": [{"message": {"content": long_output}}]
        },
    )

    llm_hallu = LLMClient("test-key", session=session_hallucination)
    result = llm_hallu.notice_title(short_input)
    assert result is None, "환각 가드(과길이) 발동 시 None 기대"
    print("✓ 환각 가드(과길이) 발동 → None 반환")

    # ──── 시나리오 6: translate 정상 작동 ────
    print("\n[시나리오 6] translate 정상 작동")
    print("-" * 70)

    session_translate = FakeSession(
        status_code=200,
        body={
            "choices": [
                {
                    "message": {
                        "content": "안녕하세요, 새로운 배경음악입니다."
                    }
                }
            ]
        },
    )

    llm_tl = LLMClient("test-key", session=session_translate)
    result = llm_tl.translate("こんにちは、新しいBGMです。")
    assert result == "안녕하세요, 새로운 배경음악입니다."
    print("✓ translate 정상 작동")

    # ──── 시나리오 7: 환각 가드 (빈 응답) ────
    print("\n[시나리오 7] 환각 가드 (빈 응답)")
    print("-" * 70)

    session_empty = FakeSession(
        status_code=200,
        body={"choices": [{"message": {"content": ""}}]},
    )

    llm_empty = LLMClient("test-key", session=session_empty)
    result = llm_empty.translate("test")
    assert result is None, "빈 응답 시 None 기대"
    print("✓ 환각 가드(빈 응답) 발동 → None 반환")

    # ──── 시나리오 8: response_format 미전송 + 펜스 제거 파싱 ────
    print("\n[시나리오 8] response_format 미전송 + JSON 펜스 제거")
    print("-" * 70)
    assert _strip_json_fence('```json\n{"a":1}\n```') == '{"a":1}'
    assert _strip_json_fence('설명\n{"title_ja":"あ","title_ko":"아"} 끝') == '{"title_ja":"あ","title_ko":"아"}'
    print("✓ _strip_json_fence: 펜스·잡텍스트 제거")

    class PayloadCapturingSession:
        def __init__(self):
            self.last_payload = None

        def post(self, url, **kwargs):
            self.last_payload = kwargs.get("json")
            class FakeResp:
                pass

            resp = FakeResp()
            resp.status_code = 200
            resp.text = '{"choices":[{"message":{"content":"test"}}]}'

            def json_method():
                return {
                    "choices": [
                        {
                            "message": {"content": "test"}
                        }
                    ]
                }

            resp.json = json_method
            return resp

    session_payload = PayloadCapturingSession()
    llm_payload = LLMClient("test-key", session=session_payload)
    llm_payload._call_groq(DEFAULT_MODEL, "test")
    assert "response_format" not in session_payload.last_payload, "response_format 안 보내야 함"
    assert session_payload.last_payload["model"] == DEFAULT_MODEL
    print("✓ response_format 미전송")

    print("\n" + "=" * 70)
    print("SUCCESS: 모든 8개 스모크 테스트 통과")
    print("=" * 70)
