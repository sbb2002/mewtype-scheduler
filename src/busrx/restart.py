"""로컬 러너 재시작 — 패치 적용 후 새 코드로 다시 띄우고 건강한지 확인한다 (Windows 기준).

러너는 운영자가 다른 터미널에서 켜 둔 프로세스다. 수신기가 그 프로세스를 종료하고 같은 명령을 분리된 프로세스로 다시 띄운다.
안전 확인: runner.json 의 pid 가 실제로 `local_runner` 를 실행 중일 때만 종료한다(엉뚱한 프로세스를 죽이지 않는다).
재시작 뒤 출력은 `<러너 폴더>/_runner.log` 에 남는다(원래 터미널 화면에는 더 이상 안 보임).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


def _runner_json(runner_dir: Path) -> dict:
    try:
        return json.loads((runner_dir / "_local" / "ops" / "runner.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def _cmdline(pid: int) -> str:
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command",
                            f"(Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}').CommandLine"],
                           capture_output=True, text=True, timeout=20)
        return r.stdout.strip()
    except Exception:
        return ""


def find_runner(runner_dir: Path) -> int | None:
    pid = _runner_json(runner_dir).get("pid")
    if not pid:
        return None
    return int(pid) if "local_runner" in _cmdline(int(pid)) else None


def healthy(runner_dir: Path, since: float = 0.0, timeout: float = 90.0, bus_dir: Path | None = None) -> bool:
    """/healthz-local ok 이고(가능하면) 발신기 hb 가 since 이후 갱신됐으면 건강."""
    port = _runner_json(runner_dir).get("port") or os.environ.get("LOCAL_PORT", "8787")
    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz-local", timeout=3) as r:
                ok = json.loads(r.read().decode()).get("ok") is True
        except Exception:
            ok = False
        if ok:
            if bus_dir is None:
                return True
            try:
                hb = json.loads((bus_dir / "hb" / "publisher.json").read_text(encoding="utf-8"))
                import datetime as dt
                ts = dt.datetime.strptime(hb["ts"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc).timestamp()
                if ts >= since:
                    return True
            except Exception:
                pass
        time.sleep(2)
    return False


def restart_runner(runner_dir: Path, python: str = "", bus_dir: Path | None = None) -> tuple[bool, str]:
    """(성공 여부, 설명). 러너가 떠 있지 않았으면 재시작하지 않는다."""
    pid = find_runner(runner_dir)
    if pid is None:
        return False, "러너가 실행 중이 아님(runner.json pid 없음/불일치) — 재시작 생략"
    py = python or str(runner_dir / ".venv" / "Scripts" / "python.exe")
    if not Path(py).exists():
        py = sys.executable
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=30)
    time.sleep(3)
    t0 = time.time()
    log = open(runner_dir / "_runner.log", "ab")
    flags = 0x00000008 | 0x00000200 | 0x08000000  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    subprocess.Popen([py, "-m", "src.backend.local_runner"], cwd=runner_dir, stdout=log, stderr=subprocess.STDOUT,
                     stdin=subprocess.DEVNULL, creationflags=flags, env=env, close_fds=True)
    ok = healthy(runner_dir, since=t0, bus_dir=bus_dir)
    return ok, f"러너 재시작({int(time.time() - t0)}초)" + ("" if ok else " — 건강 확인 실패")
