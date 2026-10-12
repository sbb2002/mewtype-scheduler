"""파이프라인 조립 화면 API self-test — 조회 · 실시간 검증 · 저장 · 삭제 · 정책 연동 (Flask 테스트 클라이언트).

    python -m src.busrx.selftest_builder
"""
from __future__ import annotations

import copy
import sys
import tempfile
import time
from pathlib import Path

from . import pipelines as P
from .receiver import Config, Receiver
from .selftest_web import FakeTG
from .web import create_app, make_token

SECRET = "builder-secret-0123456789"


def main() -> int:
    def check(c, m):
        assert c, m
        print("OK ", m)

    tmp = Path(tempfile.mkdtemp(prefix="mewbld_"))
    cfg = Config(bus_dir=tmp / "bus", stage=2, runner_dir=tmp)
    rx = Receiver(cfg, FakeTG())
    app = create_app(rx, cfg, FakeTG(), SECRET, "http://127.0.0.1:8789")
    c = app.test_client()
    std = copy.deepcopy(P.BUILTIN["standard"]["blocks"])

    check(c.get("/api/pipelines").status_code == 401, "미인증 /api/pipelines 는 401")
    c.get("/auth?t=" + make_token(SECRET, time.time()))
    h = {"X-CSRF": c.get("/api/me").get_json()["csrf"]}

    # 조회
    g = c.get("/api/pipelines").get_json()
    check({"standard", "urgent"} <= set(g["pipelines"]) and g["pipelines"]["standard"]["builtin"], "조회: 내장 프리셋 포함")
    check(len(g["catalog"]) == 11 and g["catalog"]["guard"]["locked"] and g["catalog"]["protected"]["locked"] and not g["catalog"]["verify"]["locked"],
          "조회: 블록 카탈로그(11개)와 잠금 여부")
    check(g["param_rules"]["implement"]["max_revisions"] == [0, 3] and "claude-haiku-5-5" in g["models"] and g["locked_order"][2] == "implement",
          "조회: 설정 범위 · 허용 모델 · 잠금 순서")
    check(g["used_by"].get("urgent") == ["CRITICAL"] and g["used_by"].get("standard") and "ERROR" in g["used_by"]["standard"], "조회: 정책이 쓰는 파이프라인 표시")

    # 실시간 검증 (저장하지 않음)
    check(c.post("/api/pipelines/validate", json={"blocks": std}).status_code == 403, "CSRF 없는 검증 요청은 403")
    check(c.post("/api/pipelines/validate", json={"blocks": std}, headers=h).get_json()["errors"] == [], "검증: 유효한 조립은 오류 없음")
    no_guard = [b for b in std if b["id"] != "guard"]
    e = c.post("/api/pipelines/validate", json={"blocks": no_guard}, headers=h).get_json()["errors"]
    check(e and "가드" in e[0] and "뺄 수 없음" in e[0], "검증: 가드를 빼면 즉시 오류")
    check(c.post("/api/pipelines/validate", json={}, headers=h).get_json()["errors"], "검증: blocks 없음도 오류(예외 없이)")
    check(c.post("/api/pipelines/validate", json={"blocks": "문자열"}, headers=h).get_json()["errors"], "검증: 형식이 잘못돼도 서버가 죽지 않음")
    check(not P.load_custom(cfg), "검증 요청은 아무것도 저장하지 않음")

    # 저장
    swap = copy.deepcopy(std)
    vi, ri = [b["id"] for b in swap].index("verify"), [b["id"] for b in swap].index("review")
    swap[vi], swap[ri] = swap[ri], swap[vi]
    r = c.post("/api/pipelines", json={"id": "careful", "name": "신중(검토 먼저)", "blocks": swap}, headers=h)
    check(r.status_code == 200 and "careful" in c.get("/api/pipelines").get_json()["pipelines"], "저장: 사용자 정의 파이프라인")
    check(P.resolve(cfg, "careful").blocks[5]["id"] == "review", "저장된 순서가 엔진이 읽는 정의에 그대로 반영")
    r = c.post("/api/pipelines", json={"id": "weak", "name": "가드 없음", "blocks": no_guard}, headers=h)
    check(r.status_code == 400 and r.get_json()["errors"] and "weak" not in c.get("/api/pipelines").get_json()["pipelines"], "저장: 가드 없는 조립은 400 + 저장 안 됨")
    check(c.post("/api/pipelines", json={"id": "standard", "name": "덮어쓰기", "blocks": std}, headers=h).status_code == 400, "저장: 내장 id 덮어쓰기 거부")
    check(c.post("/api/pipelines", json={"id": "Bad Id", "name": "x", "blocks": std}, headers=h).status_code == 400, "저장: 잘못된 id 거부")
    check(c.post("/api/pipelines", json={"id": "x1", "blocks": std}, headers=h).status_code in (200, 400), "저장: 이름 없이도 서버가 죽지 않음")

    # 정책 연동: 저장한 파이프라인을 정책에서 고르고, 쓰는 중이면 삭제 거부
    check("careful" in c.get("/api/policy").get_json()["presets"], "정책 화면의 프리셋 목록에 사용자 정의가 나타남")
    check(c.post("/api/policy", json={"policy": {"ERROR": {"preset": "careful"}}}, headers=h).status_code == 200, "정책에서 사용자 정의 파이프라인 선택")
    r = c.post("/api/pipelines/delete", json={"id": "careful"}, headers=h)
    check(r.status_code == 409 and "ERROR" in r.get_json()["errors"][0], "삭제: 정책이 쓰는 중이면 409(어느 레벨인지 안내)")
    c.post("/api/policy", json={"policy": {"ERROR": {"preset": "standard"}}}, headers=h)
    check(c.post("/api/pipelines/delete", json={"id": "careful"}, headers=h).status_code == 200 and "careful" not in c.get("/api/pipelines").get_json()["pipelines"],
          "삭제: 정책에서 빠진 뒤에는 삭제됨")
    check(c.post("/api/pipelines/delete", json={"id": "standard"}, headers=h).status_code in (400, 409) and "standard" in c.get("/api/pipelines").get_json()["pipelines"], "삭제: 내장 프리셋은 삭제 불가")
    check(c.post("/api/pipelines/delete", json={"id": "없음"}, headers=h).status_code == 400, "삭제: 없는 id")

    # 초기화: 정책 / 파이프라인 / 전체
    P.save_custom(cfg, "keep1", "하나", std)
    P.save_custom(cfg, "keep2", "둘", std)
    c.post("/api/policy", json={"policy": {"ERROR": {"preset": "keep1", "cooldown_sec": 5}, "WARN": {"action": "analyze"}}}, headers=h)
    check(c.post("/api/reset", json={"what": "policy"}).status_code == 403, "초기화: CSRF 없으면 403")
    check(c.post("/api/reset", json={"what": "nothing"}, headers=h).status_code == 400, "초기화: 알 수 없는 대상은 400")
    r = c.post("/api/reset", json={"what": "policy"}, headers=h).get_json()
    check(r["ok"] and r["policy"]["ERROR"]["preset"] == "standard" and r["policy"]["WARN"]["action"] == "off" and {"keep1", "keep2"} <= set(P.load_custom(cfg)),
          "정책만 초기화: 정책은 기본값, 사용자 정의 파이프라인은 그대로")
    c.post("/api/policy", json={"policy": {"ERROR": {"preset": "keep1"}}}, headers=h)
    n_custom = len(P.load_custom(cfg))
    r = c.post("/api/reset", json={"what": "pipelines"}, headers=h).get_json()
    check(r["ok"] and r["pipelines_removed"] == n_custom >= 2 and not P.load_custom(cfg) and set(c.get("/api/pipelines").get_json()["pipelines"]) == {"standard", "urgent"},
          "파이프라인만 초기화: 사용자 정의 전부 삭제, 내장만 남음")
    check(r["policy"]["ERROR"]["preset"] == "standard", "삭제된 파이프라인을 가리키던 정책은 기본 프리셋으로 안전하게 대체")
    hist = (cfg.rx / "pipelines_history.jsonl").read_text(encoding="utf-8").splitlines()
    check(len(hist) == 1 and f'"removed": {n_custom}' in hist[0], "파이프라인 초기화 이력 기록")
    P.save_custom(cfg, "again", "다시", std)
    c.post("/api/policy", json={"policy": {"CRITICAL": {"cooldown_sec": 1}}}, headers=h)
    r = c.post("/api/reset", json={"what": "all"}, headers=h).get_json()
    check(r["policy_reset"] and r["pipelines_removed"] == 1 and r["policy"]["CRITICAL"]["cooldown_sec"] == cfg.cooldown_critical and not P.load_custom(cfg),
          "전체 초기화: 정책 기본값 + 사용자 정의 모두 삭제")
    check(not (cfg.rx / "PAUSE").exists(), "전체 초기화는 수신기 정지(PAUSE) 같은 일시 설정을 건드리지 않음")
    check(c.post("/api/reset", json={"what": "pipelines"}, headers=h).get_json()["pipelines_removed"] == 0, "이미 초기 상태에서 다시 초기화해도 오류 없음")

    # 화면 파일
    html = (Path(__file__).parent / "web_static" / "index.html").read_text(encoding="utf-8")
    check(all(x in html for x in ('data-t="pipelines"', 'id="pl-chain"', 'id="pl-detail"', 'id="pl-save"', "/api/pipelines/validate", "🔒", 'id="pl-revert"', 'id="pl-reset-all"', 'id="reset-all"', "/api/reset")), "화면: 조립 탭 · 블록 도식 · 설정 패널 · 실시간 검증 호출")
    print("모두 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
