from pathlib import Path
import json,hashlib,tempfile
B=Path(__file__).parent;D=B/'delivery';R=Path(r'C:/Users/User/Documents/pyworks/mewtype-scheduler-worktrees/v4/feat-birthday-music-scene')
V=Path(tempfile.gettempdir())/'birthday-verify-third'
gpu=json.loads((V/'performance-headed.json').read_text(encoding='utf8'));cpu=json.loads((V/'performance-software.json').read_text(encoding='utf8'))
rows='\n'.join(f"| {t} | {gpu[t]['mean']:.2f} | {gpu[t]['p95']:.2f} | {cpu[t]['mean']:.2f} | {cpu[t]['p95']:.2f} |" for t in ['7.5','14','17.3','25','110'])
doc=f'''# 생일 음악 장면 3차 검증 (2026-10-31)

브랜치 `feat/birthday-music-scene`. 구현과 로컬 검증 결과이며 배포 승인이 아니다. 버전은 v4.11.0 제안만 유지하며 현재 버전 상수·푸시·병합·배포는 변경하지 않았다.

## 프레임 비용

실제 Windows Chromium의 1440×900, DPR 1 장면을 시각별 120회 측정했다. 프레임 사이에는 requestAnimationFrame으로 대기하고 기존 장면 RAF는 화면 밖으로 옮겨 정지시켰다. draw의 CPU 제출 비용이며 GPU 완료·화면 표시 시간은 포함하지 않는다. 오디오·별도 브라우저 검사는 성능 계측과 동시에 실행하지 않았다.

- GPU 헤디드 렌더러: `{gpu['renderer']}`.
- 소프트웨어 헤드리스 렌더러: `{cpu['renderer']}`.

| 곡 시각(s) | GPU 평균(ms) | GPU p95(ms) | 소프트웨어 평균(ms) | 소프트웨어 p95(ms) |
|---|---:|---:|---:|---:|
{rows}

**부분 통과**: GPU 평균은 모든 표본에서 8ms 이하다. 그러나 GPU p95는 일부 구간에서 8ms를 넘고 소프트웨어도 8ms를 넘으므로 모든 프레임의 8ms 상한을 달성했다고 판정하지 않는다. 이 데스크톱 GPU 수치로 모바일 성능을 보증하지 않는다. 소프트웨어 바닥 합성과 GPU 간헐 지연은 남은 성능 과제다. 초기 프레임 캐시 생성 비용은 별도 첫 실행이며 이 표는 워밍업 후 값이다.

## 동작 검증

- 전체 self-check 10개와 `git diff --check` 통과.
- 정본의 의도된 차이를 보정한 PC 7개 시각: RGB 차이가 2를 넘는 변경 픽셀 0%, 최대 채널 차이 1/255. 정본 수식·색·시간을 유지했다. 바닥 잘라내기/클리핑 후보는 픽셀 차이가 생겨 채택하지 않았다.
- 평일 장면·음악 요청 0. 자동재생 허용과 실제 정책 차단→터치 시작, 저장 볼륨·음소거, 이전/다음, 자정 재판정·정리를 Chromium에서 검증했다.
- 모바일 390×844·412×915·360×800 레이아웃과 컨트롤/안내 배치 확인. 실제 Safari 검증은 아니다.
- Web Audio 곡 경계 3회: 경계 앞뒤 80ms씩의 출력 샘플을 원본 PCM과 비교해 차이 허용값 1e-5를 넘는 샘플 0. 마지막 경계는 메인 스레드를 1초 막은 상태로 검사했다. Gain의 float32 반올림 오차만 남았으며 앱이 추가하는 공백은 없다. 원본 음원에 포함된 침묵·페이드 자체를 제거한 검사는 아니다.
- 일시정지/탐색/곡 선택은 예약 소스와 타이머를 취소한다. 110.125초 정지 탐색 오차 0. destroy/자정 후 생일 Audio·AudioContext·blob·RAF·예약 소스·폴링 타이머 0을 확인했다.

## 곡선·리소스와 미확인 사항

인계 문서의 곡선 충돌 해결 지시에 따라 .03→.30(3초), 2.4→1.0(17.14~18.64초)의 양 끝 값을 유지하고 quadratic ease-out으로 통일했다. 기존 선형 표본과 달리 1.5초는 .2325, 17.2초는 2.29024다. 점등 전파 중 외부 CSS brightness는 .30이며 내부 태양 중심 마스크가 밝기를 합성한다.

첫 곡은 스트리밍하면서 두 곡을 blob/PCM으로 준비하고 AudioContext 시각에 출력을 교체한다. 디코드 뒤에는 현재 곡과 다음 두 곡을 샘플 경계에 예약한다. 재생·탐색 재시작에는 80ms의 예약 여유를 둔다. 48kHz 스테레오 PCM 두 곡은 약 157MiB다. Web Audio 미지원·디코드 실패의 스트리밍 대체 경로는 무공백을 보장하지 않는다.

**실제 iPhone Safari 미확인**: 자동재생 차단→첫 탭, Gain 기본 .3·음소거, 백그라운드 복귀, 주소창 높이 변화·안전영역, 긴 누르기 메뉴, 메모리 사용과 프레임 비용. 스트리밍 대체 경로의 무공백과 OS 스피커 녹음도 미확인이다. 복사 억제는 우연한 가져가기를 어렵게 하는 장벽이며 완전한 차단이 아니다.

## 재실행

```powershell
Get-ChildItem src/frontend/js/*.selfcheck.mjs | ForEach-Object {{ node $_.FullName }}
python scripts/verify_birthday_music.py
python scripts/verify_birthday_lifecycle.py
python scripts/compare_birthday_pixels.py
python scripts/verify_birthday_addendum.py
python scripts/verify_birthday_gapless.py
python scripts/verify_birthday_performance.py --headed
python scripts/verify_birthday_performance.py
```

브라우저 검사는 서로 다른 포트를 쓰지만 성능 검사는 단독으로 실행한다. Python Playwright/Chromium·Pillow·numpy가 필요하다. 기존 캡처 검사는 명세의 운영자 PC handoff 자료를 사용한다. 새 성능/음향 검사는 기본적으로 임시 폴더 `birthday-verify-third`에 JSON을 기록하며 `BIRTHDAY_VERIFY_OUT` 환경변수로 바꿀 수 있다. 제품 소스에는 전역 디버그 훅이 없다. 테스트에서만 응답을 계측한다. 상세 산출물과 커밋 목록은 지시된 handoff `REPORT.md`의 「3차 결과」에 기록한다.
'''
(D/'docs/BIRTHDAY_MUSIC_SCENE_VERIFICATION.md').write_text(doc,encoding='utf8',newline='\n')
p=D/'docs/BIRTHDAY_SKIN.md';s=p.read_text(encoding='utf8');s+='\n최종 성능 표·통과 범위·실기기 미확인 목록은 [3차 검증](BIRTHDAY_MUSIC_SCENE_VERIFICATION.md)을 따른다. GPU 평균 8ms 기준은 충족했으나 일부 p95와 소프트웨어 렌더링은 기준을 넘었다. 전체 출시 기준 통과로 처리하지 않는다.\n';p.write_text(s,encoding='utf8',newline='\n')
p=D/'docs/VERSION.md';s=p.read_text(encoding='utf8');s=s.replace('CPU 제출 비용과 픽셀 차이의 최종 수치는 REPORT.md 「3차 결과」를 따른다.', 'GPU 평균 CPU 제출 비용은 0.72~3.76ms지만 일부 p95는 8ms를 넘었다. 최종 표·픽셀 비교·실기기 미확인 목록은 `BIRTHDAY_MUSIC_SCENE_VERIFICATION.md`와 REPORT.md 「3차 결과」를 따른다.');p.write_text(s,encoding='utf8',newline='\n')
m=json.loads((B/'manifest.json').read_text(encoding='utf8'))
for p in D.rglob('*'):
 if p.is_file():
  n=p.relative_to(D).as_posix();m[n]=hashlib.sha256((R/n).read_bytes()).hexdigest() if (R/n).exists() else None
(B/'manifest.json').write_text(json.dumps(m,indent=2),encoding='utf8')
print(rows)
