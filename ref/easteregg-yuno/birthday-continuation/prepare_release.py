from pathlib import Path
import re
R=Path(r'C:/Users/User/Documents/pyworks/mewtype-scheduler-worktrees/v4/feat-birthday-music-scene')
def change(name,fn):
 p=R/name;s=p.read_text(encoding='utf-8-sig');p.write_text(fn(s),encoding='utf8',newline='\n')
change('src/frontend/js/config.js',lambda s:s.replace('APP_VERSION = "v4.10.0"','APP_VERSION = "v4.11.0"').replace('APP_DATE = "2026-10-31"','APP_DATE = "2026-11-01"'))
change('README.md',lambda s:s.replace('현재 버전: v4.10.0 (마이너 · 2026-10-31)','현재 버전: v4.11.0 (마이너 · 2026-11-01)').replace('운영 모니터 페이지 진입(`monitor.html`)','운영 모니터 페이지 진입(`monitor.html`), 유노 생일 음악 장면·인트로와 모니터 방향 입력(↑↑↓↓←→←→ → EXT → APP)'))
change('CLAUDE.md',lambda s:s.replace('현재 버전 = v4.10.0 (마이너, 2026-10-31)','현재 버전 = v4.11.0 (마이너, 2026-11-01)').replace('현재 버전 상수는 운영자 확정 전 바꾸지 않는다.', '2026-11-01 운영자 병합·배포 승인으로 v4.11.0을 적용했다. 실기기 확인 결과는 별도로 기록한다.'))
def version(s):
 a=s.index('## 배포 전 제안');z=s.index('이 문서는 두 절이다',a);s=s[:a]+s[z:]
 i=s.index('- **v4.10.0**')
 entry='''- **v4.11.0** (마이너, 2026-11-01 — 브랜치 `feat/birthday-music-scene`, 프론트만): **유노 생일 음악 장면·일출/조명 인트로·플레이어·모니터 숨은 진입.**
  - v12 Canvas 장면과 원본 음악 2곡, 태양 일출·유노 스포트라이트·17.14초 태양 중심 점등 전파, 기기별 배치·음악 컨트롤·인코딩 사인·복사 억제를 추가했다.
  - 첫 스트리밍 뒤 Web Audio 예약 재생으로 연결한다. 스테레오 3경계 샘플 비교·메인 스레드 1초 정지에서도 추가 공백 0. GPU 가속 600프레임은 평균 0.83~3.24ms, 최대 4.8ms. 소프트웨어는 평균 17.38~32.81ms로 8ms를 넘는다.
  - 모니터 초기화 확인창에서 ↑↑↓↓←→←→를 드래그/터치하면 입력한 변이 빛나고 초기화 버튼이 빛나며 창이 닫힌다. EXT → APP으로 생일 화면에 진입하며 저장값을 지우지 않는다.
  - **검증**: self-check 11개, PC 정본 7시점 변경 픽셀 0%(최대 차이 1/255), 자연 곡 전환·정리·자동재생, PC/Android 터치 명령·가장자리 빛·시간 만료·iframe 교체 검사 통과. 상세는 `docs/BIRTHDAY_MUSIC_SCENE_VERIFICATION.md`.
  - **배포 진행**: 2026-11-01 운영자가 병합·배포를 승인했다. 병합 커밋·태그·Vercel 배포 식별자는 완료 뒤 기록한다. 롤백 = `fc6f8ca`(v4.10.0 배포 완료 main). 백엔드 변경 없음.
  - **미확인**: 실제 삼성 브라우저·iPhone Safari의 음향·터치·주소창/안전영역·메모리·성능. 운영자가 모니터 페이지를 통해 후속 확인한다. 번호가 확정되지 않아 보류했던 이전 문서의 배포 금지는 이번 운영자 지시로 해제됐다.
'''
 return s[:i]+entry+s[i:]
change('docs/VERSION.md',version)
change('docs/BIRTHDAY_SKIN.md',lambda s:s.replace('음악 장면 후속 구현(배포 전):','음악 장면 후속 구현(v4.11.0, 2026-11-01 병합·배포 승인):').replace('v4.11.0은 제안이며 번호 확정·병합·배포는 운영자 결정이다.', '2026-11-01 운영자 승인으로 v4.11.0 병합·배포를 진행한다. 실기기 확인은 운영자가 수행한다.').replace('이 연결도 배포·푸시 전 상태다.', '이 연결도 v4.11.0에 포함해 운영자 승인으로 배포한다.'))
change('docs/BIRTHDAY_MUSIC_SCENE_VERIFICATION.md',lambda s:s.replace('브랜치 `feat/birthday-music-scene`. 구현과 로컬 검증 결과이며 배포 승인이 아니다. 버전은 v4.11.0 제안만 유지하며 현재 버전 상수·푸시·병합·배포는 변경하지 않았다.', '브랜치 `feat/birthday-music-scene`의 구현과 로컬 검증 기록이다. 2026-11-01 운영자가 병합·배포를 승인해 v4.11.0으로 진행한다. 아래 미확인 실기기 검증은 운영자가 후속 확인하며, 병합·배포 식별자는 `docs/VERSION.md`에 기록한다.'))
print('v4.11.0 / 2026-11-01 버전 표기와 승인 상태 반영')
