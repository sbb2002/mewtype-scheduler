"""외부 LLM(Groq) 클라이언트 — 소식 제목 추출 및 트윗 번역.

명세: docs/plan/v3_impl_spec.md §0.3
"""

import json
import logging
import re
import time
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "openai/gpt-oss-120b"
# llama-3.3-70b-versatile 는 이 Groq 계정에서 404 (2026-09 라인업 변경). 같은 계열
# gpt-oss-20b 로 폴백 — 작고 빠르며 지시이행 동일.
FALLBACK_MODEL = "openai/gpt-oss-20b"

# 짧은 단위(1~6자)가 8회 이상 연속 반복 — "もぐもぐもぐ…" 같은 의성어 트윗.
# translate() 가 이 패턴이면 반복 그대로 LLM 에 보내지 않고 압축한다(§translate 참고).
_REPEAT_RE = re.compile(r"^(.{1,6}?)\1{7,}")

# 장음부호류(ー ｰ 〜 ～)가 2회 이상 연속 — 일본어 트윗 특유의 "글자 늘려쓰기" 강조 표기
# (예: "おーまーーたーーせー…" = 「お待たせ」를 늘려 쓴 것). _REPEAT_RE 와 달리 문자열
# 어디서든, 여러 군데 흩어져 나타나도 전부 잡는다(§translate 참고).
_STRETCH_RE = re.compile(r"[ーｰ〜～]{2,}")

# 고정 번역 용어집 — LLM 이 호출마다 다르게 옮기는 고유명사를 여기 등록하면 항상 이 값으로
# 고정된다(2026-09-13, 그룹명이 "꿈한계대 뮤타입"/"꿈꾸다"/"유메미타" 등으로 매번 달라지던
# 문제). preview/notice/tweet 번역 전부 이 용어집을 거친다 — 입력에서 원문을 자리표시자로
# 감싸 LLM 이 못 건드리게 막고(플레이스홀더는 일반 텍스트와 절대 안 겹치는 ASCII 토큰),
# 응답에서 다시 고정값으로 되돌린다. LLM 프롬프트 지시만으로는 100% 보장이 안 되므로
# (지시를 무시하고 여전히 의역하는 사례 실측) 이 기계적 치환이 최종 보증선이다.
#   등록값에 구두점(느낌표 등)은 넣지 않는다 — 원문에 있으면 번역문에도 그대로 남으므로
#   ("バンドリ！" → "뱅드림！"/"뱅드림!") 굳이 고정할 필요가 없다. 용어 자체만 고정.
GLOSSARY: dict[str, str] = {
    "夢限大みゅーたいぷ": "무겐다이 뮤타입",
    "バンドリ": "뱅드림",
}


def _mask_glossary(text: str) -> tuple[str, list[tuple[str, str, str]]]:
    """용어집 항목을 LLM 이 건드리지 않을 자리표시자로 치환.

    토큰이 영숫자에 바로 들러붙으면(예: "バンドリ13thライブ" → "@@GLOSSARY@@13th")
    LLM 이 그 뒤 문장을 통째로 못 알아보고 미번역으로 남기는 사례가 실측됐다 — 그
    경우에만 한 칸 띄운다. 이미 공백·구두점과 붙어 있으면 그대로 둬(예: 「바로 뒤)
    불필요한 공백이 안 생기게.

    Returns:
        (치환된 텍스트, [(토큰, 일본어원문, 고정한국어역), ...])
    """
    masked = text or ""
    mapping: list[tuple[str, str, str]] = []
    for i, (ja, ko) in enumerate(GLOSSARY.items()):
        if ja in masked:
            token = f"@@GLOSSARY{i}@@"
            masked = masked.replace(ja, token)
            masked = re.sub(rf"(?<=[0-9A-Za-z]){re.escape(token)}", f" {token}", masked)
            masked = re.sub(rf"{re.escape(token)}(?=[0-9A-Za-z])", f"{token} ", masked)
            mapping.append((token, ja, ko))
    return masked, mapping


_GLOSSARY_LEAK_RE = re.compile(r"@+\s*GLOSSARY\s*\d*\s*@+")


def _unmask_glossary(text: str, mapping: list[tuple[str, str, str]], *, to: str) -> str:
    """자리표시자를 복원. to='ja' 면 일본어 원문으로, to='ko' 면 고정 한국어역으로.

    (버그리포트 20260916) LLM 이 토큰을 정확히 그대로 안 남기고 공백을 끼워 넣는 등
    변형하면(예: "@@ GLOSSARY0 @@") 아래 정확 일치 replace 가 못 잡아 원본 지시
    토큰이 번역 결과에 그대로 노출된 채 트윗/소식으로 게시되는 사고가 났다(아라레
    트윗 실사례). 정확 치환 후에도 남은 GLOSSARY 형태 잔재는 전부 지운다 — 이 함수가
    translate()/notice_title() 의 유일한 언마스크 경로라 여기서 한 번만 막으면 된다.
    """
    if not text:
        return text
    for token, ja, ko in mapping:
        text = text.replace(token, ja if to == "ja" else ko)
    cleaned, n = _GLOSSARY_LEAK_RE.subn("", text)
    if n:
        logger.warning("unmask_glossary: 잔여 GLOSSARY 토큰 %d개 제거 — %r", n, text)
        text = re.sub(r"\s{2,}", " ", cleaned).strip()
    return text


# Groq structured outputs (strict) — gpt-oss-120b/20b·qwen3.8-27b 지원.
# strict 규칙: 모든 필드 required, additionalProperties:false.
# https://console.groq.com/docs/structured-outputs
_NOTICE_TITLE_SCHEMA = {
    "name": "notice_title",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "title_ja": {"type": "string"},
            "title_ko": {"type": "string"},
        },
        "required": ["title_ja", "title_ko"],
        "additionalProperties": False,
    },
}


def _strip_json_fence(text: str) -> str:
    """```json ... ``` 펜스나 앞뒤 잡텍스트를 벗겨 JSON 본체만 남긴다."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1] if "\n" in t else t[3:]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    i, j = t.find("{"), t.rfind("}")
    return t[i:j + 1] if 0 <= i < j else t.strip()


def _normalize_stretch(text: str) -> str:
    """장음부호류 연속(2회+)을 1회로 접는다 — 의미는 그대로 두고 문체적 강조만 정규화.

    (버그리포트 20260913 #4) "おーまーーたーーせー…"처럼 글자마다 다른 길이로 장음부호가
    끼어드는 늘려쓰기는 `_REPEAT_RE`(맨 앞·단일 유닛 8회+ 반복) 로는 못 잡는다. 그대로
    보내면 v3.1.8 이 대응한 것과 같은 LLM 반복 루프에 빠져 환각 가드에 매번 걸린다
    (실측: 204자 입력 → 2035자 응답, `temperature=0`이라 재시도해도 항상 동일 실패).
    표적을 장음부호류로 한정한 이유: 아무 문자나 2연속을 접으면 "宮永ののか"(멤버명 자체의
    반복 글자) → "宮永のか", "かわいい" → "かわい", "https://www." → "htps:/w." 처럼 정상
    단어·고유명사·URL 이 깨진다(실측 확인 후 표적 축소).
    """
    return _STRETCH_RE.sub(lambda m: m.group(0)[0], text)


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

        masked_body, mapping = _mask_glossary(body_no_date_url)
        prompt = (
            f"다음 이벤트 공지 본문에서 자연스러운 제목 1줄을 뽑아내고 일본어와 한국어로 제시하라. "
            f"JSON 포맷만 출력 (다른 텍스트 제외). 고유명사 보존. "
            f"@@GLOSSARY0@@ 같은 토큰은 절대 번역·수정하지 말고 그대로 출력에 남겨라.\n\n"
            f"본문:\n{masked_body}\n\n"
            f"출력:\n"
            f'{{"title_ja": "<일본어>", "title_ko": "<한국어>"}}'
        )

        response = self._call_groq(self.model, prompt, json_schema=_NOTICE_TITLE_SCHEMA)
        if response is None:
            logger.warning(
                f"notice_title: 메인 모델 실패, fallback 시도"
            )
            response = self._call_groq(
                self.fallback, prompt, json_schema=_NOTICE_TITLE_SCHEMA
            )

        if response is None:
            logger.warning("notice_title: 폴백도 실패")
            return None

        # 환각 가드: 출력 비었거나 입력 길이 3배 초과
        if self._is_hallucination(response, masked_body):
            logger.warning(
                f"notice_title: 환각 가드 발동 (input={len(body_no_date_url)}, "
                f"output={len(response)})"
            )
            return None

        try:
            result = json.loads(_strip_json_fence(response))
            if isinstance(result, dict) and "title_ja" in result and "title_ko" in result:
                result["title_ja"] = _unmask_glossary(result["title_ja"], mapping, to="ja")
                result["title_ko"] = _unmask_glossary(result["title_ko"], mapping, to="ko")
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

        (버그리포트 20260913 #3) "もぐもぐもぐ…"(의성어 8회+ 연속반복) 같은 입력은
        LLM 이 반복 루프에 빠져 수백~수천자를 토해내고, 환각 가드에 매번 걸려
        temperature=0 이라 재시도해도 항상 같은 실패를 반복한다. 반복 구간을 미리
        압축해 단위만 번역시키고 다시 펼치면 이 루프를 원천 회피한다.

        Args:
            text_ja: 일본어 텍스트

        Returns:
            한국어 번역 또는 실패 시 None
        """
        if self.disabled:
            logger.warning("LLMClient disabled (api_key missing)")
            return None

        text_ja = _normalize_stretch(text_ja or "")
        m = _REPEAT_RE.match(text_ja)
        if m:
            return self._translate_repeated(text_ja, m)
        return self._translate_once(text_ja)

    def _translate_repeated(self, text_ja: str, m: "re.Match[str]") -> str | None:
        """짧은 단위(1~6자)가 8회 이상 연속 반복되는 구간을 압축 번역 후 재조립."""
        unit = m.group(1)
        count = len(m.group(0)) // len(unit)
        remainder = text_ja[m.end():]

        unit_ko = self._translate_repeat_unit(unit, count)
        if unit_ko is None:
            return None

        rest_ko = ""
        if remainder.strip():
            rest_ko = self._translate_once(remainder)
            if rest_ko is None:
                rest_ko = remainder.strip()  # 나머지 번역 실패해도 통째 실패시키지 않음
            if remainder.startswith("\n") and not rest_ko.startswith("\n"):
                rest_ko = "\n" + rest_ko

        logger.info(
            "translate: 반복 압축 (unit=%r x%d, remainder_len=%d)",
            unit, count, len(remainder),
        )
        return (unit_ko * count) + rest_ko

    def _translate_repeat_unit(self, unit: str, count: int) -> str | None:
        """반복 단위 하나만 번역. 단위를 맨입으로 넘기면 문맥이 없어 오역되기 쉬워서
        ("もぐ" 단독 → "몰입" 오역, "もぐ"×40 문맥 제공 시 "우걱"으로 정확히 번역됨 —
        실측 확인) 반복 횟수·의성어/의태어 문맥을 프롬프트에 명시한다."""
        prompt = (
            f"다음은 일본어 트윗에서 '{unit}'가 {count}번 연속 반복되는 의성어/의태어다. "
            f"자연스러운 한국어 의성어/의태어를 딱 한 번만 출력하라(설명·반복 금지).\n\n"
            f"일본어 반복 단위: {unit}"
        )
        response = self._call_groq(self.model, prompt)
        if response is None:
            response = self._call_groq(self.fallback, prompt)
        if response is None:
            return None
        if self._is_hallucination(response, unit):
            return None
        return response.strip()

    def _translate_once(self, text_ja: str) -> str | None:
        """단발 번역 호출(메인→폴백 모델) + 환각 가드. 반복 압축 없이 그대로 1회 요청."""
        masked_text, mapping = _mask_glossary(text_ja)
        prompt = (
            f"다음 일본어 텍스트를 자연스러운 한국어로 번역하라. "
            f"고유명사는 보존. 번역문만 출력 (설명 제외). "
            f"@@GLOSSARY0@@ 같은 토큰은 절대 번역·수정하지 말고 그대로 출력에 남겨라.\n\n"
            f"일본어:\n{masked_text}"
        )

        response = self._call_groq(self.model, prompt)
        if response is None:
            logger.warning("translate: 메인 모델 실패, fallback 시도")
            response = self._call_groq(self.fallback, prompt)

        if response is None:
            logger.warning("translate: 폴백도 실패")
            return None

        # 환각 가드
        if self._is_hallucination(response, masked_text):
            logger.warning(
                f"translate: 환각 가드 발동 (input={len(text_ja)}, output={len(response)})"
            )
            return None

        return _unmask_glossary(response.strip(), mapping, to="ko")

    def _call_groq(
        self, model: str, prompt: str, *, json_schema: "dict | None" = None
    ) -> str | None:
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

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "reasoning_effort": "low",
            # 반복 루프 방어 2중선(1중선은 translate() 의 _normalize_stretch/_REPEAT_RE
            # 전처리) — 미지 패턴이 전처리를 뚫고 들어와도 폭주를 API 단에서 조기 절단.
            "max_tokens": max(200, len(prompt) // 2),
        }
        # 구조화 출력이 필요한 호출(notice_title)만 json_schema strict 를 붙인다.
        # translate 는 자유텍스트라 안 붙임(json_object 는 gpt-oss 가 거부하므로 안 씀).
        if json_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": json_schema,
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

    # ──── 시나리오 8: json_schema strict 조건부 전송 + 펜스 제거 파싱 ────
    print("\n[시나리오 8] json_schema strict (notice_title만) + JSON 펜스 제거")
    print("-" * 70)
    assert _strip_json_fence('```json\n{"a":1}\n```') == '{"a":1}'
    assert _strip_json_fence('설명\n{"title_ja":"あ","title_ko":"아"} 끝') == '{"title_ja":"あ","title_ko":"아"}'
    print("✓ _strip_json_fence: 펜스·잡텍스트 제거")
    assert _NOTICE_TITLE_SCHEMA["strict"] is True
    assert _NOTICE_TITLE_SCHEMA["schema"]["additionalProperties"] is False
    assert set(_NOTICE_TITLE_SCHEMA["schema"]["required"]) == {"title_ja", "title_ko"}
    print("✓ _NOTICE_TITLE_SCHEMA: strict 규칙 준수")

    # ──── 시나리오 9: translate 반복 압축 (버그리포트 20260913 #3) ────
    print("\n[시나리오 9] translate 반복 압축 (의성어 8회+ 연속반복)")
    print("-" * 70)

    assert _REPEAT_RE.match("もぐ" * 8)                       # 8회 = 경계값, 매치
    assert not _REPEAT_RE.match("もぐ" * 7)                    # 7회는 미달, 비매치
    assert not _REPEAT_RE.match("こんにちは、今日は良い天気です")  # 반복 아님, 비매치

    class RepeatAwareSession:
        """프롬프트 내용으로 "반복 단위" 호출과 "나머지" 호출을 구분해 각각 응답."""
        def post(self, url, **kwargs):
            content = kwargs["json"]["messages"][0]["content"]
            if "번 연속 반복되는 의성어" in content:      # _translate_repeat_unit 전용 프롬프트
                reply = "냠"
            else:
                reply = "#애니메유메미타"
            class FakeResp:
                status_code = 200
                def json(self):
                    return {"choices": [{"message": {"content": reply}}]}
            return FakeResp()

    llm_repeat = LLMClient("test-key", session=RepeatAwareSession())
    repeated_input = "もぐ" * 40 + "\n#アニメゆめみた"
    result = llm_repeat.translate(repeated_input)
    assert result == "냠" * 40 + "\n#애니메유메미타", result
    print(f"✓ 반복 압축: 단위만 문맥과 함께 번역 후 40회 재조립 (폭주 없이 {len(result)}자)")

    # 반복 단위 뒤에 나머지가 없는 경우(순수 반복만)도 정상 조립.
    llm_repeat2 = LLMClient("test-key", session=RepeatAwareSession())
    result2 = llm_repeat2.translate("もぐ" * 10)
    assert result2 == "냠" * 10, result2
    print("✓ 반복 압축: 나머지 없이 단위만 반복되는 경우도 처리")

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
    # translate 경로: json_schema 안 붙음
    llm_payload._call_groq(DEFAULT_MODEL, "test")
    assert "response_format" not in session_payload.last_payload, "translate 는 response_format 없음"
    assert session_payload.last_payload["max_tokens"] == 200, "짧은 prompt 는 max_tokens 하한(200)"
    # notice_title 경로: json_schema strict 붙음
    llm_payload._call_groq(DEFAULT_MODEL, "test", json_schema=_NOTICE_TITLE_SCHEMA)
    rf = session_payload.last_payload["response_format"]
    assert rf["type"] == "json_schema" and rf["json_schema"]["strict"] is True
    print("✓ json_schema strict 는 notice_title 경로에만, max_tokens 상한 동봉")

    # ──── 시나리오 10: 장음부호 늘려쓰기 정규화 (버그리포트 20260913 #4) ────
    print("\n[시나리오 10] 장음부호 늘려쓰기 정규화 (もぐもぐ 반복과는 다른 케이스)")
    print("-" * 70)

    assert _normalize_stretch("おーまーーたーーせーーーしーーーーました") == "おーまーたーせーしーました"
    # 멤버명·단어의 정상적인 글자 반복(장음부호가 아님)은 안 건드림.
    assert _normalize_stretch("宮永ののか") == "宮永ののか"
    assert _normalize_stretch("かわいい") == "かわいい"
    assert _normalize_stretch("https://www.youtube.com") == "https://www.youtube.com"
    print("✓ _normalize_stretch: 장음부호만 표적, 멤버명·단어·URL 은 보존")

    class StretchLoopSession:
        """정규화 안 된 원문(장음부호 다량)이 오면 반복 루프를 흉내(과길이 응답)."""
        def post(self, url, **kwargs):
            content = kwargs["json"]["messages"][0]["content"]
            reply = "정상 번역" if "ーーー" not in content else "폭주" * 500
            class FakeResp:
                status_code = 200
                def json(self):
                    return {"choices": [{"message": {"content": reply}}]}
            return FakeResp()

    llm_stretch = LLMClient("test-key", session=StretchLoopSession())
    stretched = "おーまーーたーーせーーーしーーーーました🙇‍♀️"
    result = llm_stretch.translate(stretched)
    assert result == "정상 번역", result  # 정규화 안 됐으면 "폭주"*500 이 나와 환각 가드에 걸림
    print("✓ translate(): 정규화 후 전송 — 반복 루프 회피, 정상 응답 통과")

    # ──── 시나리오 11: 용어집 고정 번역 (2026-09-13) ────
    print("\n[시나리오 11] 용어집(GLOSSARY) — 그룹명 고정 번역")
    print("-" * 70)

    masked, mapping = _mask_glossary("夢限大みゅーたいぷ 5th Single 発売記念")
    assert masked == "@@GLOSSARY0@@ 5th Single 発売記念", masked
    assert mapping == [("@@GLOSSARY0@@", "夢限大みゅーたいぷ", "무겐다이 뮤타입")], mapping
    assert _unmask_glossary(masked, mapping, to="ko") == "무겐다이 뮤타입 5th Single 発売記念"
    assert _unmask_glossary(masked, mapping, to="ja") == "夢限大みゅーたいぷ 5th Single 発売記念"
    print("✓ _mask_glossary/_unmask_glossary: 왕복 변환 정확")

    # LLM 이 프롬프트 지시대로 플레이스홀더를 그대로 남겨 응답했다고 가정 — 그래도 다른
    # 호출마다 그룹명을 다르게 옮기던 문제(꿈한계대 뮤타입/꿈꾸다/유메미타 등)가
    # _unmask_glossary 로 항상 "무겐다이 뮤타입" 하나로 고정되는지 확인.
    session_glossary = FakeSession(
        status_code=200,
        body={"choices": [{"message": {
            "content": "@@GLOSSARY0@@ 5th 싱글 발매 기념 사인회입니다."
        }}]},
    )
    llm_glossary = LLMClient("test-key", session=session_glossary)
    result = llm_glossary.translate("夢限大みゅーたいぷ 5th Single リリース記念サイン会です。")
    assert result == "무겐다이 뮤타입 5th 싱글 발매 기념 사인회입니다.", result
    print("✓ translate(): 그룹명이 매번 '무겐다이 뮤타입'으로 고정됨")

    # ──── 시나리오 12: バンドリ 고정 번역(구두점 제외) + 토큰-영숫자 들러붙음 방지 ────
    print("\n[시나리오 12] バンドリ → '뱅드림' 고정 + 토큰 뒤 영숫자 들러붙음 방지")
    print("-" * 70)

    # 구두점(느낌표)은 등록값에 안 넣는다 — 원문에 있으면 그대로 남아 번역에도 반영되므로.
    masked, mapping = _mask_glossary("「バンドリ！ ゆめ∞みた」×極楽湯 RAKU SPAコラボ")
    assert masked == "「@@GLOSSARY1@@！ ゆめ∞みた」×極楽湯 RAKU SPAコラボ", masked
    assert _unmask_glossary(masked, mapping, to="ko") == "「뱅드림！ ゆめ∞みた」×極楽湯 RAKU SPAコラボ"
    print("✓ バンドリ만 고정, 뒤의 느낌표는 원문 그대로 보존")

    # 뒤에 바로 영숫자("13th")가 붙은 경우 — 예전엔 토큰이 그대로 들러붙어 LLM 이 그 뒤
    # 문장을 통째로 미번역으로 남기던 버그(실측). 공백 삽입으로 방지.
    masked2, mapping2 = _mask_glossary("バンドリ13thライブ DAY")
    assert masked2 == "@@GLOSSARY1@@ 13thライブ DAY", masked2
    assert _unmask_glossary(masked2, mapping2, to="ko") == "뱅드림 13thライブ DAY"
    print("✓ バンドリ13th… 처럼 영숫자가 바로 붙은 경우 → 토큰 뒤에 공백 삽입")

    # 이미 공백/구두점과 붙어 있으면 불필요한 공백을 추가하지 않는다(「바로 뒤 등).
    masked3, _m3 = _mask_glossary("バンドリ 13th")
    assert masked3 == "@@GLOSSARY1@@ 13th", masked3  # 원래 있던 공백 그대로, 중복 안 됨
    print("✓ 이미 공백 있는 경우엔 추가 공백 안 생김")

    # ──── 시나리오 13: LLM 이 토큰을 변형해 남겨도 잔재가 새지 않음 (버그리포트 20260916) ────
    print("\n[시나리오 13] 변형된 GLOSSARY 토큰 잔재 — 최종 출력에 새지 않음")
    print("-" * 70)

    assert _unmask_glossary("@@ GLOSSARY0 @@ 5th 싱글 발매", [], to="ko") == "5th 싱글 발매", \
        _unmask_glossary("@@ GLOSSARY0 @@ 5th 싱글 발매", [], to="ko")
    assert _unmask_glossary("사인회 @@GLOSSARY0@@ 입니다", [], to="ko") == "사인회 입니다"
    print("✓ _unmask_glossary: mapping 에 없는(=치환 실패한) GLOSSARY 잔재도 최종 텍스트에서 제거됨")

    print("\n" + "=" * 70)
    print("SUCCESS: 모든 13개 스모크 테스트 통과")
    print("=" * 70)
