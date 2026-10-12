"""파이프라인(블록 조립) 규칙 self-test — 검증 · 저장 · 정책 연동 (git · claude 없이 즉시 실행).

    python -m src.busrx.selftest_pipeline
엔진이 블록 설정대로 실제로 도는지는 `python -m src.busrx.selftest_fix` (S14~S18).
"""
from __future__ import annotations

import copy
import sys
import tempfile
from pathlib import Path

from . import pipelines as P
from .policy import Policy
from .receiver import Config


def blocks(**over):
    """표준 파이프라인 복사본. over: {블록id: {enabled/params 변경}}"""
    b = copy.deepcopy(P.BUILTIN["standard"]["blocks"])
    for x in b:
        if x["id"] in over:
            x.update(over[x["id"]])
    return b


def main() -> int:
    def check(c, m):
        assert c, m
        print("OK ", m)

    def bad(bl, frag, msg):
        errs = P.validate({"id": "x", "blocks": bl})
        check(errs and any(frag in e for e in errs), f"{msg} → {errs[0] if errs else '통과함(오류)'}")

    # 1) 내장 프리셋
    check(not P.validate(P.BUILTIN["standard"]) and not P.validate(P.BUILTIN["urgent"]), "내장 프리셋(표준 · 긴급)은 유효")
    ids = [b["id"] for b in P.BUILTIN["standard"]["blocks"]]
    check(ids == ["spec", "worktree", "implement", "guard", "tests", "verify", "review", "commit", "protected", "apply", "restart"], "표준 파이프라인 블록 순서")
    u = P.Pipeline(P.BUILTIN["urgent"])
    check(not u.enabled("verify") and not u.enabled("review") and u.enabled("guard") and u.param("tests", "core") is False, "긴급: 검증·검토 꺼짐, 가드 켜짐, 변경 모듈 테스트만")

    # 2) 잠금 블록: 빼기 · 끄기 · 순서 바꾸기 불가
    for bid in P.LOCKED_ORDER:
        bad([b for b in blocks() if b["id"] != bid], "뺄 수 없음", f"잠금 블록 '{bid}' 제거 거부")
        bad(blocks(**{bid: {"enabled": False}}), "끌 수 없음", f"잠금 블록 '{bid}' 비활성 거부")
    b = blocks()
    gi, ii = [x["id"] for x in b].index("guard"), [x["id"] for x in b].index("implement")
    b[gi], b[ii] = b[ii], b[gi]
    bad(b, "순서는 바꿀 수 없음", "가드와 구현 순서 뒤바꿈 거부")

    # 3) 선택 블록 위치 규칙
    b = [x for x in blocks() if x["id"] != "verify"]
    b.insert([x["id"] for x in b].index("commit") + 1, {"id": "verify", "enabled": True, "params": {}})
    bad(b, "앞에만", "검증을 커밋 뒤에 놓기 거부")
    b = blocks()
    vi, ri = [x["id"] for x in b].index("verify"), [x["id"] for x in b].index("review")
    b[vi], b[ri] = b[ri], b[vi]
    check(not P.validate({"id": "x", "blocks": b}), "검증 · 독립 검토 순서 바꾸기는 허용")
    b = [x for x in blocks() if x["id"] not in ("verify", "review")]
    check(not P.validate({"id": "x", "blocks": b}), "검증 · 독립 검토를 아예 빼는 것은 허용(경고는 화면에서)")
    bad([x for x in blocks() if x["id"] != "apply"], "있어야", "적용 없이 재시작만 있는 것 거부")
    b = blocks()
    ai, pi = [x["id"] for x in b].index("apply"), [x["id"] for x in b].index("protected")
    b[ai], b[pi] = b[pi], b[ai]
    bad(b, "뒤에 놓아야", "적용을 보호 확인 앞에 놓기 거부")
    bad(blocks(apply={"enabled": False}), "재시작도 켤 수 없음", "적용을 끄고 재시작만 켜기 거부")
    check(not P.validate({"id": "x", "blocks": blocks(apply={"enabled": False}, restart={"enabled": False})}), "적용 · 재시작 둘 다 끄기는 허용")
    check(not P.validate({"id": "x", "blocks": blocks(restart={"enabled": False})}), "재시작만 끄기는 허용")

    # 4) 일반 오류
    bad(blocks() + [{"id": "verify", "enabled": True, "params": {}}], "두 번", "같은 블록 중복 거부")
    bad(blocks() + [{"id": "deploy_to_prod", "enabled": True}], "알 수 없는 블록", "알 수 없는 블록 거부")
    bad(blocks(implement={"params": {"max_revisions": 9}}), "max_revisions", "수정 라운드 상한 초과 거부")
    bad(blocks(implement={"params": {"max_revisions": -1}}), "max_revisions", "수정 라운드 음수 거부")
    bad(blocks(implement={"params": {"model": "gpt-9"}}), "model", "허용되지 않은 모델 거부")
    bad(blocks(implement={"params": {"budget": 99}}), "budget", "비용 상한 초과 거부")
    bad(blocks(guard={"params": {"strict": True}}), "알 수 없는 설정", "가드에 알 수 없는 설정 거부")
    bad(blocks(tests={"params": {"core": "yes"}}), "true/false", "tests.core 가 불리언이 아니면 거부")
    check(P.validate({"id": "x", "blocks": []}) and P.validate({"id": "x"}), "빈 파이프라인 거부")

    # 5) 저장 · 불러오기 · 삭제 · 손상 복구
    tmp = Path(tempfile.mkdtemp(prefix="mewpl_"))
    cfg = Config(bus_dir=tmp / "bus", runner_dir=tmp)
    (cfg.rx).mkdir(parents=True)
    check(set(P.all_pipelines(cfg)) == {"standard", "urgent"}, "사용자 정의가 없으면 내장 프리셋만")
    check(P.save_custom(cfg, "careful", "신중(검토 먼저)", blocks(review={"enabled": True}, implement={"params": {"max_revisions": 2}})) == [], "사용자 정의 저장")
    check(P.resolve(cfg, "careful").param("implement", "max_revisions") == 2 and P.presets_view(cfg)["careful"]["builtin"] is False, "저장한 파이프라인을 불러옴(내장 아님 표시)")
    check(P.save_custom(cfg, "standard", "덮어쓰기", blocks()), "내장 id 덮어쓰기 거부")
    check(P.save_custom(cfg, "Bad Id!", "x", blocks()), "잘못된 id 거부")
    check(P.save_custom(cfg, "weak", "약한", [x for x in blocks() if x["id"] != "guard"]), "가드 없는 파이프라인은 저장 거부")
    check(P.resolve(cfg, "없는것").id == "standard", "알 수 없는 id 는 표준으로 안전하게 대체")
    (cfg.rx / "pipelines.json").write_text('{"pipelines": {"evil": {"name": "x", "blocks": [{"id": "commit"}]}}}', encoding="utf-8")
    check("evil" not in P.all_pipelines(cfg), "파일을 손으로 고쳐 만든 부정 파이프라인(가드 없음)은 로드 시 무시")
    (cfg.rx / "pipelines.json").write_text("{깨짐", encoding="utf-8")
    check(set(P.all_pipelines(cfg)) == {"standard", "urgent"}, "파일이 손상되면 내장 프리셋만")
    P.save_custom(cfg, "careful", "신중", blocks())
    check(P.delete_custom(cfg, "careful") and not P.delete_custom(cfg, "standard") and "careful" not in P.all_pipelines(cfg), "사용자 정의 삭제 · 내장은 삭제 불가")

    # 6) 정책 연동: 사용자 정의 id 를 고를 수 있고, 없는 id 는 거부
    P.save_custom(cfg, "careful", "신중", blocks())
    pol = Policy(cfg.rx / "policy.json", cfg)
    new, errs = pol.save({"ERROR": {"preset": "careful"}})
    check(not errs and pol.get("ERROR")["preset"] == "careful", "정책에서 사용자 정의 파이프라인 선택")
    _, errs = pol.save({"ERROR": {"preset": "ghost"}})
    check(errs, "정책에서 없는 파이프라인 id 는 거부")
    P.delete_custom(cfg, "careful")
    check(Policy(cfg.rx / "policy.json", cfg).get("ERROR")["preset"] == "standard", "정책이 가리키던 파이프라인이 삭제되면 안전하게 기본값(표준)으로")
    print("모두 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
